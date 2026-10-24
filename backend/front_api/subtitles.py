"""Bounded local subtitle conversion. No transcription or external requests."""
import re,html,math


def seconds(value):
    parts=value.replace(',','.').split(':');result=sum(float(v)*60**i for i,v in enumerate(reversed(parts)))
    if not math.isfinite(result) or result>31536000:raise ValueError('字幕时间超出一年上限')
    return result


def timestamp(value):
    ms=max(0,round(value*1000));return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'


def convert(body,ext):
    cues=[]
    if ext=='.lrc':
        offset=re.search(r'\[offset:([+-]?\d+)\]',body,re.I);delta=int(offset[1])/1000 if offset else 0
        for line in body.splitlines():
            matches=list(re.finditer(r'\[(\d+:\d+(?:\.\d+)?)\]',line))
            if matches:
                text=line[matches[-1].end():].strip()
                for match in matches:cues.append((max(0,seconds(match[1])+delta),None,text))
        cues.sort(key=lambda c:c[0]);cues=[(start,cues[i+1][0] if i+1<len(cues) else start+10,text) for i,(start,_,text) in enumerate(cues)]
    else:
        pattern=r'((?:\d+:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*((?:\d+:)?\d{2}:\d{2}[.,]\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
        cues=[(seconds(a),seconds(b),text.strip()) for a,b,text in re.findall(pattern,body,re.S)]
    if len(cues)>10000:raise ValueError('字幕超过10000条，请拆分文件')
    out=['WEBVTT','']
    for start,end,text in cues:
        if end<=start:continue
        text=html.escape(re.sub(r'<[^>]*>','',text)).replace('-->','→')
        out.extend([f'{timestamp(start)} --> {timestamp(end)}',text,''])
    return '\n'.join(out)
