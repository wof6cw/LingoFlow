"""シナリオのシード定義。

フレーズやロールプレイの台詞そのものはGeminiが動的に生成し、
ここでは「場面の設定」だけを持つ。シナリオを増やすときは
SCENARIOS にエントリを追加するだけでよい。
"""

CATEGORIES = [
    {"id": "basics", "title_ja": "日常会話", "icon": "💬"},
    {"id": "travel", "title_ja": "旅行", "icon": "✈️"},
    {"id": "career", "title_ja": "キャリア", "icon": "💼"},
]

SCENARIOS = [
    {
        "id": "daily-smalltalk",
        "category": "basics",
        "order": 1,
        "title_ja": "スモールトーク",
        "title_en": "Small Talk",
        "icon": "☕",
        "level": "初級",
        "description_ja": "職場の同僚と休憩室で交わす気軽な雑談。あいさつ・近況・週末の話題など。",
        "situation": (
            "Casual small talk in the office break room. The user is chatting with "
            "a friendly coworker about the weekend, weather, and daily life."
        ),
        "ai_role": "a friendly coworker named Sam",
        "user_role": "an office worker taking a coffee break",
    },
    {
        "id": "travel-airport",
        "category": "travel",
        "order": 2,
        "title_ja": "空港でチェックイン",
        "title_en": "Airport Check-in",
        "icon": "🛫",
        "level": "初級",
        "description_ja": "国際線のチェックインカウンターで搭乗手続き。荷物・座席・搭乗ゲートの確認。",
        "situation": (
            "Checking in for an international flight at the airport. The user needs to "
            "check in, drop off baggage, choose a seat, and confirm the boarding gate."
        ),
        "ai_role": "an airline check-in counter agent",
        "user_role": "a traveler checking in for an international flight",
    },
    {
        "id": "travel-restaurant",
        "category": "travel",
        "order": 3,
        "title_ja": "レストランで注文",
        "title_en": "At a Restaurant",
        "icon": "🍽️",
        "level": "初級",
        "description_ja": "海外のレストランで席の案内から注文、会計まで。おすすめを聞いたり要望を伝えたり。",
        "situation": (
            "Dining at a restaurant abroad. The user is seated, asks about the menu and "
            "recommendations, orders food and drinks, and asks for the check."
        ),
        "ai_role": "a welcoming restaurant server",
        "user_role": "a customer dining at the restaurant",
    },
    {
        "id": "career-interview",
        "category": "career",
        "order": 4,
        "title_ja": "英語面接",
        "title_en": "Job Interview",
        "icon": "🤝",
        "level": "中級",
        "description_ja": "外資系企業の採用面接。自己紹介・強み・経験・志望動機を英語で伝える。",
        "situation": (
            "A job interview at a global company. The interviewer asks about the user's "
            "background, strengths, past experience, and motivation for applying."
        ),
        "ai_role": "a professional but friendly hiring manager",
        "user_role": "a job candidate being interviewed",
    },
    {
        "id": "career-meeting",
        "category": "career",
        "order": 5,
        "title_ja": "ビジネス会議",
        "title_en": "Business Meeting",
        "icon": "📊",
        "level": "中級",
        "description_ja": "プロジェクトの進捗会議。状況報告・意見交換・次のアクションの確認。",
        "situation": (
            "A project status meeting at work. The user reports progress, discusses an "
            "issue, exchanges opinions, and agrees on next steps with a colleague."
        ),
        "ai_role": "a project manager leading the meeting",
        "user_role": "a team member reporting on their tasks",
    },
]


def get_scenario(scenario_id: str) -> dict | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)
