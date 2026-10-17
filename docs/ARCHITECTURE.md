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
| `tags` | 分面标签 | `category`（gender / medium / source / style / type / custom）+ `name` 唯一 |
| `works` | 作品（动漫、游戏、galgame、小说、原创企划） | `kind`、`year`、`publisher` |
| `worlds` | 世界观 | `summary`、`content`（Markdown，AI 关系识别的语料） |
| `assets` | 素材 | `kind`（drawing / ai_image / material / novel / cg / reference / other）、`work_date`、`file_path`、`sha256`、`meta`（SD 参数等）、`work_id`、`world_id` |
| `collections` | 收藏集 | 与 `assets` 多对多，可挂 `work_id` |
| `characters` | 角色百科条目 | `gender`、`world_id`、`work_id`、`avatar_asset_id`、`profile` |
| `relations` | 关系网的边 | `source_id`、`target_id`、`kind`、`bidirectional`、`ai_suggested`、`confirmed` |
| `sd_models` | SD 模型登记 | `kind`、`base_model`、`local_path`、`sha256`、`trigger_words` |
| `prompts` | 提示词 | `positive`、`negative`、`params`（JSON） |
| `generations` | 出图记录 | `prompt_id` × `model_id` → `asset_id`，用于风格对比 |
| `character_cards` | AI 角色卡 | 与 Character Card V2 的 `data` 字段一一对应 |
| `chat_sessions` / `chat_messages` | 角色扮演对话 | 会话绑定角色卡，消息按顺序保存 |
| `search_index` | FTS5 虚拟表 | `entity`、`entity_id`、`title`、`body` |

标签通过 `*_tags` 关联表挂在素材、角色、世界观、作品、提示词、模型上。删除角色会级联删除其关系；删除作品/世界观只会把引用置空。

## API 一览

每个资源都有统一的五个接口：

```
GET    /api/<资源>?q=&tag=1&tag=2&limit=&offset=&<筛选>   列表（tag 多值取交集，q 走全文索引）
GET    /api/<资源>/{id}
POST   /api/<资源>
PATCH  /api/<资源>/{id}                                   只更新传入的字段
DELETE /api/<资源>/{id}
```

资源：`tags` `works` `worlds` `assets` `collections` `characters` `relations` `sd-models` `prompts` `generations` `cards`

额外接口：

| 接口 | 说明 |
| --- | --- |
| `POST /api/assets/upload` | multipart 上传，自动识别类型 / 尺寸 / SD 参数 / 小说编码 |
| `GET /api/assets/{id}/file`、`/thumb` | 原文件、WebP 缩略图 |
| `GET /api/assets/stats/timeline` | 按 年-月 × 类型 统计 |
| `GET /api/graph?world_id=` | 关系网节点与边 |
| `GET /api/prompts/{id}/compare` | 同一提示词按模型分组的出图 |
| `POST /api/sd-models/inspect` | 读取本机模型文件信息（safetensors 元数据、可选 SHA256） |
| `POST /api/cards/import` | 导入 JSON / PNG 角色卡 |
| `GET /api/cards/{id}/export.json`、`export.png` | 导出 V2 角色卡 |
| `POST /api/cards/from-character/{id}` | 从百科角色生成角色卡 |
| `GET /api/ai/status` | AI 服务状态 |
| `/api/ai/sessions[...]` | 对话会话增删查、发送消息 |
| `POST /api/ai/worlds/{id}/suggest-relations` | AI 识别世界观中的角色关系 |
| `GET /api/search?q=&entity=` | 全局全文检索 |
| `POST /api/search/rebuild` | 重建索引 |

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
    seed.py        【示例】数据
    ai/            Provider 与提示词构建
    routers/       library assets characters sd cards ai system
  tests/
frontend/
  src/views/       每个页面一个组件
  src/components/  Modal、TagPicker、TagChips
docs/
  screenshots/     README 截图（仓库中唯一允许放图片的目录之一）
```
