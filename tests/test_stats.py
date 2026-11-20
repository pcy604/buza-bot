"""/stats·일간 사용 현황 — 본인 제외 DAU/WAU/MAU·가입·기능 순위, 소유자 전용, 한국 리포트 일시 중단(비소유자). 네트워크 없이."""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['OWNER_CHAT'] = '1'
import stats, prefs, ir
TMP = Path(tempfile.mkdtemp())
stats.LOG_PATH = TMP / 'a.json'; prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'
now = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)
rows = [dict(ts=(now - timedelta(hours=h)).isoformat(), chat=c, cmd=m) for h, c, m in
        [(1, 7, '/market'), (2, 7, '/watch'), (30, 8, '/report'), (200, 9, '/yt'), (900, 10, '/help'), (1, 1, '/stats')]]
stats.LOG_PATH.write_text(__import__('json').dumps(rows))
users = [dict(chat_id=1, username='me', created_at='2026-07-01T00:00:00+00:00'),
         dict(chat_id=7, username='a', created_at=(now - timedelta(hours=5)).isoformat()),
         dict(chat_id=8, username='b', created_at=(now - timedelta(days=3)).isoformat()),
         dict(chat_id=9, username='c', created_at='2026-09-01T00:00:00+00:00')]
s = stats.compute(now, users)
assert (s['users'], s['new_1d'], s['new_7d']) == (3, 1, 2), s
assert (s['dau'], s['wau'], s['mau']) == (1, 2, 3), s
assert s['owner_msgs_7d'] == 1 and ('/market', 1) in s['top_cmds'], s
t = stats.text(s)
assert '가입자 <b>3명</b>' in t and 'DAU <b>1</b>' in t and '@a' in t, t
assert stats.cmd_of('/report@buza_alarm_bot 005930') == '/report' and stats.cmd_of('https://youtu.be/x') == '(유튜브 링크)'
assert stats.cmd_of('/report') is None and stats.cmd_of('/voc') is None and stats.cmd_of('/market') == '/market', '사용법만 본 건 안 셈'
import sys as _sys; _a = _sys.argv[:]; _sys.argv[0] = 'tests/test_stats.py'; n0 = len(stats._load()); stats.log(5, '/x'); assert len(stats._load()) == n0, '테스트 실행은 실제 로그에 안 씀'; _sys.argv[:] = _a
print('✅ 지표 계산(본인 제외)·문구')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append((str(c), t)), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
stats.compute = lambda *a, **k: s
M = lambda c, t: {'chat': {'id': c}, 'from': {'language_code': 'ko'}, 'text': t}
bot.handle(M(1, '/stats'))
assert '사용 현황' in OUT[-1][1]
bot.handle(M(7, '/stats'))
assert '사용 현황' not in OUT[-1][1], '소유자 아니면 안 보임'
import kr
kr.search = lambda q: [('031980', '피에스케이홀딩스')]
kr.to_symbol = lambda c: ('031980.KQ', '')
kr.is_kr_query = lambda q: True
DECK = []
bot.send_deck = lambda chat, sym: DECK.append((chat, sym))
bot.handle(M(7, '/report 031980'))
assert not DECK and '잠시 쉬어요' in OUT[-1][1], OUT[-1]
bot.handle(M(1, '/report 031980'))
assert DECK == [(1, '031980.KQ')], '소유자는 계속 생성(개선 확인용)'
print('✅ /stats 소유자 전용 · 한국 리포트 비소유자 일시 중단')
print('ALL PASS')
