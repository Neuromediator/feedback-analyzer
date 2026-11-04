# Status

Describes what is implemented and verified right now. Updated after each completed stage.
Last updated: after stage 13 (repository setup). Plan steps are in `plan.md`; targets Q1-Q10 in `spec.md`.

## Stages

| Stage | State | Notes |
|---|---|---|
| 0-12 (plan.md) | done | All steps except 11 (Jev). Details below. |
| 13 Repository setup | done | Git repo, GitHub remote, this document. |
| 14 Jev 1.14 analyzer | not started | Correction: the classifier IS on OpenRouter (see "Jev"). |

## Implemented

### Backend (`app/`, FastAPI, stdlib sqlite3)

- `config.py`: settings from `.env` (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_REASONING`, `API_URL`, `DB_PATH`).
  Default model `openai/gpt-6-luna`, reasoning `low`.
- `ingest.py`: cleaning (trim, collapse whitespace, drop lines under 2 chars, truncate at 2000 chars), dedup by sha256 of the
  normalized text, cap of 100 reviews, file parsing for `.txt`, `.csv` (delimiter sniffing, column auto-detect, otherwise returns
  `columns`), `.json` (array of strings or objects, wrapped list, JSON Lines). Files under 5 MB, UTF-8 (BOM tolerated).
- `sentiment.py`: score to label (1-2 negative, 3 neutral, 4-5 positive).
- `summary.py`: review count, average score, percent positive, top theme, top complaint (`other` excluded; ties alphabetical).
- `openrouter.py`: async client, strict JSON-schema output with `require_parameters`, optional reasoning effort, real cost from
  `usage.cost`. 400-404 are fatal; 429, 5xx, network errors and unusable JSON are retryable. A missing key is a fatal error.
- `analyzers/base.py` (Analyzer protocol), `analyzers/llm.py` (chat-model analyzer; per-request theme enum; results matched by
  echoed `id`; malformed or unknown items dropped).
- `suggester.py`: one-line fix suggestion for negative reviews only; failures leave the suggestion empty.
- `runner.py`: batches of 25, up to 4 concurrent, up to 2 retries re-sending only missing items, partial failure marks reviews
  `failed`, fatal errors stop the job.
- `jobs.py`: in-memory jobs with polling (`status` running/done/error, `stage` analyzing/suggesting/finished) and retry of failed.
- `db.py`: `reviews` (unique `text_hash`) and `themes` tables, default themes (food, service, wait, price, cleanliness,
  ambiance, portions, other), add theme, save with saved/skipped counts, list by theme newest first, delete.
- Routes: `GET /health`, `POST /files/parse`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`, `GET/POST /themes`,
  `POST /reviews`, `GET /reviews?theme=`, `DELETE /reviews/{id}`. App factory: `app.main:create_app`.

### UI (`ui/`, Streamlit)

Text area, file uploader with "Load into text box" and column picker, theme sidebar with add-theme, Analyze with progress bar,
summary tiles, theme bar chart, sentiment filter, results table with suggestions, Save to database (saved/skipped notice),
Retry failed, Saved history with theme filter and per-row delete, friendly errors for API down and API failure.

### Evaluation (`eval/`)

- `dataset.jsonl`: 100 synthetic reviews with known score and theme (generator `google/gemini-4-argon`, seed 42).
  Kinds: normal 45, mixed 10, sarcasm 8, short 8, non_english 8, typos 8, no_theme 7, emoji 6.
- `bakeoff.py` and `candidates.toml`: seven candidates run through the real runner; output in `docs/bakeoff.md`.
- `smoke.py`: leftover 10-review throwaway script.

### Other

- `samples/`: txt, csv (with a multi-line review), wrapped json, csv with ambiguous columns.
- `docs/`: spec, architecture, plan, bakeoff, this file, 7 Playwright screenshots in `docs/screenshots/`.
- `README.md`: overview, setup, tests, model table, limitations.

## Verified

- 49 offline tests pass (25 in `tests/test_core.py`, 24 in `tests/test_backend.py`); 1 live test (`pytest -m live`) passed once.
- Ruff clean.
- Playwright walkthrough with real model calls: file load (CSV with newline, wrapped JSON, column picker), analyze, summary,
  chart, negative filter, suggestions, save, duplicate save (0 saved, 10 skipped), history filter, delete, persistence across
  reload, custom theme, invalid theme, API down, bad key (failed banner, Retry failed does not crash).
- Clean-checkout run: copy without `.venv`, `.env`, database ran `uv sync`, 49 tests passed, `/health` served.

## Bake-off result (100 synthetic reviews)

Every candidate met every target, so the set does not separate them. Default chosen by the pre-set rule (cheapest meeting all):
`openai/gpt-6-luna` with low reasoning.

| Candidate | Label acc | Cost / 100 | Time |
|---|---|---|---|
| gpt-6-luna low (default) | 99% | $0.0018 | 6.0 s |
| haiku-5.5 low | 95% | $0.0021 | 2.7 s |
| deepseek-v4.1-flash | 100% | $0.0047 | 16.9 s |
| gemini-3.5-flash-lite | 97% | $0.0081 | 2.5 s |
| jev-router | 100% | $0.0420 | 26.1 s |

`jev-router` is a chat-model router (served by three different models in one run), not the Jev classifier.

## Jev

- Corrected finding: `typesafe/jev-1.14` (latest) and `typesafe/jev-1.13` are on OpenRouter as decision models
  (modality `text+image->decisions`, $0.042 per 1M input tokens, 262K context). They use the OpenRouter Decisions API, not
  chat completions. They are absent from `/api/v1/models` but visible at `/api/v1/models/<id>/endpoints`.
- Not implemented yet. `README.md`, `architecture.md` and `plan.md` still say the classifier is not on OpenRouter; they are
  corrected in stage 14.

## Known gaps

- Jev classifier analyzer missing (stage 14).
- Retry-failed-then-succeed is covered by backend tests only, not in the browser.
- Jobs are in memory; an API restart loses a running job.
- Q6 (time) verified at bake-off level only (6.0 s for the default).
- Dataset is easy and skewed negative (55 of 100 are scores 1-2); real reviews will score lower.
- Real Google/Yelp export field names are guessed from common names.
- Screenshots 02-05 were taken before some cosmetic fixes.
