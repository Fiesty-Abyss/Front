# Voice Studio foundation 接续 · 2026-11-07

已核对文档PR #43三项CI通过并正常合并；当前功能分支基于main ff3049775f0d527661e6948d386309072b47bfbc。功能PR待Actions，准确head/PR与后续结果由GitHub查询，不提前宣称通过。

已实现代码范围见VOICE_STUDIO：三类档案、角色/OC隔离、试听引用、偏好/标签、版本/恢复与六表结构。Project/Segment/Render仅预留，尚无台词工程或合成API。新增生成WAV/隔离DB回归及备份恢复测试；未执行本机应用/GUI/硬件/真实TTS。

工作方式：无已保存Codex Cloud，GitHub集成写403；用户后续允许读取本机PRD，现有gh登录拥有写权限。源checkout不变，只在Front缓存暂存API提交载荷，Actions运行测试。不启动本机服务、不用私人素材，不发布Release。

下一步：检查功能PR的backend/python310/frontend以及路径触发的Windows CI，修复后普通合并，取remote main再开独立分支。优先复现并修复笔记move/PATCH树约束；通用CRUD已捕获过滤器ValueError，不再误报该点。之后推进台词工程、TTS协议/Mock、有声小说；官方适配器需先核对固定版本的API，不猜接口。保留全部长期路线与既有RC未通过的验收边界。
