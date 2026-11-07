# TTS合同基础接续 · 2026-11-07

本增量基于最新main 1f329e495a524e681ced1f0799b725bee9bf480f；前序PR由GitHub核实通过并正常合并。当前合同PR仍须核对CI/合并，不能提前当成通过。

已提交范围：统一协议/能力/错误、Mock一秒标记音、固定官方GPT-SoVITS合同/显式端点许可/授权参考/WAV校验及MockTransport测试。没有真实TTS、克隆、训练或本机GUI测试。本模块不由main加载，没有新依赖/模型下载。

下一步：取本PR真实head与四项CI，失败修复、成功普通合并；当前已实现现有jobs与VoiceRender的Mock幂等/取消/恢复，验收后从remote main推进确认章节的有声小说。真实引擎尚不向浏览器开放，禁止自动启服务或调用API发送私人数据。然后推进确认章节有声小说、说话候选证据及独立朗读稿。

客户端取消不保证外部任务停止；没有真实voices/health/cancel端点就不得编造，不用/control杀用户服务。正式发布/密钥/许可和所有长期路线继续保留。

网络恢复后现有gh API写入和Actions已可用；本机只缓存载荷与指定PRD读取，没有改变个人应用/资料或运行本机测试。结束前在接续中记录最终main/PR/CI，不承诺永久后台执行。


## 当前增量补齐：仅Mock队列闭环

本PR还接入了现有jobs/VoiceRender/ingest：只有显式设置FRONT_ENABLE_VOICE_MOCK=1且请求confirm_mock=true才开放mock-requests接口，默认404；产品不默认添加测试生成功能。任务只有生成标记音，不是真实语音。uid唯一约束持久标识幂等请求，同一键/指纹返回原记录，键复用到不同请求409；失败后使用新键显式重试。

复用2worker+32队列、进度和取消；候选/音频不自动采纳，参数指纹和音频版本保留。启动时queued/running标为interrupted，绝不自动重放。取消只控制此Front任务，不停用户服务。即使工作线程先完成，写入job_id也通过原子JSON更新保留完成的音频引用。失败/取消保留台词和历史。入库后限额校验实际托管字节，重复副本损坏时拒绝采纳，不自动覆盖。

新增test_voice_tasks覆盖默认关闭、确认门槛、幂等、队满、显式重试、运行取消和重启不重放；生成WAV和隔离数据库，所有真实GPT调用仍仅MockTransport协议测试。真实引擎仍需未来授权接入，Mock闭环在本PR实现并须通过CI。有声小说仍是下一阶段。


## 下一轮准确入口

#44/#45/#46已正常合并，功能基线main 1f329e495a524e681ced1f0799b725bee9bf480f；本PR头/CI需GitHub实时核实，成功后普通合并取新main。长期任务继续保留。

Voice-D部分源代码草稿位于工作缓存voice-books-edit：models.txt/service.txt/router.txt/tests.txt，未提交/未运行。需要重新审查并补prepare、模型/路由/启动恢复注册、UI来源选择和说话人确认、字幕/章节输出及完整备份回归；不能直接调用不存在的模块或把草稿算完成。优先沿用chapterplans.source_text和已确认ChapterRevision、同一Asset/VoiceProject/VoiceSegment以及jobs。

长篇队列只捕获ID/指纹，不把全文放入闭包；源文本复用现有32MiB上限，默认仅两个worker。分次导入应有持久游标/稳定片段uid、取消和重启不重放；引用区间指向不可改写原文，标点/姓名标签规则只是待确认候选，不是AI识别证据。拆分/合并不能误标不同章节来源，单句保存继续要求expected_segment_version。书籍来源/角色需要作品和世界观身份校验。

本机源checkout仍未同步或改动；远程编辑载荷在Front缓存，实际测试仅Actions。原始个人小说/模型/音频均未读取用于测试。没有真实TTS/克隆/训练/GUI/硬件/干净安装验收，公开Release与正式签名仍需用户授权。
