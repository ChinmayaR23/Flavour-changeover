# Flavour Changeover Optimizer

A Streamlit web app that records each flavour changeover, finds the steps that cause the most
line-stop time, gives rule-based advice, and plans a shorter next changeover.
Built for the Design Thinking lab project *AI-Based Flavour Changeover Time Optimization System*.

> The app starts with **illustrative sample data** (tagged "Sample data" everywhere).
> It only advises staff and never controls machinery.

## Screens

| Page | What it does |
|---|---|
| **Dashboard** | 3D can of the flavour now running (tilt with the mouse, click to spin), KPIs, trend, top bottlenecks, latest tips |
| **Log changeover** | Live timer from the moment the line stops, Start/Stop for each step, delays, or enter a past changeover from paper |
| **Analysis** | Pareto ranking of steps, rules R1–R5 with Accept/Ignore, step variation, overlap per changeover |
| **Planner** | Day's orders → best flavour order (light → dark), due-time check, crew task plan (Gantt), changeover matrix |
| **Data and settings** | Edit flavours, steps, lines and rule limits; CSV import/export; remove or reset sample data; AI predictor status |

## Logic

1. **Durations**: `end − start` per step; line-stop = restart − stop; overlap = work ÷ line-stop.
2. **Usual time**: median of the last 20 logs of a step (planned time until 5 logs exist); CV for variation.
3. **Pareto**: steps sorted by total minutes; bottlenecks = steps until 80 % of line-stop time.
4. **Rules**: R1 overrun (> 1.25 × usual), R2 could be done off-line, R3 unstable (CV > 0.30),
   R4 waiting (> 15 min), R5 dark → light order. Severity by minutes at stake.
5. **Matrix**: pair history median once a pair has 3 logs; otherwise
   `220 + 35 × colour drop + 60 if allergen` (starting guesses, editable).
6. **Sequence optimizer**: tries every order for up to 8 flavours; above that, nearest neighbour
   plus 2-opt / move / swap. Keeps priority-1 orders first and checks due times.
7. **Task scheduler**: moves off-line steps before the stop, then gives each free person the ready step
   with the longest chain after it (critical path first).
8. **AI predictor**: random forest, used only after 30 changeovers and only if it beats the median by 10 %.

All logic is in `core/` as plain Python and is tested in `tests/`.

## Run it on your computer

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

It opens at http://localhost:8501. The database (`data/changeover.db`) is created and filled with sample
data on first run. Run the tests with `pip install pytest` then `pytest`.

## Deploy (free) on Streamlit Community Cloud

1. Push this folder to GitHub (the repo can be public or private).
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click **Create app**.
3. Pick the repo, branch `main`, main file `app.py`. Optionally choose a custom URL.
4. Click **Deploy**. In a few minutes you get a link like `https://<name>.streamlit.app`.

Every push to `main` updates the live site automatically.

**Note on data:** Streamlit Community Cloud does not keep files between restarts, so the SQLite
database resets to the sample data when the app restarts or wakes from sleep. That is fine for demos.
For real factory logging, move the database to a hosted one (for example a free Postgres) or export
CSVs regularly from *Data and settings*.

## Project structure

```
app.py                  entry point and navigation
views/                  one file per page
core/                   db, analysis, rules, matrix, optimizer, scheduler, predict, planning, ui, hero
data/schema.sql         10 tables
data/seed_sample.py     illustrative sample data
tests/                  pytest checks for core/
.streamlit/config.toml  theme
```
