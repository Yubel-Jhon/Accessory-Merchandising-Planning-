# CLAUDE.md — 商品企划 Agent 项目地图

利丰 iBiR 面试作品。选款起盘 → 逐款出图（生成→看图→人工点选）→ 纳入企划盘 → 导出多款企划 deck（HTML+PPTX）。
生图走通义 qwen-image（DashScope），识别走 qwen-vl-max。

## 怎么跑

双击 `启动demo.bat`（或 `python server.py`）→ http://localhost:8000
测试：`python -m unittest discover -s tests`（改完共享逻辑必须跑一遍）

## 目录（改哪去哪）

| 路径 | 职责 |
|---|---|
| `server.py` | Flask 后端：路由 / 后台生图任务 / 导出入口。**不写 prompt、不做导出排版** |
| `scripts/core.py` | 共享核心：路径、API key 多源加载、静态数据装载、图类型常量、参考图检索、裁图 |
| `scripts/prompts.py` | **唯一 prompt 组装入口**（build_prompt / build_variation_prompt / build_cover_prompt） |
| `scripts/qwen_client.py` | DashScope 生图客户端（直连不走系统代理；401/403 翻译成中文） |
| `scripts/recognize.py` | qwen-vl 锚点图识别 + 库内款匹配打分 + 生成图一致性自检 |
| `scripts/exporter.py` | 企划盘 → HTML 长页 + 多 slide PPTX |
| `scripts/i2i.py` | 命令行图生图小工具（qwen_client 薄封装） |
| `static/` | 前端三件套（index.html / style.css / app.js） |
| `data/*.json` | 静态数据：方向×品类库 / 图类型模板 / 零售商风格 / 对标库 |
| `images/` | upload=用户上传 · output=生成图 · models=模特参考 · references=RAG 参考图库 |
| `demo/output/` | 导出的 deck（gitignore） |

## 统一命名（全项目只用一种叫法）

- 图类型 6 类：`white_bg / studio / lifestyle / detail / fabric / model`（中文名：白底/商拍/氛围/细节/面料/模特）
- 两层：`product` 层（white_bg/detail/fabric，不要模特）｜`scene` 层（studio/lifestyle/model，可带模特参考）
- 一次生成 = 一个 job（JOBS 字典，前端轮询 /api/status/<job_id>）
- 前端状态：`state.selected` 当前工作区 → 纳入后进 `state.planSkus`（企划盘）→ 导出成 `plan`
- 演变 = 出相似款，单轴 `color / detail / silhouette`（改色/改细节/改廓形）

## 文档权威版本

**唯一依据：`商品企划Agent-产品规格文档-v2.md`（PRD v2.0）。**
旧版文档（v0.1/v0.2/v1.1/优化报告）和备用前端已在桌面 `../服装企划agent-归档/`，不要回看、不要复活。

## 已拍板的决定（别再反复问）

1. **app.py（Streamlit）和 generate.py（批量 CLI）已归档（2026-09-05）**。要批量出图：给 server 加批量接口，复用 prompts.py，不复活旧脚本。
2. **Prompt 内容只有两个家**：`data/image_types.json` 管通用模板（事实源），`prompts.py` 管特殊分支模板（model/detail/fabric 的 i2i 与兜底）+ 组装逻辑。禁止出现第三处 prompt 文案。
3. **说明图（annotation）已彻底移除（2026-09-05）**：它曾只活在 exporter 的 TYPE_LABEL 里，前端轨道一直是 6 类。以后要加新图类型，必须 data/image_types.json + core.TRANSFORMS + 前端轨道 + exporter 四处一起加，不许只加一处。
4. 生图默认 `prompt_extend=False`（提速约 20 倍）；detail/fabric 必须走 crop_center 裁块 + 原图双参考（裁太大背景色会被织进面料，踩过坑）。
5. dashscope 请求绕过系统代理（`qwen_client._OPENER`），全局代理常死。
6. **画质定案（2026-09-05）**：默认 `qwen-image-3.0-pro`（要更快设 `DASHSCOPE_IMAGE_MODEL=qwen-image-3.0`）；`build_prompt` 全路径末尾注 QUALITY，product 层有锚点图再注 PRODUCT_REF_LOCK。对外耗时口径一律「约 1–3 分钟/张」（前端 loading / README / deck 方法页已同步）。
7. **自检与导语都「只提示不拦截」**：一致性自检（`recognize.check_consistency`，同步接口 `/api/check_consistency`）失败落 unknown；买手导语（`/api/sku_copy`）失败静默跳过。锦上添花的挂了不许拖垮出图主流程。
8. **企划盘本地暂存**：localStorage key `planDeck.v1`，只存已纳入成果（planSkus/耗时/封面/整体风格/导语），工作区半成品不存；改 planSkus 条目结构时同步看 `saveState/restoreState`。
9. 演变默认一轴出 **3 案**（`/api/variation` 的 count），前端候选条点选 1 张定为演变款；单张回退直接进对比。

## 家规（AI 每次写代码都要守）

1. 每件事一个家：新逻辑先找现有家，找不到再建新的；不在路由里写 prompt，不在前端里拼 prompt。
2. sad path 用人话：面向用户的报错一律中文说清「哪里错了+怎么修」（参考 qwen_client._friendly_http_error 的做法）。
3. 后台任务一律走 `server.start_job()`，不手写线程样板；轮询一律走前端 `runJob()`。
4. 改完 `core/prompts/exporter/recognize/qwen_client` 任何共享逻辑 → 跑 `python -m unittest discover -s tests`。
5. 改 prompt 文案前先读 data/image_types.json 里有没有同义模板；改完在终端跑 `python scripts/prompts.py --type fabric` 目检输出。
