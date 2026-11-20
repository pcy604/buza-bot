"""한국 주주구성(6p)·오닐 I — DART 최대주주 현황 + 외국인·기관 수급. 네트워크 없이 돈다.

    python tests/test_kr_ownership.py

fixture(031980.KQ 피에스케이홀딩스)가 있으면 실제 6p 를 그려 OUT_PNG 에 남긴다(눈 검수용).
"""
import os
import pickle
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'decks'))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import sources_kr as SK  # noqa: E402
import oneil as O  # noqa: E402

# DART hyslrSttus.json 응답 모양 그대로(필드명·문자열 숫자·'계' 행·우선주 행)
RAW = [
    {'nm': '박경수', 'relate': '최대주주 본인', 'stock_knd': '보통주',
     'trmend_posesn_stock_co': '4,820,000', 'trmend_posesn_stock_qota_rt': '22.31'},
    {'nm': '박경수', 'relate': '최대주주 본인', 'stock_knd': '우선주',
     'trmend_posesn_stock_co': '1,000', 'trmend_posesn_stock_qota_rt': '50.00'},
    {'nm': '김가나', 'relate': '배우자', 'stock_knd': '보통주',
     'trmend_posesn_stock_co': '300,000', 'trmend_posesn_stock_qota_rt': '1.39'},
    {'nm': '(주)다라', 'relate': '계열회사', 'stock_knd': '보통주',
     'trmend_posesn_stock_co': '1,500,000', 'trmend_posesn_stock_qota_rt': '6.94'},
    {'nm': '계', 'relate': '-', 'stock_knd': '보통주',
     'trmend_posesn_stock_co': '6,620,000', 'trmend_posesn_stock_qota_rt': '30.64'},
]
p = SK.parse_major(RAW)
assert [r['name'] for r in p['rows']] == ['박경수', '(주)다라', '김가나'], p   # 우선주·'계' 제외, 지분 큰 순
assert p['total_pct'] == 30.64 and p['rows'][0]['shares'] == 4_820_000
p2 = SK.parse_major([r for r in RAW if r['nm'] != '계'])
assert p2['total_pct'] == round(22.31 + 1.39 + 6.94, 2), '계 행이 없으면 직접 합산'
assert SK.parse_major([]) == {'rows': [], 'total_pct': None}
print('✅ DART 최대주주 파싱 (보통주만 · 계 행은 합계로 · 지분 큰 순)')

FLOW = {'days': 20, 'from': '20261007', 'to': '20261103', 'foreign': 120_000, 'inst': -50_000,
        'foreign_amt': 3.6e9, 'inst_amt': -1.5e9, 'f_streak': 3, 'i_streak': -2}
rows = {r[0]: r for r in O.canslim_oneil({'ownership': {'flow': FLOW}})}
assert rows['I'][2] is True and '대리' in rows['I'][1] and '+120,000주' in rows['I'][3], rows['I']
rows = {r[0]: r for r in O.canslim_oneil({'ownership': {'flow': dict(FLOW, foreign=-1, inst=0)}})}
assert rows['I'][2] is False
rows = {r[0]: r for r in O.canslim_oneil({'ownership': {}})}
assert rows['I'][2] is None and rows['I'][1] == '기관 매집', '수급 없으면 미국 경로(판단 불가)'
print('✅ 오닐 I 한국 대리 지표 (외국인+기관 순매수 > 0)')

# ── fixture 실제 렌더 ─────────────────────────────────────────────
fx = ROOT / 'decks' / 'fixtures' / '031980_kq_live.pkl'
if fx.exists():
    tmp = Path(tempfile.mkdtemp())
    for f in fx.parent.glob('031980_kq_live*'):
        shutil.copy(f, tmp / f.name)
    d = pickle.loads(fx.read_bytes())
    own = dict(d.get('ownership') or {})
    own['major'] = dict(SK.parse_major(RAW), as_of='2026 반기보고서')
    own['flow'] = FLOW
    d['ownership'] = own
    (tmp / fx.name).write_bytes(pickle.dumps(d))
    os.environ['LIVE_FIXTURE_DIR'] = str(tmp)
    os.chdir(ROOT / 'decks')
    import build
    out = tempfile.mkdtemp()
    paths = build.build('031980.KQ', out_dir=out)
    assert len(paths) >= 10, len(paths)
    six = [x for x in paths if '_04' in Path(x).name or 'p04' in Path(x).name or '04.' in Path(x).name]
    keep = os.environ.get('OUT_PNG')
    if keep:
        for x in paths:
            shutil.copy(x, Path(keep) / Path(x).name)
    print(f'✅ 031980.KQ fixture 렌더 {len(paths)}장')
print('ALL PASS')
