# -*- coding: utf-8 -*-
"""향후 체크포인트를 일정·컨센서스에서 조립한다 — LLM 0콜.

## 위치

발행 필수 항목(BLOCK) 6개 중 `CHECKPOINTS`가 비면 발행이 막힌다. 실제로 QLYS가
여기서 막혔다 — autogen은 다 돌았는데 분당 한도 재시도 중 이 항목만 빈 채로
넘어갔다. LLM 한 콜에 발행 가능 여부가 걸려 있는 구조였다.

## 무엇을 결정론으로 채울 수 있나

- **다음 실적발표 예정일** — Yahoo `calendarEvents.earnings.earningsDate`
  (추정치면 그렇다고 표시한다. 확정처럼 쓰면 거짓이 된다.)
- **해당 분기 EPS 컨센서스** — 같은 응답의 earningsAverage/Low/High
- **당해·차년 매출·EPS 컨센서스** — `consensus()`의 0y/+1y (애널리스트 수 포함)
- **흑자 전환 전망** — 현재 적자인데 차년 EPS 컨센서스가 흑자면 그 사실
- **배당락일** — 있으면

## 정직하게 — 이건 손으로 쓴 것과 질이 다르다

SATL에 손으로 넣은 체크포인트는 'Merlin 1호기 발사', 'RPO 소진 속도'처럼
**투자 논리의 분기점**이다. 여기서 만드는 건 **달력과 컨센서스**다. 게이트를
통과시키고 "다음에 뭘 확인해야 하는지"를 알려주긴 하지만, 그 종목만의 승부처를
짚지는 못한다. 그건 사람이나 LLM의 몫으로 남는다.

그래서 이 모듈의 목표는 "LLM을 대체한다"가 아니라 **"LLM이 없어도 발행이
막히지 않게 한다"**이다. 쿼터가 있으면 LLM이 더 나은 걸 쓰고, 없으면 이게 받친다.
"""
import datetime


def _fmt_date(ts) -> str:
    """유닉스 초 → '2026년 11월'. 카드의 시점 표기가 월 단위로 통일돼 있다."""
    try:
        d = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
        return f'{d.year}년 {d.month}월'
    except Exception:
        return ''


def _money(v):
    if v is None:
        return None
    a = abs(v)
    if a >= 1e9:
        return f'${v / 1e9:,.1f}B'
    if a >= 1e6:
        return f'${v / 1e6:,.1f}M'
    return f'${v:,.0f}'


def build(ticker: str, cons: dict, ann: dict = None, cal: dict = None) -> list:
    """(시점, 제목, 설명, 중요도) 4-튜플 목록. 근거 없는 항목은 만들지 않는다."""
    ann = ann or {}
    out = []

    # ① 다음 실적발표 — 가장 가까운 확인 지점
    earn = ((cal or {}).get('earnings') or {})
    dates = earn.get('earningsDate') or []
    if dates:
        raw = dates[0].get('raw') if isinstance(dates[0], dict) else dates[0]
        when = _fmt_date(raw)
        if when:
            est = earn.get('isEarningsDateEstimate')
            title = '분기 실적발표' + (' (예정일 추정치)' if est else '')
            avg = (earn.get('earningsAverage') or {}).get('raw')
            lo = (earn.get('earningsLow') or {}).get('raw')
            hi = (earn.get('earningsHigh') or {}).get('raw')
            desc = 'EPS 컨센서스 ' + (f'${avg:,.2f}' if avg is not None else '—')
            if lo is not None and hi is not None:
                desc += f' (범위 ${lo:,.2f}~${hi:,.2f})'
            desc += ' 대비 실제치 확인'
            out.append((when, title, desc, 'high'))

    # ② 당해 회계연도 컨센서스 달성 여부
    p = (cons.get('periods') or {})
    cur = p.get('0y') or {}
    if cur.get('end') and (cur.get('rev') or cur.get('eps') is not None):
        bits = []
        if cur.get('rev'):
            bits.append(f'매출 {_money(cur["rev"])}')
        if cur.get('eps') is not None:
            bits.append(f'EPS ${cur["eps"]:,.2f}')
        n = cur.get('n')
        desc = ' · '.join(bits) + (f' (애널리스트 {n}명)' if n else '')
        out.append((f"FY{cur['end']}", '연간 컨센서스 달성 여부', desc, 'high'))

    # ③ 차년 전망 — 흑자 전환이 걸려 있으면 그게 핵심이다
    nxt = p.get('+1y') or {}
    if nxt.get('end'):
        cur_eps, nxt_eps = cur.get('eps'), nxt.get('eps')
        if cur_eps is not None and nxt_eps is not None and cur_eps < 0 <= nxt_eps:
            out.append((f"FY{nxt['end']}", 'EPS 흑자 전환 전망',
                        f'컨센서스 EPS ${cur_eps:,.2f} → ${nxt_eps:,.2f}. 전환 시점이 실제로 지켜지는지', 'high'))
        else:
            bits = []
            if nxt.get('rev'):
                bits.append(f'매출 {_money(nxt["rev"])}')
                if cur.get('rev'):
                    g = (nxt['rev'] / cur['rev'] - 1) * 100
                    bits[-1] += f'({g:+.0f}%)'
            if nxt_eps is not None:
                bits.append(f'EPS ${nxt_eps:,.2f}')
            if bits:
                out.append((f"FY{nxt['end']}", '차년 성장 전망', ' · '.join(bits), 'mid'))

    # ④ 적자 기업이면 현금 소진이 시한이다 — 산술로 나오는 사실만
    cfo_series = ann.get('cfo') or {}
    cash_series = ann.get('cash') or {}
    yrs = sorted(y for y, v in cfo_series.items() if v is not None)
    if yrs:
        cfo = cfo_series[yrs[-1]]
        cash = cash_series.get(yrs[-1])
        if cfo is not None and cfo < 0 and cash:
            runway = cash / abs(cfo)
            out.append(('매분기', '현금 소진 속도',
                        f'FY{yrs[-1]} 영업현금흐름 {_money(cfo)} · 보유 현금 {_money(cash)} '
                        f'— 같은 속도면 약 {runway:.1f}년치', 'high'))

    # ⑤ 배당락일 — 있는 회사만
    exd = (cal or {}).get('exDividendDate')
    raw = exd.get('raw') if isinstance(exd, dict) else exd
    when = _fmt_date(raw) if raw else ''
    if when:
        out.append((when, '배당락일', '배당 정책 유지 여부', 'mid'))

    return out


if __name__ == '__main__':
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import sources as S
    import ir
    for tk in (sys.argv[1:] or ['QLYS']):
        cik, name = ir.resolve_ticker(tk.upper())
        if not cik:
            print(f'{tk}: SEC에 없음')
            continue
        cal = (S.yf_summary(tk.upper(), 'calendarEvents') or {}).get('calendarEvents') or {}
        rows = build(tk.upper(), S.consensus(tk.upper()), S.annual_series(cik), cal)
        print(f'\n=== {tk} ({name}) — {len(rows)}건')
        for r in rows:
            print(f'  [{r[3]:<4}] {r[0]:<10} {r[1]}')
            print(f'         {r[2]}')


# ── 과거가 '향후 체크포인트'에 섞이는 것 차단 ──────────────────────────
# AGL 실측: 6건 중 4건이 "2026년 Q2 조정 EBITDA 가이던스 상향", "회원 수 감소"처럼
# **이미 일어난 지난 분기 실적 요약**이었다. 제목은 "향후 체크포인트"인데 과거를
# 나열하니 독자가 앞으로 뭘 확인해야 하는지 알 수 없다. LLM이 "앞으로 볼 것"과
# "방금 있었던 일"을 구분 못 하는 자리라, 시점을 파싱해 기계가 거른다.

_Q = {'q1': 3, 'q2': 6, 'q3': 9, 'q4': 12}


def period_end(label: str):
    """'2026년 Q2' · '2026년 11월' · 'FY2026' → 그 구간의 마지막 (연, 월).

    '매분기'·'상시'처럼 반복되는 것은 시점이 없으므로 None을 돌려주고,
    호출부는 그런 항목을 거르지 않는다(계속 유효하니까)."""
    import re as _re
    s = (label or '').strip().lower().replace(' ', '')
    m = _re.search(r'(\d{4})년?q([1-4])', s) or _re.search(r'fy(\d{4}).*?q([1-4])', s)
    if m:
        return int(m.group(1)), _Q[f'q{m.group(2)}']
    m = _re.search(r'(\d{4})년(\d{1,2})월', s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _re.search(r'fy(\d{4})', s) or _re.search(r'^(\d{4})년?$', s)
    if m:
        return int(m.group(1)), 12
    return None


def drop_past(rows, as_of: str = None):
    """지난 시점 항목을 뺀다. as_of는 'YYYY-MM-DD'(없으면 오늘)."""
    import datetime as _dt
    if as_of:
        try:
            base = _dt.date.fromisoformat(as_of[:10])
        except ValueError:
            base = _dt.date.today()
    else:
        base = _dt.date.today()
    out, dropped = [], []
    for r in rows or []:
        pe = period_end(r[0] if r else '')
        if pe is None:                       # 반복·상시 항목은 유지
            out.append(r)
            continue
        y, mo = pe
        if (y, mo) < (base.year, base.month):
            dropped.append(f'{r[0]} {r[1]}'[:40])
        else:
            out.append(r)
    if dropped:
        print(f'   과거 체크포인트 {len(dropped)}건 제거: ' + ' · '.join(dropped[:3]))
    return out
