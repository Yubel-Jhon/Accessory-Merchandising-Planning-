#!/usr/bin/env python
"""批量生成商品图：按类别取参考图 + 模特多样性 + 统一调性。

用法:
  python generate.py --type model --ethnicities all --count 2 --size 1536*2048
  python generate.py --type lifestyle --ethnicities east_asian,black --count 3

依赖:
  - data/reference_categories.json  image_type -> 参考图类别
  - data/diversity.json             人种清单 + 调性后缀
  - images/white_bg.jpg             产品锚点（永远第 1 张参考图，锁产品一致性）
  - images/references/<category>/   各类别参考图（按类别取第一张）

规则: 参考图按类别匹配，最多 3 张（产品锚点 + 该类型对应类别图）。调性后缀统一注入。
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_client import generate as qwen_generate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCHOR = os.path.join(ROOT, "images", "white_bg.jpg")
REF_DIR = os.path.join(ROOT, "images", "references")

IMG_EXT = (".jpg", ".jpeg", ".png", ".webp")

PROMPTS = {
    "model": "{eth} model wearing the scarf. Keep the scarf in image 1 EXACTLY unchanged — same color, structure, proportions, no design detail modified. Wrap it naturally around the model's neck like the reference. White background product photography, front view, natural relaxed pose, even soft studio lighting, product in sharp focus. {tone}",
    "lifestyle": "{eth} model wearing the scarf in a cozy autumn/winter lifestyle scene. Keep the scarf in image 1 EXACTLY unchanged — same color, structure, proportions. Natural relaxed candid pose, warm golden-hour natural light. {tone}",
    "studio": "Professional studio product photography of the scarf in image 1, keep it EXACTLY unchanged. Hero product shot, softbox key light + rim light, cashmere texture visible, clean neutral seamless background, shallow depth of field. {tone}",
    "detail": "Macro close-up of the scarf in image 1, keep the material EXACTLY unchanged. Extreme close-up of the knit / fringe detail, directional side lighting highlighting cashmere texture and craftsmanship, shallow depth of field, soft bokeh. {tone}",
    "fabric": "Macro fabric texture of the scarf in image 1, keep the material EXACTLY unchanged. Visible thread / knit structure, flat lay, directional side lighting, high clarity fabric texture, no text. {tone}",
}


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def pick_refs(image_type, ref_map):
    """产品锚点 + 该类型对应类别各取第一张，最多 3 张。"""
    refs = [ANCHOR]
    for cat in ref_map.get(image_type, []):
        if len(refs) >= 3:
            break
        files = sorted(glob.glob(os.path.join(REF_DIR, cat, "*")))
        files = [f for f in files if f.lower().endswith(IMG_EXT)]
        if files:
            refs.append(files[0])
    return refs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--type", required=True,
                   choices=list(PROMPTS), help="输出图类型")
    p.add_argument("--ethnicities", default="all",
                   help="all 或逗号分隔的人种 id（见 diversity.json）")
    p.add_argument("--count", type=int, default=2, help="每种人种生成几张")
    p.add_argument("--size", default="1280*720", help="输出尺寸 width*height")
    p.add_argument("--out", default=os.path.join(ROOT, "images", "output"))
    args = p.parse_args()

    ref_map = load_json(os.path.join(ROOT, "data", "reference_categories.json"))[
        "image_type_to_reference"]
    div = load_json(os.path.join(ROOT, "data", "diversity.json"))
    tone = div["tone_suffix"]
    eths = div["ethnicities"]
    if args.ethnicities != "all":
        wanted = set(args.ethnicities.split(","))
        eths = [e for e in eths if e["id"] in wanted]
    if not eths:
        print("ERROR: 没有匹配的人种", file=sys.stderr)
        sys.exit(1)

    refs = pick_refs(args.type, ref_map)
    template = PROMPTS[args.type]
    print(f"参考图({len(refs)}): {refs}", file=sys.stderr)
    print(f"人种({len(eths)}) x 数量({args.count}) = {len(eths) * args.count} 张",
          file=sys.stderr)

    os.makedirs(args.out, exist_ok=True)
    for e in eths:
        for i in range(args.count):
            prompt = template.format(eth=e["prompt"], tone=tone)
            print(f"[{args.type}] {e['label']} #{i + 1} ...", file=sys.stderr, flush=True)
            try:
                saved = qwen_generate(refs, prompt, size=args.size, n=1, out_dir=args.out)
                for s in saved:
                    print(f"  SAVED {s}")
            except Exception as ex:
                print(f"  ERROR: {ex}", file=sys.stderr)


if __name__ == "__main__":
    main()
