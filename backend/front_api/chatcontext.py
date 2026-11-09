"""Whole semantic units for request-only trimming; never mutate stored messages."""
def units(messages):
    result = []
    for i, message in enumerate(messages):
        if message['role'] == 'system':
            continue
        if message['role'] == 'user' or not result:
            result.append([])
        result[-1].append(i)
    return result


def trim(messages, limit=None, max_messages=40):
    groups = units(messages)
    total = sum(len(m['content']) for m in messages)
    count = sum(len(g) for g in groups)
    mandatory = sum(len(m['content']) for m in messages if m['role'] == 'system')
    if groups:
        mandatory += sum(len(messages[i]['content']) for i in groups[-1])
    if limit is not None and mandatory > limit:
        from fastapi import HTTPException
        raise HTTPException(422, '角色设定、世界书与最新完整轮次超过预算；请明确增加预算，不静默截断人设或问答')
    omitted = []
    for number, group in enumerate(groups[:-1], 1):
        if (limit is None or total <= limit) and (max_messages is None or count <= max_messages):
            break
        chars = sum(len(messages[i]['content']) for i in group)
        omitted.append({'turn': number, 'positions': group, 'roles': [messages[i]['role'] for i in group], 'characters': chars})
        total -= chars
        count -= len(group)
    removed = {i for group in omitted for i in group['positions']}
    samples = [{**group, 'positions': group['positions'][:8], 'roles': group['roles'][:8],
                'messages': len(group['positions'])} for group in omitted[:20]]
    return [m for i, m in enumerate(messages) if i not in removed], {
        'characters': total, 'limit': limit, 'max_history_messages': max_messages,
        'dropped_messages': len(removed), 'dropped_turns': sum('user' in g['roles'] for g in omitted),
        'dropped_units': len(omitted), 'dropped_introductions': sum('user' not in g['roles'] for g in omitted),
        'omitted': samples, 'omitted_details_truncated': len(omitted)>20 or any(len(g['positions'])>8 for g in omitted),
        'omitted_through': max(removed) if removed else None,
        'unit': 'characters-not-tokens', 'turn_definition': 'user-and-following-assistants; introductions-counted-separately'}
