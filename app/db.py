"""永続化層。ローカルではSQLiteファイル、本番ではTurso（libsql）を使う。

- scenario_cache: Geminiが生成したシナリオ内容（フレーズ等）のキャッシュ
- sessions: 練習履歴（ストリーク・統計・会話全文の元データ）

TURSO_DATABASE_URL / TURSO_AUTH_TOKEN が設定されていればTursoへ、
未設定ならローカルのSQLiteファイル（DB_PATH）へ接続する。
libsql_client.dbapi2.connect() はsqlite3.connect()とほぼ同じ
インターフェースなので、クエリ本体はどちらの接続でも共通で書ける
（ただしRow工場だけは接続先に応じて使い分ける必要がある）。

日付はユーザーが日本在住のため Asia/Tokyo 基準で記録する
（RenderのサーバーはUTCなので、そのままだと日付がずれる）。
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("DB_PATH", "lingoflow.db")
TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").strip() or None
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip() or None
JST = ZoneInfo("Asia/Tokyo")


def using_turso() -> bool:
    return TURSO_URL is not None


def _connect():
    if TURSO_URL:
        # Turso使用時のみ読み込む。libsql_clientはPython 3.14未対応の内部importを
        # 含むため、未使用の環境（Turso未設定）でアプリ全体が起動不能にならないよう
        # 遅延importにしている。
        from libsql_client import dbapi2 as libsql
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
        conn.row_factory = libsql.Row
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _conn():
    """コミットとクローズまで面倒を見る接続コンテキスト。

    sqlite3の `with conn:` はコミットするだけでクローズしないため、
    明示的に close してWindowsのファイルロック残りや接続リークを防ぐ。
    """
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _columns(conn, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]


def init_db() -> None:
    with _conn() as conn:
        # v1.1: キャッシュを（シナリオ×難易度）キーに移行。
        # キャッシュは再生成可能なので旧テーブルは作り直すだけでよい。
        cache_cols = _columns(conn, "scenario_cache")
        if cache_cols and "difficulty" not in cache_cols:
            conn.execute("DROP TABLE scenario_cache")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenario_cache (
                scenario_id TEXT NOT NULL,
                difficulty  TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                PRIMARY KEY (scenario_id, difficulty)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id TEXT,
                mode        TEXT NOT NULL,
                score       INTEGER,
                feedback    TEXT,
                difficulty  TEXT,
                transcript  TEXT,
                date_jst    TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS expressions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                en          TEXT NOT NULL UNIQUE,
                note        TEXT,
                source      TEXT NOT NULL,
                scenario_id TEXT,
                count       INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT NOT NULL
            );
            """
        )
        # 既存テーブルへの追加カラム（データは保持したままマイグレーション）
        session_cols = _columns(conn, "sessions")
        if "difficulty" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN difficulty TEXT")
        if "transcript" not in session_cols:
            conn.execute("ALTER TABLE sessions ADD COLUMN transcript TEXT")


def get_cached_content(scenario_id: str, difficulty: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT content FROM scenario_cache WHERE scenario_id = ? AND difficulty = ?",
            (scenario_id, difficulty),
        ).fetchone()
    return json.loads(row["content"]) if row else None


def set_cached_content(scenario_id: str, difficulty: str, content: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scenario_cache "
            "(scenario_id, difficulty, content, created_at) VALUES (?, ?, ?, ?)",
            (scenario_id, difficulty, json.dumps(content, ensure_ascii=False),
             datetime.now(JST).isoformat()),
        )


def clear_cached_content(scenario_id: str, difficulty: str) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM scenario_cache WHERE scenario_id = ? AND difficulty = ?",
            (scenario_id, difficulty),
        )


def get_cached_levels() -> dict[str, list[str]]:
    """シナリオIDごとの生成済み難易度一覧（UIで「生成済み」を示すために使う）。"""
    result: dict[str, list[str]] = {}
    with _conn() as conn:
        for r in conn.execute("SELECT scenario_id, difficulty FROM scenario_cache"):
            result.setdefault(r["scenario_id"], []).append(r["difficulty"])
    return result


def upsert_expression(en: str, note: str | None, source: str,
                      scenario_id: str | None) -> None:
    """フィードバック由来の表現を蓄積する。同じ表現が再登場したら頻度を上げる。"""
    now = datetime.now(JST).isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM expressions WHERE en = ?", (en,)).fetchone()
        if row:
            conn.execute(
                "UPDATE expressions SET count = count + 1, created_at = ? WHERE id = ?",
                (now, row["id"]))
        else:
            conn.execute(
                "INSERT INTO expressions (en, note, source, scenario_id, count, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (en, note, source, scenario_id, now))


def get_expressions(limit: int = 200) -> list[dict]:
    with _conn() as conn:
        return [
            {
                "id": r["id"],
                "en": r["en"],
                "note": r["note"],
                "source": r["source"],
                "scenario_id": r["scenario_id"],
                "count": r["count"],
                "created_at": r["created_at"],
            }
            for r in conn.execute(
                "SELECT * FROM expressions ORDER BY count DESC, id DESC LIMIT ?",
                (limit,))
        ]


def add_session(scenario_id: str | None, mode: str, score: int | None,
                feedback: dict | None, difficulty: str | None = None,
                transcript: list[dict] | None = None) -> int:
    now = datetime.now(JST)
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions "
            "(scenario_id, mode, score, feedback, difficulty, transcript, date_jst, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scenario_id,
                mode,
                score,
                json.dumps(feedback, ensure_ascii=False) if feedback else None,
                difficulty,
                json.dumps(transcript, ensure_ascii=False) if transcript else None,
                now.date().isoformat(),
                now.isoformat(),
            ),
        )
        return cur.lastrowid


def get_session(session_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "scenario_id": row["scenario_id"],
        "mode": row["mode"],
        "score": row["score"],
        "difficulty": row["difficulty"],
        "feedback": json.loads(row["feedback"]) if row["feedback"] else None,
        "transcript": json.loads(row["transcript"]) if row["transcript"] else [],
        "date": row["date_jst"],
        "created_at": row["created_at"],
    }


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


def _excerpt(transcript_json: str | None, limit: int = 40) -> str | None:
    if not transcript_json:
        return None
    messages = json.loads(transcript_json)
    first_user = next((m["text"] for m in messages if m.get("role") == "user"), None)
    if not first_user:
        return None
    return first_user if len(first_user) <= limit else first_user[:limit] + "…"


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
                "id": r["id"],
                "scenario_id": r["scenario_id"],
                "mode": r["mode"],
                "score": r["score"],
                "difficulty": r["difficulty"],
                "excerpt": _excerpt(r["transcript"]),
                "date": r["date_jst"],
                "created_at": r["created_at"],
            }
            for r in conn.execute(
                "SELECT * FROM sessions ORDER BY id DESC LIMIT 30"
            )
        ]
    return {
        "streak": _calc_streak(dates),
        "total_sessions": total,
        "today_sessions": today,
        "completed_by_scenario": completed,
        "recent": recent,
    }
