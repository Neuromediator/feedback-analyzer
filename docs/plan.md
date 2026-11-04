# Plan

Small steps; each step ends with a check that must pass before the next begins. Targets Q1-Q10 are defined in `spec.md`.
Design details are in `architecture.md`.

## Status

Steps 0-10 and 12 are done; Step 11 (Jev classifier) is not, because the classifier is not on OpenRouter and
its API is in limited early access. Deviations from the plan: the input cap is 100 reviews (not 500), the default
model is GPT-6 Luna with low reasoning (bake-off result in `bakeoff.md`), and the API starts with `--factory`.
Verification: 49 offline tests, one live test (`pytest -m live`), and a Playwright walkthrough of the UI
(screenshots in `docs/screenshots/`).

## Step 0: Verify unknowns (no app code)

- Jev: confirm how it is reached (TypeSafe API vs OpenRouter `typesafe/jev-1.13` / `typesafe/jev-router`), request shape, and whether early access is available to us.
- OpenRouter: confirm structured-output support for the candidate models (Providers section lists `structured_outputs`), and where cost per request can be read (usage fields or `/models` pricing).
- Artificial Analysis: pull the current intelligence-vs-price frontier and pick 4-6 candidates for `eval/candidates.toml`.
- Check: a one-page note in `eval/NOTES.md` with the findings. If Jev is not accessible, mark `analyzers/jev.py` as dropped and move on.

## Step 1: Scaffold

- `uv init`, add deps: fastapi, uvicorn, httpx, pydantic-settings, streamlit, python-multipart; dev: pytest, pytest-asyncio, ruff.
- Folders, `.env.example`, `.gitignore` (`.env`, `feedback.db`), `GET /health`.
- Check: `uv run uvicorn app.main:create_app --factory` serves `/health`; `uv run pytest` runs (empty) green.

## Step 2: Pure core (TDD)

- `sentiment.py`, `ingest.py` (clean, dedupe, cap, truncate), `summary.py`.
- Tests for every row in spec 3.1 and the summary rules (ties, no negatives, `other` excluded).
- Check: tests pass.

## Step 3: File parsing

- `parse_file` for txt, csv (column detection), json (array, objects, wrapped list, JSON Lines).
- `samples/` with fictional files in each shape, plus malformed files.
- Check: tests pass for good and bad files; `needs_column` path works.

## Step 4: Database

- `db.py`: schema creation, theme seeding, save with skip count, list by theme, delete.
- Check: tests on a temp SQLite file, including saving the same batch twice (saved N, skipped N).

## Step 5: LLM analyzer

- `analyzers/base.py`, `analyzers/llm.py`: prompt, per-request schema with theme enum, strict mode, `require_parameters`.
- Tests with httpx mock transport: valid, malformed JSON, out-of-range score, unknown theme.
- Check: tests pass; then one manual live call on 5 reviews returns valid results and a `model` value.

## Step 6: Runner and jobs

- `runner.py` (batching, semaphore, retry of missing items, failed status), `jobs.py`, progress counters.
- Tests with a fake analyzer that drops items, returns junk, or raises (Q10).
- Check: forced failure yields partial results; retry fills them in.

## Step 7: Suggester

- `suggester.py`: negative reviews only, failures leave null.
- Check: tests with mock transport; live call on a few negatives gives one sentence each.

## Step 8: API

- Routes: `/files/parse`, `/jobs`, `/jobs/{id}`, `/jobs/{id}/retry`, `/themes`, `/reviews`.
- Check: `TestClient` tests for every route and error (empty, over cap, bad file, save twice, delete).

## Step 9: Eval harness and bake-off

- `generate_dataset.py` -> `eval/dataset.jsonl` (~100 reviews with hard cases); hand-check ~20.
- `bakeoff.py` runs the candidates through the real runner and writes the results table.
- Check: table produced; pick the default model by the rule in spec section 4; set `OPENROUTER_MODEL` in `.env.example`.
- If a target is missed by every candidate, record the gap; tune the prompt once, re-run, then document honestly.

## Step 10: Streamlit UI

Build in this order, checking in the browser after each:
1. Text box, Analyze button, progress bar (polling), summary tiles.
2. Theme bar chart (`st.bar_chart`) and results table with the sentiment dropdown.
3. File uploader and **Load into text box** (set the text area's session-state key in an `on_click` callback), CSV/JSON column dropdown.
4. Theme management (add a theme).
5. **Save to database** with the saved/skipped message; **Saved history** with theme filter and delete.
6. Failed-reviews banner and **Retry failed**; friendly errors for missing key or API down.
- Check: manual walkthrough of the full flow with the sample files; screenshots captured.

## Step 11: Jev analyzer (if accessible)

- `analyzers/jev.py` behind the same interface; add to the bake-off.
- Check: bake-off row for Jev; if it beats the LLM default on cost within targets, say so in the README; otherwise keep it as a documented option.

## Step 12: Polish and release check

- Concise README: what it does, setup (`uv sync`, copy `.env.example`, two run commands), screenshots, bake-off table, limitations (one theme per review, synthetic data, data sent to OpenRouter).
- Check each target Q1-Q10 and record pass or fail in the README.
- Clean-checkout run following only the README (Q8).

## Order rationale

Pure logic and tests first, then the risky external pieces (LLM, persistence), then the eval that picks the model, and the UI last, so the UI is built against an API that already works. Jev is last because it is optional and its access is the least certain.

## Open questions

- Jev access method and pricing (Step 0).
- Whether `usage.cost` is available from OpenRouter for cost measurement or must be computed from token counts and model prices.
- Real Google Maps / Yelp export field names: the parser uses the common candidate names; sample files in `samples/` will mirror those shapes with fictional data.
