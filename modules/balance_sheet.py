"""
balance_sheet.py
Builds structured balance sheet from Mapp DataFrame.
Only uses accounts with side A or P (mapped rows only).
X accounts are excluded from BS.
"""
from __future__ import annotations

import pandas as pd


def build_balance_sheet(mapp_df: pd.DataFrame) -> dict:
    """
    Returns dict:
      assets_by_group     pd.DataFrame  [group, amount]
      liabilities_by_group pd.DataFrame [group, amount]
      total_assets        float
      total_liabilities   float
      difference          float
    """
    if mapp_df is None or mapp_df.empty:
        return _empty()

    mapped = mapp_df[mapp_df["mapping_status"] == "mapped"]

    assets_df = mapped[mapped["side"] == "A"]
    liab_df   = mapped[mapped["side"] == "P"]

    assets_by_group = (
        assets_df.groupby("group")["persaldo"]
        .sum()
        .reset_index()
        .rename(columns={"persaldo": "amount"})
        .sort_values("amount", ascending=False)
    )
    liab_by_group = (
        liab_df.groupby("group")["persaldo"]
        .sum()
        .reset_index()
        .rename(columns={"persaldo": "amount"})
        .sort_values("amount", ascending=False)
    )

    total_assets = float(assets_by_group["amount"].sum())
    total_liab   = float(liab_by_group["amount"].sum())
    difference   = total_assets - total_liab

    return {
        "assets_by_group":      assets_by_group,
        "liabilities_by_group": liab_by_group,
        "total_assets":         total_assets,
        "total_liabilities":    total_liab,
        "difference":           difference,
    }


def _empty() -> dict:
    cols = ["group", "amount"]
    return {
        "assets_by_group":      pd.DataFrame(columns=cols),
        "liabilities_by_group": pd.DataFrame(columns=cols),
        "total_assets":         0.0,
        "total_liabilities":    0.0,
        "difference":           0.0,
    }
