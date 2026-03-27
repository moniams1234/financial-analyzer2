"""utils.py – shared UI helpers."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

FEEDBACK_FILE = Path(__file__).parent.parent / "user_feedback.json"
MONTHS = ["Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
          "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]


def fmt(v: float, unit: str = "") -> str:
    if v is None:
        return "N/A"
    try:
        v = float(v)
    except Exception:
        return "N/A"
    suffix = f" {unit}" if unit else ""
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:,.2f}M{suffix}"
    if abs(v) >= 1_000:
        return f"{v/1_000:,.1f}K{suffix}"
    return f"{v:,.2f}{suffix}"


def render_flags(flags: list[dict]):
    if not flags:
        st.success("Brak problemów.")
        return
    for f in flags:
        t = f.get("type", "warning")
        cat = f.get("category", "")
        msg = f.get("message", "")
        txt = f"**[{cat}]** {msg}"
        if t == "error":
            st.error(f"🔴 {txt}")
        elif t == "warning":
            st.warning(f"🟡 {txt}")
        else:
            st.success(f"🟢 {txt}")


def save_feedback(rating: int, comment: str):
    entry = {"timestamp": datetime.now().isoformat(), "rating": rating, "comment": comment}
    if "feedback_log" not in st.session_state:
        st.session_state["feedback_log"] = []
    st.session_state["feedback_log"].append(entry)
    try:
        existing = json.loads(FEEDBACK_FILE.read_text("utf-8")) if FEEDBACK_FILE.exists() else []
        existing.append(entry)
        FEEDBACK_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        pass


def ss(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)


def ready() -> bool:
    return bool(st.session_state.get("analyzed"))
