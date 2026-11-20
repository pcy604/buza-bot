"""메뉴에서 명령만 눌렀을 때 → 사용법(답장 모드), 답장하면 원래 명령으로 처리. 네트워크 없이 돈다."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import prefs, ir
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'; ir.NEWS_LOG_PATH = TMP / 'n.json'
import tg
OUT = []
tg.send_message = lambda c, t, reply_markup=None, **k: (OUT.append((t, reply_markup)), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
DD = []
bot.send_deck = lambda chat, tk: DD.append(('deck', tk))
ir.resolve_ticker = lambda t: (1, 'X Corp') if t in ('TSLA', 'RIVN') else (None, None)
M = lambda t, **k: dict({'chat': {'id': 4}, 'from': {'language_code': 'ko'}, 'text': t}, **k)

# 2026-11-13 /dd 는 /report 로 통합 — 인자 유무와 관계없이 안내만
bot.handle(M('/dd'))
assert '/report' in OUT[-1][0] and not DD, OUT[-1]
bot.handle(M('/dd TSLA'))
assert '/report TSLA' in OUT[-1][0] and not DD, OUT[-1]
n = len(OUT)
bot.handle(M('/watch', _usage_sent=True))
assert len(OUT) == n, 'Worker 가 이미 보냈으면 중복 안 보냄'
bot.handle(M('/report@buza_alarm_bot'))
assert '/report' in OUT[-1][0] and OUT[-1][1]['force_reply']
bot.handle(M('TSLA', reply_to_message={'from': {'is_bot': True}, 'text': OUT[-1][0]}))
assert DD[-1] == ('deck', 'TSLA'), DD
# 사람 메시지에 답장한 건 바꾸지 않는다
assert bot._from_reply({'reply_to_message': {'from': {'is_bot': False}, 'text': '/report'}}, 'TSLA') == 'TSLA'
print('✅ 명령만 → 사용법(답장 모드) · 답장 → 원래 명령 · Worker 중복 방지')
print('ALL PASS')
