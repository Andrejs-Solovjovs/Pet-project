import os
import json
import re
import csv
import datetime as dt
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from collections import defaultdict, Counter

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# ---------------------------
# Ошибки / классификаторы
# ---------------------------
RE_NOT_PRESENT = re.compile(r"ID1c\s+(\S+)\s+not\s+present\b", re.IGNORECASE)
RE_CHECK_DATA = re.compile(r"check the data", re.IGNORECASE)


def read_text_file(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def loads_json_loose(text: str):
    """
    Парсим JSON даже если есть мусор ДО/ПОСЛЕ JSON.
    Берём первый валидный JSON-объект/массив из файла.
    """
    s = (text or "").strip()
    if not s:
        raise json.JSONDecodeError("Empty input", s, 0)

    dec = json.JSONDecoder()

    # 1) как есть
    try:
        obj, _ = dec.raw_decode(s)
        return obj
    except json.JSONDecodeError:
        pass

    # 2) ищем начало JSON
    first_curly = s.find("{")
    first_square = s.find("[")
    positions = [p for p in (first_curly, first_square) if p != -1]
    if not positions:
        raise json.JSONDecodeError("No JSON start found", s, 0)

    start = min(positions)
    sub = s[start:]
    obj, _ = dec.raw_decode(sub)  # raw_decode допускает хвост после JSON
    return obj


def channel_from_filename(filename: str) -> str:
    """
    ALL/IN/OUT логика будет работать поверх этих каналов:
    - IN_*  -> IN
    - OUT_* -> OUT
    - иначе -> OTHER
    """
    base = os.path.basename(filename)
    up = base.upper()
    if up.startswith("IN_"):
        return "IN"
    if up.startswith("OUT_"):
        return "OUT"
    return "OTHER"


def classify_error_line(line: str):
    """
    Возвращает (code, id1c_or_none, human)
    """
    if not isinstance(line, str):
        return ("UNKNOWN", None, "Неизвестная ошибка (не строка).")

    m = RE_NOT_PRESENT.search(line)
    if m:
        id1c = m.group(1)
        return ("NOT_PRESENT", id1c, "Товар не найден у получателя (в базе нет записи по этому ID1c).")

    return ("UNCLASSIFIED", None, "Сообщение об ошибке не распознано (нужен шаблон).")


def analyze_file(path: str):
    """
    Возвращает:
    {
      status: success|empty|error,
      entity: str|None,
      errors: [(code, id1c, human, raw), ...]
    }
    """
    content = read_text_file(path).strip()
    if not content:
        return {
            "status": "error",
            "entity": None,
            "errors": [("EMPTY_FILE", None, "Файл пустой.", "")]
        }

    try:
        data = loads_json_loose(content)
    except json.JSONDecodeError:
        if RE_CHECK_DATA.search(content):
            return {
                "status": "error",
                "entity": None,
                "errors": [("BAD_PAYLOAD", None, "Пакет данных отклонён: 'check the data' (нет детализации по товарам).", "check the data")]
            }
        return {
            "status": "error",
            "entity": None,
            "errors": [("NOT_JSON", None, "Файл не содержит валидный JSON.", content[:250])]
        }

    entity = None
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                entity = k
                break

    if isinstance(data, dict) and "Error" in data:
        errs = data.get("Error") or []
        parsed = []
        for e in errs:
            code, id1c, human = classify_error_line(e)
            parsed.append((code, id1c, human, e if isinstance(e, str) else str(e)))
        return {"status": "error", "entity": entity, "errors": parsed}

    if entity and isinstance(data.get(entity), list) and len(data[entity]) == 0:
        return {"status": "empty", "entity": entity, "errors": []}

    return {"status": "success", "entity": entity, "errors": []}


def make_empty_stats(root_dir: str, channel_name: str) -> dict:
    return {
        "root": root_dir,
        "channel": channel_name,
        "files_total": 0,
        "files_ok": 0,
        "files_empty": 0,
        "files_error": 0,
        "errors_total": 0,
        "errors_by_code": Counter(),
        "errors_by_day": Counter(),    # YYYY-MM-DD -> count
        "top_id1c": Counter(),         # ID1c -> count
        "errors_examples": defaultdict(list),  # code -> few examples
        "sample_unclassified": [],     # raw
    }


def update_stats(stats: dict, file_path: str, file_result: dict):
    stats["files_total"] += 1

    st = file_result["status"]
    if st == "success":
        stats["files_ok"] += 1
    elif st == "empty":
        stats["files_empty"] += 1
    else:
        stats["files_error"] += 1

    if file_result["errors"]:
        # дату считаем по mtime файла (как у тебя сейчас)
        day = dt.date.fromtimestamp(os.path.getmtime(file_path)).isoformat()

        for (code, id1c, human, raw) in file_result["errors"]:
            stats["errors_total"] += 1
            stats["errors_by_code"][code] += 1
            stats["errors_by_day"][day] += 1
            if id1c:
                stats["top_id1c"][id1c] += 1

            # примеры
            if len(stats["errors_examples"][code]) < 5:
                stats["errors_examples"][code].append(f"{human} | {str(raw)[:220]}")

            if code == "UNCLASSIFIED" and len(stats["sample_unclassified"]) < 20:
                stats["sample_unclassified"].append(str(raw)[:250])


def scan_logs_split(root_dir: str):
    """
    Сканирует все .txt/.json рекурсивно и возвращает 3 stats:
      - ALL (всё)
      - IN
      - OUT
    """
    stats_all = make_empty_stats(root_dir, "ALL")
    stats_in = make_empty_stats(root_dir, "IN")
    stats_out = make_empty_stats(root_dir, "OUT")

    for r, _, files in os.walk(root_dir):
        for fn in files:
            if not fn.lower().endswith((".txt", ".json")):
                continue
            path = os.path.join(r, fn)

            ch = channel_from_filename(fn)
            res = analyze_file(path)

            update_stats(stats_all, path, res)
            if ch == "IN":
                update_stats(stats_in, path, res)
            elif ch == "OUT":
                update_stats(stats_out, path, res)
            else:
                # OTHER включён только в ALL (чтобы не шуметь вкладки)
                pass

    return stats_all, stats_in, stats_out


def summary_text_all(stats_all: dict, stats_in: dict, stats_out: dict) -> str:
    return (
        f"Папка: {stats_all['root']}\n"
        f"Файлов всего: {stats_all['files_total']}\n"
        f"Успешных: {stats_all['files_ok']} | Пустых: {stats_all['files_empty']} | С ошибками: {stats_all['files_error']}\n"
        f"Ошибок всего (по строкам Error/текстовым): {stats_all['errors_total']}\n"
        f"IN ошибок: {stats_in['errors_total']} | OUT ошибок: {stats_out['errors_total']}\n"
        f"Топ-товаров (ID1c) с ошибками: {len(stats_all['top_id1c'])}\n"
    )


def summary_text(stats: dict) -> str:
    return (
        f"Папка: {stats['root']}\n"
        f"Канал: {stats['channel']}\n"
        f"Файлов всего: {stats['files_total']}\n"
        f"Успешных: {stats['files_ok']} | Пустых: {stats['files_empty']} | С ошибками: {stats['files_error']}\n"
        f"Ошибок всего (по строкам Error/текстовым): {stats['errors_total']}\n"
        f"Топ-товаров (ID1c) с ошибками: {len(stats['top_id1c'])}\n"
    )


def details_text(stats: dict) -> str:
    lines = []
    lines.append("Примеры ошибок по типам (до 5 примеров на тип):\n")
    for code, examples in stats["errors_examples"].items():
        lines.append(f"\n[{code}]")
        for ex in examples:
            lines.append(f" - {ex}")

    if stats["top_id1c"]:
        lines.append("\n\nТОП 20 товаров (ID1c) по числу ошибок:")
        for id1c, cnt in stats["top_id1c"].most_common(20):
            lines.append(f" - {id1c}: {cnt}")

    if stats["sample_unclassified"]:
        lines.append("\n\nUNCLASSIFIED (нужно добавить шаблон распознавания):")
        for s in stats["sample_unclassified"][:20]:
            lines.append(f" - {s}")

    return "\n".join(lines)


# ---------------------------
# UI: Tab frame
# ---------------------------
class StatsTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master)

        self.stats = None
        self.tree_codes = []

        # верх: summary
        self.lbl_summary = tk.Label(self, justify="left", font=("Segoe UI", 10))
        self.lbl_summary.pack(fill="x", padx=10, pady=8, anchor="w")

        # середина: таблица + детали + графики
        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=10)

        left = tk.Frame(mid)
        left.pack(side="left", fill="both", expand=False)

        right = tk.Frame(mid)
        right.pack(side="right", fill="both", expand=True)

        # таблица типов ошибок
        self.tree = ttk.Treeview(left, columns=("col",), show="headings", height=12)
        self.tree.heading("col", text="Тип ошибки — Кол-во")
        self.tree.column("col", width=360, anchor="w")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self.on_select_code)

        # детали
        self.txt_details = tk.Text(left, height=18, wrap="word")
        self.txt_details.pack(fill="both", expand=True, pady=8)

        # графики
        self.fig = Figure(figsize=(7.0, 4.8), dpi=100)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def set_stats(self, stats: dict, summary_override: str = None):
        self.stats = stats
        if not stats:
            self.lbl_summary.config(text="")
            return

        self.lbl_summary.config(text=summary_override if summary_override is not None else summary_text(stats))

        # таблица
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_codes = []
        for code, cnt in stats["errors_by_code"].most_common():
            self.tree.insert("", "end", values=(f"{code} — {cnt}",))
            self.tree_codes.append(code)

        # детали общие
        self.txt_details.delete("1.0", "end")
        self.txt_details.insert("1.0", details_text(stats))

        # графики
        self.draw_charts(stats)

    def draw_charts(self, stats: dict):
        # 1) ТОП-10 типов ошибок
        self.ax1.clear()
        codes = [c for c, _ in stats["errors_by_code"].most_common(10)]
        counts = [stats["errors_by_code"][c] for c in codes]
        if codes:
            self.ax1.bar(codes, counts)
            self.ax1.set_title("ТОП-10 типов ошибок")
            self.ax1.tick_params(axis="x", rotation=30)
        else:
            self.ax1.set_title("Нет ошибок для графика")

        # 2) Ошибки по дням
        self.ax2.clear()
        days = sorted(stats["errors_by_day"].keys())
        day_counts = [stats["errors_by_day"][d] for d in days]
        if days:
            self.ax2.plot(days, day_counts, marker="o")
            self.ax2.set_title("Ошибки по дням (по времени файла)")
            self.ax2.tick_params(axis="x", rotation=30)
        else:
            self.ax2.set_title("Нет данных по дням")

        self.fig.tight_layout()
        self.canvas.draw()

    def on_select_code(self, _event):
        if not self.stats:
            return
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self.tree_codes):
            return

        code = self.tree_codes[idx]
        examples = self.stats["errors_examples"].get(code, [])

        text = [
            f"Тип: {code}",
            f"Количество: {self.stats['errors_by_code'].get(code, 0)}",
            "",
            "Примеры:"
        ]
        for e in examples:
            text.append(f" - {e}")

        # для UNCLASSIFIED — добавим подсказку
        if code == "UNCLASSIFIED" and self.stats.get("sample_unclassified"):
            text.append("")
            text.append("UNCLASSIFIED (сырые строки, чтобы добавить шаблон):")
            for s in self.stats["sample_unclassified"][:20]:
                text.append(f" - {s}")

        self.txt_details.delete("1.0", "end")
        self.txt_details.insert("1.0", "\n".join(text))


# ---------------------------
# Main app
# ---------------------------
class StatsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Log Analyzer — Статистика по папке (ALL / IN / OUT)")
        self.geometry("1150x760")

        self.default_path = r"T:\ExchangeLogs\newSite"
        self.path_var = tk.StringVar(value=self.default_path)

        self.stats_all = None
        self.stats_in = None
        self.stats_out = None

        top = tk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        tk.Label(top, text="Папка с логами:").pack(side="left")
        tk.Entry(top, textvariable=self.path_var, width=75).pack(side="left", padx=8)
        tk.Button(top, text="Выбрать...", command=self.pick_dir).pack(side="left")
        tk.Button(top, text="Сканировать", command=self.run_scan).pack(side="left", padx=8)
        tk.Button(top, text="Экспорт CSV (ALL)", command=self.export_csv_all).pack(side="left")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_all = StatsTab(self.nb)
        self.tab_in = StatsTab(self.nb)
        self.tab_out = StatsTab(self.nb)

        self.nb.add(self.tab_all, text="ALL")
        self.nb.add(self.tab_in, text="IN")
        self.nb.add(self.tab_out, text="OUT")

    def pick_dir(self):
        p = filedialog.askdirectory(title="Выберите папку с логами")
        if p:
            self.path_var.set(p)

    def run_scan(self):
        root = self.path_var.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror("Ошибка", "Папка не найдена. Проверьте путь или выберите папку.")
            return

        # минимальный UI feedback
        self.tab_all.lbl_summary.config(text="Сканирую... (если логов много, может занять время)")
        self.tab_in.lbl_summary.config(text="")
        self.tab_out.lbl_summary.config(text="")
        self.update_idletasks()

        all_stats, in_stats, out_stats = scan_logs_split(root)

        self.stats_all, self.stats_in, self.stats_out = all_stats, in_stats, out_stats

        self.tab_all.set_stats(all_stats, summary_override=summary_text_all(all_stats, in_stats, out_stats))
        self.tab_in.set_stats(in_stats)
        self.tab_out.set_stats(out_stats)

        # переключимся на ALL
        self.nb.select(self.tab_all)

    def export_csv_all(self):
        if not self.stats_all:
            messagebox.showinfo("Нет данных", "Сначала нажмите 'Сканировать'.")
            return

        path = filedialog.asksaveasfilename(
            title="Сохранить CSV (ALL)",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return

        st = self.stats_all
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")

                w.writerow(["root", st["root"]])
                w.writerow(["channel", st["channel"]])
                w.writerow(["files_total", st["files_total"]])
                w.writerow(["files_ok", st["files_ok"]])
                w.writerow(["files_empty", st["files_empty"]])
                w.writerow(["files_error", st["files_error"]])
                w.writerow(["errors_total", st["errors_total"]])
                w.writerow([])

                w.writerow(["errors_by_code"])
                w.writerow(["code", "count"])
                for code, cnt in st["errors_by_code"].most_common():
                    w.writerow([code, cnt])
                w.writerow([])

                w.writerow(["errors_by_day"])
                w.writerow(["day", "count"])
                for day in sorted(st["errors_by_day"].keys()):
                    w.writerow([day, st["errors_by_day"][day]])
                w.writerow([])

                w.writerow(["top_id1c"])
                w.writerow(["id1c", "count"])
                for id1c, cnt in st["top_id1c"].most_common(500):
                    w.writerow([id1c, cnt])

            messagebox.showinfo("Готово", f"CSV сохранён:\n{path}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))


if __name__ == "__main__":
    StatsApp().mainloop()
