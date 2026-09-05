# 商品企划生成 Agent —— 产品设计文档（v0.1）

> 核心思路：一个「**图 → 图**」转换引擎，外面套一层**下拉向导**。用户上传一张图（或选一个品类）→ 下拉一步步选「要生成哪类图 / 什么商品 / 什么风格」→ 出图 → 累积成一套完整「**企划**」。
> 目标：让一个不懂 prompt 的企划/买手也能点选完成；也让后端 agent 能按结构化参数直接跑。

---

## 1. 产品定位（一句话）

把「一张图 / 一个品类想法」变成「**一套完整商品企划**」：多类型图库 + 选品逻辑 + 编排好的推介 PPT。

## 2. 核心概念：7 类图 + 转换矩阵

### 2.1 七类图（canonical）

| id | 名称 | 作用 | 能否作「源」(i2i 输入) | 生成方式 |
|---|---|---|---|---|
| white_bg | 白底图 | 产品身份证，最干净的锚点 | ✅ 枢纽 | 生图 + rembg 抠图 |
| studio | 商拍图 | 产品定调图（质感/档次） | ✅ 枢纽 | Seedream / ComfyUI |
| lifestyle | 氛围图 | 场景代入（卖给谁/什么场景） | ⚠️ 次源 | Seedream |
| detail | 细节图 | 品质论证（材质/工艺） | ⚠️ 终点为主 | 图生图/局部重绘 |
| fabric | 面料图 | 材料透明（纹理/结构） | ❌ 终点 | 微距 + 标注 |
| annotation | 说明图 | 规格透明（尺寸/功能标注） | ❌ 终点 | 干净底图 + SVG 标注 |
| model | 模特上身图 | 上身效果 | ⚠️ 次枢纽 | 虚拟试穿 (IDM-VTON/CatVTON) |

### 2.2 转换矩阵（source → 可用 target）

> 前端「目标图类型」下拉只显示 ✅ 的项。

| 源 \ 目标 | 白底 | 商拍 | 氛围 | 细节 | 面料 | 说明 | 模特 |
|---|---|---|---|---|---|---|---|
| 白底 white_bg | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 商拍 studio | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| 氛围 lifestyle | ✅ | ✅ | — | ❌ | ❌ | ❌ | ✅ |
| 细节 detail | ✅ | ❌ | ❌ | — | ❌ | ❌ | ❌ |
| 面料 fabric | ❌ | ❌ | ❌ | ❌ | — | ❌ | ❌ |
| 说明 annotation | ❌ | ❌ | ❌ | ❌ | ❌ | — | ❌ |
| 模特 model | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | — |

**三条枢纽规则（记牢）：**
1. **白底图 + 商拍图 = 枢纽源**，几乎能转到所有目标（商品信息最完整最干净）。
2. **模特上身图 = 次枢纽**，能转白底/商拍/氛围（脱模/换背景）。
3. **氛围/细节/面料/说明 = 终点**，基本只接收（细节可「还原」成白底，价值低）。

### 2.3 对应的 JSON（后端直接消费）

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

## 3. 前端交互：下拉向导（3 阶段）

### 3.1 整体流程

```
阶段1 起盘 → 阶段2 转换(可循环) → 阶段3 组装企划
```

### 3.2 每个下拉的精确选项

**阶段 1｜起盘（起点）**
| 下拉 | 选项 | 说明 |
|---|---|---|
| 起点方式 | 上传一张图 / 纯文字起盘 | 上传图 → 走 i2i；纯文字 → 先生成白底锚点图 |

**阶段 2｜一次「图→图」转换**
| 下拉 | 选项 | 逻辑 |
|---|---|---|
| ① 源图类型 | 白底图/商拍图/氛围图/细节图/面料图/说明图/模特图 | 系统自动识别（推荐）+ 可手动覆盖 |
| ② 目标图类型 | 按转换矩阵过滤后的 ✅ 项 | 例：源=白底 → 显示 商拍/氛围/细节/面料/说明/模特 |
| ③ 品类 | 级联多级：服饰配件→袜子 / 餐厨→水杯保温杯 / 收纳… | 读品类库 JSON |
| ④ 商品规格 | 材质 / 颜色 / 价格带 / 平替对象 | 4 个小下拉，或一个结构化面板 |
| ⑤ 目标零售商 | 山姆 / 京东 / BigOffs / 通用电商 | 决定白底规范、色调、文案风格 |
| ⑥ 生成数量 | 1 / 3 / 10 变体 | 变体共享同一种子，风格统一 |

→ 点「生成这张」→ 出图 → 存入当前企划图库

**阶段 3｜累积 & 组装**
- 「继续加一张」→ 回到阶段 2（源图可沿用上一张的产物，或新上传）
- 「生成完整企划」→ 按编排规则自动排版 → 出企划（选品逻辑 + 图库 + 推介 PPT）

### 3.3 一次「图→图」的完整路径示例

```
用户上传一张白底保温杯图
  ↓ 系统识别：源图类型 = 白底图
  ↓ 下拉② 目标：商拍图
  ↓ 下拉③ 品类：餐厨 → 水杯保温杯
  ↓ 下拉④ 规格：不锈钢 / 莫兰迪粉 / $19.98·2只 / Stanley平替
  ↓ 下拉⑤ 零售商：山姆
  ↓ 下拉⑥ 数量：3
  → 生成 3 张商拍图（同款保温杯的影棚质感图）
```

---

## 4. 输出：企划结构

```json
{
  "product": {
    "category": "餐厨/水杯保温杯",
    "material": "不锈钢",
    "color": "莫兰迪粉",
    "price_band": "$19.98/2只",
    "benchmark": "Stanley 平替"
  },
  "selection_logic": "LLM 生成的一段：对标谁/人群/价格带/差异化",
  "images": {
    "white_bg":  ["..."],
    "studio":    ["..."],
    "lifestyle": ["..."],
    "detail":    ["..."],
    "fabric":    ["..."],
    "annotation":["..."],
    "model":     ["..."]
  },
  "layout": ["lifestyle", "studio", "white_bg", "detail", "fabric", "annotation"],
  "export": "PPT / PDF / HTML"
}
```

> 编排顺序（买手 PPT）：氛围 → 商拍 → 白底 → 细节 → 面料 → 说明。缺哪类图就在企划里标「待补」，前端提示用户还差几张。

---

## 5. 后端数据模型（agent 直接消费）

### 5.1 图类型定义 schema

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

### 5.2 一次生成的参数（向导收集结果 → prompt 组装）

```json
{
  "source": { "type": "white_bg", "image": "upload/xxx.png" },
  "target": "studio",
  "product": { "category": "餐厨/水杯保温杯", "material": "不锈钢", "color": "莫兰迪粉", "price_band": "$19.98/2只", "benchmark": "Stanley 平替" },
  "retailer": "山姆",
  "count": 3
}
```

**prompt 组装规则：**
```
target_prompt = image_types[target].prompt_template
  .replace("{product}", 商品一句话描述 = category + color + material + benchmark)
  .replace("{material}", material)
  + retailer_style[retailer]   // 山姆=品质感/大包装；京东=高性价比；BigOffs=折扣心智
若 source.image 存在 → 作为 init image 传给 provider（i2i）
```

### 5.3 零售商风格后缀

| 零售商 | 风格后缀 |
|---|---|
| 山姆 | premium member's club quality, generous value packaging |
| 京东 | high cost-performance, clean e-commerce, data-driven |
| BigOffs | outlet discount, brand off-price, sharp price tag |

---

## 6. Agent 编排（怎么做成 agent）

### 6.1 技术栈（MVP）

- **编排**：Claude Code Skill（`trend-to-product`），前端是「HTML 结果页」或轻 Streamlit
- **生图接口（可插拔）**：Seedream（豆包 MCP，同步快，MVP 首选）→ 后续接 ComfyUI（白底精确）
- **虚拟试穿**：CatVTON / IDM-VTON（模特图，后置）
- **抠图**：rembg
- **标注**：SVG 模板（说明图尺寸线/箭头）

### 6.2 一个企划的 agent 执行流

```
用户选品类 + 上传/生成白底图
 → orchestrator 读 transforms.json + image_types.json
 → 逐条执行用户的下拉选择（每次 = 一次 generate(参数)）
 → 累积图片到 plan.images
 → 用户点「生成企划」
 → LLM 生成 selection_logic + 按 layout 排版 → 导出 PPT/HTML
```

### 6.3 MVP 边界 vs 完整版

| | MVP（面试 demo） | 完整版（入职后） |
|---|---|---|
| 图类型 | 白底 + 商拍 + 氛围 + 细节（4 类） | 全 7 类 + 面料 + 说明 + 模特 |
| 生图接口 | 全走 Seedream | 白底/细节接 ComfyUI，模特接 VTON |
| 前端 | Claude Code Skill + HTML 结果页 | Streamlit 下拉向导 |
| 品类库 | 1 个品类（水杯或收纳） | 全品类库 JSON |
| 输出 | 1 页推介 PPT | 完整企划 + 多页 PPT |

---

## 7. 下一步（等你拍板）

1. 确认 7 类图是否够（要不要加「详情介绍图」作为独立类型，还是并入说明图？）
2. MVP 前端形态：**Skill + HTML 结果页（最快）** vs **Streamlit 真下拉向导（更像产品）**
3. 先做的品类：**水杯保温杯** vs **收纳**
4. 定完我就开始搭 `trend-to-product`，先用 Seedream 跑通「白底→商拍」这一条转换。
