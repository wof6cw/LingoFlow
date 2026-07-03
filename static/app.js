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

const VIEWS = ["home", "intro", "shadowing", "talk", "feedback", "stats"];

function show(view) {
  VIEWS.forEach((v) => $(`view-${v}`).classList.toggle("hidden", v !== view));
  document.querySelectorAll(".bottom-nav button").forEach((b) => {
    b.classList.toggle("active",
      (view === "home" && b.dataset.nav === "home") ||
      (view === "stats" && b.dataset.nav === "stats") ||
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
    h < 5 ? "こんばんは！" : h < 11 ? "おはようございます！" : h < 18 ? "こんにちは！" : "こんばんは！";
  const s = state.stats;
  $("stat-streak").textContent = s.streak;
  $("stat-today").textContent = s.today_sessions;
  $("stat-total").textContent = s.total_sessions;
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
    label.textContent = `${cat.icon} ${cat.title_ja}`;
    path.appendChild(label);
    for (const sc of items) {
      const done = sc.completed_count > 0;
      const node = document.createElement("div");
      node.className = "path-node" + (done ? " done" : "");
      node.innerHTML = `
        <div class="node-icon">${done ? "✔️" : sc.icon}</div>
        <div class="node-body">
          <b>${sc.title_ja}</b>
          <div class="node-meta">${sc.title_en} ・ ${LEVEL_LABELS[sc.level] || sc.level}</div>
        </div>
        ${done ? `<span class="node-check">${sc.completed_count}回クリア</span>` : `<span class="badge">未挑戦</span>`}`;
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
  list.innerHTML = recent.map((r) => {
    const sc = state.scenarios.find((s) => s.id === r.scenario_id);
    const title = sc ? sc.title_ja : "フリートーク";
    const icon = sc ? sc.icon : "💬";
    const level = LEVEL_LABELS[r.difficulty] ? ` ・ ${LEVEL_LABELS[r.difficulty]}` : "";
    return `
      <div class="history-item">
        <span class="h-icon">${icon}</span>
        <div class="h-body"><b>${title}</b><div class="h-date">${r.date}${level}</div></div>
        ${r.score != null ? `<span class="h-score">${r.score}点</span>` : ""}
      </div>`;
  }).join("");
}

/* ================================================================ シナリオ導入 */

function openIntro(sc) {
  state.scenario = sc;
  state.content = null;
  state.difficulty = sc.level; // 推奨レベルを初期選択にする
  $("intro-title").textContent = sc.title_ja;
  $("intro-icon").textContent = sc.icon;
  $("intro-level").textContent = `おすすめ: ${LEVEL_LABELS[sc.level]} ・ ${sc.title_en}`;
  $("intro-desc").textContent = sc.description_ja;
  renderLevelToggle();
  show("intro");
}

function renderLevelToggle() {
  document.querySelectorAll("#level-toggle button").forEach((b) =>
    b.classList.toggle("active", b.dataset.level === state.difficulty));
}

async function fetchContent() {
  loading(true, "シナリオを準備中…（このレベルで初回はAIが生成します）");
  try {
    const data = await api(
      `/api/scenarios/${state.scenario.id}/content?difficulty=${state.difficulty}`,
      { method: "POST" });
    state.content = data.content;
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
  // ちょっとした達成感の演出（音は鳴らさず絵文字トースト）
  toast("🎉 Good! その調子です");
}

function toggleShadowMic() {
  const btn = $("btn-shadow-mic");
  if (activeRec) { stopListening(); return; }
  btn.classList.add("recording");
  $("shadow-hint").textContent = "録音中… もう一度タップで停止";
  $("shadow-hint").classList.remove("hidden");
  listen({
    onResult: () => {},
    onEnd: (text) => {
      btn.classList.remove("recording");
      $("shadow-hint").textContent = "🔊 でお手本を聞いて、🎤 を押して発音しましょう";
      showShadowResult(text);
    },
    onError: (msg) => {
      btn.classList.remove("recording");
      $("shadow-hint").textContent = "🔊 でお手本を聞いて、🎤 を押して発音しましょう";
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
  $("chat-log").innerHTML = "";
  $("talk-title").textContent = state.scenario ? state.scenario.title_ja : "AIフリートーク";
  setVoiceMode(state.voiceMode && sttSupported);
  show("talk");

  // 最初のAIの一言
  if (state.scenario && state.content?.opening_line) {
    addMessage("ai", state.content.opening_line);
  } else if (state.scenario) {
    if (!(await fetchContent())) { show("intro"); return; }
    addMessage("ai", state.content.opening_line);
  } else {
    addMessage("ai", "Hi! Great to see you. What's on your mind today? 😊");
  }
}

function addMessage(role, text) {
  state.messages.push({ role, text });
  const log = $("chat-log");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  if (role === "ai") {
    const replay = document.createElement("span");
    replay.className = "replay";
    replay.textContent = "🔊";
    replay.title = "もう一度聞く";
    replay.addEventListener("click", (e) => { e.stopPropagation(); speak(text); });
    div.appendChild(replay);
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
    addMessage("ai", data.reply);
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
  $("voice-input").classList.toggle("hidden", !on);
  $("text-input").classList.toggle("hidden", on);
  if (!on) { speechSynthesis.cancel(); stopListening(); }
}

function toggleTalkMic() {
  const btn = $("btn-talk-mic");
  if (activeRec) { stopListening(); return; }
  btn.classList.add("recording");
  const hint = $("talk-hint");
  hint.textContent = "録音中… もう一度タップで送信";
  listen({
    onResult: (finalText, interim) => {
      hint.textContent = (finalText + interim) || "録音中… もう一度タップで送信";
    },
    onEnd: (text) => {
      btn.classList.remove("recording");
      hint.textContent = "タップして話す";
      if (text) sendUserMessage(text);
    },
    onError: (msg) => {
      btn.classList.remove("recording");
      hint.textContent = "タップして話す";
      toast(msg);
    },
  });
}

/* ================================================================ フィードバック */

async function finishTalk() {
  const userLines = state.messages.filter((m) => m.role === "user");
  if (!userLines.length) {
    toast("まだ発話がありません。少し会話してから終了しましょう。");
    return;
  }
  speechSynthesis.cancel();
  stopListening();
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

function renderFeedback(fb) {
  const corrections = (fb.corrections || []).map((c) => `
    <div class="fb-item">
      <div><span class="fb-original">${esc(c.original)}</span></div>
      <div><span class="fb-corrected">→ ${esc(c.corrected)}</span></div>
      <div class="fb-why">${esc(c.explanation_ja)}</div>
    </div>`).join("");
  const better = (fb.better_expressions || []).map((b) => `
    <div class="fb-item">
      <div>${esc(b.original)}</div>
      <div><span class="fb-corrected">💡 ${esc(b.improved)}</span></div>
      <div class="fb-why">${esc(b.reason_ja)}</div>
    </div>`).join("");
  const good = (fb.good_points || []).map((g) => `<li>${esc(g)}</li>`).join("");

  $("feedback-body").innerHTML = `
    <div class="card score-card">
      <div class="score-ring" style="--pct:${fb.score}"><b>${fb.score}</b><span>/ 100</span></div>
      <p style="font-size:14px; text-align:left;">${esc(fb.summary_ja)}</p>
    </div>
    ${good ? `<div class="card fb-section"><h3>👍 良かった点</h3><ul class="fb-good">${good}</ul></div>` : ""}
    ${corrections ? `<div class="card fb-section"><h3>✏️ 修正ポイント</h3>${corrections}</div>` : ""}
    ${better ? `<div class="card fb-section"><h3>💡 もっと自然な言い方</h3>${better}</div>` : ""}
    ${fb.fluency_comment_ja ? `<div class="card fb-section"><h3>🗣️ 流暢さ</h3><p style="font-size:13px;">${esc(fb.fluency_comment_ja)}</p></div>` : ""}
  `;
}

/* ================================================================ イベント登録 */

document.querySelectorAll(".btn-back").forEach((b) =>
  b.addEventListener("click", () => show(b.dataset.back)));

document.querySelectorAll(".bottom-nav button").forEach((b) =>
  b.addEventListener("click", async () => {
    speechSynthesis.cancel();
    stopListening();
    const nav = b.dataset.nav;
    if (nav === "home") { await loadHome(); show("home"); }
    else if (nav === "stats") { await loadHome(); show("stats"); }
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
  stopListening();
  if (state.scenario) show("intro");
  else { await loadHome(); show("home"); }
});
$("mode-voice").addEventListener("click", () => {
  if (!sttSupported) { toast("このブラウザは音声認識非対応です（Chrome推奨）。"); return; }
  setVoiceMode(true);
});
$("mode-text").addEventListener("click", () => setVoiceMode(false));
$("btn-talk-mic").addEventListener("click", toggleTalkMic);
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
loadHome().then(() => show("home"));
