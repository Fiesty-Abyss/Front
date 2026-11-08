# 最新接续 · 资料发现与角色互动轮 · 2026-11-08

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

## 基线、分支和权限

开始时fetch的origin/main为`3309edaab8c2c7c2eb7f6506e03f9641a73c9dc1`，#54–#61均合并、main CI42454312706成功。#62精确head f3bd6d28cb045d2a109aecf02a6eb873d0923444全部CI成功：常规42458154437、Windows42458154440（冻结/ACL/迁移/更新签名协议/NSIS/便携/完整性），已按授权正常merge。最新已核实main为`47054ea9bb471d4e346fbbb406b8d61bece7bcdd`。当前独立`codex/metadata-center`从该main创建，待本PR精确head全部适用CI；未通过前不合并、不堆叠下一功能。合并后fetch实际main再开独立分支。

工作树`.cache/worktrees/voice-acceptance`；根checkout仍为3aaa9e1，用户安装、个人库及原始资料没有替换或升级。沿用既有CLI仓库写权限，GitHub连接器只读研究参考；不改网络/账号权限、不强推/绕保护、不发布Release或配置生产签名。

## 本轮已实现：多根来源与候选归档

- 新增discovery_roots配置表：稳定UID/版本、类型/深度/忽略/预算、活动状态及预览指针。复用ProjectPreview/ProjectImport/LibraryImport/Asset/ingest/jobs；无新依赖或第二套文件库。
- 显式只读扫描，不自动启动监控/联网/AI。根/目录/文件在解析前拒绝链接/Windows重解析点，跳过数据目录；限定所有目录项、文件数、声明大小、Hash与协作时间。时间检查不保证OS阻塞I/O硬超时。
- 暂停/取消保留报告与完成Hash；恢复重新枚举/复核并复用指纹，每轮报告独立，部分报告不导入。重启标interrupted，不重放。完整且配置相同的基线才报告缺失；达到预算/范围改变不把未扫描内容当丢失。
- 目录锚点建议作品/正文/附录/封面/关联资源，标签只建议，不自动建/合并作品、角色或标签。模型权重/EXE只登记信息，需专用库处理，不复制权重。ZIP只读有限目录，无解压/完整CRC承诺。
- 修复已有预览中间链接检查、未Hash通用导入、扫描失败但进度显示完成、压缩包错误计数及附录角色建议；新增队列失败/队列前取消的可恢复状态。

## 已执行证据

- 最终本机506后端通过/1权限跳过；15前端与生产构建通过，日志是discovery-acceptance-full、discovery-node、discovery-build。源码显式PYTHONPATH指向工作树，不使用根旧包。一次构建/旧测试收尾重叠导致3个dist/static夹具错误，已按先构建后全量重跑；失败批次不作验收。
- 专题15通过/1权限跳过；Windows真实Junction、链接/越界、ZIP预算/坏包、增长文件最多声明大小+1字节、深层作品锚点、并发/ID边界、暂停续扫/排队前取消、429/503/重启不重放、旧schema前置快照和完整备份独立恢复。
- 实际浏览器1440桌面与390窄屏深浅主题、键盘保存、422保留表单、失效来源明确失败；窄屏document380、正常console warn/error0，canvas/audio0。临时尺寸已重置。
- 生成样本两来源：首根9项/重复3/仅登记模型1，确认8项索引后5份共享素材，重复导入仍5；第二根1200TXT，在81项暂停后续扫复用81并完成。重启保留配置/UID/报告/素材引用，10个源样本Hash未变。失效目录只用自建空目录，诊断后其配置已清理。
- 暖缓存1200项两次重扫1.4566/1.4273秒，复用1200Hash/实际Hash读取0，50项27230B；自身源码后端一次WS117.28MiB/PrivateBytes102.11MiB。存在同时隔离pytest，不作严格前后对比、全App、冷启动、Heap/GPU或泄漏结论。最终Discovery chunk约11.30kB，无默认大型引擎。
- 所有文件/小说/模型占位均生成；本轮不触碰个人库、原始模型或私人素材。真实来源/外部模型/硬件/干净Windows未验收。

接口/限制：[DISCOVERY](DISCOVERY.md)；截图/兼容/性能：[ROOTS验收](audits/discovery/ROOTS_20261108.md)。研究初查：[锁定参考](research/CREATIVE_REFERENCE_20261108.md)。本机服务仅自建隔离实例，控制记录在专属生成标记目录，后续须核对所属后停启；禁止按进程名或PID子树广杀、指向个人活动库或重放旧prepare脚本。

## 下一步准确顺序

1. 提交资料匹配独立PR，等待常规+Windows全部适用CI和冲突检查；只正常merge，记录实际head/run/merge SHA，再fetch最新main建独立codex/分支。
2. B首增量已实现：[范围](METADATA_CENTER.md)、[验收](audits/metadata/CENTER_20261108.md)。游戏来源/Civitai复用，Open Library作品级查询，显式有限jobs/缓存/候选分级、Work/Galgame来源/人工确认/指纹事务/不可变历史；修复本篇FD错误匹配及上传封面刷新覆盖。最终521后端/1权限跳过、15前端/构建通过；生成Mock GUI桌面/390px深浅、键盘/取消/失败/恢复追加/重启5版本，真实公共图书search+detail另记。未完成ISBN/Edition/语言/动漫/作者详情、Google/NextMoe、统一模型写入历史和跨来源自动补全，不误标全B完成。新中心不读取或复制权重。
3. C角色卡：细审CharacterCard/OC/百科/世界书/证据审核/版本，补草稿/来源/封面选择与兼容导出，不创建第二套人物或生图引擎。远程发送范围必须明确预览/选择，未配置服务仍手动可用。
4. D多模式：复用ChatSession/ChatMessage消息树，审查已有单人/Provider切换，再补群聊、叙事/选项、逐角色模型/参数快照和有限轮次/token；不简单拼接所有角色System Prompt，不默认启Voice/Live2D/3D。
5. E桌面：复核现有Tauri随机端口/令牌/独立Sidecar/数据锁，补原生目录选择、统一配置与安全外链；不改Web8000或用户安装/个人活动库。实际窗口/干净安装另验。
6. F：只读深入Bandori固定提交的model_manager、click_actions、native/pet_backend和资源/IPC。GPL来源不复制，不因外部进程就保证许可兼容。先自己实现独立渲染器接口/有界动作协议与无模型生命周期原型；合法运行时/SDK/模型许可不足时不宣称真实预览。

当前仅专属生成实例，私有控制记录`private/discovery-20261108-v2/control.json`保存随机端口/自身PID/令牌（不得打印或提交）。新增缓存脚本metadata_acceptance.py用于这个有专属标记的实例，当前metadata_test_mode为MockTransport，禁止当真实外部来源；已重启验证1作品/5历史、2根/5素材和十生成源Hash保持。不要对个人8000服务执行停启。临时浏览器尺寸已重置，截图均生成内容。根checkout/用户安装仍不升级；后续停用必须核对专属标记、PID与认证回环地址，只关闭所属实例。

## 上轮Voice和长期方向

#54–#61功能证据和精确CI见[audits/voice/ACCEPTANCE_20261108](audits/voice/ACCEPTANCE_20261108.md)。个人库只读副本integrity=ok/外键0，隔离升级/备份恢复通过，原DB/WAL/SHM当时Hash保持；历史错误准确旧包仍未知，不能据旧提示重置。此轮没有再次打开原库或执行迁移。

Voice真实GPT/实际权重和引擎身份、授权声音/音质延迟、完整数据集/切片/转写/训练验证分组与外部训练预算、可恢复分片/MP3仍待；现有正弦波协议不是AI推理。Live2D/玄宝酱用途与署名/SDK、Krita/笔刷/数位板、真实SD/ComfyUI/OC、小说语义、3D、游戏/音声/特典、大规模素材和插件、干净Windows/正式签名更新/Release审批持续保留。
