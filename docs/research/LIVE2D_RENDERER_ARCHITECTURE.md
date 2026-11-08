# Live2D渲染边界与隔离协议原型

2026-11-08。本文区分参考项目的声明、Front实现与未验证能力。Front仍是Vue + FastAPI + SQLite + Tauri；本原型不渲染Live2D、不启动GPU/摄像头、不读取模型文件，也没有静态图片替代渲染。

## 参考版本与证据

只读锁定Bandori `2ed1304c25a9000bdbe75c64ca1b0acac123be38`：[后端架构](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/docs/NEOCARI_BACKEND.md)、[模型管理](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/bandori_models/model_manager.py)、[点击规则](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/bandori_live2d/live2d_click_actions.py)、[IPC实现](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/native/pet_backend/src/ipc.rs)。未构建或运行其代码，不使用其私有模型/性能数值充当Front验收。

该文档声称支持moc/moc3、独立Rust/wgpu/winit进程、透明窗口与离屏PNG、动作/口型/点击和追踪；说明Windows通过DX12/DirectComposition处理透明合成、macOS/遮挡状态有不同生命周期顺序。这些是来源项目的声明，Front没有独立复现其GPU兼容性。实际Neocari gitlink为`5ef8f49654e2cdfeb60dbbdca28c1159558da775`，不是文档/NOTICE保留的旧f4eee3。其Cargo描述CubismV2不能据此推出moc3完全不支持，也不能据来源文档认定用户所有moc3可渲染。

[Neocari实际许可证](https://github.com/HELPMEEADICE/Neocari/blob/5ef8f49654e2cdfeb60dbbdca28c1159558da775/LICENSE)及[Bandori NOTICE](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/native/pet_backend/NOTICE.md)是GPL-3.0-only。Front MIT不复制实现、特定动作桶/区域阈值、共享内存布局/魔数或下载器；独立进程并不自动解决组合分发许可，正式接入前仍需单独审查。Cubism SDK/Core和素材授权另行确认，不代接受条款。

## 官方SDK核对（2026-11-08）

官方开源Samples/Framework当前记录到5-r.5（2026-04-02）：动作更新调度、追踪参数和颜色API有变化，不能把旧封装直接认作兼容。[Samples固定提交](https://github.com/Live2D/CubismWebSamples/blob/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd/CHANGELOG.md)、[Framework固定提交](https://github.com/Live2D/CubismWebFramework/blob/d4da0aa07e47d2c1e4f5fa7ea6047861ea5e5d0b/CHANGELOG.md)。Samples的[Core更新记录](https://github.com/Live2D/CubismWebSamples/blob/b1de66b0b1f1cb881d95fb6158622aeb6a2827bd/Core/CHANGELOG.md)列出06.00.0001；这是源码记录，不是本机已安装/已获得的运行时版本。

[官方兼容说明](https://docs.live2d.com/en/cubism-sdk-manual/compatibility-with-cubism-5-3/)明确旧SDK不能读取5.3导出的较新MOC，且Framework调用也有迁移变化。未来适配器须同时锁定Core/Framework/Samples及模型实际版本，以运行时能力与真实模型验证，不能只凭扩展名或moc头检查作出渲染承诺。

[官方Core说明](https://docs.live2d.com/en/cubism-sdk-manual/cubism-core/)仍说明Core不公开于GitHub；[下载页面](https://www.live2d.com/en/sdk/download/web/)要求先同意两类协议，且提示Latest托管版本可能影响兼容。本轮只读页面，没有勾选、下载、启动、托管或再分发Core。

[Expandable Applications规则](https://www.live2d.com/en/sdk/license/expandable/)要求此类应用发布前审查与特别协议，不能直接套用普通个人/小型开发豁免。基于Front允许用户添加不定数量模型的设计，可能涉及此分类，属于功能推断，仍需向Live2D确认；用户模型个人用途授权不能替代SDK/应用公开发布资格。

## 架构对比与Front决策

| 项目 | Bandori来源描述/源码观察 | Front适配方案 |
| --- | --- | --- |
| UI与持久化 | PySide6设置/聊天；角色渲染进程不加载Python/Qt | Vue工作区 + FastAPI唯一业务写入方；Tauri仅窗口/受控子进程，不再引入Qt |
| 渲染 | 每角色Rust原生窗口，设置中显示离屏PNG | 首先评估有合法许可的Web SDK按需画布；如必须原生，再独立RendererAdapter。列表只封面，隐藏预览不常驻多个渲染器 |
| 缓存 | 归档资源有大小/版本LRU与批读预算；模型管理部分扫描缓存写在来源根目录 | Front只写自己的cache，不沿用对模型目录写缓存的行为；来源只读；复用现有扫描诊断/Asset引用 |
| 控制 | 文件映射共享队列，生命周期/控制与高频位置分开 | 当前自研JSON行CLI控制原型；未来高频输入只保留最新状态，可靠动作要ACK。没有复制二进制布局，不因研究而新增共享内存依赖 |
| 动作 | 模型声明集合校验，项目特定区域/动作优先级 | Front只使用运行时真实枚举的参数/范围/动作；不硬编码微笑/F1/标准口型参数名，点击区由用户映射而非搬运来源规则 |
| TTS | 来源原生后端处理口型及追踪 | Voice输出未来提供本地幅度/时间戳；显式映射到实际模型参数，合成/播放结束或模型更换清理。此原型仅验证归一化幅度消息，不分析或播放音频 |
| 生命周期 | 各平台窗口/合成与遮挡处理不同 | 父窗口持有自身进程句柄，关闭/崩溃/EOF释放；未来Windows Job Object复用桌面既有归属机制。不能按进程名广杀外部服务 |

只读档案参数来自JSON/CDI引用，不等于SDK完整枚举。未来适配器必须从真实运行时发布能力目录/范围，不能把扫描成功等同能播放。

## 已实现的无模型原型

`backend/front_api/live2d_protocol.py`只用标准库，未导入普通应用启动链。`RendererAdapter`定义load/update/action/release边界，默认NullRenderer只计生命周期；没有网络监听、外部二进制加载、模型/贴图读取、渲染线程或GPU。它拒绝实际模型路径和任何非`generated-protocol-only`目录。用户Studio依旧显示档案模式，本CLI未挂接GUI或HTTP。

显式运行：

```sh
python -m front_api.live2d_protocol --null-preview
```

stdin/stdout是版本1的UTF-8 JSON行。每行最多16KiB、每次进程4096条；输出也受16KiB限制。请求包含version、32位十六进制id、op、payload。先hello，再load生成能力目录；status/update/motion/expression/mouth/unload/shutdown均有白名单。load完全验证后更换当前目录，generation递增，旧世代消息拒绝。15/30/60只是待实现帧率上限配置，**本原型真实帧数始终0**。

参数只允许声明名称和有限数值范围；整体控制先验证再应用。口型参数须显式指定，幅度0–1按声明范围映射；不假定ParamMouthOpenY。表情可以开关组合，未声明动作拒绝。视图有位置/缩放/旋转/透明/可见状态，没有实际透明窗口、鼠标命中、头追/道具或TTS声音。

最近128个成功请求ID缓存原ACK，重复同内容不再次执行动作；同ID不同内容拒绝。此处是有界最近窗口，超过窗口不能保证永久幂等，未来持久动作需项目版本/序列而非声称无限去重。控制状态只保留最新值，无无限队列。shutdown/EOF释放；适配器失败关闭会话且不透出原始异常。返回renders/runtime_verified=false、graphics_contexts/frames=0，不把状态字段当OS/GPU实测。

## 验证与未完成

21项定向测试通过（最新0.32秒）：握手、非法真实模型/路径、参数/NaN/重复JSON字段/版本/预算、旧世代、动作/表情/口型、最近请求幂等/冲突、错误适配器、101次切换释放与实际自有CLI子进程的shutdown/EOF/超长输入。没有创建或停止用户Front/旧WebUI等服务。CLI为测试自己启动并等待退出的子进程，非桌宠/GPU验收。

最终本机完整后端542通过/1权限跳过194.91秒，15前端及构建6.18秒通过；远程Windows/兼容结果见本PR接续记录，未通过前不合并。没有数据库/API/前端路由变更或新依赖。没有真实GPU/RSS/FPS/贴图泄漏、Cubism兼容、第三方模型、摄像头、原生窗口/干净安装验收。

下一阶段：许可确认→合法适配器→真实运行时能力目录与资源预算→孤立预览/GPU释放→动作/点击/服装预设→道具/透明窗口→Voice口型→可选桌宠/追踪。玄宝酱素材只按个人非商用、学习/桌宠/静态截图等既有授权使用，禁止直播/商用/虚拟主播与二次发布；原件不入仓库、公开演示先核对署名和许可。Voice真实TTS、Krita/数位板、OC/生图、小说语义、3D、游戏音声/特典、正式安装与签名更新继续保留。
