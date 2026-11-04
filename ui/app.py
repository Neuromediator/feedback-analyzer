"""Streamlit front end for the Feedback Analyzer."""

import time

import pandas as pd
import streamlit as st

import api_client as api

st.set_page_config(page_title="Feedback Analyzer", layout="wide")
st.session_state.setdefault("reviews_text", "")
st.session_state.setdefault("job", None)
st.session_state.setdefault("file_columns", None)
st.session_state.setdefault("notice", None)

SAVE_FIELDS = ("text", "score", "sentiment", "theme", "suggestion", "model")


def show_notice(key: str = "notice") -> None:
    """Show a one-time message stored by a callback or a previous run."""
    if st.session_state.get(key):
        kind, message = st.session_state[key]
        getattr(st, kind)(message)
        st.session_state[key] = None


# ---- callbacks ----


def load_file() -> None:
    upload = st.session_state.get("upload")
    if upload is None:
        st.session_state.notice = ("error", "Choose a file first.")
        return
    try:
        parsed = api.parse_file(upload.name, upload.getvalue(), st.session_state.get("file_column"))
    except api.ApiError as e:
        st.session_state.notice = ("error", str(e))
        return
    if parsed["columns"]:
        st.session_state.file_columns = parsed["columns"]
        st.session_state.notice = (
            "info",
            "Choose the column that holds the review text, then load again.",
        )
    else:
        st.session_state.file_columns = None
        st.session_state.reviews_text = "\n".join(parsed["reviews"])
        st.session_state.notice = (
            "success",
            f"Loaded {len(parsed['reviews'])} reviews into the text box.",
        )


def add_theme() -> None:
    name = st.session_state.new_theme
    try:
        api.add_theme(name)
        st.session_state.new_theme = ""
        st.session_state.notice = ("success", f"Added theme '{name.strip().lower()}'.")
    except api.ApiError as e:
        st.session_state.notice = ("error", str(e))


def delete_saved(review_id: int) -> None:
    try:
        api.delete_review(review_id)
    except api.ApiError as e:
        st.session_state.notice = ("error", str(e))


def save_results() -> None:
    ok = [r for r in st.session_state.job["results"] if r["status"] == "ok"]
    try:
        result = api.save_reviews([{k: r[k] for k in SAVE_FIELDS} for r in ok])
        st.session_state.save_notice = (
            "success",
            f"Saved {result['saved']}, skipped {result['skipped']} already saved.",
        )
    except api.ApiError as e:
        st.session_state.save_notice = ("error", str(e))


# ---- analysis ----


def watch_job(job_id: str) -> None:
    """Poll the job with a progress bar, then keep the finished job in session state."""
    bar = st.progress(0.0, text="Starting...")
    while True:
        job = api.get_job(job_id)
        text = f"{job['done']} / {job['total']} reviews analyzed"
        if job["stage"] == "suggesting":
            text += " - writing suggestions"
        bar.progress(min(job["done"] / max(job["total"], 1), 1.0), text=text)
        if job["status"] != "running":
            break
        time.sleep(0.4)
    bar.empty()
    st.session_state.job = job


def run_analysis(lines: list[str]) -> None:
    try:
        watch_job(api.create_job(lines))
    except api.ApiError as e:
        st.error(str(e))


def retry_failed(job_id: str) -> None:
    try:
        api.retry_job(job_id)
        watch_job(job_id)
    except api.ApiError as e:
        st.error(str(e))
        return
    st.rerun()


def show_results(job: dict) -> None:
    st.subheader("Results")
    if job["duplicates_removed"]:
        removed = job["duplicates_removed"]
        st.info(f"{removed} duplicate review{'s' if removed != 1 else ''} removed.")
    if job["error"]:
        st.error(job["error"])
    if job["failed"]:
        st.warning(f"{job['failed']} reviews failed.")
        if st.button("Retry failed"):
            retry_failed(job["id"])

    summary = job["summary"]
    if not summary["total"]:
        return
    cols = st.columns(5)
    cols[0].metric("Reviews", summary["total"])
    cols[1].metric("Average score", f"{summary['average_score']:.1f} / 5")
    cols[2].metric("Positive", f"{summary['percent_positive']}%")
    cols[3].metric("Most mentioned theme", summary["top_theme"] or "-")
    cols[4].metric("Top complaint", summary["top_complaint_theme"] or "No complaints")

    st.caption("Reviews per theme")
    st.bar_chart(pd.Series(summary["theme_counts"]), horizontal=True)

    choice = st.selectbox("Show reviews", ["All", "Positive", "Neutral", "Negative"])
    rows = [
        r
        for r in job["results"]
        if r["status"] == "ok" and (choice == "All" or r["sentiment"] == choice.lower())
    ]
    table = pd.DataFrame(
        rows, columns=["text", "score", "sentiment", "theme", "suggestion"]
    ).fillna("")
    st.dataframe(table, width="stretch", hide_index=True)
    st.button("Save to database", type="primary", on_click=save_results)
    show_notice("save_notice")


# ---- history ----


def show_history(themes: list[str]) -> None:
    st.header("Saved history")
    theme = st.selectbox("Filter by theme", ["All"] + themes, key="history_theme")
    try:
        rows = api.list_reviews(None if theme == "All" else theme)
    except api.ApiError as e:
        st.error(str(e))
        return
    if not rows:
        st.info("Nothing saved yet.")
        return
    st.caption(f"{len(rows)} saved reviews")
    widths = [5, 1, 2, 2.2, 5, 1.6]
    for col, label in zip(
        st.columns(widths), ["Review", "Score", "Sentiment", "Theme", "Suggestion", ""]
    ):
        col.markdown(f"**{label}**")
    for r in rows:
        c = st.columns(widths)
        c[0].write(r["text"])
        c[1].write(str(r["score"]))
        c[2].write(r["sentiment"])
        c[3].write(r["theme"])
        c[4].write(r["suggestion"] or "")
        c[5].button("Delete", key=f"del{r['id']}", on_click=delete_saved, args=(r["id"],))


# ---- page ----

st.title("Customer Feedback Analyzer")
st.write(
    "Paste reviews or load a file, then click Analyze to see how customers feel "
    "and what they keep complaining about."
)

try:
    themes = api.get_themes()
except api.ApiError as e:
    st.error(str(e))
    st.stop()

with st.sidebar:
    st.header("Themes")
    st.write(", ".join(themes))
    st.text_input("Add a theme", key="new_theme", placeholder="e.g. parking")
    st.button("Add theme", on_click=add_theme)

show_notice()

st.file_uploader(
    "Load a file (.txt, .csv, .json)", type=["txt", "csv", "json", "jsonl"], key="upload"
)
if st.session_state.file_columns:
    st.selectbox("Review column", st.session_state.file_columns, key="file_column")
st.button("Load into text box", on_click=load_file)

st.text_area("Reviews (one per line)", key="reviews_text", height=240)
lines = [line for line in st.session_state.reviews_text.splitlines() if line.strip()]
st.caption(f"{len(lines)} reviews in the text box (up to 100 per analysis)")

if st.button("Analyze", type="primary", disabled=not lines):
    run_analysis(lines)

if st.session_state.job:
    show_results(st.session_state.job)

show_history(themes)
