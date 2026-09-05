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
import uuid
from datetime import datetime

from flask import Flask, request, jsonify, send_file, abort

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import (UPLOAD_DIR, OUT_DIR, EXPORT_DIR, MODEL_DIR, REF_ROOT, ensure_api_key,  # noqa: E402
                  KEY_HELP, IMAGE_TYPES, DIRECTIONS, RETAILER_STYLE, SIZE, SHARED,
                  DIRECTION_SLUG, slugify, sku_slug, find_sku, url_to_path, LAYERS,
                  crop_center)
from prompts import build_prompt, build_selection_logic, build_variation_prompt  # noqa: E402
from qwen_client import generate as qwen_generate, _http  # noqa: E402
from exporter import render_html, render_pptx, LAYOUT_ORDER  # noqa: E402

app = Flask(__name__)

# 生成任务（后台线程）
JOBS = {}
JOBS_LOCK = threading.Lock()


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
        res = recognize_img(anchor)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(res)


@app.post("/api/variation")
def variation():
    """出相似款：畅销款参考图（锚点）→ 单轴演变（改色/改细节/改廓形）→ 演变款图。"""
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
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
    job_id = uuid.uuid4().hex[:12]

    def work():
        try:
            paths = qwen_generate(refs, prompt, size=size, n=1, out_dir=OUT_DIR, retries=1)
            with JOBS_LOCK:
                JOBS[job_id] = {"done": True, "images": paths}
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id] = {"done": True, "error": str(e)}

    with JOBS_LOCK:
        JOBS[job_id] = {"done": False}
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.post("/api/generate")
def generate():
    if not ensure_api_key():
        return jsonify({"error": KEY_HELP}), 503
    data = request.get_json(force=True)
    target = data["target"]
    sku = data["sku"]  # 完整 sku 对象（前端从 meta 带上）
    direction = data.get("direction") or list(DIRECTIONS.keys())[0]
    anchor = url_to_path(data["anchor"]) if data.get("anchor") else None
    model = url_to_path(data["model"]) if data.get("model") else None

    # 细节图/面料图：裁原图局部当参考，i2i 放大还原（文生图不传原图，材质/颜色对不上）。
    # 裁剪必须收紧到产品内部：裁太大（>0.65）会把背景（白底/深灰棚）整片带进参考图，
    # 模型会把背景色「织」进面料——出现过驼色围巾生成灰色面料的实际案例。
    has_ref = False
    if target in ("detail", "fabric"):
        if anchor and os.path.isfile(anchor):
            # 文+图双参考（实测定案）：① 中心裁块管「纹理像」——fabric 0.45 纯纹理、
            # detail 0.6 带结构（缝线/拼接/收边），裁太大背景色会被织进面料（踩过坑）；
            # ② 完整原图管「整体对」——整体颜色/图案布局/结构语境，印花类尤其需要。
            # 两个一起传，配合 prompt 里的材质颜色文字锚点，三重锁定。
            ratio = 0.6 if target == "detail" else 0.45
            refs = [crop_center(anchor, ratio=ratio), os.path.abspath(anchor)]
            has_ref = True
        else:
            refs = []  # 无原图时文生图兜底（纯文字推断，还原度有限，前端会提示）
    else:
        refs = [anchor] if anchor else []
        if model and os.path.isfile(model):
            refs.append(os.path.abspath(model))

    prompt = build_prompt(target, sku, data["color_en"], data["scene_en"], data["retailer"],
                          has_model=bool(model), has_ref=has_ref)
    size = SIZE[IMAGE_TYPES[target].get("aspect_ratio", "1:1")]
    count = data.get("count", 1)
    job_id = uuid.uuid4().hex[:12]

    def work():
        try:
            paths = qwen_generate(refs, prompt, size=size, n=count, out_dir=OUT_DIR, retries=1)
            with JOBS_LOCK:
                JOBS[job_id] = {"done": True, "images": paths, "no_ref": not has_ref}
        except Exception as e:
            with JOBS_LOCK:
                JOBS[job_id] = {"done": True, "error": str(e)}

    with JOBS_LOCK:
        JOBS[job_id] = {"done": False}
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/api/status/<job_id>")
def status(job_id):
    with JOBS_LOCK:
        j = JOBS.get(job_id, {"done": False})
    imgs = j.get("images", [])
    return jsonify({"done": j["done"],
                    "error": j.get("error"),
                    "no_ref": j.get("no_ref", False),
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
    direction = data["direction"]
    sku = data["sku"]
    retailer = data["retailer"]
    selected_urls = data.get("selected", {})
    variation = data.get("variation")
    if variation:
        variation = {
            "before": url_to_path(variation["before"]),
            "after": url_to_path(variation["after"]),
            "axis": variation.get("axis", ""),
            "change": variation.get("change", ""),
        }
    plan = {
        "product": {"category": sku["name"], "material": sku["material"], "craft": sku["craft"],
                    "color": data.get("color", ""), "price_band": "¥299–499（山姆会员价）",
                    "benchmark": sku["benchmark"]},
        "direction": direction,
        "retailer": retailer,
        "selection_logic": build_selection_logic(direction, sku),
        "selected": {k: url_to_path(v) for k, v in selected_urls.items()},
        "layout": [t for t in LAYOUT_ORDER if t in selected_urls],
        "variation": variation,
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    html_path = os.path.join(EXPORT_DIR, f"企划-{stamp}.html")
    pptx_path = os.path.join(EXPORT_DIR, f"企划-{stamp}.pptx")
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
