# 阶段D：构建产物与正式发布门槛

本报告为阶段D实施前的只读审查，未改动构建脚本。审查时main为`7ca4654`，阶段A/B的PR #29/#30已通过CI并常规合并；阶段C的PR #31仍等待官方Updater Windows SDK测试结果。下文“已有”指受审代码的实际行为，不表示阶段D建议已经实现或正式发布已获批准。

受审文件主要为`.github/workflows/windows-preview.yml`、`desktop/package_portable.py`，并对照`archive_tools.py`、`build_sidecar.py`、桌面版本配置及通用CI。

## 已有构建链

Windows预览workflow通过`workflow_dispatch`或匹配路径的PR触发，权限只有`contents: read`。顺序为：安装构建依赖 → 后端测试 → 前端测试和生产构建 → 冻结Sidecar → 冻结HTTP冒烟 → 最小PATH启动/迁移回归 → 许可清单 → 阶段C真实签名/本地HTTPS测试driver → Tauri/NSIS → 便携包及Hash → 上传内部artifact。

普通步骤失败会阻止后续正常上传。失败诊断只保存Cargo.lock；没有`continue-on-error`跳过质量步骤，也没有创建GitHub Release的步骤。阶段C新增的SDK测试步骤仍需对应CI的真实成功结论，不能把workflow中存在命令视为运行已通过。

| 产物或检查 | 当前实际行为 | 已有边界 |
| --- | --- | --- |
| Python Sidecar | PyInstaller onedir，仅公共后端包及前端dist；新stage替换时保留旧stage到独立目录，不合并未知旧文件 | 校验front-backend.exe存在，并拒绝front.db、.env、ai-providers.json三个文件名；不是完整隐私白名单 |
| 冻结运行 | HTTP冒烟和最小System32 PATH回归位于上传之前 | 不是干净Windows VM，不替代安装器/缺WebView2/卸载升级矩阵 |
| Tauri/NSIS | Windows x64原生构建，安装器名须包含tauri.conf.json当前版本，且匹配数必须为1 | 目前不校验PE版本、Authenticode或安装结果 |
| 便携包 | 仅组装Front.exe、backend、Front.portable、README、LICENSE、THIRD_PARTY_NOTICES；每次创建新临时bundle | 根文件是明确输入，但backend整个子树被递归复制，尚无最终ZIP内容政策验证 |
| ZIP基础安全 | 拒绝符号链接和越出bundle边界；流式写入；兼容1980年前的上游时间戳 | 不等于敏感文件检测、ZIP CRC复验或完整性清单 |
| 附带文件 | Cargo.lock、THIRD_PARTY_NOTICES.json | 有依赖锁和许可声明，不等于全部许可已完成正式发行审查 |
| SHA256 | 对输出目录中的现有文件逐一流式计算，写SHA256SUMS.txt | 没有独立重新打开并验证清单，也没有检查清单漏项/额外文件 |
| 内部artifact | 上传stage/artifacts；不存在文件时失败；保留14天 | 无统一机器可验BUILD_MANIFEST，不能由artifact名推断版本、源码或正式发布资格 |
| 正式更新签名 | 阶段C支持官方签名验证，缺少正式公钥时关闭更新 | 测试签名/本地CA不使预览包成为正式可更新发布 |
| 正式Release | 无创建或公开发布步骤，contents权限只读 | 当前保持禁止自动正式发布 |

## 具体差距

### 1. 动态版本与产物身份

`package_portable.py`的便携ZIP名仍硬编码`Front-0.7.0-preview.1-windows-x64-portable.zip`，安装器则按Tauri配置动态筛选。仅更新版本配置可能得到旧名ZIP和新名安装器。

桌面版本还分别出现在`tauri.conf.json`、`Cargo.toml`和`desktop/package.json`，当前打包脚本不核对一致性。后端/Web版本属于独立业务版本，不应未经说明强制改成桌面版本。

**建议D实施：**确定桌面版本的读取来源，核对三处桌面声明，统一生成便携/安装/清单名称；记录后端/Web版本作为独立字段。Windows数值PE版本与SemVer预发布字符串须记录各自值及映射，不直接把二者做字符串相等判断。所有产物写入精确源码Commit和构建run，版本不能仅依赖文件名。

### 2. 缺少可机器核对的内部产物清单

现有输出缺少统一的格式版本、源码、平台、产物类型、大小、Hash、文件集合和检查结果。日志、README及artifact名无法组成自动门槛。

**建议D实施内部构建清单**（如`BUILD_MANIFEST.json`，名称以实现为准）：

- `schema_version`、`distribution=internal_preview`、源码SHA、构建run/attempt、桌面版本、目标平台/架构。
- installer/portable/lock/notices等必须产物的角色、相对名、大小和SHA256，列明预期集合，拒绝漏项和未声明额外文件。
- 运行时/前端/后端版本、工具与依赖锁指纹、ZIP策略/CRC/运行回归/签名等检查的实际状态，使用passed/failed/not_run/not_configured等明确值，不用缺省true。
- `formal_release_allowed=false`及未满足的门槛；当前正式公钥缺失、真实安装升级未完成时，不生成“可正式发布”的结论。

清单只包含必要公开构建元数据，不写绝对用户路径、命令行、环境变量全集、密钥或数据库内容。应明确Hash覆盖关系，避免让清单和SHA文件互相包含自身Hash形成循环依赖。

### 3. ZIP隐私白名单不够完整

目前安全性主要来自显式构建输入和新stage，已有已核验预览包未包含模型权重；但最终递归backend子树仍缺少机器可验内容政策。仅拒绝三个文件名不能覆盖改名数据库、缓存、原始媒体、测试私钥或误放入stage的私有目录。

**建议D实施：**

- 根层只允许声明的程序、标记、README、LICENSE、依赖声明及backend目录；新增加根文件必须显式进入政策和清单。
- 对backend来源记录PyInstaller/资源输入范围，并在最终ZIP层拒绝FrontData/private/测试fixture/测试runtime/测试key目录、个人数据库及权重等禁止项；检查路径大小写、路径穿越、重复/冲突名、链接和异常条目。
- 文件类型政策需保留合法运行资源。例如Python/SQLite动态库、公共TLS CA证书、许可文本和发布签名文件不是用户数据库或私钥，不能简单禁止所有证书/PEM/签名文件。
- 私钥检查只输出脱敏文件定位和命中类别，不把秘密内容打印到日志；使用生成的假私钥/假数据库注入测试拒绝路径，不扫描或拷贝用户真资料。
- ZIP生成后重新打开，做CRC和条目集合校验；提取验证到隔离目录，确认必要EXE/DLL/前端资源和空数据便携标记。样本规则测试不能代替实际产物扫描。

NSIS也必须使用已校验stage并记录Tauri资源范围；便携ZIP扫描不能单独证明安装器内的所有资源都符合政策。

### 4. Hash与产物完整性需要独立复验

当前SHA256SUMS仅记录“当时目录里有什么”，没有反向证明“该有的都有、只有允许的文件”。生成Hash本身也不是发行者身份认证。

**建议D实施：**打包后独立复读所有声明文件、比对大小与SHA256，检查缺失、额外、重复或清单之外的文件；复核ZIP结构/CRC及角色和版本，失败返回非零并阻止artifact上传。保留Cargo.lock与许可清单的Hash和实际对应关系。下载后的GitHub artifact摘要校验属于传输证据，应与包内逐文件Hash区分。

### 5. 更新清单、签名和正式发布是不同门槛

| 门槛 | 当前差距 | D阶段应有的处理 |
| --- | --- | --- |
| 版本/平台/通道/数据兼容 | C客户端已有检查，产物端尚无机器一致性门槛 | 核对版本、平台角色、稳定/测试通道、最低源版本与备份格式，记录清单与实际产物一致性 |
| Tauri更新签名 | 正式签名私钥/公钥未配置，不能据throwaway测试密钥签正式包 | 内部模式明确not_configured，继续允许测试artifact；正式发布模式必须拒绝缺少或不匹配的正式签名/公钥 |
| signed version | C已配置requireSignedVersion，真实SDK测试仍待CI | 使用官方工具绑定实际桌面版本，正负验签结果作为证据；不重标旧包或用假signature字段通过校验 |
| Windows Authenticode | 现流程没有验证生产证书/安装器签名 | 记录未配置/未验证，不把更新签名等同Windows代码签名；正式发布需真实证书和独立校验 |
| Release说明 | 当前仅复制README，没有绑定该版本的changelog门槛 | 要求对应版本说明并记录来源/摘要，拒绝缺失或版本错配；不凭Commit数量生成升级提示 |
| 安装/升级验收 | B本机最小PATH回归不是真干净VM，真实安装/卸载/升级仍未全覆盖 | 把环境和未覆盖矩阵作为正式发布阻断项，不由一个布尔“已测试”掩盖 |
| 公开发布 | 没有自动Release授权和发布步骤 | 本轮继续只上传内部artifact；任何正式Tag/公开Release须另行明确批准并通过全部门槛 |

若后续正式签名会改变EXE字节，应先完成相应签署，再生成最终Hash与更新签名/清单并复验，避免对签名前字节计算的Hash被用于签名后产物。更新公钥、更新私钥、Authenticode、TLS证书和Cubism/素材许可分别处理。

没有正式密钥或发布授权时，可以产出明确命名的内部候选清单/模板，但不能把占位签名、测试钥或未发布URL伪装成可用生产latest.json，也不能上传到正式更新入口。

### 6. workflow触发范围和证据归档

当前Windows预览PR过滤包含desktop、desktop入口、特定desktop测试和本workflow；单独改动其他后端路由、维护屏障、前端或根LICENSE/说明时，不保证触发这条Windows产物链。通用CI会跑后端/前端测试，但不覆盖冻结包和安装器。

**建议D实施：**按实际打包输入扩大触发范围或提供明确的强制构建机制，确保影响运行/版本/资源/发布说明的变更能触发所需门槛。记录实际runner和工具版本、精确Commit、CI结果及产物摘要。`windows-latest`/已有开发工具的runner仍不能被归类为干净用户系统。

正式发布未来应基于精确目标Commit重新满足门槛。当前PR预览和manual dispatch不等于版本Tag自动发布，本轮不增加未经批准的公开发布路径。

## 建议的D验收用例（尚未实现）

| 类别 | 最小正向 | 最小负向/故障 |
| --- | --- | --- |
| 版本 | 桌面三处版本一致、名称动态变化 | 只改一处版本、SemVer非法、旧名ZIP/新名安装器错配 |
| 文件集合 | 必须产物齐全且无额外文件 | 缺EXE/运行库/锁/说明，混入未声明文件 |
| Hash | 独立复读与清单一致 | 改一字节、错大小、漏列/多列、重复文件记录 |
| ZIP | CRC与白名单通过，隔离解压可用 | 穿越/链接/大小写冲突、FrontData/数据库/权重/假私钥注入 |
| 更新候选 | 内部状态真实，生产更新关闭可解释 | 缺正式Key却声明可正式发布，假签名、错版本/平台/通道/备份格式 |
| 发布说明 | 对应版本说明及来源明确 | 缺失、空内容、错版本、说明与产物指纹不一致 |
| CI门槛 | 所有必要步骤成功后上传内部artifact | 验证失败终止上传，仅保留允许的诊断，不上传测试钥/数据库 |
| 正式发布阻断 | 未配置项和未验环境明确列出 | 尝试由内部artifact/PR合并直接转公开Release |

## 实施与接续

计划阶段D增加内部artifact机器可验清单、ZIP隐私白名单和动态版本命名；本报告尚未证明这些已实现。实施后应逐项记录Commit、相关自动测试、前端构建、实际产物复验和CI状态，按独立PR收敛。

真实安装/升级、正式密钥和公开Release仍依赖已批准环境与人工流程，见[HUMAN_ACTIONS_REQUIRED](../../HUMAN_ACTIONS_REQUIRED.md)及[Windows验证矩阵](DESKTOP_VALIDATION_MATRIX.md)。阶段C的真实工具/Mock/CI待验边界见[SIGNED_UPDATES_C](SIGNED_UPDATES_C.md)。本轮不读取或上传用户原始素材、私人数据库和Key。


## 本轮实现：内部产物校验

从C已合并main4153e1e建立独立分支。上文保留实施前的审查证据；以下实现取代对应差距，未列出的正式发布能力仍待。

- 桌面三处版本一致性和Tag匹配在构建前验证；便携名动态读取当前桌面版本。读取PE资源的ProductVersion和FileVersion，核对预发布或对应数值版本，未执行程序。
- BUILD_MANIFEST.json记录精确构建源码SHA、版本、Windows平台、精确输出集合、尺寸和流式SHA256。它明确声明internal-artifact-only、unsigned-preview、updater_enabled=false、installation_verified=false；不是Tauri latest.json更新源。带正式公钥的构建拒绝走本预览管线。
- 清单包含产物Hash，不包含自己的Hash；SHA256SUMS包含清单，排除自身。随后重新打开文件并校验集合、内容和Hash，额外文件、遗漏或改动均停止上传。
- ZIP最终检查拒绝越界/非法Windows路径、大小写重名、符号链接、已知用户数据目录/数据库/日志/Key文件和私钥PEM。合法公共CA包保留。检查内置Python/VCRuntime、外壳和后端PE头、必要声明文件及所有成员CRC。PEM扫描有界分块；总解压尺寸上限1GiB。
- 输入仍为明确公共构建stage；ZIP规则是附加的已知路径/格式防线，不声称能发现二进制内任何未知秘密。SHA256不提供签名真实性，不能替代正式信任根与安装验收。
- Windows workflow覆盖backend/frontend变更和版本Tag；Cargo构建使用--locked。Tag只构建内部artifact，没有Release写权限/发布动作，失败阻止正常附件上传。

生成ZIP正负样本15项通过；既有经核验预览产物实际CRC/Hash/结构与PE版本检查通过。测试未运行安装器。本机251后端/3前端资源测试/生产构建通过（97.76秒/7.07秒）。独立Windows流水线尚待本PR核对。

未完成：正式签名安装包与签名更新清单的发布产物一致性、正式Release审批与保护环境、变更日志提取、干净系统安装/升级验收、Authenticode和实际失败恢复。当前正式发布仍关闭，不以内部清单替代这些门槛。


开发环境兼容补充：项目最低Python3.10，校验工具使用tomllib并在3.10回退到[Tomli官方解析器](https://pypi.org/project/tomli/2.0.1/)。依赖仅声明在dev/构建环境的Python<3.11条件，不加入核心服务常驻依赖或3.12冻结包；新增真实Python3.10专项CI，最终结果待本PR检查。
