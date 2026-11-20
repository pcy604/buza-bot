"""리포트 재고 갱신 대기열(decks/refresh.py) 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_refresh_queue.py

2026-10-20: 차단(30일)이 난 뒤에야 고치던 것을 미리 고치고, 감시 종목을 먼저 챙긴다.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'decks'))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import refresh
import check

refresh.STATE_PATH = Path(tempfile.mkdtemp()) / 'deck_refresh.json'
check._all_tickers = lambda: ['AAA', 'BBB', 'CCC', 'DDD']
refresh.scan = lambda: [('BBB', [('AS_OF', '35일')])]
AGES = {'AAA': 25, 'BBB': 35, 'CCC': 3, 'DDD': 22}
refresh._built_age = lambda tk: AGES[tk]
refresh._watched = lambda: {'DDD', 'NEWW'}

due = dict(refresh.due())
assert set(due) == {'AAA', 'BBB', 'DDD', 'NEWW'}, due          # CCC(3일)는 아직
assert due['NEWW'][0][0] == 'NEW' and due['AAA'][0][0] == 'AGE'
print('✅ 대기열: 차단 + 21일 지남 + 감시 중인데 리포트 없음 (신선한 건 제외)')

order = []
for _ in range(4):
    tk = refresh.pick()
    order.append(tk)
    refresh.mark(tk, True)
    st = refresh.load()
    st[tk]['last_try'] = '2000-01-01'          # '오늘 이미 시도' 로 걸러지지 않게 과거로
    refresh.save(st)
    refresh.scan = (lambda done: (lambda: [x for x in [('BBB', [('AS_OF', '35일')])] if x[0] not in done]))(set(order))
    AGES.update({t: 0 for t in order})
    refresh._watched = (lambda done: (lambda: {'DDD', 'NEWW'} - done))(set(order))
assert order[:2] == ['NEWW', 'BBB'] or order[:2] == ['BBB', 'NEWW'], order
assert order[2] == 'DDD' and order[3] == 'AAA', order
print(f'✅ 우선순위: 차단·신규 → 감시 중인 노후 → 그 밖의 노후 ({order})')
print('ALL PASS')
