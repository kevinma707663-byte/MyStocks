# MyStocks frontend (Emma's part)

Run locally:   pip install -r requirements.txt   then   streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud -> main file `streamlit_app.py`

## What is mine (new files only)
streamlit_app.py, app/**, .streamlit/config.toml, sample/OpenPosition_10_24_2026.csv, FRONTEND_README.md, requirements.frontend.txt
## Shared files I changed
None. Kevin's `requirements.txt` (streamlit>=1.66, anthropic>=2.3, pandas 3, plotly 7) already covers the frontend, so leave it as his.

## AI coach (Alerts tab)
Trade form: buy/sell, ticker, shares, price, optional "why" box -> "Check this trade" shows the rule warnings plus a short AI note, then "Record it" or "Discard". The coach never blocks a trade.
Key: set `ANTHROPIC_API_KEY` as an environment variable, or in Streamlit Cloud Settings -> Secrets (see `.streamlit/secrets.toml.example`). No key = the coach says it is off and everything else works. Never commit a key.
Cost guard: max 5 coach notes per visitor session (`MAX_COACH_NOTES` in app/views/headsup.py), because a public app shares one key.
Imported broker files have no buy dates, so the coach is given the portfolio without its trade diary (otherwise it would be told "15 trades this month").

## Look and feel
Light theme (`.streamlit/config.toml` + CSS in `app/theme.py`). Each tab opens with a one-line "what this means" tip, scores have bars and plain-English meanings, and every tab ends with a "Words explained" section (`GLOSSARY` in `app/theme.py`, worded from the backend's own descriptions). To add or edit a definition, change that dictionary only.

## Never touched
core/** (not in the zip at all).

