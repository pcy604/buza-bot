"""상장일(정규 거래 시작) 판정 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_listing.py

2026-10-10 에 실제로 틀렸던 사례만 넣는다. 지어낸 사례로 테스트하면
실제로 나가는 오류는 계속 통과한다.

고정된 거래량 프로파일을 넣어 판정 규칙만 시험한다. Yahoo 를 때리지
않으므로 네트워크가 죽어도, 과거 데이터가 수정돼도 이 테스트는 돈다.
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'decks'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import listing as L

D = dt.date


def _rows(start, vols):
    """(date, volume, close) 목록 — 날짜는 영업일 비슷하게만 띄운다."""
    out, d = [], start
    for v in vols:
        out.append((d, v, 10.0))
        d += dt.timedelta(days=1 if d.weekday() < 4 else 3)
    return out


def _patch(rows):
    L._get = lambda ticker, params: (
        rows if params.get('interval') == '1d' else rows[:1])


# ── 실측 프로파일 ────────────────────────────────────────────────────
# LITE — JDSU 스핀오프. 앞 7거래일이 when-issued(하루 수백~수천 주).
LITE = _rows(D(2015, 7, 23),
             [75800, 200, 2300, 1500, 1900, 800, 1600]
             + [322800, 1516900, 692700, 326700, 598900, 259100]
             + [400000] * 60)

# SNDK — WDC 스핀오프. when-issued 거래량이 20만~125만 주로 **꽤 크다**.
# 절대 하한만 쓰면 여기 걸려서 2025-02-13 을 집는다(실제는 02-24).
SNDK = _rows(D(2025, 2, 13),
             [369100, 242700, 444500, 220700, 446200, 1252100]
             + [33848500, 8198900, 8389000, 9676100, 7713800]
             + [6000000] * 60)

# PLTR — 직상장. 오염 구간이 없다. 첫날이 제일 크고 이후 감쇠한다.
PLTR = _rows(D(2020, 9, 30),
             [338584400, 124297600, 69901200, 46000000, 38000000]
             + [30000000] * 60)

fails = []


def check(name, rows, want_pre, listing_type=''):
    """몇 번째 거래일을 정규 시작으로 집는지로 검사한다.

    실제 날짜로 검사하면 픽스처의 날짜 생성기가 휴장일을 모델링하는지까지
    같이 시험하게 된다 — SNDK 는 Presidents Day 때문에 하루 밀려 '실패'가
    떴지만 규칙은 양쪽 다 6번째를 정확히 골랐다. 여기서 보려는 건 날짜
    계산이 아니라 **어디서 잘라야 하는가**다.
    """
    _patch(rows)
    got, pre, note = L.resolve('TEST', listing_type)
    want_date = rows[want_pre][0]
    if got != want_date or pre != want_pre:
        fails.append(f'{name}: {got} (앞 {pre}일) — 기대 {want_date} (앞 {want_pre}일)\n'
                     f'      근거: {note}')
    else:
        print(f'  OK  {name:<28} 앞 {pre}거래일 잘라냄 → {got}')


check('LITE 스핀오프 when-issued', LITE, 7, '스핀오프')
check('SNDK 큰 거래량 when-issued', SNDK, 6, '스핀오프')
check('PLTR 오염 없음', PLTR, 0, '직상장')

# SPAC 은 거래량으로 못 가린다 — 셸이 몇 달씩 정상 거래된다. 반드시 거부해야
# 한다. SATL 에서 2021-04-08 이라는 틀린 날짜를 자신 있게 내놓은 적이 있다.
_patch(LITE)
got, pre, note = L.resolve('TEST', 'SPAC')
if got is not None:
    fails.append(f'SPAC 거부 실패: {got} 를 돌려줌 — 거래량으로 판정하면 안 된다')
else:
    print(f'  OK  {"SPAC 은 판정 거부":<28} {note}')

print()
if fails:
    print('실패:')
    for f in fails:
        print('  X ' + f)
    sys.exit(1)
print('전부 통과')
