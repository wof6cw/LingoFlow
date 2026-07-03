"""シナリオのシード定義。

フレーズやロールプレイの台詞そのものはGeminiが動的に生成し、
ここでは「場面の設定」だけを持つ。シナリオを増やすときは
SCENARIOS にエントリを追加するだけでよい。

level はそのシナリオの推奨レベル（開始画面のレベル選択の初期値）。
ユーザーは開始前に 初級/中級/上級 を自由に切り替えられる。
"""

CATEGORIES = [
    {"id": "basics", "title_ja": "基礎", "icon": "🌱"},
    {"id": "travel", "title_ja": "旅行", "icon": "✈️"},
    {"id": "daily", "title_ja": "日常生活", "icon": "🏠"},
    {"id": "work", "title_ja": "仕事", "icon": "💼"},
    {"id": "trouble", "title_ja": "トラブル対応", "icon": "🚨"},
]

SCENARIOS = [
    # ---------------------------------------------------------------- 基礎
    {
        "id": "basics-selfintro",
        "category": "basics",
        "order": 1,
        "title_ja": "自己紹介",
        "title_en": "Introducing Yourself",
        "icon": "🙋",
        "level": "beginner",
        "description_ja": "国際交流イベントで初対面の人に自己紹介。名前・仕事・趣味・出身地を伝え、相手にも質問する。",
        "situation": (
            "Meeting someone new at an international meetup event. The user introduces "
            "themselves (name, job, hobbies, hometown) and asks the other person "
            "similar questions to keep the conversation going."
        ),
        "ai_role": "a friendly participant at an international meetup",
        "user_role": "a participant meeting someone for the first time",
    },
    {
        "id": "daily-smalltalk",
        "category": "basics",
        "order": 2,
        "title_ja": "スモールトーク",
        "title_en": "Small Talk",
        "icon": "💬",
        "level": "beginner",
        "description_ja": "職場の同僚と休憩室で交わす気軽な雑談。あいさつ・近況・週末の話題など。",
        "situation": (
            "Casual small talk in the office break room. The user is chatting with "
            "a friendly coworker about the weekend, weather, and daily life."
        ),
        "ai_role": "a friendly coworker named Sam",
        "user_role": "an office worker taking a coffee break",
    },
    {
        "id": "basics-clarify",
        "category": "basics",
        "order": 3,
        "title_ja": "聞き返し・言い換え",
        "title_en": "Asking for Clarification",
        "icon": "🔄",
        "level": "beginner",
        "description_ja": "相手の英語が聞き取れないときの対処法を練習。もう一度言ってもらう・ゆっくり話してもらう・別の言い方を頼む。",
        "situation": (
            "A conversation where the other speaker sometimes talks fast or uses "
            "idioms. The user practices asking them to repeat, slow down, or rephrase, "
            "and confirms their own understanding (e.g. 'So you mean ...?')."
        ),
        "ai_role": (
            "a chatty native-speaker acquaintance who naturally talks a bit fast and "
            "occasionally uses idioms, but is happy to rephrase when asked"
        ),
        "user_role": "a learner keeping the conversation going while asking for clarification",
    },
    # ---------------------------------------------------------------- 旅行
    {
        "id": "travel-airport",
        "category": "travel",
        "order": 4,
        "title_ja": "空港でチェックイン",
        "title_en": "Airport Check-in",
        "icon": "🛫",
        "level": "beginner",
        "description_ja": "国際線のチェックインカウンターで搭乗手続き。荷物・座席・搭乗ゲートの確認。",
        "situation": (
            "Checking in for an international flight at the airport. The user needs to "
            "check in, drop off baggage, choose a seat, and confirm the boarding gate."
        ),
        "ai_role": "an airline check-in counter agent",
        "user_role": "a traveler checking in for an international flight",
    },
    {
        "id": "travel-hotel",
        "category": "travel",
        "order": 5,
        "title_ja": "ホテルのチェックイン",
        "title_en": "Hotel Check-in",
        "icon": "🏨",
        "level": "beginner",
        "description_ja": "ホテルのフロントでチェックイン。予約の確認、部屋の希望、朝食やWi-Fiなど設備の質問。",
        "situation": (
            "Checking in at a hotel front desk. The user confirms their reservation, "
            "mentions room preferences, and asks about breakfast, Wi-Fi, and facilities."
        ),
        "ai_role": "a polite hotel front desk clerk",
        "user_role": "a guest checking in with a reservation",
    },
    {
        "id": "travel-directions",
        "category": "travel",
        "order": 6,
        "title_ja": "道案内を尋ねる",
        "title_en": "Asking for Directions",
        "icon": "🗺️",
        "level": "beginner",
        "description_ja": "旅行先の街で現地の人に道を尋ねる。行き方の確認、所要時間、目印の聞き取り。",
        "situation": (
            "Lost in a foreign city, the user asks a local for directions to a train "
            "station and a museum, confirms the route and landmarks, and asks how long "
            "it takes on foot."
        ),
        "ai_role": "a helpful local resident on the street",
        "user_role": "a tourist trying to find their way",
    },
    # ---------------------------------------------------------------- 日常生活
    {
        "id": "travel-restaurant",
        "category": "daily",
        "order": 7,
        "title_ja": "レストランで注文",
        "title_en": "At a Restaurant",
        "icon": "🍽️",
        "level": "beginner",
        "description_ja": "海外のレストランで席の案内から注文、会計まで。おすすめを聞いたり要望を伝えたり。",
        "situation": (
            "Dining at a restaurant abroad. The user is seated, asks about the menu and "
            "recommendations, orders food and drinks, and asks for the check."
        ),
        "ai_role": "a welcoming restaurant server",
        "user_role": "a customer dining at the restaurant",
    },
    {
        "id": "daily-cafe",
        "category": "daily",
        "order": 8,
        "title_ja": "カフェで注文",
        "title_en": "Ordering at a Café",
        "icon": "☕",
        "level": "beginner",
        "description_ja": "カフェでドリンクとフードを注文。サイズ・カスタマイズ・店内かテイクアウトかのやり取り。",
        "situation": (
            "Ordering at a busy café. The user orders a drink and a snack, answers "
            "questions about size and customization, and chooses for here or to go."
        ),
        "ai_role": "a cheerful café barista",
        "user_role": "a customer ordering at the counter",
    },
    {
        "id": "daily-phone-reservation",
        "category": "daily",
        "order": 9,
        "title_ja": "電話で予約",
        "title_en": "Making a Reservation by Phone",
        "icon": "📞",
        "level": "intermediate",
        "description_ja": "レストランに電話して席を予約。日時・人数・要望を伝え、聞き取りづらい電話でのやり取りに慣れる。",
        "situation": (
            "Calling a restaurant to book a table. The user gives the date, time, and "
            "party size, asks about seating options, and handles a time slot that is "
            "already full by negotiating an alternative."
        ),
        "ai_role": "a restaurant staff member answering the phone",
        "user_role": "a customer calling to make a reservation",
    },
    # ---------------------------------------------------------------- 仕事
    {
        "id": "career-interview",
        "category": "work",
        "order": 10,
        "title_ja": "英語面接",
        "title_en": "Job Interview",
        "icon": "🤝",
        "level": "intermediate",
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
        "category": "work",
        "order": 11,
        "title_ja": "ビジネス会議",
        "title_en": "Business Meeting",
        "icon": "📊",
        "level": "intermediate",
        "description_ja": "プロジェクトの進捗会議。状況報告・意見交換・次のアクションの確認。",
        "situation": (
            "A project status meeting at work. The user reports progress, discusses an "
            "issue, exchanges opinions, and agrees on next steps with a colleague."
        ),
        "ai_role": "a project manager leading the meeting",
        "user_role": "a team member reporting on their tasks",
    },
    {
        "id": "work-presentation-qa",
        "category": "work",
        "order": 12,
        "title_ja": "プレゼン後の質疑応答",
        "title_en": "Post-presentation Q&A",
        "icon": "🎤",
        "level": "advanced",
        "description_ja": "プレゼン直後の質疑応答セッション。質問の意図確認、即答できないときの時間稼ぎ、丁寧な反論。",
        "situation": (
            "A Q&A session right after the user gave a presentation about a project "
            "proposal. The audience asks questions, including some challenging ones. "
            "The user clarifies question intent, buys time when needed, and politely "
            "pushes back on misunderstandings."
        ),
        "ai_role": "an engaged audience member asking sharp but fair questions",
        "user_role": "a presenter answering questions about their proposal",
    },
    # ---------------------------------------------------------------- トラブル対応
    {
        "id": "trouble-flight-delay",
        "category": "trouble",
        "order": 13,
        "title_ja": "フライト遅延・欠航",
        "title_en": "Flight Delay & Cancellation",
        "icon": "🛬",
        "level": "intermediate",
        "description_ja": "搭乗予定便が欠航に。振替便の手配、補償やホテルの確認、乗り継ぎの相談。",
        "situation": (
            "The user's flight has just been cancelled. At the airline service counter, "
            "the user asks about rebooking options, compensation, hotel vouchers, and "
            "how to handle a missed connection."
        ),
        "ai_role": "an airline customer service agent at the rebooking counter",
        "user_role": "a passenger whose flight was cancelled",
    },
    {
        "id": "trouble-wrong-order",
        "category": "trouble",
        "order": 14,
        "title_ja": "注文ミスの指摘",
        "title_en": "Wrong Order",
        "icon": "🍔",
        "level": "beginner",
        "description_ja": "届いた料理が注文と違う、会計が間違っている…そんなとき丁寧に指摘して対応してもらう練習。",
        "situation": (
            "At a restaurant, the server brings the wrong dish and later the bill has "
            "an extra charge. The user politely points out the mistakes and asks to "
            "have them fixed, staying friendly throughout."
        ),
        "ai_role": "an apologetic but slightly flustered restaurant server",
        "user_role": "a polite customer whose order was mixed up",
    },
    {
        "id": "trouble-pharmacy",
        "category": "trouble",
        "order": 15,
        "title_ja": "薬局で症状説明",
        "title_en": "At the Pharmacy",
        "icon": "💊",
        "level": "intermediate",
        "description_ja": "旅行先で体調不良。薬剤師に症状を説明し、市販薬の選び方・用法用量・注意点を確認する。",
        "situation": (
            "Feeling unwell while traveling, the user visits a pharmacy, describes "
            "their symptoms (headache, sore throat, slight fever), and asks the "
            "pharmacist to recommend medicine, how to take it, and any precautions."
        ),
        "ai_role": "a caring and knowledgeable pharmacist",
        "user_role": "a traveler feeling unwell and seeking advice",
    },
]


def get_scenario(scenario_id: str) -> dict | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)
