"""계정 연결 — 네트워크 없이(가짜 표) (2026-11-12)."""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['OWNER_CHAT'] = '1'
import prefs, ir, account_link
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'; ir.NEWS_LOG_PATH = TMP / 'n.json'
FUT = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
PAST = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
ROWS = {'u1': {'uid': 'u1', 'code': 'ABC123', 'code_expires': FUT, 'chat_id': None, 'watch_sync': None},
        'u2': {'uid': 'u2', 'code': 'OLD999', 'code_expires': PAST, 'chat_id': None, 'watch_sync': None},
        'u3': {'uid': 'u3', 'code': None, 'chat_id': 33, 'watch_sync': ['TSLA', 'ZZZZZ']}}


class Q:
    def __init__(s): s.f, s.upd, s.notnull = {}, None, None
    def select(s, *_): return s
    def eq(s, k, v): s.f[k] = v; return s
    def update(s, d): s.upd = d; return s
    @property
    def not_(s): return s
    def is_(s, k, _v): s.notnull = k; return s
    def execute(s):
        rows = [r for r in ROWS.values() if all(r.get(k) == v for k, v in s.f.items())
                and (s.notnull is None or r.get(s.notnull) is not None)]
        if s.upd is not None:
            for r in rows: r.update(s.upd)
        return type('R', (), {'data': [dict(r) for r in rows]})()


account_link._tbl = lambda: Q()
import tg
OUT = []
tg.send_message = lambda c, t, reply_markup=None, **k: (OUT.append((str(c), t)), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
M = lambda chat, t: {'chat': {'id': chat}, 'from': {'language_code': 'ko'}, 'text': t}

bot.handle(M(7, '/start link_abc123'))
assert ROWS['u1']['chat_id'] == 7 and ROWS['u1']['code'] is None and '연결됐어요' in OUT[-1][1], OUT
bot.handle(M(8, '/link OLD999'))
assert '만료' in OUT[-1][1] and ROWS['u2']['chat_id'] is None
bot.handle(M(8, '/start link_NOPE00'))
assert '못 찾았어요' in OUT[-1][1]
print('OK 연결')

OUT.clear()
n = account_link.run_sync(lambda c, s: s if s == 'TSLA' else None, tg.send_message)
assert n == 1 and ROWS['u3']['watch_sync'] is None and 'TSLA' in OUT[-1][1] and OUT[-1][0] == '33', OUT
assert account_link.run_sync(lambda c, s: s, tg.send_message) == 0
print('ALL PASS')
