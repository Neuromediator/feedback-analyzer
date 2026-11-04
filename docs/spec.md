# Spec: Customer Feedback Analyzer

## 1. Problem

A restaurant owner has dozens to hundreds of customer reviews and no time to read them. They want to
paste reviews or load a file, click one button, and see how customers feel and what they keep
complaining about. They can then save the results to build a growing record of feedback.

Primary user: a non-technical restaurant owner. Secondary audience: portfolio reviewers who clone the repo.

## 2. Scope

In scope (v1):
- Input by pasting text, or loading `.txt`, `.csv`, `.json` / JSON Lines files (Google Maps / Yelp style exports) into the text box.
- Per-review analysis: score 1-5, derived sentiment label, one theme, and a one-line fix suggestion for negative reviews.
- Results screen: summary, theme bar chart, sentiment-filtered table.
- Save results to SQLite (`feedback.db`) and browse saved history with a theme filter and row delete.
- Configurable theme list (defaults plus owner-added themes).
- Model-agnostic analysis through OpenRouter; pluggable analyzer interface with an LLM and a Jev implementation.
- Evaluation harness (synthetic labeled dataset, model bake-off) whose results are documented.

Out of scope (v1):
- Authentication, multi-user, multi-restaurant accounts, hosting or deployment (runs locally only).
- Review ratings or dates from files (ignored), trend-over-time charts.
- Removing themes, editing saved rows, clearing all history, export.
- UI model selector (model is set by env var).
- Multiple themes per review (one primary theme only; limitation documented).
- Calling review platforms' APIs directly.

## 3. Functional requirements

### 3.1 Input

| Rule | Behavior |
|---|---|
| Format | One review per line in the text box. Blank lines ignored. |
| Duplicates | Lines identical after normalization (trim, collapse whitespace, lowercase) are analyzed once. UI shows "N duplicates removed". |
| Long review | Truncated to 2,000 characters before analysis. |
| Cap | Maximum 100 reviews after dedup (a realistic batch for one owner; typical use is 50-100). Above that the request is rejected with a clear message and the count. |
| Empty input | Analyze button disabled; backend returns 422. |
| Language | Any language accepted. Themes and suggestions are always English. |
| Whitespace-only / one-character lines | Dropped like blank lines (too short to analyze: fewer than 2 non-space characters). |

### 3.2 File loading

A file uploader plus a **Load into text box** button. The button parses the file and replaces the text box
content with one review per line (line breaks inside a review become spaces). The owner can edit before analyzing.
Star ratings and dates in the file are ignored.

| Type | Parsing |
|---|---|
| `.txt` | One review per line; if the file contains blank-line-separated paragraphs and no single-line structure, each paragraph is one review. |
| `.csv` | Header row required. Review column auto-detected from names: `review`, `text`, `comment`, `content`, `body`, `review_text`. If there is one column, use it. If ambiguous, backend returns the column list and the UI shows a dropdown. |
| `.json` | Accepts: array of strings; array of objects; object wrapping a single list; JSON Lines. Text field detected from the same candidate names plus `reviewText`; otherwise the longest string field in the first object, confirmed via the same dropdown. |

Limits: 5 MB, UTF-8 (BOM tolerated). Invalid files return a readable error, never a stack trace.
Sample files in the three formats, with fictional data, live in `samples/`.

### 3.3 Analysis

Per review, the system produces:

| Field | Type | Rule |
|---|---|---|
| `id` | int | Index within the job; echoed by the model to match results. |
| `score` | int 1-5 | From the analyzer. 1 = very negative, 5 = very positive. |
| `sentiment` | `negative` / `neutral` / `positive` | Derived in code: 1-2 negative, 3 neutral, 4-5 positive. Never produced by the model. |
| `theme` | string | One word from the active theme list, or `other`. Enforced as an enum in the schema. |
| `suggestion` | string or null | One line on how the business could fix the issue. Only for negative reviews; null otherwise. |
| `status` | `ok` / `failed` | `failed` after retries are exhausted. |
| `model` | string | Actual model that served the request, as reported by the provider. |

Suggestions are generated in a second step that sends only negative reviews to an LLM, so they work with any analyzer.

Review text is untrusted: it is delimited in the prompt, the model is told to ignore instructions inside it, and output is schema-constrained.

### 3.4 Themes

Default list: `food`, `service`, `wait`, `price`, `cleanliness`, `ambiance`, `portions`, plus the permanent `other`.
The owner can add themes in the UI. Validation: lowercase letters/hyphens, 2-24 chars, unique, no spaces.
Themes cannot be removed in v1. Themes persist in SQLite. Saved reviews store the theme as plain text, so history stays valid.

### 3.5 Results screen

Summary tiles (computed over `ok` reviews only):
- Total reviews analyzed
- Average score (1 decimal)
- Percent positive (whole number)
- Most mentioned theme (excluding `other`)
- Most complained-about theme: theme with the most negative reviews (excluding `other`); shows "No complaints" if none. Ties break alphabetically.

Below the tiles:
- Bar chart (`st.bar_chart`): review count per theme.
- Table of reviews (text, score, sentiment, theme, suggestion) with a dropdown: All / Positive / Neutral / Negative.
- A banner when some reviews failed: "N reviews failed" with a **Retry failed** button.
- **Save to database** button.

### 3.6 Saving and history

**Save to database** writes every `ok` review into the `reviews` table.
- Duplicate protection by unique hash of the normalized text. Result message: "Saved 38, skipped 12 already saved".
- Each row stores text, score, sentiment, theme, suggestion, model, created_at.

**Saved history** section: reads all saved rows (newest first), a theme filter dropdown, and a delete button per row.

### 3.7 Progress and errors

- Analysis runs as a background job; the UI shows a progress bar (reviews done / total) by polling.
- Batches of 25 reviews, up to 4 concurrent calls.
- Per batch: up to 2 retries with exponential backoff; only missing or invalid items are re-sent.
- Results are matched by echoed `id`, never by position.
- Missing OpenRouter key or unreachable API: a clear message in the UI (not a traceback).

## 4. Quality targets (evaluation criteria)

The product is judged against these. Measured on the labeled synthetic set (`eval/dataset.jsonl`, ~100 reviews including hard cases) unless noted.

| # | Criterion | Target |
|---|---|---|
| Q1 | Sentiment label accuracy (derived from score) | >= 90% |
| Q2 | Score within +/-1 of ground truth | >= 85% |
| Q3 | Theme accuracy | >= 80% |
| Q4 | Batches returning schema-valid output without manual repair | >= 99% |
| Q5 | Cost per 100 reviews | < $0.05 |
| Q6 | Time to analyze 100 reviews (4 batches of 25, run concurrently) | < 30 s |
| Q7 | Edge-case inputs in section 3.1-3.2 produce no crash and a correct message | 100%, covered by automated tests with OpenRouter mocked |
| Q8 | Fresh clone runs with `uv sync` plus two commands | Verified by following the README on a clean checkout |
| Q9 | README includes screenshots and the bake-off results table | Present |
| Q10 | Failure handling: a forced failing batch yields partial results and a working retry | Covered by a test |

Default-model rule: the cheapest candidate that meets Q1-Q6; ties go to lower latency.
If no candidate meets a target, record the best result and the gap in the README instead of lowering the bar silently.

## 5. Non-functional

- Local only; no telemetry.
- API key in `.env`, read only by the backend, never sent to the UI or logged.
- The README states that review text is sent to OpenRouter.
- Fictional data only in the repo.
- Python via uv only. Short modules, concise docstrings, no emojis in code or logs.

## 6. Risks and known limitations

| Risk | Mitigation |
|---|---|
| One theme per review loses information on mixed reviews | Documented; the eval set includes mixed reviews to show the effect. |
| Synthetic data is cleaner than real reviews | Hard cases are included deliberately; the generator model differs from the evaluated models; ~20 reviews hand-checked. |
| Strict JSON schema support differs by OpenRouter provider | Send `require_parameters: true`; bake-off records schema-validity rate per model. |
| Jev access and API shape | Resolved: `typesafe/jev-1.14` is available on OpenRouter through the Decisions API with the normal key; implemented in `analyzers/jev.py`. |
| Jev Router picks a different model per request | Candidate in the bake-off only; the actual model is stored per row. |
| Prompt injection inside reviews | Delimiting, instruction to ignore, enum-constrained output. Worst case is a wrong label. |
| In-memory job store is lost on restart | Acceptable for local use; documented. |
