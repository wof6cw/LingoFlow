/* LingoFlow frontend — vanilla JS SPA */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  scenarios: [],
  categories: [],
  stats: null,
  // 進行中のセッション
  scenario: null,      // null ならフリートーク
  content: null,       // { phrases, opening_line }
  difficulty: "intermediate",
  phraseIndex: 0,
  messages: [],        // [{role: 'user'|'ai', text}]
  voiceMode: true,
  feedback: null,
};

const LEVEL_LABELS = { beginner: "初級", intermediate: "中級", advanced: "上級" };
// 初級はお手本・AI音声をゆっくりめに再生する
const TTS_RATES = { beginner: 0.8, intermediate: 0.95, advanced: 1.0 };

// index.html の <symbol> を参照する線画アイコン（JSから動的に挿す分）
const svgIcon = (name, cls = "icon") =>
  `<svg class="${cls}"><use href="#i-${name}"/></svg>`;

// 学習パスのカテゴリ別ラインアートアイコン
const CATEGORY_ICONS = {
  basics: "sprout", travel: "compass", daily: "cup", work: "case", trouble: "alert",
};

/* ================================================================ API */

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `エラー (HTTP ${res.status})`;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

/* ================================================================ 画面制御 */

const VIEWS = ["home", "intro", "shadowing", "talk", "feedback", "phrases", "stats", "history-detail"];

function show(view) {
  VIEWS.forEach((v) => $(`view-${v}`).classList.toggle("hidden", v !== view));
  document.querySelectorAll(".bottom-nav button").forEach((b) => {
    b.classList.toggle("active",
      (view === "home" && b.dataset.nav === "home") ||
      ((view === "stats" || view === "history-detail") && b.dataset.nav === "stats") ||
      (view === "phrases" && b.dataset.nav === "phrases") ||
      (view === "talk" && !state.scenario && b.dataset.nav === "free"));
  });
  window.scrollTo(0, 0);
}

function loading(on, text) {
  $("loading").classList.toggle("hidden", !on);
  if (text) $("loading-text").textContent = text;
}

let toastTimer;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 4000);
}

/* ================================================================ 音声合成 (TTS) */

let voices = [];
function loadVoices() { voices = speechSynthesis.getVoices(); }
loadVoices();
if (typeof speechSynthesis !== "undefined") {
  speechSynthesis.onvoiceschanged = loadVoices;
}

function pickEnglishVoice() {
  const en = voices.filter((v) => v.lang.startsWith("en"));
  return (
    en.find((v) => /Google US English/i.test(v.name)) ||
    en.find((v) => v.lang === "en-US") ||
    en[0] || null
  );
}

function speak(text, onend) {
  if (typeof speechSynthesis === "undefined") { if (onend) onend(); return; }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  const v = pickEnglishVoice();
  if (v) u.voice = v;
  u.rate = TTS_RATES[state.difficulty] || 0.95;
  if (onend) { u.onend = onend; u.onerror = onend; }
  speechSynthesis.speak(u);
}

/* ================================================================ 音声認識 (STT) */

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const sttSupported = !!SR;
let activeRec = null;

function listen({ onResult, onEnd, onError }) {
  if (!sttSupported) {
    onError("このブラウザは音声認識に対応していません。Chromeを使うか、チャットモードをご利用ください。");
    return null;
  }
  speechSynthesis.cancel(); // 自分の声とTTSが混ざらないように
  const rec = new SR();
  rec.lang = "en-US";
  rec.interimResults = true;
  rec.maxAlternatives = 1;
  let finalText = "";
  let finished = false; // onerror の後にも onend が発火するため、完了通知は一度だけにする
  const finish = (fn, arg) => { if (!finished) { finished = true; fn(arg); } };
  rec.onresult = (e) => {
    let interim = "";
    for (const r of e.results) {
      if (r.isFinal) finalText += r[0].transcript;
      else interim += r[0].transcript;
    }
    onResult(finalText, interim);
  };
  rec.onerror = (e) => {
    activeRec = null;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      finish(onError, "マイクの使用が許可されていません。ブラウザの設定を確認してください。");
    } else if (e.error !== "aborted" && e.error !== "no-speech") {
      finish(onError, `音声認識エラー: ${e.error}`);
    }
    // aborted / no-speech は onend 側で（空の結果として）処理する
  };
  rec.onend = () => { activeRec = null; finish(onEnd, finalText.trim()); };
  rec.start();
  activeRec = rec;
  return rec;
}

function stopListening() {
  if (activeRec) activeRec.stop();
}

/* ================================================================ 自分の発話の録音 (MediaRecorder)

   Web Speech APIは文字起こしのみで音声自体は取れないため、
   MediaRecorderを並行して走らせて聞き返し用の音声を作る。
   音声はセッション中のみ保持し、サーバーには送らない（都度破棄）。 */

async function startAudioRecorder() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    return null;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.start();
    const release = () => stream.getTracks().forEach((t) => t.stop());
    return {
      // 停止して再生用URLを返す（録れていなければ null）
      stop: () => new Promise((resolve) => {
        recorder.onstop = () => {
          release();
          resolve(chunks.length
            ? URL.createObjectURL(new Blob(chunks, { type: recorder.mimeType }))
            : null);
        };
        try { recorder.stop(); } catch (_) { release(); resolve(null); }
      }),
      cancel: () => {
        recorder.onstop = null;
        try { recorder.stop(); } catch (_) {}
        release();
      },
    };
  } catch (_) {
    return null; // 録音できなくても文字起こしだけで続行する
  }
}

function revokeAudio(url) {
  if (url) URL.revokeObjectURL(url);
}

/* ================================================================ ホーム */

async function loadHome() {
  try {
    const data = await api("/api/scenarios");
    state.scenarios = data.scenarios;
    state.categories = data.categories;
    state.stats = data.stats;
    renderHome();
  } catch (e) {
    toast(e.message);
  }
}

function renderHome() {
  const h = new Date().getHours();
  $("greeting").textContent =
    h < 5 ? "こんばんは" : h < 11 ? "おはようございます" : h < 18 ? "こんにちは" : "こんばんは";
  const s = state.stats;
  $("stat-line").innerHTML =
    (s.streak > 0 ? `<span class="streak-pill">${s.streak}日連続</span>` : "") +
    `<span>通算${s.total_sessions}回</span>`;
  $("stats2-streak").textContent = s.streak;
  $("stats2-today").textContent = s.today_sessions;
  $("stats2-total").textContent = s.total_sessions;

  const path = $("learning-path");
  path.innerHTML = "";
  for (const cat of state.categories) {
    const items = state.scenarios.filter((sc) => sc.category === cat.id);
    if (!items.length) continue;
    const label = document.createElement("div");
    label.className = "path-category";
    label.textContent = cat.title_ja;
    path.appendChild(label);
    for (const sc of items) {
      const done = sc.completed_count > 0;
      const node = document.createElement("div");
      node.className = "path-node" + (done ? " done" : "");
      node.innerHTML = `
        <span class="node-icon">${svgIcon(CATEGORY_ICONS[sc.category] || "sprout")}</span>
        <div class="node-body">
          <b>${esc(sc.title_ja)}</b>
          <div class="node-meta">${esc(sc.title_en)} ・ ${LEVEL_LABELS[sc.level] || sc.level}</div>
        </div>
        ${done
          ? `<span class="node-check">${svgIcon("check", "icon icon-sm")}${sc.completed_count}回</span>`
          : `<span class="node-new">${svgIcon("right", "icon icon-sm")}</span>`}`;
      node.addEventListener("click", () => openIntro(sc));
      path.appendChild(node);
    }
  }
  renderHistory();
}

function renderHistory() {
  const list = $("history-list");
  const recent = state.stats?.recent || [];
  if (!recent.length) {
    list.innerHTML = `<p class="empty-note">まだ記録がありません。最初のセッションを始めましょう！</p>`;
    return;
  }
  list.innerHTML = "";
  for (const r of recent) {
    const sc = state.scenarios.find((s) => s.id === r.scenario_id);
    const title = sc ? sc.title_ja : "フリートーク";
    const level = LEVEL_LABELS[r.difficulty] ? ` ・ ${LEVEL_LABELS[r.difficulty]}` : "";
    const item = document.createElement("div");
    item.className = "history-item";
    item.innerHTML = `
      <div class="h-body">
        <b>${esc(title)}</b>
        <div class="h-date">${r.date}${level}</div>
        ${r.excerpt ? `<div class="h-excerpt">${esc(r.excerpt)}</div>` : ""}
      </div>
      ${r.score != null ? `<span class="h-score">${r.score}</span>` : ""}`;
    item.addEventListener("click", () => openHistoryDetail(r.id));
    list.appendChild(item);
  }
}

/* ================================================================ 表現集 */

const freqDots = (n) =>
  `<span class="freq-dots">${"<i></i>".repeat(Math.max(1, Math.min(3, n)))}</span>`;

function phraseRow({ en, ja, freq, count }) {
  const item = document.createElement("div");
  item.className = "phrase-item";
  item.innerHTML = `
    ${count != null ? "" : freqDots(freq)}
    <div class="phrase-body">
      <div class="phrase-item-en">${esc(en)}</div>
      ${ja ? `<div class="phrase-item-ja">${esc(ja)}</div>` : ""}
    </div>
    ${count > 1 ? `<span class="count-pill">×${count}</span>` : ""}`;
  item.addEventListener("click", () => speak(en));
  return item;
}

async function loadPhrases() {
  loading(true, "表現集を読み込み中");
  try {
    const data = await api("/api/expressions");

    const collected = $("phrases-collected");
    collected.innerHTML = "";
    const title = document.createElement("div");
    title.className = "phrase-group-title";
    title.innerHTML = `${svgIcon("book")} あなたの表現`;
    collected.appendChild(title);
    const note = document.createElement("p");
    note.className = "collected-note";
    note.textContent = "フィードバックで指摘された言い回しが自動で貯まります（×nは指摘された回数）";
    collected.appendChild(note);
    if (!data.collected.length) {
      const empty = document.createElement("p");
      empty.className = "empty-note";
      empty.textContent = "まだありません。会話を終えてフィードバックを受けると増えていきます。";
      collected.appendChild(empty);
    } else {
      for (const e of data.collected) {
        collected.appendChild(phraseRow({ en: e.en, ja: e.note, count: e.count }));
      }
    }

    const seed = $("phrases-seed");
    seed.innerHTML = "";
    for (const cat of data.categories) {
      const t = document.createElement("div");
      t.className = "phrase-group-title";
      t.textContent = cat.title_ja;
      seed.appendChild(t);
      for (const item of cat.items) {
        seed.appendChild(phraseRow(item));
      }
    }
  } catch (e) {
    toast(e.message);
  } finally {
    loading(false);
  }
}

/* ================================================================ 過去セッションの全文閲覧 */

async function openHistoryDetail(sessionId) {
  loading(true, "読み込み中…");
  try {
    const session = await api(`/api/sessions/${sessionId}`);
    const sc = state.scenarios.find((s) => s.id === session.scenario_id);
    $("history-detail-title").textContent = sc ? sc.title_ja : "フリートーク";
    const level = LEVEL_LABELS[session.difficulty] ? ` ・ ${LEVEL_LABELS[session.difficulty]}` : "";
    $("history-detail-meta").textContent = `${session.date}${level}`;

    const log = $("history-detail-log");
    log.innerHTML = "";
    for (const m of session.transcript) {
      const div = document.createElement("div");
      div.className = `bubble ${m.role}`;
      div.textContent = m.text;
      log.appendChild(div);
    }

    const fbEl = $("history-detail-feedback");
    fbEl.innerHTML = "";
    if (session.feedback) renderFeedbackInto(fbEl, session.feedback);

    show("history-detail");
  } catch (e) {
    toast(e.message);
  } finally {
    loading(false);
  }
}

/* ================================================================ シナリオ導入 */

function openIntro(sc) {
  state.scenario = sc;
  state.content = null;
  state.difficulty = sc.level; // 推奨レベルを初期選択にする
  $("intro-title").textContent = sc.title_ja;
  $("intro-level").textContent = `おすすめ: ${LEVEL_LABELS[sc.level]} ・ ${sc.title_en}`;
  $("intro-desc").textContent = sc.description_ja;
  renderLevelToggle();
  show("intro");
}

function renderLevelToggle() {
  const cached = state.scenario?.cached_levels || [];
  document.querySelectorAll("#level-toggle button").forEach((b) => {
    b.classList.toggle("active", b.dataset.level === state.difficulty);
    // 生成済みレベルにはゴールドのドットを付ける（再生成なし＝トークン消費なしで開始できる）
    b.innerHTML = LEVEL_LABELS[b.dataset.level] +
      (cached.includes(b.dataset.level) ? '<span class="cached-dot"></span>' : "");
  });
  const isCached = cached.includes(state.difficulty);
  $("cached-hint").innerHTML = isCached
    ? '<span class="cached-dot"></span>このレベルは生成済み — すぐに始められます'
    : "このレベルは初回にAIが内容を生成します";
  // 「作り直す」は生成済みのときだけ意味があるので、そのときだけ見せる
  $("btn-regenerate-content").classList.toggle("hidden", !isCached);
}

function markLevelCached() {
  if (!state.scenario) return;
  state.scenario.cached_levels = state.scenario.cached_levels || [];
  if (!state.scenario.cached_levels.includes(state.difficulty)) {
    state.scenario.cached_levels.push(state.difficulty);
  }
  renderLevelToggle();
}

async function fetchContent({ refresh = false } = {}) {
  loading(true, refresh ? "新しい内容を生成中…" : "シナリオを準備中…（このレベルで初回はAIが生成します）");
  try {
    const data = await api(
      `/api/scenarios/${state.scenario.id}/content?difficulty=${state.difficulty}&refresh=${refresh}`,
      { method: "POST" });
    state.content = data.content;
    markLevelCached();
    return true;
  } catch (e) {
    toast(e.message);
    return false;
  } finally {
    loading(false);
  }
}

/* ================================================================ シャドーイング */

async function startShadowing() {
  if (!(await fetchContent())) return;
  state.phraseIndex = 0;
  renderPhrase();
  show("shadowing");
}

function renderPhrase() {
  const phrases = state.content.phrases;
  const i = state.phraseIndex;
  const p = phrases[i];
  $("shadow-progress").textContent = `${i + 1} / ${phrases.length}`;
  $("shadow-bar").style.width = `${((i + 1) / phrases.length) * 100}%`;
  $("phrase-en").textContent = p.en;
  $("phrase-ja").textContent = p.ja;
  clearShadowAudio();
  $("shadow-result").classList.add("hidden");
  $("shadow-hint").classList.remove("hidden");
  $("btn-phrase-prev").disabled = i === 0;
  $("btn-phrase-next").textContent = i === phrases.length - 1 ? "会話練習へ ›" : "次へ ›";
}

const normalizeWords = (text) =>
  text.toLowerCase().replace(/[^a-z0-9' ]+/g, " ").split(/\s+/).filter(Boolean);

/** ターゲットの各単語が認識結果に順序を保って現れるかを判定（LCS的な貪欲マッチ） */
function comparePhrase(target, recognized) {
  const t = normalizeWords(target);
  const r = normalizeWords(recognized);
  let ri = 0;
  const hits = t.map((word) => {
    for (let j = ri; j < r.length; j++) {
      if (r[j] === word) { ri = j + 1; return true; }
    }
    return false;
  });
  const matched = hits.filter(Boolean).length;
  return { hits, accuracy: t.length ? Math.round((matched / t.length) * 100) : 0, words: t };
}

function showShadowResult(recognized) {
  const target = state.content.phrases[state.phraseIndex].en;
  const { hits, accuracy, words } = comparePhrase(target, recognized);
  const acc = $("shadow-accuracy");
  acc.textContent = recognized ? `${accuracy}%` : "聞き取れませんでした";
  acc.className = "accuracy " + (accuracy >= 80 ? "good" : accuracy >= 50 ? "ok" : "bad");
  $("shadow-recognized").innerHTML = words
    .map((w, i) => `<span class="${hits[i] ? "hit" : "miss"}">${w}</span>`)
    .join(" ");
  $("shadow-result").classList.remove("hidden");
  $("shadow-hint").classList.add("hidden");
  if (accuracy >= 80) speakPraise();
}

function speakPraise() {
  toast("Good! その調子です");
}

let shadowAudioUrl = null;
let shadowPlayer = null;

function clearShadowAudio() {
  if (shadowPlayer) { shadowPlayer.pause(); shadowPlayer = null; }
  revokeAudio(shadowAudioUrl);
  shadowAudioUrl = null;
  $("btn-shadow-replay").classList.add("hidden");
}

async function toggleShadowMic() {
  const btn = $("btn-shadow-mic");
  if (activeRec) { stopListening(); return; }
  clearShadowAudio();
  btn.classList.add("recording");
  $("shadow-hint").textContent = "録音中… もう一度タップで停止";
  $("shadow-hint").classList.remove("hidden");
  const recorder = await startAudioRecorder(); // 聞き返し用に並行録音
  const done = async () => {
    btn.classList.remove("recording");
    $("shadow-hint").textContent = "お手本を聞いてから、マイクで発音しましょう";
    if (recorder) {
      shadowAudioUrl = await recorder.stop();
      $("btn-shadow-replay").classList.toggle("hidden", !shadowAudioUrl);
    }
  };
  listen({
    onResult: () => {},
    onEnd: async (text) => {
      await done();
      showShadowResult(text);
    },
    onError: async (msg) => {
      await done();
      clearShadowAudio();
      toast(msg);
    },
  });
}

/* ================================================================ 会話（ロールプレイ / フリートーク） */

async function startTalk({ free = false } = {}) {
  if (free) {
    state.scenario = null;
    state.content = null;
    state.difficulty = "intermediate";
  }
  state.messages = [];
  clearShadowAudio();
  $("chat-log").innerHTML = "";
  $("talk-title").textContent = state.scenario ? state.scenario.title_ja : "AIフリートーク";
  setVoiceMode(state.voiceMode && sttSupported);
  show("talk");

  // 最初のAIの一言
  if (state.scenario && !state.content) {
    if (!(await fetchContent())) { show("intro"); return; }
  }
  if (state.scenario) {
    addMessage("ai", state.content.opening_line, state.content.opening_line_ja);
  } else {
    addMessage("ai", "Hi! Great to see you. What's on your mind today?",
      "やあ、会えてうれしいです。今日はどんなことを話しましょうか？");
  }
}

function addMessage(role, text, ja = null) {
  state.messages.push({ role, text }); // 履歴・API送信は英語のみ
  const log = $("chat-log");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  if (role === "ai") {
    const replay = document.createElement("span");
    replay.className = "replay";
    replay.innerHTML = svgIcon("speaker", "icon icon-sm");
    replay.title = "もう一度聞く";
    replay.addEventListener("click", (e) => { e.stopPropagation(); speak(text); });
    div.appendChild(replay);
    if (ja) {
      const btn = document.createElement("button");
      btn.className = "btn-trans";
      btn.textContent = "訳を見る";
      const jaDiv = document.createElement("div");
      jaDiv.className = "bubble-ja hidden";
      jaDiv.textContent = ja;
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const hidden = jaDiv.classList.toggle("hidden");
        btn.textContent = hidden ? "訳を見る" : "訳を隠す";
      });
      div.appendChild(btn);
      div.appendChild(jaDiv);
    }
    if (state.voiceMode) speak(text);
  }
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

async function sendUserMessage(text) {
  text = text.trim();
  if (!text) return;
  const bubble = addMessage("user", text);

  const log = $("chat-log");
  const typing = document.createElement("div");
  typing.className = "bubble ai typing";
  typing.textContent = "…";
  log.appendChild(typing);
  log.scrollTop = log.scrollHeight;

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: state.scenario?.id || null,
        messages: state.messages,
        difficulty: state.difficulty,
      }),
    });
    typing.remove();
    addMessage("ai", data.reply, data.reply_ja);
  } catch (e) {
    typing.remove();
    state.messages.pop(); // 失敗した発話は取り消して再送できるように
    bubble.remove();
    $("chat-text").value = text;
    toast(e.message);
  }
}

function setVoiceMode(on) {
  state.voiceMode = on;
  $("mode-voice").classList.toggle("active", on);
  $("mode-text").classList.toggle("active", !on);
  $("text-input").classList.toggle("hidden", on);
  if (!on) speechSynthesis.cancel();
  cancelVoiceTurn(); // モード切替時は進行中の録音・確認を破棄（updateVoiceUIも呼ばれる）
}

/* ---------------- 発話ターン（録音 → 確認 → 送信）の状態機械

   誤終了対策として認識は continuous + 自動再開で走らせ、
   終了は「マイクボタン再タップ」または「発話後しばらく無音」。
   終了後すぐには送信せず、確認パネル（再生/やり直し/送信）を挟む。 */

const turn = {
  phase: "idle",        // idle | recording | confirm
  rec: null,
  recorder: null,
  finalText: "",
  interim: "",
  manualStop: false,
  silenceTimer: null,
  audioUrl: null,
  player: null,
};

const SILENCE_AUTO_FINISH_MS = 3000;

function updateVoiceUI() {
  const btn = $("btn-talk-mic");
  const hint = $("talk-hint");
  const live = $("live-transcript");
  const recording = turn.phase === "recording";
  $("voice-input").classList.toggle("hidden", !state.voiceMode || turn.phase === "confirm");
  $("voice-confirm").classList.toggle("hidden", !state.voiceMode || turn.phase !== "confirm");
  btn.classList.toggle("recording", recording);
  $("talk-mic-icon").classList.toggle("hidden", recording);
  $("talk-stop-icon").classList.toggle("hidden", !recording);
  hint.textContent = recording ? "話し終わったらタップ" : "タップして話す";
  live.classList.toggle("hidden", !recording);
  if (recording) {
    live.textContent = (turn.finalText + turn.interim).trim() || "聞き取り中…";
  }
}

async function startVoiceTurn() {
  if (turn.phase !== "idle") return;
  if (!sttSupported) {
    toast("このブラウザは音声認識に対応していません。チャットモードをご利用ください。");
    return;
  }
  speechSynthesis.cancel();
  turn.finalText = "";
  turn.interim = "";
  turn.manualStop = false;
  turn.phase = "recording";
  updateVoiceUI();

  turn.recorder = await startAudioRecorder(); // 録音は取れなくても続行

  const rec = new SR();
  rec.lang = "en-US";
  rec.continuous = true;      // ひと区切りごとの自動停止（誤終了の主因）を防ぐ
  rec.interimResults = true;
  rec.onresult = (e) => {
    turn.interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) turn.finalText += r[0].transcript + " ";
      else turn.interim += r[0].transcript;
    }
    updateVoiceUI();
    // 発話が取れた後しばらく無音が続いたら自動で確認へ
    clearTimeout(turn.silenceTimer);
    if (turn.finalText.trim()) {
      turn.silenceTimer = setTimeout(finishVoiceTurn, SILENCE_AUTO_FINISH_MS);
    }
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      cancelVoiceTurn();
      toast("マイクの使用が許可されていません。ブラウザの設定を確認してください。");
    }
    // no-speech / aborted / network などは onend の自動再開に任せる
  };
  rec.onend = () => {
    // Chromeは無音区間で内部的にセッションを区切ることがあるため、
    // ユーザーが終了していなければ自動で認識を再開する
    if (turn.phase === "recording" && !turn.manualStop) {
      try { rec.start(); } catch (_) {}
    }
  };
  turn.rec = rec;
  try { rec.start(); } catch (_) {}
}

async function finishVoiceTurn() {
  if (turn.phase !== "recording") return;
  turn.manualStop = true;
  clearTimeout(turn.silenceTimer);
  // stop() 後に確定途中の結果が届くことがあるので onend まで待つ
  if (turn.rec) {
    await new Promise((resolve) => {
      const timeout = setTimeout(resolve, 1000);
      turn.rec.onend = () => { clearTimeout(timeout); resolve(); };
      try { turn.rec.stop(); } catch (_) { clearTimeout(timeout); resolve(); }
    });
    turn.rec = null;
  }
  turn.audioUrl = turn.recorder ? await turn.recorder.stop() : null;
  turn.recorder = null;
  turn.phase = "confirm";
  renderVoiceConfirm();
}

function renderVoiceConfirm() {
  const text = (turn.finalText + turn.interim).trim();
  const el = $("confirm-text");
  el.textContent = text || "（聞き取れませんでした。やり直してください）";
  el.classList.toggle("empty", !text);
  $("btn-send-voice").disabled = !text;
  $("btn-replay-self").disabled = !turn.audioUrl;
  updateVoiceUI();
}

function cleanupTurnAudio() {
  if (turn.player) { turn.player.pause(); turn.player = null; }
  revokeAudio(turn.audioUrl);
  turn.audioUrl = null;
}

function cancelVoiceTurn() {
  turn.manualStop = true;
  clearTimeout(turn.silenceTimer);
  if (turn.rec) {
    turn.rec.onend = null;
    try { turn.rec.stop(); } catch (_) {}
    turn.rec = null;
  }
  if (turn.recorder) { turn.recorder.cancel(); turn.recorder = null; }
  cleanupTurnAudio();
  turn.finalText = "";
  turn.interim = "";
  turn.phase = "idle";
  updateVoiceUI();
}

/* ================================================================ フィードバック */

async function finishTalk() {
  const userLines = state.messages.filter((m) => m.role === "user");
  if (!userLines.length) {
    toast("まだ発話がありません。少し会話してから終了しましょう。");
    return;
  }
  speechSynthesis.cancel();
  cancelVoiceTurn();
  loading(true, "AIコーチがフィードバックを作成中…");
  try {
    const fb = await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: state.scenario?.id || null,
        messages: state.messages,
        difficulty: state.difficulty,
      }),
    });
    state.feedback = fb;
    const saved = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        scenario_id: state.scenario?.id || null,
        mode: state.scenario ? "scenario" : "free_talk",
        score: fb.score,
        feedback: fb,
        difficulty: state.difficulty,
        transcript: state.messages,
      }),
    });
    state.stats = saved.stats;
    renderFeedback(fb);
    show("feedback");
  } catch (e) {
    toast(e.message);
  } finally {
    loading(false);
  }
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function renderFeedbackInto(el, fb) {
  const corrections = (fb.corrections || []).map((c) => `
    <div class="fb-item">
      <div><span class="fb-original">${esc(c.original)}</span></div>
      <div><span class="fb-corrected">→ ${esc(c.corrected)}</span></div>
      <div class="fb-why">${esc(c.explanation_ja)}</div>
    </div>`).join("");
  const better = (fb.better_expressions || []).map((b) => `
    <div class="fb-item">
      <div>${esc(b.original)}</div>
      <div><span class="fb-corrected">→ ${esc(b.improved)}</span></div>
      <div class="fb-why">${esc(b.reason_ja)}</div>
    </div>`).join("");
  const good = (fb.good_points || []).map((g) => `<li>${esc(g)}</li>`).join("");

  el.innerHTML = `
    <div class="card score-card">
      <div class="score-ring" style="--pct:${fb.score}"><b>${fb.score}</b><span>/ 100</span></div>
      <p style="font-size:14px; text-align:left;">${esc(fb.summary_ja)}</p>
    </div>
    ${good ? `<div class="card fb-section"><h3>良かった点</h3><ul class="fb-good">${good}</ul></div>` : ""}
    ${corrections ? `<div class="card fb-section"><h3>修正ポイント</h3>${corrections}</div>` : ""}
    ${better ? `<div class="card fb-section"><h3>もっと自然な言い方</h3>${better}</div>` : ""}
    ${fb.fluency_comment_ja ? `<div class="card fb-section"><h3>流暢さ</h3><p style="font-size:13px;">${esc(fb.fluency_comment_ja)}</p></div>` : ""}
  `;
}

function renderFeedback(fb) {
  renderFeedbackInto($("feedback-body"), fb);
}

/* ================================================================ イベント登録 */

document.querySelectorAll(".btn-back").forEach((b) =>
  b.addEventListener("click", () => show(b.dataset.back)));

document.querySelectorAll(".bottom-nav button").forEach((b) =>
  b.addEventListener("click", async () => {
    speechSynthesis.cancel();
    stopListening();
    cancelVoiceTurn();
    const nav = b.dataset.nav;
    if (nav === "home") { await loadHome(); show("home"); }
    else if (nav === "stats") { await loadHome(); show("stats"); }
    else if (nav === "phrases") { show("phrases"); loadPhrases(); }
    else if (nav === "free") startTalk({ free: true });
  }));

$("btn-free-talk").addEventListener("click", () => startTalk({ free: true }));
document.querySelectorAll("#level-toggle button").forEach((b) =>
  b.addEventListener("click", () => {
    state.difficulty = b.dataset.level;
    state.content = null; // レベルを変えたら内容は取り直す
    renderLevelToggle();
  }));
$("btn-start-shadowing").addEventListener("click", startShadowing);
$("btn-skip-to-talk").addEventListener("click", async () => {
  if (!(await fetchContent())) return;
  startTalk();
});
$("btn-regenerate-content").addEventListener("click", async () => {
  if (await fetchContent({ refresh: true })) toast("新しい内容に作り直しました");
});

$("btn-listen").addEventListener("click", () =>
  speak(state.content.phrases[state.phraseIndex].en));
$("btn-shadow-mic").addEventListener("click", toggleShadowMic);
$("btn-phrase-prev").addEventListener("click", () => {
  if (state.phraseIndex > 0) { state.phraseIndex--; renderPhrase(); }
});
$("btn-phrase-next").addEventListener("click", () => {
  speechSynthesis.cancel();
  stopListening();
  if (state.phraseIndex < state.content.phrases.length - 1) {
    state.phraseIndex++;
    renderPhrase();
  } else {
    startTalk();
  }
});

$("btn-talk-back").addEventListener("click", async () => {
  speechSynthesis.cancel();
  cancelVoiceTurn();
  if (state.scenario) show("intro");
  else { await loadHome(); show("home"); }
});
$("mode-voice").addEventListener("click", () => {
  if (!sttSupported) { toast("このブラウザは音声認識非対応です（Chrome推奨）。"); return; }
  setVoiceMode(true);
});
$("mode-text").addEventListener("click", () => setVoiceMode(false));
$("btn-talk-mic").addEventListener("click", () => {
  if (turn.phase === "recording") finishVoiceTurn();
  else startVoiceTurn();
});
$("btn-replay-self").addEventListener("click", () => {
  if (!turn.audioUrl) return;
  if (turn.player) turn.player.pause();
  turn.player = new Audio(turn.audioUrl);
  turn.player.play();
});
$("btn-redo").addEventListener("click", () => {
  cancelVoiceTurn();
  startVoiceTurn();
});
$("btn-send-voice").addEventListener("click", () => {
  const text = (turn.finalText + turn.interim).trim();
  cancelVoiceTurn(); // 音声はここで破棄（サーバーには送らない）
  if (text) sendUserMessage(text);
});
$("btn-shadow-replay").addEventListener("click", () => {
  if (!shadowAudioUrl) return;
  if (shadowPlayer) shadowPlayer.pause();
  shadowPlayer = new Audio(shadowAudioUrl);
  shadowPlayer.play();
});
$("btn-send").addEventListener("click", () => {
  const input = $("chat-text");
  sendUserMessage(input.value);
  input.value = "";
});
$("chat-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.isComposing) {
    sendUserMessage(e.target.value);
    e.target.value = "";
  }
});
$("btn-finish-talk").addEventListener("click", finishTalk);
$("btn-feedback-done").addEventListener("click", async () => {
  await loadHome();
  show("home");
});

/* ================================================================ 起動 */

if (!sttSupported) {
  state.voiceMode = false;
  setTimeout(() => toast("このブラウザは音声認識に対応していません。Chromeの利用をおすすめします（チャットモードは利用可能）。"), 800);
}
loadHome().then(() => {
  const hash = location.hash.replace("#", "");
  if (hash === "phrases") { show("phrases"); loadPhrases(); }
  else if (hash === "stats") show("stats");
  else show("home");
});
