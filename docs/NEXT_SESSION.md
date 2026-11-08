# 最新接续 · 资料发现、匹配与角色卡 · 2026-11-08

合入main812d239后的真实组合回归：568后端通过/1权限跳过176.70秒（chat-integration-final.log），18前端与生产构建6.61秒（chat-integration-node/build.log）。这是本分支加已合并角色卡/Null协议的集成实跑，不是各分支计数相加。模型切换仍无GUI证据，PR继续Draft；当前merge head远程CI必须独立查询。

2026-11-08 聊天草稿集成：#64 已在 e222190d 的常规42473081686/Windows42473081585全部成功后正常合并，最新 main **812d239a4c9ac2edb28f1ca8f110f4eb0c97de87**，包含#62/#63/#64/#67。本分支普通merge最新main，仅文档冲突保留双方，models.py加法表自动合入；没有重写已推送历史。

#66仍为Draft。原8f150867常规42472069095成功，Windows42472069127应用编译成功但官方NSIS ZIP下载504失败。新集成组合须重新测试构建/CI；无论CI是否成功，实际GUI未验不能转Ready。自动审批拒绝的是创建并启动聊天隔离GUI测试服务的组合命令，原因仅“blocked by policy”；命令没有执行，也没有替代启动绕过。聊天生成目录不存在。原有角色卡GUI证据来自独立已关闭的生成实例，不是聊天验收。

已实现范围仅单人会话的显式Provider/模型参数快照、历史、预算、并发与失败/隐私保护；群聊/叙事/选项仍未开发。原生目录/外链整合仍待；Live2D仅无模型协议。#65构建有限重试正在独立收敛，无关本Draft的GUI门槛。下方为历史时间截面，最新GitHub状态与本头优先。

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

前端收尾代码审查修正：失败响应先结束streaming，再刷新服务端会话，避免open的互斥保护拦住自己的错误恢复并留下pending幽灵消息；增加晚到响应/上下文顺序保护。前端15测试与生产构建通过，真实GUI仍未验证；下一验收须包含503/流式error后输入保留、pending清理、快速重发/切换与上下文顺序。最新数据与CI以本PR精确head为准，不引用旧文档提交的CI。

最新安全回归：旧环境服务默认标签可能包含完整端点URL，现新消息仅记录引擎名，不将端点凭据/错误正文持久化；13项专题和完整534后端/1权限跳过199.12秒通过，日志chat-security-target/chat-security-full。未执行任何真实AI请求。#66旧head的Python310 CI42470114817在setup-python下载官方3.10.22包时504，未运行兼容测试；不是代码兼容验证通过。当前head更新后应查新CI，保持Draft/GUI门槛；不为此改Python版本或跳过测试。

2026-11-08会话模型底座：独立codex/chat-model-snapshots基于最新fetch main b84b856a9ca5ec4037c2fd68afb7ee7f505b4896（#62/#63已合并）。追加模型/参数快照、实际回复来源、上下文字数预算、生成互斥/上限、失败输入保留与安全错误。534后端通过/1权限跳过199.12秒、15前端及构建，49定向包含并发/分支/旧客户端/备份恢复；全部AI是Mock。实际GUI启动组合命令被自动审批拒绝blocked by policy，未执行/未绕过，故保持Draft，不能用CI代替GUI验收。[范围](CHAT_MODEL_SELECTION.md)。#64角色卡Windows两次官方NSIS下载504未合并，#65构建有限重试独立等待CI；本分支不堆叠依赖它们。

本分支工作树.cache/worktrees/chat-models，源包以PYTHONPATH=该worktree/backend测试，TEMP/TMP均E:/Skill/front/.cache/tmp；不要误用根旧editable包。初始全量chat-full-final（533/1权限跳过）；最终全量chat-security-full（534/1权限跳过）、chat-target-7（49通过）、chat-node-final（15通过）和chat-build-final。初始失败的旧客户端配置提示与快照datetime JSON问题已修正，失败批次不作验收。

模型选择是追加历史，恢复参数先放入表单再明确保存，不改旧回复；没有UI/真实模型质量验收。Chat专用chunk以chat-recovery-build-final日志为准（本次增加失败恢复与顺序保护），按需ModelPicker4.23/2.29，初始JS216.92/83.43；只是构建大小，不是整机性能。上下文是字数预算，不是实际模型token窗口；旧全局默认兼容行为保留，已选服务删除/换址不回退。

下一步先fetch核对#65重试CI和当前main；如果main推进，普通merge origin/main进本分支（不强推）并处理文档头部时保留两个增量记录，再跑集成全量/构建/全部CI。GUI审批阻塞未解前保持Draft，即使CI绿也不合并。GUI需要验证选择A/B模型、明确切换、流式回复/停止、错误输入保留、分支/重生、历史/重启、390px/键盘和console；全部先生成数据。之后再独立开发群聊/剧情/选项，不简单拼人设或无限生成。

#62/#63已完成，#64 head f0ebf5aa Windows42466429802尝试1/2均官方下载504，常规42466429793成功；#65独立重试PR保持原锁定/签名/Hash门槛。Live2D协议codex/live2d-renderer-protocol已推送且无真实渲染，不把其他未合并分支当当前代码。

A/B/C专属测试服务均stopped=true；聊天生成目录未创建。根checkout仍3aaa9e1/clean，个人8000/安装/数据库/原始资料未操作；所有截图/协议为生成样本。长期Voice/训练/Krita/压感/真实生图/小说语义/Live2D/3D/游戏音声及正式签名更新继续保留。后续如已有更上方收敛记录，以该记录和GitHub实时状态为准。

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
