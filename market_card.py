"""장 마감 시황 포토카드 v2 (2026-11-06 차니 '넘 못생겼음' → impeccable 기준 재설계).

v1 진단
  · 휴대폰에서 1080px 이미지는 약 0.35배로 보인다 → 본문 24px 가 9px 수준. 읽히지 않았다.
  · 주인공이 없었다 — 지수 타일 3개·막대 목록 4개가 같은 무게로 1,650px.
  · 주황 소제목이 6번, 막대(최솟값 점 포함)가 40개 — 장식이 숫자를 가렸다.
  · 원/달러 +1.2% 를 초록(좋음)으로 칠했다 — 원화 약세는 좋은 일이 아니다.
  · '(LS ELECT…' 처럼 대장주 이름이 잘렸다.

v2 원칙
  · 그날의 대표 지수 등락 하나를 크게. 나머지는 표처럼 줄 맞춘 목록.
  · 본문 32px 이상(휴대폰 약 11pt). 장식 막대 없음, 색은 등락 숫자에만.
  · '오르면 나쁜' 지표(원/달러·VIX·금리)는 색 없이(뜻이 뒤집히지 않게).
  · 숫자는 market.render 와 같은 facts 에서만(계산은 대시보드 한 곳).
글꼴: Pretendard(OFL, fonts/) — 없으면 card.py 의 나눔고딕.
"""
import os

from PIL import Image, ImageDraw, ImageFont

import card
from market import clean_name, gate_line, flow_line, sector_groups

W = 1080
PAD = 64
CW = W - 2 * PAD
BG = (0xff, 0xff, 0xff)
INK = card.FG
DIM = (0x5b, 0x61, 0x6b)
FAINT = (0x8a, 0x90, 0x99)
LINE = (0xe6, 0xe7, 0xea)
TRACK = (0xf1, 0xf2, 0xf4)
UP, DN, FLAT = card.DIR_COLOR['up'], card.DIR_COLOR['dn'], card.DIR_COLOR['flat']
WD = '월화수목금토일'
TITLE = {'kr': '한국 장 마감', 'daily': '미국 장 마감', 'weekly': '주간 시황'}
HERO = {'kr': '^KS11', 'daily': '^GSPC', 'weekly': '^KS11'}
INVERSE = {'KRW=X', '^VIX', '^TNX', 'DX-Y.NYB'}   # 오르면 좋다고 말할 수 없는 쪽 — 색을 입히지 않는다
MINUS = '−'

_HERE = os.path.dirname(os.path.abspath(__file__))
_PRET = (os.path.join(_HERE, 'fonts', 'Pretendard-Regular.otf'), os.path.join(_HERE, 'fonts', 'Pretendard-Bold.otf'))
_cache = {}


def F(bold: bool, size: int):
    k = (bold, size)
    if k not in _cache:
        p = _PRET[1 if bold else 0]
        _cache[k] = ImageFont.truetype(p, size) if os.path.exists(p) else card._font(bold, size)
    return _cache[k]


def _c(v, sym=None):
    if sym in INVERSE or v is None or abs(v) < 0.05:
        return FLAT if sym not in INVERSE else INK
    return UP if v > 0 else DN


def _p(v, digits=1):
    if v is None:
        return '-'
    if abs(v) < 0.05:
        return f'{0:.{digits}f}%'
    s = f'{v:+.{digits}f}%'
    return s.replace('-', MINUS)


def _num(v):
    return f'{v:,.2f}' if v < 100 else f'{v:,.1f}' if v < 10000 else f'{v:,.0f}'


def _day(d):
    try:
        from datetime import date
        x = date.fromisoformat(d)
        return f'{x.year}.{x.month:02d}.{x.day:02d} ({WD[x.weekday()]})'
    except Exception:
        return d or ''


def _fit(dr, text, font, width):
    t = str(text)
    if dr.textlength(t, font=font) <= width:
        return t
    while t and dr.textlength(t + '…', font=font) > width:
        t = t[:-1]
    return t + '…'


def _wrap(dr, text, font, width, max_lines=3):
    words, lines, cur = str(text).split(' '), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if dr.textlength(t, font=font) <= width:
            cur = t
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and ' '.join(lines) != ' '.join(words):
        lines[-1] = _fit(dr, lines[-1] + ' ' + ' '.join(words), font, width)
    return lines


def _val(x):
    if x.get('sym') == '^TNX':
        return f"{x['close']:.2f}%"
    return _num(x['close'])


def _chg_txt(x, k):
    if x.get('sym') == '^TNX':                 # 금리는 %가 아니라 bp
        r = (x.get(k) or 0) / 100
        bp = round(x['close'] * r / (1 + r) * 100)
        return f'{bp:+d}bp'.replace('-', MINUS)
    return _p(x.get(k))


def _nm(r):
    """티커가 곧 이름인 미국 종목은 그대로(clean_name 이 'CBRS' → 'Cbrs' 로 바꿨다)."""
    return r['name'] if r.get('sym') and r['name'] == r['sym'] else clean_name(r['name'])


def _header(dr, y, title):
    y += 28
    dr.line([PAD, y, W - PAD, y], fill=LINE, width=2)
    y += 30
    dr.text((PAD, y), title, font=F(True, 34), fill=INK)
    return y + 62


def _hero(dr, y, x, k, lb):
    """대표 지수 — 이름 · 큰 등락 · 종가 · 5일."""
    dr.text((PAD, y), x['name'], font=F(False, 36), fill=DIM)
    y += 50
    big = _chg_txt(x, k)
    f = F(True, 148)
    dr.text((PAD - 6, y - 18), big, font=f, fill=_c(x.get(k), x.get('sym')))
    bw = dr.textlength(big, font=f)
    rx = PAD + bw + 40
    dr.text((rx, y + 24), _val(x), font=F(True, 46), fill=INK)
    sub = x.get('d5' if k == 'd1' else 'm1')
    dr.text((rx, y + 84), f'{lb} {_p(sub)}', font=F(False, 32), fill=DIM)
    return y + 168


def _rows(dr, y, rows, k):
    """보조 지수 — 이름 | 종가 | 등락 한 줄씩, 얇은 선으로 구분."""
    for i, x in enumerate(rows):
        if i:
            dr.line([PAD, y - 12, W - PAD, y - 12], fill=LINE, width=1)
        dr.text((PAD, y), _fit(dr, x['name'], F(False, 34), 420), font=F(False, 34), fill=INK)
        dr.text((PAD + 640, y), _val(x), font=F(False, 34), fill=DIM, anchor='ra')
        dr.text((W - PAD, y), _chg_txt(x, k), font=F(True, 34), fill=_c(x.get(k), x.get('sym')), anchor='ra')
        y += 66
    return y


def _breadth(dr, y, b, t):
    tot = max(1, b['up'] + b['down'] + b['flat'])
    h = 22
    wu, wf = int(CW * b['up'] / tot), int(CW * b['flat'] / tot)
    dr.rounded_rectangle([PAD, y, W - PAD, y + h], radius=11, fill=DN)
    if wu > 0:
        dr.rounded_rectangle([PAD, y, PAD + max(wu, h), y + h], radius=11, fill=UP)
        dr.rectangle([PAD + h // 2, y, PAD + wu, y + h], fill=UP)
    dr.rectangle([PAD + wu, y, PAD + wu + wf, y + h], fill=FLAT)
    y += h + 22
    dr.text((PAD, y), f"상승 {b['up']:,}", font=F(True, 34), fill=UP)
    dr.text((W // 2, y), f"보합 {b['flat']:,}", font=F(False, 30), fill=FAINT, anchor='ma')
    dr.text((W - PAD, y), f"하락 {b['down']:,}", font=F(True, 34), fill=DN, anchor='ra')
    y += 58
    sub = f"상승 비율 {round(b['up'] / tot * 100)}%"
    if b.get('limit_up') is not None:
        sub += f" · 상한가 {b['limit_up']} · 하한가 {b.get('limit_down', '-')}"
    dr.text((PAD, y), sub, font=F(False, 30), fill=DIM)
    y += 46
    if isinstance(t, str) and t:
        dr.text((PAD, y), _fit(dr, t, F(False, 30), CW), font=F(False, 30), fill=DIM)
        y += 46
    elif t:
        dr.text((PAD, y), '거래대금 ' + ' · '.join(f'{k} {v:,.1f}조' for k, v in t.items()), font=F(False, 30), fill=DIM)
        y += 46
    return y


def _list2(dr, y, left, right, key, sub=None, heads=None, n=5):
    """두 칸 목록 — 이름(왼쪽) · 등락(오른쪽). sub(r) 가 있으면 이름 아래 작은 글씨로(잘림 방지)."""
    gap = 56
    colw = (CW - gap) // 2
    rh = 82 if sub else 58
    if heads:
        for i, hd in enumerate(heads):
            dr.text((PAD + i * (colw + gap), y), hd, font=F(False, 28), fill=FAINT)
        y += 46
    for col, items in enumerate((left, right)):
        cx = PAD + col * (colw + gap)
        for i, r in enumerate(items[:n]):
            cy = y + i * rh
            v = r.get(key)
            pt = _p(v)
            sym = r.get('sym')
            pw = dr.textlength(pt, font=F(True, 32))
            dr.text((cx, cy), _fit(dr, _nm(r), F(False, 32), colw - pw - 20), font=F(False, 32), fill=INK)
            dr.text((cx + colw, cy), pt, font=F(True, 32), fill=_c(v, sym), anchor='ra')
            if sub and sub(r):
                dr.text((cx, cy + 40), _fit(dr, sub(r), F(False, 24), colw - 20), font=F(False, 24), fill=FAINT)
    return y + max(len(left[:n]), len(right[:n])) * rh


def _gate(dr, y, f):
    """실전 신호등 띠 — 남의 시황에 없는 것: '그래서 오늘 규칙상 사도 되나'. 봇 v1.9 지수 게이트와 같은 계산(2026-11-11)."""
    t = gate_line(f)
    if not t:
        return y
    head, _, rest = t.partition(' — ')
    col = UP if head == '신규 매수 가능' else DN if head == '신규 매수 중지' else (0xb4, 0x8a, 0x1c)
    main_, _, live = rest.partition(' (이번 주 지금까지 ')
    lines = [main_] + ([f"이번 주 지금까지 {live.rstrip(')')} · 금요일 종가에 확정"] if live else [])
    y += 22
    h = 70 + 40 * len(lines)
    dr.rounded_rectangle([PAD, y, W - PAD, y + h], radius=18, fill=(0xf4, 0xf5, 0xf7))
    dr.rounded_rectangle([PAD, y, PAD + 10, y + h], radius=5, fill=col)
    dr.text((PAD + 32, y + 16), '이번 주 시장 신호', font=F(False, 26), fill=FAINT)
    dr.text((PAD + 32 + dr.textlength('이번 주 시장 신호  ', font=F(False, 26)), y + 10), head, font=F(True, 34), fill=col)
    for i, ln in enumerate(lines):
        dr.text((PAD + 32, y + 62 + 40 * i), _fit(dr, ln.replace('-', MINUS), F(False, 26), CW - 60), font=F(False, 26), fill=DIM)
    return y + h + 4


def _movers(dr, y, kr):
    """강세 테마·52주 신고가·특징주 (2026-11-11). 숫자는 대시보드 facts 그대로.
    거래대금 상위는 시총 상위·특징주(거래대금 순위 표기)와 겹쳐 카드에서 뺐다(텍스트판엔 남음)."""
    th = kr.get('themes_top') or []
    if th:
        y = _header(dr, y, '강세 테마')
        dr.text((W - PAD, y - 58), '네이버 테마 · 구성 종목 평균', font=F(False, 26), fill=FAINT, anchor='ra')
        for t in th[:3]:
            pt = _p(t['ret'])
            dr.text((PAD, y), _fit(dr, t['name'], F(True, 32), CW - 360), font=F(True, 32), fill=INK)
            dr.text((W - PAD - 190, y + 4), f"{t['up']}/{t['n']}종 상승", font=F(False, 26), fill=FAINT, anchor='ra')
            dr.text((W - PAD, y), pt, font=F(True, 32), fill=_c(t['ret']), anchor='ra')
            lead = ' · '.join(f"{clean_name(x['name'])} {_p(x['ret'])}" for x in t['lead'][:3])
            dr.text((PAD, y + 42), _fit(dr, lead.replace('-', MINUS), F(False, 26), CW), font=F(False, 26), fill=DIM)
            y += 92
        tb = kr.get('themes_bottom') or []
        if tb:
            dr.text((PAD, y), _fit(dr, '약세  ' + ' · '.join(f"{t['name']} {_p(t['ret'])}" for t in tb[:3]), F(False, 28), CW),
                    font=F(False, 28), fill=DN)
            y += 46
    nh = kr.get('new_high_52w') or {}
    if nh:
        y = _header(dr, y, f"52주 신고가 {nh['n']}종")
        dr.text((W - PAD, y - 58), f"시총 1천억+ {nh['universe']:,}종 · 장중 고가", font=F(False, 26), fill=FAINT, anchor='ra')
        top = nh.get('top') or []
        if top:
            y = _list2(dr, y, top[0:6:2], top[1:6:2], 'ret', n=3)
    feat = kr.get('featured') or []
    if feat:
        lu = kr.get('limit_up') or []
        y = _header(dr, y, '특징주')
        dr.text((W - PAD, y - 58), f'상한가 {len(lu)}종 포함 · 거래대금 순' if lu else '거래대금 순',
                font=F(False, 26), fill=FAINT, anchor='ra')
        y = _list2(dr, y, feat[0:6:2], feat[1:6:2], 'ret', sub=lambda r: r.get('tag'), n=3)
    return y

def render(rec: dict, out_path: str, one_liner: str = '', tips=(), part: int = 0) -> str:
    """part 0 = 한 장 전부 · 1 = 시장 판단(신호등·지수·시장 폭·수급·업종·시총 상위) · 2 = 종목(테마·신고가·특징주·급등락).
    2026-11-11 차니 '한 장이 너무 길면 두 장도 OK' → 한국 장은 카테고리로 2장(코스피/코스닥으로 나누면 테마·신고가가 양쪽에 겹친다)."""
    f = rec.get('facts') or {}
    kind = rec.get('kind') or f.get('kind') or 'daily'
    p1, p2 = part in (0, 1), part in (0, 2)
    k, lb = ('d5', '1개월') if kind == 'weekly' else ('d1', '5일')
    im = Image.new('RGB', (W, 4000), BG)
    dr = ImageDraw.Draw(im)
    y = PAD
    title = TITLE.get(kind, '시황') if part != 2 else ('오늘의 종목' if kind == 'kr' else '오늘의 종목 · 미국')
    dr.text((PAD, y), title, font=F(True, 40), fill=INK)
    dr.text((W - PAD, y + 6), _day(rec.get('date', '')) + (f'  ·  {part}/2' if part else ''), font=F(False, 32), fill=DIM, anchor='ra')
    y += 92

    idx = [x for x in f.get('indices', []) if x.get('close') is not None
           and not (kind == 'daily' and x.get('sym') in ('^KS11', '^KQ11'))]
    hero = next((x for x in idx if x.get('sym') == HERO.get(kind)), idx[0] if idx else None)
    if not p1:
        idx, hero, one_liner, tips = [], None, '', ()
        y -= 30
    if hero:
        y = _hero(dr, y, hero, k, lb)
    if one_liner:
        y += 8
        for ln in _wrap(dr, one_liner, F(False, 32), CW, max_lines=3):
            dr.text((PAD, y), ln, font=F(False, 32), fill=INK)
            y += 48
    for tp in list(tips)[:2]:
        y += 6
        dr.ellipse([PAD + 2, y + 15, PAD + 12, y + 25], fill=FAINT)
        for ln in _wrap(dr, tp, F(False, 28), CW - 28, max_lines=2):
            dr.text((PAD + 28, y), ln, font=F(False, 28), fill=DIM)
            y += 40
    if kind == 'kr' and p1:
        y = _gate(dr, y, f)
    rest = [x for x in idx if x is not hero]
    if rest:
        y = _header(dr, y, '지수 · 환율' if kind == 'kr' else '지수 · 금리 · 환율')
        y = _rows(dr, y, rest, k)

    st = {m: v for m, v in (f.get('stocks') or {}).items() if isinstance(v, dict)}
    kr = st.get('KR') or {}
    us = f.get('us') or {}

    # ── 2026-11-14 대시보드 🏠 종합 '오늘의 시장'과 같은 이름·순서·정의(계산은 대시보드 한 곳) ──
    #   1장 시장 판단: 신호 → 지수 → 시장 폭(·수급) → 강한·약한 업종
    #   2장 오늘의 종목: (한국) 강세 테마 · 52주 신고가 · 특징주 / (미국) 돈이 몰린 종목 · 급등주 · 52주 신고가 → 대형주 상승·하락 → 시총 상위 10
    usi = ((f.get('internals') or {}).get('US')) or {}
    two = lambda r: (' · '.join(_nm(x) for x in (r.get('members') or [])[:2]) or r.get('lead') or '')
    if kind == 'kr' and p1 and kr.get('breadth_all'):
        y = _header(dr, y, '시장 폭')
        dr.text((W - PAD, y - 58), '코스피+코스닥 전 종목', font=F(False, 26), fill=FAINT, anchor='ra')
        y = _breadth(dr, y, kr['breadth_all'], kr.get('turnover_tn') or {})
        fl = flow_line(kr)
        if fl:
            dr.text((PAD, y), _fit(dr, fl.replace('-', MINUS), F(False, 30), CW), font=F(False, 30), fill=DIM)
            y += 46
    if kind == 'daily' and p1 and us.get('assets'):
        y = _header(dr, y, '자산')
        a = us['assets']
        h = (len(a) + 1) // 2
        y = _list2(dr, y, a[:h], a[h:], 'd1', n=4)
    if kind == 'daily' and p1 and usi.get('breadth_all'):
        tot = sum(usi['breadth_all'].get(k) or 0 for k in ('up', 'down', 'flat'))
        y = _header(dr, y, '시장 폭')
        dr.text((W - PAD, y - 58), f'미국 시총 $3억+ {tot:,}종', font=F(False, 26), fill=FAINT, anchor='ra')
        t = ' · '.join(x for x in (usi.get('turnover_txt') and f"거래대금 {usi['turnover_txt']}",
                                    usi.get('big_n') and f"대형주 {usi['big_n']}종 중 상승 {usi.get('breadth_up')}%") if x)
        y = _breadth(dr, y, usi['breadth_all'], t)

    sc = (kr.get('sectors') if kind == 'kr' else usi.get('sectors') if kind == 'daily' else None) or []
    sc = sorted([r for r in sc if r.get('ret') is not None], key=lambda r: -r['ret'])
    if sc and p1:
        y = _header(dr, y, '업종')
        dr.text((W - PAD, y - 58), '시총가중', font=F(False, 26), fill=FAINT, anchor='ra')
        y = _list2(dr, y, sc[:3], list(reversed(sc[-3:])), 'ret', sub=two, heads=('강한 업종', '약한 업종'), n=3)
    elif kind == 'daily' and p1 and us.get('sectors'):          # 옛 자료(시장 내부 없음) — S&P500 업종 ETF
        y = _header(dr, y, 'S&P500 업종')
        y = _list2(dr, y, us['sectors'][:3], list(reversed(us['sectors'][-3:])), 'd1', heads=('강한 업종', '약한 업종'), n=3)

    if kind == 'kr' and p2:
        y = _movers(dr, y, kr)
    if kind == 'daily' and p2 and usi:
        tv = usi.get('turnover_top') or []
        if tv:
            y = _header(dr, y, '돈이 몰린 종목')
            dr.text((W - PAD, y - 58), '거래대금 상위', font=F(False, 26), fill=FAINT, anchor='ra')
            y = _list2(dr, y, tv[0:6:2], tv[1:6:2], 'ret', sub=lambda r: r.get('tag'), n=3)
        ft = usi.get('featured') or []
        if ft:
            y = _header(dr, y, '급등주')
            dr.text((W - PAD, y - 58), '+7% 이상 · 돈이 몰린 순', font=F(False, 26), fill=FAINT, anchor='ra')
            y = _list2(dr, y, ft[0:6:2], ft[1:6:2], 'ret', sub=lambda r: r.get('tag'), n=3)
        nh = usi.get('new_high_52w') or {}
        if nh.get('top'):
            y = _header(dr, y, f"52주 신고가 {nh['n']}종")
            dr.text((W - PAD, y - 58), f"{nh.get('universe', 0):,}종 중 · 거래대금 순", font=F(False, 26), fill=FAINT, anchor='ra')
            y = _list2(dr, y, nh['top'][0:6:2], nh['top'][1:6:2], 'ret', n=3)

    # 대형주 상승·하락 상위 — 미국은 시장 내부(시총 상위 500 · 1일), 없으면 옛 perf(1주)
    mv = {'kr': ['KR'], 'daily': ['US'], 'weekly': ['KR', 'US']}.get(kind, [])
    for m in [m for m in mv if p2 or kind == 'weekly']:
        s = st.get(m) or {}
        top, bot, basis = s.get('top'), s.get('bottom'), {'d1': '오늘', 'ret_1w': '1주', 'ret_4w': '4주'}.get(s.get('basis'), '')
        if kind == 'daily' and usi.get('top'):
            top, bot, basis = usi['top'], usi.get('bottom') or [], '오늘'
        if not top:
            continue
        pre = ('한국 ' if m == 'KR' else '미국 ') if len(mv) > 1 else ''
        y = _header(dr, y, f'{pre}대형주 상승 · 하락 상위')
        dr.text((W - PAD, y - 58), basis, font=F(False, 26), fill=FAINT, anchor='ra')
        y = _list2(dr, y, top, bot or [], 'ret', heads=('상승', '하락'), n=3 if kind == 'kr' else 5)

    mg = kr.get('megacaps') if kind == 'kr' else (usi.get('megacaps') if kind == 'daily' else None)
    if mg and p2:
        y = _header(dr, y, '시총 상위 10')
        dr.text((W - PAD, y - 58), '지수를 움직이는 종목', font=F(False, 26), fill=FAINT, anchor='ra')
        y = _list2(dr, y, mg[:5], mg[5:10], 'ret')
    elif kind == 'daily' and p2 and us.get('megacaps'):
        y = _header(dr, y, '대형 기술주')
        y = _list2(dr, y, us['megacaps'][:5], us['megacaps'][5:10], 'd1')

    sg = f.get('signals') or {}
    md_ = {kk: v for kk, v in (sg.get('market_direction') or {}).items()
           if v and (kind == 'weekly' or kk == {'kr': 'KR', 'daily': 'US'}.get(kind))}
    y += 36
    dr.line([PAD, y, W - PAD, y], fill=LINE, width=2)
    y += 30
    want = {'kr': ('^KS11', '^KQ11'), 'daily': ('^GSPC', '^IXIC')}.get(kind, ('^KS11', '^GSPC'))
    pz = [(x['name'], (x.get('pulse') or {}).get('state')) for x in f.get('indices', []) if x.get('sym') in want]
    pz = [(n, v) for n, v in pz if v]
    if pz and p1:
        txt = '시장 추세(오닐 방식)  ' + '  ·  '.join(f'{n} {v}' for n, v in pz)
        dr.text((PAD, y), _fit(dr, txt, F(False, 28), CW), font=F(False, 28), fill=DIM)
        y += 48
    elif md_ and p1:
        txt = '시장 방향  ' + '  ·  '.join(f'{kk} {v}' for kk, v in md_.items())
        dr.text((PAD, y), _fit(dr, txt.replace('⚠️', '').replace('✅', '').replace('-', MINUS), F(False, 28), CW), font=F(False, 28), fill=DIM)
        y += 48
    dr.text((PAD, y), '부자알람 · 숫자 자동 집계 · 문장 AI · 투자 권유 아님', font=F(False, 24), fill=FAINT)
    y += 34 + PAD - 10
    im.crop((0, 0, W, y)).save(out_path, optimize=True)
    return out_path


def render_kr2(rec: dict, out_dir: str, one_liner: str = '', tips=()) -> list:
    """2장(시장 판단 / 오늘의 종목) — 한국 장, 그리고 시장 내부 자료가 있는 미국 장(2026-11-14). 둘째 장에 쓸 게 없으면 1장만."""
    f = rec.get('facts') or {}
    kind = rec.get('kind') or f.get('kind') or 'daily'
    kr = ((f.get('stocks') or {}).get('KR')) or {}
    usi = ((f.get('internals') or {}).get('US')) or {}
    has2 = (any(kr.get(k) for k in ('themes_top', 'new_high_52w', 'featured', 'top')) if kind == 'kr'
            else bool(usi.get('megacaps')) if kind == 'daily' else False)
    if not has2:
        return [render(rec, os.path.join(out_dir, f'{kind}1.png'), one_liner, tips, part=0)]
    return [render(rec, os.path.join(out_dir, f'{kind}1.png'), one_liner, tips, part=1),
            render(rec, os.path.join(out_dir, f'{kind}2.png'), part=2)]
