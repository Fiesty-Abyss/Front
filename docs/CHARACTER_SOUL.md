# Character Soul · 可审核角色身份与记忆

## 本轮范围

新增 `/souls` 懒加载工作区和 `/api/souls` API。手动管理、来源审核、有限本地检索、历史追加恢复、导出及完整备份可在没有 AI 服务时运行。它是共享引用层，不替代百科、OC、角色卡、Voice、素材库或聊天消息树。

**聊天请求尚未接入记忆注入。** `recall` 始终返回 `sent_to_ai:false`，界面明确说明这是本地预览。#66 未合法验收合并前，不复制其上下文预算实现、不堆叠群聊依赖 PR。AI 自动提取、语义冲突分析、向量检索、自动摘要和群聊均未实现。

## 公开研究与许可证边界

研究锁定 [Soul-of-Waifu 提交 747048b3b3ad7d321a667630018f7ffc04eb5f6d](https://github.com/jofizcd/Soul-of-Waifu/tree/747048b3b3ad7d321a667630018f7ffc04eb5f6d)，项目采用 GPL-3.0。仅阅读架构，未复制代码、Prompt、UI、模型或数据，未运行或安装该项目。

| 公开文件 | 观察到的职责 | Front 独立设计 |
| --- | --- | --- |
| [soul_memory.py](https://github.com/jofizcd/Soul-of-Waifu/blob/747048b3b3ad7d321a667630018f7ffc04eb5f6d/app/utils/soul_memory.py) | 角色/会话记忆目录、主题检索和响应后的更新任务 | 使用现有 SQLite/EntityVersion；来源、人工审核、冲突与引用许可分开；没有后台更新 Agent |
| [prompt_engine.py](https://github.com/jofizcd/Soul-of-Waifu/blob/747048b3b3ad7d321a667630018f7ffc04eb5f6d/app/utils/ai_clients/prompt_engine.py) | Provider 上下文编排及可选记忆检索 | 先提供有范围、引用与字数预算的预览，后续复用 #66 完整语义轮次预算 |
| [soul_stage_engine.py](https://github.com/jofizcd/Soul-of-Waifu/blob/747048b3b3ad7d321a667630018f7ffc04eb5f6d/app/utils/ai_clients/soul_stage_engine.py) | 舞台角色、世界状态、事件和路由职责 | 分支经历与正式世界观隔离；本轮没有复制舞台或剧情引擎 |
| [soul_companion.py](https://github.com/jofizcd/Soul-of-Waifu/blob/747048b3b3ad7d321a667630018f7ffc04eb5f6d/app/utils/soul_companion/soul_companion.py) | 事件循环与桌面工具注册等职责 | 本轮不实现桌面 Agent、屏幕/剪贴板读取或模型工具执行 |

没有新增 PyTorch、CUDA、embedding 模型、权重、桌面常驻进程或 npm/Python 依赖。后续桌面工具必须是独立可选模块，默认关闭，有范围白名单、逐项授权、可见日志与停止开关；模型输出不能直接成为 shell 命令。

## 为什么需要共享身份

Character 已关联世界观与作品；OC、CharacterCard、VoiceProfile 只覆盖部分角色关系。Live2D 与普通图片/3D/VRM 则仍为各自档案或 Asset。没有一个现有实体能安全承载独立角色、跨模块关联与多会话记忆。

- `soul_identities`：整数内部 ID、不可变随机 UID、名称、世界观身份快照、备注、停用状态、并发 revision。
- `soul_links`：引用既有 Character、Card、OC、ChatSession、VoiceProfile、Live2DProfile、Asset 或 LoreEntry。保存目标 UID/创建身份及角色、世界观、世界书范围快照，不拥有原资料。
- `soul_memories`：独立 UID、Soul 引用、类型、内容、范围、来源、审核/冲突/引用许可、固定、重要度、停用及 revision。

名字不参与唯一匹配。同名不同世界观不能关联；已绑定不同百科人物的资料不能静默合并。角色卡关联到 Soul 后，才能显式关联使用它的会话。未归属世界观的图片、Live2D 和独立声线可由用户显式关联；已有其他人物/世界观归属的声线仍须通过范围校验。

旧目标删除后，创建时间或 UID 不同的新记录不会继承旧关联。原记录跨世界观或作品移动、角色卡改换人物/世界书、会话卡片失效都会给出诊断。不会自动重绑，不更新正式百科、小说或原模型。

## 记忆语义

| 类型 | 边界 |
| --- | --- |
| `core` | 必须引用已关联的正式百科/角色卡/OC；保存来源内容指纹与可用版本 ID |
| `episode` | 特定剧情经历；聊天来源必须为分支范围 |
| `relationship` | 用户审核的虚构关系，可显式选角色共享或局部范围 |
| `summary` | 手工录入的有限摘要；聊天来源必须为分支范围，不代表已实现 AI 摘要 |
| `suggestion` | 待审建议；本轮没有执行 AI 提取 |
| `fictional_state` | 虚构情绪、信任等；聊天来源必须为分支范围，不修改百科 |
| `world` | 仅引用用户显式关联的世界书条目；不自动读取整本世界书 |

范围为 `character`、`session`、`branch`。共享记忆必须由用户明确选择。分支记忆只在锚点节点及其后续可见，兄弟分支和其他会话不会继承。来源记录消息创建身份、内容 SHA256、会话/分支指纹、位置和最多 300 字证据片段；完整消息仍留在原消息树。

所有新记忆为 `pending`、`allow_injection:false`。确认与允许引用需要显式操作。编辑内容重新待审；拒绝、冲突、停用会撤销引用许可。解决冲突不会自动恢复许可。恢复旧内容追加新版本，并重新待审。来源被删除、改写或重绑后，保留档案和旧证据，停止召回并提示审核。

素材来源同时核对素材库已登记的内容Hash；声线来源核对voice_key/语言/有效参数、模型UID和登记版本，个人评分和备注不构成失效原因。不在每次召回时重新读取大型原件，外部文件变化仍需既有扫描/诊断更新登记；不据此声称验证了模型真实音质。停用世界书条目会停止相关记忆召回。

本轮冲突是人工标记，不是自动语义判断。不会从私人聊天自动挖掘现实敏感信息。

## 本地检索和预算

复用 SQLite FTS5 trigram 及既有短词 LIKE 转义规则；记忆使用独立的 `soul_memory_index`，防止待审或角色私有内容落入全局搜索。索引与数据写入同一事务，可重建。短中文关键词、引号、百分号与下划线按字面处理。

先在 SQL 内按 Soul、有效审核/许可/冲突及会话/分支筛选，再按固定、重要度、更新时间和 ID 排序；最多检查 200 条候选。每条再次验证来源身份，结果最多 30 条，默认 8 条。字数预算默认 4000，上限 12000，包含 `[memory:UID]` 和换行；只纳入完整条目，超预算不截断为半句。固定也不能越过范围、来源或预算。

召回给出引用、版本、来源、选择原因和 `sent_to_ai:false`。这不是 token 精确计数，也不是已经拼装的聊天请求。未来接入顺序：角色/system → 世界书 → 场景 → 已确认相关记忆 → 完整问答单元 → 当前输入；必须在同一个 #66 预算器下检查，不能通过记忆挤掉必要设定或当前请求。

单个身份当前上限 200 条显式关联；列表默认 25/50 条身份、30 条记忆，API 上限 100；来源消息预览上限 50 条。分支检查用一次递归 CTE，仅投影 ID/parent/session，预算 5000 节点；异常、循环、缺父节点和跨会话路径拒绝。不是整树装载。

## API 与历史

- `GET/POST /api/souls`，`GET/PATCH /api/souls/{id}`：分页、字面搜索、独立或世界观身份。
- `GET /{id}/candidates`、`POST /{id}/links`、`PATCH /{id}/links/{link}`：显式关联与停用，提交时重验范围。
- `GET /{id}/source-messages`：已关联会话的有限分支原文证据。
- `GET/POST /{id}/memories`、`GET/PATCH /{id}/memories/{memory}`：分页/类型/审核筛选、编辑与审核。
- `POST /{id}/recall`：本地预览，不联网。
- `GET /{id}/export?after_id=...&limit=100`：按稳定 ID 分页导出当前记录，返回下一页游标；完整历史使用整库备份。
- 原有 `/api/versions/{kind}/{id}` 支持 `soul`、`soul_link`、`soul_memory`，不可变快照和恢复继续复用 EntityVersion/VersionBlob。

写入使用 `BEGIN IMMEDIATE` 与 expected_revision；历史恢复另有 expected_latest。恢复不允许改 UID、Soul、来源或范围，失效目标不能恢复到复用 ID。恢复 revision 单调递增，旧页面不能靠恢复绕过并发保护。

**停用、删除历史、清除既有备份是不同操作。** 当前只有可恢复的停用；不提供不可逆清除或声称从备份中抹去内容。

## 数据升级、备份与性能

仅新增三张元数据表及可重建 FTS 表，不改旧业务表或文件。既有启动前 SQLite 一致性快照会发现缺表并先备份，再执行 create_all。完整备份包含身份、关联、记忆、不可变版本及 FTS；白名单明确识别这些虚拟表及影子表。隔离恢复仍只产生新目录，不替换活动资料库。

旧程序不认识这些新表时会安全拒绝读取，不应降级旧二进制去打开已经升级的活动库；需要使用包含本功能的版本或在独立目录验证升级前备份。没有将个人库用作迁移测试。

可重复测量：`PYTHONPATH=backend python backend/tools/benchmark_soul_memory.py --output <不存在的隔离目录>`。工具拒绝已有目录，不使用个人数据；7 次顺序 ASGI 测量，见 [验收记录](audits/soul/ACCEPTANCE_20261109.md)。索引 EXPLAIN 有证据使用既有 soul_id 索引，没有新增猜测索引。压测种子不包含每条历史成本，不能代替生产库或真实浏览器/GPU/RSS 测试。

## 后续

1. 完成 #66 的合法 GUI 验收后，再接入统一上下文预览和完整轮次预算。
2. 显式开启的 AI 建议提取、来源范围/发送预览、人工批量审核。
3. 公共群聊场景记忆与角色私有记忆分离，有限轮次调度另立 PR。
4. 角色卡/Voice/小说已审核人物的更直接导航，以及更大关联列表分页。
5. 语义冲突、可选向量适配和经过用户确认的摘要；默认不启动外部推理。
6. 未来按明确范围提供历史/备份清除工具，不能混同停用。

Voice、Live2D 许可/渲染/面捕、OC/LoRA/Krita/数位板、小说/世界观、3D、游戏/音声/特典、大库和 Windows 安装/签名更新的长期规划不变。
