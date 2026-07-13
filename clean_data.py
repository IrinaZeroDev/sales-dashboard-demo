"""
Очистка и предобработка данных о продажах из Excel со справочниками.

Исходный файл data/sales_raw.xlsx содержит листы:
  Продажи  — таблица фактов (client_id, product_id — ключи к справочникам);
  Клиенты  — справочник клиентов (client_id, client_name, client_type, region);
  Продукты — справочник продуктов (product_id, product_name, category, ...).

Этапы:
  1. Чтение Excel (несколько листов), профилирование.
  2. Дедупликация справочников и факта.
  3. Нормализация справочников: регионы и категории (регистр, пробелы, опечатки).
  4. Merge факта со справочниками (LEFT JOIN по client_id и product_id),
     отметка «висящих» ключей, которых нет в справочнике.
  5. Парсинг дат в разных форматах.
  6. Обработка пропусков.
  7. Поиск аномалий (IQR + Z-оценка) -> флаг is_outlier.
  8. Коррекция некорректных количеств (<=0).
  9. Производные признаки: маржа, средний чек, временные измерения, RFM, ABC.
  10. Сохранение очищенной таблицы фактов, измерения дат и отчёта.

Запуск:
    python clean_data.py
Результат:
    data/sales_clean.csv     — очищенная таблица фактов (для дашборда/Power BI)
    data/dim_date.csv        — измерение дат (модель «звезда»)
    data/cleaning_report.txt — отчёт о качестве и применённых методах
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RAW_PATH = DATA_DIR / "sales_raw.xlsx"
OUT_CLEAN = DATA_DIR / "sales_clean.csv"
OUT_DATE = DATA_DIR / "dim_date.csv"
OUT_REPORT = DATA_DIR / "cleaning_report.txt"

REPORT: list[str] = []


def log(msg: str) -> None:
    print(msg)
    REPORT.append(msg)


# --- Канонические справочники для нормализации --------------------------
REGION_CANON = {
    "москва и мо": "Москва и МО", "москва и  мо": "Москва и МО",
    "санкт-петербург и ло": "Санкт-Петербург и ЛО",
    "краснодарский край": "Краснодарский край",
    "свердловская область": "Свердловская область",
    "республика татарстан": "Республика Татарстан",
    "новосибирская область": "Новосибирская область",
    "нижегородская область": "Нижегородская область",
    "самарская область": "Самарская область",
    "республика башкортостан": "Республика Башкортостан",
    "приморский край": "Приморский край",
    "ростовская область": "Ростовская область",
}
CATEGORY_CANON = {
    "электроника": "Электроника",
    "бытовая техника": "Бытовая техника",
    "компьютеры и комплектующие": "Компьютеры и комплектующие",
    "аксессуары": "Аксессуары",
}


def _normalize(value, canon: dict):
    if pd.isna(value):
        return np.nan
    key = str(value).strip().lower().replace("0", "о").replace("  ", " ")
    return canon.get(key, str(value).strip())


# --- 1. Чтение и профилирование -----------------------------------------
def load_workbook() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sales = pd.read_excel(RAW_PATH, sheet_name="Продажи")
    clients = pd.read_excel(RAW_PATH, sheet_name="Клиенты")
    products = pd.read_excel(RAW_PATH, sheet_name="Продукты")
    log("=== 1. ПРОФИЛИРОВАНИЕ ИСХОДНЫХ ДАННЫХ ===")
    log(f"Лист «Продажи»:  {len(sales):,} строк | пропуски:\n{sales.isna().sum().to_string()}")
    log(f"Лист «Клиенты»:  {len(clients)} строк | дубликатов client_id: {clients['client_id'].duplicated().sum()}")
    log(f"Лист «Продукты»: {len(products)} строк | дубликатов product_id: {products['product_id'].duplicated().sum()}")
    log(f"Дубликатов факта (полных): {sales.duplicated().sum():,}")
    log("")
    return sales, clients, products


# --- 2. Дедупликация ----------------------------------------------------
def dedupe(sales, clients, products):
    clients = clients.drop_duplicates(subset=["client_id"], keep="first")
    products = products.drop_duplicates(subset=["product_id"], keep="first")
    before = len(sales)
    sales = sales.drop_duplicates()
    log("=== 2. ДЕДУПЛИКАЦИЯ ===")
    log(f"Справочник клиентов: оставлено {len(clients)} уникальных")
    log(f"Справочник продуктов: оставлено {len(products)} уникальных")
    log(f"Факт: удалено дублей {before - len(sales):,} | осталось {len(sales):,}")
    log("")
    return sales, clients, products


# --- 3. Нормализация справочников --------------------------------------
def normalize_refs(clients, products):
    clients = clients.copy()
    products = products.copy()
    clients["region"] = clients["region"].apply(lambda x: _normalize(x, REGION_CANON))
    products["category"] = products["category"].apply(lambda x: _normalize(x, CATEGORY_CANON))
    for col in ["client_name", "client_type"]:
        clients[col] = clients[col].astype("string").str.strip()
    for col in ["product_name"]:
        products[col] = products[col].astype("string").str.strip()
    log("=== 3. НОРМАЛИЗАЦИЯ СПРАВОЧНИКОВ ===")
    log(f"Регионов (канон.) в справочнике клиентов: {clients['region'].nunique(dropna=False)}")
    log(f"Категорий (канон.) в справочнике продуктов: {sorted(products['category'].dropna().unique())}")
    log("")
    return clients, products


# --- 4. Merge факта со справочниками -----------------------------------
def merge_fact(sales, clients, products):
    sales = sales.merge(
        clients[["client_id", "client_name", "client_type", "region"]],
        on="client_id", how="left", validate="many_to_one",
    )
    sales = sales.merge(
        products[["product_id", "product_name", "category"]],
        on="product_id", how="left", validate="many_to_one",
    )
    missing_client = sales["client_name"].isna().sum()
    missing_product = sales["product_name"].isna().sum()
    sales["region"] = sales["region"].fillna("Не определено")
    sales["client_type"] = sales["client_type"].fillna("Не определено")
    sales["category"] = sales["category"].fillna("Не определено")
    log("=== 4. MERGE ФАКТА СО СПРАВОЧНИКАМИ ===")
    log(f"LEFT JOIN по client_id и product_id")
    log(f"Сделок без клиента в справочнике: {missing_client:,} (client_name заполнен как 'Не определено')")
    log(f"Сделок без продукта в справочнике: {missing_product:,}")
    log("")
    return sales


# --- 5. Парсинг дат -----------------------------------------------------
def _parse_one(val):
    """Разбор даты по разделителю: ISO (%Y-%m-%d), точки/слэш (%d.%m.%Y / %d/%m/%Y),
    буквенный месяц (%d %b %Y). Глобальный dayfirst ломает ISO-даты."""
    s = str(val).strip()
    if isinstance(val, (pd.Timestamp, datetime)):
        return pd.Timestamp(val)
    try:
        if "-" in s and len(s.split("-")[0]) == 4:
            return datetime.strptime(s, "%Y-%m-%d")
        if "." in s:
            return datetime.strptime(s, "%d.%m.%Y")
        if "/" in s:
            return datetime.strptime(s, "%d/%m/%Y")
        return datetime.strptime(s, "%d %b %Y")
    except (ValueError, TypeError):
        return pd.NaT


def parse_dates(df):
    df["order_date"] = df["order_date"].map(_parse_one)
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    bad = df["order_date"].isna().sum()
    log("=== 5. ПАРСИНГ ДАТ ===")
    log(f"Унифицировано в datetime (формат по разделителю). Нераспознанных: {bad}")
    log(f"Диапазон: {df['order_date'].min().date()} ... {df['order_date'].max().date()}")
    log("")
    return df


# --- 6. Пропуски --------------------------------------------------------
def handle_missing(df):
    log("=== 6. ОБРАБОТКА ПРОПУСКОВ ===")
    mask = df["revenue"].isna()
    if mask.any():
        df.loc[mask, "revenue"] = (
            df.loc[mask, "quantity"] * df.loc[mask, "unit_price"] * (1 - df.loc[mask, "discount"])
        ).round(2)
    log(f"revenue восстановлен из формулы для {mask.sum():,} строк")
    log(f"Осталось пропусков: {df.isna().sum().sum()}")
    log("")
    return df


# --- 7. Аномалии --------------------------------------------------------
def flag_outliers(df):
    log("=== 7. ПОИСК АНОМАЛИЙ ===")
    q1, q3 = df["revenue"].quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + 1.5 * iqr
    mean, std = df["revenue"].mean(), df["revenue"].std()
    df["z_score"] = ((df["revenue"] - mean) / std).round(3)
    df["is_outlier"] = ((df["revenue"] > upper) | (df["z_score"].abs() > 3)).astype(int)
    n = df["is_outlier"].sum()
    log(f"IQR: Q1={q1:,.0f} Q3={q3:,.0f} upper={upper:,.0f}")
    log(f"Помечено выбросов (is_outlier=1): {n:,} ({n/len(df)*100:.2f}%)")
    log("Выбросы не удаляются — помечаются флагом для видимости менеджерам.")
    log("")
    return df


# --- 8. Коррекция количеств --------------------------------------------
def fix_quantities(df):
    bad = df["quantity"] <= 0
    log("=== 8. КОРРЕКЦИЯ КОЛИЧЕСТВ ===")
    log(f"Некорректных (<=0) quantity: {bad.sum():,} — заменены на 1")
    df.loc[bad, "quantity"] = 1
    log("")
    return df


# --- 9. Производные признаки + аналитика -------------------------------
def enrich(df):
    log("=== 9. ПРОИЗВОДНЫЕ ПРИЗНАКИ И АНАЛИТИКА ===")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df["cost"] = pd.to_numeric(df["cost"], errors="coerce")
    df["margin"] = (df["revenue"] - df["cost"]).round(2)
    df["margin_pct"] = (df["margin"] / df["revenue"] * 100).round(2)
    d = df["order_date"]
    df["year"] = d.dt.year
    df["month"] = d.dt.to_period("M").astype(str)
    df["quarter"] = d.dt.to_period("Q").astype(str)
    df["week"] = d.dt.isocalendar().week.astype(str)
    df["dow"] = d.dt.day_name()
    log("Добавлены: margin, margin_pct, year, month, quarter, week, dow")

    # ABC-анализ продуктов
    prod_rev = df.groupby("product_name")["revenue"].sum().sort_values(ascending=False)
    cum = prod_rev.cumsum() / prod_rev.sum()
    abc = pd.cut(cum, bins=[0, 0.80, 0.95, 1.0], labels=["A", "B", "C"])
    df["abc_class"] = df["product_name"].map(abc)
    log(f"ABC-анализ: {df.groupby('abc_class')['revenue'].sum().round(0).to_dict()}")

    # RFM-сегментация клиентов
    rfm = df.groupby("client_id").agg(
        recency=("order_date", lambda x: (df["order_date"].max() - x.max()).days),
        frequency=("order_id", "count"),
        monetary=("revenue", "sum"),
    )
    rfm["r"] = pd.qcut(rfm["recency"], 4, labels=[4, 3, 2, 1]).astype(int)
    rfm["f"] = pd.qcut(rfm["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    rfm["m"] = pd.qcut(rfm["monetary"], 4, labels=[1, 2, 3, 4]).astype(int)
    rfm["rfm_score"] = rfm["r"] + rfm["f"] + rfm["m"]
    rfm["segment"] = pd.cut(rfm["rfm_score"], bins=[0, 4, 7, 9, 12],
                            labels=["Уходящие", "Спящие", "Постоянные", "VIP"])
    df["client_segment"] = df["client_id"].map(rfm["segment"])
    log(f"RFM-сегменты (по клиентам): {rfm['segment'].value_counts().to_dict()}")
    log("")
    return df


# --- 10. Сохранение ----------------------------------------------------
def save_outputs(df):
    df.to_csv(OUT_CLEAN, index=False, encoding="utf-8-sig")
    dates = pd.date_range(df["order_date"].min(), df["order_date"].max())
    dim_date = pd.DataFrame({
        "date": dates, "year": dates.year,
        "month": dates.to_period("M").astype(str),
        "quarter": dates.to_period("Q").astype(str),
        "week": dates.isocalendar().week.astype(str),
        "dow": dates.day_name(),
    })
    dim_date.to_csv(OUT_DATE, index=False, encoding="utf-8-sig")
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT))
    log("=== 10. СОХРАНЕНИЕ ===")
    log(f"Очищенные данные: {OUT_CLEAN} ({len(df):,} строк, {df.shape[1]} колонок)")
    log(f"Измерение дат: {OUT_DATE}")
    log(f"Отчёт о очистке: {OUT_REPORT}")


def main():
    sales, clients, products = load_workbook()
    sales, clients, products = dedupe(sales, clients, products)
    clients, products = normalize_refs(clients, products)
    sales = merge_fact(sales, clients, products)
    sales = parse_dates(sales)
    sales = handle_missing(sales)
    sales = flag_outliers(sales)
    sales = fix_quantities(sales)
    sales = enrich(sales)
    save_outputs(sales)


if __name__ == "__main__":
    main()
