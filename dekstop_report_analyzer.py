
import os
import re
import sys
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt


class ReportParser:
    def __init__(self) -> None:
        self.sheet_name: Optional[str] = None
        self.header_row_idx: Optional[int] = None
        self.metric_row_idx: Optional[int] = None
        self.product_col_idx: Optional[int] = None

    @staticmethod
    def normalize_text(value) -> str:
        if pd.isna(value):
            return ""
        text = str(value).strip()
        text = re.sub(r"\s+", " ", text)
        return text

    def detect_report_sheet(self, xls: pd.ExcelFile) -> str:
        for sheet in xls.sheet_names:
            preview = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)
            flat = " ".join(self.normalize_text(v) for v in preview.fillna("").values.flatten())
            if "Номенклатура.Наименование" in flat and "Количество (в базовых ед.)" in flat:
                return sheet
        return xls.sheet_names[0]

    def detect_layout(self, raw: pd.DataFrame) -> None:
        found_header = None
        found_metric = None
        product_col = 1

        max_scan_rows = min(25, raw.shape[0])
        for i in range(max_scan_rows):
            row_texts = [self.normalize_text(v) for v in raw.iloc[i].tolist()]
            if "Номенклатура.Наименование" in row_texts:
                found_header = i
                product_col = row_texts.index("Номенклатура.Наименование")
                break

        if found_header is None:
            raise ValueError("Не удалось найти строку с колонкой 'Номенклатура.Наименование'.")

        for i in range(found_header + 1, min(found_header + 4, raw.shape[0])):
            row_texts = " | ".join(self.normalize_text(v) for v in raw.iloc[i].tolist())
            if "Количество (в базовых ед.)" in row_texts:
                found_metric = i
                break

        if found_metric is None:
            raise ValueError("Не удалось найти строку с названиями показателей.")

        self.header_row_idx = found_header
        self.metric_row_idx = found_metric
        self.product_col_idx = product_col

    @staticmethod
    def metric_to_key(metric_text: str) -> Optional[str]:
        text = metric_text.lower()
        if "количество" in text:
            return "qty"
        if "сумма продажи с ндс" in text:
            return "sales_vat"
        if "сумма продажи без ндс" in text:
            return "sales_no_vat"
        if "цена с ндс" in text:
            return "price_vat"
        if "цена без ндс" in text:
            return "price_no_vat"
        return None

    @staticmethod
    def to_number(value) -> float:
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(" ", "").replace(",", ".")
        if not text:
            return 0.0
        try:
            return float(text)
        except Exception:
            return 0.0

    def parse_year_columns(self, raw: pd.DataFrame) -> Tuple[Dict[int, Dict[str, int]], Dict[str, int]]:
        year_row = raw.iloc[self.header_row_idx]
        metric_row = raw.iloc[self.metric_row_idx]

        year_map: Dict[int, Dict[str, int]] = {}
        total_map: Dict[str, int] = {}
        current_year = None
        current_group = None

        for col_idx in range(raw.shape[1]):
            year_text = self.normalize_text(year_row.iloc[col_idx])
            metric_text = self.normalize_text(metric_row.iloc[col_idx])

            if re.search(r"20\d{2}", year_text):
                current_year = int(re.search(r"(20\d{2})", year_text).group(1))
                current_group = "year"
                year_map.setdefault(current_year, {})
            elif year_text.lower() == "итог":
                current_year = None
                current_group = "total"

            if not metric_text:
                continue

            key = self.metric_to_key(metric_text)
            if not key:
                continue

            if current_group == "year" and current_year is not None:
                year_map[current_year][key] = col_idx
            elif current_group == "total":
                total_map[key] = col_idx

        return year_map, total_map

    def parse_report(self, path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        xls = pd.ExcelFile(path)
        self.sheet_name = self.detect_report_sheet(xls)
        raw = pd.read_excel(xls, sheet_name=self.sheet_name, header=None)

        self.detect_layout(raw)
        year_map, total_map = self.parse_year_columns(raw)

        if not year_map:
            raise ValueError("Не удалось определить колонки по годам в отчёте.")

        records: List[Dict] = []
        totals: List[Dict] = []

        start_row = self.metric_row_idx + 1
        for row_idx in range(start_row, raw.shape[0]):
            row = raw.iloc[row_idx]
            product = row.iloc[self.product_col_idx]
            product = self.normalize_text(product)

            if not product:
                continue
            if product.lower().startswith("итог"):
                continue
            if product in {"0", "nan"}:
                continue

            # avoid header echoes / junk
            if product.lower() in {"номенклатура.наименование"}:
                continue

            for year, cols in sorted(year_map.items()):
                rec = {
                    "product": product,
                    "year": int(year),
                    "qty": self.to_number(row.iloc[cols["qty"]]) if "qty" in cols else 0.0,
                    "sales_vat": self.to_number(row.iloc[cols["sales_vat"]]) if "sales_vat" in cols else 0.0,
                    "sales_no_vat": self.to_number(row.iloc[cols["sales_no_vat"]]) if "sales_no_vat" in cols else 0.0,
                    "price_vat": self.to_number(row.iloc[cols["price_vat"]]) if "price_vat" in cols else 0.0,
                    "price_no_vat": self.to_number(row.iloc[cols["price_no_vat"]]) if "price_no_vat" in cols else 0.0,
                }
                if any(abs(rec[k]) > 0 for k in ["qty", "sales_vat", "sales_no_vat", "price_vat", "price_no_vat"]):
                    records.append(rec)

            if total_map:
                total_rec = {
                    "product": product,
                    "qty_total": self.to_number(row.iloc[total_map["qty"]]) if "qty" in total_map else 0.0,
                    "sales_vat_total": self.to_number(row.iloc[total_map["sales_vat"]]) if "sales_vat" in total_map else 0.0,
                    "sales_no_vat_total": self.to_number(row.iloc[total_map["sales_no_vat"]]) if "sales_no_vat" in total_map else 0.0,
                    "price_vat_total": self.to_number(row.iloc[total_map["price_vat"]]) if "price_vat" in total_map else 0.0,
                    "price_no_vat_total": self.to_number(row.iloc[total_map["price_no_vat"]]) if "price_no_vat" in total_map else 0.0,
                }
                if any(abs(total_rec[k]) > 0 for k in total_rec if k != "product"):
                    totals.append(total_rec)

        if not records:
            raise ValueError("После парсинга не найдено ни одной записи с данными.")

        detailed_df = pd.DataFrame(records)
        totals_df = pd.DataFrame(totals)

        # Merge duplicate product/year rows just in case.
        detailed_df = detailed_df.groupby(["product", "year"], as_index=False).sum(numeric_only=True)
        if not totals_df.empty:
            totals_df = totals_df.groupby(["product"], as_index=False).sum(numeric_only=True)

        return detailed_df, totals_df


class ReportAnalytics:
    METRIC_LABELS = {
        "qty": "Количество",
        "sales_vat": "Сумма продажи с НДС",
        "sales_no_vat": "Сумма продажи без НДС",
        "price_vat": "Цена с НДС",
        "price_no_vat": "Цена без НДС",
    }

    def __init__(self, detailed_df: pd.DataFrame, totals_df: pd.DataFrame) -> None:
        self.detailed_df = detailed_df.copy()
        self.totals_df = totals_df.copy()

    def yearly_totals(self, metric: str = "sales_no_vat") -> pd.DataFrame:
        result = self.detailed_df.groupby("year", as_index=False)[metric].sum()
        result["yoy_pct"] = result[metric].pct_change() * 100
        return result

    def top_products(self, metric: str = "sales_no_vat", year: Optional[int] = None, n: int = 15) -> pd.DataFrame:
        df = self.detailed_df.copy()
        if year is not None:
            df = df[df["year"] == year]
        result = df.groupby("product", as_index=False)[metric].sum().sort_values(metric, ascending=False).head(n)
        return result

    def product_pivot(self, metric: str = "sales_no_vat") -> pd.DataFrame:
        pivot = self.detailed_df.pivot_table(index="product", columns="year", values=metric, aggfunc="sum", fill_value=0)
        pivot = pivot.sort_index(axis=1)
        return pivot

    def growth_table(self, metric: str = "sales_no_vat") -> pd.DataFrame:
        pivot = self.product_pivot(metric)
        years = list(pivot.columns)
        if len(years) < 2:
            return pd.DataFrame()

        first_year = years[0]
        last_year = years[-1]
        out = pivot.copy()
        out["delta_abs"] = out[last_year] - out[first_year]
        out["delta_pct"] = out.apply(lambda r: ((r[last_year] / r[first_year] - 1) * 100) if r[first_year] not in (0, None) else None, axis=1)
        out = out.reset_index().sort_values("delta_abs", ascending=False)
        out["first_year"] = first_year
        out["last_year"] = last_year
        return out

    def negatives(self) -> pd.DataFrame:
        df = self.detailed_df.copy()
        mask = (df["qty"] < 0) | (df["sales_vat"] < 0) | (df["sales_no_vat"] < 0)
        return df.loc[mask].sort_values(["year", "sales_no_vat"])

    def forecast_next_year(self, metric: str = "sales_no_vat") -> pd.DataFrame:
        pivot = self.product_pivot(metric)
        years = list(pivot.columns)
        if len(years) < 2:
            return pd.DataFrame()

        next_year = max(years) + 1
        rows = []
        for product, row in pivot.iterrows():
            vals = [float(row[y]) for y in years]
            if len(vals) >= 2:
                trend = vals[-1] - vals[-2]
                forecast = vals[-1] + trend
            else:
                forecast = vals[-1]
            rows.append({"product": product, f"forecast_{next_year}": forecast})
        result = pd.DataFrame(rows).sort_values(f"forecast_{next_year}", ascending=False)
        return result

    def summary_text(self, metric: str = "sales_no_vat") -> str:
        yearly = self.yearly_totals(metric)
        top = self.top_products(metric, year=int(yearly["year"].max()), n=10) if not yearly.empty else pd.DataFrame()
        growth = self.growth_table(metric)
        negatives = self.negatives()

        lines = []
        lines.append("=== АНАЛИЗ ОТЧЁТА ===")
        lines.append("")
        lines.append(f"Записей (товар-год): {len(self.detailed_df):,}".replace(",", " "))
        lines.append(f"Уникальных товаров: {self.detailed_df['product'].nunique():,}".replace(",", " "))
        lines.append(f"Период по годам: {', '.join(map(str, sorted(self.detailed_df['year'].unique())))}")
        lines.append(f"Основная метрика: {self.METRIC_LABELS.get(metric, metric)}")
        lines.append("")

        lines.append("Итоги по годам:")
        for _, r in yearly.iterrows():
            yoy = r["yoy_pct"]
            yoy_txt = "—" if pd.isna(yoy) else f"{yoy:,.2f}%".replace(",", " ")
            val_txt = f"{r[metric]:,.2f}".replace(",", " ")
            lines.append(f"- {int(r['year'])}: {val_txt} | YoY: {yoy_txt}")

        if not top.empty:
            lines.append("")
            lines.append(f"Топ-10 товаров за {int(yearly['year'].max())}:")
            for i, (_, r) in enumerate(top.iterrows(), start=1):
                val_txt = f"{r[metric]:,.2f}".replace(",", " ")
                lines.append(f"{i}. {r['product']} — {val_txt}")

        if not growth.empty:
            up = growth.head(10)
            down = growth.sort_values("delta_abs").head(10)
            first_year = int(growth["first_year"].iloc[0])
            last_year = int(growth["last_year"].iloc[0])

            lines.append("")
            lines.append(f"Самый сильный рост ({first_year} -> {last_year}):")
            for i, (_, r) in enumerate(up.iterrows(), start=1):
                lines.append(f"{i}. {r['product']} — Δ {r['delta_abs']:,.2f}".replace(",", " "))

            lines.append("")
            lines.append(f"Самое сильное падение ({first_year} -> {last_year}):")
            for i, (_, r) in enumerate(down.iterrows(), start=1):
                lines.append(f"{i}. {r['product']} — Δ {r['delta_abs']:,.2f}".replace(",", " "))

        if not negatives.empty:
            lines.append("")
            lines.append(f"Строк с отрицательными значениями: {len(negatives)}")

        return "\n".join(lines)


class DesktopReportApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Анализатор складских отчётов")
        self.root.geometry("1500x900")

        self.parser = ReportParser()
        self.detailed_df = pd.DataFrame()
        self.totals_df = pd.DataFrame()
        self.analytics: Optional[ReportAnalytics] = None
        self.current_file: Optional[str] = None

        self.metric_var = tk.StringVar(value="sales_no_vat")
        self.status_var = tk.StringVar(value="Откройте Excel-отчёт для анализа.")

        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="Открыть отчёт", command=self.open_file).pack(side="left", padx=4)
        ttk.Button(top, text="Анализировать", command=self.analyze_current).pack(side="left", padx=4)
        ttk.Button(top, text="Экспорт Excel", command=self.export_excel).pack(side="left", padx=4)
        ttk.Button(top, text="Экспорт TXT", command=self.export_txt).pack(side="left", padx=4)
        ttk.Button(top, text="График по годам", command=self.plot_yearly).pack(side="left", padx=4)
        ttk.Button(top, text="Топ товаров", command=self.plot_top_products).pack(side="left", padx=4)
        ttk.Button(top, text="Рост / падение", command=self.plot_growth_decline).pack(side="left", padx=4)
        ttk.Button(top, text="Прогноз", command=self.plot_forecast).pack(side="left", padx=4)

        ttk.Label(top, text="Метрика:").pack(side="left", padx=(16, 4))
        metric_combo = ttk.Combobox(
            top,
            textvariable=self.metric_var,
            state="readonly",
            width=22,
            values=["sales_no_vat", "sales_vat", "qty", "price_no_vat", "price_vat"],
        )
        metric_combo.pack(side="left")
        metric_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_views())

        file_frame = ttk.Frame(self.root, padding=(10, 0, 10, 0))
        file_frame.pack(fill="x")
        self.file_label = ttk.Label(file_frame, text="Файл не выбран")
        self.file_label.pack(side="left")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # Summary tab
        tab_summary = ttk.Frame(notebook)
        notebook.add(tab_summary, text="Сводка")

        self.summary_text = ScrolledText(tab_summary, wrap="word", font=("Consolas", 10))
        self.summary_text.pack(fill="both", expand=True, padx=8, pady=8)

    # Detailed data tab
        tab_data = ttk.Frame(notebook)
        notebook.add(tab_data, text="Данные")
        self.tree_data = self._build_tree(tab_data)

    # Top products tab
        tab_top = ttk.Frame(notebook)
        notebook.add(tab_top, text="Топ товаров")
        self.tree_top = self._build_tree(tab_top)

    # Growth tab
        tab_growth = ttk.Frame(notebook)
        notebook.add(tab_growth, text="Рост / падение")
        self.tree_growth = self._build_tree(tab_growth)

    # Negative rows tab
        tab_negative = ttk.Frame(notebook)
        notebook.add(tab_negative, text="Отрицательные строки")
        self.tree_negative = self._build_tree(tab_negative)

        status = ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w")
        status.pack(fill="x", side="bottom")

    def _build_tree(self, parent: tk.Widget) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, show="headings")
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите Excel-отчёт",
            filetypes=[("Excel files", "*.xlsx *.xls")],
        )
        if not path:
            return
        self.current_file = path
        self.file_label.config(text=path)
        self.status_var.set("Файл выбран. Нажмите 'Анализировать'.")
        self.analyze_current()

    def analyze_current(self) -> None:
        if not self.current_file:
            messagebox.showwarning("Нет файла", "Сначала выберите Excel-отчёт.")
            return
        try:
            self.status_var.set("Чтение и парсинг отчёта...")
            self.root.update_idletasks()

            detailed_df, totals_df = self.parser.parse_report(self.current_file)
            self.detailed_df = detailed_df
            self.totals_df = totals_df
            self.analytics = ReportAnalytics(detailed_df, totals_df)

            self.refresh_views()

            self.status_var.set(
                f"Готово: {len(self.detailed_df):,} записей, {self.detailed_df['product'].nunique():,} товаров.".replace(",", " ")
            )
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Ошибка анализа", str(e))
            self.status_var.set("Ошибка анализа.")

    def refresh_views(self) -> None:
        if self.analytics is None or self.detailed_df.empty:
            return
        metric = self.metric_var.get()

        # Summary
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", self.analytics.summary_text(metric))

        # Detailed
        detail_preview = self.detailed_df.sort_values(["year", metric], ascending=[True, False]).copy()
        self.populate_tree(self.tree_data, detail_preview.head(1000))

        # Top
        latest_year = int(self.detailed_df["year"].max())
        top = self.analytics.top_products(metric=metric, year=latest_year, n=200)
        self.populate_tree(self.tree_top, top)

        # Growth
        growth = self.analytics.growth_table(metric=metric)
        self.populate_tree(self.tree_growth, growth.head(500) if not growth.empty else pd.DataFrame())

        # Negative
        negative = self.analytics.negatives()
        self.populate_tree(self.tree_negative, negative.head(500) if not negative.empty else pd.DataFrame())

    def populate_tree(self, tree: ttk.Treeview, df: pd.DataFrame) -> None:
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            tree["columns"] = []
            return

        show_df = df.copy()
        for col in show_df.columns:
            if pd.api.types.is_float_dtype(show_df[col]):
                show_df[col] = show_df[col].map(lambda x: f"{x:,.2f}".replace(",", " "))

        columns = list(show_df.columns)
        tree["columns"] = columns

        for col in columns:
            tree.heading(col, text=col)
            width = 140 if col != "product" else 360
            tree.column(col, width=width, anchor="w")

        for _, row in show_df.iterrows():
            tree.insert("", "end", values=[row[col] for col in columns])

    def get_metric_label(self) -> str:
        return ReportAnalytics.METRIC_LABELS.get(self.metric_var.get(), self.metric_var.get())

    def plot_yearly(self) -> None:
        if self.analytics is None:
            return
        metric = self.metric_var.get()
        df = self.analytics.yearly_totals(metric)
        plt.figure(figsize=(9, 5))
        plt.plot(df["year"], df[metric], marker="o", linewidth=2)
        plt.title(f"Динамика по годам: {self.get_metric_label()}")
        plt.xlabel("Год")
        plt.ylabel(self.get_metric_label())
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()

    def plot_top_products(self) -> None:
        if self.analytics is None:
            return
        metric = self.metric_var.get()
        latest_year = int(self.detailed_df["year"].max())
        df = self.analytics.top_products(metric=metric, year=latest_year, n=15)
        if df.empty:
            return
        df = df.sort_values(metric, ascending=True)

        plt.figure(figsize=(12, 7))
        plt.barh(df["product"], df[metric])
        plt.title(f"Топ товаров за {latest_year}: {self.get_metric_label()}")
        plt.xlabel(self.get_metric_label())
        plt.ylabel("Товар")
        plt.tight_layout()
        plt.show()

    def plot_growth_decline(self) -> None:
        if self.analytics is None:
            return
        metric = self.metric_var.get()
        growth = self.analytics.growth_table(metric)
        if growth.empty:
            messagebox.showinfo("Недостаточно данных", "Для графика роста/падения нужно минимум 2 года данных.")
            return

        up = growth.head(10).sort_values("delta_abs", ascending=True)
        down = growth.sort_values("delta_abs").head(10)

        plt.figure(figsize=(12, 6))
        plt.barh(up["product"], up["delta_abs"])
        plt.title(f"Топ роста: {self.get_metric_label()}")
        plt.xlabel("Изменение")
        plt.ylabel("Товар")
        plt.tight_layout()
        plt.show()

        plt.figure(figsize=(12, 6))
        plt.barh(down["product"], down["delta_abs"])
        plt.title(f"Топ падения: {self.get_metric_label()}")
        plt.xlabel("Изменение")
        plt.ylabel("Товар")
        plt.tight_layout()
        plt.show()

    def plot_forecast(self) -> None:
        if self.analytics is None:
            return
        metric = self.metric_var.get()
        forecast = self.analytics.forecast_next_year(metric)
        if forecast.empty:
            messagebox.showinfo("Недостаточно данных", "Для прогноза нужно минимум 2 года данных.")
            return
        forecast_col = [c for c in forecast.columns if c.startswith("forecast_")][0]
        top = forecast.head(15).sort_values(forecast_col, ascending=True)

        plt.figure(figsize=(12, 7))
        plt.barh(top["product"], top[forecast_col])
        plt.title(f"Прогноз по товарам: {self.get_metric_label()} ({forecast_col.replace('forecast_', '')})")
        plt.xlabel(self.get_metric_label())
        plt.ylabel("Товар")
        plt.tight_layout()
        plt.show()

    def export_excel(self) -> None:
        if self.analytics is None:
            messagebox.showwarning("Нет данных", "Сначала проанализируйте отчёт.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Сохранить Excel с анализом",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not save_path:
            return

        metric = self.metric_var.get()
        try:
            with pd.ExcelWriter(save_path, engine="openpyxl") as writer:
                self.detailed_df.to_excel(writer, sheet_name="Детальные_данные", index=False)
                if not self.totals_df.empty:
                    self.totals_df.to_excel(writer, sheet_name="Итоги_по_товарам", index=False)
                self.analytics.yearly_totals(metric).to_excel(writer, sheet_name="Итоги_по_годам", index=False)
                self.analytics.top_products(metric, year=int(self.detailed_df["year"].max()), n=200).to_excel(writer, sheet_name="Топ_товаров", index=False)
                growth = self.analytics.growth_table(metric)
                if not growth.empty:
                    growth.to_excel(writer, sheet_name="Рост_и_падение", index=False)
                negatives = self.analytics.negatives()
                if not negatives.empty:
                    negatives.to_excel(writer, sheet_name="Отрицательные_строки", index=False)
                forecast = self.analytics.forecast_next_year(metric)
                if not forecast.empty:
                    forecast.to_excel(writer, sheet_name="Прогноз", index=False)

            messagebox.showinfo("Готово", f"Excel сохранён:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", str(e))

    def export_txt(self) -> None:
        if self.analytics is None:
            messagebox.showwarning("Нет данных", "Сначала проанализируйте отчёт.")
            return

        save_path = filedialog.asksaveasfilename(
            title="Сохранить текстовый отчёт",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
        )
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(self.summary_text.get("1.0", "end").strip())
            messagebox.showinfo("Готово", f"Отчёт сохранён:\n{save_path}")
        except Exception as e:
            messagebox.showerror("Ошибка экспорта", str(e))


def main() -> None:
    root = tk.Tk()
    app = DesktopReportApp(root)

    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        app.current_file = sys.argv[1]
        app.file_label.config(text=sys.argv[1])
        app.analyze_current()

    root.mainloop()


if __name__ == "__main__":
    main()
