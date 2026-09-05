#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""企划导出：把 plan（含已选图）渲染成自包含 HTML + 1 页推介 PPT。

plan 结构:
{
  "product": {category, material, craft, color, price_band, benchmark},
  "direction": str, "retailer": str,
  "selection_logic": {标题: 正文, ...},
  "selected": {image_type: 本地图片绝对路径},
  "layout": ["lifestyle", "studio", "white_bg", "detail"]  # 编排顺序
}
"""
import base64
import os

TYPE_LABEL = {
    "white_bg": "白底图 · 产品身份证",
    "studio": "商拍图 · 质感定调",
    "lifestyle": "氛围图 · 场景代入",
    "detail": "细节图 · 品质论证",
    "fabric": "面料图 · 材料透明",
    "model": "模特图 · 上身效果",
}
LAYOUT_ORDER = ["white_bg", "detail", "fabric", "studio", "lifestyle", "model"]


def _b64(path):
    with open(path, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def render_html(plan):
    p = plan["product"]
    chips = [
        ("方向", plan["direction"]),
        ("品类", p.get("category", "")),
        ("材质", p.get("material", "")),
        ("工艺", p.get("craft", "")),
        ("颜色", p.get("color", "")),
        ("价格带", p.get("price_band", "")),
        ("对标", p.get("benchmark", "")),
        ("零售商", plan["retailer"]),
    ]
    chip_html = "".join(f'<span class="chip"><b>{k}</b>{v}</span>' for k, v in chips if v)

    # 只取已选中的图，按 LAYOUT_ORDER 排序
    layout = [t for t in LAYOUT_ORDER if t in plan["selected"]]
    imgs = {t: _b64(plan["selected"][t]) for t in layout}

    grid = "".join(
        f'''<figure class="gitem {t}"><img src="{imgs[t]}" alt="{TYPE_LABEL[t]}"/>
        <figcaption>{TYPE_LABEL[t]}</figcaption></figure>''' for t in layout)

    hero = imgs[layout[0]] if layout else ""

    cards = "".join(f'<div class="card"><h3>{k}</h3><p>{v}</p></div>'
                    for k, v in plan["selection_logic"].items())

    # 演变款对比（before/after），可选
    variation_html = ""
    v = plan.get("variation")
    if v:
        axis_label = {"color": "改色", "detail": "改细节", "silhouette": "改廓形"}.get(v.get("axis"), v.get("axis", ""))
        variation_html = (
            '<h2 class="sec">演变款对比 · 畅销款 → 相似款</h2>'
            '<div class="compare">'
            f'<figure><img src="{_b64(v["before"])}" alt="before"/><figcaption>畅销款（起点）</figcaption></figure>'
            '<span class="arrow">→</span>'
            f'<figure><img src="{_b64(v["after"])}" alt="after"/><figcaption>演变款（{axis_label}：{v.get("change","")}）</figcaption></figure>'
            '</div>'
        )

    title = f'{p.get("category", "商品")} · 商品企划'

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title><style>
:root{--ink:#2C2C2C;--brown:#8B7355;--paper:#F5F1EA;--card:#FFF;--line:#E5DED2}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--paper);color:var(--ink);line-height:1.65}
.wrap{max-width:1120px;margin:0 auto;padding:40px 28px 80px}
header{text-align:center;padding:28px 0 8px}
header .eyebrow{letter-spacing:.35em;font-size:12px;color:var(--brown);text-transform:uppercase;margin-bottom:10px}
header h1{font-family:Georgia,"Songti SC",serif;font-weight:500;font-size:40px}
header .sub{color:#7a6f5f;margin-top:10px;font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin:26px 0 6px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;color:#4a4238}
.chip b{color:var(--brown);margin-right:6px;font-weight:600}
.hero{margin:34px 0 26px;border-radius:6px;overflow:hidden;box-shadow:0 12px 40px rgba(44,44,44,.14)}
.hero img{width:100%;display:block}
h2.sec{font-family:Georgia,"Songti SC",serif;font-weight:500;font-size:22px;margin:46px 0 18px;display:flex;align-items:center;gap:12px}
h2.sec::before{content:"";width:26px;height:2px;background:var(--brown);display:inline-block}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.gitem{background:var(--card);border:1px solid var(--line);border-radius:6px;overflow:hidden;display:flex;flex-direction:column}
.gitem img{width:100%;aspect-ratio:1/1;object-fit:cover;display:block}
.gitem figcaption{padding:10px 12px;font-size:13px;color:#5b5145;border-top:1px solid var(--line);background:#fbf9f5}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:18px 20px}
.card h3{font-size:14px;color:var(--brown);letter-spacing:.08em;margin-bottom:8px;font-weight:600}
.card p{font-size:14px;color:#3f3930}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:#a49a8b;text-align:center}
.compare{display:grid;grid-template-columns:1fr auto 1fr;gap:14px;align-items:center;margin:6px 0 26px}
.compare figure{background:var(--card);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.compare img{width:100%;aspect-ratio:1/1;object-fit:cover;display:block}
.compare figcaption{padding:9px 12px;font-size:13px;color:#5b5145;border-top:1px solid var(--line);background:#fbf9f5}
.compare .arrow{font-size:30px;color:var(--brown)}
@media(max-width:860px){.grid{grid-template-columns:repeat(2,1fr)}.cards{grid-template-columns:1fr}.compare{grid-template-columns:1fr}.compare .arrow{text-align:center}}
</style></head><body><div class="wrap">
<header><div class="eyebrow">Product Planning · Quiet Luxury</div>
<h1>__TITLE__</h1><div class="sub">__SUBTITLE__</div></header>
<div class="chips">__CHIPS__</div>
<div class="hero"><img src="__HERO__" alt="hero"></div>
__VARIATION__
<h2 class="sec">图库编排</h2><div class="grid">__GRID__</div>
<h2 class="sec">选品逻辑</h2><div class="cards">__CARDS__</div>
<footer>由「商品企划生成 Agent」编排生成 ｜ 生图：通义 qwen-image</footer>
</div></body></html>""".replace("__TITLE__", title) \
        .replace("__SUBTITLE__", f'{plan["direction"]} ｜ 对标 {p.get("benchmark","")} ｜ {plan["retailer"]}') \
        .replace("__CHIPS__", chip_html) \
        .replace("__HERO__", hero) \
        .replace("__GRID__", grid) \
        .replace("__CARDS__", cards) \
        .replace("__VARIATION__", variation_html)


def render_pptx(plan, out_path):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from PIL import Image

    INK = RGBColor(0x2C, 0x2C, 0x2C)
    BROWN = RGBColor(0x8B, 0x73, 0x55)
    p = plan["product"]

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    def box(x, y, w, h, fill=None, line=None, slide=slide):
        shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
        shp.fill.solid() if fill else shp.fill.background()
        if fill:
            shp.fill.fore_color.rgb = fill
        if line:
            shp.line.color.rgb = line
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        return shp

    def text(x, y, w, h, runs, align=None, slide=slide):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, (txt, size, color, bold) in enumerate(runs):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = align
            r = para.add_run(); r.text = txt
            r.font.size = Pt(size); r.font.color.rgb = color; r.font.bold = bold
            r.font.name = "Microsoft YaHei"
        return tb

    def fit_img(path, cx, cy, cw, ch, slide=slide):
        with Image.open(path) as im:
            w, h = im.size
        ar = w / h; box_ar = cw / ch
        if ar > box_ar:
            dw, dh = cw, cw / ar
        else:
            dh, dw = ch, ch * ar
        dx = cx + (cw - dw) / 2; dy = cy + (ch - dh) / 2
        slide.shapes.add_picture(path, Inches(dx), Inches(dy), Inches(dw), Inches(dh))

    box(0, 0, 13.333, 7.5, fill=RGBColor(0xF5, 0xF1, 0xEA))
    box(0, 0, 13.333, 0.12, fill=BROWN)
    text(0.55, 0.28, 12.2, 0.9, [(f'{p.get("category","商品")} · 商品企划', 30, INK, True)])
    text(0.55, 0.95, 12.2, 0.4,
         [(f'{plan["direction"]} · 对标 {p.get("benchmark","")} · {p.get("material","")} · {plan["retailer"]}', 13, BROWN, False)])

    layout = [t for t in LAYOUT_ORDER if t in plan["selected"]]
    # hero 氛围图优先，其次第一个可用图
    hero_key = "lifestyle" if "lifestyle" in plan["selected"] else layout[0]
    fit_img(plan["selected"][hero_key], 0.55, 1.5, 7.4, 5.1)
    text(0.55, 6.62, 7.4, 0.4, [(TYPE_LABEL[hero_key], 11, BROWN, False)])

    rest = [t for t in layout if t != hero_key][:3]
    rx, rw = 8.25, 4.6
    th, gap = 1.62, 0.12
    for i, key in enumerate(rest):
        ty = 1.5 + i * (th + gap)
        box(rx, ty, rw, th, fill=RGBColor(0xFF, 0xFF, 0xFF), line=RGBColor(0xE5, 0xDE, 0xD2))
        fit_img(plan["selected"][key], rx + 0.06, ty + 0.06, th - 0.12, th - 0.12)
        text(rx + th + 0.1, ty + 0.18, rw - th - 0.2, 0.9, [(TYPE_LABEL[key], 12, INK, True)])

    box(0.55, 7.0, 12.25, 0.02, fill=RGBColor(0xE5, 0xDE, 0xD2))
    one = "选品逻辑：" + " ｜ ".join(f'{k}：{v}' for k, v in plan["selection_logic"].items())[:260]
    text(0.55, 6.95, 12.25, 0.5, [(one, 10, RGBColor(0x5B, 0x51, 0x45), False)])

    v = plan.get("variation")
    if v:
        axis_label = {"color": "改色", "detail": "改细节", "silhouette": "改廓形"}.get(v.get("axis"), v.get("axis", ""))
        s2 = prs.slides.add_slide(prs.slide_layouts[6])
        box(0, 0, 13.333, 7.5, fill=RGBColor(0xF5, 0xF1, 0xEA), slide=s2)
        box(0, 0, 13.333, 0.12, fill=BROWN, slide=s2)
        text(0.55, 0.28, 12.2, 0.9, [("演变款对比 · 畅销款 → 相似款", 28, INK, True)], slide=s2)
        text(0.55, 1.02, 12.2, 0.4, [(f'{axis_label}：{v.get("change","")}', 14, BROWN, False)], slide=s2)
        fit_img(v["before"], 0.55, 1.65, 5.95, 5.15, slide=s2)
        text(0.55, 6.88, 5.95, 0.4, [("畅销款（起点）", 12, BROWN, True)], slide=s2)
        text(6.6, 3.75, 0.35, 0.6, [("→", 36, BROWN, True)], slide=s2)
        fit_img(v["after"], 7.0, 1.65, 5.95, 5.15, slide=s2)
        text(7.0, 6.88, 5.95, 0.4, [("演变款", 12, BROWN, True)], slide=s2)

    prs.save(out_path)
    return out_path
