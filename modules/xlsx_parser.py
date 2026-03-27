"""
xlsx_parser.py
Parses two types of XLSX files:
  1. Trial balance (ZOiS) – returns cleaned DataFrame
  2. Mapping file – returns dict {account_number -> {side, group}}

MAPPING FORMAT (Mapp sheet):
  Col 0: 'A' | 'P' | 'X' | group-header-name
  Col 2: account number (when col 0 is A/P/X)
  The group assigned to an account is the most-recently-seen group header row.

TRIAL BALANCE FORMAT:
  Standard ZOiS: Numer, Nazwa 2, Nazwa, BO Dt, BO Ct, Obroty Dt, Obroty Ct,
                 Obroty n. Dt, Obroty n. Ct, Saldo Dt, Saldo Ct, Persaldo
  Column names are detected heuristically (PL and EN variants).
"""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
import pandas as pd


# ─── column name aliases ────────────────────────────────────────────────────

_COL_MAP: dict[str, list[str]] = {
    "account_number": ["numer", "konto", "account", "account_number", "account number",
                       "nr konta", "numer konta", "account no"],
    "account_name2": ["nazwa 2", "name2", "label", "nazwa2"],
    "account_name":  ["nazwa", "name", "account_name", "account name", "opis", "description"],
    "bo_dt":         ["bo dt", "bo dt ", "opening debit"],
    "bo_ct":         ["bo ct", "bo ct ", "opening credit"],
    "obroty_dt":     ["obroty dt", "obroty dt ", "debit", "wn", "dt", "turnover debit"],
    "obroty_ct":     ["obroty ct", "obroty ct ", "credit", "ma", "ct", "turnover credit"],
    "obroty_n_dt":   ["obroty n. dt", "obroty n. dt "],
    "obroty_n_ct":   ["obroty n. ct", "obroty n. ct "],
    "saldo_dt":      ["saldo dt", "saldo dt ", "closing debit", "balance debit"],
    "saldo_ct":      ["saldo ct", "saldo ct ", "closing credit", "balance credit"],
    "persaldo":      ["persaldo", "saldo", "balance", "net balance", "net saldo"],
}


def _norm(s: object) -> str:
    return str(s).strip().lower() if not pd.isna(s) else ""


def _canonical(raw: str) -> str:
    r = raw.strip().lower()
    for canon, aliases in _COL_MAP.items():
        if r in aliases:
            return canon
    return r.replace(" ", "_")


def _find_header_row(df_raw: pd.DataFrame) -> int:
    best, best_score = 0, 0
    for i in range(min(15, len(df_raw))):
        score = sum(
            1 for cell in df_raw.iloc[i]
            if any(_norm(cell) in aliases for aliases in _COL_MAP.values())
        )
        if score > best_score:
            best_score, best = score, i
    return best


def _to_float(val: object) -> float:
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else 0.0


def _select_tb_sheet(xls: pd.ExcelFile) -> str:
    """Pick the most likely trial-balance sheet."""
    good = ["zois", "trial", "balance", "zestawienie", "obroty", "tb"]
    bad  = ["mapp", "hyperion", "check", "pivot", "summary", "bs "]
    scores: dict[str, int] = {}
    for name in xls.sheet_names:
        nl = name.lower()
        s = sum(2 for k in good if k in nl) - sum(3 for k in bad if k in nl)
        try:
            df = xls.parse(name, header=None, nrows=3)
            s += min(df.shape[1], 8)
        except Exception:
            pass
        scores[name] = s
    return max(scores, key=lambda n: scores[n])


# ─── public API ─────────────────────────────────────────────────────────────

def parse_trial_balance(file_obj) -> dict:
    """
    Returns:
      {df, sheet_used, warnings, error}
    df columns (canonical):
      account_number, account_name, account_name2,
      bo_dt, bo_ct, obroty_dt, obroty_ct,
      obroty_n_dt, obroty_n_ct, saldo_dt, saldo_ct, persaldo
    """
    warnings: list[str] = []
    try:
        xls = pd.ExcelFile(file_obj, engine="openpyxl")
    except Exception as e:
        return {"error": str(e)}

    sheet = _select_tb_sheet(xls)
    try:
        raw = xls.parse(sheet, header=None, dtype=str)
    except Exception as e:
        return {"error": f"Cannot read sheet '{sheet}': {e}"}

    hrow = _find_header_row(raw)
    df = xls.parse(sheet, header=hrow, dtype=str)
    df.columns = [_canonical(str(c)) for c in df.columns]
    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    # numeric columns
    num_cols = ["bo_dt","bo_ct","obroty_dt","obroty_ct",
                "obroty_n_dt","obroty_n_ct","saldo_dt","saldo_ct","persaldo"]
    for c in num_cols:
        if c not in df.columns:
            df[c] = 0.0
        else:
            df[c] = df[c].apply(_to_float)

    # account_number
    if "account_number" not in df.columns:
        df.rename(columns={df.columns[0]: "account_number"}, inplace=True)

    # account_name fallback
    if "account_name" not in df.columns:
        if "account_name2" in df.columns:
            df["account_name"] = df["account_name2"]
        else:
            df["account_name"] = df["account_number"].astype(str)

    if "account_name2" not in df.columns:
        df["account_name2"] = ""

    df["account_number"] = df["account_number"].astype(str).str.strip()
    df["account_name"]   = df["account_name"].astype(str).str.strip()

    # drop empty account rows
    df = df[df["account_number"].notna() & (df["account_number"] != "") & (df["account_number"] != "nan")]
    df.reset_index(drop=True, inplace=True)

    if df.empty:
        warnings.append("Parsed DataFrame is empty after cleaning.")

    return {"df": df, "sheet_used": sheet, "warnings": warnings}


def parse_mapping_file(file_obj) -> dict:
    """
    Parse the mapping XLSX.
    Looks for a sheet named 'Mapp' (case-insensitive), falls back to first sheet.

    Returns:
      {
        mapping: dict[account_number -> {side: str, group: str}],
        error: str | None
      }
    """
    try:
        xls = pd.ExcelFile(file_obj, engine="openpyxl")
    except Exception as e:
        return {"error": str(e), "mapping": {}}

    # find Mapp sheet
    sheet = None
    for name in xls.sheet_names:
        if name.strip().lower() == "mapp":
            sheet = name
            break
    if sheet is None:
        sheet = xls.sheet_names[0]

    try:
        df = xls.parse(sheet, header=None, dtype=str)
    except Exception as e:
        return {"error": f"Cannot read mapping sheet '{sheet}': {e}", "mapping": {}}

    mapping: dict[str, dict] = {}
    current_group: str = ""

    for _, row in df.iterrows():
        col0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        col2 = str(row.iloc[2]).strip() if len(row) > 2 and pd.notna(row.iloc[2]) else ""

        if col0 in ("A", "P", "X"):
            acc = col2
            if acc and acc != "nan":
                mapping[acc] = {"side": col0, "group": current_group}
        elif col0 and col0 != "nan":
            # group header
            current_group = col0

    return {"mapping": mapping, "sheet_used": sheet}
