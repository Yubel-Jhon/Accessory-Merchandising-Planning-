#!/usr/bin/env python
"""DashScope qwen-image-3.0-pro 图生图公共客户端（被 i2i.py / generate.py 复用）。

同步接口（该端点不支持 X-DashScope-Async，加了会 403）。提交 timeout 拉到 300s，
带提交重试，应对偶发慢；若返回 task_id 则转轮询。
"""
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

from PIL import Image as PILImage

from core import ensure_api_key, KEY_HELP  # noqa: E402  key 多源加载 + 修复指引


def _friendly_http_error(e):
    """DashScope 的 401/403/4xx 翻成中文结论（key 无效 / 欠费 / 无权限），附 API 原文。"""
    try:
        detail = e.read().decode("utf-8", "replace")[:300]
    except Exception:
        detail = ""
    if e.code == 401:
        return RuntimeError(
            f"[API key 无效] DashScope 拒绝了这把 key（401），检查是否复制完整/是否被删除。API 返回：{detail}")
    if e.code == 403:
        low = detail.lower()
        if "arrearage" in low or "欠费" in detail or "余额" in detail or "quota" in low or "balance" in low:
            return RuntimeError(
                f"[账户余额不足] DashScope 返回 403 欠费提示，去阿里云百炼控制台充值后重试。API 返回：{detail}")
        return RuntimeError(
            f"[API 拒绝访问] DashScope 返回 403（可能是欠费、未开通该模型、或 key 无权限）。API 返回：{detail}")
    return RuntimeError(f"[API 请求失败] HTTP {e.code}：{detail}")

API = "https://dashscope.aliyuncs.com/api/v1"
GENERATE = f"{API}/services/aigc/multimodal-generation/generation"

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tiff": "image/tiff",
    ".gif": "image/gif",
}

# 绕过系统代理：本机全局代理(127.0.0.1:10809)常死，DashScope 走直连更稳，
# 否则 urllib 默认读系统代理 → WinError 10061（目标计算机积极拒绝）。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# 默认 qwen-image-3.0-pro（2026-09 定案：面试 demo 画质优先，pro 的细节/质感更好）。
# 想更快可设环境变量 DASHSCOPE_IMAGE_MODEL=qwen-image-3.0 切回（能力一致、更快）。
MODEL = os.environ.get("DASHSCOPE_IMAGE_MODEL", "qwen-image-3.0-pro")


def img_to_base64(path, max_side=1280):
    """读图转 base64 data URI，并压到 max_side 以内（JPEG q85），提速上传/编码。"""
    with PILImage.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > max_side:
            s = max_side / max(w, h)
            im = im.resize((int(w * s), int(h * s)), PILImage.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        data = base64.b64encode(buf.getvalue()).decode()
    return "data:image/jpeg;base64," + data


def _http(url, method="GET", headers=None, body=None, timeout=60, retries=3):
    """HTTP 请求，对 429/503/5xx 做指数退避重试（DashScope 偶发过载会返 503）。"""
    data = json.dumps(body).encode() if body is not None else None
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with _OPENER.open(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429 or e.code == 503 or 500 <= e.code < 600:
                time.sleep(5 * (2 ** i))  # 5s → 10s → 20s 退避
                continue
            raise _friendly_http_error(e) from e  # 401/403 等直接翻译成中文结论
        except Exception as e:
            last = e
            time.sleep(3 * (2 ** i))
    raise last


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-code"})
    with _OPENER.open(req, timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())
    if os.path.getsize(path) == 0:
        os.remove(path)
        raise RuntimeError(f"图片下载为空: {url}")


def extract_urls(output):
    urls = []
    for ch in output.get("choices", []):
        for item in ch.get("message", {}).get("content", []):
            if isinstance(item, dict) and item.get("image"):
                urls.append(item["image"])
    for item in output.get("results", []):
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    for item in output.get("data", []):
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    return urls


def _save(urls, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    saved = []
    for i, url in enumerate(urls):
        path = os.path.join(out_dir, f"gen-{stamp}-{i + 1}.png")
        try:
            download(url, path)
        except Exception as e:
            print(f"  (第 {i + 1} 张下载失败，跳过: {e})", flush=True)
            continue
        saved.append(path)
    if not saved:
        raise RuntimeError("所有生成图片下载失败（URL 可能已过期）")
    return saved


def generate(refs, prompt, size="1280*720", n=1, model=MODEL,
             out_dir=None, retries=2, prompt_extend=False, post_timeout=600):
    """图生图：refs 最多 3 张参考图 + 文字指令，返回本地保存路径列表。

    prompt_extend 默认关（调用方已给完整英文 prompt，改写会加时且可能稀释约束）；
    post_timeout 拉到 600s 应对 i2i 慢（实测单张 2-7 分钟）。
    """
    if not ensure_api_key():  # 请求前再兜一次：运行中补配的 key 下一次请求就能生效
        raise RuntimeError(KEY_HELP)
    key = os.environ["DASHSCOPE_API_KEY"]

    content = [{"image": img_to_base64(r)} for r in refs[:3]]
    content.append({"text": prompt})

    auth = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {
            "n": n,
            "size": size,
            "prompt_extend": prompt_extend,
            "prompt_extend_mode": "direct",
            "watermark": False,
            "enable_thinking": False,
        },
    }

    task_id = None
    for attempt in range(retries + 1):
        try:
            resp = _http(GENERATE, "POST", auth, body, timeout=post_timeout)
            output = resp.get("output", {})
            task_id = output.get("task_id")
            if task_id:
                break
            urls = extract_urls(output)
            if urls:  # 部分情况下直接同步返回了结果
                return _save(urls, out_dir)
        except Exception as ex:
            if attempt == retries:
                raise
            time.sleep(5)
            print(f"  (提交重试 {attempt + 1}: {ex})", flush=True)

    if not task_id:
        raise RuntimeError(f"提交失败，无 task_id: {json.dumps(resp, ensure_ascii=False)}")

    poll_auth = {"Authorization": f"Bearer {key}"}
    for _ in range(200):  # 最多 ~10 分钟
        time.sleep(3)
        try:
            st = _http(f"{API}/tasks/{task_id}", headers=poll_auth, timeout=30)
        except Exception:
            continue  # 轮询偶发网络抖动/503 过载，跳过本轮继续等
        output = st.get("output", {})
        status = output.get("task_status")
        if status == "SUCCEEDED":
            urls = extract_urls(output)
            if urls:
                return _save(urls, out_dir)
            raise RuntimeError("任务成功但无图片 URL")
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"task {status}: {json.dumps(output, ensure_ascii=False)}")
    raise RuntimeError("task 轮询超时")
