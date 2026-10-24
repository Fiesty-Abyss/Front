"""Explicit OpenAI Images-compatible adapter. Credentials stay in existing providers.

Only base64 image outputs are supported; no arbitrary remote output URL fetching.
See https://developers.openai.com/api/reference/resources/images .
"""
import base64
import binascii
import httpx
from .sdgen import BackendError

client_factory=lambda **kw:httpx.Client(**kw)


def generate(provider,service,prompt,size,check):
    payload={'model':service.model,'prompt':prompt,'size':size,'n':1}
    if service.legacy_b64:payload['response_format']='b64_json'
    headers={'Authorization':'Bearer '+provider.api_key} if provider.api_key else {}
    try:
        # Bound encoded response as well as decoded image; never log keys or response bodies.
        with client_factory(timeout=min(provider.timeout or 120,300),follow_redirects=False) as client:
            with client.stream('POST',provider.base_url.rstrip('/')+'/images/generations',headers=headers,json=payload) as response:
                if response.status_code!=200:raise BackendError(f'图像API返回HTTP {response.status_code}；请核对服务和图像模型能力')
                data=bytearray()
                for block in response.iter_bytes():
                    check();data.extend(block)
                    if len(data)>48*1024*1024:raise BackendError('图像API响应超过48MiB上限')
        import json
        value=json.loads(data);encoded=value['data'][0]['b64_json']
        image=base64.b64decode(encoded,validate=True)
        if not image:raise ValueError()
        return image,value['data'][0].get('revised_prompt')
    except BackendError:raise
    except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError,binascii.Error):
        raise BackendError('图像API连接失败或未返回有效base64图像；聊天接口不能替代图像生成') from None
