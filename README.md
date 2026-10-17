<div align="center">

<img src="frontend/public/favicon.svg" width="88" alt="Front" />

# Front

**自托管的全能创作素材库 · 角色百科 · AI 工作台**

画作、AI 出图、绘画素材、小说、galgame CG、世界观与角色关系网、SD 模型与提示词、AI 角色卡与对话，全部放进一个属于自己的数据库。

[![CI](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml/badge.svg)](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-0.4.0-8b7cf6)
![license](https://img.shields.io/badge/license-MIT-f472b6)
![stack](https://img.shields.io/badge/FastAPI%20%2B%20SQLite%20%2B%20Vue%203-1f2340)

</div>

> Front 是一个长期持续开发的项目，当前为 **v0.4.0**（第四轮）。路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 能做什么

| 模块 | 说明 |
| --- | --- |
| 🗂 **素材库** | 自己的画、AI 生成图、绘画素材、参考图、小说正文。按**日期（年/月）**、**类型**、**标签**、**作品**、**世界观**筛选；上传自动读取尺寸、生成缩略图、按 SHA256 去重 |
| ⇪ **批量导入** | 输入本机文件夹路径（或在浏览器里选择文件夹），扫描预览后一键导入；可递归子文件夹、用文件修改时间作为日期、统一打标签；同内容文件自动跳过 |
| ✦ **AI 出图参数识别** | 自动识别 **SD WebUI / Forge** 的 `parameters` 与 **ComfyUI** 的 `prompt` / `workflow`：沿节点连线找出正/反向提示词，提取采样器、步数、CFG、种子、尺寸、Checkpoint、LoRA；可下载原始工作流拖回 ComfyUI，一键存入提示词库 |
| 📖 **角色百科** | 角色条目 + 分面标签：性别（男/女）、媒介（动漫/游戏）、来源作品、画风、类型……多个标签取交集，像百科一样检索 |
| ☺ **角色详情页** | Markdown 设定（表格、引用、`[[名称]]` 站内链接），编辑时实时预览；**图集**（从素材库挑图、设为头像、大图浏览）；**出场作品**（来源作品 + 客串 / 联动登记）；关系列表；所属组织、参与事件、相关地点 |
| 🌏 **世界观百科** | 设定正文之外，世界观下可建 **地点**（层级：城市 › 街区 › 建筑）、**组织**（成员与职务）、**事件**（时间、发生地点、参与角色）、**物品 / 概念** 条目，正文都支持 Markdown；事件自动排成**时间线** |
| ◈ **关系网** | 可视化角色关系图，点两个角色即可连线；**按关系类型着色**（颜色可改、自动保存）、点击类型筛选、隐藏 AI 待确认；**保存布局**（拖好的位置下次照样显示）；**导出 PNG / JSON**。AI 识别出的关系以虚线显示，人工确认后转为正式关系 |
| # **标签管理** | **层级标签**（如「游戏 › Galgame」，按上级筛选时自动包含子标签）、**别名**（搜「gal」也能找到 Galgame）、颜色、使用次数统计（**上级标签的次数包含所有子标签**，同一条目只算一次），重复标签一键**合并**（原名自动变成别名） |
| 🎮 **galgame CG 档案** | CG 模式导入时自动识别**差分**（`ev01a/ev01b`、`ev03_01/ev03_02`、`ev0401/ev0402`、`ev04_diff2`……，并要求分辨率一致），按作品归档；**鉴赏模式**全屏浏览：← → 切换 CG、↑ ↓ 切换差分、自动播放 |
| ❒ **收藏集** | 拖拽排序、自定义封面（默认第一项）、收藏集之间也可拖拽排序，可关联作品 |
| 📖 **小说阅读** | 自动拆分章节（第X章 / Chapter N / Markdown 标题 / 序章 尾声…），字数统计，阅读模式支持目录、翻章、字号、行距、四种主题，进度自动记住 |
| ✦ **出图** | 直接调用本机 **SD WebUI / Forge**（`/sdapi/v1/txt2img`）或 **ComfyUI**（`/prompt`，内置文生图模板，也可粘贴自己的 API 格式工作流并用 `{{prompt}}` `{{seed}}` 等占位符）出图；可多选模型、叠加 LoRA 与权重；**出的图自动存进素材库**（PNG 内嵌完整参数，打标签、放进收藏集），提示词自动进提示词库；后台任务带进度条，可取消 |
| ▦ **XY 网格** | 出图时选 X / Y 轴（模型、CFG、步数、采样器、调度器、种子、尺寸、Clip skip、提示词替换 S/R、LoRA 权重），一次最多 100 张，结果在提示词库里按网格排好；也能对任意已有图按两个参数自由排网格 |
| ✎ **提示词库** | 正向/反向提示词、参数 JSON、标签；**同一提示词 × 不同模型**并排风格对比，**不同的参数高亮**，还有逐张的**参数差异表**和与基准提示词相比**增 / 删的词**；从 AI 图存入时，提示词相同会自动归到同一组，并按模型名或模型哈希（AutoV1 / AutoV2）匹配已登记的模型 |
| ❏ **提示词片段** | 按质量 / 画风 / 角色 / 服装 / 动作 / 构图 / 背景 / 光影 / 负面分类收藏常用片段；**组合器**里点选拼接、调权重 `(片段:1.2)`、调顺序、自动去重，可存为提示词或一键带去出图 |
| ⬡ **SD 模型库** | **扫描模型目录**（WebUI / Forge / ComfyUI 的 `models` 文件夹，按子文件夹判断类型），预览后批量登记；计算 **SHA256 / AutoV1 / AutoV2 / AutoV3**（后台任务）、读取 `.safetensors` 元数据判断底模、导入同名预览图、读取 `.civitai.info` / `.json` 说明；**可选 Civitai 匹配**：按哈希查出模型名、版本、触发词、底模与预览图。**模型文件留在你的硬盘上，不复制、不上传** |
| ▤ **角色卡编辑器** | 在线编辑 AI 角色扮演角色卡，导入/导出 **SillyTavern / TavernAI Character Card V2**（JSON 与 PNG 卡，兼容导入 V1、V3）；可从百科角色一键生成 |
| ✉ **AI 对话** | 用角色卡进行带上下文的角色扮演对话，会话持久保存；接入任意 OpenAI 兼容接口 |
| 🔍 **全文检索** | SQLite FTS5（trigram），中文/日文子串可搜：角色设定、世界观正文、小说、提示词全部即时可搜 |
| ⚙ **完整增删改查** | 所有数据都有 REST API（`/docs` 自带交互式文档），前端实时增删改查 |

## 界面截图

> 以下截图均为真实运行的 Front v0.4.0（无头浏览器截取）。截图里的内容是内置的 **【示例】数据**：雾港市、林汐、灯塔守望会、“灯塔历”时间线、“樱色回廊”“星之回响”等均为原创虚构，图片（包括 CG 与差分角标）是程序生成的几何占位图，模型条目和 ComfyUI 工作流只是演示字段，并非真实模型或真实出图。出图相关截图连接的是仓库自带的**模拟 SD 后端**（`front_api.mock_sd`，图片角标“模拟出图”），走的是和真实 WebUI / ComfyUI 完全相同的代码路径，但画面只是占位图；扫描的模型目录是程序生成的假文件。

| 总览 | 素材库 |
| --- | --- |
| ![总览](docs/screenshots/dashboard.png) | ![素材库](docs/screenshots/assets.png) |
| **角色百科（分面标签筛选）** | **角色详情页：Markdown 设定 / 关系 / 出场作品** |
| ![角色百科](docs/screenshots/characters.png) | ![角色详情](docs/screenshots/character-detail.png) |
| **角色详情页：图集 / 参与事件 / 所属组织** | **编辑角色：Markdown 实时预览** |
| ![角色图集](docs/screenshots/character-gallery.png) | ![编辑角色](docs/screenshots/character-edit.png) |
| **世界观 · 地点（层级）** | **世界观 · 组织** |
| ![地点](docs/screenshots/world-locations.png) | ![组织](docs/screenshots/world-organizations.png) |
| **世界观 · 时间线** | **编辑事件：时间、地点、参与角色** |
| ![时间线](docs/screenshots/world-timeline.png) | ![编辑事件](docs/screenshots/world-entry-edit.png) |
| **关系网：按类型着色** | **关系网：按类型筛选（隐藏了两类）** |
| ![关系网](docs/screenshots/graph.png) | ![关系网筛选](docs/screenshots/graph-filter.png) |
| **标签：层级 / 别名 / 使用次数** | **编辑标签：上级、别名、合并** |
| ![标签](docs/screenshots/tags.png) | ![编辑标签](docs/screenshots/tag-edit.png) |
| **世界观设定** | **作品：登场角色 + galgame CG 档案** |
| ![世界观](docs/screenshots/worlds.png) | ![CG 档案](docs/screenshots/works-cg.png) |
| **批量导入 · CG 模式扫描预览（差分分组）** | **CG 鉴赏模式（差分 2 / 3）** |
| ![批量导入](docs/screenshots/import-preview.png) | ![鉴赏模式](docs/screenshots/cg-viewer.png) |
| **收藏集：拖拽排序与封面** | **小说阅读模式（夜间）** |
| ![收藏集](docs/screenshots/collections.png) | ![阅读模式](docs/screenshots/reader.png) |
| **小说阅读模式（羊皮纸）** | **ComfyUI 工作流解析（含 LoRA）** |
| ![阅读模式 羊皮纸](docs/screenshots/reader-paper.png) | ![ComfyUI](docs/screenshots/asset-comfyui.png) |
| **SD WebUI 出图参数** | **提示词替换 XY：night / dawn / sunset** |
| ![出图参数](docs/screenshots/asset-ai-params.png) | ![提示词替换](docs/screenshots/prompts-xy-sr.png) |
| **角色卡编辑器** | **AI 对话（未配置 AI 时的提示）** |
| ![角色卡](docs/screenshots/cards.png) | ![AI 对话](docs/screenshots/chat.png) |
| **全文搜索（含百科条目）** | **SD 模型库：哈希 / Civitai 标记 / 预览图** |
| ![搜索](docs/screenshots/search.png) | ![SD 模型库](docs/screenshots/models.png) |
| **扫描模型目录：预览后批量登记** | **模型详情：哈希与 Civitai 信息** |
| ![扫描模型目录](docs/screenshots/models-scan.png) | ![模型详情](docs/screenshots/model-detail.png) |
| **提示词片段与组合器** | **出图：多模型 × 采样器 XY，自动入库** |
| ![提示词片段](docs/screenshots/snippets.png) | ![出图](docs/screenshots/generate.png) |

**提示词库：XY 网格（模型 × CFG）**

![XY 网格](docs/screenshots/prompts-xy.png)

**提示词库：同一提示词 × 不同模型，差异参数高亮**

![提示词对比](docs/screenshots/prompts-compare.png)

**提示词库：参数差异表（高亮与多数不同的取值，+/− 为提示词增删）**

![参数差异表](docs/screenshots/prompts-diff.png)

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
| `FRONT_SD_WEBUI_URL` | — | SD WebUI / Forge 地址（启动时需加 `--api`），例如 `http://127.0.0.1:7860` |
| `FRONT_COMFYUI_URL` | — | ComfyUI 地址，例如 `http://127.0.0.1:8188` |
| `FRONT_SD_TIMEOUT` | `600` | 单张出图的超时秒数 |
| `FRONT_CIVITAI` | `on` | 设为 `off` 完全关闭 Civitai 查询（只有你点“匹配 Civitai”时才联网） |
| `FRONT_CIVITAI_API_KEY` | — | 可选，查询需要登录才能看的模型时使用 |

Windows PowerShell 示例：

```powershell
$env:FRONT_DATA_DIR = "D:\FrontData"
$env:FRONT_AI_BASE_URL = "http://127.0.0.1:11434/v1"
$env:FRONT_AI_MODEL = "qwen2.5:14b"
python -m front_api
```

未配置 AI 时，其余功能完全可用；AI 对话与关系识别会提示如何配置。未配置 SD 后端时，出图页会显示如何配置，其余功能不受影响。

### 没有显卡也想试试出图流程

仓库带了一个**模拟 SD 后端**，实现了 WebUI 与 ComfyUI 出图用到的那部分接口，返回带“模拟出图”角标的占位图（不是真实 AI 出图），方便体验出图、入库、XY 网格整条流程：

```bash
python -m front_api.mock_sd --port 7861
# 另开一个终端
FRONT_SD_WEBUI_URL=http://127.0.0.1:7861 FRONT_COMFYUI_URL=http://127.0.0.1:7861 python -m front_api
```

## 升级

直接 `git pull`，重新 `pip install -e "backend[dev]"`、`npm run build` 后启动即可。数据库会在启动时自动补齐新版本增加的字段，已有数据不受影响（升级前建议备份数据目录）。

## 数据安全

- 批量导入会把文件**复制**进数据目录，原文件不会被修改、移动或删除；不能从 Front 自己的数据目录导入。
- Front 默认只监听 `127.0.0.1`。批量导入、模型目录扫描与模型信息读取会访问本机路径，请不要把服务直接暴露到公网。
- 数据库、图片、小说、CG 都在 `FRONT_DATA_DIR` 里，不在仓库目录中。
- SD 模型只登记路径、哈希与元数据，模型文件本身不会被复制或上传；扫描时不能选 Front 自己的数据目录。
- Civitai 只在你手动点“匹配 Civitai”时访问 `civitai.com`，只发送模型哈希；预览图只从 Civitai 官方图床下载。`FRONT_CIVITAI=off` 可彻底关闭。
- `.gitignore` 屏蔽了 `*.safetensors`、`*.ckpt`、`*.db`、压缩包、绘画工程文件等；测试 [`test_repo_guard.py`](backend/tests/test_repo_guard.py) 会在 CI 中检查，任何模型、数据库或 `docs/screenshots/` 以外的图片被提交都会直接失败。
- Front 是**个人自托管**工具。你收藏的他人作品（游戏 CG、插画等）版权归原作者所有，请只用于个人收藏与学习，不要通过 Front 再分发。本仓库不包含任何第三方受版权保护的素材。

## 文档

- [架构说明](docs/ARCHITECTURE.md)：技术栈、数据模型、API 一览、AI 接口层
- [路线图](docs/ROADMAP.md)：后续每一轮的开发计划
- [更新日志](CHANGELOG.md)

## 技术栈

FastAPI · SQLAlchemy 2 · SQLite（FTS5 trigram）· Pillow · httpx ｜ Vue 3 · Vite · Vue Router · Cytoscape.js · markdown-it

## 许可证

[MIT](LICENSE) © Fiesty-Abyss
