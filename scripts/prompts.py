#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生图 prompt 引擎 —— 唯一的 prompt 组装入口（app.py / server.py 共用）。

模板以 data/image_types.json 为唯一事实源，叠加：
  1. 零售商风格后缀（retailer_style.json）
  2. SHARED_SUFFIX 一致性约束（image_types.json）

另备 PRODUCT_REF_LOCK / QUALITY / NEGATIVE_PROMPT 三个更强的词库（吸收
wzj177-ecommerce-image-suite 架构），目前 demo 路径未强制注入，留作后续调优开关。
"""
from core import IMAGE_TYPES, SHARED_SUFFIX, RETAILER_STYLE, DIRECTIONS, TONE, GARMENT_STRUCTURES

# 参考图存在时注入的最高优先级约束（比 SHARED_SUFFIX 更强硬，可选）
PRODUCT_REF_LOCK = (
    "CRITICAL HIGHEST PRIORITY: A product reference image is provided. "
    "You MUST use the reference image as the EXACT basis for the product. "
    "Keep EXACT same: color, material, knit/weave structure, proportions, and all design details. "
    "You may ONLY change: camera angle, zoom level, lighting, and background. "
    "The product must look IDENTICAL to the reference image."
)

# 出相似款专用锁词：允许改一个轴，其余 DNA 全锁（与 PRODUCT_REF_LOCK 的"只能改机位/光线"不同）
VARIATION_REF_LOCK = (
    "CRITICAL HIGHEST PRIORITY: A product reference image is provided. "
    "You MUST use the reference image as the EXACT basis for the product. "
    "Keep EXACT same: material, knit/weave structure, proportions, and all design details — "
    "EXCEPT the single axis being evolved below. The evolved product must look like a sibling "
    "of the reference (same family, same DNA), not a copy, not a different product."
)

# 统一画质词库（可选）
QUALITY = (
    "shot on Sony A7R V, 85mm f/2.0 lens, natural diffused studio lighting, "
    "authentic commercial product photography, true-to-life colors, no heavy post-processing, "
    "realistic fabric texture and natural drape, professional e-commerce visual style. "
    "CRITICAL: Keep the EXACT same product design, color, proportions and all details. "
    "Do NOT alter any design element."
)

NEGATIVE_PROMPT = (
    "AI-generated look, artificial, CGI, 3D render, digital art, synthetic texture, "
    "plastic skin, mannequin-like, uncanny valley, oversaturated, HDR, heavy post-processing, "
    "low resolution, blurry, deformed, ugly, bad anatomy, extra limbs, "
    "watermark, text, signature, logo, cartoon, cheap look"
)

# model 类型无 data 模板（image_types.json 里 prompt_template 为 null），单独写死
# 模特人种/姿态由用户上传的模特参考图定义，这里不再写死 East Asian
MODEL_PROMPT = (
    "Model wearing the {product}. Keep the product in the reference image EXACTLY unchanged — "
    "same color, structure, proportions, no design detail modified. Wrap it naturally like the reference. "
    "White background product photography, front view, natural relaxed pose, even soft studio lighting, "
    "product in sharp focus. {tone}"
)

# 细节图（detail）文生图模板：产品某结构细节的微距特写，用结构/工艺文字描述生成。
# 关键：不能写完整商品名（{product}），否则文生图会直接重绘完整产品、做不出微距局部。
DETAIL_TEMPLATE = (
    "extreme macro close-up of the {detail_point}, filling the entire frame, "
    "a structural detail shot — the garment's structural parts are: {structure}. "
    "focus on the construction, seams, folded edges and finishing, "
    "directional side lighting, shallow depth of field, soft bokeh background, no text, "
    "no full product, no garment silhouette, only the isolated structural detail"
)

# 文生图统一画质后缀（detail/fabric 用；文生图无参考图，只锁画质与真实纹理）
TEXT2IMG_QUALITY = (
    "photorealistic, ultra-high definition, 8K resolution, commercial photography quality, "
    "sharp details, professional lighting, true-to-life fabric texture, accurate color."
)

# 场景层（studio/lifestyle/model）注入：有上传模特参考图时锁模特一致性
MODEL_REF_HINT = (
    " The model reference image defines the model's appearance, ethnicity, and pose — "
    "keep the model consistent with it, while keeping the product IDENTICAL to its reference image."
)

# 面料图按 sku.fabric_type 分 5 支模板（织法/印花/皮革/羽绒/表面纹理）
# 定义：把产品图里的「面料」生成为一整块平铺的面料图（不是单根纤维微距、不是换面料）
FABRIC_TEMPLATES = {
    "knit": "whole flat-lay fabric swatch of {color} {weave}, the complete {material} fabric spread flat filling the frame, overall knit texture and soft drape visible, directional side lighting, high clarity, no text",
    "print": "whole flat-lay fabric swatch of the printed {material}, the complete scarf fabric spread flat filling the frame, full printed pattern and satin sheen visible across the cloth, directional side lighting, vivid accurate colors, no text",
    "leather": "whole flat-lay sheet of {color} {weave}, the complete {material} hide spread flat filling the frame, overall leather grain and natural pores visible, directional side lighting, high clarity, no text",
    "down": "whole flat-lay fabric swatch of the quilted {color} {weave}, the complete down-filled fabric spread flat filling the frame, puffy down chambers and stitching visible across the surface, directional side lighting, high clarity, no text",
    "texture": "whole flat-lay sheet of {color} {weave}, the complete {material} surface spread flat filling the frame, overall surface texture and fine grain visible, directional side lighting, high clarity, no text",
}


def _infer_fabric_type(sku):
    """按材质/织法/品类英文推断 fabric_type，兜底 recog.sku 缺字段的情况。

    directions.json 里的 sku 都有 fabric_type；但识别出来的 recog.sku 没有，会导致所有
    面料图都落到 knit 模板（草帽套「knit texture」）。这里按关键词粗判，识别不到再回落 knit。
    """
    ft = (sku.get("fabric_type") or "").strip()
    if ft in FABRIC_TEMPLATES:
        return ft
    blob = " ".join([
        sku.get("material_en") or "",
        sku.get("weave_en") or "",
        sku.get("en") or "",
        sku.get("fiber_en") or "",
    ]).lower()
    if any(k in blob for k in ("leather", "lambskin", "hide", "full-grain")):
        return "leather"
    if any(k in blob for k in ("down", "quilt", "goose", "fill")):
        return "down"
    if any(k in blob for k in ("silk", "scarf", "print", "satin", "sheen")):
        return "print"
    if any(k in blob for k in ("tpe", "non-slip", "foam", "mat", "straw", "raffia", "woven", "surface")):
        return "texture"
    return "knit"


# 细节图/面料图 i2i 模板：裁一块原图局部纹理当参考，模型只需「原样放大/填充」。
# 为什么换掉文生图：文生图不传原图，材质/颜色对不上（用户反馈「还原度不够」）；
# 直接传完整商品图又会被 i2i 重绘完整商品。折中就是 crop + i2i（参考图已是局部纹理）。
# 双保险：除了参考图，再把材质/颜色用文字钉死（{material}/{color}）——参考图管「像」，
# 文字锚点管「不跑」，模型两边对不上时以参考图为准。
MATERIAL_REF_LOCK = (
    "Use the reference image as the EXACT source of material and color. "
    "Reproduce this EXACT same texture and color — do NOT invent or change the weave, pattern, or material. "
)

FABRIC_I2I_TEMPLATE = (
    MATERIAL_REF_LOCK
    + "The reference is a close patch of the actual product fabric: {material}, {color}. "
    + "This is a ZOOM-IN of that very fabric, not a new design. "
    + "Extend this exact texture to fill the ENTIRE frame edge-to-edge as a flat-lay fabric swatch — "
    + "same yarn, same weave, same color, same sheen as the reference, pixel-faithful. "
    + "Do NOT invent a different material, do NOT shift the color, "
    + "do NOT include any background color from the reference edges. "
    + "No product shape, no silhouette, no fringe, no garment edges — only the raw fabric texture. "
    + "directional side lighting, high clarity, no text"
)

DETAIL_I2I_TEMPLATE = (
    MATERIAL_REF_LOCK
    + "The reference shows part of the actual product ({material}, {color}). "
    + "Zoom in on its {detail_point} and show an extreme macro close-up of it, filling the entire frame. "
    + "This is a structural detail shot of the SAME product — the fabric, color and construction "
    + "must stay identical to the reference; do NOT redesign it and do NOT introduce new materials. "
    + "The garment's structural parts are: {structure}. "
    + "Focus on the construction and stitching — seams, folded edges, binding, and finishing — not just the flat fabric texture. "
    + "Do NOT show the full product, no silhouette, no garment outline — only the isolated structural detail. "
    + "shallow depth of field, directional side lighting, no text"
)

# i2i 局部放大用的画质后缀：强调「保留参考图材质颜色 + 高清」，不是从零生成。
I2I_TEXTURE_QUALITY = (
    "photorealistic, ultra-high definition, sharp texture detail, "
    "true-to-life color and weave, keep the material IDENTICAL to the reference."
)

# 出相似款：三大演变轴（改色/改细节/改廓形），锁 DNA 只动一个轴
VARIATION_AXES = {
    "color": "color / colorway",
    "detail": "design details / hardware / trim",
    "silhouette": "silhouette / shape / proportions",
}


def build_prompt(target, sku, color_en, scene_en, retailer, has_model=False, has_ref=False):
    """组装生图 prompt。sku 为 directions.json 里的品类对象（含中英字段）。

    分流：
      - product 层 detail/fabric：有参考图（crop 局部）走 i2i 放大还原原图；无参考图走文生图兜底。
      - scene 层（studio/lifestyle/model）有上传模特参考图时注入 MODEL_REF_HINT。
    """
    if target == "model":
        tmpl = MODEL_PROMPT
        mapping = {"product": f'{color_en} {sku["en"]}', "tone": TONE}
    elif target == "fabric":
        if has_ref:
            tmpl = FABRIC_I2I_TEMPLATE
        else:
            ft = _infer_fabric_type(sku)
            tmpl = FABRIC_TEMPLATES.get(ft, FABRIC_TEMPLATES["knit"])
        mapping = {
            "product": f'{color_en} {sku["en"]}',
            "color": color_en,
            "material": sku["material_en"],
            "craft": sku["craft_en"],
            "detail_point": sku["detail_point_en"],
            "weave": sku["weave_en"],
            "fiber": sku["fiber_en"],
        }
    elif target == "detail":
        tmpl = DETAIL_I2I_TEMPLATE if has_ref else DETAIL_TEMPLATE
        # 细节图聚焦「结构/工艺」：先按款式类型（garment_type）查款式结构库，得到该款式的
        # 结构部件清单；查不到再退回模型识别的 structure_points，最后兜底 detail_point_en。
        structs = GARMENT_STRUCTURES.get(sku.get("garment_type")) or (sku.get("structure_points") or [])
        if not structs:
            structs = [sku.get("detail_point_en") or "the material structure and stitching"]
        detail_point = structs[0]      # 主特写目标
        structure = ", ".join(structs)  # 完整结构清单（作上下文，让模型知道这是结构特写）
        mapping = {
            "product": f'{color_en} {sku["en"]}',
            "material": sku["material_en"],
            "craft": sku["craft_en"],
            "color": color_en,
            "detail_point": detail_point,
            "structure": structure,
        }
    else:
        tmpl = IMAGE_TYPES[target]["prompt_template"]
        mapping = {
            "product": f'{color_en} {sku["en"]}',
            "material": sku["material_en"],
            "craft": sku["craft_en"],
            "persona": sku["persona_en"],
            "scene": scene_en,
            "detail_point": sku["detail_point_en"],
            "weave": sku["weave_en"],
            "fiber": sku["fiber_en"],
        }
    for k, v in mapping.items():
        tmpl = tmpl.replace("{" + k + "}", v)

    suffix = RETAILER_STYLE.get(retailer, "")
    layer = IMAGE_TYPES[target].get("layer", "product")

    if target == "fabric" or target == "detail":
        # 局部纹理图：i2i 走「保留参考图材质颜色」画质词；文生图走 TEXT2IMG_QUALITY。不拼零售商后缀。
        q = I2I_TEXTURE_QUALITY if has_ref else TEXT2IMG_QUALITY
        return f"{tmpl}. {q}"
    if layer == "scene":
        hint = MODEL_REF_HINT if has_model else ""
        return f"{tmpl}. {suffix}. {SHARED_SUFFIX}{hint}"
    return f"{tmpl}. {suffix}. {SHARED_SUFFIX}"


def build_prompt_full(target, sku, color_en, scene_en, retailer, has_ref=True):
    """增强版 prompt：在 build_prompt 之上叠加 PRODUCT_REF_LOCK + QUALITY（有参考图时）。

    用于要求更高产品一致性的场景；demo 默认走 build_prompt（更快、更省 token）。
    """
    base = build_prompt(target, sku, color_en, scene_en, retailer)
    if has_ref:
        return f"{PRODUCT_REF_LOCK}\n\n{base} {QUALITY}"
    return base


def build_variation_prompt(sku, axis, change_desc, color_en=None):
    """出相似款：锁定产品 DNA，只改一个轴（改色/改细节/改廓形），返回演变 i2i prompt。"""
    product = f'{color_en or sku["colors"][0]["en"]} {sku["en"]}'
    axis_en = VARIATION_AXES.get(axis, "design details")
    dna = (f'Keep EXACT same: material ({sku["material_en"]}), craft ({sku["craft_en"]}), '
           f'proportions, and all design details — except the single axis being evolved below.')
    return (
        f'{VARIATION_REF_LOCK}\n\n'
        f'Product: {product}. {dna}\n'
        f'EVOLUTION (change ONLY this axis): {axis_en}.\n'
        f'Change: {change_desc}.\n'
        f'Everything else stays identical to the reference. {QUALITY}'
    )


def build_selection_logic(direction, sku):
    """六段选品逻辑（对齐山姆「体面的性价比」定位）。anchor 从 directions.json 读。"""
    anchor = DIRECTIONS[direction]["anchor_sku"]
    b = sku["benchmark"]
    return {
        "对标": f'{b} 的「{sku["name"]}」——取它「无 logo + 大地色 + 原料等级」的视觉语言，砍到约 1/10 价格带。',
        "人群": "山姆会员 = 中产家庭，追求「体面的性价比」：不是买不起大牌，是不愿为 logo 溢价买单，要的是「看不见的奢侈」——原料等级 + 工艺。",
        "价格带": f'¥299–499 山姆价格带，复用山姆已验证锚点（{anchor}），会员对「原料级商品」在此价位无心理障碍。',
        "差异化": f'① 参数透明——把 {sku["material"]} / {sku["craft"]} 直接标进图里，用原料等级背书；② 无 logo 静奢，让质感自己说话；③ 山姆风格后缀（大地色 + 暖棚光 + 会员店质感），与京东/BigOffs 调性区分。',
        "山姆锚点": f'复用「{anchor}」爆款逻辑：把大牌原料翻译成「可量化的参数卖点」，价格 + 参数两张牌同时打。',
        "风险": "避免 logo 侵权（对标而非仿制）、避开运动赛道（lululemon 起诉 Costco 的侵权红线），静奢/户外配饰是安全的 MVP 切口。",
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="生成电商图生图 / 出相似款演变 prompt（独立调用 / 测试）")
    p.add_argument("--type", choices=list(IMAGE_TYPES.keys()), help="图类型（出图 prompt 模式）")
    p.add_argument("--variation", choices=list(VARIATION_AXES.keys()),
                   help="出相似款轴：color/detail/silhouette")
    p.add_argument("--change", default=None, help="演变改动描述，如「燕麦色改炭灰」")
    p.add_argument("--direction", default=list(DIRECTIONS.keys())[0], help="风格方向")
    p.add_argument("--sku", default=None, help="款式名（默认该方向第一个）")
    p.add_argument("--color", default=None, help="颜色英文（默认该款第一个）")
    p.add_argument("--scene", default=None, help="场景英文（默认该款第一个）")
    p.add_argument("--retailer", default="山姆", help="零售商")
    p.add_argument("--rich", action="store_true", help="注入 PRODUCT_REF_LOCK + QUALITY")
    args = p.parse_args()

    skus = DIRECTIONS[args.direction]["skus"]
    sku = next((s for s in skus if s["name"] == args.sku), skus[0])
    color_en = args.color or sku["colors"][0]["en"]

    if args.variation:
        if not args.change:
            p.error("--variation 需要配合 --change 描述改动")
        prompt = build_variation_prompt(sku, args.variation, args.change, color_en)
    else:
        if not args.type:
            p.error("请给 --type（出图 prompt）或 --variation（出相似款）")
        scene_en = args.scene or sku["scenes"][0]["en"]
        if args.rich:
            prompt = build_prompt_full(args.type, sku, color_en, scene_en, args.retailer, has_ref=True)
        else:
            prompt = build_prompt(args.type, sku, color_en, scene_en, args.retailer)

    print("=== PROMPT ===")
    print(prompt)
    print("\n=== NEGATIVE PROMPT ===")
    print(NEGATIVE_PROMPT)
