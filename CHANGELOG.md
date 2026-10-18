# 更新日志

## 创作迭代 · 项目预览 PR 2a · 2026-10-18

- 新增按需加载的项目只读预览：候选分类/理由、文件元数据、内容重复报告、增量哈希缓存、分页、文本片段与单张图片预览。
- 参考世界观按ID区分；其他世界观重复仅报告，不自动合并或关联。原件变化/移动后要求重新扫描，脚本不执行。
- 用户真实34文件只读验证，未创建正式世界观或素材；公开验收仅生成样本。原地索引、托管导入与内部标签仍待，见 `docs/PROJECT_PREVIEW.md`。

## 创作迭代 · 章节整理 · 2026-10-18

- 在现有阅读/分章功能上增加确认目录、手动拆并与边界/顺序调整，不修改原文；目录历史只追加，恢复创建新版本，正文变化时拒绝过期保存。
- 长文本与 EPUB 按需读取有界全文，补 UTF-16 BOM、围栏代码、严格 EPUB spine 等处理。真实资料只读扫描与生成样本验证分开记录，见 `docs/CHAPTERS.md`。
- 建立 `docs/FEATURE_BACKLOG.md`，记录世界观、版本差异、抽取审核、OC实验室及原有v0.7交付目标。

## v0.7 开发中 · 2026-10-18 · PR B

- 新增独立 Live2D Studio 档案工作区：只读扫描文件夹/ZIP/Windows RAR，多模型登记、依赖诊断、作者/许可、收藏、评分、喜爱度、标签与备注。
- 真实本机素材识别 3 模型，原始文件扫描前后 SHA256 一致；公开截图仅为生成结构样本。
- 尚未接入实时渲染、面捕、道具或方案，未内置 Cubism Core。运行时与公开发行许可的前置条件见 `docs/LIVE2D_STUDIO.md`。

## v0.7 开发中 · 2026-10-18 · PR A

- 素材主画廊完整分页；列表省略正文，打开详情后再取，避免长篇正文拖慢列表。
- 上传与目录导入改为分块哈希和磁盘临时写入，原文件只读；批量导入逐文件提交，模型文件夹打包使用磁盘流。
- 后台任务使用有限 worker 与 SQLite 持久历史，重启标记中断；导入页面支持进度、取消与恢复最近结果，不自动重放 AI 请求。
- 实测与未完成项见 `docs/audits/v0.7/foundation.md`。Live2D Studio、桌面打包、更新与 v0.7 正式发布尚未完成。

## v0.7 开发中 · 2026-10-18 · PR 1

- 建立 API、26 路由、文件预览、数据库和性能基线审计，保留真实/生成/Mock 验证边界；进度见 `docs/V07_PROGRESS.md`，完整交付计划见 `docs/V07_PLAN.md`。
- 修复 SPA 静态文件回退越过 dist 目录，以及未知 API 返回 HTTP 200 网页的问题。
- 修复删除素材在事务回滚后留下“记录还在、文件已丢”的问题：受管理文件改为提交成功后清理，保护回滚、保存点和会话关闭，并限制清理目录。
- 修复搜索素材结果不打开对应详情，以及非法搜索模式导致页面异常的问题。
- v0.7 的桌面安装/便携版、整库恢复、签名更新与 Release 流水线仍在待办；本轮不创建正式版本或升级提示。

## v0.6.4 · 2026-10-18

- **百科 Markdown 导出**：设置页下载全部百科，世界观页下载当前世界观；ZIP 内包含目录、世界观、角色和地点 / 组织 / 事件 / 物品 / 概念的独立 Markdown 文件，生成的相对链接解压后可离线阅读。
- 保留正文 Markdown、标签、角色别名 / 性别 / 出场作品、条目层级 / 事件时间 / 相关角色，以及关系方向、说明和确认状态；范围外的关联只保留名称。文件名使用 ID，避免重名和名称中的路径字符造成覆盖。
- 接口：`GET /api/exports/encyclopedia`，可选 `?world_id=<id>`。只导出已保存的百科文本，不含媒体、模型、笔记、角色卡、对话或 API Key；不提供还原，不能替代整库备份。原文中的站内链接和素材引用保留原样。


## v0.6.3 · 2026-10-17

第六轮（第四部分）：galgame 游戏库。

- **游戏库** `/galgames`：从 **Bangumi**（`api.bgm.tv` v0）、**VNDB**（Kana API）、**月幕 Galgame**（开放 API，OAuth 客户端凭证）搜索并添加游戏
- **混合模式**（默认）：三个来源同时搜索；选中一条后用原名 / 标题在其余来源里自动找同一部作品（名称相似度 ≥ 0.8、发售年份不冲突），按来源顺序合并字段（简介优先中文），别名、标签、平台、链接取并集，各来源的评分 / 排名 / 票数 / 时长分别保留；某个来源出错、超时、限流都不影响其他来源，错误显示在界面上。**单一来源模式**：出错或没结果时按顺序回退。设置里可调整模式、来源顺序、启用的来源、Bangumi 令牌（可选，用于 R18 条目）、是否拉取角色、是否模糊 R18 封面
- 游玩记录：六种状态（未游玩 / 想玩 / 在玩 / 玩过 / 搁置 / 弃坑）、1–10 评分、游玩时长、开始 / 通关日期、Markdown 游玩笔记；**手动记每一次游玩**（日期、时长、备注），详情页有近 8 周柱状图与时间线，游戏库顶部有“继续游玩”横幅（滚轮切换）、今天 / 本周 / 本月时长与 17 周游玩日历
- **手动修改优先**：改过的元数据字段记在 `overrides`，刷新元数据时保留，可一键恢复为来源数据；可单独刷新、解除或重新匹配某个来源
- 一键**新建作品**（类型 galgame），作品下的 **CG 档案**直接在游戏详情里浏览（鉴赏模式）；来源里的角色（名字、原名、配音、链接）可导入角色百科并记为出场作品
- 游戏库：网格 / 列表视图、按状态 / 来源 / 品牌筛选、六种排序、标题 / 原名 / 别名 / 品牌 / 笔记全文检索、多选批量改状态 / 置顶 / 删除、随机挑一款、**批量添加**（逐个按相似度匹配，或一键用第一条结果；匹配不上的先建标题）、手动添加、导出 JSON / CSV、R18 封面默认模糊（可临时显示）
- **分享足迹**：把玩过的作品排成一张图（排序、逐款隐藏或遮盖封面），在本机生成 PNG 或复制到剪贴板，不上传
- 封面只在添加时勾选“保存封面”或手动点“保存封面”时下载，只接受三家来源的图床地址，转成 webp 存在 `thumbs/galgame-<id>.webp`；也可以上传自己的封面
- 接口：`/api/galgames`（CRUD，`?status= &source= &developer= &nsfw= &sort=`）、`GET|PUT /api/galgames/meta/settings`、`GET /api/galgames/meta/search`、`POST /api/galgames/meta/preview`、`POST /api/galgames/from-meta`、`POST /api/galgames/quick-add`、`POST /{id}/refresh`、`POST /{id}/match`、`DELETE /{id}/sources/{source}`、`GET|POST|PUT|DELETE /{id}/cover`、`POST /{id}/work`、`POST /{id}/import-characters`、`GET /{id}/cg`、`GET|POST /{id}/plays`、`DELETE /plays/{pid}`、`GET /plays/summary`、`GET /stats/summary`、`POST /bulk`、`GET /export/file?format=json|csv`
- 模拟元数据接口 `python -m front_api.mock_galgame`（虚构的【示例】游戏，按三家真实接口格式返回），测试与示例截图都不联网；`FRONT_GALGAME=off` 可完全关闭联网
- 设计参考 ReinaManager（AGPL-3.0）与恋页 KoiPage（未指定许可证）的功能思路，未使用其代码；KoiPage 使用的 NextMoe 接口需要以资源站名义署名，因此没有接入
- **修复**：v0.6.0 起的页面切换动画（`mode="out-in"` + 同步结束的离场钩子）会让站内跳转后的新页面不渲染（页面空白，控制台报 `Cannot read properties of null (reading 'parentNode')`）；之前的截图都是逐页直接打开，没有暴露这个问题
- 测试 117 → 129 项

## v0.6.2 · 2026-10-17

第六轮（第三部分）：图表画布。

- **图表画布** `/diagrams`：基于 Vue Flow（MIT）。流程图八种形状（处理、开始 / 结束、判断、输入 / 输出、文档、数据、准备、连接点）、**节点工作流**（输入 / 输出端口与参数，端口一一对应连线）、**思维导图**、便签、分组框
- 编辑：从面板拖入或点击添加（连点自动错开）、双击改文字、四边连接点拖线、节点缩放、属性面板（文字、形状、颜色、端口、参数、链接、置顶 / 置底）；连线文字、折线 / 曲线 / 直线 / 直角、颜色、虚线、箭头、流动动画（遵循“减少动态效果”）；多选对齐 / 等距分布；`Tab` 接新节点、`Ctrl/⌘ C / V / D` 复制粘贴再制、`Ctrl/⌘ A` 全选、`Ctrl/⌘ Z / ⇧Z` 撤销重做（每个操作一步）、`?` 快捷键面板；吸附网格、小地图、缩放与适应画布
- 节点可链接到素材、笔记、角色、世界观、作品、其他图表或 http(s) 网址，点角标直接打开
- 自动保存（含视角），打开或保存时生成列表缩略图；**导出 PNG（2 倍）/ SVG / JSON**，导入 Front 图表 JSON 或 Vue Flow `toObject()` 结果；复制图表；关联作品、标签、置顶
- 接口：`/api/diagrams`（CRUD，`?kind=` 筛选，列表不带画布数据）、`GET /api/diagrams/templates`、`GET /{id}/export`、`POST /import`、`POST /{id}/duplicate`、`PUT|GET|DELETE /{id}/preview`；保存时校验节点 id 唯一、连线两端存在、链接只允许站内页面或 http(s)，节点 / 连线数量与大小有上限
- 节点标题、说明、参数与连线文字进入全文检索；总览热力图统计图表编辑；总览新增“画图表”
- 三个原创示例模板（灯塔节剧情流程、AI 出图工作流、雾港世界观脑图），同时写入【示例】数据
- 新依赖：@vue-flow/core、@vue-flow/background、@vue-flow/minimap、@vue-flow/node-resizer、html-to-image（均为 MIT）
- 测试 111 → 117 项

## v0.6.1 · 2026-10-17

第六轮（第二部分）：超级笔记本 + 多格式文件识别与预览。

- **超级笔记本** `/notes`：块编辑器（Tiptap）写笔记：标题、粗体 / 斜体 / 删除线 / 高亮、行内代码、链接、待办、有序 / 无序列表、引用、代码块（highlight.js 高亮）、表格、图片、分隔线；输入 `/` 唤出插入菜单；拖入或粘贴文件直接上传进素材库并插入；**嵌入素材**、**链接到其他笔记**（`Ctrl/⌘` + 点击跳转）；页面可无限嵌套（目录树、移动、子页面），带图标、标签、置顶、关联作品；输入 600 ms 后自动保存，`Ctrl/⌘ S` 立即保存；正文存为 Markdown
- **引用与反向链接**：每页列出“这页用到的素材”（带封面）、子页面和“链接到这里的笔记”；接口 `/api/notes`、`/api/notes/tree`、`/api/notes/{id}/move`、`/api/notes/{id}/refs`；笔记进入全文检索、总览统计与创作热力图
- **文件识别**（新包 `front_api/filetypes`）：3D 模型（glb / gltf / vrm / obj / fbx / pmx / pmd）、Live2D（Cubism 2–5）、音频、视频、PDF、Office / OpenDocument / EPUB、压缩包、代码与脚本；读出的信息存入 `meta.file`，文字进入全文检索，自动生成封面（音频封面、VRM 缩略图、视频截帧、PDF 首页、包内图片）；识别出的类型优先于手选类型；新素材类型 model3d / live2d / audio / video / pdf / document / archive / code
- **预览**：three.js 3D 预览（旋转、线框、背景、复位、动画、**设为封面**；舞台背景跟随主题），VRM 使用许可一览（人形骨骼不完整的 VRM 自动按普通 glTF 显示），自写的 PMX 静态网格读取；Live2D 贴图 / 动作 / 表情（不做实时渲染，Cubism Core 为专有许可）；音频播放器；视频播放；PDF 逐页渲染；Word / Excel / PPT 文字与表格预览；压缩包目录（包内图片可点开）；代码语法高亮
- **模型包**：批量导入时，Live2D / PMX / glTF / OBJ + MTL 文件夹被认成一个条目并打包成一个 zip 素材；预览时通过 `GET /api/assets/{id}/entry/{path}` 按需读取包内文件，不解压到硬盘，单个文件 64 MB 上限防压缩炸弹
- 新接口：`GET /api/assets/{id}/file?inline=1`、`GET /api/assets/{id}/pdf/{page}`、`PUT /api/assets/{id}/thumb`、`POST /api/assets/{id}/reanalyze`、`POST /api/assets/reanalyze`；素材列表不再带大段预览数据，打开详情时再取
- 素材库：按 图片 / 3D / Live2D / 音频 / 视频 / 文档 / 文本 / 压缩包 分段筛选；无封面的文件显示类型图标卡片；宽版详情弹窗
- 弹窗、图标按钮与链接按钮样式统一（`a.btn.ghost.iconbtn` 与按钮一致）
- 新依赖：后端 tinytag（MIT）、pypdfium2（Apache-2.0 / BSD-3-Clause）；前端 three（MIT）、@pixiv/three-vrm（MIT）、Tiptap（MIT）、tiptap-markdown（MIT）、highlight.js（BSD-3-Clause）。FFmpeg 可选
- 新文档 [docs/FILETYPES.md](docs/FILETYPES.md)
- 测试 102 → 111 项（示例文件全部由 `tests/samples.py` 现场生成）

## v0.6.0 · 2026-10-17

第六轮（第一部分）：界面焕新 + 浏览器查询。

- **新设计系统**：深靛夜色底 + 极淡网格、单一雾紫强调色，全部颜色改为语义变量；**深色 / 浅色主题**切换；悬浮圆角侧栏（可收起为图标栏，状态记在本地）、玻璃顶栏（分组眉标 + 页面标题 + 搜索胶囊，`Ctrl/⌘ K` 或 `/` 聚焦）、实心胶囊按钮、分段控件、更柔和的弹窗与提示条
- **统一图标**：导航与按钮全部换成 Lucide 线性图标
- **总览重做**：按时段问候、关键词 + 语义的大搜索框、常用操作、**创作热力图**（最近 53 周，按本机时区统计入库与编辑，连续天数）、一行统计、画廊式最近入库；新接口 `GET /api/stats/activity`
- **素材库**：画廊式网格（图片无边框、信息在图下、悬停描边）；筛选栏在滚动时固定
- **动效（GSAP）**：页面对焦进入、列表 / 卡片首次出现时依次显现（`v-reveal`）、弹窗缩放进入、侧栏高亮块滑动、提示条进出、总览数字滚动与热力图显现；全部遵循 `prefers-reduced-motion`，悬停 / 点击 / 快捷键不做 GSAP 动画
- **浏览器查询**：角色详情、作品、SD 模型详情新增“浏览器查询”弹出菜单，可切换关键词（名称 / 别名），在新标签页打开各站点搜索；默认站点 Bangumi（游戏 / 角色）、VNDB（游戏 / 角色）、月幕 Galgame、2DFan、萌娘百科、Bilibili 空间 2072586344、Civitai、Summer Pockets 官网（只在关键词匹配时出现）；设置页可增删改、排序、启用 / 停用、恢复默认。接口 `/api/quick-search`、`/api/quick-search/sites`。只生成链接，不抓取、不下载
- 关系网的文字与背景颜色跟随主题；作品页有链接时显示“官网”按钮
- 新文档 [docs/DESIGN.md](docs/DESIGN.md)
- 测试 98 → 102 项

## v0.5.0 · 2026-10-17

第五轮：AI 角色与世界观智能。

- **流式对话** `POST /api/ai/sessions/{id}/generate`（SSE：`start` / `delta` / `done` / `error`），可随时停止 `POST /api/ai/generations/{token}/stop`，停止时保留已生成的部分
- **重新生成与分支**：消息组成树（`chat_messages.parent_id` + `chat_sessions.head_id`），重新生成产生同级回复，‹ i/n › 切换；修改用户消息可“直接修改”或“另开分支并发送”；备选开场白也是可切换的根分支；编辑、删除（连同后续分支）消息；查看本次实际发给 AI 的上下文 `GET /api/ai/sessions/{id}/context`
- **世界书 / Lorebook** `/api/lorebooks`、`/api/lore-entries`：关键词（`/正则/flags`）、次关键词、常驻、递归（最多 3 轮）、扫描深度、token 预算、插入位置（角色设定之前 / 之后）、启用开关；**命中测试**；从世界观百科生成；导入 SillyTavern 世界书 JSON、角色卡 JSON / PNG 里的 `character_book`；导出 V2 / SillyTavern；角色卡导入导出时带上 `character_book`；对话时自动启用角色卡、所属世界观以及会话挂载的世界书，回复上显示命中的条目
- **设置页** `/settings`：多个 AI 服务（`/api/ai/providers`，Ollama / LM Studio / OpenAI / DeepSeek / OpenRouter 预设），读取模型列表、测试连接（对话 / 嵌入）；分别选择对话、嵌入、视觉服务；`/api/settings`。API Key 只存本机数据库，接口只返回打码提示；网页设置优先于环境变量
- **从小说抽取角色** `/extract`：按章节分段（`POST /api/ai/extract/characters`，后台任务），合并别名、与已有角色对照，表格中修改后写入 `POST /api/ai/extract/apply`；关系以“AI 待确认”写入；素材库与阅读页都有入口
- **语义检索**：`/api/search/semantic`（semantic / hybrid，RRF 融合）、`/api/search/similar`、索引状态与后台增量索引；默认本地 n-gram 向量（离线、近似），可改用嵌入模型；搜索页新增 关键词 / 语义 / 混合 切换与相关度条
- **自动打标签（可选）**：WebUI WD14 Tagger 扩展（`/tagger/v1/interrogate`）或视觉模型；结果按标签名 / 别名对到已有标签；单张建议 `GET /api/ai/tagger/assets/{id}`，批量 `POST /api/ai/tagger/run`
- **模拟 AI 服务** `python -m front_api.mock_ai`：OpenAI 兼容的对话（含流式）、嵌入与视觉接口，回复带“【模拟回复】”，用于测试、示例数据与截图；`mock_sd` 增加 Tagger 接口
- 世界书条目进入全文检索
- 数据库自动迁移：`chat_sessions.head_id` / `lorebook_ids`、`chat_messages.parent_id` / `meta`（老对话自动串成单链）、`character_cards.lorebook_id`；新表 `ai_providers`、`app_settings`、`lorebooks`、`lore_entries`、`embeddings`
- 示例数据新增：雾港世界书与林汐的角色书、带分支的示例对话、第二篇示例小说（用于抽取新角色）、两个示例 AI 服务配置、标签别名 scenery / portrait
- 测试 78 → 98 项

## v0.4.0 · 2026-10-17

第四轮：AI 绘画工作流。

- **模型目录扫描**：输入 WebUI / Forge / ComfyUI 的 `models` 路径，按子文件夹判断类型（Checkpoint / LoRA / VAE / Embedding / 放大 / ControlNet / Hypernetwork / 文本编码器），读取 safetensors 元数据判断底模，识别同名预览图与 `.civitai.info` / `.json` 说明；预览后勾选登记（后台任务，进度条，可取消），可选择同时计算哈希、导入预览图、更新已登记项
- **模型哈希**：SHA256 / AutoV1 / AutoV2 / AutoV3 一次读完同时计算；出图参数里的 `Model hash` 可按 AutoV1 / AutoV2 / SHA256 前缀匹配已登记模型
- **Civitai 匹配（可选）**：按 SHA256 查询模型 / 版本名、类型、底模、触发词与预览图，可写回模型条目；单个或全部匹配；`FRONT_CIVITAI=off` 完全关闭，`FRONT_CIVITAI_API_KEY` 可选
- **提示词片段库** `/api/prompt-snippets`：分类卡片、组合器（权重 `(片段:1.2)`、排序、去重），存为提示词或带去出图
- **出图** `/generate`：连接 SD WebUI / Forge（`FRONT_SD_WEBUI_URL`）或 ComfyUI（`FRONT_COMFYUI_URL`，内置模板或自定义工作流占位符）；多模型、LoRA 权重、XY 轴（模型 / CFG / 步数 / 采样器 / 调度器 / 种子 / 尺寸 / Clip skip / 提示词替换 / LoRA 权重），最多 100 张；结果自动入库（PNG 内嵌参数、标签、收藏集），自动建立提示词与出图记录
- **对比视图**：差异参数高亮、**参数差异表**（高亮与多数不同的取值）、与基准提示词相比增删的词；**XY 网格**（按出图批次或任意两个参数）
- **后台任务** `/api/jobs`
- **模拟 SD 后端** `python -m front_api.mock_sd`：无显卡时体验整条出图流程，图片带“模拟出图”角标
- **修正**：标签使用次数现在是“含子标签的总数”，同一条目同时打了上下级标签只算一次；界面同时显示直接使用次数
- 数据库自动迁移：`sd_models.hashes`、`sd_models.civitai`、`generations.batch`、`generations.xy`；新表 `prompt_snippets`、`prompt_snippet_tags`
- 示例数据新增：14 个提示词片段、一个模拟的 WebUI 模型目录（假文件）、两次模拟出图（模型 × CFG、提示词替换 night / dawn / sunset）
- 测试 68 → 78 项

## v0.3.0 · 2026-10-17

第三轮：百科增强。

- **角色详情页** `/characters/:id`：Markdown 设定渲染（markdown-it，禁用原始 HTML；表格、引用、`[[名称]]` 站内搜索链接）；图集（排序、追加、移出、设为头像、大图）；出场作品（来源作品 + 出场登记，可增删）；关系列表（方向、AI 待确认标记）；所属组织 / 参与事件 / 相关地点；编辑角色时 Markdown 实时预览
- **世界观百科条目** `/api/world-entries`：地点 / 组织 / 事件 / 物品 / 概念五类，层级（同一世界观内、禁止成环）、Markdown 正文、标签、关联角色及其身份；世界观页按类型分页签：地点树、组织卡片、时间线、物品 / 概念
- **时间线** `/api/worlds/{id}/timeline`：事件按排序值从早到晚（未填排最后），带显示用时间、发生地点与参与角色
- **出场登记** `/api/appearances`：角色 × 作品（身份、备注），作品页显示登场角色 `/api/works/{id}/characters`
- **角色详情聚合接口** `/api/characters/{id}/detail`，图集接口 `/api/characters/{id}/gallery`
- **关系网**：按关系类型着色（颜色可改并保存）、点击类型显示 / 隐藏、隐藏 AI 待确认、保存 / 重置布局（`PUT` / `DELETE /api/graph/layout`，按世界观分别保存）、导出 PNG 与 JSON（`/api/graph/export`）、从角色详情页跳转时高亮该角色；`/api/graph` 增加 `kinds` 筛选与类型统计
- **标签**：层级（`parent_id`，按上级标签筛选自动包含所有子标签）、别名（标签搜索与全文检索都会命中别名）、颜色、使用次数 `/api/tags/usage`、标签树 `/api/tags/tree`、合并 `POST /api/tags/{id}/merge`（使用处去重改挂、子标签迁移、原名变别名）
- 全文检索加入百科条目，搜索结果可直接跳到对应角色 / 世界观 / 条目 / 作品 / 提示词 / 角色卡
- 数据库自动迁移：`tags.aliases`、`tags.parent_id`；新表 `world_entries`、`world_entry_tags`、`entry_characters`、`appearances`、`character_assets`、`graph_layouts`
- 示例数据新增：雾港市地点树、两个组织、6 个事件的时间线、物品与概念、林汐的图集与 Markdown 设定、客串登记、一条 AI 待确认关系、关系类型配色、层级标签与别名
- 测试 61 → 68 项

## v0.2.0 · 2026-10-17

第二轮：素材与 CG。

- **批量导入**：本机文件夹路径扫描预览 + 导入（递归、文件修改时间作为日期、统一标签 / 作品 / 世界观、按内容去重、单次最多 5000 个文件）；也可在浏览器中选择文件夹上传
- **galgame CG 识别**：按文件名规则（字母差分、`_数字` 差分、末尾连续数字、`diff/sabun/差分` 标记）+ 分辨率分组；导入时可新建作品；`/api/works/{id}/cg` 分组档案、`regroup` 重新识别
- **CG 鉴赏模式**：全屏、← → 切换 CG、↑ ↓ / 数字键切换差分、自动播放、预加载、隐藏界面
- **ComfyUI 解析**：API 格式 `prompt`（沿连线解析 Combine / Primitive 等中间节点）与界面格式 `workflow`；提取 Checkpoint / UNET、LoRA、采样参数、尺寸；下载内嵌工作流
- **AI 图 → 提示词库**：`/api/prompts/from-asset/{id}`，相同提示词自动复用并加入模型对比，按文件名匹配已登记模型
- **收藏集**：内容排序（拖拽）、追加 / 移出、自定义封面（默认第一项）、收藏集排序
- **小说**：章节自动拆分、字数统计（中日文按字、英文按词）、阅读模式（目录、翻章、字号、行距、四种主题、进度记忆）
- 启动时自动迁移数据库新字段
- 测试 35 → 61 项；示例数据新增差分 CG、ComfyUI 示例图、分章节小说和收藏集

## v0.1.0 · 2026-10-17

第一轮：项目骨架与全部核心模块的第一版。

- 后端：FastAPI + SQLite，素材 / 标签 / 作品 / 世界观 / 角色 / 关系 / 收藏集 / SD 模型 / 提示词 / 出图记录 / 角色卡 / 对话会话的完整增删改查 API
- 全文检索：FTS5 trigram，中文子串可搜，增删改即时同步索引
- 素材上传：尺寸识别、缩略图、SHA256 去重、按年月存储；SD WebUI PNG 参数自动提取；txt/md 小说导入（UTF-8 / GB18030 / Shift-JIS）
- 关系网接口与可视化（Cytoscape.js），AI 建议关系需人工确认
- 提示词“同一提示词 × 不同模型”对比视图
- SD 模型登记：读取 safetensors 元数据、判断底模、计算 SHA256
- 角色卡：Character Card V2 JSON / PNG 导入导出（兼容 V1、V3），从百科角色生成
- AI 接口层：OpenAI 兼容 Provider；角色扮演对话（带上下文、{{char}}/{{user}} 占位符）；世界观关系识别
- 前端：Vue 3 管理界面，覆盖以上全部模块
- 内置【示例】数据脚本，测试 35 项，GitHub Actions CI，仓库卫士测试
