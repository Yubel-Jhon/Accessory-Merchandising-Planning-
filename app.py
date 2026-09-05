#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""商品企划生成 Agent · 本地可跑产品（Streamlit 前端）。

流程（对齐 PRD §5 三阶段）：
  ① 起盘：上传产品图（或纯文字生成白底锚点）→ 锚点节点「已生成」
  ② 转换：图类型轨道（7 类节点，转换矩阵自动亮/灰）→ 下拉向导 → Seedream 生成变体 → 选 1 张
  ③ 组装：选品逻辑 + 编排 → 导出 PPT / HTML

启动：  streamlit run app.py
"""
import os
import sys
from datetime import datetime

import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import (UPLOAD_DIR, OUT_DIR, EXPORT_DIR, ensure_api_key,  # noqa: E402
                  IMAGE_TYPES, DIRECTIONS, RETAILER_STYLE, TRANSFORMS,
                  TYPE_ORDER, TYPE_SHORT, SIZE, build_refs)
from prompts import build_prompt, build_selection_logic  # noqa: E402
from qwen_client import generate as qwen_generate  # noqa: E402
from exporter import render_html, render_pptx, TYPE_LABEL, LAYOUT_ORDER  # noqa: E402

ensure_api_key()

# 预生成示例（山羊绒围巾 4 类图），一键载入即可秒出完整企划，无需等待生图
DEMO_IMAGES = {
    "white_bg": "images/white_bg.jpg",
    "studio": "images/studio.jpg",
    "lifestyle": "images/lifestyle.jpg",
    "detail": "images/detail.jpg",
}


# ---------- 状态 ----------
def init_state():
    st.session_state.setdefault("anchor_path", None)
    st.session_state.setdefault("anchor_type", "white_bg")
    st.session_state.setdefault("plan", {"selected": {}, "variants_by_type": {}})
    st.session_state.setdefault("current_type", None)
    st.session_state.setdefault("variants", [])
    st.session_state.setdefault("variant_type", None)


# ---------- 业务 ----------
def compute_states():
    done = set(st.session_state.plan["selected"].keys())
    if st.session_state.anchor_path:
        done.add(st.session_state.anchor_type)
    avail = set()
    for d in done:
        avail.update(TRANSFORMS.get(d, []))
    avail -= done
    return done, avail


def generate_variants(direction, target, sku, color_en, scene_en, retailer, count):
    anchor = st.session_state.anchor_path
    refs = build_refs(direction, sku, target, anchor)
    prompt = build_prompt(target, sku, color_en, scene_en, retailer)
    size = SIZE[IMAGE_TYPES[target].get("aspect_ratio", "1:1")]
    paths = qwen_generate(refs, prompt, size=size, n=count, out_dir=OUT_DIR, retries=1)
    return paths, refs, prompt


# ---------- UI ----------
st.set_page_config(page_title="商品企划生成 Agent", layout="wide")
init_state()

st.title("🧣 商品企划生成 Agent")
st.caption("上传一张产品图 → 图类型轨道点选派生 → 生成变体选图 → 自动出「选品逻辑 + 编排」→ 导出 PPT/HTML")

# 一键载入预生成示例（最快演示路径）
if st.button("🚀 一键载入示例：山羊绒围巾（秒出完整企划，不等待生图）", use_container_width=True):
    for t, rel in DEMO_IMAGES.items():
        p = os.path.join(ROOT, rel)
        st.session_state.plan["selected"][t] = p
        st.session_state.plan["variants_by_type"][t] = [p]
    st.session_state.anchor_path = os.path.join(ROOT, "images/white_bg.jpg")
    st.session_state.anchor_type = "white_bg"
    st.session_state.current_type = None
    st.session_state.variants = []
    st.rerun()

# 侧边栏：方向 / 零售商 / 企划状态 / 导出
with st.sidebar:
    st.subheader("① 企划方向")
    direction = st.selectbox("风格", list(DIRECTIONS.keys()), index=0)
    retailer = st.selectbox("零售商", list(RETAILER_STYLE.keys()), index=0)
    st.divider()

    sku_names = [s["name"] for s in DIRECTIONS[direction]["skus"]]
    sku_name = st.selectbox("款式", sku_names)
    sku = next(s for s in DIRECTIONS[direction]["skus"] if s["name"] == sku_name)

    st.divider()
    st.subheader("企划状态")
    done, avail = compute_states()
    for t in TYPE_ORDER:
        mark = "●" if t in done else ("○" if t in avail else "✕")
        st.markdown(f"{mark} {TYPE_SHORT[t]} {TYPE_LABEL[t].split('·')[-1].strip()}")
    st.divider()
    if st.button("🗑 清空重来", use_container_width=True):
        st.session_state.update({"anchor_path": None, "plan": {"selected": {}, "variants_by_type": {}},
                                 "current_type": None, "variants": [], "variant_type": None})
        st.rerun()

# 主区：三阶段
# ---- 阶段 1 起盘 ----
st.subheader("① 起盘：上传产品图（锚点）")
c1, c2 = st.columns([1, 1])
with c1:
    up = st.file_uploader("上传产品图（jpg/png）", type=["jpg", "jpeg", "png", "webp"])
    if up is not None:
        ext = os.path.splitext(up.name)[1] or ".jpg"
        path = os.path.join(UPLOAD_DIR, f"anchor-{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext}")
        with open(path, "wb") as f:
            f.write(up.getbuffer())
        st.session_state.anchor_path = path
with c2:
    anchor_type = st.selectbox("识别为图类型（可手动改）", TYPE_ORDER,
                               index=TYPE_ORDER.index(st.session_state.anchor_type))
    st.session_state.anchor_type = anchor_type
    if st.session_state.anchor_path:
        st.image(st.session_state.anchor_path, caption="当前锚点图", width=260)
    else:
        st.info("还没上传。或点下方「无图起盘」先用文字生成一张白底图。")
    if st.button("✨ 无图起盘（文字 → 白底图）"):
        with st.spinner("生成白底锚点图..."):
            prompt = build_prompt("white_bg", sku, sku["colors"][0]["en"], "", retailer)
            paths = qwen_generate([], prompt, size=SIZE["1:1"], n=1, out_dir=OUT_DIR, retries=1)
            st.session_state.anchor_path = paths[0]
            st.session_state.anchor_type = "white_bg"
            st.rerun()

# ---- 阶段 2 转换 ----
st.divider()
st.subheader("② 图类型轨道（转换矩阵自动亮/灰）")
done, avail = compute_states()

cols = st.columns(len(TYPE_ORDER))
for i, t in enumerate(TYPE_ORDER):
    if t == st.session_state.current_type:
        mark, disabled = "◎", False
    elif t in done:
        mark, disabled = "●", False
    elif t in avail:
        mark, disabled = "○", False
    else:
        mark, disabled = "✕", True
    label = f"{mark} {TYPE_SHORT[t]}"
    if cols[i].button(label, key=f"node_{t}", disabled=disabled, use_container_width=True):
        st.session_state.current_type = t
        st.session_state.variants = []
        st.rerun()

cur = st.session_state.current_type
if cur:
    st.markdown(f"**当前节点：{TYPE_LABEL[cur]}**")
    cc1, cc2, cc3, cc4, cc5 = st.columns(5)
    color_opts = {f'{c["zh"]} {c["en"]}': c for c in sku["colors"]}
    color_sel = cc1.selectbox("颜色", list(color_opts.keys()))
    color = color_opts[color_sel]
    scene_opts = {f'{s["zh"]} {s["en"]}': s for s in sku["scenes"]}
    scene_sel = cc2.selectbox("场景", list(scene_opts.keys()))
    scene = scene_opts[scene_sel]
    count = cc3.selectbox("变体数量", [1, 2, 3], index=1)
    cc4.markdown("材质 / 工艺")
    cc4.info(f'{sku["material"]}\n\n{sku["craft"]}')
    cc5.markdown("对标")
    cc5.info(sku["benchmark"])

    if st.button("🎨 生成这张图", type="primary"):
        with st.spinner(f"Seedream 生成中（{count} 张变体，约 20–60 秒）..."):
            try:
                paths, refs, prompt = generate_variants(direction, cur, sku, color["en"], scene["en"], retailer, count)
                st.session_state.variants = paths
                st.session_state.variant_type = cur
                st.session_state.plan["variants_by_type"][cur] = paths
                with st.expander("查看本次 prompt / 参考图", expanded=False):
                    st.code(prompt)
                    st.write("参考图:", refs)
            except Exception as e:
                st.error(f"生成失败：{e}")

# 变体选择
if st.session_state.variants:
    vt = st.session_state.variant_type
    st.markdown(f"**结果区：{len(st.session_state.variants)} 张变体 → 点选 1 张纳入企划**")
    vcols = st.columns(len(st.session_state.variants))
    for i, p in enumerate(st.session_state.variants):
        with vcols[i]:
            st.image(p, use_container_width=True)
            if st.button(f"选这张 #{i+1}", key=f"pick_{vt}_{i}"):
                st.session_state.plan["selected"][vt] = p
                st.session_state.current_type = None
                st.session_state.variants = []
                st.rerun()

# ---- 阶段 3 组装 / 导出 ----
st.divider()
st.subheader("③ 组装：选品逻辑 + 编排导出")
sel = st.session_state.plan["selected"]
st.write(f"已生成 **{len(sel)}** 类图：{'、'.join(TYPE_SHORT[t] for t in sel) if sel else '（暂无）'}")

if st.button("📦 生成完整企划并导出（PPT + HTML）", type="primary", disabled=not sel):
    with st.spinner("生成选品逻辑 + 编排 + 导出中..."):
        plan = {
            "product": {
                "category": sku_name, "material": sku["material"], "craft": sku["craft"],
                "color": color["zh"], "price_band": "¥299–499（山姆会员价）",
                "benchmark": sku["benchmark"],
            },
            "direction": direction,
            "retailer": retailer,
            "selection_logic": build_selection_logic(direction, sku),
            "selected": dict(sel),
            "layout": [t for t in LAYOUT_ORDER if t in sel],
        }
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        html_path = os.path.join(EXPORT_DIR, f"企划-{stamp}.html")
        pptx_path = os.path.join(EXPORT_DIR, f"企划-{stamp}.pptx")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(render_html(plan))
        render_pptx(plan, pptx_path)

        st.session_state.last_export = (html_path, pptx_path)
        st.success("导出完成")

if "last_export" in st.session_state:
    html_path, pptx_path = st.session_state.last_export
    ec1, ec2 = st.columns(2)
    with ec1:
        with open(html_path, "rb") as f:
            st.download_button("⬇ 下载 HTML 企划页", f.read(), file_name=os.path.basename(html_path),
                               mime="text/html", use_container_width=True)
    with ec2:
        with open(pptx_path, "rb") as f:
            st.download_button("⬇ 下载 PPT 推介页", f.read(), file_name=os.path.basename(pptx_path),
                               use_container_width=True)
    st.markdown("#### 企划预览（HTML）")
    with open(html_path, encoding="utf-8") as f:
        st.components.v1.html(f.read(), height=900, scrolling=True)
