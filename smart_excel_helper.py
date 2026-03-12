import os
import re
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from difflib import SequenceMatcher

import pandas as pd
import matplotlib.pyplot as plt


class SmartExcelHelperV2:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Умный Excel-помощник v2")
        self.root.geometry("1450x860")

        self.df_original = None
        self.df_cleaned = None
        self.current_file = None
        self.analysis_result = {}
        self.similar_duplicates = []

        self._build_ui()

    def _build_ui(self):
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill="x")

        ttk.Button(top_frame, text="Открыть Excel / CSV", command=self.load_file).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Анализировать", command=self.analyze_data).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Очистить данные", command=self.clean_data).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Найти похожие дубли", command=self.find_similar_duplicates).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Построить графики", command=self.plot_data).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Сохранить очищенный файл", command=self.save_cleaned_file).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Сохранить отчёт", command=self.save_report).pack(side="left", padx=5)

        info_frame = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        info_frame.pack(fill="x")

        self.file_label = ttk.Label(info_frame, text="Файл не выбран")
        self.file_label.pack(side="left")

        main_pane = ttk.PanedWindow(self.root, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        main_pane.add(right_frame, weight=2)

        table_frame = ttk.LabelFrame(left_frame, text="Данные")
        table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(table_frame, show="headings")
        self.tree.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=vsb.set)

        report_frame = ttk.LabelFrame(right_frame, text="Отчёт / Анализ")
        report_frame.pack(fill="both", expand=True)

        self.report_text = ScrolledText(report_frame, wrap="word", font=("Consolas", 10))
        self.report_text.pack(fill="both", expand=True)

    def load_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл",
            filetypes=[
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()

            if ext in [".xlsx", ".xls"]:
                self.df_original = pd.read_excel(file_path)
            elif ext == ".csv":
                try:
                    self.df_original = pd.read_csv(file_path, encoding="utf-8")
                except UnicodeDecodeError:
                    self.df_original = pd.read_csv(file_path, encoding="cp1251")
            else:
                messagebox.showerror("Ошибка", "Поддерживаются только Excel и CSV файлы.")
                return

            self.current_file = file_path
            self.df_cleaned = self.df_original.copy()
            self.analysis_result = {}
            self.similar_duplicates = []

            self.file_label.config(text=f"Файл: {file_path}")
            self.display_dataframe(self.df_original)
            self.write_report("Файл успешно загружен.\nНажмите 'Анализировать' для запуска анализа.")
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", str(e))

    def display_dataframe(self, df: pd.DataFrame, max_rows: int = 150):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = list(df.columns)

        for col in df.columns:
            self.tree.heading(col, text=str(col))
            self.tree.column(col, width=140, anchor="center")

        preview = df.head(max_rows).copy()

        for _, row in preview.iterrows():
            values = [self._safe_str(v) for v in row.tolist()]
            self.tree.insert("", "end", values=values)

    def analyze_data(self):
        if self.df_original is None:
            messagebox.showwarning("Внимание", "Сначала откройте файл.")
            return

        df = self.df_original.copy()
        result = {}

        result["rows"] = len(df)
        result["cols"] = len(df.columns)
        result["columns"] = list(df.columns)
        result["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
        result["missing"] = df.isna().sum().to_dict()
        result["duplicate_rows"] = int(df.duplicated().sum())
        result["empty_rows"] = int(df.isna().all(axis=1).sum())
        result["empty_cols"] = [col for col in df.columns if df[col].isna().all()]

        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        text_cols = df.select_dtypes(include=["object"]).columns.tolist()

        result["numeric_cols"] = numeric_cols
        result["text_cols"] = text_cols
        result["unique_counts"] = {col: int(df[col].nunique(dropna=True)) for col in df.columns}
        result["structure_guess"] = self.guess_structure(df)

        outliers = {}
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                outliers[col] = 0
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                outliers[col] = 0
                continue

            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            count_outliers = int(((df[col] < lower) | (df[col] > upper)).sum())
            outliers[col] = count_outliers

        result["outliers"] = outliers

        likely_key_columns = []
        for col in df.columns:
            name = str(col).lower()
            if any(word in name for word in ["id", "код", "артикул", "sku", "part", "номер"]):
                likely_key_columns.append(col)

        result["likely_key_columns"] = likely_key_columns

        duplicate_by_key = {}
        for col in likely_key_columns:
            duplicate_by_key[col] = int(df[col].duplicated().sum())
        result["duplicate_by_key"] = duplicate_by_key

        self.analysis_result = result
        self.write_report(self.generate_report_text(result))

    def guess_structure(self, df: pd.DataFrame):
        guessed = {
            "id_like": [],
            "name_like": [],
            "price_like": [],
            "quantity_like": [],
            "date_like": [],
            "category_like": [],
            "brand_like": [],
        }

        for col in df.columns:
            col_lower = str(col).lower()

            if any(k in col_lower for k in ["id", "код", "артикул", "sku", "part", "номер"]):
                guessed["id_like"].append(col)

            if any(k in col_lower for k in ["name", "название", "товар", "product", "деталь", "item"]):
                guessed["name_like"].append(col)

            if any(k in col_lower for k in ["price", "цена", "cost", "стоимость"]):
                guessed["price_like"].append(col)

            if any(k in col_lower for k in ["qty", "кол", "quantity", "остаток", "stock", "count"]):
                guessed["quantity_like"].append(col)

            if any(k in col_lower for k in ["date", "дата", "created", "updated"]):
                guessed["date_like"].append(col)

            if any(k in col_lower for k in ["category", "катег", "group", "type"]):
                guessed["category_like"].append(col)

            if any(k in col_lower for k in ["brand", "бренд", "manufacturer", "maker"]):
                guessed["brand_like"].append(col)

        return guessed

    def clean_data(self):
        if self.df_original is None:
            messagebox.showwarning("Внимание", "Сначала откройте файл.")
            return

        df = self.df_original.copy()

        before_rows = len(df)
        before_cols = len(df.columns)

        df = df.dropna(how="all")
        df = df.dropna(axis=1, how="all")
        df.columns = [str(col).strip() for col in df.columns]

        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace("nan", pd.NA)

        df = df.drop_duplicates()

        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ["date", "дата", "created", "updated"]):
                try:
                    df[col] = pd.to_datetime(df[col], errors="ignore")
                except Exception:
                    pass

        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in ["price", "цена", "cost", "стоимость", "qty", "quantity", "остаток", "count", "кол"]):
                try:
                    if df[col].dtype == "object":
                        df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
                    df[col] = pd.to_numeric(df[col], errors="ignore")
                except Exception:
                    pass

        self.df_cleaned = df

        after_rows = len(df)
        after_cols = len(df.columns)

        self.display_dataframe(self.df_cleaned)

        msg = []
        msg.append("Очистка завершена.")
        msg.append(f"Строк до: {before_rows}, после: {after_rows}")
        msg.append(f"Колонок до: {before_cols}, после: {after_cols}")
        msg.append("")
        msg.append("Что было сделано:")
        msg.append("- Удалены полностью пустые строки")
        msg.append("- Удалены полностью пустые колонки")
        msg.append("- Удалены полные дубликаты")
        msg.append("- Обрезаны пробелы в текстовых значениях")
        msg.append("- Выполнена попытка привести даты и числа к корректному типу")

        if self.analysis_result:
            msg.append("")
            msg.append("Совет: нажми 'Найти похожие дубли', чтобы найти похожие названия товаров.")

        self.write_report("\n".join(msg))

    def find_similar_duplicates(self):
        if self.df_cleaned is None or self.df_cleaned.empty:
            messagebox.showwarning("Внимание", "Сначала загрузите и очистите данные.")
            return

        df = self.df_cleaned.copy()
        name_col = self.detect_name_column(df)

        if not name_col:
            messagebox.showwarning(
                "Внимание",
                "Не удалось автоматически определить колонку с названием товара.\n"
                "Переименуй колонку, например, в: name / название / товар / product"
            )
            return

        names_series = df[name_col].dropna().astype(str)
        indexed_names = [(idx, val.strip()) for idx, val in names_series.items() if str(val).strip()]

        if len(indexed_names) < 2:
            messagebox.showinfo("Инфо", "Недостаточно данных для поиска дублей.")
            return

        normalized = []
        for idx, name in indexed_names:
            normalized.append((idx, name, self.normalize_product_name(name)))

        duplicates = []
        threshold = 0.86

        for i in range(len(normalized)):
            idx1, original1, norm1 = normalized[i]
            if len(norm1) < 3:
                continue

            for j in range(i + 1, len(normalized)):
                idx2, original2, norm2 = normalized[j]
                if len(norm2) < 3:
                    continue

                ratio = SequenceMatcher(None, norm1, norm2).ratio()

                if ratio >= threshold and original1.lower() != original2.lower():
                    duplicates.append({
                        "row_1": idx1,
                        "row_2": idx2,
                        "name_1": original1,
                        "name_2": original2,
                        "similarity": round(ratio, 3),
                    })

        duplicates = sorted(duplicates, key=lambda x: x["similarity"], reverse=True)

        unique_pairs = []
        seen = set()
        for item in duplicates:
            key = tuple(sorted([item["name_1"].lower(), item["name_2"].lower()]))
            if key not in seen:
                seen.add(key)
                unique_pairs.append(item)

        self.similar_duplicates = unique_pairs[:200]

        text = []
        text.append("=== ПОИСК ПОХОЖИХ ДУБЛЕЙ ===")
        text.append(f"Колонка названий: {name_col}")
        text.append(f"Найдено похожих пар: {len(self.similar_duplicates)}")
        text.append("")

        if not self.similar_duplicates:
            text.append("Похожие дубли не найдены.")
        else:
            for i, item in enumerate(self.similar_duplicates[:100], start=1):
                text.append(
                    f"{i}. [{item['similarity']}] "
                    f"Строка {item['row_1']} -> {item['name_1']}  ||  "
                    f"Строка {item['row_2']} -> {item['name_2']}"
                )

        self.write_report("\n".join(text))
        messagebox.showinfo("Готово", f"Поиск завершён. Найдено похожих пар: {len(self.similar_duplicates)}")

    def detect_name_column(self, df: pd.DataFrame):
        priority_keywords = [
            "name", "название", "товар", "product", "деталь", "item", "наименование"
        ]

        for col in df.columns:
            col_lower = str(col).lower()
            if any(k in col_lower for k in priority_keywords):
                return col

        object_cols = df.select_dtypes(include=["object"]).columns.tolist()
        if object_cols:
            return object_cols[0]

        return None

    def normalize_product_name(self, text: str) -> str:
        text = text.lower().strip()

        replacements = {
            "ё": "е",
            "  ": " ",
            "-": " ",
            "_": " ",
            "/": " ",
            "\\": " ",
            ",": " ",
            ".": " ",
            ";": " ",
            ":": " ",
            "(": " ",
            ")": " ",
            "[": " ",
            "]": " ",
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        text = re.sub(r"\s+", " ", text)

        stop_words = {
            "для", "и", "в", "на", "с", "по", "из", "the", "a", "an", "of"
        }

        words = [w for w in text.split() if w not in stop_words]
        words.sort()

        return " ".join(words).strip()

    def plot_data(self):
        if self.df_cleaned is None or self.df_cleaned.empty:
            messagebox.showwarning("Внимание", "Нет данных для графиков.")
            return

        df = self.df_cleaned.copy()
        numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
        object_cols = df.select_dtypes(include=["object"]).columns.tolist()

        if not numeric_cols and not object_cols:
            messagebox.showinfo("Инфо", "Подходящих данных для графиков не найдено.")
            return

        plt.rcParams["figure.figsize"] = (10, 6)
        plt.rcParams["axes.grid"] = True
        plt.rcParams["grid.alpha"] = 0.25
        plt.rcParams["font.size"] = 10

        # 1. Гистограмма
        if numeric_cols:
            col = numeric_cols[0]
            data = df[col].dropna()

            if not data.empty:
                plt.figure()
                plt.hist(data, bins=25, edgecolor="black")
                plt.title(f"Распределение значений: {col}", fontsize=14, pad=15)
                plt.xlabel(col)
                plt.ylabel("Количество")
                plt.tight_layout()
                plt.show()

        # 2. Boxplot
        if numeric_cols:
            col = numeric_cols[0]
            data = df[col].dropna()

            if not data.empty:
                plt.figure()
                plt.boxplot(data, vert=True, patch_artist=False)
                plt.title(f"Boxplot: {col}", fontsize=14, pad=15)
                plt.ylabel(col)
                plt.tight_layout()
                plt.show()

        # 3. Топ категорий
        if object_cols:
            col = self.detect_name_column(df) or object_cols[0]
            vc = df[col].fillna("ПУСТО").astype(str).value_counts().head(10)

            if not vc.empty:
                plt.figure(figsize=(12, 6))
                plt.bar(vc.index, vc.values, edgecolor="black")
                plt.title(f"Топ-10 значений: {col}", fontsize=14, pad=15)
                plt.xlabel(col)
                plt.ylabel("Количество")
                plt.xticks(rotation=35, ha="right")
                plt.tight_layout()
                plt.show()

        # 4. Scatter
        if len(numeric_cols) >= 2:
            x_col = numeric_cols[0]
            y_col = numeric_cols[1]

            plot_df = df[[x_col, y_col]].dropna()
            if not plot_df.empty:
                plt.figure()
                plt.scatter(plot_df[x_col], plot_df[y_col], alpha=0.7, edgecolors="black")
                plt.title(f"Связь между {x_col} и {y_col}", fontsize=14, pad=15)
                plt.xlabel(x_col)
                plt.ylabel(y_col)
                plt.tight_layout()
                plt.show()

        # 5. Линейный график
        if numeric_cols:
            col = numeric_cols[0]
            data = df[col].dropna().reset_index(drop=True)

            if len(data) > 1:
                plt.figure(figsize=(11, 5))
                plt.plot(data.index, data.values, linewidth=2)
                plt.title(f"Динамика значений: {col}", fontsize=14, pad=15)
                plt.xlabel("Индекс строки")
                plt.ylabel(col)
                plt.tight_layout()
                plt.show()

        messagebox.showinfo("Готово", "Графики построены.")

    def save_cleaned_file(self):
        if self.df_cleaned is None:
            messagebox.showwarning("Внимание", "Нет очищенных данных.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Сохранить очищенный файл",
            defaultextension=".xlsx",
            filetypes=[
                ("Excel file", "*.xlsx"),
                ("CSV file", "*.csv"),
            ],
        )

        if not file_path:
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".csv":
                self.df_cleaned.to_csv(file_path, index=False, encoding="utf-8-sig")
            else:
                self.df_cleaned.to_excel(file_path, index=False)

            messagebox.showinfo("Успех", f"Файл сохранён:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения", str(e))

    def save_report(self):
        report = self.report_text.get("1.0", "end").strip()
        if not report:
            messagebox.showwarning("Внимание", "Отчёт пуст.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Сохранить отчёт",
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt")],
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report)
            messagebox.showinfo("Успех", f"Отчёт сохранён:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка сохранения отчёта", str(e))

    def generate_report_text(self, result: dict):
        lines = []
        lines.append("=== УМНЫЙ ОТЧЁТ ПО ФАЙЛУ ===")
        lines.append("")
        lines.append(f"Строк: {result.get('rows', 0)}")
        lines.append(f"Колонок: {result.get('cols', 0)}")
        lines.append("")

        lines.append("Колонки:")
        for col in result.get("columns", []):
            dtype = result.get("dtypes", {}).get(col, "unknown")
            unique = result.get("unique_counts", {}).get(col, 0)
            missing = result.get("missing", {}).get(col, 0)
            lines.append(f"- {col} | тип: {dtype} | уникальных: {unique} | пропусков: {missing}")

        lines.append("")
        lines.append(f"Полных дубликатов строк: {result.get('duplicate_rows', 0)}")
        lines.append(f"Полностью пустых строк: {result.get('empty_rows', 0)}")
        lines.append(f"Полностью пустые колонки: {result.get('empty_cols', [])}")

        lines.append("")
        lines.append("Предположения по структуре:")
        structure = result.get("structure_guess", {})
        for key, value in structure.items():
            lines.append(f"- {key}: {value}")

        lines.append("")
        lines.append("Выбросы по числовым колонкам:")
        outliers = result.get("outliers", {})
        if outliers:
            for col, count in outliers.items():
                lines.append(f"- {col}: {count}")
        else:
            lines.append("- не найдено")

        lines.append("")
        lines.append("Похожие на ключевые колонки:")
        lines.append(str(result.get("likely_key_columns", [])))

        lines.append("")
        lines.append("Дубликаты по ключевым колонкам:")
        dup_key = result.get("duplicate_by_key", {})
        if dup_key:
            for col, count in dup_key.items():
                lines.append(f"- {col}: {count}")
        else:
            lines.append("- не найдено")

        lines.append("")
        lines.append("Рекомендации:")
        lines.extend(self.generate_recommendations(result))

        if self.similar_duplicates:
            lines.append("")
            lines.append("Похожие названия товаров:")
            for i, item in enumerate(self.similar_duplicates[:30], start=1):
                lines.append(
                    f"{i}. [{item['similarity']}] "
                    f"{item['name_1']}  <->  {item['name_2']}"
                )

        return "\n".join(lines)

    def generate_recommendations(self, result: dict):
        recommendations = []

        if result.get("duplicate_rows", 0) > 0:
            recommendations.append("- Удалить полные дубликаты строк.")

        if result.get("empty_rows", 0) > 0:
            recommendations.append("- Удалить полностью пустые строки.")

        if len(result.get("empty_cols", [])) > 0:
            recommendations.append("- Удалить полностью пустые колонки.")

        missing = result.get("missing", {})
        for col, count in missing.items():
            if count > 0:
                recommendations.append(f"- Проверить пропуски в колонке '{col}'.")

        outliers = result.get("outliers", {})
        for col, count in outliers.items():
            if count > 0:
                recommendations.append(f"- Проверить выбросы в колонке '{col}'.")

        duplicate_by_key = result.get("duplicate_by_key", {})
        for col, count in duplicate_by_key.items():
            if count > 0:
                recommendations.append(f"- Проверить дубликаты по ключевой колонке '{col}'.")

        recommendations.append("- Запустить поиск похожих дублей по названиям товаров.")
        recommendations.append("- Построить графики для визуального анализа.")

        if not recommendations:
            recommendations.append("- Явных проблем не найдено.")

        return recommendations

    def write_report(self, text: str):
        self.report_text.delete("1.0", "end")
        self.report_text.insert("1.0", text)

    @staticmethod
    def _safe_str(value):
        if pd.isna(value):
            return ""
        text = str(value)
        return text[:120]


def main():
    root = tk.Tk()
    app = SmartExcelHelperV2(root)
    root.mainloop()


if __name__ == "__main__":
    main()