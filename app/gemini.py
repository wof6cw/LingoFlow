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

# 難易度ごとの生成調整。シナリオ×レベルの組み合わせは
# このパラメータをプロンプトに埋め込むだけで実現する（個別執筆なし）。
DIFFICULTY = {
    "beginner": {
        "label": "初級",
        "cefr": "CEFR A2",
        "speaking_style": (
            "Use simple, high-frequency vocabulary and short sentences (roughly 10 "
            "words or fewer). Avoid idioms and uncommon phrasal verbs. Speak clearly "
            "and patiently, like talking to a beginner learner."
        ),
        "phrase_style": (
            "Very common, simple expressions with basic sentence patterns, "
            "4-9 words each. No idioms."
        ),
        "feedback_style": (
            "初級者向け: 基本的な文法・語彙の誤りに絞って指摘し、特に優しく励ますトーンで。"
            "細かい不自然さまでは指摘しすぎない。"
        ),
    },
    "intermediate": {
        "label": "中級",
        "cefr": "CEFR B1-B2",
        "speaking_style": (
            "Use clear, natural phrasing at a standard conversational level. "
            "Common idioms are fine if the meaning is guessable from context."
        ),
        "phrase_style": (
            "Practical, high-frequency expressions, 5-14 words each. "
            "No obscure idioms."
        ),
        "feedback_style": (
            "中級者向け: 明確な誤りの修正に加えて、より自然な言い回しもバランスよく提案する。"
        ),
    },
    "advanced": {
        "label": "上級",
        "cefr": "CEFR B2-C1",
        "speaking_style": (
            "Speak like a native at a natural pace: use idioms, phrasal verbs, and "
            "indirect or nuanced phrasing where a native speaker naturally would."
        ),
        "phrase_style": (
            "Natural, native-like expressions including useful idioms and "
            "softening/hedging phrases, 5-16 words each."
        ),
        "feedback_style": (
            "上級者向け: 誤りの修正よりも、よりネイティブらしい自然な言い回し・"
            "ニュアンス・レジスター（丁寧さの度合い）の提案を重視する。"
        ),
    },
}


def _difficulty(key: str | None) -> dict:
    return DIFFICULTY.get(key or "", DIFFICULTY["intermediate"])


def _api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY が設定されていません。.env を確認してください。",
        )
    return key


def _models() -> list[str]:
    """試行順のモデル一覧。混雑・レート制限時はフォールバックモデルも試す。"""
    primary = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    fallback = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
    return [primary] if fallback == primary else [primary, fallback]


def _generate(system: str, contents: list[dict], json_mode: bool = False) -> str:
    """generateContent を呼び、テキスト部分を返す。

    無料枠では一時的な混雑(503)・レート制限(429)が起きやすいため、
    プライマリモデルで2回試した後、フォールバックモデルでも試す。
    """
    body: dict = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.8},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"

    headers = {"x-goog-api-key": _api_key()}
    last_error = ""
    for model in _models():
        url = f"{BASE_URL}/{model}:generateContent"
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
            if resp.status_code in (429, 500, 503):
                last_error = f"HTTP {resp.status_code} ({model})"
                if attempt == 0:
                    time.sleep(10)  # 少し待つと通ることが多い
                continue  # 2回失敗したら次のモデルへ
            detail = resp.json().get("error", {}).get("message", resp.text[:200]) \
                if resp.headers.get("content-type", "").startswith("application/json") \
                else resp.text[:200]
            raise HTTPException(502, f"Gemini APIエラー (HTTP {resp.status_code}): {detail}")
        
        print(f"\n⚠️ すべてのモデルが全滅しました。最後のエラー: {last_error}\n")

    raise HTTPException(
        502, f"Gemini APIが混雑しています（{last_error}）。少し待って再試行してください。")


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

def generate_scenario_content(scenario: dict, difficulty: str = "intermediate") -> dict:
    d = _difficulty(difficulty)
    system = (
        "You are a content generator for an English speaking practice app for a "
        "Japanese learner (TOEIC ~890, weak at speaking). Output JSON only."
    )
    prompt = f"""Generate practice content for this scenario.

Scenario: {scenario['title_en']}
Situation: {scenario['situation']}
Learner role: {scenario['user_role']}
AI role: {scenario['ai_role']}
Learner level: {d['label']} ({d['cefr']})

Return JSON with exactly this shape:
{{
  "phrases": [
    {{"en": "<key phrase the learner should master for this scenario, natural spoken English>",
      "ja": "<自然な日本語訳>"}}
  ],
  "opening_line": "<the first thing the AI role would say to start the roleplay, 1-2 short sentences, matched to the learner level>",
  "opening_line_ja": "<opening_lineの自然な日本語訳>"
}}

Rules:
- Exactly 7 phrases, ordered roughly in the order they would come up in the conversation.
- Phrases must be things the LEARNER (not the AI role) would say.
- Phrase style for this level: {d['phrase_style']}
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


_TRANSLATED_REPLY_FORMAT = """
Output format: JSON only, exactly this shape:
{"english": "<your reply in English>", "japanese": "<そのreplyの自然な日本語訳>"}"""


def _chat_reply(system: str, messages: list[dict]) -> dict:
    """英語の返答と日本語訳を1回の呼び出しで生成する共通処理。

    ロールプレイ・フリートーク両方の会話返答から呼ばれる。
    戻り値: {"english": str, "japanese": str | None}
    """
    text = _generate(system, _history_to_contents(messages), json_mode=True)
    try:
        data = _parse_json(text)
    except HTTPException:
        data = {}
    english = str(data.get("english") or "").strip()
    if not english:
        # JSONで返らなかった場合は本文をそのまま英語返答として扱う（訳なし）
        return {"english": text.strip(), "japanese": None}
    japanese = str(data.get("japanese") or "").strip() or None
    return {"english": english, "japanese": japanese}


def roleplay_reply(scenario: dict, messages: list[dict],
                   difficulty: str = "intermediate") -> dict:
    d = _difficulty(difficulty)
    system = f"""You are playing a role in an English conversation practice roleplay.

Your role: {scenario['ai_role']}
The learner's role: {scenario['user_role']}
Situation: {scenario['situation']}

Rules:
- Stay in character. Natural spoken English only in your "english" reply.
- Keep every reply SHORT: 1-2 sentences. This is spoken conversation practice.
- Learner level: {d['label']} ({d['cefr']}), a Japanese learner (TOEIC ~890 but weak at speaking).
- Language style for this level: {d['speaking_style']}
- Do NOT correct the learner's mistakes during the conversation (feedback comes later). If a message is hard to understand, ask a natural clarifying question in character.
- Move the scene forward with questions or new information so the learner keeps talking.
- After about 8-10 exchanges, wrap the scene up naturally.
- Never break character or mention that you are an AI.
{_TRANSLATED_REPLY_FORMAT}"""
    return _chat_reply(system, messages)


def free_chat_reply(messages: list[dict], difficulty: str = "intermediate") -> dict:
    """フリートークの返答。英語の返答と日本語訳を1回の呼び出しで生成する。"""
    d = _difficulty(difficulty)
    system = f"""You are a friendly English conversation partner for a Japanese learner
(TOEIC ~890, weak at speaking) practicing free conversation.

Rules for your "english" reply:
- Natural spoken English. Keep it SHORT: 1-3 sentences, like a real chat.
- Learner level: {d['label']} ({d['cefr']}). Language style: {d['speaking_style']}
- Always end with a question or a hook so the learner keeps talking.
- Do NOT correct mistakes during the conversation (feedback comes later).
- Be warm, curious, and encouraging. Vary topics naturally.
{_TRANSLATED_REPLY_FORMAT}"""
    return _chat_reply(system, messages)


# ---------------------------------------------------------------- フィードバック

def generate_feedback(scenario_title: str, messages: list[dict],
                      difficulty: str = "intermediate") -> dict:
    d = _difficulty(difficulty)
    transcript = "\n".join(
        f"{'AI' if m['role'] == 'ai' else 'Learner'}: {m['text']}" for m in messages
    )
    system = (
        "You are an experienced English speaking coach for Japanese learners. "
        "Analyze the learner's lines only. Output JSON only. "
        "All explanations must be in natural Japanese."
    )
    prompt = f"""以下は英会話練習（{scenario_title}、レベル: {d['label']}）の会話ログです。Learnerの発話を分析してください。

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
- レベルに応じた指摘方針: {d['feedback_style']}
- 発話が少ない場合もその範囲で誠実に評価する。励ましのトーンを保つ。"""
    fb = _parse_json(_generate(system, [_user_turn(prompt)], json_mode=True))
    if "score" not in fb or "summary_ja" not in fb:
        raise HTTPException(502, "フィードバック生成の結果が不完全でした。再試行してください。")
    fb["score"] = max(0, min(100, int(fb["score"])))
    return fb
