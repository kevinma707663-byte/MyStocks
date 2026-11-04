# MyPortfolio web app (React)

The screens people click on. Built with React + TypeScript + Vite + Tailwind,
started from a Figma Make design. Every number comes from `core/` through the
Python server in `api/`: nothing on screen is made up.

```
browser (web/, React)  --/api/...-->  api/main.py (FastAPI)  -->  core/ (the brain)
```

## Run it on your computer

You need two terminals, both started from the project folder.

**1. The Python server** (needs Python 3.12+). The first two lines are only
needed the first time.

Mac:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn api.main:app --reload --port 8000
```

Windows:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\uvicorn api.main:app --reload --port 8000
```

**2. The screens** (needs Node.js 20+). The same on Mac and Windows:

```bash
cd web
npm install                                # once
npm run dev
```

Open http://localhost:5173. While developing, Vite passes every `/api`
request on to the Python server on port 8000. Keep both terminals open.

## Where things live

| File | What it does |
|---|---|
| `src/App.tsx` | Every screen: set-up, dashboard, and the 8 guided steps |
| `src/api.ts` | The only file that talks to the server, with a type for each answer |
| `src/content.ts` | The plain-English words: each page's tip, "Words explained", what each risk area asks, the optimizer rule help. Emma's text from the Streamlit app, word for word. To add or edit a definition, change this file only |
| `src/Fin.tsx` | The first screen: Fin the fish asks 4 quick questions (scripted, not AI, no cost), the same words as the Streamlit app's `app/chat.py` and `app/mascot.py`. The answers stay in the visitor's browser. To change a question or reply, change this file only |
| `src/Chart.tsx` | Draws `core/`'s own Plotly charts (the ones the Streamlit app showed), sent by the server as JSON. plotly.js (about 1.4 MB zipped) only downloads the first time a chart is opened. Keep `plotly.js-dist-min` on the version the Python `plotly` package uses (`plotly.offline.get_plotlyjs_version()`) |
| `src/index.css` | The look (the Figma design, plus the styles added for real data and phones) |
| `../api/main.py` | The server: one address per `core/` function the screens use |

## Things to know

- **The portfolio is saved in the visitor's own browser** (localStorage), never
  on the server, so every visitor has their own. "Start over" in the sidebar
  forgets it.
- **Broker files have no buy dates.** After an import, value over time, the
  S&P 500 twin and the date-based warnings are switched off, the same as in
  the Streamlit app.
- **The AI coach** needs `ANTHROPIC_API_KEY` set in the terminal that runs the
  Python server, before starting it. Without it, the coach says it's off and
  everything else works. Each visitor gets 10 coach notes a day
  (`COACH_NOTES_PER_DAY` in `api/main.py`). Never put the key in the code or on GitHub.
  - Mac: `export ANTHROPIC_API_KEY="sk-ant-..."`
  - Windows (PowerShell): `$env:ANTHROPIC_API_KEY="sk-ant-..."`
  - Windows, for every new terminal: `setx ANTHROPIC_API_KEY "sk-ant-..."`, then
    open a new terminal (the notebook's Step 7.1 does this)
- **The server handles one request at a time**, because `core/`'s data memory
  isn't built for two at once. The first look at a stock takes 15 to 30 seconds;
  repeats within the hour are fast.
