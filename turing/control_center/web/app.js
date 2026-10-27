"use strict";

// --- state -------------------------------------------------------------------

let S = null;                 // last state() from Python
let selected = null;          // key of the source shown on the right
const fetched = {};           // provider -> model ids fetched from the provider
const results = {};           // provider -> {good, text} from the last test
const executorInfo = {};      // executor -> detect() result
let downloads = {};           // ollama model -> progress
let pollTimer = null;

const api = (name, ...args) => window.pywebview.api[name](...args);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const provider = (key) => S.providers.find((p) => p.key === key);

function modelFor(p) {
  if (p.key === "ollama") {
    const names = S.ollama.models.map((m) => m.name);
    return names.includes(p.model) ? p.model : names[0] || "";
  }
  return p.model || p.models[0] || (fetched[p.key] || [])[0] || "";
}

// --- loading -----------------------------------------------------------------

async function refresh() {
  S = await api("state");
  if (!selected) {
    const active = S.active.provider;
    selected = provider(active) ? active : (S.ollama.installed ? "ollama" : "claude");
  }
  renderFlow();
  renderNav();
  renderDetail();
}

function init() {
  // English pages go back to Chinese by drawing themselves again.
  window.onLanguageBack = () => location.reload();
  api("ui_language").then(setLang);
  setupRouter();
  setupHome();
  setupTest();
  refresh();
  for (const e of ["claude_code", "codex"]) {
    api("executor_status", e).then((r) => {
      executorInfo[e] = r;
      renderNav();
      if (selected === e) renderDetail();
    });
  }
}

if (window.pywebview && window.pywebview.api) init();
else window.addEventListener("pywebviewready", init);

// --- top: where your voice goes ---------------------------------------------

function renderFlow() {
  const node = document.getElementById("flow-ai");
  const p = provider(S.active.provider);
  node.classList.toggle("on", Boolean(p));
  node.querySelector(".node-name").textContent = p ? `AI：${shortLabel(p)}` : "AI";
  node.querySelector(".node-where").textContent = p ? (S.active.model || "默认模型") : "未开启";
  document.getElementById("ai-chip").innerHTML = p
    ? `AI：<b>${esc(shortLabel(p))}</b> ${esc(S.active.model || "")}`
    : "没有连接 AI，只听懂本地指令。去连接";
}

// --- pages -------------------------------------------------------------------

function show(view) {
  if (!document.getElementById(`view-${view}`)) view = "home";
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  document.querySelectorAll(".tab").forEach((t) =>
    t.setAttribute("aria-current", t.dataset.view === view ? "page" : "false"));
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
}

function setupRouter() {
  document.getElementById("quit").addEventListener("click", () => api("quit_app"));
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.view)));
  document.querySelectorAll("[data-goto]").forEach((b) => b.addEventListener("click", () => show(b.dataset.goto)));
  show(location.hash.slice(1) || "home");
}

// --- home: listening state and conversation ------------------------------------

const STATES = {
  stopped: ["图灵没有在听", "点下面的按钮开始。"],
  loading: ["正在准备…", "第一次启动会下载语音模型，需要一会儿。"],
  waiting: ["说「嗨，图灵」叫醒我", "可以一口气说完，比如「嗨图灵，打开微信」。"],
  listening: ["在听…", "说完停一下就好。"],
  thinking: ["想一想…", ""],
  speaking: ["", ""],
};
const WHO = { you: "你", turing: "图灵", wake: "", info: "", error: "出错" };
let lastEvent = 0;

function setupHome() {
  const power = document.getElementById("power");
  power.addEventListener("click", async () => {
    // Keep a reference to the button itself: the event's currentTarget is gone after await.
    const running = power.dataset.running === "1";
    power.disabled = true;
    try {
      await api(running ? "engine_stop" : "engine_start");
    } finally {
      power.disabled = false;
    }
  });
  schedulePoll();
  setupAsk();
}

// Typing instead of talking: the command and Turing's reply show up in the log like
// spoken ones (they come back through engine_status).
function setupAsk() {
  const form = document.getElementById("ask");
  const text = document.getElementById("ask-text");
  const send = document.getElementById("ask-send");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const command = text.value.trim();
    if (!command || send.disabled) return text.focus();
    send.disabled = true;
    send.textContent = "…";
    text.value = "";
    try {
      const r = await api("type_command", command);
      if (!r.ok) logLine("error", r.error);
    } finally {
      send.disabled = false;
      send.textContent = "发送";
      text.focus();
      schedulePoll(0);
    }
  });
}

function logLine(kind, text, time = new Date().toTimeString().slice(0, 5)) {
  const list = document.getElementById("log");
  const li = document.createElement("li");
  li.className = kind;
  li.innerHTML = `<span class="log-time">${esc(time)}</span><span class="log-who">${esc(WHO[kind])}</span>
      <span class="log-text" translate="no">${esc(text)}</span>`;
  list.append(li);
  li.scrollIntoView({ block: "end" });
  document.getElementById("log-empty").hidden = true;
}

// The main window is often tucked away while Turing lives in the orb; then there is
// nothing to update, so it stops asking Python for news (Python calls setVisible).
let visible = true;
let statusTimer = null;

function setVisible(v) {
  visible = v;
  if (v) schedulePoll(0);
}

function schedulePoll(delay = 250) {
  clearTimeout(statusTimer);
  if (!visible) return;
  statusTimer = setTimeout(async () => {
    try { await poll(); } catch (e) { /* window closing */ }
    schedulePoll(document.hidden ? 1000 : 250);
  }, delay);
}

async function poll() {
  if (!window.pywebview) return;
  const r = await api("engine_status", lastEvent);
  const orb = document.getElementById("orb");
  orb.dataset.state = r.state;
  orb.style.setProperty("--level", r.level.toFixed(3));
  const meter = document.getElementById("meter-fill");
  if (meter) meter.style.width = `${Math.round(r.level * 100)}%`;
  const [title, hint] = STATES[r.state] || STATES.stopped;
  if (r.state !== "speaking") {
    document.getElementById("stage-title").textContent = title;
    // While you talk, show the words heard so far.
    document.getElementById("stage-hint").textContent =
      r.state === "listening" && r.partial ? `“${r.partial}”` : hint;
  }
  const power = document.getElementById("power");
  const running = r.state !== "stopped";
  power.dataset.running = running ? "1" : "0";
  power.textContent = running ? "暂停聆听" : "开始聆听";
  power.classList.toggle("stop", running);

  const list = document.getElementById("log");
  for (const e of r.events) {
    lastEvent = e.id;
    if (e.kind === "turing" && r.state === "speaking") {
      document.getElementById("stage-title").textContent = e.text.replace(/^图灵 \/ Turing: /, "");
    }
    if (!["you", "turing", "error"].includes(e.kind)) continue;
    logLine(e.kind, e.text.replace(/^(你 \/ You|图灵 \/ Turing): /, ""), e.time);
  }
  document.getElementById("log-empty").hidden = list.children.length > 0;
}

// --- settings ---------------------------------------------------------------------

async function setupTest() {
  await setupSettings();
  await setupPersonas();
  setupTestPanel();
}

const set = (name, value) => api("set_setting", name, value);

async function setupSettings() {
  const t = await api("settings");
  const $ = (id) => document.getElementById(id);

  const mic = $("s-mic");
  mic.innerHTML = `<option value="">跟随系统默认麦克风</option>` + t.microphones.map((m) =>
    `<option value="${m.index}">${esc(m.name)}${m.default ? "（默认）" : ""}</option>`).join("");
  mic.value = t.microphone;
  mic.addEventListener("change", () => set("microphone", mic.value));

  $("s-sensitivity").value = t.sensitivity;
  $("s-sensitivity").addEventListener("change", (e) => set("sensitivity", Number(e.target.value)));

  const end = $("s-end");
  const showEnd = () => { $("s-end-value").textContent = `${Number(end.value).toFixed(1)} 秒`; };
  end.value = t.end_silence;
  showEnd();
  end.addEventListener("input", showEnd);
  end.addEventListener("change", () => set("end_silence", Number(end.value)));

  const follow = $("s-follow");
  follow.value = String([0, 5, 8, 15, 30].reduce((a, b) => Math.abs(b - t.follow_up) < Math.abs(a - t.follow_up) ? b : a));
  follow.addEventListener("change", () => set("follow_up", Number(follow.value)));

  $("s-barge").checked = t.barge_in;
  $("s-barge").addEventListener("change", (e) => set("barge_in", e.target.checked));

  $("s-asr").value = t.asr;
  $("s-asr-note").hidden = t.qwen3_installed;
  $("s-asr").addEventListener("change", (e) => set("asr", e.target.value));

  $("s-hotwords").value = t.hotwords;
  $("s-hotwords-save").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    await set("hotwords", $("s-hotwords").value);
    b.textContent = "已保存";
    b.disabled = false;
    setTimeout(() => { b.textContent = "保存"; }, 1500);
  });

  $("s-recordings").checked = t.keep_recordings;
  $("s-recordings").addEventListener("change", (e) => set("keep_recordings", e.target.checked));

  $("s-voice").value = t.voice;
  $("s-voice").addEventListener("change", (e) => set("voice", e.target.value));
  const speak = $("speak");
  speak.addEventListener("click", async () => {
    speak.disabled = true;
    try { await api("speak_test"); } finally { speak.disabled = false; }
  });

  const city = $("city"), citySave = $("city-save"), cityOut = $("city-result");
  city.value = t.city;
  citySave.addEventListener("click", async () => {
    citySave.disabled = true;
    try {
      await set("city", city.value);
      const r = await api("weather_test");
      cityOut.hidden = false;
      cityOut.className = "result good";
      cityOut.textContent = r.reply;
    } finally {
      citySave.disabled = false;
    }
  });

  const lang = $("s-lang");
  lang.value = t.language;
  lang.addEventListener("change", async () => {
    await set("language", lang.value);
    setLang(await api("ui_language"));
  });

  $("s-close").value = t.close_to_orb ? "1" : "0";
  $("s-close").addEventListener("change", (e) => set("close_to_orb", e.target.value === "1"));
  $("s-autostart").checked = t.autostart;
  $("s-autostart").addEventListener("change", (e) => set("autostart", e.target.checked));
  $("restart").addEventListener("click", (e) => {
    e.currentTarget.disabled = true;
    e.currentTarget.textContent = "正在重启…";
    api("restart_app");
  });
}

// --- personas ---------------------------------------------------------------------

let P = null;           // {active, presets}
let editing = null;     // name of the preset in the editor

async function setupPersonas() {
  P = await api("personas");
  editing = P.active;
  renderPersonas();
  const $ = (id) => document.getElementById(id);
  const form = () => ({ name: $("p-name").value.trim(), role: $("p-role").value.trim(),
                        style: $("p-style").value.trim(), rules: $("p-rules").value.trim() });
  const store = async (makeActive) => {
    const f = form();
    if (!f.name) return $("p-name").focus();
    if (f.name !== editing && P.presets.some((p) => p.name === f.name)) {
      const out = $("p-result");
      out.hidden = false;
      out.className = "result bad";
      out.textContent = `已经有一个叫“${f.name}”的人设了，换个名字吧。`;
      return;
    }
    const i = P.presets.findIndex((p) => p.name === editing);
    if (i >= 0) P.presets[i] = f; else P.presets.push(f);
    if (makeActive || P.active === editing) P.active = f.name;
    editing = f.name;
    const r = await api("save_personas", P);
    if (r.ok) { P = { active: r.active, presets: r.presets }; }
    const out = $("p-result");
    out.hidden = false;
    out.className = r.ok ? "result good" : "result bad";
    out.textContent = r.ok ? (P.active === f.name ? `已保存，图灵现在用“${f.name}”。` : "已保存。") : r.error;
    renderPersonas();
  };
  $("p-use").addEventListener("click", () => store(true));
  $("p-save").addEventListener("click", () => store(false));
  $("p-new").addEventListener("click", () => {
    let n = 1;
    while (P.presets.some((p) => p.name === `新人设${n}`)) n++;
    P.presets.push({ name: `新人设${n}`, role: "", style: "", rules: "" });
    editing = `新人设${n}`;
    renderPersonas();
    $("p-name").focus();
    $("p-name").select();
  });
  $("p-delete").addEventListener("click", async () => {
    if (P.presets.length <= 1) return;
    P.presets = P.presets.filter((p) => p.name !== editing);
    const r = await api("save_personas", P);
    if (r.ok) P = { active: r.active, presets: r.presets };
    editing = P.active;
    renderPersonas();
  });
}

function renderPersonas() {
  const list = document.getElementById("persona-list");
  list.innerHTML = P.presets.map((p) => `
    <button class="source" role="option" data-name="${esc(p.name)}" aria-selected="${p.name === editing}"
            aria-current="${p.name === editing}">
      <span class="source-name" translate="no">${esc(p.name)}</span>
      <span class="tag ${p.name === P.active ? "using" : ""}">${p.name === P.active ? "正在使用" : ""}</span>
    </button>`).join("");
  list.querySelectorAll(".source").forEach((b) => b.addEventListener("click", () => {
    editing = b.dataset.name;
    document.getElementById("p-result").hidden = true;
    renderPersonas();
  }));
  const p = P.presets.find((x) => x.name === editing) || P.presets[0];
  document.getElementById("p-name").value = p.name;
  document.getElementById("p-role").value = p.role || "";
  document.getElementById("p-style").value = p.style || "";
  document.getElementById("p-rules").value = p.rules || "";
  document.getElementById("p-delete").disabled = P.presets.length <= 1;
}

// --- test panel ---------------------------------------------------------------

function setupTestPanel() {
  const record = document.getElementById("record");
  const out = document.getElementById("record-result");
  record.addEventListener("click", async () => {
    record.disabled = true;
    record.textContent = "正在录音，请说话…";
    out.hidden = true;
    const r = await api("record_test");
    record.disabled = false;
    record.textContent = "录 4 秒试试";
    out.hidden = false;
    if (!r.ok) { out.className = "result bad"; out.textContent = r.error; return; }
    const quiet = r.peak < 0.05 ? t("声音很小，离麦克风近一点，或者在 Windows 声音设置里调高麦克风音量。",
      "Very quiet. Move closer to the microphone, or turn up its level in Windows sound settings.") : "";
    out.className = r.text ? "result good" : "result bad";
    out.setAttribute("translate", "no");  // what was heard stays as heard
    out.textContent = r.text ? `${t("听到：", "Heard: ")}${r.text}${quiet ? t("。", ". ") + quiet : ""}`
      : `${t("没听清。", "Didn't catch that. ")}${quiet}`;
  });
}

const shortLabel = (p) => p.label.replace(/[（(].*$/, "").trim();

// --- left: sources -------------------------------------------------------------

function sourceTag(p) {
  if (S.active.provider === p.key) return ["using", "正在使用"];
  if (p.key === "ollama") {
    if (!S.ollama.installed) return ["", "未安装"];
    if (!S.ollama.running) return ["warn", "未启动"];
    return ["ok", `${S.ollama.models.length} 个模型`];
  }
  return p.has_key ? ["ok", "已填 Key"] : ["", ""];
}

function executorTag(key) {
  const info = executorInfo[key];
  if (!info) return ["", "检查中…"];
  if (!info.installed) return ["", "未安装"];
  return info.logged_in ? ["ok", "已登录"] : ["warn", "未登录"];
}

function navButton(key, name, [cls, tag]) {
  return `<button class="source" data-key="${key}" aria-current="${selected === key}">
    <span class="source-name">${esc(name)}</span><span class="tag ${cls}">${esc(tag)}</span></button>`;
}

function renderNav() {
  const nav = document.getElementById("sources");
  const group = (g) => S.providers.filter((p) => p.group === g)
    .map((p) => navButton(p.key, p.label, sourceTag(p))).join("");
  nav.innerHTML = `
    <p class="group-title">在本机运行（免费）</p>
    ${group("local")}
    <p class="group-title">国外（填 API Key）</p>
    ${group("intl")}
    <p class="group-title">国内（填 API Key）</p>
    ${group("cn")}
    <p class="group-title">其他</p>
    ${group("other")}
    <p class="group-title">用你的订阅执行任务</p>
    ${S.executors.map((e) => navButton(e.key, e.label, executorTag(e.key))).join("")}
    <p class="group-title"></p>
    ${navButton("off", "不使用 AI", S.active.provider === "none" ? ["using", "当前"] : ["", ""])}`;
  nav.querySelectorAll(".source").forEach((b) =>
    b.addEventListener("click", () => {
      selected = b.dataset.key;
      renderNav();
      renderDetail();
      document.getElementById("detail").focus();
    }));
}

// --- right: details ----------------------------------------------------------

function renderDetail() {
  const el = document.getElementById("detail");
  if (selected === "off") el.innerHTML = offView();
  else if (selected === "ollama") el.innerHTML = ollamaView(provider("ollama"));
  else if (S.executors.some((e) => e.key === selected)) el.innerHTML = executorView(selected);
  else el.innerHTML = apiView(provider(selected));
  bind(el);
}

function heading(p) {
  const using = S.active.provider === p.key ? `<span class="badge">正在使用</span>` : "";
  return `<h2>${esc(p.label)} ${using}</h2><p class="lede">${esc(p.note)}</p>`;
}

function modelRows(p, ids, notes = {}, sizes = {}) {
  const chosen = modelFor(p);
  if (!ids.length) return `<p class="muted">还没有模型。</p>`;
  return `<div class="models" role="radiogroup" aria-label="模型">${ids.map((id) => `
    <label class="model pickable ${id === chosen ? "chosen" : ""}">
      <input type="radio" name="model" value="${esc(id)}" ${id === chosen ? "checked" : ""}
             data-act="choose" data-provider="${p.key}">
      <span class="model-id">${esc(id)}</span>
      <span class="side muted small">${esc(sizes[id] || "")}</span>
      ${notes[id] ? `<span class="model-note">${esc(notes[id])}</span>` : ""}
    </label>`).join("")}</div>`;
}

function testAndUse(p, ready) {
  const model = modelFor(p);
  const r = results[p.key];
  const active = S.active.provider === p.key && S.active.model === model;
  return `
    <div class="row">
      <button class="btn" data-act="test" data-provider="${p.key}" ${ready ? "" : "disabled"}>测试连接</button>
      <button class="btn primary" data-act="activate" data-provider="${p.key}" ${ready && !active ? "" : "disabled"}>
        ${active ? "图灵正在用这个 AI" : "让图灵用这个 AI"}</button>
    </div>
    ${r ? `<div class="result ${r.good ? "good" : "bad"}">
      <p>${esc(r.text)}</p>
      ${r.detail ? `<p class="muted small">服务商返回：${esc(r.detail)}</p>` : ""}
      ${r.credit && p.key_url ? `<button class="btn" data-act="open" data-url="${esc(p.key_url)}">打开 ${esc(p.label)} 网站充值</button>` : ""}
    </div>` : ""}
    ${ready ? `<p class="muted small">将使用模型 <span class="model-id">${esc(model)}</span>。图灵下次被叫醒时就会用上，不用重启。</p>` : ""}`;
}

function apiView(p) {
  const ids = [...new Set([...p.models, ...(fetched[p.key] || [])])];
  const keyStep = p.has_key
    ? `<p class="saved">已保存在本机的 Windows 凭据管理器里。</p>
       <div class="row"><button class="btn" data-act="replace-key">换一个 Key</button>
       <button class="btn quiet danger" data-act="delete-key" data-provider="${p.key}">删除 Key</button></div>
       <div class="row" id="key-row" hidden>${keyInput(p)}</div>`
    : `<div class="row">${keyInput(p)}</div>
       <p class="muted small">Key 只保存在本机的 Windows 凭据管理器里，不会写进文件，也不会上传。</p>`;
  const urlStep = p.url_editable ? `
    <li class="step ${p.url || p.default_url ? "done" : ""}">
      <p class="step-title">接口地址</p>
      <div class="row"><input class="input mono" id="url" value="${esc(p.url || p.default_url)}"
        placeholder="https://…/v1" aria-label="接口地址">
      <button class="btn" data-act="save-url" data-provider="${p.key}">保存地址</button></div>
      ${p.key === "custom" ? "" : `<p class="muted small">一般不用改。</p>`}
    </li>` : "";
  return `${heading(p)}
    <ol class="steps">
      ${p.key_url ? `<li class="step ${p.has_key ? "done" : ""}">
        <p class="step-title">注册并创建 API Key</p>
        <div class="row"><button class="btn" data-act="open" data-url="${esc(p.key_url)}">打开 ${esc(shortLabel(p))} 的 Key 页面</button></div>
        <p class="muted small">需要在服务商那里充值或开通，费用由你和服务商直接结算。</p>
      </li>` : ""}
      ${urlStep}
      <li class="step ${p.has_key ? "done" : ""}">
        <p class="step-title">填写 API Key</p>${keyStep}
      </li>
      <li class="step ${p.model ? "done" : ""}">
        <p class="step-title">选择模型</p>
        ${modelRows(p, ids, p.model_notes)}
        <div class="row" style="margin-top:8px">
          <button class="btn quiet" data-act="fetch" data-provider="${p.key}" ${p.has_key ? "" : "disabled"}>从 ${esc(shortLabel(p))} 获取全部模型</button>
          <input class="input mono" id="custom-model" placeholder="或者直接填模型名" aria-label="模型名">
          <button class="btn" data-act="custom-model" data-provider="${p.key}">使用</button>
        </div>
      </li>
      <li class="step">
        <p class="step-title">测试并使用</p>
        ${testAndUse(p, p.has_key && Boolean(modelFor(p)))}
      </li>
    </ol>`;
}

function keyInput(p) {
  return `<input class="input mono" id="key" type="password" autocomplete="off" spellcheck="false"
      placeholder="粘贴 API Key" aria-label="${esc(shortLabel(p))} API Key">
    <button class="btn primary" data-act="save-key" data-provider="${p.key}">保存 Key</button>`;
}

function ollamaView(p) {
  const o = S.ollama, hw = S.hardware;
  if (!o.installed) {
    return `${heading(p)}
      <ol class="steps">
        <li class="step"><p class="step-title">下载并安装 Ollama</p>
          <div class="row"><button class="btn primary" data-act="open" data-url="https://ollama.com/download">打开 Ollama 下载页</button></div></li>
        <li class="step"><p class="step-title">装好后回到这里</p>
          <div class="row"><button class="btn" data-act="reload">重新检测</button></div></li>
      </ol>`;
  }
  if (!o.running) {
    return `${heading(p)}
      <p>Ollama 已安装，但还没有启动。</p>
      <div class="row"><button class="btn primary" data-act="ollama-start">启动 Ollama</button></div>`;
  }
  const local = o.models.filter((m) => !m.cloud);
  const cloud = o.models.filter((m) => m.cloud);
  const have = new Set(o.models.map((m) => m.name));
  const sizes = Object.fromEntries(o.models.map((m) => [m.name, m.cloud ? "云端" : `${m.size_gb} GB`]));
  const best = o.recommended.find((m) => m.best);
  return `${heading(p)}
    <dl class="facts">
      <div><dt>显卡</dt><dd>${esc(hw.gpu || "未检测到独立显卡")}</dd></div>
      <div><dt>显存</dt><dd>${hw.vram_gb} GB</dd></div>
      <div><dt>内存</dt><dd>${hw.ram_gb} GB</dd></div>
      <div><dt>Ollama</dt><dd>${esc(o.version)}</dd></div>
    </dl>

    <h3>选一个模型给图灵用</h3>
    ${o.models.length ? modelRows(p, [...local, ...cloud].map((m) => m.name), {}, sizes)
      : `<p class="muted">还没有下载模型。从下面选一个下载。</p>`}
    ${best && !have.has(best.name) && local.length ? `<p class="callout">
      你现在的模型都比较小，可能会听错指令。你的电脑能跑 <span class="model-id">${esc(best.name)}</span>，会聪明很多。</p>` : ""}

    <h3>下载本地模型</h3>
    <p class="muted small">本地模型免费、不联网。越大越聪明，也越吃显卡。</p>
    <div class="models">${o.recommended.map((m) => downloadRow(m.name, `${m.size_gb} GB`, m.note, have.has(m.name), {
      best: m.best, unfit: !m.fits })).join("")}</div>

    <h3>云端模型</h3>
    <p class="muted small">在 Ollama 的服务器上运行，比本地模型聪明、也更快，不占你的显卡。需要登录 Ollama 账户。免费账户只能用标了"免费可用"的模型，额度每 5 小时和每周刷新；其他的要付费会员。</p>
    <div class="row" style="margin-bottom:10px"><button class="btn" data-act="ollama-signin">登录 Ollama 账户</button>
      <span class="muted small">会打开一个命令行窗口，按提示在浏览器里登录。</span></div>
    <div class="models">${o.cloud.map((m) => downloadRow(m.name, "云端", m.note, have.has(m.name), {
      verb: "添加", paid: m.paid, best: !m.paid })).join("")}</div>

    <h3>测试并使用</h3>
    ${testAndUse(p, Boolean(modelFor(p)))}`;
}

function downloadRow(name, size, note, installed, { best = false, unfit = false, paid = false, verb = "下载" } = {}) {
  const d = downloads[name];
  let side;
  if (installed) side = `<span class="tag ok">已${verb === "添加" ? "添加" : "下载"}</span>`;
  else if (d && d.active) side = `<span class="muted small">${esc(d.status)}</span><span class="bar"><span style="width:${d.pct}%"></span></span>`;
  else side = `<button class="btn" data-act="pull" data-model="${esc(name)}">${verb}</button>`;
  const flag = paid ? `<span class="tag warn">需要 Ollama 付费会员</span>`
    : best ? `<span class="best">${verb === "添加" ? "免费可用" : "最适合你的电脑"}</span>`
    : unfit ? `<span class="muted small">你的电脑可能跑不动</span>` : "";
  const error = d && d.error ? `<span class="model-note" style="color:var(--danger)">下载失败：${esc(d.error)}</span>` : "";
  return `<div class="model ${unfit ? "unfit" : ""}">
    <span class="muted small">${esc(size)}</span>
    <span><span class="model-id">${esc(name)}</span> ${flag}</span>
    <span class="side">${side}</span>
    <span class="model-note">${esc(note)}</span>${error}
  </div>`;
}

function executorView(key) {
  const e = S.executors.find((x) => x.key === key);
  const info = executorInfo[key];
  let status;
  if (!info) status = `<p class="muted">正在检查 ${esc(e.label)}…</p>`;
  else if (!info.installed) status = `<p>还没有安装 ${esc(e.label)}。</p>
    <div class="row"><button class="btn" data-act="open" data-url="${esc(e.install_url)}">查看安装方法</button></div>`;
  else if (!info.logged_in) status = `<p class="tag warn">已安装（${esc(info.version)}），但还没有登录。</p>
    <p class="muted">${esc(e.login_hint)}</p>`;
  else status = `<p class="saved">已登录${info.account ? `：${esc(info.account)}` : ""}</p>
    <p class="muted small">版本 ${esc(info.version.replace(/\s*\(.*\)$/, "").replace(/^\D+/, ""))}</p>`;
  return `<h2>${esc(e.label)}</h2>
    <p class="lede">用你的 ${esc(e.plan)}额度，完成检索文件、写代码这类比较大的任务。</p>
    ${status}
    <h3>它怎么工作</h3>
    <p>你说"嗨图灵，用 ${esc(e.label)} 帮我在下载文件夹里找那份合同"，图灵会在终端里打开你电脑上的 ${esc(e.label)}，把任务交给它。整个过程都在 ${esc(e.label)} 里进行，你能看到每一步。图灵不会读取或保存你的登录信息。</p>
    <label class="switch" style="margin-top:14px">
      <input type="checkbox" data-act="executor" data-key="${key}" ${e.enabled ? "checked" : ""} ${info && info.logged_in ? "" : "disabled"}>
      <span>允许图灵把任务交给 ${esc(e.label)}<br><span class="muted small">这个功能会在下一个版本启用。</span></span>
    </label>
    <p class="callout">订阅不能当图灵的日常 AI。${esc(e.why_not_daily)}而且每次启动要等好几秒，语音对话会太慢。日常对话请在左边选 Ollama 或一个 API。</p>`;
}

function offView() {
  const off = S.active.provider === "none";
  return `<h2>不使用 AI</h2>
    <p class="lede">图灵只执行本地指令：打开软件、播放暂停、调音量、报时、计时、锁屏、网页搜索。完全免费，什么都不会发出去。听不懂的话，它会直接告诉你。</p>
    <div class="row"><button class="btn primary" data-act="off" ${off ? "disabled" : ""}>${off ? "已关闭 AI" : "关闭 AI"}</button></div>`;
}

// --- actions -----------------------------------------------------------------

function bind(el) {
  el.querySelectorAll("[data-act]").forEach((node) => {
    const evt = node.matches("input[type=radio], input[type=checkbox]") ? "change" : "click";
    node.addEventListener(evt, () => act(node.dataset.act, node));
  });
  const key = el.querySelector("#key");
  if (key) key.addEventListener("keydown", (e) => {
    if (e.key === "Enter") el.querySelector('[data-act="save-key"]').click();
  });
}

async function act(what, node) {
  const p = node.dataset.provider;
  const busy = (label) => { node.disabled = true; if (label) node.textContent = label; };
  switch (what) {
    case "open":
      return api("open_url", node.dataset.url);
    case "reload":
      return refresh();
    case "replace-key":
      document.getElementById("key-row").hidden = false;
      return document.getElementById("key").focus();
    case "save-key": {
      const value = document.getElementById("key").value.trim();
      if (!value) return document.getElementById("key").focus();
      busy("正在保存…");
      const r = await api("save_key", p, value);
      results[p] = r.ok ? null : { good: false, text: r.error };
      await refresh();
      if (r.ok && !provider(p).models.length) loadModels(p);
      return;
    }
    case "delete-key":
      await api("delete_key", p);
      return refresh();
    case "save-url":
      await api("save_url", p, document.getElementById("url").value);
      return refresh();
    case "fetch":
      busy("正在获取…");
      return loadModels(p);
    case "choose":
      await api("choose_model", p, node.value);
      results[p] = null;
      return refresh();
    case "custom-model": {
      const value = document.getElementById("custom-model").value.trim();
      if (!value) return document.getElementById("custom-model").focus();
      fetched[p] = [...new Set([...(fetched[p] || []), value])];
      await api("choose_model", p, value);
      return refresh();
    }
    case "test": {
      busy("正在测试…");
      const r = await api("test", p, modelFor(provider(p)));
      results[p] = r.ok ? { good: true, text: `连接成功。AI 说：${r.reply}` }
        : { good: false, text: r.error, detail: r.detail, credit: r.kind === "credit" };
      return renderDetail();
    }
    case "activate":
      busy();
      await api("activate", p, modelFor(provider(p)));
      return refresh();
    case "off":
      await api("turn_off_ai");
      return refresh();
    case "executor":
      await api("set_executor", node.dataset.key, node.checked);
      return refresh();
    case "ollama-start":
      busy("正在启动…");
      await api("ollama_start");
      return waitForOllama();
    case "ollama-signin":
      busy("已打开登录窗口");
      await api("ollama_sign_in");
      return setTimeout(() => { node.disabled = false; node.textContent = "登录 Ollama 账户"; }, 15000);
    case "pull":
      busy("开始下载…");
      await api("ollama_pull", node.dataset.model);
      return pollDownloads();
  }
}

async function loadModels(p) {
  const r = await api("fetch_models", p);
  if (r.ok) {
    fetched[p] = r.models;
    results[p] = r.models.length ? null : { good: false, text: "服务商没有返回任何模型。" };
  } else {
    results[p] = { good: false, text: `获取模型失败：${r.error}` };
  }
  renderDetail();
}

async function waitForOllama() {
  for (let i = 0; i < 30; i++) {
    const r = await api("ollama_status");
    if (r.running) return refresh();
    await new Promise((ok) => setTimeout(ok, 1000));
  }
  refresh();
}

function pollDownloads() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    const r = await api("ollama_status");
    downloads = r.downloads;
    const active = Object.values(downloads).some((d) => d.active);
    if (!active) {
      clearInterval(pollTimer);
      pollTimer = null;
      await refresh();
    } else if (selected === "ollama") {
      renderDetail();
    }
  }, 1000);
}
