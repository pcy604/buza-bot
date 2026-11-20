"""/voc — 접수·소유자 알림·답장 입력·소유자 목록/완료·KPI 집계. 네트워크 없이 돈다."""
import os, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['OWNER_CHAT'] = '1'
import prefs, ir, voc
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'; ir.NEWS_LOG_PATH = TMP / 'n.json'
voc.LOG_PATH = TMP / 'voc.json'
import tg
OUT = []
tg.send_message = lambda c, t, reply_markup=None, **k: (OUT.append((str(c), t, reply_markup)), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
M = lambda chat, t, **k: dict({'chat': {'id': chat}, 'from': {'language_code': 'ko', 'username': f'u{chat}'}, 'text': t}, **k)

# 외부 사용자: 내용과 함께 → 접수 + 소유자(1) 알림
bot.handle(M(7, '/voc 리포트 글씨가 작아요'))
assert OUT[-2][0] == '7' and '#1' in OUT[-2][1], OUT
assert OUT[-1][0] == '1' and '새 VOC #1' in OUT[-1][1] and '@u7' in OUT[-1][1], OUT
# 명령만 → 답장 모드 사용법, 답장하면 접수
bot.handle(M(7, '/voc'))
usage = OUT[-1][1]
assert OUT[-1][2] and OUT[-1][2]['force_reply'], OUT[-1]
bot.handle(M(7, '감시 알림 시간 바꾸고 싶어요', reply_to_message={'from': {'is_bot': True}, 'text': usage}))
assert '#2' in OUT[-2][1], OUT[-2]
# 소유자 본인 건은 소유자에게 다시 알리지 않음
n = len(OUT)
bot.handle(M(1, '/voc 내가 쓰다 발견한 것'))
assert len(OUT) == n + 1 and '#3' in OUT[-1][1], OUT[n:]
# 소유자 목록·완료
bot.handle(M(1, '/voc list'))
assert '#1' in OUT[-1][1] and '#3' in OUT[-1][1] and '(나)' in OUT[-1][1], OUT[-1]
bot.handle(M(1, '/voc done 1'))
assert '#1 처리 완료' in OUT[-1][1]
assert [r['id'] for r in voc.open_items()] == [2, 3]
# 외부 사용자는 list 를 못 본다 — 'list' 가 그냥 의견으로 접수됨
bot.handle(M(7, '/voc list'))
assert '#4' in OUT[-2][1]
# KPI: 외부 3건(1·2·4), 본인 1건
c = voc.month_counts()
assert c['external'] == 3 and c['owner'] == 1 and c['open'] == 3, c
import kpi
k = kpi.kpi_voice()
assert k['value'] == '3건' and k['verdict'] == kpi.OK, k
print('✅ /voc 접수·소유자 알림·답장 입력·list/done·KPI 집계')
print('ALL PASS')
