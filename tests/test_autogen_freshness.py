"""재생성 투명성 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_autogen_freshness.py

2026-09-18: "한 번 생성된 종목은 다시 생성해도 숫자만 몇 개 바뀐다"는 지적에서 나왔다.
원인은 병합 자체가 아니라, **무엇이 옛 값인지 파일에 기록이 없었던 것**이다
(보존 목록이 콘솔에만 찍혀서 러너 실행분은 아무도 못 봤다).
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'decks'))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import autogen as A

prev = types.SimpleNamespace(
    BUILT_AT='2026-08-01',
    LOCKED=['HISTORY.founded'],
    HISTORY={'founded': 2011, 'listed': '2022-01-25'},
    SUMMARY='옛 종합평가',
)

# ── 기본(병합): 새 값이 비면 옛 값을 지키고, **지킨 사실을 기록**한다 ──
pick = A._merger(prev)
assert pick('HISTORY.founded', 2099) == 2011, 'LOCKED 가 덮어써짐'
assert pick('HISTORY.listed', '') == '2022-01-25', '빈 값 보호가 안 됨'
assert pick('SUMMARY', '새 종합평가') == '새 종합평가', '새 값이 있는데 옛 값을 씀'
assert pick.carried['HISTORY.founded'] == 'LOCKED'
assert pick.carried['HISTORY.listed'] == '2026-08-01', '보존된 값의 생성일이 기록 안 됨'
assert 'SUMMARY' not in pick.carried, '새로 뽑은 값이 보존으로 기록됨'
print('✅ 기본: LOCKED 유지 · 빈 값 보호 · 보존 사유와 직전 생성일 기록')

# ── --fresh: LOCKED 만 지키고 빈 값 보호는 끈다 ──────────────────────
pf = A._merger(prev, fresh=True)
assert pf('HISTORY.founded', 2099) == 2011, 'fresh 에서도 LOCKED 는 지켜야 한다'
assert pf('HISTORY.listed', '') == '', 'fresh 인데 옛 값이 남음'
assert 'HISTORY.listed' not in pf.carried
print('✅ --fresh: LOCKED 만 유지 · 빈 값은 빈 채로(낡은 값이 새 값인 척 못 함)')

# ── 아카이브: 티커+직전 생성일로 다른 폴더에 남는다 ──────────────────
import tempfile
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    old_out, old_hist = A.OUT_DIR, A.HISTORY_DIR
    A.OUT_DIR, A.HISTORY_DIR = tmp, tmp / 'history'
    try:
        f = tmp / 'zzz_data.py'
        f.write_text("BUILT_AT = '2026-08-01'\nSUMMARY = 'x'\n", encoding='utf-8')
        A._archive('ZZZ', f)
        dest = tmp / 'history' / 'zzz_20260801_data.py'
        assert dest.exists(), f'보관본이 없음: {list((tmp / "history").glob("*")) if (tmp/"history").exists() else "폴더 없음"}'
        assert "BUILT_AT = '2026-08-01'" in dest.read_text(encoding='utf-8')
        # 파일이 없을 때(첫 생성) 조용히 넘어가야 한다 — 보관 실패가 생성을 막으면 안 된다.
        A._archive('ZZZ', tmp / 'nonexistent_data.py')
    finally:
        A.OUT_DIR, A.HISTORY_DIR = old_out, old_hist
print('✅ 아카이브: decks/history/<티커>_<직전생성일>_data.py 로 보관 · 첫 생성 시 무시')
