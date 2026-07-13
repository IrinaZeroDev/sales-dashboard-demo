"""
Генерация демонстрационного Excel-файла с историей продаж за 12 месяцев.

Структура соответствует реальным данным заказчика: справочники клиентов и
продуктов лежат в ОТДЕЛЬНЫХ таблицах (листах), а не в одной плоской.

Листы:
  Продажи  — таблица фактов (order_id, order_date, client_id, product_id,
             quantity, unit_price, discount, revenue, cost, manager).
  Клиенты  — справочник клиентов (client_id, client_name, client_type, region).
  Продукты — справочник продуктов (product_id, product_name, category,
             base_price, base_cost).

Регион продаж берётся из справочника клиентов (region клиента) — это
распространённый случай и хорошо демонстрирует ценность merge со справочником.

Намеренно вносится «грязь», которую обрабатывает clean_data.py:
  - дубликаты строк факта;
  - пропуски в отдельных полях;
  - выбросы по выручке;
  - отрицательные/нулевые количества;
  - даты в разных форматах (строкой);
  - несогласованные названия регионов и категорий в справочниках;
  - «висящие» ключи (client_id/product_id, которых нет в справочнике).

Запуск:
    python generate_data.py
Результат: data/sales_raw.xlsx
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Справочники ---------------------------------------------------------
REGIONS = {
    "Москва и МО": 0.30, "Санкт-Петербург и ЛО": 0.18,
    "Краснодарский край": 0.10, "Свердловская область": 0.08,
    "Республика Татарстан": 0.07, "Новосибирская область": 0.06,
    "Нижегородская область": 0.05, "Самарская область": 0.04,
    "Республика Башкортостан": 0.04, "Приморский край": 0.04,
    "Ростовская область": 0.04,
}
CATEGORIES = {
    "Электроника": {
        "Смартфон Galaxy A55": (22000, 16000),
        "Ноутбук ProBook 14": (65000, 48000),
        "Беспроводные наушники AirBuds": (8500, 5200),
        "Планшет Tab S9": (55000, 41000),
        "Умные часы Watch S": (19000, 13000),
    },
    "Бытовая техника": {
        "Робот-пылесос CleanBot": (32000, 21000),
        "Кофемашина BaristaPro": (48000, 33000),
        "Микроволновая печь MWave": (9500, 6200),
        "Посудомоечная машина DishMak": (41000, 29000),
    },
    "Компьютеры и комплектующие": {
        "Монитор 27 4K": (38000, 27000),
        "SSD 1TB NVMe": (9800, 5900),
        "Игровая клавиатура MechKeys": (12500, 7400),
        "Видеокарта RTX-серия": (120000, 92000),
    },
    "Аксессуары": {
        "Зарядное устройство USB-C 65W": (3200, 1700),
        "Чехол для смартфона": (1200, 400),
        "Кабель USB-C 2м": (900, 350),
        "Внешний аккумулятор 20000mAh": (4500, 2400),
    },
}
CLIENT_TYPES = {"B2B-Крупный": 0.15, "B2B-Средний": 0.25, "B2B-Малый": 0.25, "B2C": 0.35}
FIRST_NAMES = [
    "ООС", "ТехноГрупп", "ЭлитТрейд", "СеверВектор", "ЮгСервис", "ВостокСнаб",
    "Альфа-Дистрибуция", "МегаОпт", "ПрофКомплект", "Стрела", "Дельта-Маркет",
    "ГрандРитейл", "Оникс", "ПлатинаТрейд", "АврораСервис", "Вектор-М", "ЛидерОпт",
    "Квант-С", "Прогресс-СПб", "Сфера-Юг",
]
LAST_TOKENS = ["ООО", "АО", "ИП", "ТД", "Компания", "Групп", "Сервис"]

END = datetime(2026, 7, 12)
START = END - timedelta(days=365)


def dirty_str(s: str) -> str:
    variants = [s, s.upper(), s.lower(), s.replace(" ", "  "), s + " ", " " + s,
                s.replace("о", "0").replace("О", "0")]
    return random.choice(variants)


# --- Справочник клиентов ------------------------------------------------
def build_clients(n: int = 250) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "client_id": f"C{i:04d}",
            "client_name": f"{random.choice(FIRST_NAMES)}-{random.choice(LAST_TOKENS)}-{i:03d}",
            "client_type": random.choices(list(CLIENT_TYPES), weights=list(CLIENT_TYPES.values()))[0],
            "region": random.choices(list(REGIONS), weights=list(REGIONS.values()))[0],
        })
    df = pd.DataFrame(rows)
    # Грязь в справочнике: опечатки/регистр/пробелы в регионе и client_type
    df["region"] = df["region"].apply(dirty_str)
    df["client_type"] = df["client_type"].apply(lambda x: dirty_str(x) if random.random() < 0.1 else x)
    # Пропуски
    df.loc[df.sample(frac=0.01, random_state=1).index, "region"] = np.nan
    df.loc[df.sample(frac=0.005, random_state=2).index, "client_type"] = np.nan
    return df


# --- Справочник продуктов ----------------------------------------------
def build_products() -> pd.DataFrame:
    rows = []
    pid = 1
    for cat, items in CATEGORIES.items():
        for name, (price, cost) in items.items():
            rows.append({
                "product_id": f"P{pid:03d}",
                "product_name": name,
                "category": cat,
                "base_price": price,
                "base_cost": cost,
            })
            pid += 1
    df = pd.DataFrame(rows)
    # Грязь в категории
    df["category"] = df["category"].apply(dirty_str)
    # Дублирующая запись по одному продукту (для проверки дедупликации справочника)
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    return df


# --- Таблица фактов ------------------------------------------------------
def build_sales(clients: pd.DataFrame, products: pd.DataFrame, n_rows: int = 14000) -> pd.DataFrame:
    client_ids = clients["client_id"].tolist()
    product_rows = products[["product_id", "base_price", "base_cost"]].drop_duplicates("product_id").to_dict("records")
    rows = []
    for _ in range(n_rows):
        date = START + timedelta(days=random.randint(0, 364))
        month_weight = {11: 1.8, 12: 2.0, 3: 1.3, 6: 1.2, 7: 1.1}.get(date.month, 1.0)
        if random.random() > 0.6 * month_weight / 1.5:
            continue
        p = random.choice(product_rows)
        qty = int(np.random.poisson(3)) + 1
        discount = random.choices([0.0, 0.05, 0.10, 0.15, 0.20, 0.30],
                                   weights=[40, 20, 15, 10, 10, 5])[0]
        revenue = round(p["base_price"] * qty * (1 - discount), 2)
        rows.append({
            "order_id": f"ORD-{random.randint(100000, 999999)}",
            "order_date": date,
            "client_id": random.choice(client_ids),
            "product_id": p["product_id"],
            "quantity": qty,
            "unit_price": p["base_price"],
            "discount": discount,
            "revenue": revenue,
            "cost": round(p["base_cost"] * qty, 2),
            "manager": random.choice(["Иванов И.И.", "Петрова А.С.", "Сидоров В.П.",
                                      "Кузнецова Е.Д.", "Морозов А.Р."]),
        })
    df = pd.DataFrame(rows)

    # Грязь в факте
    # 1. Дубликаты
    df = pd.concat([df, df.sample(frac=0.015, random_state=7)], ignore_index=True)
    # 2. Пропуски
    df.loc[df.sample(frac=0.01, random_state=1).index, "client_id"] = np.nan
    df.loc[df.sample(frac=0.005, random_state=3).index, "revenue"] = np.nan
    # 3. Выбросы по выручке
    df.loc[df.sample(frac=0.004, random_state=4).index, "revenue"] *= 8
    # 4. Отрицательные/нулевые количества
    df.loc[df.sample(frac=0.002, random_state=5).index, "quantity"] = random.choice([-2, -1, 0])
    # 5. «Висящие» ключи (нет в справочнике)
    df.loc[df.sample(frac=0.003, random_state=6).index, "client_id"] = "C9999"
    df.loc[df.sample(frac=0.002, random_state=8).index, "product_id"] = "P999"
    # 6. Даты в разных форматах (строкой)
    fmts = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d %b %Y"]
    df["order_date"] = df["order_date"].dt.strftime("%Y-%m-%d")
    df["order_date"] = df["order_date"].apply(
        lambda d: datetime.strptime(d, "%Y-%m-%d").strftime(random.choice(fmts))
    )
    # 7. Лишние пробелы
    df["manager"] = df["manager"].apply(lambda x: x + " " if random.random() < 0.05 else x)
    return df.sample(frac=1, random_state=9).reset_index(drop=True)


def main() -> None:
    clients = build_clients()
    products = build_products()
    sales = build_sales(clients, products)

    out_path = OUT_DIR / "sales_raw.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        sales.to_excel(xw, sheet_name="Продажи", index=False)
        clients.to_excel(xw, sheet_name="Клиенты", index=False)
        products.to_excel(xw, sheet_name="Продукты", index=False)
    print(f"OK: {out_path}")
    print(f"  Продажи: {len(sales):,} строк | Клиенты: {len(clients)} | Продукты: {len(products)}")
    print("  Листы: Продажи, Клиенты, Продукты")


if __name__ == "__main__":
    main()
