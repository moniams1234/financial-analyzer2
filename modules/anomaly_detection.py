"""
anomaly_detection.py
Red flag detection.

Each flag: {type: error|warning|success, category: str, message: str}
"""
from __future__ import annotations

import pandas as pd
import numpy as np


def build_red_flags(
    df: pd.DataFrame | None,
    mapp_df: pd.DataFrame | None,
    bs: dict,
    kpis: dict,
    warnings: list[str],
) -> list[dict]:
    flags: list[dict] = []

    def flag(t: str, cat: str, msg: str):
        flags.append({"type": t, "category": cat, "message": msg})

    # Parser warnings
    for w in warnings:
        flag("warning", "Parser", w)

    # No data
    if df is None or df.empty:
        flag("error", "Data", "No data could be parsed from the trial balance file.")
        return flags

    # Required columns
    for col in ["account_number", "saldo_dt", "saldo_ct"]:
        if col not in df.columns:
            flag("error", "Missing Column", f"Column '{col}' not found.")

    # Non-numeric check: warn only if ALL saldo columns are zero AND persaldo is also all zero
    if "saldo_dt" in df.columns and "saldo_ct" in df.columns and "persaldo" in df.columns:
        nonzero = (df["saldo_dt"] != 0) | (df["saldo_ct"] != 0) | (df["persaldo"] != 0)
        if nonzero.sum() == 0:
            flag("warning", "Data Quality",
                 "Wszystkie kolumny saldo mają wartość zero – sprawdź detekcję kolumn.")

    if mapp_df is None or mapp_df.empty:
        flag("error", "Mapping", "Mapping result is empty.")
        return flags

    # Unmapped accounts
    n_unmapped = kpis.get("unmapped_accounts", 0)
    n_total    = kpis.get("total_accounts", 1)
    n_mapped   = kpis.get("mapped_accounts", 0)
    n_excl     = kpis.get("excluded_accounts", 0)

    active = n_total - n_excl
    if active > 0:
        pct_unmapped = n_unmapped / active * 100
    else:
        pct_unmapped = 0.0

    if n_unmapped == 0:
        flag("success", "Mapping", f"All {n_mapped} active accounts mapped.")
    elif pct_unmapped < 5:
        flag("warning", "Mapping", f"{n_unmapped} accounts ({pct_unmapped:.1f}%) not in mapping file.")
    else:
        flag("error", "Mapping",
             f"{n_unmapped} accounts ({pct_unmapped:.1f}%) not mapped. Add them to the mapping file.")

    # Accounts starting with 9
    n_excl_9 = n_excl
    if n_excl_9 > 0:
        flag("warning", "Exclusions",
             f"{n_excl_9} accounts starting with '9' were excluded from balance sheet.")

    # Balance check
    diff = bs.get("difference", None)
    if diff is not None:
        if abs(diff) < 1.0:
            flag("success", "Balance", "Balance sheet is balanced (Assets = Liabilities).")
        elif abs(diff) < 1000:
            flag("warning", "Balance", f"Small imbalance: {diff:,.2f}. May be rounding.")
        else:
            flag("error", "Balance",
                 f"Balance sheet does NOT balance. Difference: {diff:,.2f}")

    # Duplicate account numbers
    dupes = mapp_df[mapp_df.duplicated(subset=["account_number"], keep=False)]
    if not dupes.empty:
        flag("warning", "Data Quality",
             f"{len(dupes)} duplicate account numbers in trial balance.")

    # Zero total assets
    if bs.get("total_assets", 0) == 0:
        flag("error", "Balance", "Total assets = 0. Check mapping or trial balance data.")

    return flags
