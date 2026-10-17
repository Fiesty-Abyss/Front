# 更新日志

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
