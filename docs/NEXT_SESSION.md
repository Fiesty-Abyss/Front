# Front 接续记录 · 2026-11-07

当前功能main：`745b7cad94e044a306e443b1874d058302404dfb`（已合并PR #36/#37/#38/#39，四项CI均通过）。本记录来自后续独立启动进度分支；接管先fetch最新main和PR，不能把文档内的基线当成以后最新SHA。

## 本轮已完成

- #36：大收藏摘要、稳定成员游标、筛选、跨页选择、批量编辑及事务/CAS排序；10k/50k/100k和真实桌面/390px浏览器交互。100k单页13.24KB/暖态ASGI5.53ms，旧全量64.86MB/3569.72ms。
- #37：混合生成压力（20世界/2000人物/3960关系、1000 PNG/200 WAV/1000章、模型提示词/OC/任务），真实进程中断/取消/重试；首次章节预览配对362.48→186.23ms。未测Heap/GPU/TTI，不冒充真实AI。
- #38：Windows真实ACL拒绝时长重试修复；冻结CI实际Deny ACE/恢复、最小PATH及迁移回归，安装/便携附件Hash核验。主机原生包空库打开、素材导航、正常退出通过，不等于干净系统安装。
- 当前D：单个本地启动窗口、固定升级阶段与计数、有界握手和关闭取消；旧Sidecar默认协议兼容。源进程生成媒体/旧表升级专项已实现，候选Rust/原生验收须等对应CI产物。详见RC_STARTUP_D.md。

## 下一步准确操作

1. 查看D分支codex/startup-progress-rc的PR/CI；Windows无本机MSVC，由CI编译两项startup_tests和既有六项真实Updater测试及完整包门槛。CI通过后下载同一SHA附件，检查原生阶段/失败/多实例/关闭取消和日志时间。
2. D正常合并并同步main后，独立E工作树.cache/worktrees/updater-transport-rc补真实SDK下载取消/断流/降级和manifest通道兼容测试。目前仅本地transport-only通过，不能称Rust八项已过，也没有执行安装器。
3. F生成内部候选附件、Hash和测试/许可/已知问题矩阵。干净VM、正式更新信任根、真实安装中断/二进制恢复未验证，禁止公开正式Release。

## 环境与边界

日常主机Windows11家庭中文版22631，有开发工具，无经验证干净VM。不改系统WebView2或用户安全设置。真实个人库private/front-data和原8000服务本轮未启动/改动；E盘原创/第三方模型及F盘旧WebUI原件未动。所有生成压测在.cache。

生成源服务8001（启动器35700/后端33276）和8002（30964/4620），PID必须重新核对归属后再停止；浏览器仅代理自建QA标签。原生基线27772已正常退出，不按旧PID盲目结束进程。最终精确运行状态记private/RC_SPRINT_STATUS.json。

本机首次C PyInstaller构建曾用默认用户cache，检查时已完成；随后build_sidecar强制项目.cache和TEMP并重建，没有额外清理默认用户cache。后续受控输出留E盘。未公开Release、未配置正式密钥、未接受Cubism协议。长期Live2D/Krita/数位板/OC/真实AI/3D/特典和插件路线继续保留。

## E提交时补充

D Windows run42351228491全部通过（262后端/1跳过、6真实Updater+2启动Rust、冻结ACL/迁移、两包Hash）。已下载核验外层digest/内层Hash。未来生成库原生错误提示实际可见，冻结复核DBHash不变。正常空库native日志621/2164/2495ms分别是窗口创建/服务ready/document load，非TTI，150%缩放。后续激活/捕获多次返回最小化/用户输入提示，停止反复激活；点击取消、完整原生导航和多DPI不标通过。私有截图含桌宠叠层，不公开。

1GiB生成媒体迁移真实中途强制结束壳，源DB/媒体Hash不变；重启产生完整备份/隔离恢复并完成迁移，ready5540ms/document5837ms，非GUI/TTI；.cache/rc-native-migration-01/report.json。原生测试PID31604/35184/35572/34744均已结束，仍须复核无所属后端，不能按旧PID盲杀。

独立E已265后端/8前端/生产构建通过，待PR与真实Rust八项Windows CI；通过后普通合并，再同步F分支codex/candidate-docs-rc。F草稿含preview.2版本与安装/备份/许可/RC不放行说明，不得未验收公开Release。
