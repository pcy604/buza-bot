"""Content → 플랫폼별 Post. 코어는 같고 '쪼개는 수'와 형식만 다르다.

플랫폼 제한(2026-11 기준, 바뀌면 여기만 고친다):
  threads   : 글 500자, 이미지 ≤10(캐러셀), 답글 체인으로 이어쓰기
  x         : 280 가중치(한글·한자 1글자=2 → 한글 기준 140자), URL은 23, 이미지 ≤4
  instagram : 캡션 2,200자, 캐러셀 ≤10, 본문 링크 클릭 불가(프로필 링크로)
  naver     : 제한 없음, API 없음 → 마크다운 초안만
"""
from .models import Content, Post

X_LIMIT, THREADS_LIMIT, IG_LIMIT = 280, 500, 2200
X_URL_W = 23

def x_weight(s: str) -> int:
    """X 글자 가중치 — CJK·한글·이모지 2, 그 외 1 (URL은 호출부에서 23 고정)."""
    w = 0
    for ch in s:
        o = ord(ch)
        w += 2 if (0x1100 <= o <= 0x11FF or 0x3000 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF
                   or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFFEF or o >= 0x1F000) else 1
    return w

def _chunk(paras: list, limit: int, weight) -> list:
    """문단 목록을 limit 이하 덩어리로. 문단 하나가 limit를 넘으면 문장 단위로 자른다."""
    out, cur = [], ''
    def push():
        nonlocal cur
        if cur.strip():
            out.append(cur.strip())
        cur = ''
    for p in paras:
        if weight(p) > limit:                       # 문장 단위 분할
            sent = [s.strip() for s in p.replace('。', '.').split('. ') if s.strip()]
            for s in sent:
                s = s if s.endswith(('.', '다', '요', '!', '?')) else s + '.'
                if weight(cur + '\n' + s) > limit:
                    push()
                cur = (cur + '\n' + s).strip()
            continue
        if weight(cur + '\n\n' + p) > limit:
            push()
        cur = (cur + '\n\n' + p).strip()
    push()
    return out

def _numbers_block(c: Content) -> str:
    return '\n'.join(f'· {n}' for n in c.numbers)

def to_threads(c: Content) -> Post:
    first = c.hook
    body = list(c.core)
    if c.numbers:
        body.append(_numbers_block(c))
    tail = [x for x in (c.takeaway, ('⚠️ ' + c.caveat) if c.caveat else '') if x]
    cta = f'{c.cta}\n{c.cta_url}'.strip() if c.cta else ''
    texts = [first] + _chunk(body, THREADS_LIMIT, len) + _chunk(tail, THREADS_LIMIT, len)
    if cta:
        texts.append(cta)
    texts.append(c.disclaimer)
    return Post('threads', texts, c.images[:10], note='첫 글에 대표 이미지, 나머지는 답글 체인')

def to_x(c: Content) -> Post:
    def w(s):   # URL 23 가중치 반영
        tot, rest = 0, s
        for tok in s.split():
            if tok.startswith('http'):
                tot += X_URL_W + 1
                rest = rest.replace(tok, '')
        return tot + x_weight(rest)
    body = list(c.core)
    if c.numbers:
        body.append(_numbers_block(c))
    tail = [x for x in (c.takeaway, ('⚠️ ' + c.caveat) if c.caveat else '') if x]
    texts = _chunk([c.hook], X_LIMIT, w) + _chunk(body, X_LIMIT, w) + _chunk(tail, X_LIMIT, w)
    if c.cta:
        texts += _chunk([f'{c.cta}\n{c.cta_url}'.strip()], X_LIMIT, w)
    texts += _chunk([c.disclaimer], X_LIMIT, w)
    # 번호 붙이기 (1/N)
    n = len(texts)
    numbered = []
    for i, t in enumerate(texts, 1):
        tag = f' ({i}/{n})'
        numbered.append(t + tag if w(t + tag) <= X_LIMIT else t)
    return Post('x', numbered, c.images[:4], note='한글은 140자 상당. 번호는 자리 남을 때만')

def to_instagram(c: Content) -> Post:
    parts = [c.hook, ''] + list(c.core)
    if c.numbers:
        parts += ['', _numbers_block(c)]
    if c.takeaway:
        parts += ['', c.takeaway]
    if c.caveat:
        parts += ['', '⚠️ ' + c.caveat]
    if c.cta:
        parts += ['', f'{c.cta} → 프로필 링크']
    parts += ['', c.disclaimer, '', ' '.join('#' + t for t in c.tags)]
    cap = '\n'.join(parts)
    note = ''
    if len(cap) > IG_LIMIT:
        cap, note = cap[:IG_LIMIT - 1] + '…', f'캡션 {len(cap)}자 → 2,200자로 잘림'
    imgs = c.images[:10]
    if len(c.images) > 10:
        note += f' / 캐러셀 10장 제한으로 {len(c.images) - 10}장 생략'
    return Post('instagram', [cap], imgs, note=note.strip(' /'))

def to_naver(c: Content) -> Post:
    md = [f'# {c.hook}', '']
    md += [p + '\n' for p in c.core]
    if c.numbers:
        md += ['| 구분 | 내용 |', '|---|---|'] + [f'| {i+1} | {n} |' for i, n in enumerate(c.numbers)] + ['']
    if c.takeaway:
        md += [f'**{c.takeaway}**', '']
    if c.caveat:
        md += [f'> ⚠️ {c.caveat}', '']
    if c.cta:
        md += [f'{c.cta}: {c.cta_url}', '']
    md += ['---', f'*{c.disclaimer}*']
    return Post('naver', ['\n'.join(md)], c.images, note='API 없음. 복사해서 수동 게시')

ADAPTERS = {'threads': to_threads, 'x': to_x, 'instagram': to_instagram, 'naver': to_naver}

def adapt(c: Content, platforms=None) -> list:
    return [ADAPTERS[p](c) for p in (platforms or ADAPTERS)]
