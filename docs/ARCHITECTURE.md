# 架构说明

## 总览

```
┌──────────── 浏览器 ────────────┐        ┌──────────────── Front 后端（FastAPI）────────────────┐
│ Vue 3 + Vite 单页应用           │  HTTP  │ routers/  REST API（/api/*，/docs 自动文档）          │
│ 素材库 · 百科 · 关系网 · 提示词 │ ─────▶ │ crud.py   通用增删改查工厂（分页/标签交集/全文/筛选） │
│ 模型库 · 角色卡 · AI 对话        │        │ search.py FTS5 trigram 索引，flush 时自动同步          │
└─────────────────────────────────┘        │ pngmeta.py SD 参数解析、角色卡 PNG 读写               │
                                           │ ai/       Provider 接口 + 提示词构建                   │
                                           └───────┬───────────────────────────┬──────────────────┘
                                                   │                           │
                                     FRONT_DATA_DIR（仓库之外）          OpenAI 兼容服务（可选）
                                     ├─ front.db   SQLite               OpenAI / DeepSeek / Ollama /
                                     ├─ media/YYYY/MM/<sha>.<ext>       LM Studio / vLLM …
                                     └─ thumbs/<id>.webp
```

- **单文件数据库**：所有元数据在一个 SQLite 文件里，零运维，备份数据目录即可。
- **文件按内容寻址**：上传文件以 SHA256 命名，同一文件不会重复入库。
- **后端托管前端**：`frontend/dist` 存在时，后端直接提供页面（`/static` + SPA 回退），只需启动一个进程。

## 数据模型

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `tags` | 分面标签 | `category`（gender / medium / source / style / type / custom）+ `name` 唯一；`aliases`（JSON 列表）、`parent_id`（层级）、`color` |
| `works` | 作品（动漫、游戏、galgame、小说、原创企划） | `kind`、`year`、`publisher` |
| `worlds` | 世界观 | `summary`、`content`（Markdown，AI 关系识别的语料） |
| `assets` | 素材 | `kind`（drawing / ai_image / material / novel / cg / reference / other）、`work_date`、`file_path`、`sha256`、`meta`（SD 参数等）、`work_id`、`world_id` |
| `collections` | 收藏集 | 与 `assets` 多对多，可挂 `work_id` |
| `characters` | 角色百科条目 | `gender`、`world_id`、`work_id`、`avatar_asset_id`、`profile` |
| `world_entries` | 世界观百科条目 | `world_id`、`kind`（location / organization / event / item / concept）、`parent_id`（层级；事件的上级即发生地点）、`content`（Markdown）、`date_label` + `sort_key`（时间线） |
| `entry_characters` | 条目 × 角色 | `role`（会长、成员、当事人……） |
| `appearances` | 出场登记 | `character_id` × `work_id` 唯一，`role`、`note` |
| `character_assets` | 角色图集 | `position` 排序 |
| `graph_layouts` | 关系网布局 | `scope`（`world:<id>` / `all`）、`positions`、`kind_colors` |
| `relations` | 关系网的边 | `source_id`、`target_id`、`kind`、`bidirectional`、`ai_suggested`、`confirmed` |
| `sd_models` | SD 模型登记 | `kind`、`base_model`、`local_path`、`sha256`、`hashes`（SHA256 / AutoV1 / AutoV2 / AutoV3）、`civitai`（匹配结果摘要）、`trigger_words` |
| `prompts` | 提示词 | `positive`、`negative`、`params`（JSON） |
| `prompt_snippets` | 提示词片段 | `category`（quality / style / character / clothing / pose / composition / background / lighting / negative / other）、`positive`、`negative`、`position`，多对多 `prompt_snippet_tags` |
| `generations` | 出图记录 | `prompt_id` × `model_id` → `asset_id`、`params`；`batch`（同一次出图任务）、`xy`（该格在 X / Y 轴上的取值） |
| `character_cards` | AI 角色卡 | 与 Character Card V2 的 `data` 字段一一对应 |
| `chat_sessions` / `chat_messages` | 角色扮演对话 | 会话绑定角色卡，消息按顺序保存 |
| `search_index` | FTS5 虚拟表 | `entity`、`entity_id`、`title`、`body` |

标签通过 `*_tags` 关联表挂在素材、角色、世界观、作品、提示词、模型上。删除角色会级联删除其关系、出场登记、图集与条目关联；删除世界观会级联删除其百科条目；删除作品/世界观只会把引用置空。

## API 一览

每个资源都有统一的五个接口：

```
GET    /api/<资源>?q=&tag=1&tag=2&limit=&offset=&<筛选>   列表（tag 多值取交集，q 走全文索引）
GET    /api/<资源>/{id}
POST   /api/<资源>
PATCH  /api/<资源>/{id}                                   只更新传入的字段
DELETE /api/<资源>/{id}
```

资源：`tags` `works` `worlds` `world-entries` `appearances` `assets` `collections` `characters` `relations` `sd-models` `prompts` `prompt-snippets` `generations` `cards`

按标签筛选（`tag=`）会同时匹配该标签的所有子标签；`/api/tags?name=` 同时匹配别名。

额外接口：

| 接口 | 说明 |
| --- | --- |
| `POST /api/assets/upload` | multipart 上传，自动识别类型 / 尺寸 / SD WebUI 与 ComfyUI 出图信息 / 小说编码 |
| `POST /api/import/scan` | 扫描本机文件夹（只读预览）；`cg_mode` 时返回差分分组 |
| `POST /api/import/run` | 导入文件夹：复制进数据目录、去重、可新建作品，CG 模式下自动分组 |
| `GET /api/works/{id}/cg`、`POST .../cg/regroup` | CG 档案（按差分分组）、重新识别差分 |
| `GET /api/assets/{id}/chapters`、`/chapters/{n}` | 小说目录与字数、单章正文（含上一章 / 下一章） |
| `GET /api/assets/{id}/workflow` | 下载 PNG 内嵌的 ComfyUI 工作流 |
| `POST /api/prompts/from-asset/{id}` | AI 图的出图参数存入提示词库并记录一次出图 |
| `POST /api/collections/{id}/items`、`DELETE .../items/{asset}`、`PUT .../order`、`PUT /api/collections/order` | 收藏集追加 / 移出 / 排序、收藏集之间排序 |
| `GET /api/assets/{id}/file`、`/thumb` | 原文件、WebP 缩略图 |
| `GET /api/assets/stats/timeline` | 按 年-月 × 类型 统计 |
| `GET /api/graph?world_id=&kinds=&include_unconfirmed=` | 关系网节点与边、关系类型统计、已保存的布局与配色 |
| `PUT /api/graph/layout`、`DELETE /api/graph/layout?world_id=` | 保存节点位置 / 关系类型颜色（只更新传入的字段）、恢复自动布局 |
| `GET /api/graph/export?world_id=` | 导出关系网 JSON |
| `GET /api/characters/{id}/detail` | 角色详情聚合：世界观、图集、出场作品、关系、所属条目、角色卡 |
| `PUT/POST /api/characters/{id}/gallery`、`DELETE .../gallery/{asset}` | 图集整体排序 / 追加 / 移出 |
| `GET /api/worlds/{id}/timeline` | 事件时间线（含地点与参与角色） |
| `GET /api/works/{id}/characters` | 作品的登场角色 |
| `GET /api/tags/tree`、`/api/tags/usage`、`POST /api/tags/{id}/merge` | 标签树、使用次数（`{direct, total}`，total 含所有子标签、同一条目去重）、合并标签 |
| `GET /api/prompts/{id}/compare` | 同一提示词按模型分组的出图；每张带归一化参数 `norm`、相对基准提示词的增删词，顶层 `diff_keys`（取值不同的参数）与 `common` |
| `GET /api/prompts/{id}/batches`、`/xy?x=&y=&batch=` | 出图批次列表；XY 网格（批次自带的轴优先，也可按任意两个参数排） |
| `POST /api/sd-models/inspect` | 读取本机模型文件信息（safetensors 元数据、可选哈希） |
| `POST /api/sd-models/scan`、`/scan/run` | 扫描模型目录（只读预览）；后台登记（可算哈希、导入预览图、更新已登记项） |
| `POST /api/sd-models/{id}/hash`、`/hash-all` | 计算 SHA256 / AutoV1 / AutoV2 / AutoV3（单个同步、全部为后台任务） |
| `POST /api/sd-models/{id}/civitai`、`/civitai-all` | 按 SHA256 查询 Civitai，可写回名称、底模、触发词并下载预览图 |
| `POST /api/prompt-snippets/compose` | 拼接基准提示词与片段（权重、去重） |
| `GET /api/generate/status`、`POST /api/generate` | SD 后端状态（模型、采样器、LoRA）；提交出图任务（多模型、LoRA、XY 轴，最多 100 张） |
| `GET /api/jobs`、`/api/jobs/{id}`、`POST /api/jobs/{id}/cancel` | 后台任务进度与取消（任务保存在内存中，重启后清空） |
| `POST /api/cards/import` | 导入 JSON / PNG 角色卡 |
| `GET /api/cards/{id}/export.json`、`export.png` | 导出 V2 角色卡 |
| `POST /api/cards/from-character/{id}` | 从百科角色生成角色卡 |
| `GET /api/ai/status` | AI 服务状态 |
| `/api/ai/sessions[...]` | 对话会话增删查、发送消息 |
| `POST /api/ai/worlds/{id}/suggest-relations` | AI 识别世界观中的角色关系 |
| `GET /api/search?q=&entity=` | 全局全文检索 |
| `POST /api/search/rebuild` | 重建索引 |

## 素材入库流程（`ingest.py`）

上传接口与文件夹导入共用 `ingest()`：计算 SHA256 去重 → 判断类型（文本 / 图片）→ 读取尺寸 → 识别出图信息（`parameters` → SD WebUI；`prompt` / `workflow` → ComfyUI，见 `comfy.py`）→ 写入 `media/YYYY/MM/<sha>.<ext>` → 生成缩略图。

## galgame CG 分组（`cg.py`）

按顺序尝试：显式差分标记（`ev01_diff2`、`ev01差分2`）→ 数字后接字母（`ev01a`）→ 带数字前缀 + 分隔符 + 数字（`ev01_02`）→ 末尾 4 位以上数字且有兄弟文件（`ev0101`/`ev0102`）。同组还要求分辨率相同，同名不同分辨率的组以 `@1920x1080` 区分。分组结果写入 `asset.meta["cg"]`（group / variant / 顺序），档案与鉴赏模式按它展示。

## 小说章节（`chapters.py`）

按行识别“第X章/节/回/卷”、`Chapter N`、Markdown `#` 标题、序章 / 楔子 / 尾声 / 番外等；第一个标题前的内容归为“前言”。字数：中日文按字、英文按词。

## AI 绘画工作流（v0.4）

- **模型扫描**（`modelscan.py`）：遍历 `.safetensors / .ckpt / .pt / .pth / .bin / .gguf`，按所在文件夹（`Stable-diffusion`、`checkpoints`、`Lora`、`loras`、`VAE`、`embeddings`、`ESRGAN`、`upscale_models`、`ControlNet` …）判断类型，读取 safetensors 头部元数据推断底模，查找同名预览图和 `.civitai.info` / `.json` 说明。哈希一次读完文件同时算出：SHA256（整个文件）、AutoV1（偏移 1 MiB 起 64 KiB 的 SHA256 前 8 位）、AutoV2（SHA256 前 10 位）、AutoV3（safetensors 去掉头部后的张量数据 SHA256）。
- **Civitai**（`civitai.py`）：`GET /api/v1/model-versions/by-hash/<sha256>`，只取模型 / 版本名、类型、底模、触发词、链接与预览图地址；预览图只允许从 `image.civitai.com` / `imagecache.civitai.com` 下载，最大 20 MB。
- **出图**（`sdgen.py`）：WebUI 走 `/sdapi/v1/txt2img`（`override_settings` 切换模型，LoRA 写成 `<lora:名称:权重>`），返回的 PNG 补写 A1111 格式的 `parameters`；ComfyUI 走 `/prompt` → 轮询 `/history` → `/view` 取图，内置 Checkpoint → LoRA 链 → KSampler → VAEDecode 模板，也接受用户的 API 格式工作流（`{{prompt}}` `{{negative}}` `{{seed}}` `{{steps}}` `{{cfg}}` `{{width}}` `{{height}}` `{{sampler}}` `{{scheduler}}` `{{model}}` 占位符）。每张图都走 `ingest()` 入库，因而和手动上传的 AI 图一样能被解析、检索。
- **后台任务**（`jobs.py`）：线程 + 内存登记表，支持进度与取消；前端轮询。
- **参数归一化**（`sdparams.py`）：把 WebUI / ComfyUI / 手填的参数名统一（`Sampler`→`sampler`、`width`+`height`→`size` …），对比视图和 XY 网格都基于它。
- **模拟后端**（`mock_sd.py`）：实现上述 WebUI / ComfyUI 接口的子集，返回带“模拟出图”角标的占位图，用于测试、示例数据与截图。

## 数据库迁移（`migrate.py`）

`create_all` 只会建新表。`migrate.py` 在启动时检查已有表，缺少的新列用 `ALTER TABLE ... ADD COLUMN` 补齐，老版本的数据库可以直接升级。

## 全文检索

`search_index` 使用 FTS5 的 `trigram` 分词器，中文、日文不需要额外分词即可按子串搜索。SQLAlchemy 的 `after_flush` 事件在每次写入时同步索引，所以新增、修改、删除即时生效。trigram 至少需要 3 个字符，更短的查询（如“诗梦”）自动退回 `LIKE` 子串匹配。

## AI 接口层

```python
class AIProvider(Protocol):
    name: str
    def available(self) -> bool: ...
    def chat(self, messages, *, temperature=0.8, max_tokens=None) -> str: ...
```

- `OpenAICompatibleProvider`：调用 `{FRONT_AI_BASE_URL}/chat/completions`。
- `NullProvider`：未配置时使用，相关接口返回 503 和配置提示。
- 路由通过 FastAPI 依赖 `provider_dep` 获取 Provider，测试中用假 Provider 替换。

**角色扮演**：`build_roleplay_messages` 把角色卡的 system_prompt、description、personality、scenario、mes_example 组装成 system 消息，替换 `{{char}}` / `{{user}}`，附上最近 40 条历史，最后追加 `post_history_instructions`。

**关系识别**：`build_relation_messages` 把世界观正文与角色名单交给模型，要求只输出 JSON 数组；`parse_relations` 过滤掉不存在的角色 id、自环和重复项。结果以 `ai_suggested=True, confirmed=False` 写入，在关系网中以虚线显示，人工确认后才算正式关系。

## 目录结构

```
backend/
  front_api/
    main.py        应用工厂、路由注册、前端托管
    config.py      环境变量配置
    db.py models.py schemas.py
    crud.py        通用 CRUD 工厂
    search.py      FTS5 索引
    pngmeta.py     SD 参数 / 角色卡 PNG
    ingest.py      素材入库（上传与批量导入共用）
    comfy.py       ComfyUI prompt / workflow 解析
    cg.py          CG 差分分组
    chapters.py    小说章节与字数
    migrate.py     启动时补齐新列
    modelscan.py   模型目录扫描与哈希
    civitai.py     Civitai 按哈希查询
    sdgen.py       WebUI / ComfyUI 出图客户端、XY 轴
    sdparams.py    出图参数归一化与差异
    jobs.py        后台任务
    mock_sd.py     模拟 SD 后端（测试 / 演示）
    seed.py        【示例】数据
    ai/            Provider 与提示词构建
    routers/       library assets importer collections characters sd sdtools cards ai system
  tests/
frontend/
  src/views/       每个页面一个组件
  src/components/  Modal、TagPicker、TagChips、TagTree、JobProgress
docs/
  screenshots/     README 截图（仓库中唯一允许放图片的目录之一）
```
