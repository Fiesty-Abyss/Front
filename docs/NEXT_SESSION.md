# 最新接续 · 资料发现、匹配与角色卡 · 2026-11-08

集成 main812d239 后的最终本机验证：582后端通过/1权限跳过，172.44秒（bundle-integration-final.log）；18前端通过与生产构建6.41秒（bundle-integration-node/build.log）。这是已合并发现/匹配/角色卡/Null协议加本补丁的真实组合，不是各分支测试数相加。没有新增前端或应用运行时变化；远程CI须检查本merge head全部结果。

2026-11-08 收敛更新：#64 已在精确 head e222190d06fcc173594984c958e7063a2227830c 的常规 42473081686 与 Windows 42473081585 全成功后正常合并，最新 main **812d239a4c9ac2edb28f1ca8f110f4eb0c97de87**。Windows 实际生成 NSIS/便携包并通过独立完整性校验；不是正式发布或干净系统安装验收。角色卡集成 555 后端/1权限跳过、18前端与生产构建以及此前生成 GUI 均通过。#67 无模型协议已合并；真实渲染仍未完成。

当前 #65 普通 merge 该最新 main，仅处理文档冲突、保留双方历史，不强推。须重新执行本组合完整测试/构建和全部适用 CI。旧 head24816bad 的 Windows42469928847三次官方 NSIS 下载仍504，限次失败正确保留；#64与#67后续成功提供上游间歇恢复证据，不代表重试必成功。

#66 head8f1508678106a98517d50f923c64b8b0a2f361bd 仍为 Draft：常规42472069095成功，Windows42472069127在官方 NSIS ZIP 下载504失败；实际 GUI 启动组合被自动审批拒绝（blocked by policy），未执行、未绕过。群聊/剧情/选项模式、原生目录选择、真实AI与Live2D均不算完成。下方为历史时间截面，以本头和最新 GitHub 状态为准。

角色卡集成最终本机结果：普通合入main9a427b6（#67）后，555后端通过/1权限跳过172.41秒，18前端测试和生产构建6.51秒通过（card-main-integration/card-integration-node/card-integration-build）。角色卡已有生成GUI证据对应的前后端源码未改变，仅新增独立未初始化的协议与文档。新merge head仍须全部适用CI，旧#64 NSIS504记录不当通过。

2026-11-08集成收敛：#67无模型Live2D协议已正常合并main **9a427b6c76b8f8163b8408d4149693ea7addd2bb**，head bf43ff013fefc18ce045c0e69799b0e52e3d6ff3；常规42470955962尝试2和Windows42470955968全成功（安装器/便携/完整性，非正式发布）。当前#64普通merge该最新main，只发生文档头部冲突，保留双方记录；角色卡前后端源文件与已做生成GUI验收的f0ebf5aa一致，新增协议不在应用初始化链。旧#64两次Windows504仍保留，合并后的真正集成测试/构建和精确head CI必须重新执行，不能直接沿用旧结果。

当前工作树.cache/worktrees/card-workbench，#64在普通merge origin/main，不强推或重写任何已推送提交。源前后端与f0ebf5aa相同，只有新增独立协议和文档集成；接着先前端测试/构建，再全量后端，确认后完成merge commit并push，核对本head常规+Windows全部CI再正常合并。

#65 head24816bad：常规42469928766尝试2全部成功（Python310安装504重试后真跑兼容）；Windows42469928847实跑三次build，ZIP部分成功并验Hash，helper/ZIP仍交替504，最终非零失败，没有上传不合格包。没有修改镜像/版本或门槛，暂不重跑整个Windows直到有新的恢复依据。

#66最新源代码head8f1508678106a98517d50f923c64b8b0a2f361bd：534本机后端/1跳过、13专题/旧49联合专题、前端15与最新构建（Chat14.12kB/gzip5.99）通过。此head补失败后解除streaming再刷新、晚到/上下文顺序保护，真实GUI仍受自动审批拒绝而未验证，保持Draft；最新CI42472069095/42472069127以实际状态为准。其他旧head已因更新取消自己的过时Windows任务，不能把取消当当前检查通过。

上一原型分支的“停止前状态”和其他相同日期段落为当时快照，保留追踪；本头部优先。Main原型不等实际模型渲染，Card AI仅Mock/生成GUI，不等真实模型质量。B更多匹配、群聊/故事/选项、原生目录导航、Voice真实TTS/训练、Krita/数位板/真实生图/小说语义/3D/游戏音声与正式签名更新全部保留。自建测试实例均stopped=true，根旧checkout/个人安装/库/原始素材仍未动，不需要现在提供Key或接受许可。

## 精确基线与GitHub

## 2026-11-08 · 停止前收敛状态（Live2D协议分支）

截至本提交最新fetch main **b84b856a9ca5ec4037c2fd68afb7ee7f505b4896**，即#63；#62/#63精确head与成功CI见下文历史。根checkout仍3aaa9e1且clean，未升级个人安装/库。当前工作树.cache/worktrees/live2d-protocol，codex/live2d-renderer-protocol为独立分支，非其他未合并PR的堆叠基线。

### 已提交与CI门槛

- #62多根目录与候选归档、#63联网资料匹配均正常merge；#62常规42458154437/Windows42458154440、#63常规42461583921/Windows42461583955成功。范围和未完成内容见DISCOVERY/METADATA_CENTER。
- #64角色卡head f0ebf5aa95cebee738de7239f74ebf49ed2da5c8：534本机后端/1跳过、18前端/构建与生成真实GUI/390px/版本恢复/重启/隔离备份通过；常规42466429793成功；Windows42466429802尝试1/2分别因官方NSIS helper/ZIP HTTP504失败，未合并，不算完整Windows通过。没有无限重跑或门槛豁免。
- #65 codex/windows-bundle-retry，head24816bad14c16962277f62ffa92064d1aed2f921：27专题、548本机后端/1跳过、15前端/构建通过。常规42469928766的backend/frontend成功，但Python310在setup-python下载官方3.10.22 Linux26.04包时504，尚未运行兼容测试；Windows42469928847以实时结果为准。仅官方工具502/503/504有限重试，不更改签名/Hash/版本/镜像，不保证持续上游故障消失。
- #66 codex/chat-model-snapshots为Draft：模型/参数追加快照、预算/互斥/实际回复来源、安全错误/URL标签及草稿保留。最新534本机后端/1跳过199.12秒、13专题（旧49联合专题另记）、15前端/构建通过。原6c34 head常规42470114817在Python310安装504，旧Windows42470114805已在更新后申请取消，不能拿旧head结果代替最新；实际head/CI必须查询。隔离GUI服务创建/启动组合命令被自动审批拒绝blocked by policy，未执行/未绕过，未创建聊天生成目录；即使CI绿也须GUI/窄屏/键盘/重启后才转Ready。
- 当前Live2D协议原型：最终542本机后端/1权限跳过194.91秒（live2d-protocol-final）、21专题（含真实自有CLI子进程/UTF-8/EOF/超长输入/101切换）、15前端及构建6.18秒。仅生成目录、无模型/文件/SDK/GPU/网络监听/应用初始化，代码最后修改提交82a7247，后续文档提交不代表多做了渲染。创建本PR后按其精确head检查普通/Windows全部CI；不因其他分支失败就跳过。

以上统计来自各自b84基线独立分支，**不能相加作最终集成通过数**。待main可推进时，普通merge最新main进各分支（不强推），保留文档所有记录、重跑真正集成全量/构建/CI再合并。目前未执行含所有未合并代码的最终集成验收。

### 下一轮精确操作

1. git fetch origin main并用gh pr list/view核实#64/#65/#66和当前协议PR的head/CI/冲突；不要沿用本文时间截面的状态。官方资源下载仍504时先保留失败，不改Python最低版本/镜像或绕过签名/保护。#65若全绿且无冲突可按授权正常merge；否则保留。
2. main推进后先收敛#64：普通merge origin/main、处理文档头保留双方内容、后端全量/前端测试构建/Windows全部CI，再正常merge。角色卡没有真实语义质量/自动封面/直接小说转卡新界面，已有OC/抽取证据流程继续复用。
3. 协议原型可在适用CI全绿且无冲突后普通merge，无GUI变化；实际渲染仍待合法运行时、Core/Framework版本配套、真实模型/GPU/窗口。绝不复制GPL实现或打包第三方模型。固定参考与官方当前版本证据见research/LIVE2D_RENDERER_ARCHITECTURE。
4. #66保持Draft直至可批准执行的隔离GUI验收；之后再按独立增量做群聊参与者/逐角色上下文与模型、有限轮次、旁白/剧情与选项分支。已有单人编辑/重生/分支不重写；模型面板不等于多模式完成。原生目录选择/外链导航、更多图书匹配也仍待。

### 数据、资源与长期方向

A/B专属private/discovery-20261108-v2、C专属private/cards-20261108-v1均核对生成标记并认证关闭，control.stopped=true；令牌不得打印/提交。十个生成发现源与生成原地封面Hash保持；不是重新验证个人原件的Hash。浏览器临时尺寸已重置，公开截图全部生成；C截图在#64分支，不要使用用户模型/小说作公开演示。

没有停止个人8000、访问旧WebUI/模型/原始世界观或替换个人库/安装；没有真实/付费AI调用、Core下载/协议接受、摄像头/GPU或公开Release。测试PYTHONPATH指向当前工作树backend，TEMP/TMP在E:/Skill/front/.cache/tmp；不要误用根旧editable包或重放旧准备脚本。

原型未改前端/业务DB/API/依赖，初始bundle与基线相同；无整机CPU/RSS/PrivateBytes/Heap/GPU/FPS或冷启动/泄漏新结论。Voice真实TTS/数据集/训练/制作、Live2D动作/道具/面捕/玄宝酱授权、Krita/笔刷/压感、真实OC/生图、小说语义、3D、游戏音声/特典、大库、正式Windows/签名更新/插件方向完整保留。

## 2026-11-08 · 当前构建阻塞与独立重试增量

截至本提交最新fetch origin/main为 **b84b856a9ca5ec4037c2fd68afb7ee7f505b4896**（#63正常merge）。#62常规42458154437/Windows42458154440与#63常规42461583921/Windows42461583955全部成功，原精确记录以下保留为历史。

#64角色卡head **f0ebf5aa95cebee738de7239f74ebf49ed2da5c8**：534本机后端/1权限跳过、18前端/构建、生成实际GUI/390px深浅/重启/隔离恢复通过，常规42466429793成功；Windows **42466429802尝试1/2均失败**，第一回helper DLL504，第二回NSIS ZIP504，应用/Rust编译及此前测试成功。没有合并、不把失败当验收；不要继续无界重跑整个job。

当前codex/windows-bundle-retry从同一最新main创建，严格官方来源502/503/504最多两次重试（5/15秒），保持原命令/锁文件/哈希/签名及最终失败门槛。27定向、548本机后端/1权限跳过166.77秒、15前端与构建通过，远程CI以该PR精确head为准。若限次仍遇上游故障则留下待合并，不能豁免Windows门槛。见BUILD_RELIABILITY.md。

已推送且独立基于同一main的两个功能分支：codex/chat-model-snapshots（533后端/1跳过、15前端与构建，Mock/并发/备份；GUI启动组合命令被自动审批拒绝blocked by policy，保持Draft/未验GUI）；codex/live2d-renderer-protocol（初始542后端/1跳过、15前端/构建，UTF-8更新后21定向通过，CLI非渲染；下一同步基线后再记录集成全量）。各自范围文档在对应分支，未复制GPL代码、未下载/同意Core许可。

准确后续：先检查构建重试PR完整CI/实际下载结果；通过且无冲突才普通merge，再把最新main普通merge进#64，重新测试/构建/全部CI后考虑合并。聊天待真正隔离GUI，勿仅凭Mock和绿CI转Ready。Live2D头less原型可独立验收并提交PR，但真实渲染/窗口/GPU需要许可/环境。不要强推、改镜像/校验或发布Release。

自建A/B与C实例均已认证关闭：private/discovery-20261108-v2和private/cards-20261108-v1的专属标记/control均核对stopped=true，令牌不得打印/提交；聊天生成目录未创建。Root checkout仍3aaa9e1且clean，个人8000/安装/数据库和原始素材未替换或操作。旧NEXT关于A/B实例仍运行为历史，不能重放。临时浏览器尺寸已重置；已公开截图全部生成。

所有Voice真实TTS/数据集/制作、Krita/压感、真实OC/生图/小说语义、Live2D动作/道具/面捕/授权、3D、游戏音声/特典、更多匹配、大库和桌面/正式签名更新等长期方向保留；当前不需要用户夜间给密钥或接受协议。

## 基线、分支和权限

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
