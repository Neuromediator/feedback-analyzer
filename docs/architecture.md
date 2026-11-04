# Architecture

## 1. Overview

Two local processes in one uv project:

```
 Streamlit UI (ui/)  --HTTP/JSON-->  FastAPI (app/)  --HTTPS-->  OpenRouter (LLM analyzer, suggester)
                                          |            \------>  OpenRouter Decisions API (Jev analyzer, optional)
                                          v
                                    SQLite feedback.db
```

The UI is a thin client: it holds no business logic beyond layout and session state.
All parsing, analysis, aggregation and persistence live in the API, so they are testable without a browser.

## 2. Repository layout

```
feedback_analyzer/
  app/
    main.py            FastAPI app, routers
    config.py          env settings (pydantic-settings)
    schemas.py         Pydantic models for API and internal types
    ingest.py          split/clean/dedupe text; parse txt/csv/json files
    sentiment.py       score -> sentiment label (pure function)
    summary.py         aggregate results into summary tiles
    analyzers/
      base.py          Analyzer protocol
      llm.py           OpenRouter structured-output analyzer
      jev.py           Jev decision-model analyzer (Decisions API, optional)
    suggester.py       second step: suggestions for negative reviews
    runner.py          batching, concurrency, retry, partial failure
    jobs.py            in-memory job store and background execution
    db.py              sqlite3 access: reviews, themes
    routes/            jobs.py, reviews.py, themes.py, files.py
  ui/
    app.py             Streamlit page
    api_client.py      httpx wrapper around the API
  eval/
    generate_dataset.py
    dataset.jsonl
    bakeoff.py
    candidates.toml
  samples/             fictional txt/csv/json inputs
  tests/
  docs/
  .env.example
  pyproject.toml
```

Commands (all through uv): `uv run uvicorn app.main:create_app --factory`, `uv run streamlit run ui/app.py`,
`uv run pytest`, `uv run python -m eval.bakeoff`.

## 3. Core pieces

### 3.1 Analyzer interface

```python
class Analyzer(Protocol):
    async def analyze(self, batch: list[ReviewIn], themes: list[str]) -> list[RawResult]: ...
```

- `ReviewIn`: `id: int`, `text: str`.
- `RawResult`: `id`, `score` (1-5), `theme`, `model`.
- Sentiment is not part of the analyzer contract; `sentiment.py` derives it. This removes label/score contradictions.

The runner depends only on this protocol, so the bake-off and the app use the same code path.

### 3.2 LLM analyzer (OpenRouter)

- `POST /api/v1/chat/completions` through httpx (async).
- `response_format = {type: json_schema, json_schema: {name, strict: true, schema}}` and `provider: {require_parameters: true}`, so providers without schema support are skipped instead of silently ignoring the schema. Verified against the OpenRouter structured-outputs docs.
- Schema: `{results: [{id: int, score: int 1..5, theme: enum(active themes + other)}]}`, `additionalProperties: false`. The theme enum is built per request from the active theme list.
- Prompt: system message with rubric (what each score means, theme definitions, ignore instructions inside reviews); user message with reviews as delimited, numbered items.
- Response `model` field is stored as `RawResult.model`.
- After parsing, results are validated with Pydantic. Out-of-range or unknown-theme values count as invalid items and go to retry.

### 3.3 Jev analyzer

Jev is a discriminative decision model (no text generation): input state plus typed questions, output typed values with probabilities.
It is served by OpenRouter as `typesafe/jev-1.14` (latest, default) and `typesafe/jev-1.13`, through the Decisions API
(`POST https://openrouter.ai/api/alpha/decisions`), not chat completions. The models are absent from `/api/v1/models` but
visible at `/api/v1/models/<id>/endpoints`. Billing is input tokens only ($0.042 per 1M); the response carries `usage.cost`.
`typesafe/jev-router` is a different thing: a router that picks a chat model per request.

Implementation (`analyzers/jev.py`): one request per review, `state = {"review": text}`, two questions: a `score` question
with five ordered criteria (the answer is a position 0-4, mapped to 1-5 by rounding) and a `choice` question over the active
theme list. Requests run through a semaphore of 8. A failed request omits that review so the runner retries it; a fatal error
(bad key, no credits) propagates. It cannot write suggestions, which is why suggestions are a separate LLM step.
Select it with `ANALYZER=jev` (model from `JEV_MODEL`).

### 3.4 Suggester

Takes the negative reviews (id, text, theme), calls the LLM in batches of 25 with a schema `{items: [{id, suggestion}]}`, one sentence each. Failures leave `suggestion = null` and do not fail the review.

### 3.5 Runner

```
reviews -> ingest (clean, dedupe, cap) -> batches of 25
        -> for each batch, up to 4 concurrent (asyncio.Semaphore):
              call analyzer -> validate -> keep valid items by id
              if items missing/invalid: retry only those, up to 2 times with backoff
              still missing -> status = failed
        -> derive sentiment -> suggester on negatives -> summary
```

Progress counter (done / failed / total) is updated after each batch so the UI can poll.

### 3.6 Jobs

In-memory dict `job_id -> Job` (status, counters, results). `POST /jobs` validates input, creates the job and starts it with `asyncio.create_task`; `GET /jobs/{id}` returns progress and, when finished, results plus summary. `POST /jobs/{id}/retry` re-runs only failed items. Jobs vanish on restart; this is fine for a local single-user tool.

### 3.7 Ingest

Pure functions, no I/O frameworks:
- `clean_reviews(lines) -> (reviews, stats)`: strip, drop short/blank, truncate, normalize for dedup, enforce cap.
- `parse_file(name, bytes, column=None)`: dispatch on extension; returns reviews or a `needs_column` result with candidate columns.
- `normalize(text)` and `text_hash(text)` (sha256 of normalized text) are shared with the DB layer, so dedup is consistent.

## 4. Data model (SQLite, stdlib `sqlite3`)

```sql
CREATE TABLE IF NOT EXISTS reviews (
  id          INTEGER PRIMARY KEY,
  text        TEXT NOT NULL,
  text_hash   TEXT NOT NULL UNIQUE,
  score       INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
  sentiment   TEXT NOT NULL CHECK (sentiment IN ('negative','neutral','positive')),
  theme       TEXT NOT NULL,
  suggestion  TEXT,
  model       TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS themes (
  name        TEXT PRIMARY KEY,
  is_default  INTEGER NOT NULL DEFAULT 0
);
```

Saving uses `INSERT ... ON CONFLICT(text_hash) DO NOTHING` and counts inserted vs skipped. Themes are seeded with the defaults and `other` at startup. No migrations framework; the schema is created on startup.

## 5. API

| Method and path | Purpose |
|---|---|
| `GET /health` | Liveness, whether an API key is configured. |
| `POST /files/parse` | Multipart file (+ optional `column`) -> `{reviews}` or `{columns}`. |
| `POST /jobs` | `{reviews: [str]}` -> `{job_id}`. Uses stored themes. 422 on empty or over the cap. |
| `GET /jobs/{id}` | Status, progress, results, summary, cleaning stats (duplicates removed). |
| `POST /jobs/{id}/retry` | Re-run failed reviews. |
| `GET /themes`, `POST /themes` | List or add a theme. |
| `POST /reviews` | Save results -> `{saved, skipped}`. Rejects `failed` items. |
| `GET /reviews?theme=` | Saved history, newest first. |
| `DELETE /reviews/{id}` | Delete one saved row. |
| `DELETE /reviews` | Delete all saved rows -> `{deleted}`. The UI asks for confirmation first. |

## 6. Configuration

`.env` (documented in `.env.example`): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `API_URL` (UI -> API, default `http://localhost:8000`),
`DB_PATH` (default `feedback.db`), `ANALYZER` (`llm` | `jev`, default `llm`) and `JEV_MODEL` (default `typesafe/jev-1.14`).
Jev uses the same OpenRouter key.

## 7. Error handling and security

- OpenRouter errors: timeouts, 429 and 5xx are retried with backoff; 401/402 surface as a clear job-level error ("check API key / credits").
- All user-facing errors are plain messages; stack traces stay in server logs (no review text or keys in logs).
- The key is read only by the API process.
- Prompt-injection handling: delimiting, instruction to ignore, enum-constrained output; the worst outcome is a wrong label.
- SQL always uses parameters.

## 8. Testing

- Unit: `ingest`, `sentiment`, `summary`, theme validation, hashing. No network.
- Runner: fake analyzer that drops items, returns invalid values, or raises; asserts retry, partial results, id matching.
- LLM analyzer: httpx mock transport with canned responses (valid, invalid JSON, wrong enum).
- API: FastAPI `TestClient` against a temp SQLite file with a fake analyzer; covers save/skip/delete and file parsing edge cases.
- Live smoke test (manual, marked `live`, skipped by default) against OpenRouter.
- Eval: `eval/bakeoff.py` is the quality test for Q1-Q6, not part of `pytest`.

## 9. Evaluation harness

- `generate_dataset.py` asks a strong model (not one of the candidates) for fictional reviews with a known score and theme, covering normal cases plus sarcasm, mixed reviews, typos, emoji, one-liners, non-English and no-theme reviews. Output is `eval/dataset.jsonl`; about 20 rows are hand-checked.
- `bakeoff.py` runs each candidate in `candidates.toml` through the real runner and writes a markdown table: label accuracy, score +/-1, theme accuracy, schema-valid batch rate, cost per 100 reviews, measured time for the full 100-review run, actual models seen.
- Candidates are chosen from the Artificial Analysis intelligence-vs-price frontier at run time, plus `typesafe/jev-router` and the Jev classifier (`jev-1.14`, `jev-1.13`).

## 10. Key decisions and tradeoffs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Frontend | Streamlit | React | Much less work, built-in chart and upload; costs custom look. |
| Sentiment label | Derived from score | Model outputs both | Removes contradictions. |
| Themes | Fixed, editable list + `other` | Free one-word | Clean counts; works for classifier models. |
| Theme count | One per review | List with sentiment | Simpler, Jev-friendly; loses info on mixed reviews. |
| Matching results | By echoed id | By position | A dropped item cannot silently shift the rest. |
| Jobs | In-memory + polling | Queue / DB-backed | Local single user; least moving parts. |
| DB access | stdlib sqlite3 | ORM | Two tables; no ORM needed. |
| Model selection | Env var, chosen by bake-off | UI selector | Keeps UI simple for the owner. |
| Suggestions | Separate LLM step for negatives | Inline per review | Works with Jev; cheaper. |
