"""Conservative identity hints, never an authority to merge user records."""
import re
import unicodedata
from difflib import SequenceMatcher


def normalized(value):
    return re.sub(r'[\s\W_]+', '', unicodedata.normalize('NFKC', value or '').casefold())


def identity(value):
    # Punctuation can distinguish an edition or a different title (e.g. A+B / AB).
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '').casefold())


def confidence(title, candidate, author=None, year=None):
    names = [candidate.get(k) for k in ('title', 'title_cn', 'original')]
    names += (candidate.get('aliases') or [])[:30]
    query = normalized(title)
    names = [normalized(n) for n in names if isinstance(n, str) and n]
    exact = bool(query and any(identity(title) == identity(n) for n in [candidate.get(k) for k in ('title', 'title_cn', 'original')] + (candidate.get('aliases') or [])[:30] if isinstance(n, str) and n))
    score = max((SequenceMatcher(None, query, n).ratio() for n in names), default=0)
    reasons = []
    authors = [normalized(a) for a in candidate.get('authors', []) if isinstance(a, str)]
    conflict = bool(author and authors and normalized(author) not in authors)
    if conflict:
        reasons.append('作者不一致')
    date = candidate.get('date') or candidate.get('release_date') or ''
    candidate_year = candidate.get('year') or (int(date[:4]) if str(date)[:4].isdigit() else None)
    if year and candidate_year and abs(int(year) - int(candidate_year)) > 1:
        conflict = True
        reasons.append('年份不一致')
    if not exact:
        reasons.append('标题未完全匹配；系列、本篇、续作和改编须人工区分')
    tier = 'exact' if exact and not conflict else 'weak'
    if exact and author and not authors:
        tier = 'strong'
        reasons.append('来源未提供作者，无法核对')
    return {'tier': tier, 'score': round(score, 3), 'reasons': reasons,
            'requires_confirmation': True}


def rank(title, items, author=None, year=None):
    for item in items:
        item['match'] = confidence(title, item, author, year)
    exact = {str(i.get('sid')) for i in items if i['match']['tier'] == 'exact'}
    if len(exact) > 1:
        for item in items:
            if item['match']['tier'] == 'exact':
                item['match']['ambiguous'] = True
                item['match']['reasons'].append('同一来源存在多个完全匹配的独立条目')
    return sorted(items, key=lambda i: (i['match']['tier'] == 'exact', i['match']['tier'] == 'strong', i['match']['score']), reverse=True)
