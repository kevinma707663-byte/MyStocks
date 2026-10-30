# MyStocks frontend (Emma's part)

Run locally:   pip install -r requirements.txt   then   streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud -> main file `streamlit_app.py`

## What is mine (new files only)
streamlit_app.py, app/**, .streamlit/config.toml, sample/OpenPosition_10_24_2026.csv, FRONTEND_README.md, requirements.frontend.txt
## Shared file where need changes
requirements.txt: NOT yet in the zip. Edit needed: streamlit to streamlit>=1.50 (needed for st.segmented_control and width="stretch"). Keep the notebook libs. See requirements.frontend.txt for reference.
