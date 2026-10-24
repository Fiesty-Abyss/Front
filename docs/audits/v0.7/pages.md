# 页面检查与截图

2026-10-18；桌面 1440×1000，窄屏 390×844。样本为生成数据与 Mock 元数据，不是个人内容。首屏截图和加载检查不代表全部编辑/删除/导出分支均验收通过。

| 页面 | 路由 | 桌面截图 | 窄屏截图 | 窄屏内容宽度 px |
| --- | --- | --- | --- | --- |
| 笔记 | /notes/1 | [桌面](../../screenshots/v07-audit/notes-desktop.jpg) | [窄屏](../../screenshots/v07-audit/notes-mobile.jpg) | 982 |
| 图表列表 | /diagrams | [桌面](../../screenshots/v07-audit/diagrams-desktop.jpg) | [窄屏](../../screenshots/v07-audit/diagrams-mobile.jpg) | 469 |
| 图表编辑 | /diagrams/1 | [桌面](../../screenshots/v07-audit/diagram-editor-desktop.jpg) | [窄屏](../../screenshots/v07-audit/diagram-editor-mobile.jpg) | 879 |
| 批量导入 | /import | [桌面](../../screenshots/v07-audit/import-desktop.jpg) | [窄屏](../../screenshots/v07-audit/import-mobile.jpg) | 624 |
| 游戏库 | /galgames | [桌面](../../screenshots/v07-audit/galgames-desktop.jpg) | [窄屏](../../screenshots/v07-audit/galgames-mobile.jpg) | 397 |
| 游戏详情 | /galgames/1 | [桌面](../../screenshots/v07-audit/galgame-detail-desktop.jpg) | [窄屏](../../screenshots/v07-audit/galgame-detail-mobile.jpg) | 653 |
| 作品/CG | /works | [桌面](../../screenshots/v07-audit/works-desktop.jpg) | [窄屏](../../screenshots/v07-audit/works-mobile.jpg) | 641 |
| 收藏集 | /collections | [桌面](../../screenshots/v07-audit/collections-desktop.jpg) | [窄屏](../../screenshots/v07-audit/collections-mobile.jpg) | 703 |
| 标签 | /tags | [桌面](../../screenshots/v07-audit/tags-desktop.jpg) | [窄屏](../../screenshots/v07-audit/tags-mobile.jpg) | 436 |
| 角色百科 | /characters | [桌面](../../screenshots/v07-audit/characters-desktop.jpg) | [窄屏](../../screenshots/v07-audit/characters-mobile.jpg) | 380 |
| 角色详情 | /characters/1 | [桌面](../../screenshots/v07-audit/character-detail-desktop.jpg) | [窄屏](../../screenshots/v07-audit/character-detail-mobile.jpg) | 774 |
| 世界观 | /worlds | [桌面](../../screenshots/v07-audit/worlds-desktop.jpg) | [窄屏](../../screenshots/v07-audit/worlds-mobile.jpg) | 568 |
| 关系网 | /graph | [桌面](../../screenshots/v07-audit/graph-desktop.jpg) | [窄屏](../../screenshots/v07-audit/graph-mobile.jpg) | 380 |
| 小说阅读 | /read/45 | [桌面](../../screenshots/v07-audit/reader-desktop.jpg) | [窄屏](../../screenshots/v07-audit/reader-mobile.jpg) | 743 |
| 提示词 | /prompts | [桌面](../../screenshots/v07-audit/prompts-desktop.jpg) | [窄屏](../../screenshots/v07-audit/prompts-mobile.jpg) | 661 |
| 模型 | /models | [桌面](../../screenshots/v07-audit/models-desktop.jpg) | [窄屏](../../screenshots/v07-audit/models-mobile.jpg) | 839 |
| 提示词片段 | /snippets | [桌面](../../screenshots/v07-audit/snippets-desktop.jpg) | [窄屏](../../screenshots/v07-audit/snippets-mobile.jpg) | 667 |
| 出图 | /generate | [桌面](../../screenshots/v07-audit/generate-desktop.jpg) | [窄屏](../../screenshots/v07-audit/generate-mobile.jpg) | 817 |
| 角色卡 | /cards | [桌面](../../screenshots/v07-audit/cards-desktop.jpg) | [窄屏](../../screenshots/v07-audit/cards-mobile.jpg) | 601 |
| AI 对话 | /chat | [桌面](../../screenshots/v07-audit/chat-desktop.jpg) | [窄屏](../../screenshots/v07-audit/chat-mobile.jpg) | 535 |
| 世界书 | /lorebooks | [桌面](../../screenshots/v07-audit/lorebooks-desktop.jpg) | [窄屏](../../screenshots/v07-audit/lorebooks-mobile.jpg) | 867 |
| 角色抽取 | /extract | [桌面](../../screenshots/v07-audit/extract-desktop.jpg) | [窄屏](../../screenshots/v07-audit/extract-mobile.jpg) | 613 |
| 设置 | /settings | [桌面](../../screenshots/v07-audit/settings-desktop.jpg) | [窄屏](../../screenshots/v07-audit/settings-mobile.jpg) | 776 |
| 搜索 | /search?q=林汐 | [桌面](../../screenshots/v07-audit/search-desktop.jpg) | [窄屏](../../screenshots/v07-audit/search-mobile.jpg) | 380 |
| 总览 | / | [桌面](../../screenshots/v07-audit/dashboard-desktop.jpg) | [窄屏](../../screenshots/v07-audit/dashboard-mobile.jpg) | 380 |
| 素材库 | /assets | [桌面](../../screenshots/v07-audit/assets-desktop.jpg) | [窄屏](../../screenshots/v07-audit/assets-mobile.jpg) | 639 |

额外证据：

- [生成 GLB 实际渲染](../../screenshots/v07-audit/preview-glb.jpg)
- [生成 VRM 的明确降级](../../screenshots/v07-audit/preview-vrm.jpg)
- [Live2D 贴图/动作信息](../../screenshots/v07-audit/preview-live2d.jpg)
- [PDF](../../screenshots/v07-audit/preview-pdf.jpg)、[DOCX](../../screenshots/v07-audit/preview-docx.jpg)、[音频](../../screenshots/v07-audit/preview-audio.jpg)
- [损坏文件提示](../../screenshots/v07-audit/preview-broken-glb.jpg)
- [搜索打开对应素材](../../screenshots/v07-audit/search-opens-asset.jpg)
- [浅色主题](../../screenshots/v07-audit/search-light-desktop.jpg)

22/26 路由在窄屏出现横向溢出。笔记页编辑区位于首屏右侧之外；不要把横向滚动后的可见误写为移动适配已完成。
