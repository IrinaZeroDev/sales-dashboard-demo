"""
Интерактивный дашборд продаж на Plotly Dash.

Финальная версия под ТЗ заказчика: только запрошенные метрики и разрезы.

KPI: объём продаж, количество транзакций, средний чек (с дельтой к прошлому периоду).
Графики: динамика продаж, продажи по регионам, продажи по категориям,
         тепловая карта «регион × категория».
Динамические фильтры: период (календарь + пресеты), регион, категория,
                      гранулярность тренда (день/неделя/месяц), учёт аномалий.

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

DATA = Path(__file__).parent / "data" / "sales_clean.csv"

df = pd.read_csv(DATA, parse_dates=["order_date"])
df = df.sort_values("order_date").reset_index(drop=True)

REGIONS = sorted(df["region"].unique().tolist())
CATEGORIES = sorted(df["category"].unique().tolist())
MIN_DATE, MAX_DATE = df["order_date"].min().date(), df["order_date"].max().date()
DEFAULT_START = (df["order_date"].max() - pd.DateOffset(months=6)).date()

ACCENT = "#2563eb"
ACCENT_RED = "#dc2626"
BG = "#f7f8fa"
CARD_BG = "#ffffff"
TEXT = "#1f2937"

CAT_SHORT = {
    "Электроника": "Электроника", "Бытовая техника": "Быт. техника",
    "Компьютеры и комплектующие": "Компьютеры", "Аксессуары": "Аксессуары",
    "Не определено": "Н/о",
}


# ---------- Стили --------------------------------------------------------
def label_style(marginTop: str = "0px") -> dict:
    return {"fontSize": "12px", "color": "#374151", "fontWeight": 600,
            "marginTop": marginTop, "marginBottom": "4px"}


def btn_style() -> dict:
    return {"fontSize": "11px", "padding": "5px 8px", "border": "1px solid #d1d5db",
            "borderRadius": "6px", "backgroundColor": "#fff", "cursor": "pointer", "color": TEXT}


def card_style() -> dict:
    return {"backgroundColor": CARD_BG, "padding": "16px 18px", "borderRadius": "12px",
            "boxShadow": "0 1px 3px rgba(0,0,0,0.08)", "border": "1px solid #eef0f3"}


def kpi_card(title: str, value: str, delta: float | None) -> html.Div:
    if delta is None:
        delta_html = html.Span("—", style={"color": "#9ca3af", "fontSize": "13px"})
    else:
        color = "#16a34a" if delta >= 0 else ACCENT_RED
        arrow = "▲" if delta >= 0 else "▼"
        delta_html = html.Span(f"{arrow} {delta:+.1f}% к пред. периоду",
                               style={"color": color, "fontSize": "13px", "fontWeight": 600})
    return html.Div(
        [html.Div(title, style={"color": "#6b7280", "fontSize": "13px", "marginBottom": "6px"}),
         html.Div(value, style={"fontSize": "26px", "fontWeight": 700, "color": TEXT}),
         html.Div(delta_html, style={"marginTop": "6px"})],
        style=card_style(),
    )


# ---------- Приложение --------------------------------------------------
app = Dash(__name__, title="Дашборд продаж")
app.layout = html.Div(
    [
        html.Div(
            [html.H1("Дашборд продаж", style={"margin": 0, "fontSize": "24px", "color": TEXT}),
             html.Div(f"Период данных: {MIN_DATE} — {MAX_DATE}",
                      style={"color": "#6b7280", "fontSize": "13px"})],
            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
                   "marginBottom": "16px", "width": "100%"},
        ),
        html.Div(
            [
                html.Div("Фильтры", style={"fontWeight": 700, "marginBottom": "12px", "color": TEXT}),
                html.Label("Период", style=label_style()),
                dcc.DatePickerRange(id="date-range", min_date_allowed=MIN_DATE, max_date_allowed=MAX_DATE,
                                    start_date=DEFAULT_START, end_date=MAX_DATE,
                                    display_format="DD.MM.YYYY", style={"width": "100%"}),
                html.Div(
                    [html.Button("Посл. месяц", id="btn-month", n_clicks=0, style=btn_style()),
                     html.Button("Посл. квартал", id="btn-quarter", n_clicks=0, style=btn_style()),
                     html.Button("Весь год", id="btn-year", n_clicks=0, style=btn_style())],
                    style={"display": "flex", "gap": "6px", "marginTop": "8px", "flexWrap": "wrap"},
                ),
                html.Label("Регион", style=label_style("14px")),
                dcc.Dropdown(id="region", options=REGIONS, multi=True, placeholder="Все регионы",
                             style={"fontSize": "13px"}),
                html.Label("Категория продукта", style=label_style("14px")),
                dcc.Dropdown(id="category", options=CATEGORIES, multi=True, placeholder="Все категории",
                             style={"fontSize": "13px"}),
                html.Label("Гранулярность тренда", style=label_style("14px")),
                dcc.RadioItems(id="granularity",
                               options=[{"label": x, "value": x} for x in ["День", "Неделя", "Месяц"]],
                               value="Месяц", inline=True, style={"fontSize": "13px"}),
                html.Label("Учитывать аномалии", style=label_style("14px")),
                dcc.RadioItems(id="outliers",
                               options=[{"label": "Да", "value": "yes"}, {"label": "Нет (только норма)", "value": "no"}],
                               value="yes", inline=True, style={"fontSize": "13px"}),
            ],
            style={"width": "240px", "flexShrink": 0, **card_style(), "height": "fit-content"},
        ),
        html.Div(
            [
                html.Div(
                    [html.Div(id="kpi-revenue"), html.Div(id="kpi-orders"), html.Div(id="kpi-check")],
                    style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "12px",
                           "marginBottom": "12px"},
                ),
                dcc.Graph(id="graph-trend", style={**card_style(), "height": "340px"}),
                dcc.Graph(id="graph-region", style={**card_style(), "height": "360px"}),
                dcc.Graph(id="graph-category", style={**card_style(), "height": "340px"}),
                dcc.Graph(id="graph-heatmap", style={**card_style(), "height": "380px"}),
            ],
            style={"flex": 1, "minWidth": 0},
        ),
    ],
    style={"display": "flex", "flexDirection": "column", "gap": "16px", "padding": "20px",
           "backgroundColor": BG, "minHeight": "100vh", "fontFamily": "Inter, Arial, sans-serif"},
)


# ---------- Фильтрация ---------------------------------------------------
def filter_df(start, end, regions, categories, outliers) -> pd.DataFrame:
    d = df[(df["order_date"] >= pd.Timestamp(start)) & (df["order_date"] <= pd.Timestamp(end))]
    if regions:
        d = d[d["region"].isin(regions)]
    if categories:
        d = d[d["category"].isin(categories)]
    if outliers == "no":
        d = d[d["is_outlier"] == 0]
    return d


def previous_window(start, end):
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    length = (e - s).days + 1
    pe = s - pd.Timedelta(days=1)
    return (pe - pd.Timedelta(days=length - 1)).date(), pe.date()


def fmt_money(x: float) -> str:
    if x >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f} млрд ₽"
    if x >= 1_000_000:
        return f"{x/1_000_000:.2f} млн ₽"
    if x >= 1_000:
        return f"{x/1_000:.0f} тыс ₽"
    return f"{x:,.0f} ₽"


def delta_pct(curr, prev) -> float | None:
    if not prev:
        return None
    return (curr - prev) / prev * 100


@callback(
    Output("date-range", "start_date"), Output("date-range", "end_date"),
    Input("btn-month", "n_clicks"), Input("btn-quarter", "n_clicks"), Input("btn-year", "n_clicks"),
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


@callback(
    Output("kpi-revenue", "children"), Output("kpi-orders", "children"), Output("kpi-check", "children"),
    Output("graph-trend", "figure"), Output("graph-region", "figure"),
    Output("graph-category", "figure"), Output("graph-heatmap", "figure"),
    Input("date-range", "start_date"), Input("date-range", "end_date"),
    Input("region", "value"), Input("category", "value"),
    Input("granularity", "value"), Input("outliers", "value"),
)
def update_dashboard(start, end, regions, categories, gran, outliers):
    d = filter_df(start, end, regions, categories, outliers)
    ps, pe = previous_window(start, end)
    d_prev = filter_df(ps, pe, regions, categories, outliers)

    revenue = d["revenue"].sum()
    orders = d["order_id"].nunique()
    avg_check = revenue / orders if orders else 0
    rev_p, ord_p = d_prev["revenue"].sum(), d_prev["order_id"].nunique()
    chk_p = rev_p / ord_p if ord_p else 0

    cards = [
        kpi_card("Объём продаж", fmt_money(revenue), delta_pct(revenue, rev_p)),
        kpi_card("Транзакции", f"{orders:,}".replace(",", " "), delta_pct(orders, ord_p)),
        kpi_card("Средний чек", fmt_money(avg_check), delta_pct(avg_check, chk_p)),
    ]

    # Тренд
    freq = {"День": "D", "Неделя": "W", "Месяц": "ME"}[gran]
    trend = d.set_index("order_date").resample(freq)["revenue"].sum().reset_index()
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(x=trend["order_date"], y=trend["revenue"], mode="lines+markers",
                                   line=dict(color=ACCENT, width=2.5), marker=dict(size=5),
                                   fill="tozeroy", fillcolor="rgba(37,99,235,0.08)", name="Объём продаж"))
    if gran == "День":
        out = d[d["is_outlier"] == 1]
        if len(out):
            fig_trend.add_trace(go.Scatter(x=out["order_date"], y=out["revenue"], mode="markers",
                                           marker=dict(color=ACCENT_RED, size=5, symbol="x", opacity=0.55),
                                           name="Аномалия"))
    fig_trend.update_layout(title="Динамика продаж", template="plotly_white", height=320,
                            margin=dict(t=45, b=35, l=50, r=20), hovermode="x unified", showlegend=False)
    fig_trend.update_yaxes(title_text="Объём продаж, ₽", tickformat=",.0f")

    # По регионам
    by_reg = d.groupby("region")["revenue"].sum().sort_values().reset_index()
    by_reg["lbl"] = by_reg["revenue"].map(lambda v: f"{v:,.0f}".replace(",", " "))
    fig_region = px.bar(by_reg, x="revenue", y="region", orientation="h", color="revenue",
                        color_continuous_scale="Blues", text="lbl")
    fig_region.update_layout(title="Продажи по регионам", template="plotly_white", height=340,
                             margin=dict(t=45, b=30, l=210, r=20), coloraxis_showscale=False,
                             yaxis_title="", xaxis_title="", xaxis_showticklabels=False,
                             yaxis=dict(tickfont=dict(size=9)))
    fig_region.update_traces(texttemplate="%{text}", textposition="outside", textfont_size=9)
    fig_region.update_xaxes(range=[0, by_reg["revenue"].max() * 1.2])

    # По категориям
    by_cat = d.groupby("category")["revenue"].sum().sort_values(ascending=False).reset_index()
    by_cat["lbl"] = by_cat["revenue"].map(lambda v: f"{v:,.0f}".replace(",", " "))
    by_cat["short"] = by_cat["category"].map(lambda c: CAT_SHORT.get(c, c))
    fig_cat = px.bar(by_cat, x="short", y="revenue", text="lbl",
                    color_discrete_sequence=["#4e79a7", "#59a14f", "#f28e2b", "#e15759", "#76b7b2"])
    fig_cat.update_layout(title="Продажи по категориям", template="plotly_white", height=300,
                          margin=dict(t=45, b=30, l=50, r=20), showlegend=False,
                          xaxis_title="", yaxis_title="", xaxis=dict(tickfont=dict(size=11)),
                          yaxis_showticklabels=False)
    fig_cat.update_traces(texttemplate="%{text}", textposition="auto", textfont_size=11)

    # Тепловая карта регион × категория
    heat = d.pivot_table(index="region", columns="category", values="revenue", aggfunc="sum", fill_value=0)
    fig_heat = go.Figure(data=go.Heatmap(
        z=heat.values, x=[CAT_SHORT.get(c, c) for c in heat.columns], y=heat.index,
        colorscale="Blues", hovertemplate="Регион: %{y}<br>Категория: %{x}<br>Продажи: %{z:,.0f}<extra></extra>"))
    fig_heat.update_layout(title="Продажи: регион × категория", template="plotly_white", height=360,
                           margin=dict(t=45, b=60, l=170, r=20),
                           xaxis=dict(tickangle=0, tickfont=dict(size=10)),
                           yaxis=dict(tickfont=dict(size=8)))

    return (*cards, fig_trend, fig_region, fig_cat, fig_heat)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)
