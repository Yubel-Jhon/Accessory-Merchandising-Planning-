"use strict";

const TYPE_ORDER = ["white_bg", "studio", "lifestyle", "detail", "fabric", "model"];
const PRODUCT_TYPES = ["white_bg", "detail", "fabric"];
const SCENE_TYPES = ["studio", "lifestyle", "model"];
const TYPE_SHORT = { white_bg: "白底", studio: "商拍", lifestyle: "氛围", detail: "细节",
  fabric: "面料", model: "模特" };
const TRANSFORMS = {
  white_bg: ["studio", "lifestyle", "detail", "fabric", "model"],
  studio: ["white_bg", "lifestyle", "detail", "fabric", "model"],
  lifestyle: ["white_bg", "studio", "model"],
  detail: ["white_bg"], fabric: [],
  model: ["white_bg", "studio", "lifestyle"],
};
const DEMO = { white_bg: "/file/images/white_bg.jpg", studio: "/file/images/studio.jpg",
  lifestyle: "/file/images/lifestyle.jpg", detail: "/file/images/detail.jpg" };

const state = {
  meta: null,
  anchor: null, anchorType: "white_bg",
  model: null,         // 上传的模特图 url（scene 层用）
  currentType: null,
  selected: {},        // 当前工作区：type -> url（纳入企划盘后清空）
  variation: null,     // 本款演变记录（生成即归属本款，纳入企划盘时自动带上）
  recog: null,          // 客观识别结果（自由格式，不套用数据库）
  planSkus: [],         // 企划盘：[{ sku, colorZh, colorEn, direction, retailer, selected, variation }]
  timing: { evolve_sec: 0, images_sec: 0 },  // 实测耗时累计 → 导出尾页「耗时拆解」
  cover: null,          // deck 封面 url（从氛围图挑的或再生成的）→ 导出 P01
  coverCandidates: [],  // 「再生成」出的封面候选
  checks: {},           // 一致性自检缓存（检验③）：生成图 url -> {verdict, reason}
};

const $ = (id) => document.getElementById(id);

// ---------- API 体检：页面一打开就查 key 是否接上 / 账户是否欠费，出问题顶部亮红条 ----------
async function checkApiHealth() {
  const el = $("apiHealth");
  if (!el) return;
  try {
    const res = await fetch("/api/health").then(r => r.json());
    if (res.ok) { el.hidden = true; return; }
    el.hidden = false;
    el.innerHTML = "<div>⚠️ " + escapeHtml(res.message || "API 异常") +
      "</div><pre>" + escapeHtml(res.fix || "") + "</pre>" +
      "<button id='btnRecheck'>重新检测</button>";
    $("btnRecheck").onclick = () => { el.innerHTML = "<div>检测中…</div>"; checkApiHealth(); };
  } catch { /* 后端没起时页面本来就用不了，不额外报错 */ }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  return r.json();
}

// ---------- 生效 SKU：识别命中库内款 → 继承库内参数（成分/规格/双价格） ----------
function effectiveSku() {
  if (state.recog) return (state.recog.lib_match && state.recog.lib_match.sku) || state.recog.sku;
  return currentSku();
}

// ---------- 渲染：图类型轨道 ----------
function renderTrack() {
  const { done, avail } = computeStates();
  renderTrackInto($("trackProduct"), PRODUCT_TYPES, done, avail);
  renderTrackInto($("trackScene"), SCENE_TYPES, done, avail);
}

function renderTrackInto(el, types, done, avail) {
  el.innerHTML = "";
  for (const t of types) {
    const n = document.createElement("div");
    let mark, cls;
    if (t === state.currentType) { mark = "◎"; cls = "current"; }
    else if (done.has(t)) { mark = "●"; cls = "done"; }
    else if (avail.has(t)) { mark = "○"; cls = "avail"; }
    else { mark = "✕"; cls = "block"; }
    n.className = "node " + cls;
    n.innerHTML = `<span class="mark">${mark}</span>${TYPE_SHORT[t]}`;
    if (cls !== "block") n.onclick = () => { state.currentType = t; renderTrack(); renderConfig(); };
    el.appendChild(n);
  }
}

// ---------- 渲染：折叠栏标签 + 按钮态（替代旧「企划状态」列表） ----------
function renderWorkState() {
  const { done } = computeStates();
  const skuName = effectiveSku() ? (effectiveSku().name || "未命名款") : "未选款";
  $("workSkuTag").textContent = state.anchor ? skuName : "未选款";
  $("setupTag").textContent = state.anchor
    ? (state.recog ? "已识别" : "已选图")
    : "";
  $("workTag").textContent = done.size ? `已出 ${done.size}/${TYPE_ORDER.length} 类` : "";
  $("planCountTag").textContent = state.planSkus.length;
  $("doneTag").textContent = state.planSkus.length ? `${state.planSkus.length} 款` : "";
  $("btnIntoPlan").disabled = Object.keys(state.selected).length === 0;
  $("btnExport").disabled = state.planSkus.length === 0;
  const cs = $("coverSection");
  if (cs) cs.hidden = state.planSkus.length === 0;
  renderOverview();
  renderCover();
}

function computeStates() {
  const done = new Set(Object.keys(state.selected));
  if (state.anchor) done.add(state.anchorType);
  const avail = new Set();
  for (const d of done) for (const t of (TRANSFORMS[d] || [])) avail.add(t);
  for (const d of done) avail.delete(d);
  return { done, avail };
}

function renderSamples() {
  const g = $("sampleGallery");
  g.innerHTML = "";
  for (const s of state.meta.samples) {
    const item = document.createElement("div");
    item.className = "gitem";
    const img = document.createElement("img");
    img.src = s.url; img.alt = s.label;
    img.className = state.anchor === s.url ? "sel" : "";
    img.onclick = () => setAnchor(s.url);
    const lab = document.createElement("div");
    lab.className = "glabel"; lab.textContent = s.label;
    item.appendChild(img); item.appendChild(lab); g.appendChild(item);
  }
}

function renderConfig() {
  if (!state.currentType) { $("configPanel").hidden = true; return; }
  $("configPanel").hidden = false;
  $("genTypeLabel").textContent = (TYPE_SHORT[state.currentType] || state.currentType) + "图";
  $("skuMeta").innerHTML = skuMetaHtml();
  renderAiSummary();
}

// 本款已选：工作区里已点选的图（一边做一边看的可视状态，可反悔删掉）
function renderSelectedStrip() {
  const strip = $("selStrip");
  const wrap = $("selectedStrip");
  if (!strip) return;
  const types = ["white_bg", "studio", "lifestyle", "detail", "fabric", "model"]
    .filter(t => state.selected[t]);
  if (!types.length) { wrap.hidden = true; strip.innerHTML = ""; return; }
  wrap.hidden = false;
  strip.innerHTML = "";
  for (const t of types) {
    const item = document.createElement("div");
    item.className = "sel-item";
    item.innerHTML = `<img src="${state.selected[t]}"><div class="lab">${TYPE_SHORT[t]}图</div>` +
      `<button class="del" title="移除这张">✕</button>`;
    item.querySelector(".del").onclick = () => {
      delete state.selected[t];
      renderTrack(); renderSelectedStrip(); renderWorkState();
    };
    strip.appendChild(item);
  }
}

function renderDirection() {
  const sel = $("direction");
  sel.innerHTML = "";
  for (const d of Object.keys(state.meta.directions)) {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    if (d === state.meta.mvp.direction) o.selected = true;
    sel.appendChild(o);
  }
}

function currentSku() {
  const dir = $("direction").value;
  const name = $("sku").value;
  return state.meta.directions[dir].skus.find(s => s.name === name);
}

function renderSku() {
  const dir = $("direction").value;
  const sel = $("sku");
  sel.innerHTML = "";
  const skus = state.meta.directions[dir].skus;
  for (const s of skus) {
    const o = document.createElement("option");
    o.value = s.name; o.textContent = s.name;
    if (s.name === state.meta.mvp.sku && dir === state.meta.mvp.direction) o.selected = true;
    sel.appendChild(o);
  }
  renderColorScene();
}

function renderColorScene() {
  const sku = currentSku();
  const c = $("color"); c.innerHTML = "";
  for (const col of sku.colors) {
    const o = document.createElement("option");
    o.value = col.en; o.textContent = col.zh; c.appendChild(o);
  }
  const s = $("scene"); s.innerHTML = "";
  for (const sc of sku.scenes) {
    const o = document.createElement("option");
    o.value = sc.en; o.textContent = sc.zh; s.appendChild(o);
  }
}

function skuMetaHtml() {
  const m = state.recog && state.recog.lib_match;
  if (m) {
    const s = m.sku;
    const p = s.price || {};
    return `✅ 已匹配库内款「${m.name}」（${m.direction}）：成分 ${s.composition || "—"} · 规格 ${s.spec || "—"} · ` +
      `会员价 ${p.currency || "¥"}${p.msrp || "—"} / 供货价 ${p.currency || "¥"}${p.wholesale || "—"}（参数自动带入）`;
  }
  if (state.recog) {
    const s = state.recog.sku;
    return `材质：${s.material || "—"}　·　工艺：${s.craft || "—"}　·　对标：${s.benchmark || "—"}`;
  }
  const sku = currentSku();
  return `材质：${sku.material}　·　工艺：${sku.craft}　·　对标：${sku.benchmark}`;
}

function renderAiSummary() {
  const parts = [];
  if (state.recog && state.recog.summary) {
    parts.push(`<span class="chip"><b>识别</b>${state.recog.summary}</span>`);
  }
  if (state.recog && state.recog.lib_match) {
    parts.push(`<span class="chip"><b>匹配</b>库内款「${state.recog.lib_match.name}」</span>`);
  }
  parts.push(`<span class="chip"><b>图类型</b>${TYPE_SHORT[state.anchorType] || state.anchorType}</span>`);
  parts.push(`<span class="chip"><b>零售商</b>${$("retailer").value}</span>`);
  $("aiSummary").innerHTML = parts.join("");
}

// ---------- 交互 ----------
function updateAnchorPreview(url) {
  const pv = $("anchorPreview");
  if (!pv) return;
  if (url) { pv.src = url; pv.hidden = false; }
  else { pv.src = ""; pv.hidden = true; }
}

function setAnchor(url) {
  state.anchor = url;
  $("anchorStatus").innerHTML = `已选：<span class="ok">${url.split("/").pop()}</span>`;
  updateAnchorPreview(url);
  renderSamples(); renderTrack(); renderWorkState();
  autoRecognize();  // 选好图就自动识别，无需手配
}

async function autoRecognize() {
  if (!state.anchor) { $("anchorStatus").textContent = "请先上传/选一张产品图"; return; }
  const btn = $("btnRecognize");
  btn.disabled = true; btn.textContent = "识别中…";
  try {
    const res = await api("/api/recognize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anchor: state.anchor, direction: $("direction").value }),
    });
    if (res.error) throw new Error(res.error);
    state.recog = res;
    if (res.image_type) { state.anchorType = res.image_type; $("anchorType").value = res.image_type; }
    renderTrack(); renderWorkState(); renderConfig();
    const lib = res.lib_match
      ? `　✅ 已匹配库内款「${res.lib_match.name}」，成分/规格/双价格自动带入`
      : "";
    $("anchorStatus").innerHTML = `识别：<span class="ok">${res.summary || "（已识别）"}</span>${lib}`;
  } catch (err) {
    $("anchorStatus").textContent = "识别失败：" + err.message;
  } finally {
    btn.disabled = false; btn.textContent = "🔍 识别风格/款式";
  }
}

function uploadModel() {
  const fi = $("modelFileInput");
  const f = fi.files[0];
  if (!f) return;
  const fd = new FormData();
  fd.append("file", f);
  $("modelStatus").textContent = "上传中…";
  fetch("/api/upload_model", { method: "POST", body: fd })
    .then(r => r.json())
    .then(res => {
      if (!res.url) throw new Error("服务器未返回地址");
      state.model = res.url;
      const pv = $("modelPreview");
      pv.src = res.url; pv.hidden = false;
      $("modelStatus").textContent = "已上传模特";
      fi.value = "";
    })
    .catch(err => { $("modelStatus").textContent = "上传失败：" + err.message; });
}

function renderVariants(imgs) {
  const g = $("variantGallery");
  g.innerHTML = "";
  for (const u of imgs) {
    const item = document.createElement("div");
    item.className = "gitem";
    const img = document.createElement("img");
    img.src = u;
    img.onclick = () => selectVariant(u);
    const badge = document.createElement("div");
    badge.className = "ck-badge pending";
    badge.textContent = "⏳ 自检中";
    item.appendChild(img); item.appendChild(badge); g.appendChild(item);
    runConsistencyCheck(u, badge);   // 异步挂角标，不挡选图
  }
}

// ---------- 一致性自检（检验③）：锚点原图 vs 生成图，qwen-vl 给 PASS/FAIL 角标 ----------
// 只提示不拦截：自检失败/超时都落「自检不可用」，用户照常选图；结果按图 url 缓存不重复查。
async function runConsistencyCheck(url, badge) {
  if (!state.anchor) { paintCheckBadge(badge, { verdict: "na" }); return; }
  if (state.checks[url]) { paintCheckBadge(badge, state.checks[url]); return; }
  try {
    const res = await api("/api/check_consistency", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: state.anchor, image: url }),
    });
    state.checks[url] = res;
    paintCheckBadge(badge, res);
  } catch (err) {
    paintCheckBadge(badge, { verdict: "na" });
  }
}

function paintCheckBadge(badge, res) {
  if (res.verdict === "PASS") { badge.className = "ck-badge pass"; badge.textContent = "✅ 与原图一致"; }
  else if (res.verdict === "FAIL") { badge.className = "ck-badge fail"; badge.textContent = "⚠️ " + (res.reason || "与原图有出入"); }
  else { badge.className = "ck-badge na"; badge.textContent = "自检不可用"; }
}

function selectVariant(url) {
  state.selected[state.variantType] = url;
  state.currentType = null;
  state.variants = [];
  $("resultPanel").hidden = true;
  $("configPanel").hidden = true;
  renderTrack(); renderSelectedStrip(); renderWorkState();
}

// ---------- 公共：提交后台任务 + 轮询结果（出图 / 演变 / 封面三处共用，家规见 CLAUDE.md） ----------
// opts: { url, body, btn, status, loading, waiting, doneLabel, onElapsed(sec), onDone(res, statusEl) }
// 后端断开/双开时状态查询会失败：连续 5 次（约 10 秒）仍不通就明确报错，不再无限转圈
const POLL_MS = 2000, POLL_MAX_FAILS = 5;

async function runJob(opts) {
  const btn = $(opts.btn), st = $(opts.status);
  btn.disabled = true;
  st.className = "gen-status loading";
  st.textContent = opts.loading;
  let res;
  try {
    res = await api(opts.url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts.body),
    });
  } catch (err) {
    btn.disabled = false;
    st.className = "gen-status error";
    st.textContent = "提交失败（后端未响应）：" + err.message;
    return;
  }
  const pollOnce = async (jobId, fails) => {
    let r;
    try {
      r = await api("/api/status/" + jobId);
      fails = 0;
    } catch (err) {
      if (++fails < POLL_MAX_FAILS) { setTimeout(() => pollOnce(jobId, fails), POLL_MS); return; }
      btn.disabled = false;
      st.className = "gen-status error";
      st.textContent = "查询生成状态连续失败（后端可能断开或重启了）：" + err.message;
      return;
    }
    if (!r.done) {
      st.textContent = opts.waiting || "生成中…请稍候";
      setTimeout(() => pollOnce(jobId, fails), POLL_MS);
      return;
    }
    btn.disabled = false;
    if (r.error) {
      st.className = "gen-status error";
      st.textContent = (opts.doneLabel || "生成") + "失败：" + r.error;
      return;
    }
    if (r.elapsed && opts.onElapsed) { opts.onElapsed(r.elapsed); renderWorkState(); }
    st.className = "gen-status";
    opts.onDone(r, st);
  };
  pollOnce(res.job_id, 0);
}

// ---------- 生成（一边做一边看：生成 → 看图 → 人工点选） ----------
async function generate() {
  const sku = effectiveSku();
  const colorEn = state.recog ? state.recog.color_en : $("color").value;
  const sceneEn = state.recog ? state.recog.scene_en : $("scene").value;
  runJob({
    url: "/api/generate",
    body: {
      target: state.currentType,
      sku: sku,
      direction: $("direction").value,
      anchor: state.anchor,
      model: SCENE_TYPES.includes(state.currentType) ? state.model : null,
      color_en: colorEn,
      scene_en: sceneEn,
      retailer: $("retailer").value,
      count: parseInt($("count").value, 10),
      style_hint: ($("planStyle") && $("planStyle").value.trim()) || "",
    },
    btn: "btnGenerate", status: "genStatus",
    loading: "提交生成中…（pro 模型，约 1–3 分钟/张）",
    waiting: "生成中…请稍候",
    doneLabel: "生成",
    onElapsed: (sec) => { state.timing.images_sec += sec; },
    onDone: (r, st) => {
      const tookTxt = r.elapsed ? `（用时 ${r.elapsed} 秒）` : "";
      st.textContent = r.no_ref
        ? `生成完成${tookTxt}（⚠️ 本次无原图参考，按文字推断生成，面料/颜色可能与实物不符）：`
        : `生成完成${tookTxt}，请在下方点选 1 张：`;
      state.variantType = state.currentType;
      state.variants = r.images;
      $("resultPanel").hidden = false;
      renderVariants(r.images);
    },
  });
}

// ---------- 演变（出相似款）----------
const VAR_AXIS_LABEL = { color: "改色", detail: "改细节", silhouette: "改廓形" };

function renderVariationCompare(v) {
  // 生成即归属本款：不需要单独的「归纳」开关，纳入企划盘时自动带上
  state.variation = v;
  $("varBefore").src = v.before;
  $("varAfter").src = v.after;
  $("varAfterCap").textContent = `演变款（${VAR_AXIS_LABEL[v.axis] || v.axis}${v.change ? "：" + v.change : ""}）`;
  $("varCompare").hidden = false;
  $("varActions").hidden = false;
}

function discardVariation() {
  state.variation = null;
  $("varCompare").hidden = true;
  $("varActions").hidden = true;
  $("varStatus").textContent = "已丢弃这组演变，可重新生成";
}

async function doVariation() {
  if (!state.anchor) { $("varStatus").textContent = "请先在「① 起盘」选/传一张畅销款参考图"; return; }
  runJob({
    url: "/api/variation",
    body: {
      sku: effectiveSku(),
      direction: $("direction").value,
      anchor: state.anchor,
      axis: $("varAxis").value,
      change: $("varChange").value.trim(),
      color_en: state.recog ? state.recog.color_en : $("color").value,
    },
    btn: "btnVariation", status: "varStatus",
    loading: "提交演变生成中…（3 案，pro 模型，约 1–3 分钟）",
    waiting: "演变生成中…请稍候",
    doneLabel: "演变生成",
    onElapsed: (sec) => { state.timing.evolve_sec += sec; },
    onDone: (r, st) => {
      const took = r.elapsed ? `（用时 ${r.elapsed} 秒）` : "";
      // 一轴多案（扩展⑥）：多张走候选条挑 1，单张（旧结果/兜底）直接进对比
      if (r.images.length > 1) {
        st.textContent = `演变候选已出${took}：点一张定为演变款`;
        renderVarCandidates(r.images);
        return;
      }
      st.textContent = `演变生成完成${took}，已生成 before/after 对比`;
      renderVariationCompare({
        before: state.anchor,
        after: r.images[0],
        axis: $("varAxis").value,
        change: $("varChange").value.trim(),
      });
    },
  });
}

function renderVarCandidates(imgs) {
  const wrap = $("varCandidates"), strip = $("varCandStrip");
  strip.innerHTML = "";
  imgs.forEach((u, i) => {
    const d = document.createElement("div");
    d.className = "cand";
    const img = document.createElement("img");
    img.src = u; img.title = "点此定为演变款";
    const lab = document.createElement("div");
    lab.className = "no"; lab.textContent = `案 ${i + 1}`;
    img.onclick = () => {
      wrap.hidden = true;
      renderVariationCompare({
        before: state.anchor,
        after: u,
        axis: $("varAxis").value,
        change: $("varChange").value.trim(),
      });
    };
    d.appendChild(img); d.appendChild(lab); strip.appendChild(d);
  });
  wrap.hidden = false;
}

// ---------- 企划盘：纳入 / 渲染 / 重开 / 移除 ----------
// ---------- 本地暂存（保险⑤）：刷新/误关浏览器不丢企划盘 ----------
// 只存「已纳入的成果」（planSkus/耗时/封面/整体风格），工作区的半成品不存。
// 生成的图片都落盘在 images/output/，url 不变，刷新后照样显示。
const STORE_KEY = "planDeck.v1";

function saveState() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({
      planSkus: state.planSkus,
      timing: state.timing,
      cover: state.cover,
      coverCandidates: state.coverCandidates,
      planStyle: ($("planStyle") && $("planStyle").value.trim()) || "",
    }));
  } catch (err) { /* 暂存失败不影响主流程（隐私模式/容量满） */ }
}

function restoreState() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return false;
    const d = JSON.parse(raw);
    if (!d || !Array.isArray(d.planSkus) || !d.planSkus.length) return false;
    state.planSkus = d.planSkus;
    state.timing = d.timing || { evolve_sec: 0, images_sec: 0 };
    state.cover = d.cover || null;
    state.coverCandidates = d.coverCandidates || [];
    if (d.planStyle && $("planStyle")) $("planStyle").value = d.planStyle;
    return true;
  } catch (err) { return false; }
}

function intoPlan() {
  if (Object.keys(state.selected).length === 0) return;
  const sku = effectiveSku();
  const colorZh = state.recog ? (state.recog.color_zh || "") : ($("color").selectedOptions[0] ? $("color").selectedOptions[0].textContent : "");
  const colorEn = state.recog ? state.recog.color_en : $("color").value;
  const entry = {
    sku: sku,
    colorZh: colorZh, colorEn: colorEn,
    direction: $("direction").value,
    retailer: $("retailer").value,
    selected: { ...state.selected },
    variation: state.variation ? { ...state.variation } : null,
  };
  const i = state.planSkus.findIndex(e => e.sku.name === entry.sku.name);
  if (i >= 0) state.planSkus[i] = entry; else state.planSkus.push(entry);
  fetchSkuCopy(entry);  // 扩展⑦：异步补一句买手导语，成了再刷新

  // 工作区清空，准备下一款（保留 风格/零售商/模特图/耗时累计）
  state.anchor = null; state.anchorType = "white_bg"; state.currentType = null;
  state.selected = {}; state.recog = null;
  state.variation = null;
  updateAnchorPreview(null);
  $("anchorStatus").textContent = "未选择产品图";
  $("anchorType").value = "white_bg";
  $("configPanel").hidden = true; $("resultPanel").hidden = true;
  $("varCompare").hidden = true; $("varActions").hidden = true; $("varStatus").textContent = "";
  $("genStatus").textContent = "";
  $("foldDone").open = true;
  saveState();
  renderSamples(); renderTrack(); renderSelectedStrip(); renderWorkState();
  renderPlanStack(); renderPlanSkus();
}

// 买手导语（扩展⑦）：纳入后异步生成一句卖点，写成 entry.copy；失败静默跳过
function fetchSkuCopy(entry) {
  if (entry.copy) return;
  api("/api/sku_copy", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sku: entry.sku, color_zh: entry.colorZh, direction: entry.direction,
      retailer: entry.retailer, has_variation: !!entry.variation,
    }),
  }).then(res => {
    if (!res.copy) return;   // 导语缺位不打扰用户
    entry.copy = res.copy;
    saveState(); renderPlanStack();
  }).catch(() => { /* 导语缺位不影响企划盘 */ });
}

// 成品堆叠：确认过的款按顺序堆在这里（最新在最上），每块只放这款生成的图 + 演变对比
function renderPlanStack() {
  const wrap = $("doneStack");
  if (!wrap) return;
  wrap.innerHTML = "";
  if (!state.planSkus.length) {
    wrap.innerHTML = '<p class="hint">还没有确认的款。在「② 逐款出图」生成并点选图片后，点「✅ 本款完成 · 纳入企划盘」，这款的成品版块就会堆到这里。</p>';
    return;
  }
  [...state.planSkus].reverse().forEach((e, r) => {
    const i = state.planSkus.length - 1 - r;
    const d = document.createElement("details");
    d.className = "sku-entry";
    if (r === 0) d.open = true;
    const types = Object.keys(e.selected).map(t => TYPE_SHORT[t] || t).join(" / ");
    d.innerHTML = `<summary><span class="dot">●</span> ${escapeHtml(e.sku.name || "未命名款")}` +
      `${e.colorZh ? `（${escapeHtml(e.colorZh)}）` : ""}<span class="cnt">${Object.keys(e.selected).length} 类图 · ${types}${e.variation ? " · 含演变" : ""}</span></summary>`;
    const body = document.createElement("div");
    body.className = "sku-entry-body";
    const g = document.createElement("div");
    g.className = "gallery";
    for (const [t, u] of Object.entries(e.selected)) {
      const item = document.createElement("div");
      item.className = "gitem";
      const img = document.createElement("img");
      img.src = u; img.title = TYPE_SHORT[t] || t;
      const lab = document.createElement("div");
      lab.className = "glabel"; lab.textContent = (TYPE_SHORT[t] || t) + "图";
      item.appendChild(img); item.appendChild(lab); g.appendChild(item);
    }
    body.appendChild(g);
    if (e.copy) {
      const c = document.createElement("div");
      c.className = "sku-copy";
      c.textContent = `🗣 买手导语：${e.copy}`;
      body.insertBefore(c, g);
    }
    if (e.variation) {
      const cmp = document.createElement("div");
      cmp.className = "compare mini-compare";
      cmp.innerHTML = `<figure><img src="${e.variation.before}"><figcaption>畅销款（起点）</figcaption></figure>` +
        `<span class="arrow">→</span>` +
        `<figure><img src="${e.variation.after}"><figcaption>演变款（${VAR_AXIS_LABEL[e.variation.axis] || e.variation.axis}）</figcaption></figure>`;
      body.appendChild(cmp);
    }
    const acts = document.createElement("div");
    acts.className = "sku-entry-actions";
    const mk = (txt, fn, cls) => {
      const b = document.createElement("button");
      b.className = "btn " + (cls || "ghost"); b.textContent = txt; b.onclick = fn;
      acts.appendChild(b);
    };
    mk("✏️ 重开编辑", () => reopenSkuEntry(i));
    mk("🗑 移除", () => removePlanSku(i));
    body.appendChild(acts);
    d.appendChild(body);
    wrap.appendChild(d);
  });
}

function removePlanSku(i) {
  state.planSkus.splice(i, 1);
  saveState();
  renderPlanStack(); renderPlanSkus(); renderWorkState();
}

// ③ 企划盘汇总：紧凑列表（大图在上方成品堆叠里，这里只汇总看结构）
function renderPlanSkus() {
  const wrap = $("planSkusList");
  wrap.innerHTML = "";
  if (!state.planSkus.length) {
    wrap.innerHTML = '<p class="hint">还没有款纳入。成品版块在上方「✅ 成品堆叠」里，这里汇总全盘。</p>';
    return;
  }
  state.planSkus.forEach((e, i) => {
    const row = document.createElement("div");
    row.className = "plan-row";
    const types = Object.keys(e.selected).map(t => TYPE_SHORT[t] || t).join("/");
    row.innerHTML = `<span class="dot">●</span> <b>${escapeHtml(e.sku.name || "未命名款")}</b>` +
      `${e.colorZh ? `（${escapeHtml(e.colorZh)}）` : ""}` +
      `<span class="cnt">${Object.keys(e.selected).length} 类图 · ${types}${e.variation ? " · 含演变" : ""}</span>`;
    wrap.appendChild(row);
  });
}

function reopenSkuEntry(i) {
  const e = state.planSkus[i];
  state.planSkus.splice(i, 1);
  saveState();
  // 条目回填工作区（识别结果不再有：直接用条目里存好的生效 sku）
  state.anchor = Object.values(e.selected)[0];
  state.anchorType = Object.keys(e.selected)[0];
  state.selected = { ...e.selected };
  state.recog = null;
  state.variation = e.variation ? { ...e.variation } : null;
  if (e.direction) $("direction").value = e.direction;
  renderSku();
  updateAnchorPreview(state.anchor);
  $("anchorStatus").innerHTML = `编辑中：<span class="ok">${escapeHtml(e.sku.name || "")}</span>（企划盘条目已取回）`;
  $("foldWork").open = true;
  renderSamples(); renderTrack(); renderSelectedStrip(); renderWorkState();
  renderPlanStack(); renderPlanSkus();
  renderVariationCompareIfAny();
}

function renderVariationCompareIfAny() {
  if (state.variation) renderVariationCompare(state.variation);
}

// ---------- 右侧总览板块 ----------
function renderOverview() {
  const ul = $("deckChecklist");
  if (!ul) return;
  ul.innerHTML = "";
  const n = state.planSkus.length;
  const items = [
    ["P01 封面", true, state.cover ? "已选封面" : "默认首图"],
    ["P02 企划方法", true, ""],
    ["P03 人群画像", true, ""],
    ["P04 产品结构总表", n > 0, n > 0 ? `${n} 款` : "待纳入"],
    ["P05+ 逐款页", n > 0, n > 0 ? `× ${n}` : "待纳入"],
  ];
  const varCnt = state.planSkus.filter(e => e.variation).length;
  if (n > 0) items.push(["P06+ 演变对比", varCnt > 0, varCnt > 0 ? `× ${varCnt}` : "无演变记录"]);
  items.push(["品类矩阵", n > 0, ""], ["AI 出图体系", n > 0, ""], ["开发日历", true, ""], ["尾页 · 实测耗时", state.timing.images_sec + state.timing.evolve_sec > 0, ""]);
  for (const [name, ok, tag] of items) {
    const li = document.createElement("li");
    if (ok) li.className = "done";
    li.innerHTML = `<span><span class="mark">${ok ? "●" : "○"}</span>${name}</span>` +
      (tag ? `<span class="pageno">${tag}</span>` : "");
    ul.appendChild(li);
  }

  const skusEl = $("overviewSkus");
  skusEl.innerHTML = "";
  state.planSkus.forEach((e, i) => {
    const row = document.createElement("div");
    row.className = "ov-sku";
    const img = document.createElement("img");
    img.src = Object.values(e.selected)[0];
    const info = document.createElement("div");
    info.className = "info";
    info.innerHTML = `<div class="nm">${escapeHtml(e.sku.name || "未命名款")}${e.colorZh ? ` · ${escapeHtml(e.colorZh)}` : ""}</div>` +
      `<div class="meta">${Object.keys(e.selected).length} 类图${e.variation ? " · 含演变" : ""}</div>`;
    const del = document.createElement("button");
    del.textContent = "移除"; del.title = "从企划盘移除";
    del.onclick = () => removePlanSku(i);
    row.appendChild(img); row.appendChild(info); row.appendChild(del);
    skusEl.appendChild(row);
  });

  const t = state.timing;
  const total = t.evolve_sec + t.images_sec;
  $("overviewTiming").textContent = total > 0
    ? `⚡ 实测累计：${t.evolve_sec ? `演变 ${t.evolve_sec}s · ` : ""}出图 ${t.images_sec}s · 合计约 ${Math.max(1, Math.round(total / 60))} 分钟`
    : "尚无实测耗时（生成后自动累计）";
}

// ---------- deck 封面：从各款氛围图里挑，或用已完成图再生成一张 ----------
function coverRefPool() {
  // 封面参考图池：优先各款氛围图；一款都没有时回退到每款的第一张图
  const lifestyle = state.planSkus.filter(e => e.selected.lifestyle)
    .map(e => ({ url: e.selected.lifestyle, label: `${e.sku.name || "款"} · 氛围图` }));
  if (lifestyle.length) return lifestyle;
  return state.planSkus.map(e => ({ url: Object.values(e.selected)[0], label: `${e.sku.name || "款"} · 首图` }));
}

function renderCover() {
  const pick = $("coverPick");
  if (!pick) return;
  pick.innerHTML = "";
  const pool = coverRefPool();
  const cands = pool.map(p => ({ ...p, kind: "ref" }))
    .concat(state.coverCandidates.map((u, i) => ({ url: u, label: `生成封面 ${i + 1}`, kind: "gen" })));
  if (!cands.length) { $("btnGenCover").disabled = true; return; }
  $("btnGenCover").disabled = state.planSkus.length === 0;
  for (const c of cands) {
    const item = document.createElement("div");
    item.className = "cv-item";
    const img = document.createElement("img");
    img.src = c.url; img.title = c.label;
    if (state.cover === c.url) img.classList.add("sel");
    img.onclick = () => {
      state.cover = state.cover === c.url ? null : c.url;
      saveState();
      renderCover();
    };
    const lab = document.createElement("div");
    lab.className = "glabel"; lab.textContent = c.label;
    item.appendChild(img); item.appendChild(lab); pick.appendChild(item);
  }
}

async function genCover() {
  const pool = coverRefPool();
  if (!pool.length) return;
  runJob({
    url: "/api/cover",
    body: {
      direction: $("direction").value,
      style_hint: ($("planStyle") && $("planStyle").value.trim()) || "",
      refs: pool.map(p => p.url),
      skus: state.planSkus.map(e => ({ name: e.sku.name, en: e.sku.en })),
    },
    btn: "btnGenCover", status: "coverStatus",
    loading: "封面生成中…（pro 模型，约 1–3 分钟）",
    waiting: "封面生成中…请稍候",
    doneLabel: "封面生成",
    onDone: (r, st) => {
      st.textContent = "封面候选已出，点上面一张设为封面";
      state.coverCandidates.push(...r.images);
      saveState();
      renderCover();
    },
  });
}

// ---------- 导出（企划盘多款） ----------
async function doExport() {
  if (!state.planSkus.length) return;
  const t = state.timing;
  const totalMin = Math.round((t.evolve_sec + t.images_sec) / 60);
  const body = {
    direction: $("direction").value,
    retailer: $("retailer").value,
    skus: state.planSkus.map(e => ({
      sku: e.sku,
      color: e.colorZh || "",
      selected: e.selected,
      variation: e.variation,
      copy: e.copy || null,  // 买手导语（扩展⑦）
    })),
    cover: state.cover,  // P01 封面（氛围图挑的或再生成）；null 时导出用首款首图版式
    plan_style: ($("planStyle") && $("planStyle").value.trim()) || "",
    timing: totalMin > 0 ? { ...t, total_min: totalMin } : { ...t },
  };
  $("btnExport").textContent = "导出中…";
  $("btnExport").disabled = true;
  let res;
  try {
    res = await api("/api/export", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch (err) {
    $("btnExport").textContent = "📦 导出完整企划 deck";
    $("btnExport").disabled = false;
    alert("导出失败（后端未响应）：" + err.message);
    return;
  }
  $("btnExport").textContent = "📦 导出完整企划 deck";
  $("btnExport").disabled = false;
  if (res.error) { alert("导出失败：" + res.error); return; }
  const row = $("exportRow");
  row.innerHTML = "";
  const mk = (txt, href, name) => {
    const a = document.createElement("a");
    a.className = "btn primary"; a.href = href; a.download = name; a.textContent = txt;
    row.appendChild(a);
  };
  mk("⬇ HTML 企划盘", res.html, res.html.split("/").pop());
  mk("⬇ PPT deck", res.pptx, res.pptx.split("/").pop());
  const frame = $("previewFrame");
  frame.hidden = false;
  frame.src = res.html;
}

// ---------- 示例 / 重置 ----------
function loadSample() {
  state.anchor = DEMO.white_bg;
  state.anchorType = "white_bg";
  state.selected = { ...DEMO };
  state.currentType = null; state.recog = null;
  updateAnchorPreview(DEMO.white_bg);
  $("anchorStatus").innerHTML = `已选：<span class="ok">示例 · 山羊绒围巾（4 类图已就绪）</span>`;
  $("configPanel").hidden = true; $("resultPanel").hidden = true;
  $("foldWork").open = true;
  renderSamples(); renderTrack(); renderSelectedStrip(); renderWorkState();
}

function reset() {
  Object.assign(state, { anchor: null, anchorType: "white_bg", model: null, currentType: null,
    selected: {}, variants: [], variation: null, recog: null,
    planSkus: [], timing: { evolve_sec: 0, images_sec: 0 },
    cover: null, coverCandidates: [], checks: {} });
  try { localStorage.removeItem(STORE_KEY); } catch (err) { /* 忽略 */ }
  updateAnchorPreview(null);
  const mp = $("modelPreview"); if (mp) { mp.src = ""; mp.hidden = true; }
  $("modelStatus").textContent = "";
  $("anchorStatus").textContent = "未选择产品图";
  $("anchorType").value = "white_bg";
  $("configPanel").hidden = true; $("resultPanel").hidden = true;
  $("previewFrame").hidden = true;
  $("exportRow").innerHTML = "";
  $("varCompare").hidden = true; $("varActions").hidden = true; $("varStatus").textContent = "";
  $("coverStatus").textContent = "";
  renderSamples(); renderTrack(); renderSelectedStrip(); renderWorkState();
  renderPlanStack(); renderPlanSkus();
}

// ---------- 绑定 & 启动 ----------
function init() {
  $("btnSample").onclick = loadSample;
  $("btnReset").onclick = reset;
  $("btnGenerate").onclick = generate;
  $("btnExport").onclick = doExport;
  $("btnVariation").onclick = doVariation;
  $("btnVarDiscard").onclick = discardVariation;
  $("btnGenCover").onclick = genCover;
  $("btnIntoPlan").onclick = intoPlan;
  $("direction").onchange = () => { renderSku(); renderConfig(); renderWorkState(); };
  $("sku").onchange = () => { renderColorScene(); $("skuMeta").innerHTML = skuMetaHtml(); };
  $("uploadZone").onclick = () => $("fileInput").click();
  $("btnRecognize").onclick = autoRecognize;
  $("planStyle").addEventListener("change", saveState);  // 整体风格也是暂存内容之一
  $("btnUploadModel").onclick = () => $("modelFileInput").click();
  $("modelFileInput").onchange = uploadModel;
  $("fileInput").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    $("anchorStatus").textContent = "上传中…";
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await fetch("/api/upload", { method: "POST", body: fd });
      const res = await r.json();
      if (!res.url) throw new Error("服务器未返回图片地址");
      setAnchor(res.url);
    } catch (err) {
      $("anchorStatus").textContent = "上传失败：" + err.message;
    }
  };

  // 锚点类型下拉
  const at = $("anchorType");
  at.innerHTML = "";
  for (const t of TYPE_ORDER) {
    const o = document.createElement("option");
    o.value = t; o.textContent = TYPE_SHORT[t]; at.appendChild(o);
  }
  at.onchange = () => { state.anchorType = at.value; renderTrack(); renderWorkState(); };

  // 零售商
  $("retailer").innerHTML = "";
  for (const r of state.meta.retailers) {
    const o = document.createElement("option");
    o.value = r; o.textContent = r; $("retailer").appendChild(o);
  }

  renderDirection();
  renderSku();

  // 保险⑤：上次会话纳入过的款，刷新后原样回来（图片都落盘过，url 仍有效）
  if (restoreState()) {
    $("foldDone").open = true;
    $("foldPlan").open = true;
    $("anchorStatus").innerHTML = `<span class="ok">已恢复上次会话的企划盘（${state.planSkus.length} 款）</span>，上传新图继续加款`;
  }

  renderTrack(); renderWorkState(); renderPlanStack(); renderPlanSkus();
}

(async () => {
  checkApiHealth();  // 不阻塞页面：先体检，红了也不影响用户看界面
  state.meta = await api("/api/meta");
  init();
  renderSamples();
})();
