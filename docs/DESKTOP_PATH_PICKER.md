# 桌面本机路径选择

## 范围

复用现有导入、预览和扫描业务；选择只填写路径，仍需用户按“扫描预览 / 读取信息 / 确认导入”。不新增文件数据库，不扫描整盘、不启动推理，也不改写源文件。

| 入口 | 选择目标 | 后续操作 |
| --- | --- | --- |
| Discovery 新建来源 | 单个目录 | 原有根目录配置、深度、忽略及预算；已保存路径仍不可直接修改 |
| 素材导入 | 单个目录 | 原有只读预览与导入确认 |
| 项目预览 / 小说资料目录 | 单个目录 | 原有 ProjectPreview 与世界观归档 |
| Audio Library / 通用归档面板 | 单个目录 | 共用 LibraryImportPanel，不复制第二套索引 |
| 模型库 | 模型目录或单个权重文件 | 原地登记；读取或 Hash 仍需明确按钮 |
| Live2D Studio | 单个目录或 ZIP/RAR | 原有包预算和资源诊断；没有新增运行时或真实渲染 |

小说单文件、OC 参考图片继续使用已有浏览器原生文件上传及 Asset 选择，不增加没有业务消费方的路径输入。网页连接远程 Front 时，手动路径指向运行后端的电脑；不把本地浏览器选择说成远程磁盘授权。

## 权限和生命周期

仅 Windows 桌面主窗口、该实例随机回环端口获得 `allow-desktop-pick-path`。Rust 命令再次核对窗口名和完整 origin，不能由个人 Web 8000、外部网页、其他窗口或启动页借用。目的枚举和文件过滤固定，不接受任意命令、路径访问脚本或 URL。

使用官方 `tauri-plugin-dialog = 2.8.4` 的 Rust builder，**不授予** `dialog:default`、`dialog:allow-open` 或 FS 权限；没有调用会自动扩展 asset/FS scope 的 JS open 命令。插件的 `tauri-plugin-fs` 仅为上游类型依赖，Front 不注册 FS 插件。选中路径不会赋予父目录或整盘的额外范围；后端继续按原有本地应用访问与路径校验规则处理，不声称它是新的 OS 沙箱。

一个实例只允许一个选择窗口。回调持有互斥租约，IPC 接收方离开不会在原对话框仍打开时允许第二个；结束回调才释放。取消返回 null；用户同时改输入、禁用字段或离开页面时，迟到结果不覆盖当前输入。无常驻轮询、摄像头、音频或额外后台进程。

## 依赖审查

按 frontend-tooling-trust-gate 核对官方维护者、API、许可证与安装脚本。项目局部 Cargo 锁文件仅新增 dialog 2.8.4、其 fs 2.7.1 和 rfd 0.17.2；没有 npm 新依赖、注册表镜像切换或全局安装。官方插件为 MIT OR Apache-2.0；构建许可证清单沿用既有 inventory。Windows-only 依赖，不承诺尚未验收平台。

原始依据：[官方 Dialog 文档](https://v2.tauri.app/plugin/dialog/)、[Rust API](https://docs.rs/tauri-plugin-dialog/2.8.4/tauri_plugin_dialog/trait.DialogExt.html)、[官方源码](https://github.com/tauri-apps/plugins-workspace/tree/v2/plugins/dialog)。

## 当前验证边界 · 2026-11-09

- 生成路径/取消/显式调用/无浏览器桥接/错误脱敏及 Vue 输入迟到保护等前端 **28 项通过**，生产构建 **8.18 秒**；不是操作系统对话框验收。键盘 Enter 仅从输入触发原操作，选择按钮不会冒泡误触扫描。
- Rust origin、固定目的与单窗口租约测试纳入 Windows CI。锁解析成功，仅新增三项；本机 cargo check 因缺失 MSVC `link.exe` 停止，未声称 Rust 编译通过，也未安装全局工具链。
- 本机后端全量 **605通过 / 1权限跳过 / 1失败**（230.24秒），失败为既有 Windows 进程身份测试；单组再跑8通过/1同失败，诊断确认 Get-CimInstance Win32_Process 返回 HRESULT **0x80004005**，无法提供进程清单。未改遥测断言或系统/WMI配置。不是本增量编译或GUI结果；保留原始日志，独立 Windows CI 仍须逐项核对。
- Windows 编译/打包和真实原生选择 GUI 尚待当前 head 验证。PR 保持 Draft，不能只因 Node 构建绿而合并。
- 独立生成目录验收应覆盖中文/空格路径、文件/目录选择、取消、手动修改、切换页面、不同来源、键盘以及窄屏。不能以伪造 Tauri 标志的网页代替原生验收。
- 不重试之前被审批拒绝的聊天验收服务，不通过本任务顺便完成或宣称聊天 GUI。个人库/8000/安装、原始小说和模型未操作。
