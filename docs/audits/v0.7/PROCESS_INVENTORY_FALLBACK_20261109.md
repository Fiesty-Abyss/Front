# Windows 只读进程清单回退 · 2026-11-09

## 有证据的缺陷

现有 `desktop/profiling.py` 仅使用 PowerShell/CIM 的 Win32_Process。当前主机多次返回0x80004005/空清单，使 `test_windows_process_handle_matches_inventory_and_rejects_wrong_birth` 失败。相同故障在未改此工具的 #72/#74 工作树出现，分别为605通过/1跳过/1失败和618通过/1跳过/1失败。Get-Process、现有Win32内存查询则可读取当前测试进程。

没有修改WMI、系统服务、权限、隐私或安全设置。不是放宽失败测试或把未知内存记为零。

## 改动

1. 保留有效CIM清单及WebView2详细角色；仅当CIM失败、格式异常或无法验证根进程时回退。
2. 使用Windows自带 `CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS)`、`Process32FirstW/NextW` 读取PID、父PID与名称；不枚举模块/线程或读取进程内容。
3. 只为请求的候选进程树打开 `PROCESS_QUERY_LIMITED_INFORMATION` 句柄，用 `GetProcessTimes` 获取创建时间。所有快照与进程句柄在finally关闭，无提权、下载、新依赖、终止或注入进程。
4. 在快照前记录FILETIME；快照后才出生的PID可能已经被复用，身份按未知处理。继续复用原 `verified_tree` 排除早于父进程的子PID、歧义、循环和未验证边；未知覆盖仍导致相应总量为null。
5. 回退显式标记 `inventory_method:toolhelp`。没有CIM命令行时，WebView2子角色为 `webview2_unknown`，不能伪称浏览器/渲染器/GPU角色已区分。
6. GPU前后身份检查沿用既有句柄检查的1微秒精度容差，兼容CIM微秒与原生100ns FILETIME的表示差异；真实身份变化仍拒绝。

7. 快照前UTC边界使用[GetSystemTimePreciseAsFileTime](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemtimepreciseasfiletime)的高精度时间，避免粗粒度时钟落在刚创建进程之前。保留“快照后出生则未知”规则，不增加宽松时间窗口；目标Windows10/11具备该API（官方最低Windows8）。

这只是显式执行的开发测量工具，不加入Front启动路径、Sidecar常驻任务或角色桌面Agent。没有改产品业务、SQLite架构、用户资料或模型文件。

## 官方API核对

- [PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)：使用正确Unicode字段、指针宽度及dwSize。
- [Process32NextW](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-process32nextw)：只有ERROR_NO_MORE_FILES视为正常结束；其他中断不输出“完整”清单。
- [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)：限定查询权限及创建时间。

依据接口规范原创实现，没有复制GPL代码或引入SDK运行时。

## 验证边界

专项15项通过，包含原有失败用例、强制CIM不可用的真实Windows当前进程和专属Python子进程、创建时间不匹配拒绝、PID快照竞争、只查询候选树、拒绝访问、WebView2角色未知、正常CIM优先以及GPU混合精度。

真实子进程仅执行生成的限时等待，使用独立基础解释器避免venv启动器产生额外孙进程，finally终止并wait回收；不启动网络服务、AI或用户软件。模拟行验证和真实Windows API验证分别保留，不等于干净安装、产品启动性能或真实GPU显存验收。

正常合入已验收的#72主线 c351084d684219b838f821d8fea43ce5bd6a679a 后，本机完整后端 **612通过/1既有跳过，187.37秒**；前端 **22项通过**，生产构建 **7.37秒**。此前原CIM失败已在本机真实Windows API回退下通过；没有将其跳过。

精确head远端CI结果在PR与NEXT_SESSION收尾记录。所有长期创作、Soul/聊天/Voice/Live2D、绘画、大库和正式桌面发布计划保留。

## 首轮Windows失败与后续修正

旧head9b8fd4b的Windows42634383975实际失败：611通过/1跳过/1失败，714.37秒；强制CIM失效的真实专属子进程未出现在验证清单。没有把这项失败跳过。该日志没有保留原始快照/创建时间，无法确定是初始化可见性还是时钟边界，不宣称已经复现其唯一原因。本机30次即建即测生成子进程均通过，最接近快照的创建时间仍早约2ms。

现修正测试fixture为等待专属子进程stdout的ready（5秒上限），不靠固定sleep/重试；仍要求同一PID/父PID、真实内存与错误出生时间拒绝，失败会打印有界元数据便于诊断，finally回收子进程/管道/就绪线程。同时产品采样改高精度UTC，以消除文档确认的粗时钟比较风险。最新head必须重跑完整本机及WindowsCI；e14后端曾成功也不代替修正后的精确head。
