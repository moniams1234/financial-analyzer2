"""
pnl.py

P&L calculation rules:
  Include synthetic accounts (length == 3) starting with 4 or 7
  Exclude accounts 409 and 490
  Additionally include: 870, 590

Net result = sum of persaldo for qualifying accounts
  persaldo for P&L accounts = saldo_ct - saldo_dt
  (positive = credit = income; negative = debit = expense)
"""
from __future__ import annotations

import pandas as pd

# Accounts explicitly excluded from P&L even if they match the 3-char / 4xx / 7xx rule
_PNL_EXCLUDE: frozenset = frozenset({"409", "490"})

# Accounts explicitly included regardless of other rules
_PNL_EXTRA: frozenset = frozenset({"870", "590"})


def compute_pnl(df: pd.DataFrame) -> dict:
    """
    Parameters
    ----------
    df : cleaned trial balance DataFrame (before mapping filter, all accounts)

    Returns
    -------
    dict with:
      pnl_df    - filtered DataFrame of P&L accounts
      net_result - float
    """
    if df is None or df.empty:
        return {"pnl_df": pd.DataFrame(), "net_result": 0.0}

    acc_col = "account_number"

    def is_pnl(acc: str) -> bool:
        acc = str(acc).strip()
        # Explicitly included extras (regardless of other rules)
        if acc in _PNL_EXTRA:
            return True
        # Explicitly excluded
        if acc in _PNL_EXCLUDE:
            return False
        # Synthetic (3-char) starting with 4 or 7
        if len(acc) == 3 and acc[0] in ("4", "7"):
            return True
        return False

    mask = df[acc_col].apply(is_pnl)
    pnl_df = df[mask].copy()

    if pnl_df.empty:
        return {"pnl_df": pnl_df, "net_result": 0.0}

    # persaldo for P&L: credit minus debit (positive = income)
    pnl_df["persaldo_pnl"] = pnl_df["saldo_ct"] - pnl_df["saldo_dt"]
    pnl_df["pnl_type"] = pnl_df["account_number"].apply(
        lambda a: "income" if str(a).strip()[0] == "7" else "expense"
    )

    net_result = float(pnl_df["persaldo_pnl"].sum())

    return {
        "pnl_df":     pnl_df,
        "net_result": net_result,
    }
