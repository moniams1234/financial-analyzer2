"""
mapping_engine.py

Business rules:
  - Mapping is EXACT match on account_number only (no prefix, no heuristics)
  - Exclude ALL accounts starting with "9" EXCEPT those in _9XX_WHITELIST
  - Group "X" accounts are excluded from balance sheet (not A or P)
  - heuristic_mapped is always 0 in this engine

9xx whitelist (these are PPE accounts mapped in the Mapp sheet):
  902-03, 907, 907-01, 907-02, 907-03,
  910, 910-01, 910-02, 910-03,
  912, 912-01,
  972, 972-01,
  973, 973-03

Persaldo sign convention:
  A (assets):   persaldo = saldo_dt - saldo_ct   (positive = debit balance)
  P (liab/eq):  persaldo = saldo_ct - saldo_dt   (positive = credit balance)
  X:            persaldo = saldo_dt - saldo_ct   (neutral, kept for reference)
"""
from __future__ import annotations

import pandas as pd
import numpy as np

# 9xx accounts that are legitimate BS accounts and must NOT be excluded
_9XX_WHITELIST: frozenset = frozenset({
    "902-03",
    "907", "907-01", "907-02", "907-03",
    "910", "910-01", "910-02", "910-03",
    "912", "912-01",
    "972", "972-01",
    "973", "973-03",
})


def _is_excluded(acc: str) -> bool:
    """Return True if account should be excluded (9xx but NOT whitelisted)."""
    if not acc.startswith("9"):
        return False
    return acc not in _9XX_WHITELIST


def run_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Apply exact-match mapping to trial balance DataFrame.

    Parameters
    ----------
    df      : cleaned trial balance DataFrame
    mapping : dict {account_number -> {side, group}}

    Returns
    -------
    DataFrame with columns:
      account_number, account_name, group, side, debit, credit,
      saldo_dt, saldo_ct, persaldo, persaldo_group, mapping_status
    """
    records = []

    for _, row in df.iterrows():
        acc = str(row.get("account_number", "")).strip()

        # Exclude 9xx accounts (except whitelisted ones)
        if _is_excluded(acc):
            records.append(_make_record(row, acc, side="excluded", group="", status="excluded"))
            continue

        match = mapping.get(acc)

        if match:
            side   = match["side"]
            group  = match["group"]
            status = "mapped"
        else:
            side   = "unmapped"
            group  = ""
            status = "unmapped"

        records.append(_make_record(row, acc, side=side, group=group, status=status))

    result = pd.DataFrame(records)

    # persaldo_group: sum of persaldo within group (only for mapped rows)
    mapped_mask = result["mapping_status"] == "mapped"
    if mapped_mask.any():
        group_sums = (
            result[mapped_mask]
            .groupby("group")["persaldo"]
            .sum()
            .rename("persaldo_group")
        )
        result = result.merge(group_sums, on="group", how="left")
    else:
        result["persaldo_group"] = 0.0

    result["persaldo_group"] = result["persaldo_group"].fillna(0.0)

    return result


def _make_record(row: pd.Series, acc: str, side: str, group: str, status: str) -> dict:
    debit    = float(row.get("obroty_dt", 0) or 0)
    credit   = float(row.get("obroty_ct", 0) or 0)
    saldo_dt = float(row.get("saldo_dt",  0) or 0)
    saldo_ct = float(row.get("saldo_ct",  0) or 0)
    name     = str(row.get("account_name", "")).strip()

    # Persaldo sign by side
    if side == "P":
        persaldo = saldo_ct - saldo_dt
    else:
        persaldo = saldo_dt - saldo_ct

    return {
        "account_number": acc,
        "account_name":   name,
        "group":          group,
        "side":           side,
        "debit":          debit,
        "credit":         credit,
        "saldo_dt":       saldo_dt,
        "saldo_ct":       saldo_ct,
        "persaldo":       persaldo,
        "mapping_status": status,
    }


def compute_kpis(mapp_df: pd.DataFrame) -> dict:
    """Compute high-level KPIs from the Mapp table."""
    if mapp_df is None or mapp_df.empty:
        return {}

    total    = len(mapp_df)
    mapped   = int((mapp_df["mapping_status"] == "mapped").sum())
    unmapped = int((mapp_df["mapping_status"] == "unmapped").sum())
    excluded = int((mapp_df["mapping_status"] == "excluded").sum())

    assets_df = mapp_df[(mapp_df["side"] == "A") & (mapp_df["mapping_status"] == "mapped")]
    liab_df   = mapp_df[(mapp_df["side"] == "P") & (mapp_df["mapping_status"] == "mapped")]

    total_assets = float(assets_df["persaldo"].sum())
    total_liab   = float(liab_df["persaldo"].sum())
    difference   = total_assets - total_liab

    return {
        "total_accounts":    total,
        "mapped_accounts":   mapped,
        "heuristic_mapped":  0,          # always 0 per business rule
        "unmapped_accounts": unmapped,
        "excluded_accounts": excluded,
        "total_assets":      total_assets,
        "total_liabilities": total_liab,
        "difference":        difference,
    }
