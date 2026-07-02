"""SQLiteによる永続化。

- scenario_cache: Geminiが生成したシナリオ内容（フレーズ等）のキャッシュ
- sessions: 練習履歴（ストリーク・統計の元データ）

日付はユーザーが日本在住のため Asia/Tokyo 基準で記録する
（RenderのサーバーはUTCなので、そのままだと日付がずれる）。
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("DB_PATH", "lingoflow.db")
JST = ZoneInfo("Asia/Tokyo")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenario_cache (
                scenario_id TEXT PRIMARY KEY,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT,
                mode        TEXT NOT NULL,
                score       INTEGER,
                feedback    TEXT,
                date_jst    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            """
        )


def get_cached_content(scenario_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT content FROM scenario_cache WHERE scenario_id = ?",
            (scenario_id,),
        ).fetchone()
    return json.loads(row["content"]) if row else None


def set_cached_content(scenario_id: str, content: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scenario_cache (scenario_id, content, created_at) "
            "VALUES (?, ?, ?)",
            (scenario_id, json.dumps(content, ensure_ascii=False),
             datetime.now(JST).isoformat()),
        )


def clear_cached_content(scenario_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM scenario_cache WHERE scenario_id = ?", (scenario_id,)
        )


def add_session(scenario_id: str | None, mode: str,
                score: int | None, feedback: dict | None) -> None:
    now = datetime.now(JST)
    with _conn() as conn:
        conn.execute(
            "INSERT INTO sessions (scenario_id, mode, score, feedback, date_jst, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                scenario_id,
                mode,
                score,
                json.dumps(feedback, ensure_ascii=False) if feedback else None,
                now.date().isoformat(),
                now.isoformat(),
            ),
        )


def _calc_streak(dates: list[str]) -> int:
    """練習した日付（降順・重複なし）から連続日数を数える。

    今日まだ練習していなくても、昨日までの連続が続いていればストリーク継続扱い。
    """
    if not dates:
        return 0
    today = datetime.now(JST).date()
    day_set = {datetime.fromisoformat(d).date() for d in dates}
    cursor = today if today in day_set else today - timedelta(days=1)
    streak = 0
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_stats() -> dict:
    with _conn() as conn:
        dates = [
            r["date_jst"]
            for r in conn.execute(
                "SELECT DISTINCT date_jst FROM sessions ORDER BY date_jst DESC"
            )
        ]
        total = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
        today = conn.execute(
            "SELECT COUNT(*) AS c FROM sessions WHERE date_jst = ?",
            (datetime.now(JST).date().isoformat(),),
        ).fetchone()["c"]
        completed = {
            r["scenario_id"]: r["c"]
            for r in conn.execute(
                "SELECT scenario_id, COUNT(*) AS c FROM sessions "
                "WHERE scenario_id IS NOT NULL GROUP BY scenario_id"
            )
        }
        recent = [
            {
                "scenario_id": r["scenario_id"],
                "mode": r["mode"],
                "score": r["score"],
                "date": r["date_jst"],
                "created_at": r["created_at"],
            }
            for r in conn.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT 20"
            )
        ]
    return {
        "streak": _calc_streak(dates),
        "total_sessions": total,
        "today_sessions": today,
        "completed_by_scenario": completed,
        "recent": recent,
    }
