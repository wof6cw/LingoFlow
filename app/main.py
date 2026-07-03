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


@app.get("/api/scenarios")
def list_scenarios():
    stats = db.get_stats()
    return {
        "categories": CATEGORIES,
        "scenarios": [
            {**s, "completed_count": stats["completed_by_scenario"].get(s["id"], 0)}
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
        reply = gemini.roleplay_reply(scenario, messages, req.difficulty)
        return {"reply": reply, "reply_ja": None}
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


@app.post("/api/sessions")
def record_session(req: SessionRequest):
    db.add_session(req.scenario_id, req.mode, req.score, req.feedback, req.difficulty)
    return {"ok": True, "stats": db.get_stats()}


@app.get("/api/stats")
def stats():
    return db.get_stats()


# 静的ファイル（フロントエンド）。APIルート定義の後にマウントする。
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
