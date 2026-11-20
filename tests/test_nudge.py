"""먼저 묻기(nudge) + /voc done 회신 + 바로 써보기 예시 — 네트워크 없이 돈다 (2026-11-12)."""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ['OWNER_CHAT'] = '1'
import prefs, ir, voc, nudge
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'; ir.NEWS_LOG_PATH = TMP / 'n.json'
voc.LOG_PATH = TMP / 'voc.json'; nudge.STATE_PATH = TMP / 'nudge.json'
import tg
OUT = []
tg.send_message = lambda c, t, reply_markup=None, **k: (OUT.append((str(c), t, reply_markup)), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
import stats
stats.log = lambda *a, **k: None
M = lambda chat, t: {'chat': {'id': chat}, 'from': {'language_code': 'ko', 'username': f'u{chat}'}, 'text': t}

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
ago = lambda h: (NOW - timedelta(hours=h)).isoformat()
rows = [
    {'ts': ago(30), 'chat': 1, 'cmd': '/report'},           # 소유자 — 제외
    {'ts': ago(30), 'chat': 2, 'cmd': '/start'},            # 24h+ 미등록 → remind
    {'ts': ago(10), 'chat': 3, 'cmd': '/start'},            # 아직 24h 안 됨
    {'ts': ago(40), 'chat': 4, 'cmd': '/start'}, {'ts': ago(30), 'chat': 4, 'cmd': '/report'},  # → survey
    {'ts': ago(5), 'chat': 5, 'cmd': '/market'},            # 첫 사용 5시간 → 아직
    {'ts': ago(24 * 40), 'chat': 6, 'cmd': '/start'},       # 40일 조용 → 제외
    {'ts': ago(30), 'chat': 7, 'cmd': '/start'},            # 감시만 있음(온보딩 텍스트 등록) → remind 아님
]
p = sorted(nudge.plan(rows, '1', {'7'}, {}, NOW))
assert p == [('2', 'remind'), ('4', 'survey')], p
# 한 번 보낸 사람은 다시 안 보낸다
assert nudge.plan(rows, '1', {'7'}, {'2': {'remind': 'x'}, '4': {'survey': 'x'}}, NOW) == []

n = nudge.run(lambda c, t, kb: tg.send_message(c, t, reply_markup=kb), '1', {'7'}, rows=rows, now=NOW)
assert n == 2, n
assert OUT[0][2] is nudge.ONBOARD_KB and OUT[1][2] is nudge.SURVEY_KB
assert prefs.get(2).get('onboarding') is True          # 버튼 누르면 곧장 감시 등록되게
assert nudge.run(lambda *a: True, '1', {'7'}, rows=rows, now=NOW) == 0   # 사람당 1회
print('OK 리마인드·설문 대상 선정')

# 설문 버튼 응답 → VOC 접수(+소유자 알림) · 👎 면 답장 입력 받기
OUT.clear()
bot.handle(M(4, '👎 별로예요'))
assert nudge.summary()['bad'] == 1
assert any('[설문] 👎' in r['text'] for r in voc._load())
assert any('/voc' in t and rm and rm.get('force_reply') for c, t, rm in OUT if c == '4'), OUT
assert any(c == '1' and '새 VOC' in t for c, t, _ in OUT), '소유자 알림'
OUT.clear()
bot.handle(M(9, '👍 쓸만해요'))
assert nudge.summary()['good'] == 1 and not any((rm or {}).get('force_reply') for _, _, rm in OUT)
print('OK 설문 응답')

# /voc done → 원래 보낸 사람에게 회신
OUT.clear()
bot.handle(M(8, '/voc 시황이 너무 길어요'))
vid = max(r['id'] for r in voc._load())
OUT.clear()
bot.handle(M(1, f'/voc done {vid} 요약판을 추가했어요'))
to_user = [t for c, t, _ in OUT if c == '8']
assert to_user and '반영했어요' in to_user[0] and '요약판' in to_user[0], OUT
assert any(c == '1' and '사용자에게 알림 보냄' in t for c, t, _ in OUT)
OUT.clear()
bot.handle(M(1, f'/voc done {vid}'))                    # 이미 처리됨
assert any('못 찾았어요' in t for _, t, _ in OUT)
print('OK /voc done 회신')

# 바로 써보기 예시는 비소유자도 성공하는 명령이어야 한다(/report 한국 종목은 비소유자 중단)
quick = bot.WELCOME.split('빠른 시작')[1].split('\n')[1]
assert '/report 삼성전자' not in quick and '/report TSLA' in quick, quick
assert '삼성전자' not in bot.USAGE['/report'][1]
# /start(감시 없음) → 버튼 달린 온보딩
OUT.clear()
bot.handle(M(11, '/start'))
assert OUT and OUT[-1][2] is nudge.ONBOARD_KB
print('OK 온보딩 예시·버튼')
print('ALL PASS')
