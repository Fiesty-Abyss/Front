# TTS adapter contract foundation

本增量包含统一Python协议、Mock标记音、固定GPT-SoVITS wire contract与可显式启用的Mock后台流程。没有将真实引擎暴露为浏览器合成API，也没有安装/下载/启动推理、声库或训练环境。

## 能力与来源

TTSAdapter提供health/capabilities/list_voices/validate_voice/synthesize/cancel及可选train。能力必须逐项说明；不支持的voices和training返回Unsupported。Mock输出一秒220Hz标记音，speech=false、origin=mock，不是朗读或声音克隆，不支持语速等音色参数。

GPT-SoVITS合同仅核对官方[api_v2.py固定提交04a44eb977586645f33594b72af13a035a2056c6](https://github.com/RVC-Boss/GPT-SoVITS/blob/04a44eb977586645f33594b72af13a035a2056c6/api_v2.py)。用POST /tts、JSON字段text/text_lang/ref_audio_path/prompt_text/prompt_lang/speed_factor/seed，输出选非流式WAV。Front仍流式读取HTTP响应以限制内存/体积；不会把接口参数streaming_mode=false说成服务端逐片生成。

该文件没有独立声库枚举、health或单请求cancel接口，不能猜测。health只GET FastAPI的openapi.json并检查/tts请求字段，runtime_verified和server_revision_verified仍false，不代表权重/推理可用。取消只合作停止客户端读取，无法保证外部GPU任务停止；不调用/control或切换服务端权重。训练未支持。

## 安全与校验

- 只有调用者显式构造适配器才创建HTTP客户端；默认不联网，不启服务。端点必须匹配显式allowed_origins，禁止URL凭据/查询/片段；不跟随重定向。未来公开API仍须做独立认证、出口/DNS与配置授权评审，不能让浏览器提交任意代理URL。
- GPT请求须有参考音频使用权声明和来源、参考路径/语言/文本；没有授权先拒绝，不发请求。服务端路径不意味着Front上传或复制音频，也不代表Front已取得声库/模型发布许可。本轮全部测试使用生成标记音和虚拟路径，不执行真人克隆。
- 参数白名单及范围检查，未知参数明确拒绝；模型/声线UID和版本、台词、参数、合同版本参与指纹。Mock请求同时使用VoiceRender唯一uid承载持久幂等；实际引擎授权接入必须复用该门槛。
- 请求超时、网络中断、HTTP错误、格式/体积异常均为稳定错误代码，不回显上游正文、路径、密钥。输出只允许空的调用者自有流；失败/取消清理本次半成品，不改原文件。
- WAV校验PCM格式、采样率/声道、声明帧数和实际长度；响应最多64MiB、固定块读取并计算Hash。非法/截断/非WAV不能入素材库。现有Audio Library仍是唯一播放器和媒体入口。

## 验证边界与后续

test_tts_contract用HTTPX MockTransport及生成WAV验证确切字段、二进制输出、无授权零请求、禁止重定向、超时/取消/中断/体积/坏文件拒绝和原输出保护。CI通过只是协议/Mock证据，不是实际GPT-SoVITS推理、音质、延迟或许可验收。没有新第三方依赖（httpx原已存在），本模块不由main默认导入。

现有jobs与VoiceRender已接入持久Mock幂等、限流/取消/恢复与ingest音频；真实服务由用户之后授权测试。再接确认章节的有声小说工程。CosyVoice/IndexTTS/F5/云API、数据集和训练保持Backlog，不复制多套UI。


## 当前增量补齐：仅Mock队列闭环

本PR还接入了现有jobs/VoiceRender/ingest：只有显式设置FRONT_ENABLE_VOICE_MOCK=1且请求confirm_mock=true才开放mock-requests接口，默认404；产品不默认添加测试生成功能。任务只有生成标记音，不是真实语音。uid唯一约束持久标识幂等请求，同一键/指纹返回原记录，键复用到不同请求409；失败后使用新键显式重试。

复用2worker+32队列、进度和取消；候选/音频不自动采纳，参数指纹和音频版本保留。启动时queued/running标为interrupted，绝不自动重放。取消只控制此Front任务，不停用户服务。即使工作线程先完成，写入job_id也通过原子JSON更新保留完成的音频引用。失败/取消保留台词和历史。入库后限额校验实际托管字节，重复副本损坏时拒绝采纳，不自动覆盖。

新增test_voice_tasks覆盖默认关闭、确认门槛、幂等、队满、显式重试、运行取消和重启不重放；生成WAV和隔离数据库，所有真实GPT调用仍仅MockTransport协议测试。真实引擎仍需未来授权接入，Mock闭环在本PR实现并须通过CI。有声小说仍是下一阶段。
