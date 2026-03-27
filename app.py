"""
app.py – Financial Analyzer v2
Run: python -m streamlit run app.py
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from modules.xlsx_parser    import parse_trial_balance, parse_mapping_file
from modules.mapping_engine import run_mapping, compute_kpis
from modules.balance_sheet  import build_balance_sheet
from modules.pnl            import compute_pnl
from modules.anomaly_detection import build_red_flags
from modules.charts         import (balance_bar, assets_pie, liabilities_pie,
                                    mapp_group_bar, pnl_waterfall, mapping_donut)
from modules.export_utils   import build_excel_export, build_json_export
from modules.utils          import fmt, render_flags, save_feedback, ss, ready, MONTHS

# ─── page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Financial Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0F172A; }
[data-testid="stSidebar"] * { color: #E2E8F0 !important; }
[data-testid="stSidebar"] .stButton>button {
    background: #1E3A5F; border: 1px solid #2563EB;
    color: #F1F5F9 !important; width: 100%;
}
[data-testid="stSidebar"] .stButton>button:hover { background: #2563EB; }
div[data-testid="metric-container"] {
    background: #1E293B; border-radius: 8px;
    padding: 12px 16px; border-left: 3px solid #2563EB;
}
.stDataFrame { border: 1px solid #334155 !important; }
h1,h2,h3 { color: #F1F5F9; }
</style>
""", unsafe_allow_html=True)

# ─── session defaults ────────────────────────────────────────────────────────
for _k, _v in {
    "analyzed":       False,
    "df":             None,
    "mapp_df":        None,
    "bs":             {},
    "pnl":            {},
    "kpis":           {},
    "flags":          [],
    "mapping":        {},
    "mapping_name":   "",
    "tb_name":        "",
    "feedback_log":   [],
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
SECTIONS = [
    "📈 XLSX Analysis",
    "💬 CFO Chat",
    "📝 Board Memo LLM",
    "🔍 Anomaly Detection",
    "🗣️ NL Query",
    "🗺️ Mapp",
    "⚖️ Balance Sheet",
    "📉 P&L",
    "📦 Batch Processing",
    "💡 User Feedback",
]

with st.sidebar:
    # ── 1. Navigation ────────────────────────────────────────────────────────
    st.markdown("## 📊 Financial Analyzer")
    st.markdown("---")
    section = st.radio("Nawigacja", SECTIONS, label_visibility="collapsed")
    st.markdown("---")

    # ── 2. Upload danych ─────────────────────────────────────────────────────
    st.markdown("### 📂 Upload Danych")
    tb_file  = st.file_uploader("Trial Balance (XLSX)", type=["xlsx"], key="tb_upload")
    map_file = st.file_uploader("Mapping (XLSX)",       type=["xlsx"], key="map_upload")

    # Info about currently loaded files
    tb_name  = st.session_state["tb_name"]
    map_name = st.session_state["mapping_name"]

    st.caption(f"Source File: **{tb_name or '—'}**")
    st.caption(f"Mapping File: **{map_name or '—'}**")

    if map_file is None and st.session_state["mapping"]:
        st.caption("ℹ️ Używany ostatnio wgrany mapping.")
    elif map_file is None and not st.session_state["mapping"]:
        st.caption("⚠️ Brak mappingu – wgraj plik.")

    # ── 3. Okres raportowy ──────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📅 Okres Raportowy")
    col_m, col_y = st.columns(2)
    with col_m:
        month_name = st.selectbox("Miesiąc", MONTHS,
                                  index=datetime.now().month - 1,
                                  label_visibility="collapsed")
    with col_y:
        year = st.number_input("Rok", min_value=2000, max_value=2100,
                               value=datetime.now().year,
                               step=1, label_visibility="collapsed")
    period_str = f"{month_name} {year}"

    # ── 4. Akcje ─────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### ⚡ Akcje")
    mappuj_clicked = st.button("▶ Mappuj", use_container_width=True, type="primary")

    if st.button("🗑️ Wyczyść dane", use_container_width=True):
        for k in ["analyzed","df","mapp_df","bs","pnl","kpis","flags","tb_name"]:
            st.session_state[k] = False if k == "analyzed" else ({} if k in ["bs","pnl","kpis"] else ([] if k == "flags" else None))
        st.session_state["tb_name"] = ""
        st.rerun()

    # ── 5. Status ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Status")
    kpis = st.session_state["kpis"]
    flags = st.session_state["flags"]
    st.caption(f"Total Accounts:    **{kpis.get('total_accounts', '—')}**")
    st.caption(f"Mapped Accounts:   **{kpis.get('mapped_accounts', '—')}**")
    st.caption(f"Unmapped Accounts: **{kpis.get('unmapped_accounts', '—')}**")
    st.caption(f"Excluded (9xx):    **{kpis.get('excluded_accounts', '—')}**")
    n_err  = sum(1 for f in flags if f.get("type") == "error")
    n_warn = sum(1 for f in flags if f.get("type") == "warning")
    st.caption(f"🔴 Red Flag Errors:   **{n_err}**")
    st.caption(f"🟡 Red Flag Warnings: **{n_warn}**")

    # ── 6. Eksport ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 💾 Eksport")

    if ready():
        _mapp_df = st.session_state["mapp_df"]
        _bs      = st.session_state["bs"]
        _pnl     = st.session_state["pnl"]
        _flags   = st.session_state["flags"]
        _kpis    = st.session_state["kpis"]
        _mapping = st.session_state["mapping"]
        _raw_df  = st.session_state["df"]
        _fname   = st.session_state["tb_name"]

        xlsx_bytes = build_excel_export(
            _raw_df, _mapping, _mapp_df, _bs, _pnl, _flags, _kpis, _fname, period_str
        )
        st.download_button(
            "⬇ Excel",
            data=xlsx_bytes,
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        json_str = build_json_export(
            _mapp_df, _bs, _pnl, _flags, _kpis, _fname, period_str
        )
        st.download_button(
            "⬇ JSON",
            data=json_str.encode("utf-8"),
            file_name=f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )
    else:
        st.caption("Wykonaj Mappuj, aby odblokować eksport.")

# ════════════════════════════════════════════════════════════════════════════
# MAPPING PIPELINE (triggered by button)
# ════════════════════════════════════════════════════════════════════════════
if mappuj_clicked:
    errors: list[str] = []

    # Load / update mapping
    if map_file is not None:
        map_result = parse_mapping_file(map_file)
        if "error" in map_result and map_result["error"]:
            errors.append(f"Błąd mappingu: {map_result['error']}")
        else:
            st.session_state["mapping"]      = map_result["mapping"]
            st.session_state["mapping_name"] = map_file.name
    else:
        if not st.session_state["mapping"]:
            errors.append("Brak pliku mappingu. Wgraj plik Mapping XLSX.")

    # Load trial balance
    if tb_file is None:
        errors.append("Brak pliku trial balance. Wgraj plik XLSX.")
    else:
        tb_result = parse_trial_balance(tb_file)
        if "error" in tb_result and tb_result["error"]:
            errors.append(f"Błąd parsowania: {tb_result['error']}")
        else:
            st.session_state["df"]      = tb_result["df"]
            st.session_state["tb_name"] = tb_file.name

    if errors:
        for e in errors:
            st.error(f"❌ {e}")
        st.stop()

    df      = st.session_state["df"]
    mapping = st.session_state["mapping"]

    with st.spinner("Mapowanie…"):
        mapp_df = run_mapping(df, mapping)
        st.session_state["mapp_df"] = mapp_df

    with st.spinner("Balance Sheet…"):
        bs = build_balance_sheet(mapp_df)
        st.session_state["bs"] = bs

    with st.spinner("P&L…"):
        pnl = compute_pnl(df)
        st.session_state["pnl"] = pnl

    with st.spinner("KPI + Red Flags…"):
        kpis = compute_kpis(mapp_df)
        st.session_state["kpis"] = kpis
        flags = build_red_flags(
            df, mapp_df, bs, kpis, tb_result.get("warnings", [])
        )
        st.session_state["flags"] = flags

    st.session_state["analyzed"] = True
    st.success(f"✅ Mappowanie zakończone. Kont: {kpis['total_accounts']:,} | "
               f"Zmapowanych: {kpis['mapped_accounts']:,} | "
               f"Niezmapowanych: {kpis['unmapped_accounts']:,}")

# ════════════════════════════════════════════════════════════════════════════
# VIEW ROUTING
# ════════════════════════════════════════════════════════════════════════════
key = section.split(" ", 1)[1].strip()

def _no_data():
    st.info("📂 Wgraj pliki i kliknij **▶ Mappuj**, aby zobaczyć wyniki.")


# ──────────────────────────────────────────────────────────────────────────
# 1. XLSX Analysis (dashboard)
# ──────────────────────────────────────────────────────────────────────────
if key == "XLSX Analysis":
    st.markdown(f"## 📈 Dashboard Finansowy — {period_str}")

    if not ready():
        _no_data()
        st.markdown("""
        ### Jak zacząć
        1. Wgraj plik **Trial Balance (XLSX)** w sidebarze.
        2. Wgraj plik **Mapping (XLSX)** (arkusz `Mapp`).
        3. Wybierz **Okres Raportowy**.
        4. Kliknij **▶ Mappuj**.

        ### Format mappingu
        Arkusz `Mapp` w pliku mapping:
        - Kolumna A: `A` / `P` / `X` (typ konta) lub nagłówek grupy
        - Kolumna C: numer konta (exact match)

        ### Reguły P&L
        - Konta syntetyczne (3 znaki) zaczynające się od **4** lub **7**, poza **409**
        - Dodatkowo: **870**, **590**
        """)
    else:
        kpis  = st.session_state["kpis"]
        bs    = st.session_state["bs"]
        pnl   = st.session_state["pnl"]
        flags = st.session_state["flags"]

        ta  = kpis.get("total_assets",    0)
        tl  = kpis.get("total_liabilities", 0)
        nr  = pnl.get("net_result", 0)
        diff = bs.get("difference", 0)

        # KPI row
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Assets",      fmt(ta))
        c2.metric("Total Liabilities", fmt(tl))
        c3.metric("Wynik Netto",       fmt(nr))
        c4.metric("Różnica Bilansowa", fmt(diff),
                  delta="✓ Zbilansowany" if abs(diff) < 1 else f"⚠ {fmt(abs(diff))}")

        c5, c6, c7 = st.columns(3)
        c5.metric("Total Accounts",  kpis.get("total_accounts", 0))
        c6.metric("Mapped",          kpis.get("mapped_accounts", 0))
        c7.metric("Unmapped",        kpis.get("unmapped_accounts", 0))

        st.markdown("---")

        # Charts
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(balance_bar(ta, tl), use_container_width=True, key="balance_bar_dashboard")
        with col2:
            st.plotly_chart(mapping_donut(
                kpis.get("mapped_accounts", 0),
                kpis.get("unmapped_accounts", 0),
                kpis.get("excluded_accounts", 0),
            ), use_container_width=True, key="mapping_donut_dashboard")

        col3, col4 = st.columns(2)
        with col3:
            st.plotly_chart(assets_pie(bs.get("assets_by_group", pd.DataFrame(columns=["group","amount"]))),
                            use_container_width=True, key="assets_pie_dashboard")
        with col4:
            st.plotly_chart(liabilities_pie(bs.get("liabilities_by_group", pd.DataFrame(columns=["group","amount"]))),
                            use_container_width=True, key="liabilities_pie_dashboard")

        mapp_df = st.session_state["mapp_df"]
        st.plotly_chart(mapp_group_bar(mapp_df), use_container_width=True, key="mapp_group_bar_dashboard")

        # Red flags
        st.markdown("### 🚩 Red Flags")
        render_flags(flags)

        # Raw data
        with st.expander("📋 Surowe dane (pierwsze 200 wierszy)"):
            df = st.session_state["df"]
            if df is not None:
                st.dataframe(df.head(200), use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────
# 2. CFO Chat
# ──────────────────────────────────────────────────────────────────────────
elif key == "CFO Chat":
    st.markdown("## 💬 CFO Chat")

    if not ready():
        _no_data()
    else:
        kpis  = st.session_state["kpis"]
        bs    = st.session_state["bs"]
        pnl   = st.session_state["pnl"]
        flags = st.session_state["flags"]
        fname = st.session_state["tb_name"]

        ta  = kpis.get("total_assets", 0)
        tl  = kpis.get("total_liabilities", 0)
        nr  = pnl.get("net_result", 0)
        diff = bs.get("difference", 0)
        n_err = sum(1 for f in flags if f["type"] == "error")

        summary = f"""## Analiza CFO — {fname} ({period_str})

**Total Assets:** {fmt(ta)}
**Total Liabilities:** {fmt(tl)}
**Wynik Netto:** {fmt(nr)}
**Bilans:** {"✅ Zbilansowany" if abs(diff) < 1 else f"⚠️ Różnica {fmt(diff)}"}
**Problemy:** {n_err} error(s)
"""
        st.markdown(summary)
        st.markdown("---")

        if "cfo_history" not in st.session_state:
            st.session_state["cfo_history"] = []

        for msg in st.session_state["cfo_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Zadaj pytanie…"):
            st.session_state["cfo_history"].append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            q = prompt.lower()
            mapp_df = st.session_state["mapp_df"]

            if any(k in q for k in ["asset", "aktywa"]):
                ans = f"**Total Assets:** {fmt(ta)}"
            elif any(k in q for k in ["liabilit", "pasywa", "zobowiązan"]):
                ans = f"**Total Liabilities:** {fmt(tl)}"
            elif any(k in q for k in ["wynik", "profit", "p&l", "netto"]):
                ans = f"**Wynik Netto:** {fmt(nr)}"
            elif any(k in q for k in ["bilans", "balance", "różnic"]):
                ans = f"**Różnica bilansowa:** {fmt(diff)}"
            elif any(k in q for k in ["unmapp", "niezmapp"]):
                ans = f"**Niezmapowane konta:** {kpis.get('unmapped_accounts', 0)}"
            elif any(k in q for k in ["top", "najwięks", "largest"]) and mapp_df is not None:
                top5 = (mapp_df[mapp_df["mapping_status"] == "mapped"]
                        .nlargest(5, "persaldo")[["account_number","account_name","persaldo"]])
                rows = "\n".join(f"- **{r.account_number}** {r.account_name}: {fmt(r.persaldo)}"
                                 for r in top5.itertuples())
                ans = f"**Top 5 kont wg persaldo:**\n{rows}"
            else:
                ans = (f"Dostępne dane: Total Assets={fmt(ta)}, Total Liabilities={fmt(tl)}, "
                       f"Wynik Netto={fmt(nr)}. Pytaj o aktywa, pasywa, wynik lub bilans.")

            st.session_state["cfo_history"].append({"role": "assistant", "content": ans})
            with st.chat_message("assistant"):
                st.markdown(ans)


# ──────────────────────────────────────────────────────────────────────────
# 3. Board Memo LLM
# ──────────────────────────────────────────────────────────────────────────
elif key == "Board Memo LLM":
    st.markdown("## 📝 Board Memo")

    if not ready():
        _no_data()
    else:
        kpis  = st.session_state["kpis"]
        bs    = st.session_state["bs"]
        pnl   = st.session_state["pnl"]
        flags = st.session_state["flags"]
        fname = st.session_state["tb_name"]

        ta   = kpis.get("total_assets", 0)
        tl   = kpis.get("total_liabilities", 0)
        nr   = pnl.get("net_result", 0)
        diff = bs.get("difference", 0)

        memo = f"""# Memo dla Zarządu

**Temat:** Przegląd Bilansu – {fname}
**Okres:** {period_str}
**Opracował:** Financial Analyzer System

---

## Podsumowanie Wykonawcze

| Pozycja | Wartość |
|---|---|
| Aktywa Razem | {fmt(ta)} |
| Pasywa Razem | {fmt(tl)} |
| Wynik Netto | {fmt(nr)} |
| Różnica Bilansowa | {fmt(diff)} |

## Obserwacje

1. **Integralność bilansu:** {"Bilans jest zbilansowany." if abs(diff) < 1 else f"Wykryto różnicę {fmt(diff)} – wymaga wyjaśnienia."}
2. **Wynik finansowy:** Wynik netto za okres wynosi **{fmt(nr)}**.
3. **Jakość danych:** {sum(1 for f in flags if f["type"] == "error")} błąd(y) w danych.

## Rekomendacje

- Zweryfikować konta niezmapowane ({kpis.get('unmapped_accounts', 0)} szt.)
- Potwierdzić saldo kont eliminacyjnych
- Uzgodnić ewentualną różnicę bilansową przed zamknięciem okresu

---
*Memo wygenerowane automatycznie przez Financial Analyzer. Wymaga weryfikacji.*
"""
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(memo)
        with col2:
            st.download_button(
                "⬇ Pobierz (.md)",
                data=memo.encode("utf-8"),
                file_name=f"memo_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )


# ──────────────────────────────────────────────────────────────────────────
# 4. Anomaly Detection
# ──────────────────────────────────────────────────────────────────────────
elif key == "Anomaly Detection":
    st.markdown("## 🔍 Anomaly Detection")

    if not ready():
        _no_data()
    else:
        flags   = st.session_state["flags"]
        mapp_df = st.session_state["mapp_df"]
        kpis    = st.session_state["kpis"]

        n_err  = sum(1 for f in flags if f["type"] == "error")
        n_warn = sum(1 for f in flags if f["type"] == "warning")
        n_ok   = sum(1 for f in flags if f["type"] == "success")

        c1, c2, c3 = st.columns(3)
        c1.metric("🔴 Errors",   n_err)
        c2.metric("🟡 Warnings", n_warn)
        c3.metric("🟢 OK",       n_ok)
        st.markdown("---")

        render_flags(flags)

        st.markdown("---")
        st.markdown("### Mapping Status Detail")
        if mapp_df is not None and not mapp_df.empty:
            status_summary = (
                mapp_df.groupby("mapping_status")
                .agg(count=("account_number","count"),
                     total_persaldo=("persaldo","sum"))
                .reset_index()
            )
            st.dataframe(status_summary, use_container_width=True)

            st.markdown("### Niezmapowane konta")
            unmapped = mapp_df[mapp_df["mapping_status"] == "unmapped"]
            if not unmapped.empty:
                st.dataframe(
                    unmapped[["account_number","account_name","saldo_dt","saldo_ct","persaldo"]],
                    use_container_width=True,
                )
            else:
                st.success("Wszystkie aktywne konta są zmapowane.")

            st.markdown("### Wykluczone konta (9xx)")
            excl = mapp_df[mapp_df["mapping_status"] == "excluded"]
            if not excl.empty:
                st.dataframe(
                    excl[["account_number","account_name","persaldo"]].head(100),
                    use_container_width=True,
                )


# ──────────────────────────────────────────────────────────────────────────
# 5. NL Query
# ──────────────────────────────────────────────────────────────────────────
elif key == "NL Query":
    st.markdown("## 🗣️ Natural Language Query")

    if not ready():
        _no_data()
    else:
        st.markdown("""
        Zadaj pytanie o dane finansowe. Przykłady:
        - *Jakie są aktywa razem?*
        - *Ile kont nie jest zmapowanych?*
        - *Jaki jest wynik netto?*
        - *Czy bilans jest zbilansowany?*
        """)

        query = st.text_input("Twoje pytanie:", placeholder="np. Jakie są aktywa razem?")

        if st.button("Zapytaj", type="primary") and query:
            kpis    = st.session_state["kpis"]
            bs      = st.session_state["bs"]
            pnl     = st.session_state["pnl"]
            mapp_df = st.session_state["mapp_df"]

            ta  = kpis.get("total_assets", 0)
            tl  = kpis.get("total_liabilities", 0)
            nr  = pnl.get("net_result", 0)
            diff = bs.get("difference", 0)
            q   = query.lower()

            if any(k in q for k in ["asset", "aktywa"]):
                ans = f"**Total Assets:** {fmt(ta)}"
            elif any(k in q for k in ["liabilit", "pasywa", "zobowiązan"]):
                ans = f"**Total Liabilities:** {fmt(tl)}"
            elif any(k in q for k in ["wynik", "netto", "profit", "p&l"]):
                ans = f"**Wynik Netto:** {fmt(nr)}"
            elif any(k in q for k in ["bilans", "balance", "różnic", "zbilans"]):
                status = "zbilansowany ✓" if abs(diff) < 1 else f"niezbalansowany (różnica {fmt(diff)})"
                ans = f"**Status bilansu:** {status}"
            elif any(k in q for k in ["unmapp", "niezmapp"]):
                n = kpis.get("unmapped_accounts", 0)
                ans = f"**Niezmapowane konta:** {n}"
            elif any(k in q for k in ["wykluczon", "excluded", "9xx"]):
                n = kpis.get("excluded_accounts", 0)
                ans = f"**Wykluczone konta (9xx):** {n}"
            elif any(k in q for k in ["top", "najwięks", "largest"]) and mapp_df is not None:
                top5 = (mapp_df[mapp_df["mapping_status"] == "mapped"]
                        .nlargest(5, "persaldo")[["account_number","account_name","persaldo"]])
                rows = "\n".join(f"- **{r.account_number}** {r.account_name}: {fmt(r.persaldo)}"
                                 for r in top5.itertuples())
                ans = f"**Top 5 kont wg persaldo:**\n{rows}"
            else:
                ans = (f"Nie rozpoznano pytania. Dostępne dane: "
                       f"aktywa={fmt(ta)}, pasywa={fmt(tl)}, wynik={fmt(nr)}.")

            st.markdown(f"**Odpowiedź:** {ans}")

        st.markdown("---")
        st.markdown("### Szybki podgląd")
        kpis = st.session_state["kpis"]
        bs   = st.session_state["bs"]
        pnl  = st.session_state["pnl"]
        data = {
            "Pozycja": ["Total Assets", "Total Liabilities", "Wynik Netto",
                        "Różnica Bilansowa", "Kont ogółem", "Zmapowanych", "Niezmapowanych"],
            "Wartość": [
                fmt(kpis.get("total_assets", 0)),
                fmt(kpis.get("total_liabilities", 0)),
                fmt(pnl.get("net_result", 0)),
                fmt(bs.get("difference", 0)),
                str(kpis.get("total_accounts", 0)),
                str(kpis.get("mapped_accounts", 0)),
                str(kpis.get("unmapped_accounts", 0)),
            ],
        }
        st.table(pd.DataFrame(data))


# ──────────────────────────────────────────────────────────────────────────
# 6. Mapp
# ──────────────────────────────────────────────────────────────────────────
elif key == "Mapp":
    st.markdown("## 🗺️ Tabela Mappingu")

    if not ready():
        _no_data()
    else:
        mapp_df = st.session_state["mapp_df"]

        if mapp_df is None or mapp_df.empty:
            st.warning("Brak danych mappingu.")
        else:
            # Filters
            col1, col2, col3 = st.columns(3)
            with col1:
                side_opts = sorted(mapp_df["side"].unique().tolist())
                side_filter = st.multiselect("Typ (side)", side_opts, default=side_opts)
            with col2:
                status_opts = sorted(mapp_df["mapping_status"].unique().tolist())
                status_filter = st.multiselect("Status", status_opts, default=status_opts)
            with col3:
                search = st.text_input("Szukaj konta / nazwy", "")

            filtered = mapp_df[
                mapp_df["side"].isin(side_filter) &
                mapp_df["mapping_status"].isin(status_filter)
            ]
            if search:
                mask = (
                    filtered["account_number"].str.contains(search, case=False, na=False) |
                    filtered["account_name"].str.contains(search, case=False, na=False)
                )
                filtered = filtered[mask]

            cols = ["account_number","account_name","group","side",
                    "debit","credit","saldo_dt","saldo_ct",
                    "persaldo","persaldo_group","mapping_status"]
            cols = [c for c in cols if c in filtered.columns]

            st.markdown(f"**{len(filtered):,}** z **{len(mapp_df):,}** kont")
            st.dataframe(
                filtered[cols].style.format({
                    c: "{:,.2f}" for c in ["debit","credit","saldo_dt","saldo_ct","persaldo","persaldo_group"]
                    if c in filtered.columns
                }),
                use_container_width=True, height=480,
            )

            st.markdown("### Sumy wg grupy")
            grp_sum = (
                filtered[filtered["mapping_status"] == "mapped"]
                .groupby(["side","group"])
                .agg(kont=("account_number","count"), persaldo=("persaldo","sum"))
                .reset_index()
                .sort_values(["side","persaldo"], ascending=[True, False])
            )
            st.dataframe(
                grp_sum.style.format({"persaldo": "{:,.2f}"}),
                use_container_width=True,
            )

            with st.expander("📖 Zasady persaldo"):
                st.markdown("""
                | Typ | Formuła | Znaczenie dodatniego |
                |---|---|---|
                | **A** (Aktywa) | `Saldo Dt − Saldo Ct` | Saldo debetowe (normalne dla aktywów) |
                | **P** (Pasywa) | `Saldo Ct − Saldo Dt` | Saldo kredytowe (normalne dla pasywów) |
                | **X** | `Saldo Dt − Saldo Ct` | Tylko informacyjnie |
                """)


# ──────────────────────────────────────────────────────────────────────────
# 7. Balance Sheet
# ──────────────────────────────────────────────────────────────────────────
elif key == "Balance Sheet":
    st.markdown(f"## ⚖️ Balance Sheet — {period_str}")

    if not ready():
        _no_data()
    else:
        bs   = st.session_state["bs"]
        kpis = st.session_state["kpis"]

        ta   = bs.get("total_assets", 0)
        tl   = bs.get("total_liabilities", 0)
        diff = bs.get("difference", 0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Assets",      fmt(ta))
        c2.metric("Total Liabilities", fmt(tl))
        c3.metric("Różnica", fmt(diff),
                  delta="✓ Zbilansowany" if abs(diff) < 1 else "⚠ Niezbalansowany")

        st.markdown("---")
        col_a, col_p = st.columns(2)

        with col_a:
            st.markdown("### AKTYWA (A)")
            ag = bs.get("assets_by_group")
            if ag is not None and not ag.empty:
                st.dataframe(ag.style.format({"amount": "{:,.2f}"}), use_container_width=True)
            st.markdown(f"**Razem Aktywa: {fmt(ta)}**")

        with col_p:
            st.markdown("### PASYWA (P)")
            lg = bs.get("liabilities_by_group")
            if lg is not None and not lg.empty:
                st.dataframe(lg.style.format({"amount": "{:,.2f}"}), use_container_width=True)
            st.markdown(f"**Razem Pasywa: {fmt(tl)}**")

        st.markdown("---")
        if abs(diff) < 1:
            st.success(f"Bilans zbilansowany. Różnica: {fmt(diff)}")
        else:
            st.error(f"Bilans NIE jest zbilansowany. Różnica: {fmt(diff)}")

        col1, col2 = st.columns(2)
        with col1:
            ag = bs.get("assets_by_group", pd.DataFrame(columns=["group","amount"]))
            st.plotly_chart(assets_pie(ag), use_container_width=True, key="assets_pie_bs")
        with col2:
            lg = bs.get("liabilities_by_group", pd.DataFrame(columns=["group","amount"]))
            st.plotly_chart(liabilities_pie(lg), use_container_width=True, key="liabilities_pie_bs")

        st.plotly_chart(balance_bar(ta, tl), use_container_width=True, key="balance_bar_bs")


# ──────────────────────────────────────────────────────────────────────────
# 8. P&L
# ──────────────────────────────────────────────────────────────────────────
elif key == "P&L":
    st.markdown(f"## 📉 P&L — {period_str}")

    if not ready():
        _no_data()
    else:
        pnl = st.session_state["pnl"]
        pnl_df = pnl.get("pnl_df", pd.DataFrame())
        nr     = pnl.get("net_result", 0)

        st.metric("Wynik Netto", fmt(nr),
                  delta="zysk" if nr > 0 else "strata")

        st.markdown("---")
        st.markdown("""
        **Reguły kwalifikacji kont P&L:**
        - Konta syntetyczne (3 znaki) zaczynające się od **4** lub **7**, z wyjątkiem **409**
        - Dodatkowo konta: **870**, **590**
        - Persaldo = Saldo Ct − Saldo Dt (dodatnie = przychód)
        """)

        if pnl_df.empty:
            st.warning("Brak kont P&L po zastosowaniu reguł.")
        else:
            income  = pnl_df[pnl_df["persaldo_pnl"] > 0]["persaldo_pnl"].sum()
            expense = pnl_df[pnl_df["persaldo_pnl"] < 0]["persaldo_pnl"].sum()

            c1, c2, c3 = st.columns(3)
            c1.metric("Przychody (+)",  fmt(income))
            c2.metric("Koszty (−)",     fmt(expense))
            c3.metric("Wynik Netto",    fmt(nr))

            st.plotly_chart(pnl_waterfall(pnl_df, nr), use_container_width=True, key="pnl_waterfall")

            st.markdown("### Konta P&L")
            cols = ["account_number","account_name","saldo_dt","saldo_ct","persaldo_pnl","pnl_type"]
            cols = [c for c in cols if c in pnl_df.columns]
            st.dataframe(
                pnl_df[cols].style.format({
                    c: "{:,.2f}" for c in ["saldo_dt","saldo_ct","persaldo_pnl"]
                    if c in pnl_df.columns
                }),
                use_container_width=True, height=420,
            )


# ──────────────────────────────────────────────────────────────────────────
# 9. Batch Processing
# ──────────────────────────────────────────────────────────────────────────
elif key == "Batch Processing":
    st.markdown("## 📦 Batch Processing")
    st.markdown("Wgraj wiele plików Trial Balance i przetwórz je wsadowo.")

    batch_files = st.file_uploader(
        "Pliki Trial Balance (wiele)",
        type=["xlsx"],
        accept_multiple_files=True,
        key="batch_upload",
    )

    if st.button("▶ Przetwórz wsadowo", type="primary") and batch_files:
        if not st.session_state["mapping"]:
            st.error("Brak mappingu. Wgraj plik Mapping w panelu głównym.")
            st.stop()

        mapping = st.session_state["mapping"]
        results = []
        prog    = st.progress(0)
        status  = st.empty()

        for i, f in enumerate(batch_files):
            status.info(f"Przetwarzam {f.name}… ({i+1}/{len(batch_files)})")
            try:
                pr = parse_trial_balance(f)
                if "error" in pr and pr["error"]:
                    raise ValueError(pr["error"])
                df_b    = pr["df"]
                mapp_b  = run_mapping(df_b, mapping)
                bs_b    = build_balance_sheet(mapp_b)
                pnl_b   = compute_pnl(df_b)
                kpis_b  = compute_kpis(mapp_b)
                results.append({
                    "filename":      f.name,
                    "status":        "ok",
                    "accounts":      kpis_b["total_accounts"],
                    "mapped":        kpis_b["mapped_accounts"],
                    "unmapped":      kpis_b["unmapped_accounts"],
                    "total_assets":  round(bs_b["total_assets"], 2),
                    "total_liab":    round(bs_b["total_liabilities"], 2),
                    "difference":    round(bs_b["difference"], 2),
                    "net_result":    round(pnl_b["net_result"], 2),
                    "error":         "",
                })
            except Exception as e:
                results.append({
                    "filename": f.name, "status": "error",
                    "accounts": 0, "mapped": 0, "unmapped": 0,
                    "total_assets": None, "total_liab": None,
                    "difference": None, "net_result": None, "error": str(e),
                })
            prog.progress((i + 1) / len(batch_files))

        status.success(f"✅ Gotowe: {len(batch_files)} pliki przetworzone.")
        res_df = pd.DataFrame(results)
        st.dataframe(res_df, use_container_width=True)
        st.session_state["batch_results"] = results

        csv = res_df.to_csv(index=False)
        st.download_button("⬇ Pobierz CSV", data=csv.encode("utf-8"),
                           file_name=f"batch_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv")
    elif "batch_results" in st.session_state:
        st.markdown("### Poprzednie wyniki")
        st.dataframe(pd.DataFrame(st.session_state["batch_results"]), use_container_width=True)
    else:
        st.info("Wgraj pliki i kliknij ▶ Przetwórz wsadowo.")


# ──────────────────────────────────────────────────────────────────────────
# 10. User Feedback
# ──────────────────────────────────────────────────────────────────────────
elif key == "User Feedback":
    st.markdown("## 💡 Feedback")

    with st.form("feedback"):
        rating = st.slider("Ocena", 1, 5, 4)
        st.markdown("⭐" * rating)
        cat = st.selectbox("Kategoria", ["Ogólny","Parsowanie","Mapowanie","UI/UX","Eksport","Inne"])
        comment = st.text_area("Komentarz")
        if st.form_submit_button("Wyślij", type="primary"):
            save_feedback(rating, f"[{cat}] {comment}")
            st.success("✅ Dziękujemy za feedback!")

    log = st.session_state.get("feedback_log", [])
    if log:
        st.markdown("---")
        st.markdown("### Historia (bieżąca sesja)")
        for e in reversed(log[-10:]):
            ts = e.get("timestamp","")[:19]
            r  = e.get("rating", 0)
            c  = e.get("comment","")
            st.markdown(f"**{ts}** {'⭐'*r} — {c}")
