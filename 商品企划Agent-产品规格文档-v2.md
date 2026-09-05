# 商品企划生成 Agent · 产品规格文档（PRD v2.0）

> 本文档合并 v1.1 全部规格与 v2.0 重定位，为**唯一依据**的完整版：后续搭 agent 以本文档为准，不需再回看 v1.1。
> v2.0 变更：定位重校为**面向山姆的服装配饰 B端企划工具**；新增款轨道（三轴演变）与图轨道并列的双轨模型；新增 §6 B端语言（双价格/参数条/人群/日历）；数据模型补字段；导出升级多页 deck；技术栈按实际落地修订。**v1.1 核心 MVP（锚点→图轨道→企划）保留不动。**
> 钟于泊 · 2026-09-05（v1.1 · 2026-09-02）

---

## 1. 产品定位

**一句话**：把「一张畅销款图」变成「一套可递给山姆买手的产品企划 deck」——畅销款拆解 → 单轴演变 → AI 出图 → B端推介 PPT。

对齐利丰 C2M 产品企划 AI 岗职责链：**数据选款 → AI 图生图演变 → B端推介**。核心不是设计审美，是「畅销品判断 + AI 快速出概念」。

**核心形态**：一个「图 → 图」转换引擎 + 一个「款 → 款」演变引擎，外面套「演变轨道 × 图类型轨道」双轨点选交互。
**目标用户**：利丰 iBiR 的商品企划 / 买手（不懂 prompt，全程点选）。
**品类边界**：服装配饰（围巾/帽子/手套/袜子/领带/皮带），面向山姆等会员制零售商的 B端供货企划。

**最小核心 = 4 件事**：
1. 一张**锚点图**（畅销款起点，上传即识别）
2. **单轴演变**（改色/改细节/改廓形，锁 DNA 出相似款）
3. **图→图派生**（七类图轨道，转换矩阵约束）
4. 累积成**企划 deck**（参数条 + 双价格 + 编排导出）

---

## 2. 核心概念：双轨道模型

先定「款」，再定「图」：

```
锚点图（畅销款）
   │
   ├── 款轨道：演变（改色/改细节/改廓形）→ 演变款 = 新 SKU 概念
   │              └── 演变款可设为新锚点，再进任一轨道
   └── 图轨道：白底/商拍/氛围/细节/面料/说明/模特 → 该 SKU 的完整图库
```

### 2.1 款轨道 —— 三轴演变

对应 JD 核心动作「对现有畅销款微调/演变，产出新产品视觉概念图」。入口是畅销款参考图（锚点），只动一个轴，其余 DNA 全锁。

| 演变轴 | 英文 | 例 |
|---|---|---|
| 改色 | color | 驼色 → 炭灰 |
| 改细节 | detail | 净色 → 字母提花 |
| 改廓形 | silhouette | 窄版 → 宽版加厚 |

**锁词机制（VARIATION_REF_LOCK）**：材质/织法/比例/全部设计细节 EXACT same，仅演变轴允许变化；产出必须是「同族兄弟款」（same family, same DNA），不是复制品，也不是另一个产品。

**产出**：演变款图 + before/after 对比记录（before 路径 / after 路径 / 轴 / 改动描述），纳入企划后进逐款页。

**设计方向 = 演变轴语言**：真实企划 deck（COLE HAAN FW26）每款页写的「设计方向：① 字母提花 ② 正反异色」本质就是演变轴（① 改细节 ② 改色）。逐款页的「设计方向」与演变功能共用同一数据结构（§7.2 `design_directions`）。

### 2.2 图轨道 —— 七类图

| id | 名称 | 作用 | 能否作源 | 生成方式 |
|---|---|---|---|---|
| white_bg | 白底图 | 产品身份证，最干净锚点 | ✅ 枢纽 | 图生图 + rembg 抠图 |
| studio | 商拍图 | 产品定调（质感/档次） | ✅ 枢纽 | 图生图 / Seedream |
| lifestyle | 氛围图 | 场景代入（卖给谁/什么场景） | ⚠️ 次源 | 图生图 + 模特参考图 |
| detail | 细节图 | 品质论证（结构/工艺） | ⚠️ 终点为主 | 原图局部裁剪 + i2i 放大 |
| fabric | 面料图 | 材料透明（纹理/结构） | ❌ 终点 | 原图中心裁剪 + i2i 放大 |
| annotation | 说明图 | 规格透明（尺寸/功能标注） | ❌ 终点 | ⚠️ v2 降级为兜底（见下） |
| model | 模特上身图 | 上身效果 | ⚠️ 次枢纽 | 图生图 + 模特参考图锁一致性 |

**annotation 降级修正（v2）**：真实企划 deck 的「规格透明」用的是**文字参数条**（成分/规格/功能直接排版），不是生成图。逐款页参数条优先（§6.2），annotation 生成图可选兜底。

### 2.3 转换矩阵（source → 可用 target）

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

### 2.4 节点状态机（4 态）

| 状态 | 显示 | 含义 |
|---|---|---|
| 已生成 | ● 实心 | 该类型图已在当前企划中 |
| 当前 | ◎ 高亮 | 正在配置下拉、待生成 |
| 可点 | ○ 空心 | 转换矩阵允许从某「已生成」节点到达 |
| 不可点 | ✕ 灰 | 转换矩阵不允许，或缺少必要源图 |

**轨道规则**：
1. 锚点图决定起点；起点节点标记「已生成」。
2. 任一「已生成」节点能到达的所有 target（按矩阵）点亮为「可点」。
3. 点「可点」节点 → 变「当前」→ 下拉配置 → 生成 → 变「已生成」。
4. 轨道是「并查集」：多张已生成图的 target 并集同时点亮。

---

## 3. 能力排布：企划方向轨道 + 双轨下层

### 3.1 企划方向轨道（上层选择器）

下拉选方向 → 自动切换默认品类库 + 对标库 + 氛围色调。三个方向（对应山姆已验证爆款锚点）：

| 方向 | 对标大牌 | 默认品类 | 山姆锚点爆款 |
|---|---|---|---|
| 羽绒/户外保暖 | 波司登 / 加拿大鹅 / Moncler | 羽绒帽、羽绒手套、脖套围巾、保暖袜 | 499元400g羽绒服 |
| 静奢/老钱风 | Loro Piana / Brunello Cucinelli / The Row | 山羊绒围巾、真丝方巾、羊皮手套、羊毛帽 | 299羊绒衫、5A桑蚕丝 |
| 轻运动/瑜伽 | lululemon / Alo / Vuori | 运动袜、发带、瑜伽垫、防晒配件 | 瑜伽裤(lulu平替) |

> 优先级（面试弹药，非产品逻辑）：羽绒配件 > 静奢围巾丝巾 > 运动配件（运动有 lululemon 起诉 Costco 的侵权红线）。

### 3.2 双轨下层

方向之下并列两条轨道：**款轨道**（§2.1 演变）先定「这个企划推什么款」，**图轨道**（§2.2 七类图）再定「这个款怎么拍」。MVP 可只用图轨道（v1.1 行为），款轨道从锚点直接进入。

---

## 4. 界面设计（v1.1 四区块 + v2 两处新增，左→右）

```
┌─────────────────────────────────────────────────────────────┐
│  商品企划生成器                          [导出企划 → Deck]     │
├─────────────────────────────────────────────────────────────┤
│ ① 锚点图（左）        │ ② 双轨道（顶）                        │
│ ┌───────────┐        │  款轨道: [改色▾][改细节▾][改廓形▾]      │
│ │  [上传]    │        │         → [出相似款]                   │
│ │ [识别:白底]│        │  图轨道: ●白底 → ◎商拍 → ○氛围 →       │
│ │  [改类型▾] │        │   ○细节 → ○面料 → ○说明 → ○模特        │
│ └───────────┘        │   (矩阵自动亮/灰)                      │
│ [🧬 出相似款↓]       ├──────────────────────────────────────┤
│  before│after 对比卡  │ ③ 下拉选项（一条条，不写 prompt）       │
│                     │  方向:[静奢/老钱▾] 品类:[山羊绒围巾▾]    │
│                     │  颜色:[驼色▾] 场景:[冬季通勤▾]           │
│                     │  零售商:[山姆▾] 数量:[3▾]               │
│                     │  [生成这张图]                          │
├─────────────────────────────────────────────────────────────┤
│ ④ 结果区：3 张变体横向排列 → 点选 1 张纳入企划                  │
│  [图1]  [图2]  [图3]        （演变款 before/after 单独对比卡）  │
│ ⑤ 企划盘侧栏（完整版）：每个纳入 SKU 一张卡（缩略图+状态）       │
└─────────────────────────────────────────────────────────────┘
```

**五区块职责**：
1. **锚点图**：上传即识别类型（qwen-vl-max），可手动改。
2. **双轨道**：款轨道（三轴演变按钮）+ 图类型轨道（七类节点 4 态状态机）。
3. **下拉选项**：方向 / 品类 / 颜色 / 场景 / 零售商 / 数量（+ 演变轴 / 改动描述）。
4. **结果区**：多变体横向选，选中纳入；演变款出 before/after 对比卡。
5. **企划盘侧栏（完整版）**：MVP 单款隐藏；多 SKU 时每个纳入 SKU 一张卡。

---

## 5. 完整交互流（3 阶段）

### 阶段 1 起盘
上传一张图 → 识别类型 → 锚点节点「已生成」；或「纯文字起盘」→ 先生成白底锚点图。

### 阶段 2 转换（先定款、再出图，可循环）
1. **定款**：款轨道选演变轴 + 改动描述 → 生成演变款 → 选 1 张 → before/after 纳入企划。
2. **出图**：图轨道点「可点」节点 → 下拉配置 → 生成 N 变体 → 选 1 → 节点「已生成」。
3. 演变款可设为新锚点，重复 1-2。

### 阶段 3 组装
点「导出企划」→ 按 §8 deck 结构生成**多页 PPT + HTML**（含参数条/双价格/演变对比/耗时）。

### 完整案例（方向 → 演变 → 出图 → deck）
```
1. 下拉「方向=静奢/老钱」→ 品类库带入「山羊绒围巾 / 真丝方巾 / 羊皮手套...」
2. 上传白底山羊绒围巾图 → 识别「白底」→ 白底节点●
3. 款轨道：[改细节] + 「净色改字母提花」→ 出相似款 → before/after 纳入
4. 图轨道亮起：商拍/氛围/细节/面料/说明/模特 全可点
5. 点「商拍」→ 颜色=驼色, 零售商=山姆, 数量=3 → 选 1 → 商拍●
6. 点「氛围」→ 场景=冬季通勤 → 选 1 → 氛围●
7. 点「细节」→ 结构=织边/穗 → 选 1 → 细节●
8. [导出企划] → 生成 9 页 deck：封面/方法/人群/逐款页(参数条+双价格+before-after)/图体系/日历/尾页
```

---

## 6. B端语言：山姆买手看什么（v2 新增）

COLE HAAN FW26 真实企划 deck（29页）每款页必带三样东西，是字段标准的依据：

### 6.1 双价格体系

| COLE HAAN 用语 | 山姆版用语 | 字段 |
|---|---|---|
| MSRP（零售指导价） | 会员价 | `price.msrp` |
| WHOLESALE（批发价） | 供货价 | `price.wholesale` |

买手赚差价，**没有供货价 = 没法算毛利 = 不合格的 B端企划**。v1.1 硬编码「¥299–499」废弃。

### 6.2 参数条字段标准（逐款页必带）

```
成分（composition）   "100%山羊绒" / "51%羊毛 49%桑蚕丝"
规格（spec）          "180×30CM（含穗）"
细度（fineness）      "16.5um"（面料类）
功能（attributes）    "7A抗菌 / 手工无感袜头收口"（可空）
```

**这四行就是 JD 功能 5「采购对接：设计可生产」在 deck 里的呈现形式**——真实 deck 不上成本系统，参数写全即可。

### 6.3 人群画像 + 开发日历（deck 固定结构）

- **人群画像页**：每方向挂 3 类人群文案（`direction.personas`）。真实 deck 无销售数据页，入口就是人群画像——「趋势识别」在真实企划里的表达形式。
- **开发日历页**：8 节点时间线（企划→设计企划→产品开发→定版→下单→备料生产→验货出货→进店销售），静态模板 + AI 压缩标注（设计出图 5 人日 → 45 分钟）。

### 6.4 零售商风格后缀（生图用）

```json
{
  "retailer_style": {
    "山姆": "no logo, quiet luxury, visible raw-material grade (支数/等级 parameter tag), earth-tone palette, warm studio lighting, member's club quality",
    "京东": "high cost-performance, clean e-commerce, data-driven",
    "BigOffs": "outlet discount, brand off-price, sharp price tag"
  }
}
```

---

## 7. 后端数据模型（agent 直接消费的 JSON）

### 7.1 图类型定义 + prompt 模板（image_types.json，沿用 v1.1 实装）

```json
{
  "image_types": {
    "white_bg":  { "name": "白底正面图", "prompt_template": "{product} isolated on pure white background, front view, product-only, no shadow, centered, e-commerce photo", "aspect_ratio": "1:1" },
    "studio":    { "name": "商拍图",   "prompt_template": "professional studio product photography, {product} as hero, softbox key+rim light, {material} texture, clean neutral background", "aspect_ratio": "4:5" },
    "lifestyle": { "name": "氛围图",   "prompt_template": "lifestyle photo, {persona} using {product} in {scene}, natural light, shallow dof, product in focus", "aspect_ratio": "16:9" },
    "detail":    { "name": "细节图",   "prompt_template": null, "i2i_crop": 0.8, "aspect_ratio": "1:1" },
    "fabric":    { "name": "面料图",   "prompt_template": null, "i2i_crop": 0.65, "fabric_type_branch": true },
    "annotation":{ "name": "说明图",   "prompt_template": "clean flat product diagram on light neutral bg, front+side view, space for dimension annotation, no text", "aspect_ratio": "1:1" },
    "model":     { "name": "模特上身图", "prompt_template": null, "needs_model_ref": true, "aspect_ratio": "1:1" }
  }
}
```

**实装说明（与 v1.1 计划的差异）**：detail/fabric 不再走文生图模板，改为**裁原图局部 + i2i 放大还原**（detail 裁 0.8 保留结构，fabric 裁 0.65 取中心纹理）——文生图材质颜色对不上；fabric 按 `fabric_type` 分 5 支模板（knit/print/leather/down/texture，丝巾=print）。

### 7.2 sku 对象（v2 补 6 字段，加粗为新增）

```json
{
  "name": "山羊绒围巾", "en": "cashmere scarf",
  "benchmark": "Loro Piana",
  "material": "16.5um 小山羊绒", "material_en": "16.5 micron baby cashmere",
  "craft": "12 针精纺", "craft_en": "12-gauge fine knit",
  "detail_point_en": "fine knit stitch and hand-rolled fringe",
  "weave_en": "tight twill cashmere weave", "fiber_en": "...",
  "fabric_type": "knit", "persona_en": "urban middle-class professional, understated luxury",
  "colors": [ { "zh": "驼色", "en": "camel" }, ... ],
  "scenes": [ { "zh": "冬季通勤", "en": "winter city commute, wool coat, morning light" }, ... ],

  "composition": "100%山羊绒",
  "spec": "窄版 180×30CM（含穗）/ 宽版 200×52CM（含穗）",
  "fineness": "16.5um",
  "price": { "msrp": 399, "wholesale": 199, "currency": "¥" },
  "attributes": { "功能": "无logo / 手工卷边穗" },
  "design_directions": [
    { "axis": "detail", "desc": "字母提花" },
    { "axis": "color",  "desc": "正反异色" }
  ]
}
```

> 价格数值为占位，directions.json 填充时按山姆价带校准（**needs_confirmation**，不编造毛利数据）。

### 7.3 direction 对象（v2 补 personas）

```json
{
  "anchor_sku": "299羊绒衫 / 5A桑蚕丝",
  "tone": "...",
  "personas": [
    { "name": "城市老钱",  "desc": "沉稳、内敛、非凡成就" },
    { "name": "都市菁英",  "desc": "质感、精致、全球视野" },
    { "name": "Z世代新贵", "desc": "自信、独立、充满激情" }
  ],
  "skus": [ "…§7.2 结构，每方向 4 个 SKU 同构…"]
}
```

### 7.4 品类库 + 对标库（按方向组织，沿用 v1.1 三方向）

方向轨道下拉选方向 → 自动带入品类 + 对标大牌 + 参数。每个 SKU 挂大牌 benchmark + 核心参数，生图 prompt 自动带参数卖点（本 Agent 区别于「只会用 Midjourney 的设计师」的关键）。

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

> 上表为速览格式；磁盘上 `directions.json` 的 sku 已是 §7.2 全字段结构，v2 补的字段（composition/spec/fineness/price/attributes/design_directions）逐 SKU 填充。MVP 默认 = **静奢/老钱风 → 山羊绒围巾**。

### 7.5 企划 plan（单款 MVP → 企划盘完整版）

```json
// MVP（单款）
{
  "direction": "静奢/老钱风", "retailer": "山姆",
  "sku": { "…§7.2 全字段…" },
  "selected": { "white_bg": "path", "studio": "path", "lifestyle": "path", "detail": "path" },
  "variation": { "before": "path", "after": "path", "axis": "detail", "change": "净色改字母提花" },
  "timing": { "evolve_sec": 34, "images_sec": 412, "total_min": 8 }
}

// 完整版（企划盘）
{
  "direction": "...", "retailer": "...",
  "skus": [ { "sku": {}, "selected": {}, "variation": {} } ],
  "timing": { }
}
```

### 7.6 编排规则（沿用 v1.1）

```json
{
  "layout_order": ["lifestyle", "studio", "white_bg", "detail", "fabric", "annotation", "model"],
  "quick_proposal": ["lifestyle", "studio", "white_bg", "detail"],
  "fallback": "企划里缺的图类型标「待补」，前端提示还差几张"
}
```

---

## 8. 导出：企划 deck 结构（v2 新增，两档）

### 8.1 MVP deck（单款，9 页）

| 页 | 内容 | 数据来源 |
|---|---|---|
| P01 封面 | 方向 × 季节 × 「AI 企划」副标题 | plan 元信息 |
| P02 企划方法 | 4 步流程（锚点拆解→单轴演变→AI出图→组装）+ 工具/耗时 | 静态模板 |
| P03 人群画像 | 3 类人群 | direction.personas |
| P04 逐款页 | 图组 + **参数条 + 双价格 + 设计方向（演变轴）+ before/after 对比** | sku 全字段 |
| P05 AI 出图体系 | 该 SKU × 图类型矩阵 | plan.selected |
| P06 开发日历 | 8 节点 + AI 压缩标注 | 静态模板 |
| P07 尾页 | 工具链 + **真实耗时拆解** | plan.timing |

（HTML 单页滚动式；PPTX 多 slide。页面模板共 7 种函数，方法/日历/尾页为静态模板，一次成本。）

### 8.2 完整版 deck（企划盘，15 页，对齐 COLE HAAN 真实结构）

在 MVP deck 基础上插入：**产品结构总表**（品类×SPU×SKU×TTL，由 plan.skus 聚合）、**逐款页 × N**、**品类矩阵页 × 3**（帽子手套/袜子/皮带领带拼版 + 每款价格）。

---

## 9. Agent 编排（技术栈按 9/5 实际落地修订）

| 层 | v1.1 计划 | 实际落地 |
|---|---|---|
| 前端 | Streamlit | **Flask + 自定义前端**（static/，点选式交互，后台线程+轮询） |
| 生图 | Seedream 为主 | **qwen-image-3.0-pro 图生图为主**（同步接口，20-60s/张，prompt_extend 已关提速） |
| 演变 | — | qwen i2i + VARIATION_REF_LOCK（已跑通） |
| 识别 | — | qwen-vl-max 锚点识别 → 自由格式 sku 字段（已跑通） |
| 视频 | — | Seedance（已具备，未接入，M7） |
| 导出 | exporter | **exporter.py 重写为 deck 生成器**（M5 核心工作） |
| 备选 | ComfyUI/VTON/rembg | 保留为完整版选项 |

### 执行流
```
用户选方向 → 上传/生成锚点图
 → 款轨道：演变(轴+改动) → before/after 纳入
 → 图轨道：逐节点 generate(参数) → 选图 → 累积 plan.selected
 → 导出：exporter 按 §8 组装 deck（读 sku 字段 + timing）→ PPT/HTML
```

---

## 10. MVP 范围 vs 完整版

| | MVP（面试 demo，核心保留） | 完整版（入职后） |
|---|---|---|
| 流程 | 单 SKU：锚点 → 演变 → 图轨道 → 导出 | 企划盘多 SKU |
| 轨道 | 款轨道 + 图轨道（4 类图：白底/商拍/氛围/细节） | 全 7 类 + 企划盘侧栏 |
| 导出 | **MVP deck 9 页** | 完整 15 页 + 总表 + 矩阵页 |
| 品类 | 静奢/老钱 → 山羊绒围巾（+2-3 款） | 三方向全品类库 |
| 视频 | 无 | Seedance 视频样稿页 |
| 目标 | 面试 live demo：45 分钟出全套 | 真能用 |

---

## 11. 里程碑（v1.1 M0-M3 已完成，v2 接续）

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0-M3 | PRD v1.1 + 单款全流程跑通（演变/七类图/识别/导出 1 页/Flask 前端） | ✅ 完成（9/4） |
| **M5** | 字段升级（§7.2/7.3）+ exporter 重写：单款 MVP deck 9 页 | 待做 |
| **M6** | 企划盘多 SKU（企划盘侧栏 + /api/export 升级 + 总表/矩阵页） | 待做 |
| **M7** | 耗时统计（plan.timing 真实数据）+ Seedance 视频样稿页 + bug 修复（0字节图清理/参考图库入口砍除） | 待做 |
| **M8** | 演示故事线固化：载入 → 演变 → 出图 → 导出 deck → 尾页真实耗时 | 待做 |
| M4 | 「商品企划版」简历 + 背山姆硬数据（499羽绒服/299羊绒/5A桑蚕丝） | 待做 |

---

## 12. 待确认开放项

1. **双价格口径**：山姆价带下 会员价/供货价 比例（需校准，不编造毛利）。
2. **企划盘侧栏交互形态**：侧栏列表 vs 顶部 SKU Tab。
3. **annotation 说明图**：v2 方案为降级兜底（参数条优先），是否彻底砍掉？
4. 耗时拆解页的口径：按 plan.timing 真实累计 vs 固定「45 分钟」叙事（建议真实数据，封面可保留「45 分钟」话术）。

---
*v2.0 变更摘要：合并 v1.1 全部规格；定位改山姆 B端；双轨模型（款轨道=三轴演变 + 图轨道=七类图）；annotation 降级；§6 B端语言；数据模型 sku+6 字段 / direction+personas / plan+timing；导出两档 deck（9 页 MVP / 15 页完整）；技术栈按实装修订（Flask + qwen-image）；里程碑 M5-M8 接续。*
