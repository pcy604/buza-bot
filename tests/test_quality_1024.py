"""2026-10-24 운영 점검 반영 — 유튜브 환각 시점 제거 · 뉴스 헤드라인 원문 연결·나머지 접기·중요 n건 표기. 네트워크 없이."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import analyzer
a = {'key_points': [{'point': 'x', 't': 120}, {'point': 'y', 't': 27210}], 'tickers': [{'name': 'SK', 't': 62140}]}
analyzer.sanitize_times(a, 1300)
assert a['key_points'][0]['t'] == 120 and a['key_points'][1]['t'] is None and a['tickers'][0]['t'] is None, a
b = {'key_points': [{'point': 'z', 't': 30000}]}
assert analyzer.sanitize_times(b)['key_points'][0]['t'] is None, '길이 모르면 6시간 상한'
print('✅ 유튜브: 영상 길이 넘는 시점 제거')

import prefs, ir
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'; ir.NEWS_LOG_PATH = TMP / 'n.json'
import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
ev = [{'title': f'기사 {i}', 'link': f'https://n/{i}', 'source': 'S', 'date': '2026-10-23'} for i in range(1, 8)]
dg = [{'headline': 'SpaceX 합병 협상', 'so_what': '', 'links': ['https://n/3']}, {'headline': '3분기 실적', 'so_what': '이익 증가', 'links': ['https://n/5', 'https://n/6']}]
bot.send_ir_news(1, 'TSLA', ev, dg, lang='ko')
m = OUT[-1]
assert '중요 2건' in m and '새 사건 7건 중' in m, m
assert '<a href="https://n/3"><b>SpaceX 합병 협상</b></a>' in m, m
assert '<blockquote expandable>' in m and m.count('https://n/5') == 1 and 'https://n/1' in m, m
assert '↳ 이익 증가' in m and m.count('↳') == 1, '빈 so_what 은 줄을 안 만든다'
print('✅ 뉴스: 중요 n건 · 헤드라인 원문 링크 · 나머지 접기')
print('ALL PASS')
