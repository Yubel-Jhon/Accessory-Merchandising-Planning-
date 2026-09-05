#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""共享核心：路径 / API Key / 静态数据 / 图类型常量 / 参考图选取。

app.py（Streamlit）与 server.py（Flask）此前各自内联了这些逻辑，
现在统一收口到这一个模块，两个前端只保留各自的 UI / 路由。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UPLOAD_DIR = os.path.join(ROOT, "images", "upload")
OUT_DIR = os.path.join(ROOT, "images", "output")
EXPORT_DIR = os.path.join(ROOT, "demo", "output")
MODEL_DIR = os.path.join(ROOT, "images", "models")
for d in (UPLOAD_DIR, OUT_DIR, EXPORT_DIR, MODEL_DIR):
    os.makedirs(d, exist_ok=True)


def ensure_api_key():
    """保证 DASHSCOPE_API_KEY 可用，按序兜底：环境变量 → 项目 .env → Claude settings(.local).json。

    幂等且廉价，可放在每个请求前调用：服务运行中补配了 key，下一次请求自动生效，无需重启。
    返回 True/False 表示是否找到了 key。
    """
    if os.environ.get("DASHSCOPE_API_KEY"):
        return True
    # ① 项目根 .env：双击 .bat 场景下最直观的修法——在文件夹里建个 .env 写一行
    try:
        with open(os.path.join(ROOT, ".env"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("DASHSCOPE_API_KEY=") and len(line) > 19:
                    os.environ["DASHSCOPE_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return True
    except OSError:
        pass
    # ② Claude Code 配置（key 一般跟着 Claude Code 的 env 走）
    for name in ("settings.json", "settings.local.json"):
        sp = os.path.join(os.path.expanduser("~"), ".claude", name)
        try:
            with open(sp, encoding="utf-8") as f:
                k = json.load(f).get("env", {}).get("DASHSCOPE_API_KEY")
            if k:
                os.environ["DASHSCOPE_API_KEY"] = k
                return True
        except Exception:
            pass
    return False


KEY_HELP = (
    "API key（DASHSCOPE_API_KEY）没接上。三种修法任选其一：\n"
    "  1. 在本文件夹新建 .env 文件，写一行：DASHSCOPE_API_KEY=你的key\n"
    f"  2. 编辑 {os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')}"
    "，在 env 里加一行：\"DASHSCOPE_API_KEY\": \"你的key\"\n"
    "  3. 临时设环境变量：set DASHSCOPE_API_KEY=你的key（然后重启 server.py）\n"
    "key 在阿里云百炼控制台（bailian.console.aliyun.com → API-KEY 管理）获取/查看。"
)


def _load(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


# ---------- 静态数据 ----------
IMAGE_TYPES = _load("image_types.json")["image_types"]
SHARED_SUFFIX = _load("image_types.json")["shared_suffix"]
RETAILER_STYLE = _load("retailer_style.json")["retailer_style"]
DIRECTIONS = _load("directions.json")["directions"]
REF_MAP = _load("reference_categories.json")["image_type_to_reference"]
TONE = _load("diversity.json")["tone_suffix"]

# ---------- 图类型常量 ----------
TRANSFORMS = {
    "white_bg":  ["studio", "lifestyle", "detail", "fabric", "model"],
    "studio":    ["white_bg", "lifestyle", "detail", "fabric", "model"],
    "lifestyle": ["white_bg", "studio", "model"],
    "detail":    ["white_bg"],
    "fabric":    [],
    "model":     ["white_bg", "studio", "lifestyle"],
}
TYPE_ORDER = ["white_bg", "studio", "lifestyle", "detail", "fabric", "model"]
# 两层拆分：product 层锁产品本身（不要模特），scene 层需用户上传模特
LAYERS = {
    "product": ["white_bg", "detail", "fabric"],
    "scene": ["studio", "lifestyle", "model"],
}
TYPE_SHORT = {"white_bg": "白底", "studio": "商拍", "lifestyle": "氛围",
              "detail": "细节", "fabric": "面料", "model": "模特"}
SIZE = {"1:1": "1280*1280", "4:5": "1280*1600", "16:9": "1280*720", "3:4": "1536*2048"}

# ---------- 款式结构库 ----------
# 细节图聚焦「结构/工艺」而非面料（用户拍板）。每个款式类型对应一组结构部件清单（英文，
# 每个是「部位+做工/结构细节」），识别出 garment_type 后查这里，比模型随手输出的 2-3 个
# 结构点更全更具体。覆盖 directions.json 的配饰品类 + 常见配饰兜底。
GARMENT_STRUCTURES = {
    "scarf": ["rolled hem edge", "knit stitch structure", "fringe detailing", "twilled weave pattern"],
    "square_scarf": ["hand-rolled hem corner", "printed pattern edge", "satin sheen surface", "folded corner finishing"],
    "gloves": ["hand-stitched finger seams", "ribbed wrist cuff", "full-grain leather surface grain", "lined cuff opening"],
    "mittens": ["quilted down chamber", "fleece-lined opening", "touchscreen fingertip patch", "wrist cinch closure"],
    "beanie": ["ribbed knit crown", "seamless top closure", "folded cuff brim", "knit gauge structure"],
    "hat": ["structured crown", "brim edge binding", "hat band attachment seam", "woven shell structure"],
    "socks": ["ribbed leg cuff", "heel reinforcement panel", "toe seam closure", "arch support band"],
    "neck_gaiter": ["stand collar seam", "quilted down tube", "drawcord channel", "windproof shell finish"],
    "headband": ["anti-slip silicone strip", "stretch knit band structure", "stitched edge finishing"],
    "yoga_mat": ["non-slip surface texture", "rolled edge finish", "dense foam cross-section"],
    "arm_sleeves": ["cooling knit weave", "hemmed cuff edge", "flatlock seam", "printed UV detail"],
}

# ---------- AI RAG 参考图库 ----------
# 目录结构：images/references/{方向slug}/{品类slug}/{图类型}/  +  _shared/ 放跨类共享图
REF_ROOT = os.path.join(ROOT, "images", "references")
SHARED = "_shared"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# 方向（中文 key）→ 目录 slug（避免中文进 URL/路径）
DIRECTION_SLUG = {
    "静奢/老钱风": "quiet-luxury",
    "羽绒/户外保暖": "down-outdoor",
    "轻运动/瑜伽": "sport-yoga",
}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def sku_slug(sku):
    """sku 对象（directions.json）或名字字符串 → 目录 slug。"""
    name = sku.get("en") or sku.get("name") if isinstance(sku, dict) else str(sku)
    return slugify(name)


def find_sku(direction, sku_name):
    for s in DIRECTIONS.get(direction, {}).get("skus", []):
        if s["name"] == sku_name:
            return s
    return None


def _imgs_in(dirpath):
    if not os.path.isdir(dirpath):
        return []
    return sorted(os.path.join(dirpath, f) for f in os.listdir(dirpath)
                  if f.lower().endswith(IMG_EXTS))


def retrieve_refs(direction, sku, image_type, limit=3):
    """按 方向×品类×图类型 检索参考图，逐级兜底，返回本地绝对路径列表。

    兜底链：精确格子 → 品类级（任意类型）→ 全局共享·该类型 → 全局共享·任意。
    """
    d = DIRECTION_SLUG.get(direction, slugify(direction))
    s = sku_slug(sku)
    cells = [
        (os.path.join(REF_ROOT, d, s, image_type), False),
        (os.path.join(REF_ROOT, d, s), True),
        (os.path.join(REF_ROOT, SHARED, image_type), False),
        (os.path.join(REF_ROOT, SHARED), True),
    ]
    refs = []
    for cell, recursive in cells:
        if recursive:
            for root, _, files in os.walk(cell):
                for f in sorted(files):
                    if f.lower().endswith(IMG_EXTS):
                        refs.append(os.path.join(root, f))
        else:
            refs.extend(_imgs_in(cell))
        if len(refs) >= limit:
            break
    return refs[:limit]


def build_refs(direction, sku, image_type, anchor_path=None):
    """锚点 + 检索参考，去重、限 3。生图时统一走这里。"""
    refs = [os.path.abspath(anchor_path)] if anchor_path else []
    for p in retrieve_refs(direction, sku, image_type, limit=3):
        ap = os.path.abspath(p)
        if ap not in [os.path.abspath(r) for r in refs]:
            refs.append(ap)
        if len(refs) >= 3:
            break
    return refs[:3]


def list_reference_images():
    """参考图全量清单（供 /api/meta），含方向/品类/图类型元信息，供前端筛选展示。"""
    out = []
    for root, _, files in os.walk(REF_ROOT):
        rel = os.path.relpath(root, REF_ROOT).replace(os.sep, "/")
        parts = rel.split("/") if rel != "." else []
        for f in sorted(files):
            if not f.lower().endswith(IMG_EXTS):
                continue
            if parts and parts[0] == SHARED:
                direction, sku, itype = SHARED, "", (parts[-1] if len(parts) > 1 else "")
            else:
                direction = parts[0] if parts else ""
                sku = parts[1] if len(parts) > 1 else ""
                itype = parts[-1] if parts else ""
            full = os.path.join(root, f)
            out.append({
                "url": "/file/" + os.path.relpath(full, ROOT).replace("\\", "/"),
                "label": f,
                "direction": direction,
                "sku": sku,
                "type": itype,
            })
    return out


def url_to_path(url):
    """前端 /file/... URL → 本地绝对路径。"""
    return os.path.join(ROOT, url.replace("/file/", ""))


def crop_center(path, ratio=0.7, out_dir=None):
    """裁原图中心正方形局部，作为 detail/fabric 的 i2i 参考。

    为什么：文生图不传原图，材质/颜色对不上（用户反馈「还原度不够」）；直接传完整商品图
    又会被 i2i 重绘完整商品。折中：裁一块原图局部纹理当参考，模型只需原样放大/填充，
    既还原原图，又不会重绘完整商品（参考图本身已是局部纹理）。
    """
    from PIL import Image
    out_dir = out_dir or UPLOAD_DIR
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        s = int(min(w, h) * ratio)
        x = (w - s) // 2
        y = (h - s) // 2
        crop = im.crop((x, y, x + s, y + s))
    base = os.path.splitext(os.path.basename(path))[0]
    out = os.path.join(out_dir, f"_crop_{base}.jpg")
    crop.save(out, quality=92)
    return out
