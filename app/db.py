"""SQLite storage for saved reviews and the theme list."""

import re
import sqlite3
from contextlib import contextmanager

from app.ingest import text_hash
from app.schemas import SaveItem

DEFAULT_THEMES = [
    "food",
    "service",
    "wait",
    "price",
    "cleanliness",
    "ambiance",
    "portions",
    "other",
]
THEME_RE = re.compile(r"^[a-z][a-z-]{1,23}$")

SCHEMA = """
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
"""


class ThemeExists(ValueError):
    pass


class Db:
    def __init__(self, path: str):
        self.path = path
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.executemany(
                "INSERT OR IGNORE INTO themes (name, is_default) VALUES (?, 1)",
                [(t,) for t in DEFAULT_THEMES],
            )

    @contextmanager
    def _connect(self):
        """Open a connection; commit on success, roll back on error, always close."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def themes(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM themes ORDER BY is_default DESC, rowid"
            ).fetchall()
        return [r["name"] for r in rows]

    def add_theme(self, name: str) -> None:
        if not THEME_RE.match(name):
            raise ValueError("Theme must be 2-24 lowercase letters or hyphens, with no spaces.")
        try:
            with self._connect() as conn:
                conn.execute("INSERT INTO themes (name) VALUES (?)", (name,))
        except sqlite3.IntegrityError:
            raise ThemeExists(f"Theme '{name}' already exists.") from None

    def save_reviews(self, items: list[SaveItem]) -> tuple[int, int]:
        """Insert reviews, skipping texts already saved. Returns (saved, skipped)."""
        saved = 0
        with self._connect() as conn:
            for item in items:
                cur = conn.execute(
                    "INSERT INTO reviews (text, text_hash, score, sentiment, theme, suggestion, model)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(text_hash) DO NOTHING",
                    (
                        item.text,
                        text_hash(item.text),
                        item.score,
                        item.sentiment,
                        item.theme,
                        item.suggestion,
                        item.model,
                    ),
                )
                saved += cur.rowcount
        return saved, len(items) - saved

    def list_reviews(self, theme: str | None = None) -> list[dict]:
        sql = "SELECT id, text, score, sentiment, theme, suggestion, model, created_at FROM reviews"
        params: tuple = ()
        if theme:
            sql += " WHERE theme = ?"
            params = (theme,)
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", params)]

    def delete_review(self, review_id: int) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,)).rowcount > 0

    def delete_all(self) -> int:
        """Delete every saved review and return how many were removed."""
        with self._connect() as conn:
            return conn.execute("DELETE FROM reviews").rowcount
