"""Gemini API 連携（httpxでREST APIを直接呼ぶ）。

APIキーはサーバー側の環境変数でのみ保持し、フロントには渡さない。
無料枠のレート制限(429)や一時エラー(503)には1回だけリトライする。
"""

import json
import os
import re
import time

import httpx
from fastapi import HTTPException

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY が設定されていません。.env を確認してください。",
        )
    return key


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _generate(system: str, contents: list[dict], json_mode: bool = False) -> str:
    """generateContent を呼び、テキスト部分を返す。"""
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.8},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = f"{BASE_URL}/{_model()}:generateContent"
    headers = {"x-goog-api-key": _api_key()}

    last_error = ""
    for attempt in range(2):
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=60)
        except httpx.HTTPError as e:
            last_error = f"通信エラー: {e}"
            continue
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise HTTPException(502, "Geminiの応答形式が想定外でした。")
        if resp.status_code in (429, 500, 503) and attempt == 0:
            time.sleep(3)  # 無料枠のレート制限は少し待つと通ることが多い
            last_error = f"HTTP {resp.status_code}"
            continue
        detail = resp.json().get("error", {}).get("message", resp.text[:200]) \
            if resp.headers.get("content-type", "").startswith("application/json") \
            else resp.text[:200]
        raise HTTPException(502, f"Gemini APIエラー (HTTP {resp.status_code}): {detail}")

    raise HTTPException(502, f"Gemini APIに接続できませんでした（{last_error}）。少し待って再試行してください。")


def _parse_json(text: str) -> dict:
    """JSONモードでも稀にコードフェンス付きで返るため、剥がしてからパースする。"""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise HTTPException(502, "Geminiの応答をJSONとして解釈できませんでした。再試行してください。")


def _user_turn(text: str) -> dict:
    return {"role": "user", "parts": [{"text": text}]}


# ---------------------------------------------------------------- シナリオ生成

def generate_scenario_content(scenario: dict) -> dict:
    system = (
        "You are a content generator for an English speaking practice app for a "
        "Japanese learner (TOEIC ~890, weak at speaking). Output JSON only."
    )
    prompt = f"""Generate practice content for this scenario.

Scenario: {scenario['title_en']}
Situation: {scenario['situation']}
Learner role: {scenario['user_role']}
AI role: {scenario['ai_role']}
Level: {scenario['level']} (初級 = CEFR A2-B1, 中級 = B1-B2)

Return JSON with exactly this shape:
{{
  "phrases": [
    {{"en": "<key phrase the learner should master for this scenario, natural spoken English, 5-14 words>",
      "ja": "<自然な日本語訳>"}}
  ],
  "opening_line": "<the first thing the AI role would say to start the roleplay, 1-2 short sentences>"
}}

Rules:
- Exactly 7 phrases, ordered roughly in the order they would come up in the conversation.
- Phrases must be things the LEARNER (not the AI role) would say.
- Practical, high-frequency expressions. No obscure idioms.
"""
    content = _parse_json(_generate(system, [_user_turn(prompt)], json_mode=True))
    if not isinstance(content.get("phrases"), list) or not content.get("opening_line"):
        raise HTTPException(502, "シナリオ生成の結果が不完全でした。再試行してください。")
    return content


# ---------------------------------------------------------------- 会話

def _history_to_contents(messages: list[dict]) -> list[dict]:
    return [
        {"role": "model" if m["role"] == "ai" else "user",
         "parts": [{"text": m["text"]}]}
        for m in messages
    ]


def roleplay_reply(scenario: dict, messages: list[dict]) -> str:
    system = f"""You are playing a role in an English conversation practice roleplay.

Your role: {scenario['ai_role']}
The learner's role: {scenario['user_role']}
Situation: {scenario['situation']}

Rules:
- Stay in character. Natural spoken English only.
- Keep every reply SHORT: 1-2 sentences. This is spoken conversation practice.
- Level: {scenario['level']} learner (Japanese, TOEIC ~890 but weak at speaking). Use clear, natural phrasing.
- Do NOT correct the learner's mistakes during the conversation (feedback comes later). If a message is hard to understand, ask a natural clarifying question in character.
- Move the scene forward with questions or new information so the learner keeps talking.
- After about 8-10 exchanges, wrap the scene up naturally.
- Never use Japanese. Never break character or mention that you are an AI."""
    return _generate(system, _history_to_contents(messages)).strip()


def free_chat_reply(messages: list[dict]) -> str:
    system = """You are a friendly English conversation partner for a Japanese learner
(TOEIC ~890, weak at speaking) practicing free conversation.

Rules:
- Natural spoken English only. Never use Japanese.
- Keep every reply SHORT: 1-3 sentences, like a real chat.
- Always end with a question or a hook so the learner keeps talking.
- Do NOT correct mistakes during the conversation (feedback comes later).
- Be warm, curious, and encouraging. Vary topics naturally."""
    return _generate(system, _history_to_contents(messages)).strip()


# ---------------------------------------------------------------- フィードバック

def generate_feedback(scenario_title: str, messages: list[dict]) -> dict:
    transcript = "\n".join(
        f"{'AI' if m['role'] == 'ai' else 'Learner'}: {m['text']}" for m in messages
    )
    system = (
        "You are an experienced English speaking coach for Japanese learners. "
        "Analyze the learner's lines only. Output JSON only. "
        "All explanations must be in natural Japanese."
    )
    prompt = f"""以下は英会話練習（{scenario_title}）の会話ログです。Learnerの発話を分析してください。

{transcript}

Return JSON with exactly this shape:
{{
  "score": <0-100の総合スコア。文法・語彙・流暢さ・場面への適切さを総合評価>,
  "summary_ja": "<全体講評。良かった点に必ず触れつつ、2-3文で>",
  "good_points": ["<良かった点（日本語、1-3個）>"],
  "corrections": [
    {{"original": "<Learnerの実際の発話>",
      "corrected": "<修正版>",
      "explanation_ja": "<なぜ直すのか簡潔に>"}}
  ],
  "better_expressions": [
    {{"original": "<Learnerの発話（文法的には正しいが不自然/硬い表現）>",
      "improved": "<ネイティブらしい言い方>",
      "reason_ja": "<理由>"}}
  ],
  "fluency_comment_ja": "<流暢さ・会話の続け方についてのコメント、1-2文>"
}}

Rules:
- corrections は明確な誤りのみ（最大5個）。誤りがなければ空配列。
- better_expressions は最大3個。
- 発話が少ない場合もその範囲で誠実に評価する。励ましのトーンを保つ。"""
    fb = _parse_json(_generate(system, [_user_turn(prompt)], json_mode=True))
    if "score" not in fb or "summary_ja" not in fb:
        raise HTTPException(502, "フィードバック生成の結果が不完全でした。再試行してください。")
    fb["score"] = max(0, min(100, int(fb["score"])))
    return fb
