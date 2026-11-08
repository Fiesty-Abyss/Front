# 资料发现、角色互动与渲染参考初查

2026-11-08只读查阅，不执行参考仓库的命令、安装依赖、复制代码或导入模型。本文只记录研究证据，完成状态以Front实际功能PR为准。

## 固定参考版本

- KoiPage：`f0e844aa6d706013b6ef50ba43778479f3671fe2`。[根配置](https://github.com/morilove37/KoiPage/blob/f0e844aa6d706013b6ef50ba43778479f3671fe2/src-tauri/src/commands/scan_roots.rs)、[扫描器](https://github.com/morilove37/KoiPage/blob/f0e844aa6d706013b6ef50ba43778479f3671fe2/src-tauri/src/scanner/mod.rs)、[匹配规则](https://github.com/morilove37/KoiPage/blob/f0e844aa6d706013b6ef50ba43778479f3671fe2/src-tauri/src/metadata/matching.rs)。配置根与主动扫描分开，启发式目录发现、深度与重解析点保护；匹配分级且警惕同系列/短名碰撞。Front保留现有文件导入与SQLite，不移植Rust/React或自动执行游戏启动器。
- KoiPage仓库[LICENSE](https://github.com/morilove37/KoiPage/blob/f0e844aa6d706013b6ef50ba43778479f3671fe2/LICENSE)标记GPL-3.0，作为设计参考，不复制其实现进Front。
- BandoriPet：`2ed1304c25a9000bdbe75c64ca1b0acac123be38`。[架构文档](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/docs/NEOCARI_BACKEND.md)描述每角色独立Rust渲染进程、wgpu/winit透明窗口、离屏预览、UI与渲染分界、有限资源缓存及控制/高频消息分流。[NOTICE](https://github.com/HELPMEEADICE/BANDORI-PET-REV/blob/2ed1304c25a9000bdbe75c64ca1b0acac123be38/native/pet_backend/NOTICE.md)说明本项目及Neocari为GPL-3.0-only，并记录Neocari提交f4eee3e95ec27530a1ebfdb60aa6bd478b4cabbc；不能因其保留历史MIT notice而认为现有整体可直接引入MIT Front。完整源码/许可证及进程协议对照在独立Live2D研究阶段继续，不据本文声称已可渲染。
- [Faraday](https://faraday.dev/)当前重定向[Backyard](https://backyard.ai/)，官方页面说明服务已停止、正常云功能关闭。只保留历史“本地角色卡/参数管理”的产品方向参考，不将其当作当前可集成服务、有效API或可验证的现役界面。
- [Saylo](https://www.sayloai.com/)本次直接访问超时，尚无可靠接口/当前UI证据。不抓取登录/付费内容，不猜测其私有API。Front多模式互动按用户需求和既有ChatSession/消息树设计，分别验证。

## Front复用与待办

进一步核对：Bandori上述固定树实际vendor/neocari gitlink是`5ef8f49654e2cdfeb60dbbdca28c1159558da775`，与NOTICE/部分注释保留的旧f4eee3不同。[实际Neocari Cargo](https://github.com/HELPMEEADICE/Neocari/blob/5ef8f49654e2cdfeb60dbbdca28c1159558da775/Cargo.toml)和[LICENSE](https://github.com/HELPMEEADICE/Neocari/blob/5ef8f49654e2cdfeb60dbbdca28c1159558da775/LICENSE)仍为GPL-3.0-only（0.4.0）；不能用旧注释代替树指针或许可审查。已只读model_manager与click_actions相关源码，借鉴轻量元数据缓存、按实际声明动作/表情校验绑定，不复制源码、项目特定模型名/点击区或下载逻辑。F原型尚未因此实现。

联网中心首闭环见[实际范围](../METADATA_CENTER.md)；书籍接口基于官方API和许可资料，不搬运KoiPage GPL代码。Google Books身份/NextMoe公开API与许可尚未核实完成，不假称可用。

扫描增量复用ProjectPreview/LibraryImport/ProjectImport/Asset/jobs，只增加来源配置。联网资料仍需审查现有Bangumi/VNDB/Ymgal和Civitai实现，再加统一能力/来源/人工覆盖协议；书籍Provider、跨来源字段来源和歧义策略不能凭扫描候选认为完成。

角色卡、ChatSession、Lorebook和消息分支已经存在；一对一/群聊/叙事/选项的实际能力、逐角色Provider快照与生成调度需逐项源码/测试验收，不直接堆叠第二套聊天存储。桌面Sidecar/实例令牌/随机端口已存在；原生目录选择和外部导航仍按独立增量处理。

Front Live2D现为只读档案，不含Cubism/Neocari运行时。后续优先独立、自己实现的渲染器接口/有界动作协议/受控进程生命周期与无模型测试；没有合法运行时和真实模型渲染证据时不得用静态图宣称完成。玄宝酱模型与Cubism SDK/Core及公开分发资格仍分别核对，不接受协议或打包第三方素材。
