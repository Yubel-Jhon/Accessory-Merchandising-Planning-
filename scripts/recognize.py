#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""锚点图识别：qwen-vl-max 视觉 → 客观描述（自由格式，不套用数据库枚举）。

compatible-mode 的 OpenAI 风格端点，图片走 base64 data URI 直传。
按图里实际看到的内容输出：品类/材质/工艺/颜色/场景等中英文字段 + 一张图的拍摄类型。
返回 dict：
{
  "image_type": 拍摄类型枚举（7 类之一，None 表示识别不到）,
  "summary":    一句中文客观总结,
  "sku":        自由格式"款式"对象（字段对齐 build_prompt 的读取：en/material_en/craft_en/...）,
  "color_en"/"scene_en"/"color_zh"/"scene_zh": 颜色与场景中英文,
}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import IMAGE_TYPES, GARMENT_STRUCTURES, ensure_api_key, KEY_HELP  # noqa: E402
from qwen_client import img_to_base64, _http  # noqa: E402

VL_API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VL_MODEL = "qwen-vl-max"

TYPE_LIST = list(IMAGE_TYPES.keys())
TYPE_ZH = {"白底图": "white_bg", "商拍图": "studio", "氛围图": "lifestyle",
           "细节图": "detail", "面料图": "fabric", "模特图": "model"}


_CJK = re.compile(r"[一-鿿]")


def _en(val):
    """英文兜底：模型偶发把中文字塞进 *_en 字段，会污染生图 prompt。出现中文则置空。"""
    v = (val or "").strip()
    return "" if _CJK.search(v) else v


def _parse_json(raw):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip("json").strip()
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


_PROMPT = (
    "你是商品企划图片识别助手。客观描述这张产品图，按你实际看到的来，不要套用任何预设分类。\n"
    "只输出一个 JSON 对象，不要任何多余文字。字段：\n"
    f'"image_type"：这张图的拍摄类型，只能从英文 key 里选一个：{TYPE_LIST}\n'
    '"name"：品类中文名（如「连帽羽绒服」）\n'
    '"en"：品类英文描述，不含颜色（如 "hooded down jacket"）\n'
    '"material"：材质中文\n'
    '"material_en"：材质英文\n'
    '"craft"：工艺中文\n'
    '"craft_en"：工艺英文\n'
    '"persona_en"：目标人群/穿着氛围英文一句话\n'
    '"detail_point_en"：最能体现做工/结构的关键细节英文（如缝线/拼接/收边/装饰/廓形结构，不是面料纹理本身）\n'
    '"structure_points"：结构细节点 JSON 数组，2-3 个英文条目，每个是一个「部位+做工/结构细节」（如 "hand-rolled fringe edge"、"stitched seam where the band meets the crown"），聚焦结构/工艺，不含纯面料纹理\n'
    f'"garment_type"：款式类型，只能从这些英文 key 里选一个：{list(GARMENT_STRUCTURES.keys())}\n'
    '"weave_en"：织法/结构英文\n'
    '"fiber_en"：纤维成分英文\n'
    '"fabric_type"：面料类型，只能从 knit/print/leather/down/texture 里选一个（针织/印花/皮革/羽绒/表面纹理）\n'
    '"color_zh"：颜色中文\n'
    '"color_en"：颜色英文\n'
    '"scene_zh"：场景中文\n'
    '"scene_en"：场景英文\n'
    '"benchmark"：可对标的高端品牌名，没有就空字符串\n'
    '"summary"：一句中文客观总结（品类+材质+颜色+风格）\n'
    '格式：{"image_type":"...","name":"...","en":"...","material":"...","material_en":"...",'
    '"craft":"...","craft_en":"...","persona_en":"...","detail_point_en":"...","structure_points":["..."],'
    '"garment_type":"scarf","weave_en":"...","fiber_en":"...","fabric_type":"knit","color_zh":"...","color_en":"...","scene_zh":"...","scene_en":"...",'
    '"benchmark":"...","summary":"..."}'
    '。不确定的字段给空字符串，但必须输出 JSON。'
)


def recognize(anchor_path):
    if not ensure_api_key():
        raise RuntimeError(KEY_HELP)
    key = os.environ["DASHSCOPE_API_KEY"]

    body = {
        "model": VL_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": img_to_base64(anchor_path)}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = _http(VL_API, "POST", headers, body, timeout=120)
    raw = resp["choices"][0]["message"]["content"]
    if isinstance(raw, list):
        raw = "".join(p.get("text", "") for p in raw if isinstance(p, dict))
    data = _parse_json(raw)

    image_type = data.get("image_type")
    if image_type not in IMAGE_TYPES:
        image_type = TYPE_ZH.get(image_type)

    color_en = (data.get("color_en") or "").strip()
    scene_en = (data.get("scene_en") or "").strip()

    # 结构细节点：模型偶发返回字符串或混入中文，逐条过 _en() 清洗，空串剔除。
    _sp = data.get("structure_points") or []
    if isinstance(_sp, str):
        _sp = [x.strip() for x in _sp.replace("，", ",").split(",") if x.strip()]
    structure_points = [s for s in (_en(x) for x in _sp) if s] if isinstance(_sp, list) else []

    # 款式类型：必须落在结构库枚举里，否则置空（prompts 侧再兜底推断）。
    garment_type = _en(data.get("garment_type"))
    if garment_type not in GARMENT_STRUCTURES:
        garment_type = ""

    # 自由格式"款式"，字段对齐 prompts.build_prompt / build_variation_prompt 的读取。
    # *_en 字段统一过 _en() 兜底，防止模型把中文塞进英文 prompt。
    sku = {
        "name": data.get("name") or "",
        "en": _en(data.get("en")),
        "material": data.get("material") or "",
        "material_en": _en(data.get("material_en")),
        "craft": data.get("craft") or "",
        "craft_en": _en(data.get("craft_en")),
        "persona_en": _en(data.get("persona_en")),
        "detail_point_en": _en(data.get("detail_point_en")),
        "structure_points": structure_points,
        "garment_type": garment_type,
        "weave_en": _en(data.get("weave_en")),
        "fiber_en": _en(data.get("fiber_en")),
        "fabric_type": _en(data.get("fabric_type")),
        "benchmark": data.get("benchmark") or "",
        "colors": [{"en": color_en, "zh": data.get("color_zh") or color_en}],
        "scenes": [{"en": scene_en, "zh": data.get("scene_zh") or scene_en}],
    }
    return {
        "image_type": image_type,
        "summary": data.get("summary") or "",
        "sku": sku,
        "color_en": color_en,
        "scene_en": scene_en,
        "color_zh": data.get("color_zh") or "",
        "scene_zh": data.get("scene_zh") or "",
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("img")
    a = p.parse_args()
    print(json.dumps(recognize(a.img), ensure_ascii=False))
