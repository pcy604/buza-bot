"""대가 관점 3장(린치·오닐·리버모어) 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_guru_pages.py

규칙 판정(lynch.py · oneil.py)을 합성 데이터로 고정하고, fixture(러너가 받아 둔 라이브
번들)가 있으면 실제 렌더까지 돌려 16장이 나오는지 본다.
"""
import os
import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'decks'))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import lynch as LY
import oneil as O

# ── 린치 6유형 ───────────────────────────────────────────────────────
A = lambda r, o=None: {'revenue': r, 'opinc': o or {}}
t = LY.classify(A({2022: 10e6, 2025: 20e6}), [-5e6, -4e6, -3e6, -2e6])
assert t['type'] == 'turnaround', t
t = LY.classify(A({2022: 10e6, 2025: 20e6}), [-5e6, -4e6, -3e6, -2e6, 20e6])
assert t['type'] == 'turnaround' and '흑자 전환' in t['why'], t
t = LY.classify(A({2022: 100e6, 2025: 110e6}), [5e6] * 4, market_cap=100e6, cash=80e6, debt=10e6)
assert t['type'] == 'asset', t
t = LY.classify(A({2021: 100e6, 2025: 120e6}, {2021: 10e6, 2022: -5e6, 2023: 20e6, 2024: 2e6, 2025: 15e6}),
                [5e6] * 4, market_cap=5e9, sector='철강')
assert t['type'] == 'cyclical', t
t = LY.classify(A({2022: 100e6, 2025: 200e6}), [5e6] * 4, market_cap=5e9)
assert t['type'] == 'fast', t
t = LY.classify(A({2022: 100e9, 2025: 130e9}), [5e9] * 4, market_cap=500e9)
assert t['type'] == 'stalwart', t
t = LY.classify(A({2022: 100e6, 2025: 130e6}), [5e6] * 4, market_cap=2e9)
assert t['type'] == 'fast' and t['flags'], '소형 중간성장은 고성장 점검 + 표시'
t = LY.classify(A({2022: 100e9, 2025: 105e9}), [5e9] * 4, market_cap=500e9)
assert t['type'] == 'slow', t
print('✅ 린치 6유형 판정 (회생·자산·경기순환·고성장·대형우량·저성장, 소형 중간성장 표시)')
assert LY.peg(20, 40)[0] == 0.5 and LY.peg(20, 40)[1] == '매우 매력'
assert LY.peg(None, 30)[0] is None and LY.peg(20, -5)[1] == '정의 불가'
print('✅ PEG (린치 기준 구간 · 적자/역성장은 정의 불가)')

# ── 오닐·리버모어 ────────────────────────────────────────────────────
t0 = int(dt.datetime(2024, 1, 1).timestamp())


def mk(prices, vols=None):
    return [{'t': t0 + i * 86400, 'o': p, 'h': p * 1.01, 'l': p * 0.99, 'c': p,
             'v': (vols[i] if vols else 1000)} for i, p in enumerate(prices)]


up = [100 * (1.003 ** i) for i in range(500)]
spy = mk([100 * (1.0005 ** i) for i in range(500)])
cr = O.chart_read(mk(up), spy)
assert cr['ok'] and cr['line'] == '상승' and cr['stage2'] and cr['rs_vs_spy'] > 10, cr['line']
down = [300 * (0.997 ** i) for i in range(500)]
cr2 = O.chart_read(mk(down), spy)
assert cr2['line'] == '하락' and not cr2['stage2'] and cr2['depth'] > 33, (cr2['line'], cr2['depth'])
print('✅ 차트 읽기: 상승 추세=2단계·최소저항선 상승 / 하락 추세=하락·깊은 조정')

m = O.market_direction(spy)
assert m['state'] == '상승 확인' and m['dist_days'] == 0, m
spy_dd = mk([100 * (1.0005 ** i) for i in range(475)] + [123 - 0.5 * k for k in range(25)],
            [1000 + i for i in range(500)])
m2 = O.market_direction(spy_dd)
assert m2['dist_days'] >= 5 and m2['state'] != '상승 확인', m2
print('✅ M: 200일선 + 분산일(하락·거래량 증가) 판정')

L = {'q_eps': {'eps': {'2025-06-30': 0.10, '2026-06-30': 0.20}},
     'quarterly': {'revenue': {'2025-06-30': 100, '2026-06-30': 140}},
     'annual': {'netinc': {2022: 10, 2023: 13, 2024: 17, 2025: 22}, 'equity': {2025: 100}},
     'technical': {'from_high_pct': -5}, 'daily': mk(up), 'inst_activity': {'increased': 10, 'decreased': 5},
     '_chart': cr, '_market': m}
rows = {r[0]: r for r in O.canslim_oneil(L)}
assert [k for k in 'CANSLIM'] == list(rows)
assert rows['C'][2] is True and '+100%' in rows['C'][3]
assert rows['A'][2] is True, rows['A']
assert rows['N'][2] and rows['L'][2] and rows['I'][2] and rows['M'][2]
assert rows['S'][2] is True, rows['S']
L2 = dict(L, q_eps={}, inst_activity={}, ownership={})
r2 = {r[0]: r for r in O.canslim_oneil(L2)}
assert r2['C'][2] is None and r2['I'][2] is None, '데이터 없으면 판단 불가(None)'
print('✅ CANSLIM 원전 7관문: 충족 판정 · 데이터 없으면 판단 불가')

# ── fixture 가 있으면 실제 렌더 ────────────────────────────────────────
fx = ROOT / 'decks' / 'fixtures' / 'satl_live.pkl'
if fx.exists():
    import tempfile
    os.environ['LIVE_FIXTURE_DIR'] = str(fx.parent)
    os.chdir(ROOT / 'decks')
    import build
    out = tempfile.mkdtemp()
    paths = build.build('SATL', out_dir=out)
    assert len(paths) == 17, len(paths)
    print(f'✅ SATL fixture 렌더 {len(paths)}장 (대가 관점 4장 포함)')
print('ALL PASS')
