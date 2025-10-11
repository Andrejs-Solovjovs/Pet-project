package main

import (
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type Mode string

const (
	ModeExt      Mode = "ext"
	ModeDate     Mode = "date"
	ModeCategory Mode = "category"
)

type Op struct {
	Src       string `json:"src"`
	Dst       string `json:"dst"`
	Action    string `json:"action"` // "move" | "copy"
	SizeBytes int64  `json:"size_bytes"`
}

type LogFile struct {
	CreatedAt time.Time `json:"created_at"`
	By        Mode      `json:"by"`
	SrcRoot   string    `json:"src_root"`
	DstRoot   string    `json:"dst_root"`
	Ops       []Op      `json:"ops"`
}

func main() {
	var (
		src        = flag.String("src", ".", "Папка-источник (сканировать здесь)")
		dst        = flag.String("dst", "", "Папка-назначение (по умолчанию = src)")
		byStr      = flag.String("by", "category", "Стратегия группировки: ext | date | category")
		dry        = flag.Bool("dry", false, "Режим предпросмотра (ничего не меняет)")
		copyFlag   = flag.Bool("copy", false, "Копировать вместо перемещения")
		lowercase  = flag.Bool("lowercase", true, "Приводить имена папок (по расширениям) к нижнему регистру")
		logPath    = flag.String("log", "", "Путь для сохранения лога операций (по умолчанию auto)")
		undoLog    = flag.String("undo", "", "Путь к лог-файлу для отката перемещений")
		excludeDst = flag.Bool("exclude-dst", true, "Исключать папку назначения из обхода")
	)
	flag.Parse()

	// Режим отката
	if *undoLog != "" {
		if err := undo(*undoLog); err != nil {
			fail("undo error: %v", err)
		}
		fmt.Println("✅ Undo завершён.")
		return
	}

	// Нормализация путей
	srcAbs, err := filepath.Abs(*src)
	check(err)
	dstAbs := srcAbs
	if *dst != "" {
		dstAbs, err = filepath.Abs(*dst)
		check(err)
	}

	by := Mode(strings.ToLower(*byStr))
	if by != ModeExt && by != ModeDate && by != ModeCategory {
		fail("неизвестный режим --by: %s (используй: ext | date | category)", *byStr)
	}

	// Создадим папку назначения
	if err := os.MkdirAll(dstAbs, 0755); err != nil {
		fail("mkdir dst: %v", err)
	}

	ops := []Op{}
	err = filepath.WalkDir(srcAbs, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			// пропускаем проблемные файлы/папки
			fmt.Printf("warn: %s\n", err)
			return nil
		}
		// Пропускаем саму папку назначения (чтобы не зациклиться)
		if *excludeDst {
			if samePath(path, dstAbs) || strings.HasPrefix(path+string(os.PathSeparator), dstAbs+string(os.PathSeparator)) {
				if path != srcAbs {
					return filepath.SkipDir
				}
			}
		}
		// Пропускаем папки
		if d.IsDir() {
			return nil
		}
		// Пропускаем уже разложенные копии (если dst внутри src)
		if strings.HasPrefix(path+string(os.PathSeparator), dstAbs+string(os.PathSeparator)) {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			fmt.Printf("warn: stat %s: %v\n", path, err)
			return nil
		}
		if info.Size() == 0 {
			// Можно пропускать нулевые файлы по желанию
			// return nil
		}

		relTarget, err := buildTargetRelPath(by, path, info, *lowercase)
		if err != nil {
			fmt.Printf("warn: target for %s: %v\n", path, err)
			return nil
		}
		dstPath := filepath.Join(dstAbs, relTarget, filepath.Base(path))

		if samePath(path, dstPath) {
			// уже на месте
			return nil
		}

		action := "move"
		if *copyFlag {
			action = "copy"
		}

		fmt.Printf("%s: %s\n  -> %s\n", strings.ToUpper(action), path, dstPath)

		if !*dry {
			// создаём родительскую папку
			if err := os.MkdirAll(filepath.Dir(dstPath), 0755); err != nil {
				fmt.Printf("error: mkdir %s: %v\n", filepath.Dir(dstPath), err)
				return nil
			}
			// выполняем
			if *copyFlag {
				if err := copyFile(path, dstPath); err != nil {
					fmt.Printf("error: copy %s -> %s: %v\n", path, dstPath, err)
					return nil
				}
			} else {
				// перемещение с попыткой rename, при неудаче — копия+удаление
				if err := moveFile(path, dstPath); err != nil {
					fmt.Printf("error: move %s -> %s: %v\n", path, dstPath, err)
					return nil
				}
			}
			ops = append(ops, Op{
				Src:       path,
				Dst:       dstPath,
				Action:    action,
				SizeBytes: info.Size(),
			})
		}

		return nil
	})
	check(err)

	if *dry {
		fmt.Printf("\n💡 DRY-RUN завершён: операций запланировано: %d\n", len(ops))
		return
	}

	// Сохраняем лог
	if len(ops) > 0 {
		if *logPath == "" {
			*logPath = filepath.Join(dstAbs, "organizer_log_"+time.Now().Format("20060102_150405")+".json")
		}
		lf := LogFile{
			CreatedAt: time.Now(),
			By:        by,
			SrcRoot:   srcAbs,
			DstRoot:   dstAbs,
			Ops:       ops,
		}
		if err := saveLog(*logPath, lf); err != nil {
			fmt.Printf("warn: не удалось сохранить лог %s: %v\n", *logPath, err)
		} else {
			fmt.Printf("\n📝 Лог операций: %s\n", *logPath)
			fmt.Println("↩️  Для отката: file-organizer --undo \"ПУТЬ_К_ЛОГУ.json\"")
		}
	}

	fmt.Printf("\n✅ Готово. Выполнено операций: %d\n", len(ops))
}

func buildTargetRelPath(by Mode, fullPath string, info fs.FileInfo, lowercase bool) (string, error) {
	switch by {
	case ModeExt:
		ext := strings.TrimPrefix(strings.ToLower(filepath.Ext(fullPath)), ".")
		if ext == "" {
			ext = "noext"
		}
		if lowercase {
			return ext, nil
		}
		return strings.ToUpper(ext), nil
	case ModeDate:
		t := info.ModTime()
		year := fmt.Sprintf("%04d", t.Year())
		month := fmt.Sprintf("%02d", int(t.Month()))
		return filepath.Join(year, month), nil
	case ModeCategory:
		ext := strings.TrimPrefix(strings.ToLower(filepath.Ext(fullPath)), ".")
		cat := extCategory(ext)
		return cat, nil
	default:
		return "", errors.New("unknown mode")
	}
}

func extCategory(ext string) string {
	if ext == "" {
		return "Other"
	}
	images := map[string]bool{"jpg": true, "jpeg": true, "png": true, "gif": true, "bmp": true, "webp": true, "tiff": true, "heic": true, "svg": true}
	video := map[string]bool{"mp4": true, "mkv": true, "mov": true, "avi": true, "webm": true, "wmv": true}
	audio := map[string]bool{"mp3": true, "wav": true, "flac": true, "aac": true, "ogg": true, "m4a": true}
	docs := map[string]bool{"pdf": true, "doc": true, "docx": true, "xls": true, "xlsx": true, "ppt": true, "pptx": true, "txt": true, "md": true, "rtf": true}
	archives := map[string]bool{"zip": true, "rar": true, "7z": true, "tar": true, "gz": true}
	code := map[string]bool{"go": true, "py": true, "js": true, "ts": true, "java": true, "cs": true, "cpp": true, "c": true, "rb": true, "php": true, "html": true, "css": true, "json": true, "xml": true, "yml": true, "yaml": true, "sql": true, "sh": true, "ps1": true}

	switch {
	case images[ext]:
		return "Images"
	case video[ext]:
		return "Video"
	case audio[ext]:
		return "Audio"
	case docs[ext]:
		return "Docs"
	case archives[ext]:
		return "Archives"
	case code[ext]:
		return "Code"
	default:
		return "Other"
	}
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer func() {
		_ = out.Close()
	}()
	if _, err := io.Copy(out, in); err != nil {
		return err
	}
	return out.Sync()
}

// moveFile пытается os.Rename, при неудаче (например, между разными дисками) делает copy+remove
func moveFile(src, dst string) error {
	if err := os.Rename(src, dst); err == nil {
		return nil
	}
	if err := copyFile(src, dst); err != nil {
		return err
	}
	return os.Remove(src)
}

func saveLog(path string, data LogFile) error {
	b, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0644)
}

func loadLog(path string) (LogFile, error) {
	var lf LogFile
	b, err := os.ReadFile(path)
	if err != nil {
		return lf, err
	}
	err = json.Unmarshal(b, &lf)
	return lf, err
}

func undo(logPath string) error {
	lf, err := loadLog(logPath)
	if err != nil {
		return err
	}
	// Откатываем только перемещения (копии не трогаем, чтобы случайно не удалить нужные файлы)
	count := 0
	for i := len(lf.Ops) - 1; i >= 0; i-- {
		op := lf.Ops[i]
		if op.Action != "move" {
			fmt.Printf("skip copy: %s\n", op.Dst)
			continue
		}
		// на случай, если исходник существует, а dst — нет
		_ = os.MkdirAll(filepath.Dir(op.Src), 0755)
		if err := moveFile(op.Dst, op.Src); err != nil {
			fmt.Printf("undo error: %s <- %s: %v\n", op.Src, op.Dst, err)
			continue
		}
		fmt.Printf("UNDO: %s <- %s\n", op.Src, op.Dst)
		count++
	}
	fmt.Printf("UNDO завершён. Откатили: %d операций\n", count)
	return nil
}

func samePath(a, b string) bool {
	ra := filepath.Clean(a)
	rb := filepath.Clean(b)
	if strings.EqualFold(ra, rb) {
		return true
	}
	return false
}

func check(err error) {
	if err != nil {
		fail("%v", err)
	}
}

func fail(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "error: "+format+"\n", a...)
	os.Exit(1)
}
