package main

import (
	"bufio"
	"fmt"
	"math/rand"
	"os"
	"strings"
	"time"
)

type Country struct {
	ISO  string
	Name string
}

var countries = []Country{
	{"US", "United States"},
	{"CA", "Canada"},
	{"BR", "Brazil"},
	{"AR", "Argentina"},
	{"MX", "Mexico"},
	{"GB", "United Kingdom"},
	{"FR", "France"},
	{"DE", "Germany"},
	{"ES", "Spain"},
	{"IT", "Italy"},
	{"SE", "Sweden"},
	{"NO", "Norway"},
	{"FI", "Finland"},
	{"PL", "Poland"},
	{"UA", "Ukraine"},
	{"TR", "Türkiye"},
	{"EG", "Egypt"},
	{"ZA", "South Africa"},
	{"IN", "India"},
	{"CN", "China"},
	{"JP", "Japan"},
	{"KR", "South Korea"},
	{"AU", "Australia"},
	{"NZ", "New Zealand"},
}

func flagEmoji(iso string) string {
	iso = strings.ToUpper(iso)
	// Regional Indicator Symbol Letter A starts at 0x1F1E6
	runes := []rune{}
	for _, ch := range iso {
		runes = append(runes, rune(0x1F1E6+(ch-'A')))
	}
	return string(runes)
}

func main() {
	rand.Seed(time.Now().UnixNano())
	reader := bufio.NewReader(os.Stdin)

	fmt.Println("🌍 GeoQuiz — угадай страну по флагу!")
	fmt.Println("Введите ответ на английском (например, France). Для выхода — пустой ввод.\n")

	score, rounds := 0, 0

	for {
		// 1) выбираем страну-ответ
		ans := countries[rand.Intn(len(countries))]

		// 2) собираем варианты (1 правильный + 3 случайных)
		options := []Country{ans}
		used := map[string]bool{ans.ISO: true}
		for len(options) < 4 {
			c := countries[rand.Intn(len(countries))]
			if !used[c.ISO] {
				options = append(options, c)
				used[c.ISO] = true
			}
		}
		// перемешиваем варианты
		rand.Shuffle(len(options), func(i, j int) { options[i], options[j] = options[j], options[i] })

		// 3) задаём вопрос
		fmt.Printf("Флаг: %s  — какая это страна?\n", flagEmoji(ans.ISO))
		for i, o := range options {
			fmt.Printf("  %d) %s\n", i+1, o.Name)
		}
		fmt.Print("Ваш ответ (1-4 или имя страны): ")

		input, _ := reader.ReadString('\n')
		input = strings.TrimSpace(input)
		if input == "" {
			break
		}

		rounds++

		// проверка по номеру
		ok := false
		switch input {
		case "1", "2", "3", "4":
			idx := int(input[0] - '1')
			if idx >= 0 && idx < len(options) && options[idx].ISO == ans.ISO {
				ok = true
			}
		default:
			// проверка по названию (без регистра)
			if strings.EqualFold(input, ans.Name) {
				ok = true
			}
		}

		if ok {
			score++
			fmt.Println("✅ Верно!")
		} else {
			fmt.Printf("❌ Неверно. Правильно: %s\n", ans.Name)
		}
		fmt.Printf("Счёт: %d/%d\n\n", score, rounds)
	}

	fmt.Printf("Итог: %d/%d. Спасибо за игру!\n", score, rounds)
}
