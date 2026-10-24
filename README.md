<div align="center">

<img src="frontend/public/favicon.svg" width="88" alt="Front" />

# Front

**自托管的全能创作素材库 · 角色百科 · AI 工作台**

画作、AI 出图、绘画素材、小说、galgame CG、世界观与角色关系网、SD 模型与提示词、AI 角色卡与对话，全部放进一个属于自己的数据库。

[![CI](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml/badge.svg)](https://github.com/Fiesty-Abyss/Front/actions/workflows/ci.yml)
![version](https://img.shields.io/badge/version-0.6.4-9a6ad0)
![license](https://img.shields.io/badge/license-MIT-f472b6)
![stack](https://img.shields.io/badge/FastAPI%20%2B%20SQLite%20%2B%20Vue%203-1f2340)

</div>

> Front 是一个长期持续开发的项目，当前为 **v0.6.4**（百科 Markdown 导出）。路线图见 [docs/ROADMAP.md](docs/ROADMAP.md)。

**v0.7 正在按阶段开发，尚无正式 Windows 安装/便携版。** 真实能力与缺口见 [第一阶段审计](docs/audits/v0.7/README.md)，交付门槛见 [开发计划](docs/V07_PLAN.md)，每轮进度见 [接续记录](docs/V07_PROGRESS.md)。请勿把测试截图、Mock 元数据或 PR 当成已发布的软件能力。

在**设置 → 数据导出**下载全部百科，或在世界观页点击**导出当前百科 · Markdown ZIP**。解压后打开 `README.md`，可沿相对链接阅读世界观、角色、地点、组织、事件、物品和概念，以及角色关系的方向与确认状态。只导出已保存的百科文字，正文中的站内链接和素材引用保留原样；不包含媒体、模型、笔记、角色卡、对话与 API Key，不能代替整库备份，也不能用于还原数据库。

## 能做什么

| 模块 | 说明 |
| --- | --- |
| 🎨 **全新界面（v0.6）** | 深靛夜色 + 单一雾紫强调色的统一设计系统，悬浮侧栏（可收起）、玻璃顶栏、画廊式素材网格、创作热力图总览；深色 / 浅色两套主题；GSAP 驱动的克制动效（页面对焦进入、列表依次显现、侧栏高亮块滑动），自动遵循系统“减少动态效果”。设计说明见 [docs/DESIGN.md](docs/DESIGN.md) |
| 📓 **超级笔记本（v0.6.1）** | 块编辑器写笔记：标题、待办、表格、引用、代码块（语法高亮）、高亮、图片；输入 `/` 唤出插入菜单，拖入 / 粘贴文件直接上传进素材库；**嵌入素材**与**链接到其他笔记**，自动列出“这页用到的素材”和**反向链接**；页面可以无限嵌套、拖成目录树，带图标、标签、置顶、关联作品；自动保存（`Ctrl/⌘ S` 立即保存），正文存为 Markdown，进入全文检索 |
| 🧭 **图表画布（v0.6.2）** | 像 Visio 一样画**流程图**（处理 / 开始结束 / 判断 / 输入输出 / 文档 / 数据 / 准备 / 连接点八种形状）、带输入输出端口的**节点工作流**、**思维导图**，还有便签和分组框；从左侧拖入或点击添加，双击改文字，拖动连接点连线，连线可加文字、换样式（折线 / 曲线 / 直线 / 直角）、颜色、虚线、箭头与流动动画；多选后对齐与等距分布，`Tab` 快速接一个新节点，复制粘贴、撤销重做、吸附网格、小地图；节点可以链接到素材、笔记或网址。自动保存在 Front 里，列表显示缩略图，可**导出 PNG / SVG / JSON**、导入 JSON，节点和连线上的文字进入全文检索。内置三个原创示例模板 |
| 🎮 **galgame 游戏库（v0.6.3）** | 从 **Bangumi / VNDB / 月幕 Galgame** 搜索并添加游戏：默认**混合模式**同时查询三个来源，选中一条后自动在其他来源里找到同一部作品并合并（中文名、原名、别名、品牌、发售日、平台、简介、标签、角色与声优、各来源评分 / 排名 / 时长），某个来源出错或没有结果时不影响其他来源；也可以只用一个来源并按顺序回退。记录**游玩状态**（未游玩 / 想玩 / 在玩 / 玩过 / 搁置 / 弃坑）、1–10 评分、开始 / 通关日期、游玩笔记，**手动记每一次游玩**（日期 + 时长 + 备注），有“继续游玩”横幅、游玩日历、近 8 周柱状图和时间线。改过的字段会被记住，刷新元数据时不覆盖。一键新建作品，**CG 档案**直接显示在游戏详情里；来源里的角色可导入角色百科。网格 / 列表视图、按状态 / 来源 / 品牌筛选、原名与别名可搜索、多选批量改状态或删除、随机挑一款、批量添加（逐个匹配或一键用第一条结果）、导出 JSON / CSV、R18 封面默认模糊、在本机生成**分享足迹**图片。只在你搜索 / 添加 / 刷新时联网，封面只在添加或点“保存封面”时下载 |
| 🧊 **多格式文件预览（v0.6.1）** | 上传或批量导入时自动识别格式并读出信息：**3D 模型** glb / gltf / vrm / obj / fbx / pmx / pmd（浏览器内 three.js 预览：旋转、线框、换背景、播放动画、把当前画面**设为封面**；VRM 读出作者与使用许可）、**Live2D**（Cubism 2–5 的 `model.json` / `model3.json`、moc / moc3 版本、贴图、动作、表情）、**音频**（标签、封面、内置播放器）、**视频**（时长、编码、自动截帧做封面，需要 ffmpeg）、**PDF**（逐页渲染）、**Word / Excel / PowerPoint / ODT / EPUB**（文字与表格预览）、**压缩包**（zip / tar 目录，7z / rar 识别）、**代码 / 脚本**（语法高亮，Ren'Py / KiriKiri 标签）。模型文件夹（Live2D、PMX + 贴图、glTF + bin、OBJ + MTL）**整包存为一个 zip**，预览时只读取包内文件，不解压到硬盘。详见 [docs/FILETYPES.md](docs/FILETYPES.md) |
| 🗂 **素材库** | 自己的画、AI 生成图、绘画素材、参考图、小说正文，以及 3D / Live2D 模型、音频、视频、文档、压缩包、代码。按类型分段筛选；按**日期（年/月）**、**类型**、**标签**、**作品**、**世界观**筛选；上传自动读取尺寸、生成缩略图、按 SHA256 去重 |
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
| ▤ **角色卡编辑器** | 在线编辑 AI 角色扮演角色卡，导入/导出 **SillyTavern / TavernAI Character Card V2**（JSON 与 PNG 卡，兼容导入 V1、V3），**内嵌世界书 `character_book` 一并导入导出**；可从百科角色一键生成 |
| ✉ **AI 对话** | **流式输出**（逐字显示，可随时停止）；**重新生成**与**分支**：每条回复可 ‹ 1/3 › 左右切换，修改自己的话可以直接改或另开分支，开场白与备选开场白也是可切换的分支；可编辑 / 删除消息、查看本次实际发给 AI 的上下文和命中的世界书条目 |
| ❧ **世界书 / Lorebook** | 兼容 SillyTavern 世界书与 Character Card V2 `character_book`：关键词（支持 `/正则/`）、次关键词（AND）、常驻、递归激活、扫描深度、token 预算、插入位置；**命中测试**输入一段话实时看哪些条目会被触发；可从世界观百科一键生成，导入 JSON / PNG 卡，导出 V2 或 SillyTavern 格式；对话时自动启用角色卡、所属世界观的世界书，也可按会话额外挂载 |
| ⌕ **从小说抽取角色** | 选素材库里的小说（或粘贴文本），按章节分段交给 AI，汇总出角色、别名、性别、简介、特征与角色关系；结果与已有角色自动对照，可在表格里逐条修改、勾选后写入角色百科，关系以“AI 待确认”写入关系网 |
| ≈ **语义检索** | 关键词 / 语义 / 混合（RRF 融合）三种检索方式，还能“找相似”；默认用离线的本地 n-gram 向量（无需任何服务，但只是近似），在设置里换成嵌入模型（如 Ollama `bge-m3`）才是真正的语义检索；后台增量建索引 |
| 🏷 **自动打标签（可选）** | 接 SD WebUI 的 WD14 Tagger 扩展或任意视觉模型识别图片，结果**按标签名和别名对到你已有的标签**（给标签加上 danbooru 风格的别名即可），单张点选加入，或后台批量给没有标签的图片打上高置信度标签 |
| ⚙ **设置页** | 在网页里管理多个 AI 服务（Ollama / LM Studio / OpenAI / DeepSeek / OpenRouter 预设，或任意 OpenAI 兼容接口），读取模型列表、测试连接；分别指定对话、嵌入、视觉用哪个服务。API Key 只存在本机数据库里，接口只返回打码后的提示 |
| 🌐 **浏览器查询** | 在角色、作品、SD 模型页面一键用 Bangumi、VNDB、月幕 Galgame、2DFan、萌娘百科、Civitai 等站点在新标签页里搜索；站点列表在设置里随意增删（名称 + 带 `{q}` 的搜索网址模板，也可以只放主页链接）。**只打开链接**：Front 不抓取这些网站，也不下载任何文件 |
| 🔍 **全文检索** | SQLite FTS5（trigram），中文/日文子串可搜：角色设定、世界观正文、小说、提示词、世界书条目全部即时可搜 |
| ⚙ **完整增删改查** | 所有数据都有 REST API（`/docs` 自带交互式文档），前端实时增删改查 |

## 界面截图

> 以下截图均为真实运行的 Front v0.6.3（无头浏览器截取）。截图里的内容是内置的 **【示例】数据**：雾港市、林汐、灯塔守望会、“灯塔历”时间线、“樱色回廊”“星之回响”等均为原创虚构，图片（包括 CG 与差分角标）是程序生成的几何占位图，模型条目和 ComfyUI 工作流只是演示字段，并非真实模型或真实出图。v0.6.1 的 3D 模型（灯塔、灯笼）、Live2D 结构演示包、音乐（五声音阶小曲）、视频、PDF 与 Office 文档全部是截图前由脚本**现场生成的原创文件**（生成方法与 [`backend/tests/samples.py`](backend/tests/samples.py) 相同，不含任何第三方模型、音乐或文档）；Live2D 演示包只有结构和贴图，不是可以运行的模型。v0.6.2 的图表（灯塔节剧情流程、AI 出图工作流、雾港世界观脑图）是内置的原创示例模板；“导出的 PNG”是在运行中的 Front 里点“导出 → PNG”得到的真实文件。v0.6.3 游戏库里的游戏（樱色回廊、雾港夜想曲、星屑邮局、夏日方程式、白夜图书馆、月下钟楼、海潮信号）、角色和声优都是虚构的【示例】数据，封面与角色图是程序生成的几何海报；元数据来自仓库自带的**模拟元数据接口**（`front_api.mock_galgame`，按 Bangumi / VNDB / 月幕的真实接口格式返回），走的是和真实来源完全相同的代码路径，截图时没有访问任何外部网站。出图相关截图连接的是仓库自带的**模拟 SD 后端**（`front_api.mock_sd`，图片角标“模拟出图”），走的是和真实 WebUI / ComfyUI 完全相同的代码路径，但画面只是占位图；扫描的模型目录是程序生成的假文件。AI 相关截图（对话、抽取角色、语义检索、自动打标签）连接的是仓库自带的**模拟 AI 服务**（`front_api.mock_ai`），回复以“【模拟回复】”开头、由模板拼出，**不是真实大模型的输出**，只用来演示界面和完整流程。

| **游戏库：继续游玩横幅、游玩日历、按状态筛选** | **列表视图** |
| --- | --- |
| ![游戏库](docs/screenshots/galgames.png) | ![列表视图](docs/screenshots/galgames-list.png) |
| **游戏详情：多来源评分、状态、评分、时长** | **游玩记录：手动记时长、近 8 周、时间线** |
| ![游戏详情](docs/screenshots/galgame-detail.png) | ![游玩记录](docs/screenshots/galgame-plays.png) |
| **添加游戏：三个来源同时搜索** | **预览混合补全：自动匹配其他来源** |
| ![添加游戏](docs/screenshots/galgame-add.png) | ![混合补全](docs/screenshots/galgame-preview.png) |
| **登场角色：导入角色百科** | **关联作品的 CG 档案** |
| ![角色](docs/screenshots/galgame-chars.png) | ![CG 档案](docs/screenshots/galgame-cg.png) |
| **元数据来源与手动修改过的字段** | **刚加入游戏库的条目** |
| ![元数据来源](docs/screenshots/galgame-meta.png) | ![新加入](docs/screenshots/galgame-added.png) |
| **批量添加：逐个匹配** | **多选：批量改状态 / 删除** |
| ![批量添加](docs/screenshots/galgame-batch.png) | ![多选](docs/screenshots/galgames-bulk.png) |
| **分享足迹（本机生成 PNG，可遮盖封面）** | **设置：来源模式与顺序** |
| ![分享足迹](docs/screenshots/galgame-share.png) | ![游戏库设置](docs/screenshots/galgame-settings.png) |
| **浅色主题 · 游戏详情** | **浅色主题 · 游戏库** |
| ![浅色详情](docs/screenshots/galgame-light.png) | ![浅色游戏库](docs/screenshots/galgames-light.png) |

| **图表画布 · 流程图（选中节点：形状、颜色、链接）** | **图表画布 · 选中连线：文字、样式、颜色、箭头** |
| --- | --- |
| ![流程图](docs/screenshots/diagram-flow.png) | ![连线属性](docs/screenshots/diagram-edge.png) |
| **节点工作流：输入 / 输出端口与参数** | **思维导图** |
| ![节点工作流](docs/screenshots/diagram-workflow.png) | ![思维导图](docs/screenshots/diagram-mind.png) |
| **多选对齐与快捷键** | **图表列表（自动缩略图）** |
| ![多选对齐](docs/screenshots/diagram-select.png) | ![图表列表](docs/screenshots/diagrams.png) |
| **从模板新建** | **浅色主题 · 图表画布** |
| ![新建图表](docs/screenshots/diagram-new.png) | ![浅色图表](docs/screenshots/diagram-light.png) |

**导出的 PNG（真实导出文件，2 倍分辨率）**

![导出的 PNG](docs/screenshots/diagram-export.png)

| **超级笔记本：块编辑、嵌入素材、待办** | **笔记本总览（目录树 + 置顶页面）** |
| --- | --- |
| ![笔记页](docs/screenshots/note-page.png) | ![笔记本](docs/screenshots/notes.png) |
| **`/` 插入菜单、站内链接** | **这页用到的素材 + 反向链接** |
| ![斜杠菜单](docs/screenshots/note-slash.png) | ![引用](docs/screenshots/note-refs.png) |
| **3D 预览 · glTF（可设为封面）** | **3D 预览 · VRM 元数据与使用许可** |
| ![glTF](docs/screenshots/preview-gltf.png) | ![VRM](docs/screenshots/preview-vrm.png) |
| **3D 预览 · PMX 模型包** | **3D 预览 · OBJ + MTL（浅色主题）** |
| ![PMX](docs/screenshots/preview-pmx.png) | ![OBJ](docs/screenshots/preview-light.png) |
| **Live2D：版本、贴图、动作、表情** | **音频：封面、标签、播放器** |
| ![Live2D](docs/screenshots/preview-live2d.png) | ![音频](docs/screenshots/preview-audio.png) |
| **视频：自动截帧封面** | **PDF 逐页预览** |
| ![视频](docs/screenshots/preview-video.png) | ![PDF](docs/screenshots/preview-pdf.png) |
| **Word 文档** | **Excel 表格** |
| ![Word](docs/screenshots/preview-docx.png) | ![Excel](docs/screenshots/preview-xlsx.png) |
| **PowerPoint 幻灯片** | **压缩包目录** |
| ![PPT](docs/screenshots/preview-pptx.png) | ![压缩包](docs/screenshots/preview-archive.png) |
| **Ren'Py 脚本（语法高亮 + 标签）** | **素材库 · 3D 分类（封面来自“设为封面”）** |
| ![代码](docs/screenshots/preview-code.png) | ![3D 分类](docs/screenshots/assets-3d.png) |
| **浅色主题 · 笔记本** | |
| ![浅色笔记本](docs/screenshots/note-light.png) | |

| 总览：问候、创作热力图、统计 | 素材库：画廊式网格 |
| --- | --- |
| ![总览](docs/screenshots/dashboard.png) | ![素材库](docs/screenshots/assets.png) |
| **浅色主题 · 总览** | **浅色主题 · 素材库** |
| ![浅色总览](docs/screenshots/dashboard-light.png) | ![浅色素材库](docs/screenshots/assets-light.png) |
| **浏览器查询（只打开链接）** | **设置：浏览器查询站点列表** |
| ![浏览器查询](docs/screenshots/quick-search.png) | ![站点设置](docs/screenshots/settings-quick-search.png) |
| **侧栏收起为图标栏** | |
| ![侧栏收起](docs/screenshots/sidebar-collapsed.png) | |
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
| **角色卡编辑器（含角色世界书）** | **AI 对话：分支切换 ‹ 2/2 ›、命中的世界书** |
| ![角色卡](docs/screenshots/cards.png) | ![AI 对话](docs/screenshots/chat.png) |
| **AI 对话：流式输出中（可停止）** | **AI 对话：查看实际发送的上下文** |
| ![流式输出](docs/screenshots/chat-streaming.png) | ![上下文](docs/screenshots/chat-context.png) |
| **世界书：条目编辑与命中测试** | **从小说抽取角色：与已有角色对照** |
| ![世界书](docs/screenshots/lorebooks.png) | ![抽取角色](docs/screenshots/extract.png) |
| **混合检索（关键词 + 语义）** | **设置：AI 服务、语义检索、自动打标签** |
| ![语义检索](docs/screenshots/search-semantic.png) | ![设置](docs/screenshots/settings.png) |
| **AI 识别标签：英文标签按别名对到已有标签** | **全文搜索（含百科条目）** |
| ![自动打标签](docs/screenshots/asset-autotag.png) | ![搜索](docs/screenshots/search.png) |
| **SD 模型库：哈希 / Civitai 标记 / 预览图** | |
| ![SD 模型库](docs/screenshots/models.png) | |
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
| `FRONT_AI_BASE_URL` | — | （也可以直接在网页“设置”里配置，设置页优先）OpenAI 兼容接口地址，例如 `https://api.deepseek.com/v1`、`http://127.0.0.1:11434/v1`（Ollama）、`http://127.0.0.1:1234/v1`（LM Studio） |
| `FRONT_AI_MODEL` | — | 模型名，例如 `deepseek-chat`、`qwen2.5:14b` |
| `FRONT_AI_API_KEY` | — | 需要鉴权时填写 |
| `FRONT_SD_WEBUI_URL` | — | SD WebUI / Forge 地址（启动时需加 `--api`），例如 `http://127.0.0.1:7860` |
| `FRONT_COMFYUI_URL` | — | ComfyUI 地址，例如 `http://127.0.0.1:8188` |
| `FRONT_SD_TIMEOUT` | `600` | 单张出图的超时秒数 |
| `FRONT_CIVITAI` | `on` | 设为 `off` 完全关闭 Civitai 查询（只有你点“匹配 Civitai”时才联网） |
| `FRONT_CIVITAI_API_KEY` | — | 可选，查询需要登录才能看的模型时使用 |
| `FRONT_GALGAME` | `on` | 设为 `off` 完全关闭游戏库的联网元数据（Bangumi / VNDB / 月幕），只能手动添加 |
| `FRONT_BANGUMI_API` / `FRONT_VNDB_API` / `FRONT_YMGAL_API` | 官方地址 | 元数据接口地址，一般不用改（测试与示例截图指向 `front_api.mock_galgame`） |
| `FRONT_YMGAL_CLIENT_ID` / `FRONT_YMGAL_CLIENT_SECRET` | 月幕公开的公共凭证 | 换成你向月幕申请的专属凭证 |

Windows PowerShell 示例：

```powershell
$env:FRONT_DATA_DIR = "D:\FrontData"
$env:FRONT_AI_BASE_URL = "http://127.0.0.1:11434/v1"
$env:FRONT_AI_MODEL = "qwen2.5:14b"
python -m front_api
```

AI 服务更推荐在网页左侧 **系统 › 设置** 里添加：选预设（Ollama、LM Studio、OpenAI、DeepSeek、OpenRouter）、填地址和 Key、点“读取模型列表”“测试连接”，再分别选对话、嵌入、视觉用哪个服务。设置页里的配置优先于环境变量。

未配置 AI 时，其余功能完全可用；AI 对话、抽取角色与关系识别会提示如何配置，语义检索自动使用离线的本地向量。未配置 SD 后端时，出图页会显示如何配置，其余功能不受影响。

### 没有显卡也想试试出图流程

仓库带了一个**模拟 SD 后端**，实现了 WebUI 与 ComfyUI 出图用到的那部分接口，返回带“模拟出图”角标的占位图（不是真实 AI 出图），方便体验出图、入库、XY 网格整条流程：

```bash
python -m front_api.mock_sd --port 7861
# 另开一个终端
FRONT_SD_WEBUI_URL=http://127.0.0.1:7861 FRONT_COMFYUI_URL=http://127.0.0.1:7861 python -m front_api
```

### 没有大模型也想试试 AI 流程

同样有一个**模拟 AI 服务**（OpenAI 兼容：`/v1/models`、`/v1/chat/completions`（含流式）、`/v1/embeddings`，以及视觉识别），回复以“【模拟回复】”开头、由模板拼出，抽取角色用的是简单的规则，**不是真实大模型**，只用于体验界面和完整流程：

```bash
python -m front_api.mock_ai --port 7862
```

然后在 设置 › 添加服务 › 自定义，地址填 `http://127.0.0.1:7862/v1`，模型填 `mock-chat`（嵌入 `mock-embed`、视觉 `mock-vision`）。示例数据里已经带了这条配置，只需在“对话 · 抽取角色”里选中它。

### 不联网也想试试游戏库

**模拟元数据接口**按 Bangumi、VNDB、月幕的接口格式返回几部虚构的【示例】游戏：

```bash
python -m front_api.mock_galgame --port 7863
FRONT_BANGUMI_API=http://127.0.0.1:7863/bangumi FRONT_VNDB_API=http://127.0.0.1:7863/vndb FRONT_YMGAL_API=http://127.0.0.1:7863/ymgal python -m front_api
```

## 升级

直接 `git pull`，重新 `pip install -e "backend[dev]"`、`npm run build` 后启动即可。数据库会在启动时自动补齐新版本增加的字段，已有数据不受影响（升级前建议备份数据目录）。

## 数据安全

- 批量导入会把文件**复制**进数据目录，原文件不会被修改、移动或删除；不能从 Front 自己的数据目录导入。
- Front 默认只监听 `127.0.0.1`。批量导入、模型目录扫描与模型信息读取会访问本机路径，请不要把服务直接暴露到公网。
- 数据库、图片、小说、CG 都在 `FRONT_DATA_DIR` 里，不在仓库目录中。
- SD 模型只登记路径、哈希与元数据，模型文件本身不会被复制或上传；扫描时不能选 Front 自己的数据目录。
- AI 服务的 API Key 只保存在本机数据目录的数据库里（明文，与其余数据同等对待），接口永远只返回 `sk-…abcd` 这样的打码提示；对话、抽取角色、打标签只会把内容发给**你自己配置的** AI 服务。
- 浏览器查询只是在新标签页打开你配置的网址（关键词经过 URL 编码），Front 不会访问、抓取这些站点，也不会下载其中的任何文件；站点列表只允许 `http(s)://` 网址。
- Civitai 只在你手动点“匹配 Civitai”时访问 `civitai.com`，只发送模型哈希；预览图只从 Civitai 官方图床下载。`FRONT_CIVITAI=off` 可彻底关闭。
- `.gitignore` 屏蔽了 `*.safetensors`、`*.ckpt`、`*.db`、压缩包、绘画工程文件等；测试 [`test_repo_guard.py`](backend/tests/test_repo_guard.py) 会在 CI 中检查，任何模型、数据库或 `docs/screenshots/` 以外的图片被提交都会直接失败。
- 游戏库只在你搜索、添加、刷新时访问 Bangumi（`api.bgm.tv`）、VNDB（`api.vndb.org`）、月幕（`www.ymgal.games`），发送的只有游戏名或条目 id；封面只从这三家的图床下载，并且只在添加时勾选“保存封面”或手动点“保存封面”时才下载。Bangumi 令牌（可选）只保存在本机数据库，接口不会返回它。`FRONT_GALGAME=off` 可彻底关闭。Front 不提供任何游戏下载。
- Front 是**个人自托管**工具。你收藏的他人作品（游戏 CG、插画等）版权归原作者所有，请只用于个人收藏与学习，不要通过 Front 再分发。本仓库不包含任何第三方受版权保护的素材。

## 文档

- [设计与动效](docs/DESIGN.md)：设计令牌、克制原则、动效清单
- [支持的文件格式](docs/FILETYPES.md)：每种格式读出哪些信息、怎样预览、有哪些限制
- [架构说明](docs/ARCHITECTURE.md)：技术栈、数据模型、API 一览、AI 接口层、世界书匹配规则
- [路线图](docs/ROADMAP.md)：后续每一轮的开发计划
- [更新日志](CHANGELOG.md)

## 致谢与参考

- 界面观感参考了 [Nephele Workshop](https://nephele.arisfusion.com/) 官网展示的设计风格（只参考风格与布局思路，未使用其代码、图片或品牌素材）。
- 设计与动效原则参考：[apple-design-skills](https://github.com/s1gmamale1/apple-design-skills)（MIT）、[gsap-skills](https://github.com/greensock/gsap-skills)（MIT）、[design-motion-principles](https://github.com/kylezantos/design-motion-principles)（MIT）、[awesome-ai-motion](https://github.com/guanmo-ai/awesome-ai-motion)（MIT，仅学习案例思路）。具体取舍见 [docs/DESIGN.md](docs/DESIGN.md)。
- 动效库 [GSAP](https://gsap.com)（GreenSock 标准免费许可 “Standard no-charge license”），图标 [Lucide](https://lucide.dev)（ISC）。
- 图表画布 [Vue Flow](https://vueflow.dev)（MIT），导出图片 [html-to-image](https://github.com/bubkoo/html-to-image)（MIT）。
- 笔记本编辑器 [Tiptap](https://tiptap.dev)（MIT）与 [tiptap-markdown](https://github.com/aguingand/tiptap-markdown)（MIT），代码高亮 [highlight.js](https://highlightjs.org)（BSD-3-Clause）。
- 3D 预览 [three.js](https://threejs.org)（MIT）与 [@pixiv/three-vrm](https://github.com/pixiv/three-vrm)（MIT）；PMX / PMD 读取按公开的格式说明自行实现（只读静态网格与材质）。
- 音频标签 [tinytag](https://github.com/tinytag/tinytag)（MIT），PDF 渲染 [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)（Apache-2.0 / BSD-3-Clause，内含 PDFium，BSD-3-Clause）；视频信息与截帧调用本机的 [FFmpeg](https://ffmpeg.org)（可选，不随 Front 分发）。
- galgame 游戏库的设计参考了 [ReinaManager](https://github.com/huoshen80/ReinaManager)（AGPL-3.0）与 [恋页 KoiPage](https://github.com/morilove37/koipage)（作者 [@morilove37](https://github.com/morilove37)，仓库未指定开源许可证）：多来源元数据、用户修改优先、状态筛选、批量添加、继续游玩横幅、游玩时长日历与时间线、分享足迹等**功能思路**。Front 只参考了它们公开的功能与界面思路，**没有使用两者的任何代码、图片或素材**，界面与实现均为独立编写。
- 元数据来自 [Bangumi 番组计划](https://bgm.tv)（[API](https://github.com/bangumi/api)）、[VNDB](https://vndb.org)（[Kana API](https://api.vndb.org/kana)，数据按 [VNDB 数据许可](https://vndb.org/d17) 使用，非商业）与 [月幕 Galgame](https://www.ymgal.games)（[开放 API](https://www.ymgal.games/developer)，使用其公开的公共客户端凭证，非商业）。资料与封面归各自权利人所有；Front 与这些网站没有合作关系。
- Live2D：只按公开的 `model3.json` / `model.json` 结构读取信息与贴图，**不包含也不调用** Live2D Cubism Core（专有许可），因此不做实时渲染。

## 技术栈

FastAPI · SQLAlchemy 2 · SQLite（FTS5 trigram）· Pillow · httpx ｜ Vue 3 · Vite · Vue Router · GSAP · Lucide · Cytoscape.js · markdown-it · Tiptap · three.js · highlight.js · Vue Flow ｜ tinytag · pypdfium2 · FFmpeg（可选）

## 许可证

[MIT](LICENSE) © Fiesty-Abyss
