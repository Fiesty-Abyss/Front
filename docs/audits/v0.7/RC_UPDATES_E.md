# RC E：真实Updater传输与兼容性拒绝

复用已有官方Tauri Updater、签名版本、来源/通道和完整备份屏障。生产下载来源、IPC、正式公钥缺省和安装策略不变；未引入新依赖。当前构建仍不注册正式Updater，不能把本测试当成更新上线。

## 新增测试

- 一次性官方CLI测试密钥和一天有效测试TLS CA；CA只注入测试客户端，不安装系统信任。payload是明确标注非安装器的生成文本。
- 实际HTTPS分块慢传，真实下载progress触发后中止Future，确认取消且不触发完成回调；真实服务提前断开连接且声明更长Content-Length，下载失败而非形成可安装结果。
- 低版本manifest经SDK check返回无更新；现有正确/错误签名、错误密钥、签名版本重放、传输篡改、未信任TLS和平台拒绝测试保留。
- 官方SDK解析更新对象后调用已有生产validate：本地测试传输不能通过生产来源校验；不实际下载的固定仓库生成URL用于验证预览/稳定通道、便携目标不匹配、未知通道、不支持的备份格式、最低源版本及稳定通道预发布版本拒绝。
- 生成夹必须为当前checkout.cache下全新目录，拒绝外部和已有输出。Windows在生成密钥前设置仅当前用户/SYSTEM ACL并确认继承保护；Unix目录0700/私钥0600。不打印CLI捕获的私钥输出。失败保留隔离夹，不清理用户未知目录。

## 实测状态

本机最终265后端/8前端测试及生产构建通过；已通过official signer、真实Python HTTPS完整/中断传输和受限测试夹检查（transport-only），以及两项输出边界负向测试。**本机没有MSVC，Rust新增八项回归必须以Windows CI结果确认**；transport-only输出明确rust_sdk_tests=not run、installation_executed=false。

CI执行真实SDK网络/签名测试，不调用install。安装过程异常退出、断电/安装器回滚、旧/新程序二进制恢复和真实便携替换尚未验收，依赖干净隔离环境。现有生成DB/媒体完整备份和恢复测试不能替代这些场景；正式信任根与公开Release仍需独立授权。
