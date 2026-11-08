"""Bounded edition identity helpers. No network, model or database initialization."""
import re


def isbn(value):
    """Return canonical ISBN-13; reject explicit/ISBN-shaped invalid identifiers."""
    if not isinstance(value, str):
        return None
    explicit = bool(re.match(r'^ISBN(?:-1[03])?\s*[: ]', value.strip(), re.I))
    raw = re.sub(r'^ISBN(?:-1[03])?\s*[: ]\s*', '', value.strip(), flags=re.I)
    compact = re.sub(r'[\s-]', '', raw).upper()
    if not explicit and not (len(compact) in (10, 13) and re.fullmatch(r'[0-9X]+', compact)):
        return None
    if re.fullmatch(r'[0-9]{9}[0-9X]', compact):
        digits = [int(v) if v != 'X' else 10 for v in compact]
        if sum((10-i)*v for i, v in enumerate(digits)) % 11:
            raise ValueError('invalid ISBN checksum')
        stem = '978' + compact[:9]
        return stem + str((-sum(int(v)*(1 if i % 2 == 0 else 3) for i, v in enumerate(stem))) % 10)
    if re.fullmatch(r'97[89][0-9]{10}', compact) and sum(int(v)*(1 if i % 2 == 0 else 3) for i, v in enumerate(compact)) % 10 == 0:
        return compact
    raise ValueError('invalid ISBN')


def identifiers(raw, size):
    values = raw if isinstance(raw, list) else []
    out = []
    for value in values[:20]:
        if not isinstance(value, str):
            continue
        compact = re.sub(r'[\s-]', '', value).upper()
        try:
            valid = isbn(compact)
        except ValueError:
            continue
        if valid and len(compact) == size and compact not in out:
            out.append(compact)
    return out


def edition(raw, expected=None, requested_isbn=None):
    if not isinstance(raw, dict) or not re.fullmatch(r'/books/OL[0-9]{1,18}M', str(raw.get('key', ''))):
        raise ValueError('invalid edition identity')
    sid = raw['key'].split('/')[-1]
    if expected and sid != expected:
        raise ValueError('different edition returned')
    tens, thirteens = identifiers(raw.get('isbn_10'), 10), identifiers(raw.get('isbn_13'), 13)
    if requested_isbn and requested_isbn not in {isbn(v) for v in tens + thirteens}:
        raise ValueError('ISBN does not belong to returned edition')
    def refs(field, pattern):
        values = raw.get(field)
        return list(dict.fromkeys(v['key'].split('/')[-1] for v in values[:20]
                    if isinstance(v, dict) and isinstance(v.get('key'), str) and re.fullmatch(pattern, v['key']))) if isinstance(values, list) else []
    authors = raw.get('authors')
    covers = raw.get('covers')
    date = raw.get('publish_date') if isinstance(raw.get('publish_date'), str) else None
    year = re.search(r'(?<!\d)([12]\d{3})(?!\d)', date or '')
    publishers = raw.get('publishers')
    description = raw.get('description')
    if isinstance(description, dict):
        description = description.get('value')
    return {'sid': sid, 'title': raw.get('title'), 'description': description,
            'publisher': ', '.join(v[:200] for v in publishers[:10] if isinstance(v, str)) if isinstance(publishers, list) else None,
            'year': int(year[1]) if year else None, 'publish_date': date, 'edition_name': raw.get('edition_name'),
            'record_type': 'edition', 'isbn_10': tens, 'isbn_13': thirteens,
            'languages': refs('languages', r'/languages/[a-z]{3}'), 'work_ids': refs('works', r'/works/OL[0-9]{1,18}W'),
            'authors': [v['name'] for v in authors[:20] if isinstance(v, dict) and isinstance(v.get('name'), str)] if isinstance(authors, list) else [],
            'url': 'https://openlibrary.org/books/' + sid,
            'covers': [f'https://covers.openlibrary.org/b/id/{v}-L.jpg?default=false' for v in covers[:4] if type(v) is int and v > 0] if isinstance(covers, list) else []}
