"""
Интерактивный дашборд продаж на Plotly Dash.

Динамические фильтры:
  - период (DatePickerRange) + пресеты;
  - регион, категория продукта, сегмент клиента, тип клиента (multi-select);
  - гранулярность временного ряда (день / неделя / месяц);
  - переключатель учёта аномалий (выбросов по выручке).

Метрики: выручка, маржа, число сделок, средний чек — с дельтой к предыдущему
сопоставимому периоду. Тренды, тепловая карта «регион × категория», топ
продуктов (ABC), структура по сегментам клиентов.

Запуск локально:
    python app.py
Откроется на http://127.0.0.1:8050
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, callback, dcc, html
from plotly.subplots import make_subplots

DATA = Path(__file__).parent / "data" / "sales_clean.csv"

# ---------- Данные -------------------------------------------------------
df = pd.read_csv(DATA, parse_dates=["order_date"])
df = df.sort_values("order_date").reset_index(drop=True)

REGIONS = sorted(df["region"].unique().tolist())
CATEGORIES = sorted(df["category"].unique().tolist())
SEGMENTS = ["VIP", "Постоянные", "Спящие", "Уходящие"]
CLIENT_TYPES = sorted(df["client_type"].unique().tolist())
MIN_DATE, MAX_DATE = df["order_date"].min().date(), df["order_date"].max().date()
DEFAULT_START = (df["order_date"].max() - pd.DateOffset(months=6)).date()

# Цветовая палитра
PALETTE = px.colors.qualitative.Set2
ACCENT = "#2563eb"
ACCENT_RED = "#dc2626"
BG = "#f7f8fa"
CARD_BG = "#ffffff"
TEXT = "#1f2937"

# ---------- Стили --------------------------------------------------------
def label_style(marginTop: str = "0px") -> dict:
    return {"fontSize": "12px", "color": "#374151", "fontWeight": 600, "marginTop": marginTop,
            "marginBottom": "4px"}


def btn_style() -> dict:
    return {"fontSize": "11px", "padding": "5px 8px", "border": "1px solid #d1d5db",
            "borderRadius": "6px", "backgroundColor": "#fff", "cursor": "pointer", "color": TEXT}


def dd_style() -> dict:
    return {"fontSize": "13px"}


def card_style() -> dict:
    return {
        "backgroundColor": CARD_BG,
        "padding": "16px 18px",
        "borderRadius": "12px",
        "boxShadow": "0 1px 3px rgba(0,0,0,0.08)",
        "border": "1px solid #eef0f3",
    }


def kpi_card(title: str, value: str, delta: float | None, fmt: str = "money") -> html.Div:
    if delta is None:
        delta_html = html.Span("—", style={"color": "#9ca3af", "fontSize": "13px"})
    else:
        color = "#16a34a" if delta >= 0 else ACCENT_RED
        arrow = "▲" if delta >= 0 else "▼"
        delta_html = html.Span(
            f"{arrow} {delta:+.1f}% к пред. периоду",
            style={"color": color, "fontSize": "13px", "fontWeight": 600},
        )
    return html.Div(
        [
            html.Div(title, style={"color": "#6b7280", "fontSize": "13px", "marginBottom": "6px"}),
            html.Div(value, style={"fontSize": "26px", "fontWeight": 700, "color": TEXT}),
            html.Div(delta_html, style={"marginTop": "6px"}),
        ],
        style=card_style(),
    )


app = Dash(__name__, title="Дашборд продаж")
app.layout = html.Div(
    [
        html.Div(
            [
                html.H1("Дашборд продаж", style={"margin": 0, "fontSize": "24px", "color": TEXT}),
                html.Div(
                    f"Период данных: {MIN_DATE} — {MAX_DATE}",
                    style={"color": "#6b7280", "fontSize": "13px"},
                ),
            ],
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                   "marginBottom": "16px", "width": "100%"},
        ),
        html.Div(
            [
        # Сайдбар с фильтрами
        html.Div(
            [
                html.Div("Фильтры", style={"fontWeight": 700, "marginBottom": "12px", "color": TEXT}),
                html.Label("Период", style=label_style()),
                dcc.DatePickerRange(
                    id="date-range",
                    min_date_allowed=MIN_DATE,
                    max_date_allowed=MAX_DATE,
                    start_date=DEFAULT_START,
                    end_date=MAX_DATE,
                    display_format="DD.MM.YYYY",
                    style={"width": "100%"},
                ),
                html.Div(
                    [
                        html.Button("Посл. месяц", id="btn-month", n_clicks=0, style=btn_style()),
                        html.Button("Посл. квартал", id="btn-quarter", n_clicks=0, style=btn_style()),
                        html.Button("Весь год", id="btn-year", n_clicks=0, style=btn_style()),
                    ],
                    style={"display": "flex", "gap": "6px", "marginTop": "8px", "flexWrap": "wrap"},
                ),
                html.Label("Регион", style=label_style(marginTop="14px")),
                dcc.Dropdown(id="region", options=REGIONS, multi=True, placeholder="Все регионы",
                             style=dd_style()),
                html.Label("Категория продукта", style=label_style(marginTop="14px")),
                dcc.Dropdown(id="category", options=CATEGORIES, multi=True, placeholder="Все категории",
                             style=dd_style()),
                html.Label("Сегмент клиента (RFM)", style=label_style(marginTop="14px")),
                dcc.Dropdown(id="segment", options=SEGMENTS, multi=True, placeholder="Все сегменты",
                             style=dd_style()),
                html.Label("Тип клиента", style=label_style(marginTop="14px")),
                dcc.Dropdown(id="ctype", options=CLIENT_TYPES, multi=True, placeholder="Все типы",
                             style=dd_style()),
                html.Label("Гранулярность тренда", style=label_style(marginTop="14px")),
                dcc.RadioItems(
                    id="granularity",
                    options=[{"label": x, "value": x} for x in ["День", "Неделя", "Месяц"]],
                    value="Месяц",
                    inline=True,
                    style={"fontSize": "13px"},
                ),
                html.Label("Учитывать аномалии", style=label_style(marginTop="14px")),
                dcc.RadioItems(
                    id="outliers",
                    options=[{"label": "Да", "value": "yes"}, {"label": "Нет (только норма)", "value": "no"}],
                    value="yes",
                    inline=True,
                    style={"fontSize": "13px"},
                ),
            ],
            style={"width": "240px", "flexShrink": 0, **card_style(), "height": "fit-content"},
        ),
        # Основная область
        html.Div(
            [
                html.Div(
                    [
                        html.Div(id="kpi-revenue"),
                        html.Div(id="kpi-margin"),
                        html.Div(id="kpi-orders"),
                        html.Div(id="kpi-check"),
                    ],
                    style={"display": "grid", "gridTemplateColumns": "repeat(4, 1fr)", "gap": "12px",
                           "marginBottom": "12px"},
                ),
                dcc.Graph(id="graph-trend", style={**card_style(), "height": "340px"}),
                dcc.Graph(id="graph-region", style={**card_style(), "height": "340px"}),
                dcc.Graph(id="graph-heatmap", style={**card_style(), "height": "360px"}),
                dcc.Graph(id="graph-top-products", style={**card_style(), "height": "360px"}),
                dcc.Graph(id="graph-segments", style={**card_style(), "height": "320px"}),
            ],
            style={"flex": 1, "minWidth": 0},
        ),
            ],
            style={"display": "flex", "gap": "16px"},
        ),
    ],
    style={"display": "flex", "flexDirection": "column", "gap": "16px", "padding": "20px",
           "backgroundColor": BG, "minHeight": "100vh", "fontFamily": "Inter, Arial, sans-serif"},
)
# ---------- Приложение --------------------------------------------------
def filter_df(start, end, regions, categories, segments, ctypes, outliers) -> pd.DataFrame:
    d = df[(df["order_date"] >= pd.Timestamp(start)) & (df["order_date"] <= pd.Timestamp(end))]
    if regions:
        d = d[d["region"].isin(regions)]
    if categories:
        d = d[d["category"].isin(categories)]
    if segments:
        d = d[d["client_segment"].isin(segments)]
    if ctypes:
        d = d[d["client_type"].isin(ctypes)]
    if outliers == "no":
        d = d[d["is_outlier"] == 0]
    return d


def previous_period_window(start, end):
    """Окно предыдущего сопоставимого периода той же длины."""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    length = (e - s).days + 1
    prev_e = s - pd.Timedelta(days=1)
    prev_s = prev_e - pd.Timedelta(days=length - 1)
    return prev_s, prev_e


def fmt_money(x: float) -> str:
    if x >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f} млрд ₽"
    if x >= 1_000_000:
        return f"{x/1_000_000:.2f} млн ₽"
    if x >= 1_000:
        return f"{x/1_000:.0f} тыс ₽"
    return f"{x:,.0f} ₽"


def delta_pct(curr, prev) -> float | None:
    if prev == 0 or prev is None:
        return None
    return (curr - prev) / prev * 100


# ---------- Callback пресетов периода ------------------------------------
@callback(
    Output("date-range", "start_date"),
    Output("date-range", "end_date"),
    Input("btn-month", "n_clicks"),
    Input("btn-quarter", "n_clicks"),
    Input("btn-year", "n_clicks"),
    prevent_initial_call=True,
)
def set_preset(month, quarter, year):
    from dash import ctx
    end = pd.Timestamp(MAX_DATE)
    if ctx.triggered_id == "btn-month":
        start = end - pd.DateOffset(months=1)
    elif ctx.triggered_id == "btn-quarter":
        start = end - pd.DateOffset(months=3)
    else:
        start = pd.Timestamp(MIN_DATE)
    return start.date(), end.date()


# ---------- Главный callback --------------------------------------------
@callback(
    Output("kpi-revenue", "children"),
    Output("kpi-margin", "children"),
    Output("kpi-orders", "children"),
    Output("kpi-check", "children"),
    Output("graph-trend", "figure"),
    Output("graph-region", "figure"),
    Output("graph-heatmap", "figure"),
    Output("graph-top-products", "figure"),
    Output("graph-segments", "figure"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
    Input("region", "value"),
    Input("category", "value"),
    Input("segment", "value"),
    Input("ctype", "value"),
    Input("granularity", "value"),
    Input("outliers", "value"),
)
def update_dashboard(start, end, regions, categories, segments, ctypes, gran, outliers):
    d = filter_df(start, end, regions, categories, segments, ctypes, outliers)

    # Предыдущий сопоставимый период для дельты
    ps, pe = previous_period_window(start, end)
    d_prev = filter_df(ps.date(), pe.date(), regions, categories, segments, ctypes, outliers)

    revenue = d["revenue"].sum()
    margin = d["margin"].sum()
    orders = d["order_id"].nunique()
    avg_check = revenue / orders if orders else 0

    rev_prev = d_prev["revenue"].sum()
    mar_prev = d_prev["margin"].sum()
    ord_prev = d_prev["order_id"].nunique()
    chk_prev = rev_prev / ord_prev if ord_prev else 0

    cards = [
        kpi_card("Объём продаж", fmt_money(revenue), delta_pct(revenue, rev_prev)),
        kpi_card("Маржа", fmt_money(margin), delta_pct(margin, mar_prev)),
        kpi_card("Транзакции", f"{orders:,}".replace(",", " "), delta_pct(orders, ord_prev)),
        kpi_card("Средний чек", fmt_money(avg_check), delta_pct(avg_check, chk_prev)),
    ]

    # Тренд по гранулярности
    freq = {"День": "D", "Неделя": "W", "Месяц": "ME"}[gran]
    trend = (
        d.set_index("order_date")
        .resample(freq)["revenue"].sum()
        .reset_index()
    )
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=trend["order_date"], y=trend["revenue"], mode="lines+markers",
        line=dict(color=ACCENT, width=2.5), marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.08)", name="Выручка",
    ))
    # Точки-аномалии поверх (только при дневной гранулярности, иначе — шум)
    out = d[d["is_outlier"] == 1]
    if len(out) and gran == "День":
        fig_trend.add_trace(go.Scatter(
            x=out["order_date"], y=out["revenue"], mode="markers",
            marker=dict(color=ACCENT_RED, size=5, symbol="x", opacity=0.55),
            name="Аномалия",
        ))
    fig_trend.update_layout(
        title="Динамика выручки", template="plotly_white", height=320,
        margin=dict(t=45, b=35, l=50, r=20),
        hovermode="x unified",
        showlegend=False,
    )
    fig_trend.update_yaxes(title_text="Выручка, ₽", tickformat=",.0f")
    fig_trend.update_xaxes(title_text="")

    # Выручка по регионам
    by_region = d.groupby("region")["revenue"].sum().sort_values().reset_index()
    by_region["lbl"] = by_region["revenue"].map(lambda v: f"{v:,.0f}".replace(",", " "))
    fig_region = px.bar(
        by_region, x="revenue", y="region", orientation="h",
        color="revenue", color_continuous_scale="Blues", text="lbl",
    )
    fig_region.update_layout(
        title="Выручка по регионам", template="plotly_white", height=300,
        margin=dict(t=45, b=20, l=210, r=20), coloraxis_showscale=False,
        yaxis_title="", xaxis_title="", xaxis_showticklabels=False,
        yaxis=dict(tickfont=dict(size=9)),
    )
    fig_region.update_traces(texttemplate="%{text}", textposition="outside", textfont_size=9)
    fig_region.update_xaxes(range=[0, by_region["revenue"].max() * 1.2])

    # Тепловая карта регион × категория
    cat_short = {
        "Электроника": "Электроника",
        "Бытовая техника": "Быт. техника",
        "Компьютеры и комплектующие": "Компьютеры",
        "Аксессуары": "Аксессуары",
    }
    heat = d.pivot_table(index="region", columns="category", values="revenue",
                         aggfunc="sum", fill_value=0)
    heat.columns = [cat_short.get(c, c) for c in heat.columns]
    fig_heat = go.Figure(data=go.Heatmap(
        z=heat.values, x=heat.columns, y=heat.index,
        colorscale="Blues", hovertemplate="Регион: %{y}<br>Категория: %{x}<br>Выручка: %{z:,.0f}<extra></extra>",
        texttemplate=None,
    ))
    fig_heat.update_layout(
        title="Выручка: регион × категория", template="plotly_white", height=300,
        margin=dict(t=45, b=55, l=170, r=20),
        xaxis=dict(tickangle=0, tickfont=dict(size=10)),
        yaxis=dict(tickfont=dict(size=8)),
    )

    # Топ продуктов (ABC-окраска)
    top = d.groupby(["product_name", "abc_class"])["revenue"].sum().reset_index()
    top = top.sort_values("revenue", ascending=False).head(12)
    top["short"] = top["product_name"].apply(
        lambda x: x if len(x) <= 28 else x[:27] + "…"
    )
    fig_top = px.bar(
        top, y="short", x="revenue", color="abc_class", hover_name="product_name",
        color_discrete_map={"A": "#16a34a", "B": "#f59e0b", "C": "#9ca3af"},
        orientation="h", category_orders={"short": top["short"][::-1].tolist()},
    )
    fig_top.update_layout(
        title="Топ-12 продуктов", template="plotly_white", height=300,
        margin=dict(t=45, b=20, l=185, r=20),
        yaxis_title="", xaxis_title="", showlegend=True,
        legend=dict(orientation="h", y=1.08, title="Класс ABC"),
        yaxis=dict(tickfont=dict(size=9)),
    )

    # Структура по сегментам клиентов
    seg = d.groupby("client_segment")["revenue"].sum().reindex(SEGMENTS).fillna(0).reset_index()
    seg["lbl"] = seg["revenue"].map(lambda v: f"{v:,.0f}".replace(",", " "))
    fig_seg = px.bar(
        seg, x="client_segment", y="revenue", color="client_segment",
        color_discrete_sequence=PALETTE, text="lbl",
    )
    fig_seg.update_layout(
        title="Выручка по сегментам (RFM)", template="plotly_white", height=300,
        margin=dict(t=50, b=40, l=50, r=20), showlegend=False,
        xaxis_title="", yaxis_title="", xaxis=dict(tickfont=dict(size=11)),
    )
    fig_seg.update_traces(texttemplate="%{text}", textposition="outside", textfont_size=10)

    return (*cards, fig_trend, fig_region, fig_heat, fig_top, fig_seg)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
