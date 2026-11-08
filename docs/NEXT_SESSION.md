# 最新接续 · 资料发现与角色互动轮 · 2026-11-08

最新安全回归：旧环境服务默认标签可能包含完整端点URL，现新消息仅记录引擎名，不将端点凭据/错误正文持久化；13项专题和完整534后端/1权限跳过199.12秒通过，日志chat-security-target/chat-security-full。未执行任何真实AI请求。#66旧head的Python310 CI42470114817在setup-python下载官方3.10.22包时504，未运行兼容测试；不是代码兼容验证通过。当前head更新后应查新CI，保持Draft/GUI门槛；不为此改Python版本或跳过测试。

2026-11-08会话模型底座：独立codex/chat-model-snapshots基于最新fetch main b84b856a9ca5ec4037c2fd68afb7ee7f505b4896（#62/#63已合并）。追加模型/参数快照、实际回复来源、上下文字数预算、生成互斥/上限、失败输入保留与安全错误。534后端通过/1权限跳过199.12秒、15前端及构建，49定向包含并发/分支/旧客户端/备份恢复；全部AI是Mock。实际GUI启动组合命令被自动审批拒绝blocked by policy，未执行/未绕过，故保持Draft，不能用CI代替GUI验收。[范围](CHAT_MODEL_SELECTION.md)。#64角色卡Windows两次官方NSIS下载504未合并，#65构建有限重试独立等待CI；本分支不堆叠依赖它们。

本分支工作树.cache/worktrees/chat-models，源包以PYTHONPATH=该worktree/backend测试，TEMP/TMP均E:/Skill/front/.cache/tmp；不要误用根旧editable包。最终本机全量日志chat-full-final（534/1权限跳过）、chat-target-7（49通过）、chat-node-final（15通过）和chat-build-final。初始失败的旧客户端配置提示与快照datetime JSON问题已修正，失败批次不作验收。

模型选择是追加历史，恢复参数先放入表单再明确保存，不改旧回复；没有UI/真实模型质量验收。Chat专用chunk13.97kB/gzip5.92，按需ModelPicker4.23/2.29，初始JS216.92/83.43；只是构建大小，不是整机性能。上下文是字数预算，不是实际模型token窗口；旧全局默认兼容行为保留，已选服务删除/换址不回退。

下一步先fetch核对#65重试CI和当前main；如果main推进，普通merge origin/main进本分支（不强推）并处理文档头部时保留两个增量记录，再跑集成全量/构建/全部CI。GUI审批阻塞未解前保持Draft，即使CI绿也不合并。GUI需要验证选择A/B模型、明确切换、流式回复/停止、错误输入保留、分支/重生、历史/重启、390px/键盘和console；全部先生成数据。之后再独立开发群聊/剧情/选项，不简单拼人设或无限生成。

#62/#63已完成，#64 head f0ebf5aa Windows42466429802尝试1/2均官方下载504，常规42466429793成功；#65独立重试PR保持原锁定/签名/Hash门槛。Live2D协议codex/live2d-renderer-protocol已推送且无真实渲染，不把其他未合并分支当当前代码。

A/B/C专属测试服务均stopped=true；聊天生成目录未创建。根checkout仍3aaa9e1/clean，个人8000/安装/数据库/原始资料未操作；所有截图/协议为生成样本。长期Voice/训练/Krita/压感/真实生图/小说语义/Live2D/3D/游戏音声及正式签名更新继续保留。后续如已有更上方收敛记录，以该记录和GitHub实时状态为准。

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
