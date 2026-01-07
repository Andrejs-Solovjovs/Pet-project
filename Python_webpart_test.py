import pandas as pd
import requests
from datetime import datetime
from urllib.parse import quote

# ===== НАСТРОЙКИ =====
INPUT_EXCEL = "Info.xlsx"
OUTPUT_EXCEL = "report.xlsx"
HEADER_ROW = 7
COLUMN_NAME = "Артикул производителя"

BASE_URL = "https://lvt.mstarproject.com/search_text/"
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7,lv;q=0.6",
    "Referer": "https://lvt.mstarproject.com/",
    "Connection": "keep-alive",
}

# Текст "не найдено" (латышский + запасные варианты)
NOT_FOUND_TEXTS = [
    "nav atrasts",
    "не найдено",
    "ничего не найдено",
    "нет результатов",
    "no results",
]

# Сколько HTML сохранять для спорных случаев (в папку debug_html)
SAVE_DEBUG_HTML = True
DEBUG_SAVE_LIMIT = 30  # максимум файлов
# ====================


def make_url(article: str) -> str:
    # Кодируем артикул так, чтобы /, пробелы, # и т.п. не ломали URL
    encoded = quote(article, safe="")
    return BASE_URL + encoded


def main():
    print("=== START ===")
    df = pd.read_excel(INPUT_EXCEL, header=HEADER_ROW)

    if COLUMN_NAME not in df.columns:
        print(f"ОШИБКА: колонка '{COLUMN_NAME}' не найдена. Колонки: {list(df.columns)}")
        return

    articles = df[COLUMN_NAME].dropna().astype(str).str.strip()
    articles = articles[articles != ""]
    total = len(articles)
    print(f"Найдено артикулов: {total}")

    s = requests.Session()
    s.headers.update(HEADERS)

    results = []
    saved_debug = 0

    for i, article in enumerate(articles, start=1):
        url = make_url(article)
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        http_status = None
        found = "UNKNOWN"
        reason = ""
        error = ""
        final_url = ""

        try:
            r = s.get(url, timeout=TIMEOUT, allow_redirects=True)
            http_status = r.status_code
            final_url = r.url
            text = (r.text or "")
            low = text.lower()

            if http_status == 404:
                found = "NO"
                reason = "HTTP 404"
            elif http_status == 403:
                found = "BLOCKED"
                reason = "HTTP 403"
            elif http_status != 200:
                found = "UNKNOWN"
                reason = f"HTTP {http_status}"
            else:
                # 200: определяем по содержимому
                has_not_found_text = any(t in low for t in NOT_FOUND_TEXTS)

                # ВАЖНО: если "nav atrasts" встречается в шаблоне,
                # мы можем ошибиться. Поэтому если видим "не найдено",
                # сохраняем HTML для проверки (и потом уточним маркер результатов).
                if has_not_found_text:
                    found = "NO"
                    reason = "Not found text on page"
                    if SAVE_DEBUG_HTML and saved_debug < DEBUG_SAVE_LIMIT:
                        import os
                        os.makedirs("debug_html", exist_ok=True)
                        fn = f"debug_html/not_found_{i}_{quote(article, safe='')}.html"
                        with open(fn, "w", encoding="utf-8") as f:
                            f.write(text)
                        saved_debug += 1
                else:
                    found = "YES"
                    reason = "No 'not found' text"

        except Exception as e:
            http_status = "ERROR"
            found = "ERROR"
            reason = "Request error"
            error = str(e)

        results.append({
            "Артикул производителя": article,
            "URL": url,
            "Final URL": final_url,
            "HTTP Status": http_status,
            "Found": found,
            "Reason": reason,
            "Error": error,
            "Checked at": checked_at
        })

        if i <= 5 or i == total or i % 200 == 0:
            print(f"[{i}/{total}] {article} -> {http_status} ({found})")

    pd.DataFrame(results).to_excel(OUTPUT_EXCEL, index=False)
    print(f"=== ГОТОВО === Отчет сохранён: {OUTPUT_EXCEL}")
    if SAVE_DEBUG_HTML:
        print("Если были NO, HTML сохранён в папку: debug_html")


if __name__ == "__main__":
    main()
