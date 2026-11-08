# 最新接续 · 资料发现、匹配与角色卡 · 2026-11-08

## 精确基线与GitHub

- 开始main3309eda，#54–#61已合并；#62 head f3bd6d28cb045d2a109aecf02a6eb873d0923444，常规42458154437/Windows42458154440成功，正常merge47054ea9bb471d4e346fbbb406b8d61bece7bcdd。
- #63 head eeda2640c1df4276d2647ede26af9462968500ad，常规42461583921/Windows42461583955全部成功，正常merge **b84b856a9ca5ec4037c2fd68afb7ee7f505b4896**，这是本提交前最新fetch已验证main。
- 当前独立codex/card-workbench从该main开发，待精确head常规及Windows全部适用CI后正常merge；不强推、不绕保护、不发布Release。合并后fetch实际main再开新分支。

工作树`.cache/worktrees/card-workbench`；root checkout仍旧3aaa9e1，用户安装和个人库没有替换或升级。CLI GitHub写权限可用；无账号/网络权限改动。此前A/B工作树voice-acceptance保留，勿删未合并工作/他人stash。个人资料/原始模型不改动。

## 本轮已交付与实际范围

- A多根配置、稳定UID/版本、安全有限扫描、暂停续扫/增量候选、人工归档，复用Asset/ProjectPreview/jobs。506后端/1权限跳过、15前端与构建，生成9项及1200TXT实际GUI/390px/续扫/重启/Hash保护，#62全CI成功。[范围](DISCOVERY.md)/[验收](audits/discovery/ROOTS_20261108.md)。不是全盘监控、语义归属或自动模型复制。
- B显式联网中心、游戏/书籍/Hash候选、Work/Galgame字段来源/人工保护/事务/版本；修复FD误匹配/手工封面刷新。521后端/1权限跳过、15前端与构建，生成Mock GUI与公共Open Library真实search/detail分开，#63全CI成功。[范围](METADATA_CENTER.md)/[验收](audits/metadata/CENTER_20261108.md)。ISBN/Edition/语言/动漫/作者详情、Google/NextMoe、统一模型写历史及自动跨来源补全未完成。
- C增强既有角色卡，分页摘要/独立与OC/百科草稿、设计收藏字段/封面/世界书、兼容JSON/PNG、指纹事务/不可变历史、明确服务/发送范围的AI候选与人工采用。一张加法候选表，无第二套人物库/推理依赖。最终534后端/1权限跳过166.32秒、18前端与构建6.54秒；生成GUI/390px深浅、导入/失败/取消/恢复5历史/重启保留4卡3候选3素材、世界隔离及隔离备份恢复。真实AI/封面自动生成/小说直接转卡未完成。[范围](CHARACTER_CARD_STUDIO.md)/[验收](audits/cards/WORKBENCH_20261108.md)。

C真实发现并修复别名输入丢失、别名FTS缺失、旧poll覆盖worker ready、时区时间戳往返指纹。一次最终批次1失败后新增确定性CAS回归，修复后全量如上；不要引用失败批次作通过。已有外部扩展历史索引需显式重建，本轮只重建专属生成库，不自动大规模重建个人数据。

## 本地隔离服务与证据

A/B专属生成实例`private/discovery-20261108-v2`已经认证关闭；2根/5素材/1作品/5历史及十生成源Hash保留。勿把旧NEXT的“仍运行”当现状。

C仅生成标记实例`private/cards-20261108-v1`，私有control.json保存自身PID/随机端口/令牌，不打印/提交。`.cache/card_acceptance.py restart/stop`必须先核对标记和实例归属，禁止对个人8000或按进程名广杀。最终重启验证后已认证关闭自身服务，control记录stopped=true。真实模型从未调用；provider明确非真实AI，MockTransport不是语义质量证据。

仅公开docs/screenshots/cards里的生成内容；实际API导出文件经校验，浏览器下载目录未验。最终正常console error0、audio/canvas0，viewport重置。初始JS216.96kB/gzip83.44，Cards21.32/8.58、按需CardAssist7.54/3.79；不能代替整机CPU/RSS/Heap/GPU/冷启动或泄漏测试。无真实Tauri窗口/干净Windows/个人资料迁移。

## 下一步准确顺序

1. 对当前C最终head提交PR、附报告，检查普通/Windows全CI、冲突与保护；只在全部成功且head未变时普通merge。记录准确PR/run/merge，再fetch main；PR合并不是用户软件发布。
2. D从现有ChatSession/ChatMessage消息树、provider/context/lorebook细审，保留已有编辑/重生/分支。按独立PR补会话/逐角色模型参数快照、有限群聊调度、旁白与选项分支，避免简单拼角色System或无限轮次。不默认启Voice/Live2D/3D；Mock与真实推理分别记录。
3. E现有Tauri已随机端口/令牌/自身Sidecar/写锁/退出保护，补原生目录选择和统一设置/安全外链。不要替换用户安装、切个人活动库或改Web8000；真实窗口/干净安装仍须单验。
4. F锁定Bandori源码见[研究记录](research/CREATIVE_REFERENCE_20261108.md)。Neocari实际gitlink5ef8f49654e2cdfeb60dbbdca28c1159558da775，GPL3-only且描述CubismV2，不误认Moc3通用运行时。只自行实现有界渲染器协议/动作及无模型生命周期原型，不复制GPL/专有SDK，不因隔进程就保证许可兼容。
5. B ISBN/版次/语言/更多来源和C自动封面/更完整小说证据转卡后续独立增量，不把未做标已做。

## 不丢失的长期方向

#54–#61真实范围见[audits/voice/ACCEPTANCE_20261108](audits/voice/ACCEPTANCE_20261108.md)：原个人DB/WAL/SHM当时Hash保持、隔离升级/恢复通过；历史错误准确旧包仍未知，不能重置。本轮未再次打开个人数据库。

Voice真实TTS/实际权重/授权声音/质量延迟、数据集/切片/校对/训练预算、分片续拼/MP3；Live2D真实渲染/快捷动作/道具/面捕与玄宝酱用途署名/SDK许可；Krita/笔刷/数位板、真实SD/ComfyUI/OC、小说语义、3D、游戏/音声/特典、大型素材、插件、干净Windows/正式签名/Release审批持续保留。不索取夜间密钥、不自动付费/下载权重/接受协议。
