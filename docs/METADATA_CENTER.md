# 联网资料匹配中心

`/metadata` 按需加载，手动确认检索词/作者或 SHA256 后才联网。复用 Work、Galgame、原有 Bangumi/VNDB/Ymgal、Civitai 与 jobs，不加载推理引擎，不自动创建/合并作品、人物、世界观或标签。

## 本增量可用范围

| 来源 | 种类 | 行为与限制 |
| --- | --- | --- |
| Open Library | 图书/小说 | 官方 search.json 和 works/OL…W.json；书名/可选作者、作品级详情。不是具体出版社/ISBN 版次鉴定，不猜测作品级缺失作者名/年份/出版商 |
| Bangumi / VNDB / 月幕 | 游戏 | 复用已有 search/detail；详情不额外抓取角色。游戏与动画改编不混为同类 |
| Civitai | SD 模型/LoRA | 仅 SHA256 查询版本，复用 lookup/summarize；有声明 Hash 时检查一致性。不读/复制权重、不启动服务；应用仍由现有模型档案确认 |
| Google Books / NextMoe | 未接入 | 前者专用 API 身份未配置；后者公开接口和许可尚待核实。不借用聊天 API Key |

动漫/漫画专门匹配、ISBN/Edition/语言检索、更完整作者详情、跨来源自动互补和统一模型字段历史仍待后续增量。不能把能力目录或来源链接视为这些功能已完成。

## 身份与应用

- Exact 为规范化后标题/别名相同，Strong 为标题相同但待核对的作者证据不足，其他只是 Weak；同来源多个 Exact 明确标歧义。年份/作者冲突降级。符号仍参与身份比较（A+B 不等于 AB）。这些等级不是 AI 概率或正确性保证，全部仍需人工选条目。
- 旧游戏自动补来源和快速添加也改为保守精确身份；本篇标题不再因包含于 Fan Disc/续作名称而自动接受。显式 accept_first 保留为用户主动选择，不能后台调用绕过歧义。
- 选择已有 Work/Galgame，比较每个字段。非空人工值、人工清空、未授权刷新的旧值需要逐字段确认替换；一个字段冲突则整个本次应用回滚。不会覆盖个人备注、评分或文件。
- `metadata_catalog` 保存 schema、字段原始标准化值/采用值、provider、外部 ID/链接、获取时间、人工修改状态及允许显式刷新的标志。现有编辑器改动受管字段会标记 manual。不同来源可在不同字段上互补，不自动猜测不同来源条目为同一作品。
- 后端使用服务端短期详情凭据，不接受客户端伪造来源值。应用前验证目标身份/内容指纹并在短 SQLite BEGIN IMMEDIATE 事务内写入；事务中不联网。另一个窗口保存后返回409，须重新载入核对。
- 复用不可变版本：应用前快照和之后变更都保留，恢复追加版本。作品列表/游戏列表不附带大 catalog，专用目标接口按需获取。新中心应用的游戏字段加入旧 overrides，旧刷新也不能静默覆盖。
- 手动上传的游戏封面独立标记；普通元数据刷新保留它，用户明确保存来源封面或显式重置覆盖规则才替换。新中心只保存候选地址，不自动下载封面。

## 队列、网络与隐私

`GET /api/metadata/providers` 返回能力/开关；`POST /search`、`POST /detail` 要求 online=true，返回既有后台 Job。搜索最多四来源，每来源十候选；共用2 worker/32等待预算，来源逐个处理，单来源门控间隔至少1.1秒。取消在来源调用/门控之间生效，不能声称中断已经发出的同步 HTTP。部分来源失败保留其他结果，错误不包含远程异常中的令牌/私有地址。

本地 metadata-cache 是可重建、至多128个 JSON文件的短期缓存/预览凭据，TTL一小时；重启不重放网络任务。正式字段来源/历史在数据库中，随完整备份保护，不依赖缓存恢复。Open Library 显式流式 JSON 上限2MiB、12秒网络超时/5秒连接超时、禁止重定向。旧游戏/Civitai适配器继续用已有15/20秒客户端；它们的响应读取尚未全部改为统一流式预算，不宣称旧网络层已全面加固。

`FRONT_METADATA=off` 关闭新中心联网入口；原有 FRONT_GALGAME/FRONT_CIVITAI 开关仍生效。只有用户输入的标题/作者或 Hash 会发送；不从扫描根自动发送文件名、路径、正文、私人设定或文件。应用/恢复本身不联网。用户主动点外部来源/封面链接会联系相应网站，界面明确提示；不自动加载所有候选封面。

## 数据升级与验证

只给 works、galgames 增加 JSON metadata_catalog 默认空对象；既有升级前一致性快照流程先运行。新增 Galgame 版本种类，不迁移/重置历史内容。旧列缺失补齐、原行保留、完整备份隔离恢复、integrity_check 和 foreign_key_check 已用生成数据库验证；不在个人活动库执行测试。

验收见 [2026-11-08 记录](audits/metadata/CENTER_20261108.md)。这不是多人租户系统；沿用 Front 本机访问保护，不能把本地缓存凭据称为完整多用户授权机制。

## 官方资料与许可

- [Open Library Search](https://openlibrary.org/dev/docs/api/search)、[现代书籍/作品 API](https://openlibrary.org/dev/docs/api/books)、[使用准则/限流](https://openlibrary.org/developers/api)：面向用户主动查询、缓存、默认1请求/秒，非批量抓取后台。Front UA 标明项目仓库，未冒充提供用户联系邮箱或提升配额；公开部署前仍需登记/联系资料提供方。
- [Open Library licensing](https://openlibrary.org/developers/licensing)、[Covers](https://openlibrary.org/dev/docs/api/covers)：并非所有贡献与封面都获得无条件再分发许可；保留原始来源链接，不批量抓取或打包封面。
- [Google Books 使用](https://developers.google.com/books/docs/v1/using)、[VNDB Kana](https://api.vndb.org/kana)、[月幕开发者说明](https://www.ymgal.games/developer)：身份、非商业/限流和来源条款分别适用，不代用户接受协议。各来源真实可用性与接口变化需持续验证。

## ISBN版次后端增量

ISBN校验/OL…M具体版次、来源身份及人工保护已独立实现，详见[BOOK_EDITIONS](BOOK_EDITIONS.md)；OL…W书名查询保持。无新增UI、自动封面下载/标签翻译、跨源自动合并或个人数据迁移。实际GUI待验，最终测试和CI以NEXT_SESSION为准。
