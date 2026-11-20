# -*- coding: utf-8 -*-
"""정규 거래 첫날 — 상장일을 거래량으로 확정한다. LLM 0콜.

    python listing.py TICKER [TICKER ...]

차트의 **첫 데이터 날짜를 상장일로 쓰면 틀린다.** 그게 지금까지 이 값이
비어 있던 이유다(LITE·SATL·IONQ·SNDK 가 전부 같은 사유로 비어 있었다).

실측 — LITE(JDSU 스핀오프):

    2015-07-23   vol     75,800   close 17.00   ← 차트의 첫 날
    2015-07-24   vol        200   close 17.00      when-issued 구간.
    2015-07-27   vol      2,300   close 20.85      하루 수백 주, 종가가
    ...                                            $21.00 에 붙박여 있다
    2015-08-03   vol    322,800   close 23.45   ← 정규 거래 시작(150배)

스핀오프 완료가 2015-08-01(토)이라 첫 정규장이 8/3(월)이다. 이 7거래일을
안 자르면 **차트 시작점과 상장후 CAGR 이 둘 다 가짜 가격에서 출발한다.**
SPAC 도 모양이 같다 — 합병 전 셸이 같은 티커로 거래된 이력이 붙어 온다.

## 판정 규칙

거래량 **중앙값의 10%를 3거래일 연속** 넘긴 첫날을 정규 거래 시작으로 본다.
하루만 보면 안 된다: LITE 의 첫날은 75,800 주로 혼자 튀어 있고 바로 다음날
200 주로 꺼진다. 3일 연속을 요구해야 그 가짜 봉우리가 걸러진다.

중앙값은 창 **뒷부분**에서 잡는다. 앞부분은 오염 구간일 수 있어서, 거기서
기준을 뽑으면 오염된 값으로 오염을 판정하게 된다.

## 이 방법으로 **못 푸는 것** — 직접 당해보고 적는다

첫 판에서 7종목에 돌려 2건을 틀렸다. 원인이 서로 달랐다.

**SPAC 은 원리적으로 안 된다.** SATL 은 합병 전 셸이 같은 티커로 10개월을
거래했고, 창(200일)이 통째로 셸 구간 안에 들어갔다. 그러면 기준으로 쓰는
중앙값마저 셸 거래량이라 **오염된 값으로 오염을 판정**하게 된다. 셸이 몇 달씩
정상 거래되면 거래량으로는 못 가린다 — 합병완료 8-K 를 봐야 한다. 그래서
SPAC 은 여기서 **판정을 거부한다**.

**차트의 첫 날짜도 못 믿는다.** AAPL 에 `range=max&interval=1mo` 를 주면
1984-12 부터 169개 포인트가 온다. 실제 상장은 1980-12 고, 169개월은 지금까지의
기간과도 안 맞는다 — Yahoo 가 조용히 잘라서 준다. 그래서 오래된 종목은
창 자체가 엉뚱한 곳에 잡힌다.

## 안 하는 것

**자동으로 써넣지 않는다.** 이건 날짜와 **근거(거래량 프로파일)**를 같이
내놓는 도구고, 확정은 사람이 한다. 판정이 애매하면 지어내지 않고 비운다 —
상장일은 차트 시작점과 CAGR 의 기준점이라 틀린 날짜가 빈 값보다 나쁘다.
빈 값은 pagecheck 가 경고로 띄우지만, 틀린 날짜는 통과해서 그대로 발행된다.
"""
import sys
import datetime as dt
import statistics as st

import requests

UA = {'User-Agent': 'Mozilla/5.0'}
CHART = 'https://query1.finance.yahoo.com/v8/finance/chart/{}'

WINDOW_DAYS = 200        # 첫 거래일로부터 볼 구간
SUSTAIN = 3              # 며칠 연속 기준을 넘어야 '정규 거래'로 보는가
FLOOR_RATIO = 0.10       # 중앙값 대비 몇 배 이상이어야 하는가
TAIL = 60                # 중앙값을 뽑을 창의 뒷부분 길이


def _get(ticker, params):
    r = requests.get(CHART.format(ticker), params=params, headers=UA, timeout=25)
    r.raise_for_status()
    res = r.json()['chart']['result'][0]
    q = res['indicators']['quote'][0]
    rows = []
    for t, v, c in zip(res['timestamp'], q.get('volume') or [], q.get('close') or []):
        if v is None or c is None:
            continue
        rows.append((dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), int(v), float(c)))
    return rows


SHELL_FLOOR = 5_000      # 하루 이만큼도 안 되면 정규 거래로 보지 않는다
MIN_JUMP = 20            # 상장 전 구간 대비 거래량이 몇 배는 뛰어야 한다


def resolve(ticker: str, listing_type: str = ''):
    """(date|None, pre_days, note) — pre_days 는 잘라내야 할 상장 전 거래일 수.

    listing_type 에 'SPAC' 이 들어오면 보지 않고 거부한다. 위 독스트링 참조.
    """
    if 'SPAC' in str(listing_type).upper() or '스팩' in str(listing_type):
        return None, 0, 'SPAC — 거래량으로 판정 불가, 합병완료 8-K 필요'
    try:
        # range=max 는 일봉을 안 준다(주봉·월봉으로 자동 축소된다). 그래서
        # 월봉으로 대략의 시작점만 잡고, 그 주변을 일봉으로 다시 받는다.
        coarse = _get(ticker, {'range': 'max', 'interval': '1mo'})
        if not coarse:
            return None, 0, '차트 없음'
        t0 = dt.datetime.combine(coarse[0][0], dt.time(), dt.timezone.utc)
        rows = _get(ticker, {'period1': int(t0.timestamp()) - 86400 * 10,
                             'period2': int(t0.timestamp()) + 86400 * WINDOW_DAYS,
                             'interval': '1d'})
    except Exception as e:
        return None, 0, f'조회 실패: {type(e).__name__}'
    if len(rows) < SUSTAIN + 10:
        return None, 0, f'표본 부족({len(rows)}일)'

    vols = [v for _, v, _ in rows]
    med = st.median(vols[-TAIL:]) if len(vols) > TAIL else st.median(vols)
    if med <= 0:
        return None, 0, '거래량 0'
    # '바닥을 처음 넘는 날'을 찾으면 안 된다. SNDK 의 when-issued 구간은
    # 하루 20만~125만 주로 어지간한 바닥을 다 넘는다 — 그걸로 골라서 2025-02-13
    # 을 집었고, 실제 정규 거래는 거래량이 33,848,500 주로 뛴 2025-02-24 였다.
    # 찾아야 하는 건 바닥이 아니라 **급증 지점**이다.
    best_i, best_ratio = 0, 0.0
    for i in range(1, len(rows) - SUSTAIN + 1):
        pre = st.median(vols[:i])
        # 중앙값이 아니라 최솟값이다. SNDK 는 분할일(02-21, 125만주) 바로 다음
        # 거래일에 3,384만 주가 터지는데, 중앙값으로 보면 그 큰 값이 경계일까지
        # 끌어올려 02-21 을 정규 시작으로 집는다. 구간의 **모든 날**이 커야
        # 거기서부터 정규 거래다.
        post = min(vols[i:i + SUSTAIN])
        if pre <= 0:
            continue
        ratio = post / pre
        if ratio > best_ratio:
            best_i, best_ratio = i, ratio

    if best_ratio < MIN_JUMP:
        return rows[0][0], 0, (f'첫 거래일부터 정규 거래 '
                               f'(최대 급증 {best_ratio:.1f}배 < {MIN_JUMP}배 기준)')
    pre = st.median(vols[:best_i])
    post = min(vols[best_i:best_i + SUSTAIN])
    return rows[best_i][0], best_i, (
        f'앞 {best_i}거래일은 상장 전(when-issued) 거래 — '
        f'{rows[0][0]}~{rows[best_i - 1][0]}, 하루 중앙값 {int(pre):,}주 '
        f'→ {int(post):,}주로 {best_ratio:.0f}배 급증')


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    if len(sys.argv) < 2:
        sys.exit('사용법: python listing.py TICKER [TICKER ...]')
    for tk in sys.argv[1:]:
        d, pre, note = resolve(tk.upper())
        mark = '·' if d and not pre else ('!' if d else 'X')
        print(f'  {mark} {tk.upper():<6} {d or "미확정"}   {note}')
