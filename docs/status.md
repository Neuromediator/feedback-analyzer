# Status

Describes what is implemented and verified right now. Updated after each completed stage.
Last updated: after stage 15 (Jev vs Luna on a synthetic file). Plan steps are in `plan.md`; targets Q1-Q10 in `spec.md`.

## Stages

| Stage | State | Notes |
|---|---|---|
| 0-12 (plan.md) | done | Backend, UI, eval, docs, screenshots. |
| 13 Repository setup | done | Git repo, private GitHub remote, this document. |
| 14 Jev 1.14 analyzer | done | `ANALYZER=jev`; bake-off rows for 1.14 and 1.13; docs corrected. |
| 15 Jev vs Luna on a synthetic file | done | `samples/synthetic_reviews.csv`; results in "Jev vs Luna on a synthetic file". |

## Implemented

### Backend (`app/`, FastAPI, stdlib sqlite3)

- `config.py`: settings from `.env`: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default `openai/gpt-6-luna`),
  `OPENROUTER_REASONING` (default `low`), `ANALYZER` (`llm` default, or `jev`), `JEV_MODEL` (default `typesafe/jev-1.14`),
  `API_URL`, `DB_PATH`.
- `ingest.py`: cleaning (trim, collapse whitespace, drop lines under 2 chars, truncate at 2000 chars), dedup by sha256 of the
  normalized text, cap of 100 reviews, file parsing for `.txt`, `.csv` (delimiter sniffing, column auto-detect, otherwise returns
  `columns`), `.json` (array of strings or objects, wrapped list, JSON Lines). Files under 5 MB, UTF-8 (BOM tolerated).
- `sentiment.py`: score to label (1-2 negative, 3 neutral, 4-5 positive).
- `summary.py`: review count, average score, percent positive, top theme, top complaint (`other` excluded; ties alphabetical).
- `openrouter.py`: async chat client, strict JSON-schema output with `require_parameters`, optional reasoning effort, real cost
  from `usage.cost`. `response_error` classifies HTTP errors: 400-404 fatal; 429, 5xx, network errors, unusable JSON retryable.
  A missing key is a fatal error.
- `analyzers/base.py` (Analyzer protocol), `analyzers/llm.py` (chat-model analyzer; per-request theme enum; results matched by
  echoed `id`; malformed or unknown items dropped).
- `analyzers/jev.py`: Jev decision-model analyzer over the OpenRouter Decisions API
  (`POST /api/alpha/decisions`). One request per review (`state = {review}`), a `score` question with five ordered criteria
  (answer position 0-4, rounded and shifted to 1-5) and a `choice` question over the active themes. Semaphore of 8 requests.
  Failed requests are omitted so the runner retries them; if every request fails the first error is raised so the message
  reaches the UI; fatal errors propagate. Tracks cost, served models and call stats like the bake-off needs.
- `suggester.py`: one-line fix suggestion for negative reviews only (chat model, also used when `ANALYZER=jev`); failures leave
  the suggestion empty.
- `runner.py`: batches of 25, up to 4 concurrent, up to 2 retries re-sending only missing items, partial failure marks reviews
  `failed`, fatal errors stop the job.
- `jobs.py`: in-memory jobs with polling (`status` running/done/error, `stage` analyzing/suggesting/finished), retry of failed.
- `db.py`: `reviews` (unique `text_hash`) and `themes` tables, default themes (food, service, wait, price, cleanliness,
  ambiance, portions, other), add theme, save with saved/skipped counts, list by theme newest first, delete.
- Routes: `GET /health`, `POST /files/parse`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/retry`, `GET/POST /themes`,
  `POST /reviews`, `GET /reviews?theme=`, `DELETE /reviews/{id}`. App factory: `app.main:create_app` (run with `--factory`).

### UI (`ui/`, Streamlit)

Text area, file uploader with "Load into text box" and column picker, theme sidebar with add-theme, Analyze with progress bar,
summary tiles, theme bar chart, sentiment filter, results table with suggestions, Save to database (saved/skipped notice),
Retry failed, Saved history with theme filter and per-row delete, friendly errors for API down and API failure.
The UI is unchanged by the analyzer choice.

### Evaluation (`eval/`)

- `dataset.jsonl`: 100 synthetic reviews with known score and theme (generator `google/gemini-4-argon`, seed 42).
  Kinds: normal 45, mixed 10, sarcasm 8, short 8, non_english 8, typos 8, no_theme 7, emoji 6.
- `bakeoff.py` and `candidates.toml`: nine candidates (`analyzer = "jev"` selects the Decisions API) run through the real
  runner; output in `docs/bakeoff.md`. A run rewrites the whole report, so partial runs by name overwrite it.
- `smoke.py`: leftover 10-review throwaway script.

### Other

- `samples/`: txt, csv (with a multi-line review), wrapped json, csv with ambiguous columns.
- `docs/`: spec, architecture, plan, bakeoff, this file, 7 Playwright screenshots in `docs/screenshots/`.
- `README.md`: overview, setup, tests, model table, limitations.

## Verified

- 66 offline tests pass (25 in `tests/test_core.py`, 24 in `tests/test_backend.py`, 17 in `tests/test_jev.py`).
  Two live tests pass (`pytest -m live`): chat analyzer plus suggester, and Jev analyzer.
- Ruff check and format clean.
- Jev end to end: API started with `ANALYZER=jev`, the 16 sample reviews were analyzed by `typesafe/jev-1.14-20261014`,
  summary and suggestions returned, server stopped. Not repeated in the browser UI.
- Playwright walkthrough with real model calls (earlier stage, chat analyzer): file load (CSV with newline, wrapped JSON,
  column picker), analyze, summary, chart, negative filter, suggestions, save, duplicate save (0 saved, 10 skipped), history
  filter, delete, persistence across reload, custom theme, invalid theme, API down, bad key (failed banner, Retry failed does
  not crash).
- Clean-checkout run (earlier stage): copy without `.venv`, `.env`, database ran `uv sync`, 49 tests passed, `/health` served.

## Bake-off result (100 synthetic reviews, second run)

Every candidate met every target, so the set does not separate them. Default by the pre-set rule (cheapest meeting all):
`openai/gpt-6-luna` with low reasoning. Run-to-run noise is visible: against the first run, label accuracy moved by up to
3 points, GPT-6 Luna low went from 6.0 s to 14.0 s, and Jev Router cost went from $0.0420 to $0.0213.

| Candidate | Label acc | Score +/-1 | Theme acc | Cost / 100 | Time |
|---|---|---|---|---|---|
| gpt-6-luna low (default) | 98% | 100% | 100% | $0.0018 | 14.0 s |
| haiku-5.5 low | 97% | 100% | 100% | $0.0021 | 2.7 s |
| jev-1.14 | 99% | 100% | 100% | $0.0025 | 3.9 s |
| jev-1.13 | 99% | 100% | 100% | $0.0025 | 3.3 s |
| deepseek-v4.1-flash | 100% | 100% | 100% | $0.0056 | 16.0 s |
| gemini-3.5-flash-lite | 98% | 100% | 100% | $0.0100 | 2.2 s |
| jev-router | 100% | 100% | 100% | $0.0213 | 23.6 s |

Jev 1.14 and 1.13 gave identical accuracy; both missed one `normal` review. `jev-router` is a chat-model router (three
different serving models in one run), not the Jev decision model. Jev cost covers analysis only; suggestions are extra.

## Jev vs Luna on a synthetic file

`samples/synthetic_reviews.csv`: 64 hand-written fictional reviews with a `stars` column as reference (themes are not
labeled). Mix: normal, sarcasm, mixed, one-liners, typos, emoji, Finnish/Spanish/German/French/Estonian, one prompt
injection. Compared `openai/gpt-6-luna` (low reasoning) and `typesafe/jev-1.14`, same runner (batches of 25, 4 concurrent).

| Measure | GPT-6 Luna low | Jev 1.14 |
|---|---|---|
| Analysis time, direct, 2 runs | 6.9 s, 6.6 s | 3.4 s, 3.2 s |
| Analysis time through the API, 2 runs | 7.5 s, 13.1 s | 5.0 s, 3.3 s |
| Analysis cost, 64 reviews (2 runs) | $0.0011, $0.0012 | $0.0015, $0.0015 |
| Cost per 100 reviews | $0.0017-0.0018 | $0.0023 |
| Sentiment label matches stars | 97% | 97% |
| Score within +/-1 of stars | 98% | 98% |
| Exact score equals stars | 75% | 86% |
| Failed reviews | 0 | 0 |

- Both analyzers agree on the sentiment label for 62 of 64 reviews and on the theme for 57 of 64. Theme disagreements are
  mostly reviews with two topics (for example "sticky tables but fine food", Finnish "cold food and arrogant waiter").
- Suggestion step (26 negative reviews, same chat model for both): 6-7 s and about $0.0005 in addition.
- Full job through the API (analysis plus suggestions): Luna 14.9 s and 19.0 s; Jev 11.6 s and 10.0 s. The very first Jev job
  on a fresh server took 24.8 s (cause not investigated; later jobs did not repeat it).
- Jev is about 2x faster at analysis and about 30% more expensive per review; in absolute terms the cost gap is $0.0005
  per 100 reviews. Exact-score agreement with the stars was higher for Jev. One file, one writer, two runs each: indicative
  only. The default model is unchanged.

## Jev

- `typesafe/jev-1.14` (latest) and `typesafe/jev-1.13` are on OpenRouter as decision models (modality `text+image->decisions`,
  $0.042 per 1M input tokens, output free, 262K context), reachable with the normal OpenRouter key. They are absent from
  `/api/v1/models` but visible at `/api/v1/models/<id>/endpoints`. An earlier version of the docs claimed otherwise; that
  was wrong and is corrected.
- The OpenRouter docs mention a `~typesafe/jev-latest` alias; not tested. The default pins `typesafe/jev-1.14`.
- OpenRouter also lists other decision models (OpenAI, Microsoft, Perplexity, Cloudflare per its Jev tutorial); not tested.

## Known gaps

- Jev not exercised in the browser UI, only through the API and tests.
- Jev score is a probability-weighted position rounded to 1-5; exact-score accuracy was not measured (label and +/-1 only).
- `.env.example` does not list `ANALYZER` and `JEV_MODEL` (the file is outside what this session may edit); defaults apply.
- Retry-failed-then-succeed is covered by backend tests only, not in the browser.
- Jobs are in memory; an API restart loses a running job.
- Q6 (time) verified at bake-off level only, and timings vary between runs.
- Dataset is easy and skewed negative (55 of 100 are scores 1-2); real reviews will score lower.
- Real Google/Yelp export field names are guessed from common names.
- Screenshots 02-05 were taken before some cosmetic fixes.
