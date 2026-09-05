# -*- coding: utf-8 -*-
"""冒烟测试：只锁「改 prompt 引擎 / 识别匹配 / 导出入口时最容易碰坏又不自知」的三个函数。

跑法：python -m unittest discover -s tests   （家规见 CLAUDE.md）
不联网、不调 API、不生图——纯函数级断言，几秒跑完。
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from core import DIRECTIONS, GARMENT_STRUCTURES  # noqa: E402
from prompts import build_prompt, FABRIC_TEMPLATES  # noqa: E402
from recognize import match_library_sku  # noqa: E402
from exporter import _normalize_entries  # noqa: E402


def _lib_sku():
    """库内第一个方向的第一款（字段齐：fabric_type/材质等），测试统一用它。"""
    d = next(iter(DIRECTIONS))
    return DIRECTIONS[d]["skus"][0], d


def _assert_no_leftover_placeholder(testcase, prompt):
    """组装完的 prompt 不允许残留 {placeholder}——漏替换就是肉眼难察觉的生图事故。"""
    leftover = re.findall(r"\{[a-z_]+\}", prompt)
    testcase.assertFalse(leftover, f"prompt 里有没替换掉的占位符: {leftover}")


class BuildPromptTests(unittest.TestCase):
    def test_fabric_i2i_uses_material_lock(self):
        """有参考图（crop 局部）走 i2i：必须带材质锁词 + 材质/颜色文字锚点。"""
        sku, _ = _lib_sku()
        p = build_prompt("fabric", sku, "oatmeal", "indoor", "山姆", has_ref=True)
        self.assertIn("Use the reference image as the EXACT source of material", p)
        self.assertIn(sku["material_en"], p)
        self.assertIn("oatmeal", p)
        _assert_no_leftover_placeholder(self, p)

    def test_fabric_text2img_picks_branch_template(self):
        """无参考图走文生图兜底：按 fabric_type 落到 5 支模板之一，不许报错/落空。"""
        sku, _ = _lib_sku()
        p = build_prompt("fabric", sku, "oatmeal", "indoor", "山姆", has_ref=False)
        self.assertTrue(p.strip())
        _assert_no_leftover_placeholder(self, p)

    def test_detail_uses_garment_structure(self):
        """细节图：garment_type 命中结构库时，主特写目标取自结构库而非随手编。"""
        sku, _ = _lib_sku()
        gt = sku.get("garment_type") or "scarf"
        sku = dict(sku, garment_type=gt)
        if gt not in GARMENT_STRUCTURES:  # 库里这款没覆盖就换 scarf 验证机制本身
            sku["en"] = sku.get("en", "scarf")
            sku["garment_type"] = gt = "scarf"
        p = build_prompt("detail", sku, "oatmeal", "indoor", "山姆", has_ref=True)
        self.assertIn(GARMENT_STRUCTURES[gt][0], p)
        _assert_no_leftover_placeholder(self, p)

    def test_scene_layer_locks_uploaded_model(self):
        """scene 层带模特参考图时必须注入模特一致性锁词；不带则不注入。"""
        sku, _ = _lib_sku()
        with_model = build_prompt("studio", sku, "navy", "street", "山姆", has_model=True)
        without_model = build_prompt("studio", sku, "navy", "street", "山姆", has_model=False)
        self.assertIn("model's appearance", with_model)
        self.assertNotIn("model's appearance", without_model)

    def test_lifestyle_injects_style_hint(self):
        """氛围图要把整体企划风格带进 prompt；其他图类型不注入。"""
        sku, _ = _lib_sku()
        p = build_prompt("lifestyle", sku, "navy", "street", "山姆", style_hint="老钱风·大地色")
        self.assertIn("老钱风·大地色", p)
        p2 = build_prompt("studio", sku, "navy", "street", "山姆", style_hint="老钱风·大地色")
        self.assertNotIn("老钱风·大地色", p2)

    def test_product_lock_and_quality_injection(self):
        """画质①②：product 层有参考图注 PRODUCT_REF_LOCK；所有图型末尾注 QUALITY 画质词。"""
        sku, _ = _lib_sku()
        p = build_prompt("white_bg", sku, "oatmeal", "indoor", "山姆", has_ref=True)
        self.assertIn("CRITICAL HIGHEST PRIORITY", p)   # 产品锁在最前
        self.assertIn("shot on Sony A7R V", p)          # 画质词在末尾
        # scene 层锁产品靠模板+SHARED_SUFFIX，不重复注产品锁，但画质词要注入
        ps = build_prompt("studio", sku, "navy", "street", "山姆", has_ref=True, has_model=False)
        self.assertNotIn("CRITICAL HIGHEST PRIORITY", ps)
        self.assertIn("shot on Sony A7R V", ps)
        # 无参考图（文生图兜底）不注产品锁，画质词仍注入
        p0 = build_prompt("white_bg", sku, "oatmeal", "indoor", "山姆", has_ref=False)
        self.assertNotIn("CRITICAL HIGHEST PRIORITY", p0)
        self.assertIn("shot on Sony A7R V", p0)
        _assert_no_leftover_placeholder(self, p)


class MatchLibrarySkuTests(unittest.TestCase):
    def test_matches_by_zh_name(self):
        """识别结果的中文名命中库内款 → 返回库内款（成分/规格/双价格自动带入的根基）。"""
        _, d = _lib_sku()
        lib = DIRECTIONS[d]["skus"][0]
        hit = match_library_sku({"name": lib["name"], "en": "", "material_en": ""}, d)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["sku"]["name"], lib["name"])
        self.assertEqual(hit["direction"], d)

    def test_no_match_returns_none(self):
        """完全不认识的东西不硬匹配——没匹配就老实返回 None，前端走自由格式。"""
        self.assertIsNone(match_library_sku({"name": "不存在的量子围巾", "en": "", "material_en": ""}, None))
        self.assertIsNone(match_library_sku({}, None))


class NormalizeEntriesTests(unittest.TestCase):
    def test_v03_multi_sku(self):
        """v0.3 企划盘：多款各成条目；没选图的空款剔除。"""
        plan = {"skus": [
            {"sku": {"name": "A"}, "color": "藏青", "selected": {"white_bg": "a.jpg"}},
            {"sku": {"name": "空款"}, "color": "", "selected": {}},
            {"sku": {"name": "B"}, "color": "驼", "selected": {"studio": "b.jpg",
                                                              "lifestyle": "c.jpg"}},
        ]}
        entries = _normalize_entries(plan)
        self.assertEqual([e["sku"]["name"] for e in entries], ["A", "B"])
        self.assertEqual(len(entries[1]["selected"]), 2)

    def test_v01_single_sku_fallback(self):
        """v0.1/v0.2 旧单款字段（product/selected）→ 合成一条目，老导出请求不炸。"""
        plan = {"product": {"color": "驼"}, "selected": {"white_bg": "x.jpg"}}
        entries = _normalize_entries(plan)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["color"], "驼")

    def test_empty_plan(self):
        self.assertEqual(_normalize_entries({"skus": []}), [])


if __name__ == "__main__":
    unittest.main()
