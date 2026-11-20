# -*- coding: utf-8 -*-
"""윌리엄 오닐 CANSLIM 7항목 원전 판정 + 오닐·리버모어 차트 읽기 — 결정론(LLM 0콜).

왜 따로 두나(2026-10-20 정합화):
  리포트의 기존 'CANSLIM' 페이지는 **체슬리투자자문 방식**이다(canslim.py — 체슬리
  리포트 4건에서 공식을 역산해 일치 확인). 체슬리 방식은 C·A·N 세 글자만 점수로
  합산하고, C·A 를 EPS 가 아니라 **영업이익**으로, N 을 '신제품·신고가'가 아니라
  '글로벌 탑티어·성장 연수·경쟁·지배구조·신시장 CAGR'로 재정의했다. S·L·I·M 은 없다.
  오닐 원전(『How to Make Money in Stocks』)은 점수 합산이 아니라 **7개 관문 체크**다.
  두 방식은 이름만 같고 다른 도구라, 섞지 않고 나란히 보여준다.

오닐 원전 기준(책의 숫자 그대로):
  C  최근 분기 EPS 전년동기 대비 +25% 이상 (매출도 +25% 이상이면 가점)
  A  연간 EPS 3년 연속 +25% 이상 성장, ROE 17% 이상
  N  신제품·신경영·**신고가** — 여기선 가격으로 판정: 52주 고가 대비 -15% 이내
  S  수급 — 상승일 거래량 > 하락일 거래량(50일), 주식수 희석 없음
  L  주도주 — 상대강도(RS) 상위 20%. 전 종목 백분위가 없어 **S&P500 대비 가중수익률로 대리**
  I  기관 매집 — 보유 기관 수 증가(증가 기관 > 감소 기관)
  M  시장 방향 — S&P500 이 200일선 위 + 최근 25거래일 분산일(하락+거래량 증가) 5일 미만
대리 지표를 쓴 항목은 화면에 '대리'라고 밝힌다. 판정 못 하면 None(빈칸이 아니라 '판단 불가').
"""
import datetime as _dt


# ── 공통 ─────────────────────────────────────────────────────────────
def _pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a - b) / abs(b) * 100


def weekly_from_daily(daily: list) -> list:
    """일봉 → 주봉(ISO 주 기준) [{'t','o','h','l','c','v'}]."""
    out, cur, key = [], None, None
    for r in daily or []:
        k = _dt.datetime.utcfromtimestamp(r['t']).isocalendar()[:2]
        if k != key:
            if cur:
                out.append(cur)
            key = k
            cur = {'t': r['t'], 'o': r.get('o') or r['c'], 'h': r.get('h') or r['c'],
                   'l': r.get('l') or r['c'], 'c': r['c'], 'v': r.get('v') or 0}
        else:
            cur['h'] = max(cur['h'], r.get('h') or r['c'])
            cur['l'] = min(cur['l'], r.get('l') or r['c'])
            cur['c'] = r['c']
            cur['v'] += r.get('v') or 0
    if cur:
        out.append(cur)
    return out


def sma(vals, n):
    return [None if i + 1 < n else sum(vals[i + 1 - n:i + 1]) / n for i in range(len(vals))]


def weighted_return(closes_daily: list):
    """오닐 RS 계산식: 최근 3개월 40% + 그 앞 3개월씩 각 20% (약 63거래일 단위)."""
    c = closes_daily
    if len(c) < 253:
        return None
    q = [c[-1 - 63 * i] / c[-1 - 63 * (i + 1)] - 1 for i in range(4)]
    return (0.4 * q[0] + 0.2 * q[1] + 0.2 * q[2] + 0.2 * q[3]) * 100


# ── M: 시장 방향 ──────────────────────────────────────────────────────
def market_direction(spy_daily: list, name: str = 'S&P500') -> dict:
    c = [r['c'] for r in spy_daily or []]
    v = [r.get('v') or 0 for r in spy_daily or []]
    if len(c) < 200:
        return {'state': None, 'note': f'{name} 데이터 부족'}
    ma200 = sum(c[-200:]) / 200
    dd = sum(1 for i in range(len(c) - 25, len(c))
             if c[i] < c[i - 1] * 0.998 and v[i] > v[i - 1])
    above = c[-1] > ma200
    state = ('상승 확인' if above and dd < 5 else '압박받는 상승' if above else '하락 국면')
    return {'state': state, 'above200': above, 'dist_days': dd,
            'vs200': (c[-1] / ma200 - 1) * 100,
            'note': f'{name} 200일선 {"위" if above else "아래"}({(c[-1] / ma200 - 1) * 100:+.1f}%) · 분산일 {dd}일/25일'}


# ── 차트 읽기: 오닐(베이스·피벗·거래량) + 리버모어(최소저항선·피벗포인트) ──
def chart_read(daily: list, spy_daily: list = None, fmt=None, index_name: str = 'S&P500') -> dict:
    fmt = fmt or (lambda v: f'${v:,.2f}')
    w = weekly_from_daily(daily)
    if len(w) < 45:
        return {'ok': False, 'note': '주봉 45주 미만 — 차트 판정 생략'}
    c = [x['c'] for x in w]
    ma10, ma30, ma40 = sma(c, 10), sma(c, 30), sma(c, 40)
    last = w[-1]
    # 오닐 베이스: 최근 52주 고점(피벗 후보) 이후의 조정 깊이와 기간
    look = w[-52:]
    hi_i = max(range(len(look)), key=lambda i: look[i]['h'])
    pivot = look[hi_i]['h']
    after = look[hi_i:]
    low_after = min(x['l'] for x in after)
    depth = (pivot - low_after) / pivot * 100
    weeks = len(look) - 1 - hi_i
    vol50 = sum((r.get('v') or 0) for r in daily[-50:]) / max(1, len(daily[-50:]))
    last_vol_ratio = (daily[-1].get('v') or 0) / vol50 if vol50 else None
    dist_pivot = (last['c'] / pivot - 1) * 100
    if weeks == 0:
        base = '신고가 영역 — 직전 베이스 돌파 후 진행 중'
    elif weeks <= 2:
        base = f'52주 고점 부근({weeks}주 전 고점, -{depth:.0f}%) — 새 베이스 형성 전'
    elif depth <= 33 and weeks >= 7:
        base = f'건전한 베이스 형성 중 ({weeks}주, 조정 -{depth:.0f}%)'
    elif depth > 33:
        base = f'조정이 깊음 (-{depth:.0f}%, {weeks}주) — 오닐 기준 베이스(최대 -33%) 초과'
    else:
        base = f'베이스 기간 짧음 ({weeks}주 < 7주)'
    stage2 = (ma10[-1] and ma30[-1] and ma40[-1] and last['c'] > ma30[-1] > ma40[-1]
              and ma40[-1] > (ma40[-5] or ma40[-1]))
    # 리버모어: 최근 주봉 스윙 고점·저점의 방향(최소저항선)
    sw_hi, sw_lo = [], []
    for i in range(2, len(w) - 2):
        if w[i]['h'] >= max(x['h'] for x in w[i - 2:i + 3]):
            sw_hi.append(w[i]['h'])
        if w[i]['l'] <= min(x['l'] for x in w[i - 2:i + 3]):
            sw_lo.append(w[i]['l'])
    hh = len(sw_hi) >= 2 and sw_hi[-1] > sw_hi[-2]
    hl = len(sw_lo) >= 2 and sw_lo[-1] > sw_lo[-2]
    lh = len(sw_hi) >= 2 and sw_hi[-1] < sw_hi[-2]
    ll = len(sw_lo) >= 2 and sw_lo[-1] < sw_lo[-2]
    # 스윙만 보면 큰 하락 중의 작은 반등도 '상승'으로 읽힌다(SATL 실측: 피벗 대비 -67%인데
    # 최근 두 스윙이 올라 '상승'). 리버모어의 최소저항선은 큰 흐름이다 — 30주선과 같은
    # 방향일 때만 상승·하락으로 확정하고, 엇갈리면 전환 중으로 둔다.
    above30 = bool(ma30[-1]) and last['c'] > ma30[-1]
    falling40 = bool(ma40[-1] and ma40[-5]) and ma40[-1] < ma40[-5]
    rising40 = bool(ma40[-1] and ma40[-5]) and ma40[-1] > ma40[-5]
    if len(sw_hi) < 2 or len(sw_lo) < 2:          # 스윙이 없을 만큼 한 방향이면 이평으로
        line = '상승' if above30 and rising40 else '하락' if not above30 and falling40 else '횡보·전환 중'
    elif hh and hl and above30:
        line = '상승'
    elif (lh and ll) or (not above30 and falling40):
        line = '하락'
    else:
        line = '횡보·전환 중'
    if dist_pivot >= 0 and last_vol_ratio and last_vol_ratio >= 1.4:
        pstate = '피벗 돌파 (거래량 동반)'
    elif dist_pivot >= 0:
        pstate = '피벗 위 — 거래량 확인 필요'
    elif dist_pivot >= -5:
        pstate = f'피벗 아래 {dist_pivot:.1f}% — 돌파 대기'
    else:
        pstate = f'피벗까지 {-dist_pivot:.0f}% — 베이스 진행 중'
    rs = None
    if spy_daily:
        r1 = weighted_return([r['c'] for r in daily])
        r2 = weighted_return([r['c'] for r in spy_daily])
        rs = None if r1 is None or r2 is None else r1 - r2
    oneil = [base,
             f'추세: {"2단계 상승(종가>30주선>40주선, 40주선 상승)" if stage2 else "2단계 상승 아님"}',
             f'피벗 {fmt(pivot)} · {pstate}',
             f'손절선(피벗 매수 가정, -8%): {fmt(pivot * 0.92)}']
    livermore = [f'최소저항선: {line}' + (' (고점·저점 모두 높아지는 중)' if line == '상승' else
                                       ' (고점·저점 모두 낮아지는 중)' if line == '하락' else ''),
                 f'피벗 포인트: 52주 고점 {fmt(pivot)} 돌파 시 추세 확인, '
                 f'최근 저점 {fmt(low_after)} 이탈 시 추세 실패',
                 '원칙: 시장이 방향을 확인해 줄 때까지 기다린다 — '
                 + ('지금은 확인된 상태' if line == '상승' and dist_pivot >= 0 else '지금은 확인 전')]
    return {'ok': True, 'weekly': w, 'ma10': ma10, 'ma30': ma30, 'ma40': ma40,
            'pivot': pivot, 'pivot_i': len(w) - 52 + hi_i, 'low_after': low_after,
            'depth': depth, 'base_weeks': weeks, 'dist_pivot': dist_pivot, 'stage2': bool(stage2),
            'vol_ratio': last_vol_ratio, 'line': line, 'rs_vs_spy': rs,
            'oneil': oneil, 'livermore': livermore}


# ── CANSLIM 원전 7항목 ────────────────────────────────────────────────
def _q_sorted(d: dict):
    return sorted(((k, v) for k, v in (d or {}).items() if v is not None), key=lambda x: x[0])


def _yoy_q(series: dict):
    """최근 분기 vs 전년 같은 분기(종료일 ±20일). (cur, prior, end) 또는 None."""
    pts = _q_sorted(series)
    if not pts:
        return None
    end, cur = pts[-1]
    e = _dt.date.fromisoformat(end[:10])
    for k, v in pts:
        d = _dt.date.fromisoformat(k[:10])
        if abs((e - d).days - 365) <= 20:
            return cur, v, end
    return None


def canslim_oneil(L: dict) -> list:
    """[(글자, 이름, 판정 True/False/None, 값 문장, 기준 문장)]."""
    rows = []
    qe = (L.get('q_eps') or {})
    eps = qe.get('eps') or {}
    rev = (L.get('quarterly') or {}).get('revenue') or {}
    # C
    y = _yoy_q(eps)
    yr = _yoy_q(rev)
    if y:
        cur, prior, end = y
        g = _pct(cur, prior)
        ok = (cur > 0 and prior > 0 and g is not None and g >= 25)
        val = f'EPS {prior:+.2f} → {cur:+.2f} ({end[:7]})' + (f' · {g:+.0f}%' if g is not None and prior > 0 else ' · 적자 포함')
        if yr:
            rg = _pct(yr[0], yr[1])
            val += f' · 매출 {rg:+.0f}%' if rg is not None else ''
        rows.append(('C', '분기 EPS 성장', ok, val, '전년 동기 대비 +25% 이상'))
    else:
        rows.append(('C', '분기 EPS 성장', None, 'EPS 분기 데이터 없음', '전년 동기 대비 +25% 이상'))
    # A — 연간 EPS 대신 순이익(주식수 변화가 크면 왜곡) — 대리 표기
    ni = sorted(((y, v) for y, v in ((L.get('annual') or {}).get('netinc') or {}).items() if v is not None))
    eq = (L.get('annual') or {}).get('equity') or {}
    if len(ni) >= 4:
        last4 = ni[-4:]
        gs = [_pct(b[1], a[1]) if a[1] > 0 else None for a, b in zip(last4, last4[1:])]
        ok = all(g is not None and g >= 25 for g in gs)
        roe = (ni[-1][1] / eq.get(ni[-1][0]) * 100) if eq.get(ni[-1][0]) and eq.get(ni[-1][0]) > 0 else None
        ok = ok and roe is not None and roe >= 17
        val = '순이익 성장 ' + ' · '.join('—' if g is None else f'{g:+.0f}%' for g in gs) + \
              (f' · ROE {roe:.0f}%' if roe is not None else ' · ROE 계산 불가')
        rows.append(('A', '연간 이익 성장(대리: 순이익)', ok, val, '3년 연속 +25% · ROE 17% 이상'))
    else:
        rows.append(('A', '연간 이익 성장(대리: 순이익)', False if ni and ni[-1][1] <= 0 else None,
                     '흑자 연간 이익 이력 부족' if ni else '연간 이익 데이터 없음', '3년 연속 +25% · ROE 17% 이상'))
    # N
    tech = L.get('technical') or {}
    fh = tech.get('from_high_pct')
    rows.append(('N', '신고가 근접', None if fh is None else fh >= -15,
                 '데이터 없음' if fh is None else f'52주 고가 대비 {fh:+.0f}%', '52주 고가 -15% 이내(신제품·신경영은 본문 참고)'))
    # S
    daily = L.get('daily') or []
    ud = None
    if len(daily) >= 51:
        up = sum(daily[i].get('v') or 0 for i in range(len(daily) - 50, len(daily)) if daily[i]['c'] > daily[i - 1]['c'])
        dn = sum(daily[i].get('v') or 0 for i in range(len(daily) - 50, len(daily)) if daily[i]['c'] < daily[i - 1]['c'])
        ud = up / dn if dn else (99.0 if up else None)   # 50일 내내 오르기만 했으면 사실상 무한대
    # 주식수는 분기 5개 이상 있을 때만 1년 변화로 본다. 2개뿐이면 표지 기준일·클래스가 섞여
    # 엉뚱한 값이 나온다(SATL 실측: 2점으로 +416%).
    sh = _q_sorted(qe.get('shares') or {})
    dil = _pct(sh[-1][1], sh[-5][1]) if len(sh) >= 5 else None
    s_ok = None if ud is None else (ud >= 1.0 and (dil is None or dil < 5))
    rows.append(('S', '수급(거래량·주식수)', s_ok,
                 (f'상승/하락 거래량 {ud:.2f}' if ud else '거래량 데이터 없음') +
                 (f' · 주식수 1년 {dil:+.0f}%' if dil is not None else ''),
                 '상승일 거래량 우위(≥1.0) · 희석 5% 미만'))
    # L
    cr = L.get('_chart') or {}
    rs = cr.get('rs_vs_spy')
    ix = L.get('_index_name') or 'S&P500'
    rows.append(('L', f'주도주(대리: {ix} 대비 RS)', None if rs is None else rs >= 10,
                 '데이터 없음' if rs is None else f'가중 수익률이 {ix} 보다 {rs:+.0f}%p',
                 f'RS 상위 20% (대리: {ix} 대비 +10%p 이상)'))
    # I
    ia = L.get('inst_activity') or {}
    own = L.get('ownership') or {}
    fl = own.get('flow') or {}
    if fl.get('days'):
        # 한국(2026-11-04): 13F 가 없다 → 같은 질문('큰손이 사 모으나')을 외국인+기관 순매수로 잰다.
        #   오닐 원뜻(보유 기관 수 증가)과 다른 대리 지표라 기준 문구에 그렇게 적는다.
        net = (fl.get('foreign') or 0) + (fl.get('inst') or 0)
        rows.append(('I', '기관 매집(대리: 외국인+기관 수급)', net > 0,
                     f"{fl['days']}거래일 외국인 {fl.get('foreign', 0):+,.0f}주 · 기관 {fl.get('inst', 0):+,.0f}주",
                     f"{fl['days']}거래일 외국인+기관 순매수 > 0"))
    else:
        if ia.get('increased') is not None and ia.get('decreased') is not None:
            ok = ia['increased'] > ia['decreased']
            val = f'증가 {ia["increased"]:.0f}곳 · 감소 {ia["decreased"]:.0f}곳' + \
                  (f' · 신규 {ia["new"]:.0f}·전량매도 {ia["soldout"]:.0f}' if ia.get('new') is not None and ia.get('soldout') is not None else '')
        else:
            ok = None
            val = (f'기관 {own.get("inst_count"):.0f}곳 보유 · {own["institutions_pct"] * 100:.0f}% (증감 데이터 없음)'
                   if own.get('inst_count') and own.get('institutions_pct') is not None else '데이터 없음')
        rows.append(('I', '기관 매집', ok, val, '보유 기관 수 증가(증가 > 감소)'))
    # M
    m = L.get('_market') or {}
    rows.append(('M', '시장 방향', None if m.get('state') is None else m['state'] == '상승 확인',
                 m.get('note', '데이터 없음'), f'{ix} 200일선 위 · 분산일 5일 미만'))
    return rows
