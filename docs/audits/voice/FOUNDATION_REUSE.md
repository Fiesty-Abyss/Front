# Voice Studio接管、功能状态与复用边界

2026-11-07；基线main `3aaa9e1731185046bee1f26a7eef1119514f8e33`，无开放PR，main CI [42355716567](https://github.com/Fiesty-Abyss/Front/actions/runs/42355716567)成功。已按仓库树、源码、测试文件及既有审计交叉核对；下表不是本轮重新跑过全部真实环境的声明。

状态：**证据实现**=已有源码和对应回归；**缺陷**=已定位源代码问题、仍待独立回归；**部分**=边界内可用，仍有缺项；**生成/Mock**=验证范围而非真实AI质量；**设计**=文档存在但未有代码；**未开发**=入口/模型/实现未出现。

| 模块 | 状态与证据 | 本轮复用与限制 |
| --- | --- | --- |
| 素材/索引/预览 | 证据实现、部分；assets/ingest/projectpreview、test_search_assets/test_project_archive | 复用Asset/文件流/缩略图；格式支持依FILETYPES，不因有封面称完整专业编辑 |
| 收藏/标签/评分 | 证据实现；collectionpages及test_collection_pages，10k/50k/100k报告 | 复用Tag和Asset；语音引用同一音频，不复制文件；旧完整API仍无界 |
| 音声收藏/播放器 | 证据实现、部分；routers/audio、AudioPlayer、test_audio_library | 复用音轨Range、进度/字幕/波形；编码降级和压缩波形/转码仍待 |
| 后台任务 | 证据实现、部分；jobs.Manager=2worker+32排队，SQLite账本，test_foundation/test_mixed_benchmark | 已持久化历史；重启queued/running转interrupted，不自动重发收费/推理请求，不宣称所有任务自动续跑 |
| 版本/完整备份 | 证据实现、部分；versions/backups、test_versions/test_backups | 不可变快照/恢复追加；托管文件备份及隔离恢复；不在线覆盖当前库，不默认复制外部原件 |
| 笔记 | 证据实现、部分；routers/notes、crud.make_crud_router、test_v061_notebook | 纠正接管误判：通用CRUD已捕获过滤器ValueError/OverflowError并返回422；不能把该处认定为500。move及普通PATCH的树约束另作验证 |
| 小说章节 | 证据实现、部分；chapterplans、test_chapter_plans | 复用确认目录、原文Hash/区间；朗读稿独立，单次只取选中章/分页片段 |
| 世界观/角色/百科 | 证据实现、部分；encyclopedia/extractionreview、隔离/证据测试 | 稳定ID与created_at身份；禁止同名跨世界合并；真实AI语义冲突仍待 |
| OC档案 | 证据实现、部分；ocstudio/routers/oc、test_oc | 角色/造型/引用/版本已存在；声线只引用OC，不另建百科 |
| 图像生成/学习 | 部分、生成/Mock；ocimages/ocdrawing、对应测试 | 手动管理/派生图可用；真实生图质量与硬件未验 |
| 游戏/特典/画布/角色卡 | 证据实现、部分；对应router及test_bonuses/test_v062_diagrams/test_v063_galgame/test_cards_ai | 保持现有职责；平台元数据、DRM/授权和外部工具边界不变 |
| Live2D | 档案证据实现；渲染/面捕未开发，LIVE2D_STUDIO | 无Core/追踪引擎初始化；第三方SDK和素材许可仍待 |
| Windows/Updater | 部分、生成包/真实SDK证据；preview.2、RC报告 | 包已构建；干净系统安装/真实更新回滚、正式签名feed尚未验收 |
| Voice Studio | 部分实现；/voice、voicestudio、test_voice_studio | 三类档案/试听引用/历史；六表中工程、片段、生成表仅预留；CI结果以对应PR为准，无真实TTS |
| 零样本克隆/训练/高级时间轴 | 仅设计、未开发 | 不自动下载权重/安装训练环境；未经授权录音不创建克隆任务 |

## 新模块落点

- 模型：现有models/Base注册六表VoiceProvider/VoiceModel/VoiceProfile/VoiceProject/VoiceSegment/VoiceRender，外部文件只登记；真实凭据复用AIProviderConfig引用，输出音频只存Asset。
- 业务：voice服务负责身份/归属/指纹/并发；router只协调。Provider配置不自动联机，能力未知明确显示未检测，Mock来源独立标记。
- 前端：main.js增加动态import `/voice`，共享导航/AssetPicker/AudioPlayer/VersionPanel。档案与工程分页，入口不加载TTS/训练/播放器实例。
- 历史：扩展既有versions实体注册及恢复校验，模型/角色/OC/参考音频保留身份快照；引用删除/ID复用不得静默换成新资源。
- 迁移：复用dbbackup.before_schema_change、Base与迁移账本；旧库新增表前备份、隔离恢复用生成样本验证，不触碰私人库。
- 任务：复用jobs；语音结果提交前校验请求指纹和关联身份，取消/中断后显式重试；收费/推理请求不自动回放。

## 本轮环境与验证口径

没有可运行的已保存Codex Cloud配置；GitHub集成写入403。用户随后允许读取本机PRD，现有CLI已确认仓库push权限；只在Front缓存暂存远程编辑载荷，通过GitHub API提交，Actions负责测试。不把此方式称为已启动Codex Cloud电脑。未启动本机Front/AI服务，不用个人小说/音频/模型测试，不执行本机GUI/硬件/安装验收。

文档PR不改变程序行为，沿用远程CI测试/前端构建；本轮新代码和回归结果在对应独立PR更新。真实TTS自然度、克隆相似度、训练、GPU、摄像头、数位板和干净Windows均待以后授权环境验证。
