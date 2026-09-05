# 商品企划生成 Agent · 产品规格文档（PRD v1.1）

> 最终版，合并 v0.1（后端数据模型）+ v0.2（企划端交互）。后续搭 agent 以本文档为唯一依据。
> v1.1：新增「企划方向轨道 + 对标库」，MVP 品类改为「山羊绒围巾」。
> 钟于泊 · 2026-09-02

---

## 1. 产品定位

把「一张图 / 一个品类想法」变成「一套完整商品企划」：多类型图库 + 选品逻辑 + 编排好的推介 PPT。

**核心形态**：一个「图 → 图」转换引擎，外面套一层「图类型轨道 + 下拉向导」。
**目标用户**：利丰 iBiR 的商品企划 / 买手（不懂 prompt，全程点选）。

**最小核心 = 3 件事**（砍掉营销端，只留设计+表现）：
1. 一张**锚点图**（上传即识别类型）
2. **图→图派生**（轨道点选，转换矩阵约束）
3. 累积成**企划**（编排 + 导出 PPT）

---

## 2. 核心概念：七类图 + 转换矩阵

### 2.1 七类图

| id | 名称 | 作用 | 能否作源 | 生成方式 |
|---|---|---|---|---|
| white_bg | 白底图 | 产品身份证，最干净锚点 | ✅ 枢纽 | 生图 + rembg 抠图 |
| studio | 商拍图 | 产品定调（质感/档次） | ✅ 枢纽 | Seedream / ComfyUI |
| lifestyle | 氛围图 | 场景代入（卖给谁/什么场景） | ⚠️ 次源 | Seedream |
| detail | 细节图 | 品质论证（材质/工艺） | ⚠️ 终点为主 | 图生图/局部重绘 |
| fabric | 面料图 | 材料透明（纹理/结构） | ❌ 终点 | 微距 + 标注 |
| annotation | 说明图 | 规格透明（尺寸/功能标注） | ❌ 终点 | 干净底图 + SVG 标注 |
| model | 模特上身图 | 上身效果 | ⚠️ 次枢纽 | 虚拟试穿 (IDM-VTON/CatVTON) |

### 2.2 转换矩阵（source → 可用 target）

| 源 \ 目标 | 白底 | 商拍 | 氛围 | 细节 | 面料 | 说明 | 模特 |
|---|---|---|---|---|---|---|---|
| 白底 | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 商拍 | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| 氛围 | ✅ | ✅ | — | ❌ | ❌ | ❌ | ✅ |
| 细节 | ✅ | ❌ | ❌ | — | ❌ | ❌ | ❌ |
| 面料 | ❌ | ❌ | ❌ | ❌ | — | ❌ | ❌ |
| 说明 | ❌ | ❌ | ❌ | ❌ | ❌ | — | ❌ |
| 模特 | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | — |

**三条枢纽规则**：① 白底+商拍=枢纽源；② 模特=次枢纽；③ 氛围/细节/面料/说明=终点。

```json
{
  "transforms": {
    "white_bg":  ["studio", "lifestyle", "detail", "fabric", "annotation", "model"],
    "studio":    ["white_bg", "lifestyle", "detail", "fabric", "annotation", "model"],
    "lifestyle": ["white_bg", "studio", "model"],
    "detail":    ["white_bg"],
    "fabric":    [],
    "annotation":[],
    "model":     ["white_bg", "studio", "lifestyle"]
  }
}
```

---

## 3. 能力排布：企划方向轨道 + 图类型轨道

### 3.1 企划方向轨道（上层选择器）

在图类型轨道之上加一层「企划方向」，下拉选方向 → 自动切换默认品类库 + 对标库 + 氛围图色调。三个方向（对应山姆已验证的爆款锚点）：

| 方向 | 对标大牌 | 默认品类 | 山姆锚点爆款 |
|---|---|---|---|
| 羽绒/户外保暖 | 波司登 / 加拿大鹅 / Moncler | 羽绒帽、羽绒手套、脖套围巾、保暖袜 | 499元400g羽绒服 |
| 静奢/老钱风 | Loro Piana / Brunello Cucinelli / The Row | 山羊绒围巾、真丝方巾、羊皮手套、羊毛帽 | 299羊绒衫、5A桑蚕丝 |
| 轻运动/瑜伽 | lululemon / Alo / Vuori | 运动袜、发带、瑜伽垫、防晒配件 | 瑜伽裤(lulu平替) |

> 优先级（面试弹药，非产品逻辑）：羽绒配件 > 静奢围巾丝巾 > 运动配件（运动有 lululemon 起诉 Costco 的侵权红线）。

### 3.2 图类型轨道（下层）

七类图排成一条轨道（不是 MuseGate 的营销链路）：

```
锚点图 ──→ 白底 ──→ 商拍 ──→ 氛围 ──→ 细节 ──→ 面料 ──→ 说明
                              └────→ 模特 ────┘
```

**节点状态机（4 态）：**

| 状态 | 显示 | 含义 |
|---|---|---|
| 已生成 | ● 实心 | 该类型图已在当前企划中 |
| 当前 | ◎ 高亮 | 正在配置下拉、待生成 |
| 可点 | ○ 空心 | 转换矩阵允许从某「已生成」节点到达 |
| 不可点 | ✕ 灰 | 转换矩阵不允许，或缺少必要源图 |

**轨道规则：**
1. 锚点图决定起点；起点节点标记「已生成」。
2. 任一「已生成」节点，能到达的所有 target（按矩阵）都点亮为「可点」。
3. 用户点「可点」节点 → 变「当前」→ 右侧出下拉 → 生成 → 变「已生成」。
4. 轨道是「并查集」：多张已生成图会同时扩大可点范围（如已生成白底+商拍，则它们的 target 并集都点亮）。

---

## 4. 界面设计（参考绘蛙的引导式，左→右）

```
┌─────────────────────────────────────────────────────────────┐
│  商品企划生成器                          [导出企划 → PPT]      │
├─────────────────────────────────────────────────────────────┤
│ ① 锚点图（左）        │ ② 图类型轨道（顶）                     │
│ ┌───────────┐        │  ●白底 → ◎商拍 → ○氛围 → ○细节 →      │
│ │  [上传]    │        │  ○面料 → ○说明 → ○模特                 │
│ │ [识别:白底]│        │  (矩阵自动亮/灰)                       │
│ │  [改类型▾] │        ├──────────────────────────────────────┤
│ └───────────┘        │ ③ 下拉选项（一条条，不写 prompt）
│                      │  方向:[静奢/老钱▾] 自动带品类/对标       │
│                      │  目标图:[商拍▾] 品类:[山羊绒围巾▾]       │
│                      │  材质:[16.5um山羊绒▾] 颜色:[驼色▾]        │
│                      │  场景:[影棚▾] 零售商:[山姆▾] 数量:[3▾]  │
│                      │  [生成这张图]                          │
├─────────────────────────────────────────────────────────────┤
│ ④ 结果区：3 张变体横向排列 → 点选 1 张纳入企划（同 seed 风格统一）│
│  [图1]  [图2]  [图3]                                          │
└─────────────────────────────────────────────────────────────┘
```

**四区块职责：**
1. **锚点图**：上传即识别类型，可手动改。= 绘蛙的「上传平铺图」。
2. **图类型轨道**：七类节点 + 4 态状态机，矩阵自动亮/灰。
3. **下拉选项**：方向 / 目标图类型 / 品类 / 材质 / 颜色 / 场景 / 零售商 / 数量。
4. **结果区**：多张变体横向选，选中纳入企划。

---

## 5. 完整交互流（3 阶段）

### 阶段 1 起盘
- 上传一张图 → 系统识别类型 → 锚点节点「已生成」；或「纯文字起盘」→ 先生成白底锚点图。

### 阶段 2 转换（可循环）
1. 点轨道上「可点」节点 → 变「当前」。
2. 填下拉：方向（自动带入品类/对标）、目标图类型（自动=所点节点）、品类、材质、颜色、场景、零售商、数量。
3. 点「生成这张图」→ 出 N 张变体 → 选 1 张 → 该节点变「已生成」。
4. 重复，直到集齐目标图库。

### 阶段 3 组装
- 点「导出企划」→ LLM 生成选品逻辑 + 按编排规则排版 → 导出 PPT/PDF/HTML。

### 完整案例（方向 → 白底 → 商拍 → 氛围 → 企划）
```
1. 下拉选「方向=静奢/老钱」→ 品类库自动带入「山羊绒围巾 / 真丝方巾 / 羊皮手套...」
2. 上传白底山羊绒围巾图 → 识别「白底」→ 白底节点●（或纯文字起盘生成白底）
3. 轨道亮起：商拍/氛围/细节/面料/说明/模特 全可点
4. 点「商拍」→ 下拉:品类=山羊绒围巾,材质=16.5um山羊绒,颜色=驼色,零售商=山姆,数量=3
5. 生成 3 张商拍 → 选 1 → 商拍节点●
6. 点「氛围」→ 场景=冬季通勤,人群=中产家庭 → 生成 → 选 → 氛围节点●
7. 点「细节」→ 卖点=16.5um羊绒+12针精纺 → 生成 → 选 → 细节节点●
8. [导出企划] → 按 氛围→商拍→白底→细节 编排成 1 页推介 PPT
```

---

## 6. 后端数据模型（agent 直接消费的 JSON）

### 6.1 图类型定义 + prompt 模板

```json
{
  "image_types": {
    "white_bg": {
      "name": "白底正面图",
      "prompt_template": "{product} isolated on pure white background, front view, product-only, no model, no shadow, centered, e-commerce photo --ar 1:1",
      "provider": "comfyui",
      "needs_rembg": true
    },
    "studio": {
      "name": "商拍图",
      "prompt_template": "professional studio product photography, {product} as hero, softbox key+rim light, {material} texture, clean neutral background --ar 4:5",
      "provider": "seedream",
      "needs_rembg": false
    },
    "lifestyle": {
      "name": "氛围图",
      "prompt_template": "lifestyle photo, {persona} using {product} in {scene}, natural light, shallow dof, product in focus --ar 16:9",
      "provider": "seedream",
      "needs_rembg": false
    },
    "detail": {
      "name": "细节图",
      "prompt_template": "extreme close-up macro of {detail_point}, {material} texture, {craft}, single selling point, blurred bg --ar 1:1",
      "provider": "comfyui",
      "needs_rembg": false
    },
    "fabric": {
      "name": "面料结构图",
      "prompt_template": "macro fabric texture of {weave}, visible thread structure of {fiber}, flat lay --ar 1:1",
      "provider": "comfyui",
      "needs_rembg": false
    },
    "annotation": {
      "name": "说明图",
      "prompt_template": "clean flat product diagram on light neutral bg, front+side view, space for dimension annotation, no text --ar 1:1",
      "provider": "seedream",
      "needs_svg_overlay": true
    },
    "model": {
      "name": "模特上身图",
      "prompt_template": null,
      "provider": "vton",
      "needs_vton": true
    }
  }
}
```

### 6.2 一次生成的参数（向导收集 → prompt 组装）

```json
{
  "source": { "type": "white_bg", "image": "upload/xxx.png" },
  "target": "studio",
  "direction": "静奢/老钱风",
  "product": { "category": "山羊绒围巾", "material": "16.5um山羊绒", "color": "驼色", "price_band": "$59.9", "benchmark": "Loro Piana 平替" },
  "scene": "影棚",
  "retailer": "山姆",
  "count": 3
}
```

**prompt 组装规则：**
```
target_prompt = image_types[target].prompt_template
  .replace("{product}", category + color + material + benchmark)
  .replace("{material}", material)
  .replace("{persona}", 目标人群)   // 氛围图专用
  .replace("{scene}", scene)        // 氛围图专用
  + retailer_style[retailer]        // 山姆/京东/BigOffs 风格后缀
若 source.image 存在 → 作为 init image 传给 provider（i2i）
```

### 6.3 零售商风格后缀

```json
{
  "retailer_style": {
    "山姆": "no logo, quiet luxury, visible raw-material grade (充绒量/支数/等级 parameter tag), earth-tone palette, warm studio lighting, member's club quality",
    "京东": "high cost-performance, clean e-commerce, data-driven",
    "BigOffs": "outlet discount, brand off-price, sharp price tag"
  }
}
```

### 6.4 品类库 + 对标库（按企划方向组织）

方向轨道下拉选「方向」→ 自动带入下面的默认品类 + 对标大牌 + 参数。每个 SPU 挂一个大牌 benchmark + 核心参数，生图 prompt 自动带参数卖点（这是本 Agent 区别于「只会用 Midjourney 的设计师」的关键）。

```json
{
  "directions": {
    "羽绒/户外保暖": {
      "anchor_sku": "499元400g羽绒服",
      "skus": [
        { "name": "羽绒帽",   "benchmark": "加拿大鹅",  "params": "90%白鹅绒 / 充绒30g / 防风面料" },
        { "name": "羽绒手套", "benchmark": "Moncler",   "params": "90%鹅绒 / 触屏指 / 内里抓绒" },
        { "name": "脖套围巾", "benchmark": "波司登",    "params": "充绒量可视化 / 立领防风" },
        { "name": "保暖袜",   "benchmark": "Smartwool", "params": "美利奴羊毛 / 户外级" }
      ]
    },
    "静奢/老钱风": {
      "anchor_sku": "299羊绒衫 / 5A桑蚕丝",
      "skus": [
        { "name": "山羊绒围巾", "benchmark": "Loro Piana", "params": "16.5um小山羊绒 / 12针精纺 / 无logo" },
        { "name": "真丝方巾",   "benchmark": "爱马仕",     "params": "5A桑蚕丝 / 14姆米 / 手工卷边" },
        { "name": "羊皮手套",   "benchmark": "Coach",      "params": "头层羊皮 / 内里羊绒 / 手缝" },
        { "name": "羊毛帽",     "benchmark": "The Row",    "params": "美利奴羊毛 / 无logo / 极简" }
      ]
    },
    "轻运动/瑜伽": {
      "anchor_sku": "瑜伽裤(lulu平替)",
      "skus": [
        { "name": "运动袜",   "benchmark": "Bombas",    "params": "吸湿排汗 / 足弓支撑" },
        { "name": "发带",     "benchmark": "lululemon", "params": "吸汗 / 防滑硅胶条" },
        { "name": "瑜伽垫",   "benchmark": "Manduka",   "params": "6mm厚 / 防滑 / 轻量" },
        { "name": "防晒配件", "benchmark": "蕉下",      "params": "UPF100+ / 冰感" }
      ]
    }
  },
  "mvp_direction": "静奢/老钱风",
  "mvp_sku": "山羊绒围巾"
}
```

> MVP 默认 = **静奢/老钱风 → 山羊绒围巾**（对标 COLE HAAN 那份题目，用它的同赛道、压过它）。

### 6.5 编排规则

```json
{
  "layout_order": ["lifestyle", "studio", "white_bg", "detail", "fabric", "annotation"],
  "quick_proposal": ["lifestyle", "studio", "white_bg", "detail"],   // MVP 4 张即可
  "fallback": "企划里缺的图类型标「待补」，前端提示还差几张"
}
```

### 6.6 企划输出结构

```json
{
  "product": { "category": "山羊绒围巾", "material": "16.5um山羊绒", "color": "驼色", "price_band": "$59.9", "benchmark": "Loro Piana 平替" },
  "selection_logic": "LLM 生成：对标谁/人群/价格带/差异化",
  "images": { "white_bg": ["..."], "studio": ["..."], "lifestyle": ["..."], "detail": ["..."] },
  "layout": ["lifestyle", "studio", "white_bg", "detail"],
  "export": "PPT / PDF / HTML"
}
```

---

## 7. Agent 编排（技术栈 + 执行流）

### 7.1 技术栈（MVP）
- **编排**：Claude Code Skill（`trend-to-product`），前端 = HTML 结果页（后升级 Streamlit 真下拉向导）
- **生图接口（可插拔）**：Seedream（豆包 MCP，同步快，MVP 首选）→ 白底/细节接 ComfyUI
- **虚拟试穿**：CatVTON / IDM-VTON（模特图，后置）
- **抠图**：rembg；**标注**：SVG 模板

### 7.2 一个企划的执行流
```
用户选方向+品类 + 上传/生成白底锚点图
 → orchestrator 读 transforms.json + image_types.json
 → 逐条执行轨道选择（每次 = generate(参数) → 选图）
 → 累积到 plan.images
 → 用户点「导出企划」
 → LLM 生成 selection_logic + 按 layout_order 排版 → 导出 PPT/HTML
```

---

## 8. MVP 范围 vs 完整版

| | MVP（面试 demo） | 完整版（入职后） |
|---|---|---|
| 图类型 | 白底 + 商拍 + 氛围 + 细节（4 类） | 全 7 类 + 面料 + 说明 + 模特 |
| 生图接口 | 全走 Seedream | 白底/细节 ComfyUI，模特 VTON |
| 前端 | Claude Code Skill + HTML 结果页 | Streamlit 轨道+下拉向导 |
| 品类库 | 静奢/老钱 → 山羊绒围巾 1 个 | 三方向全品类库 JSON |
| 输出 | 1 页推介 PPT | 完整企划 + 多页 PPT |
| 目标 | 48h 内出敲门砖 + live demo | 真能用 |

---

## 9. 里程碑（落地顺序 = 一条线走穿，不并行）

1. **改 PRD**（本步）→ 2. **demo 只做「静奢老钱围巾」一条线**（M1→M3）→ 3. **背数据**（M4）。

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 本文档（规格冻结 + 方向轨道/对标库入库） | ✅ 完成 |
| M1 | 跑通「白底→商拍」单条转换 + 3 变体（Seedream），品类 = 山羊绒围巾 | 待搭 |
| M2 | 补齐 氛围/细节 + 编排成 1 页 PPT（企划端最小闭环） | 待搭 |
| M3 | 封装 `trend-to-product` Skill + HTML 结果页（live demo） | 待搭 |
| M4 | 出一版「商品企划版」简历 + 背山姆硬数据（499羽绒服/299羊绒/5A桑蚕丝/占销售40%） | 待搭 |

---

## 10. 待用户确认的 2 个开放项

1. 「详情介绍图」是否要作为独立第 8 类，还是并入「说明图」？（当前并入说明图）
2. MVP 前端：Skill + HTML 结果页（最快）vs Streamlit 真轨道向导（更像产品，但慢）？

---

*本文档为规格 v1.1，后续改动需在本文件更新并标注版本。*
