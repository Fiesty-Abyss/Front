# Front 接续记录 · 2026-11-07

本F分支提交前最新main：`15cc1a30bf4af3b9b3f9dbe9e747c22c67a7eae7`，PR #36–#40全部四项CI通过并正常合并。本记录是后续独立候选分支的一部分，接管先fetch再查询最新main/PR/CI；最终合并SHA、附件和本机状态记private/RC_SPRINT_STATUS.json，不把文档基线冒充未来提交自身SHA。

## 已完成

| PR | 范围 | 证据 |
| --- | --- | --- |
| #36 | 大收藏摘要/成员游标/跨页选择/批量/事务CAS排序 | 10k/50k/100k、完整游标走查、真实浏览器拖拽/评分/390px；RC_COLLECTIONS_A.md |
| #37 | 混合规模与真实任务中断、章节识别复用、收藏选择器减负 | 20世界/2000人物/3960关系/1000章，1000 PNG/200 WAV/OC/模型元数据；RC_MIXED_B.md |
| #38 | 真实Windows ACL预检长重试修复/冻结门槛 | 源/本机冻结和CI真实Deny及恢复；RC_WINDOWS_C.md |
| #39 | 可见启动阶段、有界握手、单WebView及数值启动日志 | Windows42351228491，6真实Updater+2启动Rust；RC_STARTUP_D.md |
| #40 | SDK取消/断流/降级和manifest拒绝、私有测试Key夹 | Windows42352769584，8真实Updater+2启动Rust；RC_UPDATES_E.md |

本F分支同步基线后全量265后端/8前端/生产构建通过。Windows #40为264通过/1跳过；3.10仅兼容专项，不称全后端。Starlette/httpx弃用警告保留，不为消警告迁移依赖。所有公开截图/压力数据为生成样本；SDK测试是生成HTTPS源与真实签名/网络，未调用install/真实AI。

D同一已验CI包实际未来库错误窗口，DBHash复核不变；空库窗口621ms/服务2164ms/document2495ms，150%缩放，非TTI/冷缓存。9进程RSS633.83/PrivateBytes443.45MiB、专用GPU66.33/共享63.93MiB为单次最小化状态；非峰值/长期优化证明。1GiB生成托管媒体实际复制中强制结束壳，源DB/媒体Hash不变；重启完成完整备份/独立恢复/迁移。不是点击关闭取消或安装故障恢复。

## 当前F与下一步

1. 独立分支codex/candidate-docs-rc（.cache/worktrees/candidate-docs-rc）已同步上述main；preview.2配置/Node/Rust锁身份一致，随包README和RELEASE_CANDIDATE_STATUS已整理。本机265后端/8前端/生产构建已通过；等待PR和Windows全部门槛，不能提前把候选产物标成功。
2. 成功后下载对应源SHA的内部Artifact，核对外层digest、内层SHA/CRC/版本，隔离新目录最小PATH启动；不运行NSIS安装器或公开Release。最终包放private/deliveries独立新目录，不能覆盖旧包/FrontData。
3. F正常合并后补最终交接。正式RC仍未放行；干净VM安装/旧二进制升级/卸载重装、缺少/离线WebView2、真正只读磁盘、真实更新安装中断/二进制恢复、TTI/Heap/长期GPU/多DPI和点击关闭取消待验。
4. 正式信任根/签名feed、Authenticode、依赖许可及公开发布需人工条件，见HUMAN_ACTIONS_REQUIRED；测试根不编译为生产根，不要求现在提供Key/接受SDK协议。

## 运行与资料边界

日常主机Windows11家庭中文版22631，有开发工具，无经验证干净VM。原8000本轮未运行；private/front-data、原创项目、第三方模型和旧WebUI原件未启动/改动，没有远程AI发送。

自建8001/8002服务经命令/父子/端口复核后已停止；100000及101201生成库integrity_check=ok、外键无异常。自建浏览器页已关闭，用户8000页未动。D原生Front/Sidecar/WebView自有进程已退出。PID记录只取证，不能按旧PID盲杀。生成库/私有截图保留.cache；截图含桌宠叠层未公开。

首次C本机PyInstaller曾完成于默认用户cache，随后固定项目.cache和TEMP重建，没有额外清理默认用户cache。所有后续受控输出在E盘项目，未删除用户资料。原始素材不进入Git或安装包。长期Live2D/Krita/数位板/真实AI/OC/小说语义/3D/游戏音声特典及插件继续保留FEATURE_BACKLOG。

不虚构离线后台持续运行；当前状态以实际进程和private/RC_SPRINT_STATUS.json为准。
