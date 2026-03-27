"""
charts.py – Plotly visualizations for financial dashboard.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

_DARK = "rgba(0,0,0,0)"
_FONT = dict(color="#F1F5F9", family="Arial, sans-serif", size=12)
_GRID = "#334155"

_BASE = dict(
    paper_bgcolor=_DARK,
    plot_bgcolor=_DARK,
    font=_FONT,
    margin=dict(l=40, r=20, t=48, b=40),
)

_C = {"A": "#2563EB", "P": "#DC2626", "X": "#64748B",
      "income": "#059669", "expense": "#D97706"}


def balance_bar(total_assets: float, total_liab: float) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=["Total Assets", "Total Liabilities"],
        y=[total_assets, total_liab],
        marker_color=[_C["A"], _C["P"]],
        text=[f"{v/1e6:.2f}M" for v in [total_assets, total_liab]],
        textposition="auto",
    ))
    fig.update_layout(title="Assets vs Liabilities", **_BASE,
                      xaxis=dict(showgrid=False),
                      yaxis=dict(showgrid=True, gridcolor=_GRID))
    return fig


def assets_pie(assets_by_group: pd.DataFrame) -> go.Figure:
    df = assets_by_group[assets_by_group["amount"] > 0].copy()
    if df.empty:
        return go.Figure()
    fig = go.Figure(go.Pie(
        labels=df["group"], values=df["amount"],
        hole=0.4,
        marker=dict(colors=px.colors.qualitative.Set3),
        textinfo="label+percent",
    ))
    fig.update_layout(title="Asset Structure", **_BASE)
    return fig


def liabilities_pie(liab_by_group: pd.DataFrame) -> go.Figure:
    df = liab_by_group[liab_by_group["amount"] > 0].copy()
    if df.empty:
        return go.Figure()
    fig = go.Figure(go.Pie(
        labels=df["group"], values=df["amount"],
        hole=0.4,
        marker=dict(colors=px.colors.qualitative.Pastel),
        textinfo="label+percent",
    ))
    fig.update_layout(title="Liability Structure", **_BASE)
    return fig


def mapp_group_bar(mapp_df: pd.DataFrame) -> go.Figure:
    if mapp_df is None or mapp_df.empty:
        return go.Figure()
    mapped = mapp_df[mapp_df["mapping_status"] == "mapped"]
    grp = mapped.groupby(["group", "side"])["persaldo"].sum().reset_index()
    color_map = {"A": _C["A"], "P": _C["P"], "X": _C["X"]}
    fig = px.bar(grp, x="group", y="persaldo", color="side",
                 color_discrete_map=color_map,
                 title="Net Balance by Group",
                 labels={"persaldo": "Net Balance", "group": "Group"})
    fig.update_layout(**_BASE,
                      xaxis=dict(tickangle=-40, showgrid=False),
                      yaxis=dict(showgrid=True, gridcolor=_GRID))
    return fig


def pnl_waterfall(pnl_df: pd.DataFrame, net_result: float) -> go.Figure:
    if pnl_df is None or pnl_df.empty:
        return go.Figure()
    income  = pnl_df[pnl_df["persaldo_pnl"] > 0]["persaldo_pnl"].sum()
    expense = pnl_df[pnl_df["persaldo_pnl"] < 0]["persaldo_pnl"].sum()
    fig = go.Figure(go.Waterfall(
        x=["Income", "Expenses", "Net Result"],
        y=[income, expense, net_result],
        measure=["relative", "relative", "total"],
        connector=dict(line=dict(color="#94A3B8")),
        increasing=dict(marker_color=_C["income"]),
        decreasing=dict(marker_color=_C["expense"]),
        totals=dict(marker_color="#2563EB"),
    ))
    fig.update_layout(title="P&L Waterfall", **_BASE,
                      yaxis=dict(showgrid=True, gridcolor=_GRID))
    return fig


def mapping_donut(n_mapped: int, n_unmapped: int, n_excluded: int) -> go.Figure:
    labels = ["Mapped", "Unmapped", "Excluded (9xx)"]
    values = [n_mapped, n_unmapped, n_excluded]
    colors = [_C["income"], _C["P"], _C["X"]]
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.5,
        marker=dict(colors=colors),
    ))
    fig.update_layout(title="Mapping Coverage", **_BASE)
    return fig
