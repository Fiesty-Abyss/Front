# Front 接续记录 · 2026-11-07

## 当前 RC 会话

PR #37全部四项CI通过并正常合并，当前main=`10eb0a71dd8785b91cb2985a4a73f672f9eab32d`。C工作树`.cache/worktrees/windows-acl-rc`/分支codex/windows-acl-rc已同步main并完成真实源/本机冻结ACL及启动/迁移组件回归，最终262后端/8前端和构建通过，等待独立PR和Windows CI。C之前本机PyInstaller首次使用默认用户缓存，已固定项目cache和TEMP并重建，没有额外清理用户默认缓存；不是私人资料迁移。

下一步：C完整CI后普通合并；D启动可视进度草稿在.cache/startup-draft（尚未编译或验收），同步最新main后独立开发。E继续真实SDK网络中断/取消测试；F内部候选和完整门槛文档。没有干净VM/正式签名根，不能发布公开正式版。主机原8000仍未启动，真实个人库未动。

PR #36已通过backend/frontend/python310-compat/windows-x64并正常合并，当前已同步main=`425d789ac6155ee022640d2bfafea5188548c61b`。RC B分支`codex/mixed-reliability-rc`完成261本机后端/8前端/构建及完整混合工具、浏览器生成资料，待本阶段PR/CI。报告RC_MIXED_B.md；.cache/rc-mixed-final-01保留101201条生成素材，HTTP8002启动器30964（停机前重新核对实际归属）。

Windows真实ACL草测发现TemporaryFile无限式重试（观察超过60秒后停止已核对的测试进程）；原ACL在finally恢复，原生成哨兵仍在，恢复写入成功。待独立C修复prepare_folder为有界独占新建探测，并补真实ACL/Frozen验收。`.cache/rc-acl-probe-01`是生成目录，不是用户目录。主机Windows11家庭版22631，尚无经过验证的干净VM/快照，真实安装/卸载/升级不可用日常主机测试替代。

以下“接管”及上轮段落保留历史语境，不将过时SHA作为最新。后续继续C/D/E及内部候选包，正式信任根和公开Release仍未授权。

接管已fetch确认origin/main=`d2a14d41cc1b256133978d127624b353ace4e606`，无开放PR；以下RC A独立分支`codex/collection-pagination-rc`，尚待本轮最终CI与合并，后续合并状态会再更新，不能把下方上轮历史main当最新。

RC A摘要/游标/批量/排序及隔离10k/50k/100k、真实浏览器/390px已完成；本机259后端、8前端和构建通过，最终回归进行中。报告`audits/v0.7/RC_COLLECTIONS_A.md`。生成库与HTTP测试服务在.cache/rc-collections-*，不在private/front-data；原始世界观、WebUI、Live2D及私人库未启动或改动。原8000当前未运行，不能沿用上轮“服务持续返回200”的结论。

下一阶段：混合小说/角色关系/世界观/模型/提示词/音频/OC/队列积压与取消恢复；真正干净Windows、正式信任根/公开Release仍受环境/授权限制，不伪造验证。

## 上轮交接（历史，2026-10-25）

## 仓库与CI

- 最新已核验功能main SHA：`9e1096e35eee3bafee34e1bbcc2723e6eee7744a`。这是本交接文档PR创建时的精确main；交接PR只改文档。接管先fetch再读origin/main，最新提交/本机交付状态另存private/DESKTOP_SPRINT_STATUS.json。
- PR #29–#34均已普通合并，没有遗留功能PR。不要重开已完成的功能，不强推、不删除尚未合并工作。
- 最终F head aa7dc19，四项检查backend/frontend/python310-compat/windows-x64 success。Windows run40126359742：253后端通过/1跳过、6前端/生产构建、6真实Rust SDK/TLS/竞态、冻结HTTP与最小PATH/迁移回归、NSIS/便携、清单/CRC/Hash都通过。
- 本机最终254后端、6前端、生产构建通过。3.10是18项工具/大库专项CI，不宣称全后端均在3.10实测。Windows runner有预装开发工具，最小PATH冻结验证不等于干净VM。
- 构建commit `92782cfc8740fb01b558a1d738838ca298135257` Git tree与上述功能main相同，已核对；Artifact不是Release。程序默认无正式更新公钥，真实自动更新关闭，未执行安装器/真实更新。

## 已完成范围

A：3D生命周期与静态按需绘制，同条件10次PrivateBytes1340.71→907.49MiB、候选30次685.75；5秒静态CPU单核等效19.69→1.56%。不是物理独占RAM/峰值，也不等于零泄漏或冷启动TTI完成。

B：可写性预检、损坏/未来库拒绝、真实冻结最小PATH、中文空格特殊字符、多实例/重启、旧结构完整备份与隔离恢复。真只读ACL、安装/卸载/升级矩阵未覆盖。

C/D：官方Updater固定来源/通道、签名版本验证、取消竞态、完整备份及隔离恢复后的写屏障；内部版本/Tag/PE/manifest/ZIP/CRC/Hash gate。正式信任根、签名feed、安装中断/二进制恢复及正式发布审批仍待。没有接受Cubism协议。

E：10k/50k/100k SQL元数据、1000真实生成PNG/缩略图、101k库浏览器完整搜索/分页、全媒体备份/预览/独立恢复；修复1万搜索截断和世界观索引。100k世界观约4.4ms、普通分页7.3ms为暖态ASGI，完整短词约217ms，不能称全面变快。独立后端RSS111.62MiB是末态非峰值，前端heap未测。

F：导航名称/搜索焦点、收藏和提示词窄屏、空/读取/错误重试、空音轨0–0、Reader键盘/偏好防护。正常浏览与生成数据实际保存/重开通过，Mock503明确分类。390 iframe clientWidth实测，但工具无法点击子frame控件；不是完整窄屏交互或实体手机。

详见docs/audits/v0.7的A–F报告。长期Live2D/SDK与作者许可、Krita/数位板、真实SD/ComfyUI/AI、OC、小说语义、3D动画、游戏特典/音声与插件均继续保留。

## 下一轮准确操作

1. `git status`；`git fetch origin`；同步main并查询PR/CI；从当时最新main建新codex/分支。优先大收藏摘要和成员分页，当前1万成员约6.89MB全量响应。
2. 复用Collection/collection_assets/Asset，增加可选摘要及稳定(position,id)分页，保留旧API兼容；前端只加载当前页。不要将当前页IDs直接交给旧完整排序接口，会误把成员移到头部。绝对位置/事务/并发版本保护需独立测试。
3. 再补E混合长篇章节、多世界角色/模型/音频/正向复杂标签、大收藏、后台队列积压/取消/重启、前端heap/FPS/TTI和峰值。只有EXPLAIN和测量证据支持才加索引。
4. A真实冷热启动分布/标准可交互，B干净Windows和真实权限/安装升级，C/D正式密钥/签名feed/实际安装失败恢复由HUMAN_ACTIONS_REQUIRED列明。不得把测试密钥或构建成功视为正式发布许可。
5. F继续完整键盘、真实触控/跨浏览器/缩放、非空和长内容组合、长期切换回收。包内desktop README仍有上轮默认“无自动更新”描述，可在下一次包构建改为“实现但默认未启用”，不改成已经上线。

## 本机与数据边界

正式8000持续使用private/web-runtime-176e59c稳定快照，未切换真实库；返回200。个人资料private/front-data（外部原件引用/32模型档案），没有生成压力写入、原文件改写或公开上传。不要让Web和桌面同时指向同一活动库；切换前须完整备份、隔离恢复及单实例停机验收。

本轮自有8001/8002/8003/8004/5174服务与五个QA标签页已关闭，原生测试实例已退出。缓存pid文件只作取证，不得按旧PID直接停止后来进程。生成小库/101k大库在停止后integrity_check=ok，样本保留.cache供复测；新压测工具拒绝已有输出目录。

自动审批曾拒绝调试启动参数及Vite重配置复合命令，均未执行、未给具体理由，未重试绕过。普通原生窗口/IPC测试和显式Mock无API更新页已完成；前端heap等未覆盖。所有可控输出留E盘项目缓存/私有目录。F盘WebUI、原创项目、第三方Live2D原件只读边界持续有效；未启动真实生图/摄像头或接受第三方SDK协议。

本轮约5小时后收尾，后续工作仅记录在此，不虚构离线或后台持续运行。
