import pandas as pd
import requests
from datetime import datetime

INPUT_EXCEL = "Info.xlsx"
OUTPUT_EXCEL = "report.xlsx"
COLUMN_NAME = "Артикул производителя"
BASE_URL = "https://lvt.mstarproject.com/search_text/"
TIMEOUT = 20
HEADER_ROW = 7

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://lvt.mstarproject.com/",
    "Connection": "keep-alive",
}

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

    for i, article in enumerate(articles, start=1):
        url = BASE_URL + article
        checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            r = s.get(url, timeout=TIMEOUT, allow_redirects=True)
            status = r.status_code
            error = ""
        except Exception as e:
            status = "ERROR"
            error = str(e)

        # ВАЖНО: если 403 — это не "бренда нет", это "доступ запрещён"
        if status == 404:
            result = "404 NOT FOUND"
        elif status == 403:
            result = "403 FORBIDDEN (blocked)"
        else:
            result = "OK"

        results.append({
            "Артикул производителя": article,
            "URL": url,
            "HTTP Status": status,
            "Result": result,
            "Error": error,
            "Checked at": checked_at
        })

        if i <= 5 or i == total or i % 50 == 0:
            print(f"[{i}/{total}] {article} -> {status}")

    pd.DataFrame(results).to_excel(OUTPUT_EXCEL, index=False)
    print(f"=== ГОТОВО === Отчет сохранён: {OUTPUT_EXCEL}")

if __name__ == "__main__":
    main()
