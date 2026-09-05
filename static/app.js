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
  selected: {},        // type -> url
  jobId: null, timer: null,
  variation: null, variationInPlan: false,
  varJobId: null, varTimer: null,
  recog: null,          // 客观识别结果（自由格式，不套用数据库）
  timing: { evolve_sec: 0, images_sec: 0 },  // 实测耗时累计 → 导出尾页「耗时拆解」
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

// ---------- 渲染 ----------
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

function renderStatus() {
  const { done, avail } = computeStates();
  const ul = $("planStatus");
  ul.innerHTML = "";
  for (const t of TYPE_ORDER) {
    const li = document.createElement("li");
    if (done.has(t)) { li.className = "done"; li.innerHTML = `<span class="mark">●</span> ${TYPE_SHORT[t]} 已生成`; }
    else if (avail.has(t)) li.innerHTML = `<span class="mark">○</span> ${TYPE_SHORT[t]} 可点`;
    else li.innerHTML = `<span class="mark">✕</span> ${TYPE_SHORT[t]}`;
    ul.appendChild(li);
  }
  const n = Object.keys(state.selected).length;
  $("btnExport").disabled = (n === 0);
  // 实测耗时：有数据就展示（演示时这是「Agent 真跑出来的数字」）
  const t = state.timing;
  if (t.images_sec || t.evolve_sec) {
    const li = document.createElement("li");
    li.className = "done";
    const parts = [];
    if (t.evolve_sec) parts.push(`演变 ${t.evolve_sec}s`);
    if (t.images_sec) parts.push(`出图 ${t.images_sec}s`);
    li.innerHTML = `<span class="mark">⚡</span> 实测累计：${parts.join(" · ")}`;
    ul.appendChild(li);
  }
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
  $("skuMeta").innerHTML = skuMetaHtml();
  renderAiSummary();
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
  renderSamples(); renderTrack(); renderStatus();
  autoRecognize();  // 选好图就自动识别，无需手配
}

async function autoRecognize() {
  if (!state.anchor) { $("anchorStatus").textContent = "请先上传/选一张产品图"; return; }
  const btn = $("btnRecognize");
  btn.disabled = true; btn.textContent = "识别中…";
  try {
    const res = await api("/api/recognize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anchor: state.anchor }),
    });
    if (res.error) throw new Error(res.error);
    state.recog = res;
    if (res.image_type) { state.anchorType = res.image_type; $("anchorType").value = res.image_type; }
    renderTrack(); renderStatus(); renderConfig();
    $("anchorStatus").innerHTML = `识别：<span class="ok">${res.summary || "（已识别）"}</span>`;
  } catch (err) {
    $("anchorStatus").textContent = "识别失败：" + err.message;
  } finally {
    btn.disabled = false; btn.textContent = "🔍 重新识别";
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
    item.appendChild(img); g.appendChild(item);
  }
}

function selectVariant(url) {
  state.selected[state.variantType] = url;
  state.currentType = null;
  state.variants = [];
  $("resultPanel").hidden = true;
  renderTrack(); renderStatus();
}

async function generate() {
  const recog = state.recog;
  const sku = recog ? recog.sku : currentSku();
  const colorEn = recog ? recog.color_en : $("color").value;
  const sceneEn = recog ? recog.scene_en : $("scene").value;
  const body = {
    target: state.currentType,
    sku: sku,
    direction: $("direction").value,
    anchor: state.anchor,
    model: SCENE_TYPES.includes(state.currentType) ? state.model : null,
    color_en: colorEn,
    scene_en: sceneEn,
    retailer: $("retailer").value,
    count: parseInt($("count").value, 10),
  };
  $("genStatus").className = "gen-status loading";
  $("genStatus").textContent = "提交生成中…（约 20–60 秒/张）";
  $("btnGenerate").disabled = true;
  let res;
  try {
    res = await api("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch (err) {
    $("btnGenerate").disabled = false;
    $("genStatus").className = "gen-status error";
    $("genStatus").textContent = "提交失败（后端未响应）：" + err.message;
    return;
  }
  state.jobId = res.job_id;
  poll();
}

async function poll() {
  // 后端断开/双开时状态查询会失败：连续 5 次（约 10 秒）仍不通就明确报错，不再无限转圈
  let res;
  try {
    res = await api("/api/status/" + state.jobId);
    state.pollFails = 0;
  } catch (err) {
    state.pollFails = (state.pollFails || 0) + 1;
    if (state.pollFails < 5) { state.timer = setTimeout(poll, 2000); return; }
    $("btnGenerate").disabled = false;
    $("genStatus").className = "gen-status error";
    $("genStatus").textContent = "查询生成状态连续失败（后端可能断开或重启了）：" + err.message;
    return;
  }
  if (res.done) {
    $("btnGenerate").disabled = false;
    if (res.error) {
      $("genStatus").className = "gen-status error";
      $("genStatus").textContent = "生成失败：" + res.error;
      return;
    }
    $("genStatus").className = "gen-status";
    const tookTxt = res.elapsed ? `（用时 ${res.elapsed} 秒）` : "";
    if (res.elapsed) { state.timing.images_sec += res.elapsed; renderStatus(); }
    $("genStatus").textContent = res.no_ref
      ? `生成完成${tookTxt}（⚠️ 本次无原图参考，按文字推断生成，面料/颜色可能与实物不符）：`
      : `生成完成${tookTxt}，请在下方点选 1 张：`;
    state.variantType = state.currentType;
    state.variants = res.images;
    $("resultPanel").hidden = false;
    renderVariants(res.images);
  } else {
    $("genStatus").textContent = "生成中…请稍候";
    state.timer = setTimeout(poll, 2000);
  }
}

// ---------- 演变（出相似款）----------
const VAR_AXIS_LABEL = { color: "改色", detail: "改细节", silhouette: "改廓形" };

function renderVariationCompare(v) {
  state.variation = v;
  $("varBefore").src = v.before;
  $("varAfter").src = v.after;
  $("varAfterCap").textContent = `演变款（${VAR_AXIS_LABEL[v.axis] || v.axis}${v.change ? "：" + v.change : ""}）`;
  $("varCompare").hidden = false;
  state.variationInPlan = true;
  const b = $("btnVarIntoPlan");
  b.hidden = false;
  b.className = "btn primary block";
  b.textContent = "✅ 已归纳进企划（导出会带上 before/after）";
}

async function doVariation() {
  if (!state.anchor) { $("varStatus").textContent = "请先在「① 起盘」选/传一张畅销款参考图"; return; }
  const recog = state.recog;
  const sku = recog ? recog.sku : currentSku();
  const colorEn = recog ? recog.color_en : $("color").value;
  const body = {
    sku: sku,
    direction: $("direction").value,
    anchor: state.anchor,
    axis: $("varAxis").value,
    change: $("varChange").value.trim(),
    color_en: colorEn,
  };
  $("varStatus").className = "gen-status loading";
  $("varStatus").textContent = "提交演变生成中…（约 20–60 秒）";
  $("btnVariation").disabled = true;
  let res;
  try {
    res = await api("/api/variation", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch (err) {
    $("btnVariation").disabled = false;
    $("varStatus").className = "gen-status error";
    $("varStatus").textContent = "提交失败（后端未响应）：" + err.message;
    return;
  }
  state.varJobId = res.job_id;
  pollVariation();
}

async function pollVariation() {
  let res;
  try {
    res = await api("/api/status/" + state.varJobId);
    state.varPollFails = 0;
  } catch (err) {
    state.varPollFails = (state.varPollFails || 0) + 1;
    if (state.varPollFails < 5) { state.varTimer = setTimeout(pollVariation, 2000); return; }
    $("btnVariation").disabled = false;
    $("varStatus").className = "gen-status error";
    $("varStatus").textContent = "查询演变状态连续失败（后端可能断开或重启了）：" + err.message;
    return;
  }
  if (res.done) {
    $("btnVariation").disabled = false;
    if (res.error) {
      $("varStatus").className = "gen-status error";
      $("varStatus").textContent = "演变生成失败：" + res.error;
      return;
    }
    $("varStatus").className = "gen-status";
    if (res.elapsed) { state.timing.evolve_sec += res.elapsed; renderStatus(); }
    $("varStatus").textContent = `演变生成完成${res.elapsed ? `（用时 ${res.elapsed} 秒）` : ""}，已生成 before/after 对比`;
    renderVariationCompare({
      before: state.anchor,
      after: res.images[0],
      axis: $("varAxis").value,
      change: $("varChange").value.trim(),
    });
  } else {
    $("varStatus").textContent = "演变生成中…请稍候";
    state.varTimer = setTimeout(pollVariation, 2000);
  }
}

function toggleVarIntoPlan() {
  if (!state.variation) return;
  state.variationInPlan = !state.variationInPlan;
  const b = $("btnVarIntoPlan");
  b.className = state.variationInPlan ? "btn primary block" : "btn ghost block";
  b.textContent = state.variationInPlan ? "✅ 已归纳进企划（导出会带上 before/after）" : "➕ 归纳进企划（导出时带上 before/after）";
}

async function doExport() {
  const recog = state.recog;
  const sku = recog ? recog.sku : currentSku();
  const color = recog ? recog.color_zh : $("color").selectedOptions[0].textContent;
  const body = {
    direction: $("direction").value,
    sku: sku,
    retailer: $("retailer").value,
    color: color,
    selected: state.selected,
    variation: state.variationInPlan ? state.variation : null,
    timing: state.timing,  // 实测耗时 → 导出尾页「耗时拆解」
  };
  $("btnExport").textContent = "导出中…";
  const res = await api("/api/export", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  $("btnExport").textContent = "📦 导出企划";
  const row = $("exportRow");
  row.innerHTML = "";
  const mk = (txt, href, name) => {
    const a = document.createElement("a");
    a.className = "btn primary"; a.href = href; a.download = name; a.textContent = txt;
    row.appendChild(a);
  };
  mk("⬇ 下载 HTML 企划页", res.html, res.html.split("/").pop());
  mk("⬇ 下载 PPT 推介页", res.pptx, res.pptx.split("/").pop());
  $("exportPanel").hidden = false;
  const frame = $("previewFrame");
  frame.hidden = false;
  frame.src = res.html;
}

function loadSample() {
  state.anchor = DEMO.white_bg;
  state.anchorType = "white_bg";
  state.selected = { ...DEMO };
  state.currentType = null; state.recog = null; state.model = null;
  const mp0 = $("modelPreview"); if (mp0) { mp0.src = ""; mp0.hidden = true; }
  $("modelStatus").textContent = "";
  updateAnchorPreview(DEMO.white_bg);
  $("anchorStatus").innerHTML = `已选：<span class="ok">示例 · 山羊绒围巾（4 类图已就绪）</span>`;
  renderSamples(); renderTrack(); renderStatus();
  $("configPanel").hidden = true; $("resultPanel").hidden = true;
  $("exportPanel").hidden = true;
}

function reset() {
  Object.assign(state, { anchor: null, anchorType: "white_bg", model: null, currentType: null,
    selected: {}, jobId: null, variants: [], variation: null, variationInPlan: false, recog: null,
    timing: { evolve_sec: 0, images_sec: 0 } });
  updateAnchorPreview(null);
  const mp = $("modelPreview"); if (mp) { mp.src = ""; mp.hidden = true; }
  $("modelStatus").textContent = "";
  $("anchorStatus").textContent = "未选择产品图";
  $("configPanel").hidden = true; $("resultPanel").hidden = true; $("exportPanel").hidden = true;
  $("previewFrame").hidden = true;
  $("varCompare").hidden = true; $("btnVarIntoPlan").hidden = true; $("varStatus").textContent = "";
  renderSamples(); renderTrack(); renderStatus();
}

// ---------- 绑定 & 启动 ----------
function init() {
  $("btnSample").onclick = loadSample;
  $("btnReset").onclick = reset;
  $("btnGenerate").onclick = generate;
  $("btnExport").onclick = doExport;
  $("btnVariation").onclick = doVariation;
  $("btnVarIntoPlan").onclick = toggleVarIntoPlan;
  $("direction").onchange = () => { renderSku(); renderConfig(); };
  $("sku").onchange = () => { renderColorScene(); $("skuMeta").innerHTML = skuMetaHtml(); };
  $("uploadZone").onclick = () => $("fileInput").click();
  $("btnRecognize").onclick = autoRecognize;
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
  at.onchange = () => { state.anchorType = at.value; renderTrack(); renderStatus(); };

  // 零售商
  $("retailer").innerHTML = "";
  for (const r of state.meta.retailers) {
    const o = document.createElement("option");
    o.value = r; o.textContent = r; $("retailer").appendChild(o);
  }

  renderDirection();
  renderSku();
  renderTrack(); renderStatus();
}

(async () => {
  checkApiHealth();  // 不阻塞页面：先体检，红了也不影响用户看界面
  state.meta = await api("/api/meta");
  init();
  renderSamples();
})();
