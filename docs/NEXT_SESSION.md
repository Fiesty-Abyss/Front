# 接续 · 严格聊天收敛与独立资料体验

## 当前结论 · 2026-11-09

本次接续提交前 origin/main **69cb89bf21468c8f501b74f3d4297be9867e991c**。本轮已实际修改、测试并推送三个功能分支，均保持 Draft，未将缺失的GUI验收视为通过。群聊/有限调度/剧情/选项仍未开发，没有叠在#66上的依赖PR。

| PR / 精确 head | 实际完成范围 | CI / 门槛 |
| --- | --- | --- |
| [#66](https://github.com/Fiesty-Abyss/Front/pull/66) `b56bd4209cdd55eef74ba7dc899696d561e23a28` | 正常合入main；完整问答单元裁剪，开场白另计；省略摘要分页；SSE首事件前断连/部分保存/正确释放；轻量会话分页、测量索引和升级前快照 | 常规42617831053全成功；Windows42617831079待最终核对。聊天GUI未执行，不Ready/合并 |
| [#71](https://github.com/Fiesty-Abyss/Front/pull/71) `1f6fcb9e2b878181a8e154dc99b7ec1cd58c0c92` | 六类现有入口的官方Rust路径桥接，精确origin/主窗口权限、单对话框租约和迟到保护，无新表 | 常规42614869262 / Windows42614869254全成功。真实目录选择/取消/保存/4文件扫描已验；模型文件/完整窄屏键盘/重启未验，继续Draft |
| [#72](https://github.com/Fiesty-Abyss/Front/pull/72) `e038cf5da2cde575dca0b879e1cf74b5747e52ac` | 复用#69的ISBN说明、年份筛选、作品/版次标识、无目标时来源字段摘要/中文标签，无新来源/表 | 常规42617623143全成功；Windows42617623224待最终核对。22项Node含Vue SSR，不是GUI，继续Draft |

重新查询当前head与全部检查，不能用旧head成功替代。本次文档不会安装软件或发布Release。上一main快照归档至 [PRE_HARDENING_MAIN_20261109](audits/chat/PRE_HARDENING_MAIN_20261109.md)，其他文档中11-08状态不覆盖本页。

## 代码缺陷与性能证据

- 上下文改为用户请求和其回复整体裁剪；system/必要世界书/当前完整单元保留。预算不足422回滚未发送输入；历史、分支和原人设不改写。省略消息、问答、开场白分别计数。
- 即使首次SSE前断开，也释放未启动占位；start/delta后断开、取消、超时、坏格式、截断、超额有协议回归。上游同步调用未返回时仍占槽，不声称已停止远端计算。终结事件前关闭/保存/释放，旧流清理不能释放新token。
- 新摘要cursor页默认50/最多100，不装载消息树；更新时间+ID稳定排序，标题字面搜索。旧数组保留字段但改为有界limit/offset，依赖无界结果的外部调用者须分页。详情树仍按需全量读。
- 省略预览原先返回全部省略正文：120生成轮次响应 **1,007,365 → 9,087 bytes**。现默认20条/上限100，每条240字符，生成meta只存有界位置样本和准确总计。预览明确不含草稿，发送时重算。

同corpus ASGI/tracemalloc，1k/10k会话：旧响应183,787/1,857,789 → 新8,756/8,860 bytes；耗时216.26/2,838.75 → 223.13/284.66 ms；Python分配峰值12,718,703/123,709,424 → 1,511,958/1,473,170 bytes。1k耗时未改善。这不是RSS、Heap、GPU、启动或真实滚动。EXPLAIN先证实排序/分组临时B-tree，再增加两索引；旧库先一致快照再幂等建索引。

实现和专题回归在各PR的 docs/audits/chat/HARDENING_20261109.md、docs/DESKTOP_PATH_PICKER.md、docs/audits/metadata/EDITION_UI_20261109.md；未合并前从对应分支读取。

## 测试与GUI边界

本次仅文档接续的main基线另行实跑：**606后端通过/1权限跳过173.23秒、18前端通过、生产构建6.27秒**。这是独立组合，不与下面三个分支的数量相加。

- #66：曾完整641通过/1权限跳过251.85秒；最后Python组合（新增摘要回归）**641通过/1跳过/1既有CIM清单失败225.70秒**，24 Node/构建7.55秒。首次索引报告断言失败已补索引列断言，不删测。CIM只读诊断返回0x80004005，未改WMI配置/弱化断言。远端精确head另核对。
- #71：28 Node含Vue内存renderer行为/构建8.18秒；首次Linux测试等“一拍”的动态import假设失败，改为等待bridge实际进入，新head全CI通过。本机605通过/1跳过/1既有CIM失败；远端Windows完整回归、原生权限/租约、冻结后端/迁移/ACL、测试签名、NSIS、便携与完整性全通过。
- #72：**606通过/1权限跳过215.28秒**、22 Node含Vue SSR/构建7.62秒；无后端/数据库改动。静态Metadata路由chunk14,344→17,074 bytes，不是运行时验收；无新常驻引擎或封面解码。
- #66没有重包装重试历史审批拒绝的聊天helper创建/启动组合，没有新拒绝或聊天GUI结论。无真实AI质量/付费调用验证。

#71独立GUI用成功run42614869254的便携Artifact；四产物SHA/CRC/manifest校验通过。包源为GitHub合并测试SHA **9bbe0263ae9bcb4060844a051a51641fbed81760**，parents已核对为main69cb和head1f6，不假称等于分支head。未运行安装器。

CUA真实窗口使用专属便携FrontData/随机端口57045。已看到空库、原生目录对话框、取消后名称保留、含中文/空格/&路径正确回填、保存来源、手动扫描4项/0错误/未归档。随后窗口最小化，CUA不能恢复；官方Computer Use同窗口激活持续报“user input was detected…call get_window_state”，重新观察又报“window is minimized…activate_window”。停止GUI，不把模型文件、窄屏、键盘或重启标已验；这不是新的审批拒绝，也不能归因Front产品缺陷。

仅清理本轮精确EXE路径匹配的测试壳，其后所属后端数0、端口不再监听。生成库只读检查 **integrity_check=ok、外键问题0、来源1、Asset0**；4生成源文件SHA256不变，测试数据保留。#72未借此启动新GUI/聊天服务。

验收观察图未提交公开仓库；屏幕上其他悬浮桌宠不属于Front渲染结果，不能用作Live2D完成证据。

## 下一步准确操作

1. fetch origin/main，查询#66/#71/#72最新head、Draft、CI、保护和冲突。根checkout仍 **3aaa9e1 clean**，不得从旧树覆盖main。使用对应.cache/worktrees；pytest显式PYTHONPATH指向该树backend，TEMP/TMP独立.cache/tmp。
2. #66只在审批方明确允许的隔离方式做真实GUI：新建、Provider/参数快照、发送停止/异常草稿、编辑重生分支、Provider删除、重启、390px/键盘/控制台。不得换工具/包装绕过历史服务启动拒绝。全部验收和精确head全CI后才Ready/正常合并。
3. #71先确认Computer Use可观察/激活可见窗口，再用内部Artifact继续文件选择、其余入口、键盘/窄屏/深浅主题及正常重启。#72另验真实字段显示、公开ISBN主动查询、人工覆盖/版本及键盘窄屏。验收前保持Draft；不能用SSR或伪造Tauri标志替代。
4. 正常merge更新main；全局接续文档冲突保留当前权威状态，细节放各自audit，不复制旧完成措辞。源分支独立，不强推、不删未合并工作。
5. #66验收合并后，才开发稳定参与者/角色版本/独立Provider与上下文，再有限轮次/token/并发/费用/停止，最后剧情节点/选项/会话记忆。不得改正式百科、世界观或已有分支。

## 位置、隐私和长期目标

源工作树：chat-models、desktop-path-picker、metadata-edition-ui；接续树chat-quality-handoff。缓存日志保留chat-hardening-full-1/2/3/4、chat-omission-repro-2、chat-final-node/build、path-picker-node/CI/frontend/cargo、edition-ui-full-1/node-final3/build-final3。原生生成目录private/desktop-picker-20261109，包和测试FrontData在.cache/native-picker-ci-42614869254，均不进Git。

未访问/改写个人库/8000/安装、旧WebUI、原创世界观、SD/第三方Live2D原件；无私人正文、图片、录音、权重或Key公开。无正式Release/生产签名/许可接受/大型模型下载/收费AI。

Voice真实TTS/授权声线/数据集/切片转写/独立训练/MP3续拼，Live2D合法Core/SDK/玄宝酱许可署名/真实渲染/动作道具面捕，Krita/笔刷/数位板，OC/LoRA/真实SD和ComfyUI，小说语义/多世界观关系，3D/游戏音声特典，大库性能、正式安装升级/签名更新和插件全部保留。


---

# 保留的历史接续（2026-11-08，不覆盖上文）

# 最新接续 · 聊天收敛与ISBN版次

## 本轮最终收敛 · 2026-11-08

本次文档提交前main **7a8d4ed5ffab875c69d3daaca600cd761f335a01**。#69已正常合并：head88fe6fd1a39aae0df578af572ead33ac1221e52b，常规42480759918/Windows42480759995全成功（NSIS、便携、独立完整性与内部Artifact）；合并后主线42482442395亦成功。没有正式Release/签名信任根或个人安装更新。

#66当前head **c2f815e76f8f25b1fc7d660c027e0adfe42a2609**，普通合入此最新功能主线，已解决文档冲突，聊天源码/元数据/角色卡/Null协议/构建重试均保留；与主线的差异仅聊天代码和专属文档。常规42482805929与Windows42482805944：**全部成功（常规与完整Windows）**。继续Draft，即使CI绿也不能代替真实GUI。

主线ISBN本机完整606通过/1权限跳过180.12秒，18前端/构建6.07秒；Draft最终组合619通过/1权限跳过225.91秒，18前端/构建8.91秒。这是两套各自实跑，不相加。前一聊天组合先594通过/1跳过/1 CIM清单失败，单组9通过、全量595通过及最终619通过均保留，未跳过失败或按猜测修改遥测。

本轮没有重试此前自动审批拒绝的聊天服务创建/启动组合，也没有改变包装/工具绕过；因此没有新的拒绝结论或GUI证据。GUI所有必要流程仍待，群聊/叙事/选项不堆叠Draft。独立ISBN API有生成协议/版本恢复/人工保护和真实公共书目验证，无新增前端、表、服务或推理；浏览器对新增字段的实际显示未验。

约定.cache/cubism-sdk目录检查不存在，未下载Core、接受协议或读取第三方模型；真实Live2D继续受合法运行时/许可和硬件验收阻塞。原生目录整合、Voice/数据集/训练、Krita/数位板、OC/真实AI、小说语义、3D、游戏音声/特典、安装升级/正式签名更新与插件全部保留。个人库、8000、旧WebUI、原始世界观/模型和私人素材未写入或替换。

以下旧记录为历史时间截面，不覆盖本节与GitHub实际状态。

## 当前代码与验证

| 增量 | 状态与证据 | 未验证/未完成 |
| --- | --- | --- |
| #69 ISBN版次 | 已合并；校验ISBN-10/13、OL…M版次与OL…W作品隔离、固定JSON跳转/限流、来源/人工保护、恢复追加版本；606后端/18前端/完整Windows成功 | 无专用新UI、自动标签翻译、封面下载或批量版次；实际浏览器新增字段未验 |
| #66单人模型快照 | Draft；先合bce的3e9288e，常规42480402678/Windows42480402751全成功；再合7a8d4ed到c2f815e并本机619完整通过，最终CI见上 | 真实GUI未验，不转Ready、不合并；不是多角色/剧情系统 |
| Live2D | 既有档案/原创Null协议保留，现约定SDK目录不存在 | 无真实渲染、动作/道具/面捕/GPU结论；许可不代接受 |
| 其他创作模块 | 原有Voice/OC/小说/世界观/素材与完整备份测试继续执行并保留 | 不把本轮API测试当真实TTS/生图/训练/专业硬件或干净安装验收 |

ISBN公共兼容样本9780140328721由官方302到OL7353617M；搜索/详情同一版次，eng、关联作品OL45804W。只查公开书目，不下载封面/正文或发送个人资料。校验位、作者/年份/错版次、恶意跳转、旧空缓存、并发指纹、人工保护、事务、追加恢复为生成样本/Mock。旧空缓存回归先失败再修复，最终测试含该回归。见[实现范围](BOOK_EDITIONS.md)/[验收](audits/metadata/EDITIONS_20261108.md)。

聊天Draft范围与源测试见[固定head文档](https://github.com/Fiesty-Abyss/Front/blob/c2f815e76f8f25b1fc7d660c027e0adfe42a2609/docs/audits/chat/SNAPSHOT_MODELS_20261108.md)，不是main已上线能力。当前只有一个聊天Draft，未增加依赖它的群聊或剧情PR。

## 下一步准确操作

1. fetch origin/main并查询#66最新head、CI、mergeable及main；不能照抄本快照。已合并#69无待合并事项；普通merge/不强推，不删除未合并工作。
2. #66在可合规执行的隔离环境完成新建、Provider/模型/温度/预算、快照恢复、发送/停止/重生、异常草稿保留、编辑分支、重启恢复、桌面/390px/键盘和控制台。不得换包装绕过先前拒绝。全部完成才Ready，重新同步主线并通过完整CI后正常合并。
3. #66未完成时不新建群聊/剧情依赖PR；可先独立做原生文件夹选择/安全导航、更多来源或ISBN专用编辑体验，各自提供明确真实验收范围。
4. 后续群聊先参与者稳定身份/版本与独立Provider/参数/上下文，再手动轮次、有限自动调度/停止；剧情/选项复用消息树和版本，不覆盖原分支、正式百科或世界观。所有角色/Provider删除和世界观变更须有证据回归。
5. Live2D先核对合法SDK/Core配套与发行/素材许可，再真实模型/GPU测试；当前未下载、未接受。继续原创接口/动作预设/生命周期，不能以Null、静态图或空Canvas宣称渲染。
6. Voice真实引擎/授权声音、数据集、切片/校对、独立训练和MP3/续拼按既有PRD继续；不自动启用服务、付费、下载权重或克隆。

## 执行位置与隐私

Root checkout仍3aaa9e1731185046bee1f26a7eef1119514f8e33且clean，不代表GitHub最新代码已安装到个人电脑。本轮源工作树为.cache/worktrees/chat-models、metadata-editions，接续文档在chat-isbn-handoff。全部pytest使用独立.cache/tmp和显式PYTHONPATH=当前backend，避免误用根旧editable包。

日志：chat-convergence-backend首次CIM失败、chat-convergence-backend-2全595、chat-isbn-final全619、isbn-cache-repro复现旧缓存、isbn-final-full全606、对应node/build和远程watch记录。没有真实AI请求/质量结论，也没有整机CPU/RSS/Heap/GPU/启动性能新增测量；构建耗时不能替代它们。前端无ISBN源码改动，未启动新GUI服务。

A/B与角色卡上轮生成实例已关闭；本轮没有重启它们或个人8000。原始世界观、小说、Live2D和SD权重未修改，API Key、个人数据库、私有原文/图片/录音未公开。无正式Release或生产密钥配置。

本次文档前快照已[归档](audits/chat/PRE_HANDOFF_20261108.md)，更早记录见原audits；长期Backlog/PRD与授权条件保留。

多角色/剧情只完成后续约束文档，**没有实现新调度或数据表**：[CHAT_MODES_DESIGN](CHAT_MODES_DESIGN.md)。优先完成#66真实验收，再按其中门槛逐步实施。
