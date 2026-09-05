# 商品企划生成 Agent（本地 demo）

> 利丰 iBiR 商品企划 AI 岗面试作品。**选一张产品图 → 点选图类型轨道 → 生成变体选图 → 自动出「选品逻辑 + 编排」→ 导出 PPT/HTML。**

## 🚀 马上就能用

双击 **`启动demo.bat`** → 自动装依赖 → 自动开浏览器 `http://localhost:8000`。

> 或手动：`python server.py`

打开后，**最快演示路径**：点右上「🚀 载入示例（山羊绒围巾）」→ 4 类图秒载入 → 点「📦 导出企划」→ 页面内直接预览 + 下载 PPT/HTML。

> **v0.2（develop）**：导出从 1 页拼图升级为 **8 页企划 deck**（封面/企划方法/人群画像/逐款页[参数条+双价格+设计方向]/演变对比/AI出图体系/开发日历/尾页耗时），对齐 COLE HAAN FW26 真实企划结构，详见 `商品企划Agent-产品规格文档-v2.md` §8。

## 前端怎么「选图片」

| 区块 | 选图方式 |
|---|---|
| ① 起盘 · 选产品图 | 上传，或点缩略图从示例产品图里选 |
| ② 选参考图 | 点缩略图**多选**（Loro Piana 氛围大片 / 白底模特姿态），高亮即选中，生图时作风格参考 |
| ③ 图类型轨道 | 7 类节点，转换矩阵自动亮/灰，点节点进入配置 |
| ④ 配置 | 方向 / 品类 / 颜色 / 场景 / 零售商 / 数量，全程下拉点选 |
| ⑤ 结果区 | 生成的变体缩略图，**点选 1 张**纳入企划 |

## 产品流程（对齐 PRD §5 三阶段）

1. **起盘**：上传或选一张产品图（自动识别类型 / 可手改）。
2. **转换**：点图类型轨道节点 → 下拉向导 → Seedream 生成变体 → 点选 1 张。
3. **组装**：自动出 6 段选品逻辑 → 编排 → 导出 PPT + HTML。

## 生图说明

- 生图走**通义 qwen-image-3.0-pro**（图生图），API Key 从 `~/.claude/settings.json` 自动读取，无需手动配置。
- 约 20–60 秒/张（已关闭 `prompt_extend` 提速约 20 倍）。
- 生成图落盘 `images/output/`，导出落盘 `demo/output/`。

## 目录

| 路径 | 说明 |
|---|---|
| `server.py` | 后端（Flask，含生图/导出 API） |
| `static/` | 前端（index.html / style.css / app.js，选图片交互） |
| `启动demo.bat` | 双击启动脚本 |
| `data/directions.json` | 3 方向 × 4 品类库（中英双语） |
| `data/image_types.json` 等 | 图类型 prompt / 零售商风格 / 对标库 |
| `scripts/core.py` | 共享核心：路径 / API Key / 静态数据 / 图类型常量 / 参考图选取 |
| `scripts/prompts.py` | 唯一 prompt 组装入口（`build_prompt` / `build_selection_logic`） |
| `scripts/qwen_client.py` | 生图客户端（Seedream） |
| `scripts/exporter.py` | HTML/PPT 导出 |
| `app.py` | 备用 Streamlit 版前端（`streamlit run app.py`） |
| `商品企划Agent-产品规格文档.md` | 完整 PRD v1.1 |
