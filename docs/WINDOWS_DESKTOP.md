# Windows 桌面测试交付

独立Tauri 2外壳加载同一份Vue生产构建。Python业务通过PyInstaller onedir冻结为Sidecar，Rust直接管理资源目录中的可执行文件，不向远程Vue页面开放Shell/文件系统IPC能力。打包输入仅后端公共包、前端dist、图标、许可证与白名单资源，不归档整个工作目录。

## 生命周期和访问边界

- 后端预绑定127.0.0.1随机空闲端口并保留socket，不争用Web开发版8000端口。启动完成后通过私有stdout管道发送端口、PID和随机令牌；原生外壳校验PID。
- 引导URL的令牌仅在fragment，立即清除并换取HttpOnly/SameSite严格cookie。所有业务和静态请求须认证，Host及Origin须匹配本实例；跨站访问拒绝。令牌不写配置、日志或localStorage。
- 正常退出用仅原生令牌可调用的停止接口，等待最多8秒后仅终止自有子进程。Windows Job Object绑定Sidecar，外壳异常终止时关闭所属进程树；不遍历或终止其他Python/AI/Web服务。
- 数据目录锁防止两个桌面实例并发使用同一库。现有Web进程不共享该锁，不应人为给二者配置相同数据目录。默认安装与便携数据目录均与已有Web数据分离。
- 安装模式使用标准用户目录，便携标记启用程序旁FrontData，可用FRONT_DATA_DIR覆盖。WebView缓存与轮转生命周期日志也在该目录。权限不足拒绝启动，不清空或重置数据。

## 升级与备份

启动前拒绝未来未知表/字段或损坏库。有结构变更时复用完整托管媒体备份，默认不复制外部原件，Hash校验并在独立恢复目录试迁移后，才运行共用create_all/upgrade。完整备份有缺失资源时停止默认升级。安装和卸载不自定义删除个人数据。

## 构建与当前验证

本机没有Rust/MSVC，使用Windows Actions runner构建NSIS安装器与便携ZIP，先跑后端测试、前端构建及冻结Sidecar真实HTTP启动/认证/写入/退出检查，再上传带SHA256清单的测试附件。失败步骤不会上传测试包；没有Release、Tag触发发布或Updater，也没有签名密钥。首次构建Cargo解析结果将保留Cargo.lock以固定后续构建。

本机源代码Sidecar已有真实回环启动退出测试，另有Host/Origin/cookie/原生停止权限、数据锁、未来结构拒绝与升级前隔离恢复测试。221项后端测试及前端构建通过。**冻结程序、原生窗口、安装器、CPU/RSS和启动速度在Windows构建完成后补充实测，当前不能认定验收完成。**

当前安装包缺少WebView2时通过微软引导程序下载运行时；便携版要求系统已有WebView2。纯离线运行时、安装/卸载升级矩阵、签名与正式更新仍待完成。用户不需要Python、Node、Rust或GPU。

构建工具可信度检查：官方Tauri CLI 2.12.4及Rust包（MIT/Apache-2.0），官方PyInstaller 6.22.3（GPL及打包例外）为preferred，仅项目本地/CI安装，不全局安装或索取新凭据。复制可用依赖许可证文本并生成声明清单，正式公开Release前继续审核。参考：[Tauri Sidecar](https://v2.tauri.app/develop/sidecar/)、[Windows安装器](https://v2.tauri.app/distribute/windows-installer/)、[PyInstaller许可](https://pyinstaller.org/en/stable/license.html)。
