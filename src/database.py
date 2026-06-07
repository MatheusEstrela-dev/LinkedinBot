import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def _conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init():
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id       TEXT PRIMARY KEY,
                title    TEXT,
                company  TEXT,
                score    INTEGER,
                link     TEXT,
                seen_at  TEXT
            )
        """)


def seen(job_id: str) -> bool:
    with _conn() as con:
        row = con.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row is not None


def save(job: dict, score: int):
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO jobs (id, title, company, score, link, seen_at) VALUES (?,?,?,?,?,?)",
            (job["id"], job["title"], job["company"], score, job["link"], datetime.utcnow().isoformat()),
        )


def get_recent_jobs(limit: int = 10) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, title, company, score, link, seen_at FROM jobs ORDER BY seen_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "company": r[2], "score": r[3], "link": r[4], "seen_at": r[5]}
        for r in rows
    ]


def count_jobs() -> int:
    with _conn() as con:
        row = con.execute("SELECT COUNT(*) FROM jobs").fetchone()
    return row[0] if row else 0
