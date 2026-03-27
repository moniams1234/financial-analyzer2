# Financial Analyzer v2

Aplikacja Streamlit do analizy trial balance (ZOiS) z mapowaniem do struktury raportowej.

## Uruchomienie

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Struktura projektu

```
financial_analyzer/
├── app.py                     ← główna aplikacja Streamlit
├── requirements.txt
├── README.md
└── modules/
    ├── xlsx_parser.py         ← parser ZOiS i pliku mappingu
    ├── mapping_engine.py      ← silnik mapowania (exact match)
    ├── balance_sheet.py       ← budowanie bilansu
    ├── pnl.py                 ← rachunek wyników
    ├── anomaly_detection.py   ← red flags
    ├── export_utils.py        ← eksport Excel i JSON
    ├── charts.py              ← wykresy Plotly
    └── utils.py               ← helpery
```

## Format pliku mappingu

Plik XLSX z arkuszem `Mapp`:
- Kolumna A: `A` (aktywa) / `P` (pasywa) / `X` (wykluczone z bilansu) lub nazwa grupy
- Kolumna C: numer konta (exact match)
- Kolejne wiersze z tą samą grupą są przypisywane do ostatnio widzianej grupy

## Kluczowe zasady biznesowe

| Reguła | Opis |
|---|---|
| Mapowanie | Wyłącznie po pełnym numerze konta (exact match) |
| Konta 9xx | Wykluczane automatycznie (status: excluded) |
| Heuristic Mapped | Zawsze = 0 |
| Grupa X | Nie wchodzi do bilansu |
| P&L – konta | Syntetyczne (3 znaki) zaczynające się od 4 lub 7, bez 409; plus 870, 590 |

## Persaldo

| Typ | Formuła | Znaczenie |
|---|---|---|
| A | Saldo Dt − Saldo Ct | Dodatnie = saldo debetowe |
| P | Saldo Ct − Saldo Dt | Dodatnie = saldo kredytowe |
| P&L | Saldo Ct − Saldo Dt | Dodatnie = przychód |

## Eksport Excel

Arkusze: Raw_Trial_Balance, Mapping, Mapp, Balance_Sheet, P&L, Red_Flags, Summary

## Summary zawiera

Generated At, Source File, Total Accounts, Mapped Accounts, Heuristic Mapped (=0),
Total Assets, Total Liabilities, Total Equity, Balance Difference,
Red Flag Errors, Red Flag Warnings, Okres Raportowy, Wynik Netto
