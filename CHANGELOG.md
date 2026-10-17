# 更新日志

## v0.1.0 · 2026-10-17

第一轮：项目骨架与全部核心模块的第一版。

- 后端：FastAPI + SQLite，素材 / 标签 / 作品 / 世界观 / 角色 / 关系 / 收藏集 / SD 模型 / 提示词 / 出图记录 / 角色卡 / 对话会话的完整增删改查 API
- 全文检索：FTS5 trigram，中文子串可搜，增删改即时同步索引
- 素材上传：尺寸识别、缩略图、SHA256 去重、按年月存储；SD WebUI PNG 参数自动提取；txt/md 小说导入（UTF-8 / GB18030 / Shift-JIS）
- 关系网接口与可视化（Cytoscape.js），AI 建议关系需人工确认
- 提示词“同一提示词 × 不同模型”对比视图
- SD 模型登记：读取 safetensors 元数据、判断底模、计算 SHA256
- 角色卡：Character Card V2 JSON / PNG 导入导出（兼容 V1、V3），从百科角色生成
- AI 接口层：OpenAI 兼容 Provider；角色扮演对话（带上下文、{{char}}/{{user}} 占位符）；世界观关系识别
- 前端：Vue 3 管理界面，覆盖以上全部模块
- 内置【示例】数据脚本，测试 35 项，GitHub Actions CI，仓库卫士测试
