"""LingoFlow — AIスピーキング練習アプリ バックエンド。

エンドポイント:
  GET  /api/scenarios                 シナリオ一覧＋統計（学習パス表示用）
  POST /api/scenarios/{id}/content    シナリオ内容の取得（Gemini生成、SQLiteにキャッシュ）
  POST /api/chat                      ロールプレイ / フリートークの返答
  POST /api/feedback                  会話ログから総合フィードバック生成
  POST /api/sessions                  練習セッションの記録（履歴・ストリーク用）
  GET  /api/stats                     統計（ストリーク・履歴）
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # 環境変数の読み込みは他モジュールのimportより先に行う

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, gemini
from .expressions import EXPRESSION_CATEGORIES
from .scenarios import CATEGORIES, SCENARIOS, get_scenario

app = FastAPI(title="LingoFlow")
db.init_db()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


DIFFICULTY_PATTERN = "^(beginner|intermediate|advanced)$"


class Message(BaseModel):
    role: str = Field(pattern="^(user|ai)$")
    text: str


class ChatRequest(BaseModel):
    scenario_id: str | None = None  # None ならフリートーク
    messages: list[Message]
    difficulty: str = Field(default="intermediate", pattern=DIFFICULTY_PATTERN)


class FeedbackRequest(BaseModel):
    scenario_id: str | None = None
    messages: list[Message]
    difficulty: str = Field(default="intermediate", pattern=DIFFICULTY_PATTERN)


class SessionRequest(BaseModel):
    scenario_id: str | None = None
    mode: str = Field(pattern="^(scenario|free_talk)$")
    score: int | None = None
    feedback: dict | None = None
    difficulty: str | None = Field(default=None, pattern=DIFFICULTY_PATTERN)
    transcript: list[Message] | None = None


@app.get("/api/scenarios")
def list_scenarios():
    stats = db.get_stats()
    cached = db.get_cached_levels()
    return {
        "categories": CATEGORIES,
        "scenarios": [
            {
                **s,
                "completed_count": stats["completed_by_scenario"].get(s["id"], 0),
                "cached_levels": cached.get(s["id"], []),
            }
            for s in sorted(SCENARIOS, key=lambda s: s["order"])
        ],
        "stats": stats,
    }


@app.post("/api/scenarios/{scenario_id}/content")
def scenario_content(scenario_id: str, difficulty: str = "intermediate",
                     refresh: bool = False):
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(404, "シナリオが見つかりません。")
    if difficulty not in gemini.DIFFICULTY:
        raise HTTPException(422, "difficulty は beginner / intermediate / advanced のいずれかです。")
    if refresh:
        db.clear_cached_content(scenario_id, difficulty)
    content = None if refresh else db.get_cached_content(scenario_id, difficulty)
    if content is None:
        content = gemini.generate_scenario_content(scenario, difficulty)
        db.set_cached_content(scenario_id, difficulty, content)
    return {"scenario": scenario, "content": content}


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(400, "messages が空です。")
    messages = [m.model_dump() for m in req.messages]
    if req.scenario_id:
        scenario = get_scenario(req.scenario_id)
        if not scenario:
            raise HTTPException(404, "シナリオが見つかりません。")
        result = gemini.roleplay_reply(scenario, messages, req.difficulty)
    else:
        result = gemini.free_chat_reply(messages, req.difficulty)
    return {"reply": result["english"], "reply_ja": result["japanese"]}


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    user_lines = [m for m in req.messages if m.role == "user"]
    if not user_lines:
        raise HTTPException(400, "あなたの発話がまだありません。少し会話してからフィードバックを受けてください。")
    scenario = get_scenario(req.scenario_id) if req.scenario_id else None
    title = scenario["title_en"] if scenario else "Free Talk"
    return gemini.generate_feedback(
        title, [m.model_dump() for m in req.messages], req.difficulty)


def _collect_expressions(feedback: dict, scenario_id: str | None) -> None:
    """フィードバック中の修正・自然な言い回しを表現集に自動蓄積する。"""
    for c in (feedback.get("corrections") or [])[:5]:
        en = str(c.get("corrected") or "").strip()
        if en:
            db.upsert_expression(en, str(c.get("explanation_ja") or "").strip() or None,
                                 "correction", scenario_id)
    for b in (feedback.get("better_expressions") or [])[:3]:
        en = str(b.get("improved") or "").strip()
        if en:
            db.upsert_expression(en, str(b.get("reason_ja") or "").strip() or None,
                                 "better", scenario_id)


@app.post("/api/sessions")
def record_session(req: SessionRequest):
    transcript = [m.model_dump() for m in req.transcript] if req.transcript else None
    session_id = db.add_session(
        req.scenario_id, req.mode, req.score, req.feedback, req.difficulty, transcript)
    if req.feedback:
        try:
            _collect_expressions(req.feedback, req.scenario_id)
        except Exception:
            pass  # 表現集への蓄積失敗でセッション記録自体は失敗させない
    return {"ok": True, "session_id": session_id, "stats": db.get_stats()}


@app.get("/api/expressions")
def expressions():
    return {"categories": EXPRESSION_CATEGORIES, "collected": db.get_expressions()}


@app.get("/api/sessions/{session_id}")
def session_detail(session_id: int):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "セッションが見つかりません。")
    return session


@app.get("/api/stats")
def stats():
    return db.get_stats()


# 静的ファイル（フロントエンド）。APIルート定義の後にマウントする。
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_stale_static(request, call_next):
    """静的ファイルは毎回ETagで再検証させる。

    デプロイ後に古いapp.jsと新しいindex.htmlが混在すると
    フロントが壊れるため（実際に起きた）、no-cacheで防ぐ。
    ファイルが小さいので304検証のコストは無視できる。
    """
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-cache"
    return response
