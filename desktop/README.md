# Front Windows Preview

这是未签名的 Windows x64 测试包，不是 v0.7 正式发布，也没有自动更新功能。

安装版使用系统用户数据目录（`%LOCALAPPDATA%/io.github.fiesty-abyss.front`），程序与资料分离。便携版解压后打开 `Front.exe`；同目录的 `Front.portable` 标记启用独立 `FrontData`。请完整保留 `backend` 文件夹，不要只复制 EXE。只读目录会停止启动，移动至可写目录后重试；不会重置数据库。

有经验的用户可通过 `FRONT_DATA_DIR` 自定义数据目录；普通用户无需命令、Python、Node、Rust或显卡。WebView2使用Windows已安装的运行时；安装包在缺少时引导下载微软运行时，便携包目前要求系统已有WebView2。完整离线运行时包后续提供。

首次运行自动创建资料库。已有资料升级前检查结构，发现未知未来结构拒绝降级；有迁移时生成完整备份并在隔离目录验证恢复，再沿用Web版迁移逻辑。缺失素材会阻止默认升级，请在Web版检查备份报告。外部原地索引文件默认只保存路径引用。

关闭窗口会停止本窗口拥有的后台服务，强制结束窗口进程也会通过Windows Job Object关闭所属Sidecar。不会停止已运行的Web版或AI服务。不启动SD/ComfyUI/Ollama，不扫描私人目录。摄像头和模型推理不会自动启动。

日志位于资料目录的 `logs/desktop.log`，仅记录生命周期和错误类型，轮转限制1MiB×4，不写API Key或访问日志。WebView缓存位于该资料目录的 `webview`。私人数据、模型、密钥不属于安装包构建输入。

卸载/升级程序后保留用户数据；删除便携目录前自行保管其中FrontData。恢复完整备份先在隔离目录校验，不能覆盖运行中的数据库。当前不提供程序内无缝切换数据目录与签名更新。

依赖来源：Tauri官方CLI/Rust库（MIT/Apache-2.0），PyInstaller官方发行（GPL及打包例外）；应用依赖的声明与可用许可证文本随 `backend/licenses`、`THIRD_PARTY_NOTICES.json` 提供。公开正式发布前仍需完成依赖和安装器验收、代码签名与更新签名，不携带任何Live2D专有SDK或第三方模型。
