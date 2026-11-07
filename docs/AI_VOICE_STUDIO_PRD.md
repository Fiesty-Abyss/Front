<!-- Original planning document preserved below. Implementation status is separate. -->

> 2026-11-07入库：用户提供原始规划草案v1.0。原文件名`Front_AI_Voice_Studio_PRD_2026-10-26.md`，原始字节SHA256为`8f83c477779a0301d94dde6e150dcc4891e304a5170fb249634fd1bf990f14c0`。正文保留规划时的目标与安全约束；其中引擎版本、许可、历史进度及给Agent的交接语句是文档内容，不替代最新用户授权或证明功能已实现。
>
> 本轮实施顺序以最新任务书为准：基础档案→角色对白→协议/Mock→有声小说；真实引擎/训练/硬件与安装验收另行开展。引擎API和许可在适配前按锁定的官方版本复核。本次入库仅文档，Voice代码尚未提交；状态和复用证据见[状态表](audits/voice/FOUNDATION_REUSE.md)。

# Front AI Voice Studio — 产品需求与开发实施方案

版本：规划草案 v1.0（2026-10-26）  
目标仓库：`Fiesty-Abyss/Front`  
状态：**仅规划，未实施；不代表已发布功能**

## 0. 项目定位与边界

把 AI Voice Studio 建成 Front 的一等创作模块，以“角色 → 台词/小说 → 声线 → 生成 → 审听 → 再生成 → 入库/导出”为闭环，兼顾：角色配音、批量有声小说、现成声库、授权零样本克隆、后续本地训练。

**不做**：从零训练基础 TTS 大模型；把 PyTorch/CUDA/权重加入 Front 默认安装包；重建第二套音频素材仓库、角色百科、阅读器、任务队列；在用户未授权时上传原文/音频到云端；宣称不同 TTS 引擎拥有一致的情感和音素控制。

**现有基座**：Vue 3 / FastAPI / SQLite / Tauri 2；Asset、Audio Library、OC、Character、小说、AI Provider 设置、有限且持久的后台队列、备份与恢复、懒加载。2026-10-25 交接报告中 v0.7 的签名更新代码与包校验已有阶段性成果，但真实安装/升级/签名上线仍待验证。因此语音 PR 独立排期，不能阻塞或夸大 v0.7 的交付。

## 1. 目标使用者与核心流程

### 1.1 角色配音

1. 在角色百科或 OC Studio 打开「声音」分栏，创建 Voice Profile。
2. 选择现有声库/模型，或绑定用户有权使用的参考录音；声明用途与授权来源。
3. 输入一句或批量台词、设置语言、说话风格/速度（引擎能力允许时）；试听并选最佳版本。
4. 生成 WAV 或可选 MP3；产物登记进既有 Asset/Audio Library，关联角色、作品、项目；支持导出对白、字幕、元数据。
5. 声线可一人多款（不同年龄段/形态/语言/场景）；删除或换模型不静默覆盖历史成品。

### 1.2 有声小说

1. 从 Front 已有小说/章节引用正文，不批量复制源文件，也不自动发送给云端。
2. 默认采用规则分段：章节 → 旁白、对话候选、段落；AI 分角色只作可确认建议，保留原文偏移和来源哈希，禁止无审阅强制覆盖。
3. 将段落中的说话人映射到 Character 或 Voice Profile；旁白可指定独立声线；对白归属未知时标记「待确认」。
4. 可修改朗读文本，但原文保持不变；维护“原文 / 读音文本 / 发音词典”分层。
5. 分片合成，失败只重跑该片；支持试听、替换、批量导出 WAV/MP3 + SRT/VTT + 章节/合订音频。
6. 支持章节断点、预计/实际时长、完成量和失效提示；可关联 Audio Library 的专辑、书签、续听。

### 1.3 零样本克隆

1. 用户明确上传、选择或引用已授权的参考音频；录音只作为参考资产保留。
2. 系统校验格式、时长/采样率、单一说话人建议、静音/削波；必要时提出“参考文字/转写缺失”提示。
3. `Voice Profile` 区分 **reference-based zero-shot** 与 **trained checkpoint**；不把一次推理生成称作“训练了模型”。
4. 同声线不同引擎的音色一致性不保证；用户可 A/B 试听并保存偏好。

### 1.4 本地训练（后续阶段）

数据集创建 → 原地索引录音 → 授权声明 → 录音切片 → 可选离线 ASR → 文本人工校对 → 清洗/QC → 划分训练/验证集 → 训练/微调 → 监听日志和取消 → 测试句评估 → 注册新模型版本 → 明确选择发布到该声线档案。

训练失败不能损坏源录音、现有声库或 Front 数据库；任何清理仅针对 Front 创建的专属临时目录。

## 2. 页面信息架构

新路由 `/voice`，独立异步 chunk，建议包括：

- `Voice Studio / 工作台`：快速合成、多版本试听、任务状态、最近项目；未配置引擎也可管理文本和声线档案。
- `Voices / 声库`：声线卡片、语言、引擎、模型版本、试听样本、授权标签、角色关联、只读原路径、缺失文件诊断。
- `Projects / 配音工程`：角色对白、长篇小说、广播剧；项目包含段落列表/章节导航、声音映射、预览/合成与审听状态。
- `Editor / 台词与时间轴`：MVP 采用段落编辑 + 单片试听；高级版才做多轨波形、裁剪、停顿、背景音乐和拖拽排布；避免一次做 DAW。
- `Datasets / 数据集`：仅到训练阶段启用；来源授权、录音预览、切片和转写校对。
- `Training / 训练中心`：环境自检、参数/预算/资源估计、开始/暂停(若支持)/取消、日志、检查点与版本。
- `Settings / 引擎与输出`：连接/能力探测、任务并发、数据根目录、GPU 策略、隐私与云端开关、默认导出格式。

建议角色/OC 详情额外加「声音」分栏，小说阅读页可通过明确操作「创建语音项目」，但不改原页面的核心职责。

## 3. 统一适配器架构

```
VoiceStudio.vue / VoiceProjects.vue / VoiceEditor.vue
             │ Front FastAPI REST + Auth
             ▼
VoiceService ─ VoiceProjectService ─ existing jobs/Asset/Version/Backup
             │
             ▼
TTSAdapter Registry & Capability Negotiation
      ├── GPTSoVITSAdapter        [首个真实适配器]
      ├── CosyVoiceAdapter        [第二轮]
      ├── IndexTTSAdapter         [后续]
      ├── F5TTSAdapter            [后续]
      └── CloudTTSAdapter         [按明确配置启用]
             │
      localhost remote API / child service / HTTPS authorized provider
```

建议 adapter 契约（伪接口）：

- `health() -> Health`: 可达、版本、就绪、错误信息。
- `capabilities() -> Capabilities`: `languages`, `zero_shot`, `trained_voice`, `training`, `batch`, `streaming`, `emotion`, `phoneme`, `speed`, `pitch`, `speaker_id`, `sample_rates`, `output_formats`。**每项来自真实适配器能力探测，不猜测**。
- `list_voices()`, `validate_voice(voice_ref)`：获取声线/模型元数据和可用性。
- `synthesize(request, cancel_token) -> streamed/file output`: 请求必须记录引擎、版本、声线、参考素材、文本、规范化设置、可用参数；所有参数在适配层验证。
- `prepare_dataset`, `train`, `list_checkpoints`: 训练能力单独契约，未支持则不可点击。

前端只消费统一能力描述；不要把 GPT-SoVITS 固定字段写进共享 Voice 页面。浏览器不直连未知第三方 TTS URL，通过 FastAPI 受控代理或 adapter 交互；禁止用户任意地址经后端读取本机/内网服务。云端调用先显示数据范围与成本，用户明确授权后执行。

### 3.1 引擎选型

- **P0 GPT-SoVITS**：中文/日语等角色声音、参考录音、后续微调；官方有 `api_v2.py` 和 WebUI。先验证选定版本，再锁定适配器所依赖的接口版本。
- **P1 CosyVoice 3**：多语言、零样本/跨语种、自然旁白；当前官方源为 `QwenAudio/CosyVoice`。注意安装环境与首次加载成本。
- **P2 IndexTTS 2.5**：情绪/发音/语速等可控性；其独立 Bilibili Model Use License 需要人工核查。
- **P2 F5-TTS**：零样本与 fine-tune 研究用途；代码 MIT，不代表官方预训练权重可商用（后者 CC-BY-NC）。
- **可选云端**：用户提供 API Key 与计费确认；预设云端不改变本地优先策略。
- **ACE Studio**：仅保留外部歌唱工程链接/音频文件导入设想；截至规划日其官网说明不提供常规 TTS，公共 API 尚未开放，不以其声库可直接调用为设计前提。

## 4. 数据模型（建议的新表；先检查现有实体避免重复）

- `voice_providers`：id、adapter_type、name、service_endpoint、enabled、capability_snapshot、version、last_check；密钥复用现有保密配置，不在新表明文复制。
- `voice_models`：id、provider_id、kind(`tts/voice_clone/finetune`) 、external_model_ref、engine_version、fingerprint、license_code、origin、size、capabilities、missing/ready。只登记模型文件原路径，非用户确认不复制。
- `voice_profiles`：id、display_name、character_id(nullable)、oc_profile_id(nullable)、provider/model_ref、mode(`preset/zero_shot/trained`)、reference_audio_asset_id、reference_transcript、language、auth_source、usage_scope、model_version、created_at。与角色仅“引用”，不覆盖角色百科。
- `voice_projects`：id、kind(`dialogue/novel/drama`)、source_asset_id/reader_chapter_id、world_id、title、revision、default_voice_id、narrator_voice_id。
- `voice_segments`：id、project_id、stable_order、chapter_ref、source_span_start/end、source_hash、original_text、spoken_text、speaker_ref/voice_profile_ref、controls_json、revision、review_state。
- `voice_renders`：id、segment_id、request_fingerprint、provider/model/voice snapshot、audio_asset_id、duration、sample_rate、job_id、status、created_at、accepted；同一片允许多个版本。
- `voice_datasets` 与 `voice_dataset_items`：id、原始音频Asset引用、转写、时间片、授权、校对状态、质量标签、训练/验证划分。
- `voice_training_runs`：dataset_id、adapter、base_model、config_snapshot、status、checkpoints、logs_ref、metrics、duration、resource_peak。

无必要时不另建 `voice_jobs` 表；优先使用 Front 已有持久化任务账本，以独立 `voice.*` 类型区分。所有模型/声线/段落/渲染使用稳定 ID；模型/参考音频/原文变更通过 fingerprint 和版本号让相关合成结果标为「过期」，**但旧结果仍可试听，不自动销毁**。

保存音频应使用 Asset/托管文件机制，渲染只维护关联；一个文件被多个段落/项目引用不重复拷贝。默认训练权重/外部录音只做只读索引，并在备份页面明确说明“外部原件默认不随备份复制”。

## 5. API 合同草案

接口前缀建议 `/api/voice`，实际以仓库当前 router 风格为准：

- `GET /capabilities`：列出 Front 支持能力与已连接引擎能力。
- `GET /providers`, `POST /providers/test`：连接状态，校验 localhost / HTTPS 目标白名单及凭据管理。
- `GET /models?provider_id=...`, `POST /models/index`：查找、登记模型（默认只读）。
- `GET /voices`, `POST /voices`, `PATCH /voices/{id}`：声线档案。
- `GET /projects`, `POST /projects`, `GET /projects/{id}`：分页项目。
- `POST /projects/{id}/segments/import`, `PATCH /segments/{id}`：原文、候选分段、发音稿与审校。
- `POST /renders`：启动单片或多片合成；返回 HTTP 202 + `job_id`；请求携带幂等键，避免双击重复生成。
- `GET /renders/{id}`, `POST /renders/{id}/accept`：试听候选和采纳版本。
- `POST /projects/{id}/exports`：导出，生成后复用 Asset 与任务下载。
- `POST /datasets/{id}/validate`, `POST /training-runs`：训练阶段才开放。

进度查询和取消复用现有 jobs API；如果没有可靠事件推送，先限频轮询，不另上 WebSocket 基础设施。合成参数在后端做 schema 校验、大小限制、速率控制。大请求分片入队，前端不直接上传整本小说给一个推理 API。

## 6. 长篇配音管线

1. 章节引用/文本解析（保存源哈希及字符位置），应用文本正规化，但保留原文展示。
2. 分段：优先标点+段落边界，控制单片字符/音频时长上限，避免错断姓名、引号、外语；提供人工合并拆分。
3. 可选“谁在说话”智能建议，任何不确定片段待审；不把大模型推测身份写回正式人物百科。
4. 映射 Voice Profile（角色、旁白、未知默认声线），保存句级 voice snapshot。
5. 生成任务含 idempotency key；仅按能力支持的控制项传给当前引擎；并发 1 个 GPU 推理任务为保守默认（用户配置后可调整）。
6. 合成音频先写临时文件，校验持续时间/编码/大小/哈希，再原子提交为 Asset；任务完成必须可追溯 model/version/reference/prompt。
7. 分片失败保留已完成分片；取消停止新任务，受控终止**自己启动**的引擎子进程，不根据进程名杀掉用户已有服务。
8. 章节导出时由被批准的转码/拼接器把片段顺序合成，插入可配间隔，生成 SRT/VTT 片段时间轴与 JSON 元数据；对齐到词/字的时间轴只在具备真实强制对齐模型后开放。
9. 本地采纳版本可以重用，改变一句话只重合成对应句，不强制重跑整章。

### 6.1 关于音频编辑

MVP **不要**开发完整多轨 DAW。优先“段落列表 + 单片波形预览 + 采纳版本 + 章节序列 + 简单停顿”。后续才扩展波形拖拽、多声道混音、音量标准化、EQ/降噪、背景音乐轨和自动对齐。特效处理依赖可选 FFmpeg，不悄悄更改用户原始音频。

## 7. 训练工作台的隔离策略

- 训练是 optional feature，不出现在默认 Front 依赖里；必须有已安装/已配置的引擎专用环境。
- 一模型一隔离环境或对应引擎服务；不混装到 Front 的 Sidecar Python 环境；不要污染其固定依赖。
- 由引擎 adapter 公开可验证的硬件检查（CUDA/设备/可用显存、磁盘预算等）；不能用“有 GPU”当作“任何训练都支持”。
- 数据集与模型版本不可覆盖；训练产物写入隔离目录，成功才注册新版本；暂停只有引擎真实支持时才显示。
- 自动切片和 ASR 需用户复核、允许撤销；保留合法来源与许可说明，避免训练无授权人声。
- 日志/失败诊断不包含原始音频、密钥、小说全文、用户私有路径；训练残留和缓存设置最大空间预算和清理确认。
- 不自动下载大模型，展示权重大小、许可证和下载来源，经用户确认后操作。训练失败/崩溃后 Front 本体依旧可打开。

## 8. 权限、隐私和安全要求

- 录音克隆须确认上传人有权使用该声音；第三方声库保留来源、可使用范围和授权证据。不提供伪造身份或绕过许可的工作流。
- 本地推理默认 `127.0.0.1`；URL/端口须经校验，外部服务明确显示；避免 SSRF、路径穿越、读取非授权本机文件；调用时以 Front 既有 cookie/session/Origin 保护和可配置超时为界。
- 推理引擎为外部软件，不能纳入 Front 自有进程自动清理，除非由本次 Front 会话明确启动且进程所有权可验证。
- 文本/参考音频/权重不进入遥测、Git 仓库、日志或公开截图；Mock 和真实合成结果在报告中明确区分。
- 许可证区别：引擎代码许可、预训练权重许可、第三方声线许可、参考录音权利、生成音频使用条款；不能以“开源”一概而论。
- 云端 API 调用对用户显示：上传内容类别、提供商、语言、计费和失败重试可能产生费用；默认不开启自动上传。

## 9. 逐 PR 路线图（基于已合并 main 的独立分支）

| 阶段 | 建议 PR | 交付范围 | 关键验收 |
|---|---|---|---|
| A | `voice-01-foundation` | 文档、数据表迁移、安全备份、数据模型、能力协议、Mock adapter、/voice 空态与声库管理 | 无引擎可保存档案；升级前备份可恢复；回归旧功能 |
| B | `voice-02-first-tts` | GPT-SoVITS 真实 adapter、单片 TTS、零样本参考音频、采纳候选、结果入 Asset/Audio | 真实授权样本生成 WAV；错误断连/取消/重复提交可靠 |
| C | `voice-03-dialogue` | 角色/OC 关联，多声线版本、批量对白、导出字幕、差分重生 | 改一条台词只重生受影响片段；历史版可恢复 |
| D | `voice-04-audiobook` | 现有小说引入、分章/待确认说话人、旁白与对白映射、队列与章节导出 | 1000片生成样本的分页/取消/恢复；真实小章听读验收 |
| E | `voice-05-multi-engine` | CosyVoice adapter 和可选云端 provider、能力协商、A/B 质量比较 | 模型不同能力不会出现无效控件；云端需确认和费用提示 |
| F | `voice-06-datasets` | 数据集、录音切分、ASR 可选、人工校对、质量报告、授权字段 | 数据源哈希不变；错误恢复和重新索引不重复复制 |
| G | `voice-07-training` | GPT-SoVITS 训练适配器、隔离依赖/进程、指标/检查点、训练后模型登记 | 真实授权训练与中断恢复可核；Front 桌面无需 GPU 依旧可运行 |
| H | `voice-08-polish` | 按实际需求加 IndexTTS / F5-TTS、时间轴/混音、发音词典和综合性能优化 | 兼容与真实资源回归达标，再讨论正式发布 |

每个 PR 必须：检查远端 main/PR/CI → 建独立分支 → 新建/迁移表前完整备份与隔离恢复 → 单元+API+前端测试 → 生成/Mock 与真实测试分别标注 → 桌面1440px/390px/UI无横向溢出 → Windows 构建/Sidecar 不含模型权重 → 普通合并，不强推 main。

## 10. MVP 的精确定义

**MVP = A+B+C 的小范围闭环，不含长篇自动配音与本地模型训练**：

- 使用现成或用户授权参考音频在本地生成一句/一组对白。
- 绑定角色声线；输出可试听、比较、采纳、打标签、放进 Audio Library。
- 显示引擎和声线状态/能力；无引擎可管理档案。
- 数据可备份与恢复；生成任务可取消、失败可重试；模型文件只读，不另复制。

完成 MVP 后才进入完整长篇批量处理、自动角色识别、训练界面和音频制作高级工具。这样真正形成使用价值，而不是一堆装饰性按钮。

## 11. 测试与质量门槛

- 功能：角色一对多声线、零样本 vs 训练模型区分、台词修订/并发冲突、段落重排与读音稿修改。
- 内容：中文、日语、英文、混合语种；引号/破折号/括号、数字、角色姓名、长句/空串/特殊符号、跨章节。
- 耐久：1000段批量任务；重复发起、部分成功、取消、重启、磁盘满、坏 WAV、模型丢失、音频路径变更、服务断连。
- 质量：真实音频必须由真人听审，不以 mocked 文件或 API 200 证明朗读自然；字错/漏/吞、参考相似度/情绪表现与速度由试验记录，做模型对照。
- 性能：关闭 `/voice` 不保持 GPU/第三方服务常驻；音频长列表分页/懒加载；记录 idle RAM、峰值 RAM、GPU 显存、首片延迟和 10 分钟/1000段混合测试。
- 安全：无授权不上传、旧资产原件哈希不变、路径与 URL 校验、任务权限隔离、进程清理只影响自有服务、升级失败可恢复。
- 兼容：Web 与 Tauri 2 同业务逻辑；Windows 便携/安装分离存储，后端 Sidecar 不携带大型声库或深度学习环境；无 TTS 引擎、无 GPU、断网情况下 Front 核心功能正常。

## 12. 不依赖开发的问题清单

正式编码前明确：

- 当前机器可用 GPU、显存、存储空间、Windows 与 Python 运行环境（决定真实模型可否跑、选何种量化/设备）。
- 已有 GPT-SoVITS 等引擎是外部独立部署还是需要可选安装引导（禁止偷偷安装）。
- 是否需要商业使用和公开分发？会影响声库与预训练权重许可。
- 用户拥有哪些可授权的参考录音和测评文本？没有就以合成测试音频、用户自录及许可明确的示例验证。
- 发布计划：Voice Studio 独立功能分支先开发，在桌面版已通过真实安装/升级门槛前，不让其影响正式发布。

## 13. 给 Codex 的执行交接要求

> 请先只读核验 `Fiesty-Abyss/Front` 的最新 origin/main、当前开放 PR、CI、`docs/NEXT_SESSION.md`、`docs/V07_PROGRESS.md`、`docs/AUDIO_LIBRARY.md`、`docs/OC_STUDIO.md` 和任务/Asset/Provider 的真实源码，列出 A 阶段复用表/路由/函数与新建位置。不得从历史 SHA 直接开发或假定旧文档仍最新。
>
> 只实施 `voice-01-foundation`，不要连带实现 GPT-SoVITS 训练或替用户安装依赖。要求新 `/voice` 懒加载页面、SQLite 可追踪迁移、VoiceProvider/VoiceModel/VoiceProfile/VoiceProject/VoiceSegment/VoiceRender 基础关系、能力协商协议、Mock adapter、只读声库导入与缺失资源诊断、稳定分页、严格身份/路径检查、完整备份及隔离恢复测试。新模型权重和音频原件只登记、默认不复制。公开仓库不得含真实用户数据、模型、密钥。后端/前端/Windows 回归通过后开独立 PR，说明 Mock 与真实未验范围，不自行宣称正式发布。

## 14. 参考资料

- Front 仓库： https://github.com/Fiesty-Abyss/Front
- Front audio 文档： https://github.com/Fiesty-Abyss/Front/blob/main/docs/AUDIO_LIBRARY.md
- Front OC 文档： https://github.com/Fiesty-Abyss/Front/blob/main/docs/OC_STUDIO.md
- GPT-SoVITS： https://github.com/RVC-Boss/GPT-SoVITS
- CosyVoice 3： https://github.com/QwenAudio/CosyVoice
- IndexTTS： https://github.com/index-tts/index-tts
- F5-TTS： https://github.com/SWivid/F5-TTS
- ACE 官方声音功能： https://acestudio.ai/custom-voice/

**本文件是设计规划，尚未创建 GitHub PR、修改 Front 仓库或实际连接 TTS 服务。**
