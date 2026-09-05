#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""商品企划生成 Agent · 自定义前端后端（Flask）。

前端 static/index.html 是「选图片」式交互：点选产品图 / 参考图 / 变体。
生图走通义 qwen-image（后台线程 + 轮询），导出走 exporter.py。

启动：  python server.py   （浏览器访问 http://localhost:8000）
"""
import os
import socket
import sys
import threading
import time
import uuid
from datetime import datetime

from flask import Flask, request, jsonify, send_file, abort

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import (UPLOAD_DIR, OUT_DIR, EXPORT_DIR, MODEL_DIR, REF_ROOT, ensure_api_key,  # noqa: E402
                  KEY_HELP, IMAGE_TYPES, DIRECTIONS, RETAILER_STYLE, SIZE, SHARED,
                  DIRECTION_SLUG, slugify, sku_slug, find_sku, url_to_path, LAYERS,
                  crop_center)
from prompts import build_prompt, build_variation_prompt, build_cover_prompt  # noqa: E402
from qwen_client import generate as qwen_generate, _http  # noqa: E402
from exporter import render_html, render_pptx  # noqa: E402

app = Flask(__name__)

# 生成任务（后台线程）
JOBS = {}
JOBS_LOCK = threading.Lock()


def start_job(work):
    """后台生图任务的唯一入口（家规见 CLAUDE.md）：建 job_id、记时、存 JOBS、开线程。

    work() 由调用方给「真正干活的函数」，返回的 dict 会原样进任务结果
    （通常带 images；error/elapsed/done 由这里统一负责，调用方不用管）。
    """
    job_id = uuid.uuid4().hex[:12]
    t0 = time.monotonic()  # 耗时统计：导出尾页「真实耗时拆解」的数据源

    def runner():
        try:
            result = work()
            result["done"] = True
            result["elapsed"] = round(time.monotonic() - t0)
            result["finished_at"] = time.time()
        except Exception as e:
            result = {"done": True, "error": str(e), "finished_at": time.time()}
        with JOBS_LOCK:
            JOBS[job_id] = result
            _sweep_jobs()

    with JOBS_LOCK:
        JOBS[job_id] = {"done": False}
    threading.Thread(target=runner, daemon=True).start()
    return job_id


def _sweep_jobs():
    """JOBS 只进不出会慢慢攒内存：清掉 1 小时前已完成的任务（须持锁调用）。"""
    cutoff = time.time() - 3600
    stale = [j for j, r in JOBS.items() if r.get("finished_at", 0) < cutoff]
    for j in stale:
        JOBS.pop(j, None)


# ---------- 路由 ----------
@app.get("/")
def index():
    return send_file(os.path.join(ROOT, "static", "index.html"))


@app.get("/file/<path:rel>")
def serve_file(rel):
    full = os.path.abspath(os.path.join(ROOT, rel))
    allowed = [os.path.join(ROOT, "images"), os.path.join(ROOT, "demo", "output"),
               os.path.join(ROOT, "static")]
    if not any(full.startswith(d + os.sep) or full == d for d in allowed):
        abort(403)
    if not os.path.isfile(full):
        abort(404)
    return send_file(full)


@app.get("/api/meta")
def meta():
    samples = [{"label": "山羊绒围巾 · 白底", "url": "/file/images/white_bg.jpg"},
               {"label": "山羊绒围巾 · 商拍", "url": "/file/images/studio.jpg"},
               {"label": "山羊绒围巾 · 细节", "url": "/file/images/detail.jpg"}]
    return jsonify({
        "directions": DIRECTIONS,
        "retailers": list(RETAILER_STYLE.keys()),
        "samples": samples,
        "layers": LAYERS,
        "mvp": {"direction": "静奢/老钱风", "sku": "山羊绒围巾"},
    })


@app.post("/api/upload")
def upload():
    f = request.files["file"]
    ext = os.path.splitext(f.filename)[1] or ".jpg"
    name = f"anchor-{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}"
    p = os.path.join(UPLOAD_DIR, name)
    f.save(p)
    return jsonify({"url": "/file/" + os.path.relpath(p, ROOT).replace("\\", "/")})


@app.post("/api/upload_ref")
def upload_ref():
    """上传参考图到「方向×品类×图类型」格子，落盘 RAG 参考图库。"""
    direction = request.form.get("direction") or list(DIRECTIONS.keys())[0]
    sku_name = request.form.get("sku_name", "")
    image_type = request.form.get("type", "white_bg")
    f = request.files["file"]
    ext = os.path.splitext(f.filename)[1] or ".jpg"

    sku_obj = find_sku(direction, sku_name)
    d = DIRECTION_SLUG.get(direction, slugify(direction))
    s = sku_slug(sku_obj) if sku_obj else slugify(sku_name)
    cell = os.path.join(REF_ROOT, d, s, image_type)
    os.makedirs(cell, exist_ok=True)
    name = f"ref-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}{ext}"
    p = os.path.join(cell, name)
    f.save(p)
    return jsonify({"url": "/file/" + os.path.relpath(p, ROOT).replace("\\", "/")})


@app.post("/api/upload_model")
def upload_model():
    """上传模特照片到 images/models/，作为 scene 层（商拍/氛围/模特）的模特参考图。"""
    f = request.files["file"]
    ext = os.path.splitext(f.filename)[1] or ".jpg"
    name = f"model-{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}"
    p = os.path.join(MODEL_DIR, name)
    f.save(p)
    return jsonify({"url": "/file/" + os.path.relpath(p, ROOT).replace("\\", "/")})


@app.post("/api/recognize")
def recognize():
    """调用 qwen-vl-max 识别锚点图 → 方向/品类/图类型（收编到库内枚举，无匹配则 None）。"""
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
    anchor = url_to_path(data["anchor"]) if data.get("anchor") else None
    if not anchor or not os.path.isfile(anchor):
        return jsonify({"error": "无锚点图"}), 400
    from recognize import recognize as recognize_img  # noqa: E402
    try:
        res = recognize_img(anchor, direction_hint=data.get("direction"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(res)


@app.post("/api/variation")
def variation():
    """出相似款：畅销款参考图（锚点）→ 单轴演变（改色/改细节/改廓形）→ 演变款图。"""
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
    if not data.get("sku"):
        return jsonify({"error": "缺少 sku（请先上传/选择锚点图完成识别）"}), 400
    sku = data["sku"]
    direction = data.get("direction") or list(DIRECTIONS.keys())[0]
    anchor = url_to_path(data["anchor"]) if data.get("anchor") else None
    axis = data.get("axis", "color")
    change_desc = data.get("change", "")
    color_en = data.get("color_en")

    if not anchor or not os.path.isfile(anchor):
        return jsonify({"error": "无畅销款参考图（锚点）"}), 400

    prompt = build_variation_prompt(sku, axis, change_desc, color_en)
    refs = [anchor]  # 畅销款参考图就是演变起点，锁它 DNA
    size = SIZE["1:1"]
    # 一轴多案（扩展⑥）：默认一次出 3 案挑 1，比单发更容易挑出满意的演变方向
    count = int(data.get("count") or 3)

    job_id = start_job(lambda: {"images": qwen_generate(refs, prompt, size=size, n=count,
                                                        out_dir=OUT_DIR, retries=1)})
    return jsonify({"job_id": job_id})


@app.post("/api/cover")
def cover():
    """deck 封面：用各款已完成的图（优先氛围图）作参考 + 整体企划风格 → 生成 P01 封面候选。"""
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
    refs = [url_to_path(u) for u in (data.get("refs") or [])]
    refs = [p for p in refs if p and os.path.isfile(p)]
    if not refs:
        return jsonify({"error": "没有可用的参考图——先把至少一款的图生成出来再出封面"}), 400
    direction = data.get("direction") or list(DIRECTIONS.keys())[0]
    style_hint = data.get("style_hint") or ""
    names = [s.get("name") or s.get("en") or "" for s in (data.get("skus") or []) if s]
    prompt = build_cover_prompt(names, direction, style_hint)
    size = SIZE["16:9"]  # 封面是横幅构图，和 1:1 的单款图区分开

    job_id = start_job(lambda: {"images": qwen_generate(refs[:3], prompt, size=size, n=1,
                                                        out_dir=OUT_DIR, retries=1)})
    return jsonify({"job_id": job_id})


@app.post("/api/generate")
def generate():
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
    # 入参校验：缺字段/类型错时给中文 400，而不是裸 KeyError 500（前端表现为「后端未响应」）
    missing = [k for k in ("target", "sku", "color_en", "scene_en") if not data.get(k)]
    if missing:
        return jsonify({"error": f"缺少参数：{'、'.join(missing)}（请先上传锚点图完成识别）"}), 400
    if data["target"] not in IMAGE_TYPES:
        return jsonify({"error": f"未知图类型：{data['target']}"}), 400
    target = data["target"]
    sku = data["sku"]  # 完整 sku 对象（前端从 meta 带上）
    direction = data.get("direction") or list(DIRECTIONS.keys())[0]
    anchor = url_to_path(data["anchor"]) if data.get("anchor") else None
    model = url_to_path(data["model"]) if data.get("model") else None

    # 锚点图在 = 有产品参考图。细节/面料用它裁局部 i2i；white_bg 用它决定注不注产品锁（画质①）。
    has_ref = bool(anchor and os.path.isfile(anchor))
    # 细节图/面料图：裁原图局部当参考，i2i 放大还原（文生图不传原图，材质/颜色对不上）。
    # 裁剪必须收紧到产品内部：裁太大（>0.65）会把背景（白底/深灰棚）整片带进参考图，
    # 模型会把背景色「织」进面料——出现过驼色围巾生成灰色面料的实际案例。
    if target in ("detail", "fabric"):
        if has_ref:
            # 文+图双参考（实测定案）：① 中心裁块管「纹理像」——fabric 0.45 纯纹理、
            # detail 0.6 带结构（缝线/拼接/收边），裁太大背景色会被织进面料（踩过坑）；
            # ② 完整原图管「整体对」——整体颜色/图案布局/结构语境，印花类尤其需要。
            # 两个一起传，配合 prompt 里的材质颜色文字锚点，三重锁定。
            ratio = 0.6 if target == "detail" else 0.45
            refs = [crop_center(anchor, ratio=ratio), os.path.abspath(anchor)]
        else:
            refs = []  # 无原图时文生图兜底（纯文字推断，还原度有限，前端会提示）
    else:
        refs = [anchor] if has_ref else []
        if model and os.path.isfile(model):
            refs.append(os.path.abspath(model))

    prompt = build_prompt(target, sku, data["color_en"], data["scene_en"], data["retailer"],
                          has_model=bool(model), has_ref=has_ref,
                          style_hint=data.get("style_hint"))
    size = SIZE[IMAGE_TYPES[target].get("aspect_ratio", "1:1")]
    count = data.get("count", 1)

    job_id = start_job(lambda: {"images": qwen_generate(refs, prompt, size=size, n=count,
                                                        out_dir=OUT_DIR, retries=1),
                                "no_ref": not has_ref})
    return jsonify({"job_id": job_id})


@app.post("/api/check_consistency")
def check_consistency():
    """轻量一致性自检（检验③）：锚点原图 vs 生成图（qwen-vl），PASS/FAIL + 一句中文原因。

    同步接口（几秒返回）：前端生成完成后逐张后台调用，结果只挂角标提示、不拦截选图。
    自检自身失败也返回 unknown（不报 5xx），让前端好统一渲染。
    """
    if not ensure_api_key():
        return jsonify({"verdict": "unknown", "reason": "API key 未接上，无法自检"})
    data = request.get_json(force=True)
    ref = url_to_path(data["ref"]) if data.get("ref") else None
    img = url_to_path(data["image"]) if data.get("image") else None
    if not ref or not os.path.isfile(ref) or not img or not os.path.isfile(img):
        return jsonify({"verdict": "unknown", "reason": "参考图或生成图缺失，无法自检"})
    from recognize import check_consistency as check  # noqa: E402
    return jsonify(check(ref, img))


@app.get("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        j = JOBS.get(job_id, {"done": False})
    imgs = j.get("images", [])
    return jsonify({"done": j["done"],
                    "error": j.get("error"),
                    "no_ref": j.get("no_ref", False),
                    "elapsed": j.get("elapsed"),
                    "images": ["/file/" + os.path.relpath(p, ROOT).replace("\\", "/") for p in imgs]})


@app.get("/api/health")
def health():
    """一键体检：区分「key 没接上 / key 无效 / 账户欠费 / 网络」还是「一切正常」。

    用一次最小的文本调用（qwen-turbo，5 token）做真实探测，前端加载时自动调它，
    出问题在页面顶部亮红条并给出修法。
    """
    if not ensure_api_key():
        return jsonify({"ok": False, "level": "missing", "message": "API key 未接上", "fix": KEY_HELP})
    body = {"model": "qwen-turbo", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
    headers = {"Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}", "Content-Type": "application/json"}
    try:
        _http("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
              "POST", headers, body, timeout=15, retries=1)
    except RuntimeError as e:  # _http 已把 401/403 翻译成中文结论
        return jsonify({"ok": False, "level": "api", "message": str(e), "fix": KEY_HELP})
    except Exception as e:
        return jsonify({"ok": False, "level": "network",
                        "message": f"连不上 DashScope（网络/代理问题）：{e}", "fix": KEY_HELP})
    return jsonify({"ok": True, "message": "API 正常：key 已接上，账户可调用"})


@app.post("/api/export")
def export():
    data = request.get_json(force=True)
    missing = [k for k in ("direction", "retailer") if not data.get(k)]
    if missing:
        return jsonify({"error": f"缺少参数：{'、'.join(missing)}"}), 400
    direction = data["direction"]
    retailer = data["retailer"]

    def _norm_variation(v):
        if not v:
            return None
        return {"before": url_to_path(v["before"]), "after": url_to_path(v["after"]),
                "axis": v.get("axis", ""), "change": v.get("change", "")}

    # 企划盘（v0.3）：skus[] 多款；兼容旧单款字段（sku/selected）
    entries = []
    for e in data.get("skus") or []:
        sel = e.get("selected") or {}
        if not sel:
            continue
        entries.append({"sku": e.get("sku") or {}, "color": e.get("color", ""),
                        "selected": {k: url_to_path(v) for k, v in sel.items()},
                        "variation": _norm_variation(e.get("variation"))})
    if not entries and data.get("selected"):
        sku = data.get("sku")
        if not sku:
            return jsonify({"error": "缺少 sku"}), 400
        entries.append({"sku": sku, "color": data.get("color", ""),
                        "selected": {k: url_to_path(v) for k, v in data["selected"].items()},
                        "variation": _norm_variation(data.get("variation"))})
    if not entries:
        return jsonify({"error": "企划盘是空的——先生成并点选图片，再「纳入企划盘」"}), 400

    cover = url_to_path(data["cover"]) if data.get("cover") else None
    if cover and not os.path.isfile(cover):
        cover = None  # 封面文件丢了就回退到无封面版式，不让导出整体失败

    plan = {
        "direction": direction,
        "retailer": retailer,
        "personas": DIRECTIONS.get(direction, {}).get("personas", []),
        "skus": entries,
        "cover": cover,  # P01 封面图（用户从氛围图挑选或再生成）；None 时回退到首图版式
        "plan_style": data.get("plan_style") or "",  # 整体企划风格 → 封面副标/总览 chip
        "timing": data.get("timing") or {},  # 前端累计的实测耗时 → 尾页「耗时拆解」
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    html_path = os.path.join(EXPORT_DIR, f"企划盘-{stamp}.html")
    pptx_path = os.path.join(EXPORT_DIR, f"企划盘-{stamp}.pptx")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(plan))
    render_pptx(plan, pptx_path)
    return jsonify({
        "html": "/file/" + os.path.relpath(html_path, ROOT).replace("\\", "/"),
        "pptx": "/file/" + os.path.relpath(pptx_path, ROOT).replace("\\", "/"),
    })


def assert_port_free(host, port):
    """启动前试绑端口：Windows 下 SO_REUSEADDR 允许重复绑定（两个实例同挂 8000，
    请求随机落错进程，任务查不到 → 前端表现为永远转圈/断开）。裸 socket 不带
    SO_REUSEADDR，端口被占就直接报错退出，杜绝双开。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
    except OSError:
        print(f"[错误] 端口 {port} 已被占用——大概率已经有一个 server.py 在跑。"
              f"先关掉旧实例再启动（taskkill /F /PID <pid>，PID 用 netstat -ano | findstr :{port} 查）。")
        sys.exit(1)
    finally:
        s.close()


if __name__ == "__main__":
    assert_port_free("0.0.0.0", 8000)
    if ensure_api_key():
        print("[OK] API key 已加载（" + os.environ["DASHSCOPE_API_KEY"][:8] + "...）")
    else:
        print("[错误] API key 未接上，识别/生图会失败。修法：\n" + KEY_HELP)
    print("商品企划生成 Agent 已启动： http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=False, threaded=True)
