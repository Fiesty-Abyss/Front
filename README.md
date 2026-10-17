<div align="center">

<img src="frontend/public/favicon.svg" width="88" alt="Front" />

# Front

**自托管的全能创作素材库 · 角色百科 · AI 工作台**

画作、AI 出图、绘画素材、小说、galgame CG、世界观与角色关系网、SD 模型与提示词、AI 角色卡与对话，全部放进一个属于自己的数据库。

[![CI](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml/badge.svg)](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-0.2.0-8b7cf6)
![license](https://img.shields.io/badge/license-MIT-f472b6)
![stack](https://img.shields.io/badge/FastAPI%20%2B%20SQLite%20%2B%20Vue%203-1f2340)

</div>

> Front 是一个长期持续开发的项目，当前为 **v0.2.0**（第二轮）。路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 能做什么

| 模块 | 说明 |
| --- | --- |
| 🗂 **素材库** | 自己的画、AI 生成图、绘画素材、参考图、小说正文。按**日期（年/月）**、**类型**、**标签**、**作品**、**世界观**筛选；上传自动读取尺寸、生成缩略图、按 SHA256 去重 |
| ⇪ **批量导入** | 输入本机文件夹路径（或在浏览器里选择文件夹），扫描预览后一键导入；可递归子文件夹、用文件修改时间作为日期、统一打标签；同内容文件自动跳过 |
| ✦ **AI 出图参数识别** | 自动识别 **SD WebUI / Forge** 的 `parameters` 与 **ComfyUI** 的 `prompt` / `workflow`：沿节点连线找出正/反向提示词，提取采样器、步数、CFG、种子、尺寸、Checkpoint、LoRA；可下载原始工作流拖回 ComfyUI，一键存入提示词库 |
| 📖 **角色百科** | 角色条目 + 分面标签：性别（男/女）、媒介（动漫/游戏）、来源作品、画风、类型……多个标签取交集，像百科一样检索 |
| 🌏 **世界观** | Markdown 设定正文，挂接角色与素材 |
| ⟡ **关系网** | 可视化角色关系图，点两个角色即可连线；AI 识别出的关系以虚线显示，人工确认后转为正式关系 |
| 🎮 **galgame CG 档案** | CG 模式导入时自动识别**差分**（`ev01a/ev01b`、`ev03_01/ev03_02`、`ev0401/ev0402`、`ev04_diff2`……，并要求分辨率一致），按作品归档；**鉴赏模式**全屏浏览：← → 切换 CG、↑ ↓ 切换差分、自动播放 |
| ❒ **收藏集** | 拖拽排序、自定义封面（默认第一项）、收藏集之间也可拖拽排序，可关联作品 |
| 📖 **小说阅读** | 自动拆分章节（第X章 / Chapter N / Markdown 标题 / 序章 尾声…），字数统计，阅读模式支持目录、翻章、字号、行距、四种主题，进度自动记住 |
| ✎ **提示词库** | 正向/反向提示词、参数 JSON、标签；**同一提示词 × 不同模型**并排风格对比——从 AI 图存入时，提示词相同会自动归到同一组对比，并按模型名匹配已登记的模型 |
| ⬡ **SD 模型库** | 登记 Checkpoint / LoRA / VAE / Embedding……读取本地 `.safetensors` 元数据、自动判断底模、计算 SHA256。**模型文件留在你的硬盘上，不复制、不上传** |
| ▤ **角色卡编辑器** | 在线编辑 AI 角色扮演角色卡，导入/导出 **SillyTavern / TavernAI Character Card V2**（JSON 与 PNG 卡，兼容导入 V1、V3）；可从百科角色一键生成 |
| ✉ **AI 对话** | 用角色卡进行带上下文的角色扮演对话，会话持久保存；接入任意 OpenAI 兼容接口 |
| 🔍 **全文检索** | SQLite FTS5（trigram），中文/日文子串可搜：角色设定、世界观正文、小说、提示词全部即时可搜 |
| ⚙ **完整增删改查** | 所有数据都有 REST API（`/docs` 自带交互式文档），前端实时增删改查 |

## 界面截图

> 以下截图均为真实运行的 Front v0.2.0（无头浏览器截取）。截图里的内容是内置的 **【示例】数据**：雾港市、林汐、“樱色回廊”“星之回响”等均为原创虚构，图片（包括 CG 与差分角标）是程序生成的几何占位图，模型条目和 ComfyUI 工作流只是演示字段，并非真实模型或真实出图。

| 总览 | 素材库 |
| --- | --- |
| ![总览](docs/screenshots/dashboard.png) | ![素材库](docs/screenshots/assets.png) |
| **角色百科（分面标签筛选）** | **角色详情 / 关系编辑** |
| ![角色百科](docs/screenshots/characters.png) | ![角色详情](docs/screenshots/character-detail.png) |
| **角色关系网** | **世界观** |
| ![关系网](docs/screenshots/graph.png) | ![世界观](docs/screenshots/worlds.png) |
| **批量导入 · CG 模式扫描预览（差分分组）** | **galgame CG 档案（按差分分组）** |
| ![批量导入](docs/screenshots/import-preview.png) | ![CG 档案](docs/screenshots/works-cg.png) |
| **CG 鉴赏模式（差分 2 / 3）** | **收藏集：拖拽排序与封面** |
| ![鉴赏模式](docs/screenshots/cg-viewer.png) | ![收藏集](docs/screenshots/collections.png) |
| **小说阅读模式（夜间）** | **小说阅读模式（羊皮纸）** |
| ![阅读模式](docs/screenshots/reader.png) | ![阅读模式 羊皮纸](docs/screenshots/reader-paper.png) |
| **ComfyUI 工作流解析（含 LoRA）** | **SD WebUI 出图参数** |
| ![ComfyUI](docs/screenshots/asset-comfyui.png) | ![出图参数](docs/screenshots/asset-ai-params.png) |
| **SD 模型库** | **角色卡编辑器** |
| ![SD 模型库](docs/screenshots/models.png) | ![角色卡](docs/screenshots/cards.png) |
| **AI 对话（未配置 AI 时的提示）** | **全文搜索** |
| ![AI 对话](docs/screenshots/chat.png) | ![搜索](docs/screenshots/search.png) |

**提示词库：同一提示词 × 不同模型的风格对比**

![提示词对比](docs/screenshots/prompts-compare.png)

## 快速开始

需要 **Python 3.10+** 和 **Node.js 18+**。

```bash
git clone https://github.com/Fiesty-Abyss/Front.git
cd Front

# 1. 后端
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e "backend[dev]"

# 2. 前端（构建一次即可，之后由后端直接托管）
cd frontend && npm install && npm run build && cd ..

# 3. （可选）写入一套示例数据体验各个页面
python -m front_api.seed

# 4. 启动
python -m front_api            # 打开 http://127.0.0.1:8000
```

API 交互式文档：<http://127.0.0.1:8000/docs>

开发前端时可以 `cd frontend && npm run dev`（Vite 热更新，`/api` 自动代理到 8000 端口）。

## 配置

全部通过环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `FRONT_DATA_DIR` | `~/.front-data` | 数据目录：数据库 `front.db`、上传文件 `media/`、缩略图 `thumbs/`。**在仓库之外**，备份这一个文件夹即可 |
| `FRONT_MAX_UPLOAD_MB` | `200` | 单个文件上传 / 导入上限 |
| `FRONT_AI_BASE_URL` | — | OpenAI 兼容接口地址，例如 `https://api.deepseek.com/v1`、`http://127.0.0.1:11434/v1`（Ollama）、`http://127.0.0.1:1234/v1`（LM Studio） |
| `FRONT_AI_MODEL` | — | 模型名，例如 `deepseek-chat`、`qwen2.5:14b` |
| `FRONT_AI_API_KEY` | — | 需要鉴权时填写 |

Windows PowerShell 示例：

```powershell
$env:FRONT_DATA_DIR = "D:\FrontData"
$env:FRONT_AI_BASE_URL = "http://127.0.0.1:11434/v1"
$env:FRONT_AI_MODEL = "qwen2.5:14b"
python -m front_api
```

未配置 AI 时，其余功能完全可用；AI 对话与关系识别会提示如何配置。

## 升级

直接 `git pull`，重新 `pip install -e "backend[dev]"`、`npm run build` 后启动即可。数据库会在启动时自动补齐新版本增加的字段，已有数据不受影响（升级前建议备份数据目录）。

## 数据安全

- 批量导入会把文件**复制**进数据目录，原文件不会被修改、移动或删除；不能从 Front 自己的数据目录导入。
- Front 默认只监听 `127.0.0.1`。批量导入与模型信息读取会访问本机路径，请不要把服务直接暴露到公网。
- 数据库、图片、小说、CG 都在 `FRONT_DATA_DIR` 里，不在仓库目录中。
- SD 模型只登记路径与元数据，模型文件本身不会被复制或上传。
- `.gitignore` 屏蔽了 `*.safetensors`、`*.ckpt`、`*.db`、压缩包、绘画工程文件等；测试 [`test_repo_guard.py`](backend/tests/test_repo_guard.py) 会在 CI 中检查，任何模型、数据库或 `docs/screenshots/` 以外的图片被提交都会直接失败。
- Front 是**个人自托管**工具。你收藏的他人作品（游戏 CG、插画等）版权归原作者所有，请只用于个人收藏与学习，不要通过 Front 再分发。本仓库不包含任何第三方受版权保护的素材。

## 文档

- [架构说明](docs/ARCHITECTURE.md)：技术栈、数据模型、API 一览、AI 接口层
- [路线图](docs/ROADMAP.md)：后续每一轮的开发计划
- [更新日志](CHANGELOG.md)

## 技术栈

FastAPI · SQLAlchemy 2 · SQLite（FTS5 trigram）· Pillow · httpx ｜ Vue 3 · Vite · Vue Router · Cytoscape.js

## 许可证

[MIT](LICENSE) © Fiesty-Abyss
