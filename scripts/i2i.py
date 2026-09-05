#!/usr/bin/env python
"""通义千问 qwen-image-3.0-pro 图生图 CLI —— qwen_client 的薄封装。

用法:
  python i2i.py "<文字指令>" --ref <参考图路径> [--ref <图2>] [--ref <图3>]
                  [--size 1280*720] [--n 1] [--out DIR] [--prompt-extend]

支持 1-3 张参考图（品牌参考图 + 锚点白底图），文字指令做精确编辑/风格迁移。
依赖 DASHSCOPE_API_KEY（settings.json 已配）。参考图转 base64 直接传，无需上传 OSS。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import ensure_api_key  # noqa: E402
from qwen_client import generate  # noqa: E402

ensure_api_key()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt", help="文字指令（编辑/风格迁移描述）")
    p.add_argument("--ref", required=True, action="append", default=[],
                   help="参考图路径，可多次传，最多 3 张")
    p.add_argument("--size", default="1280*720", help="输出尺寸 width*height")
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--prompt-extend", dest="prompt_extend", action="store_true",
                   help="提示词智能改写（默认关，提速约 20 倍）")
    p.add_argument("--out", default=os.path.join(
        os.path.expanduser("~"), "Pictures", "ai-images"))
    args = p.parse_args()

    if len(args.ref) > 3:
        print("ERROR: 最多 3 张参考图", file=sys.stderr)
        sys.exit(1)

    try:
        saved = generate(args.ref, args.prompt, size=args.size, n=args.n,
                         out_dir=args.out, prompt_extend=args.prompt_extend)
    except Exception as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        sys.exit(1)

    for s in saved:
        print(f"SAVED {s}")


if __name__ == "__main__":
    main()
