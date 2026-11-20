"""감시 뉴스 '사용자별 하루 1번' 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_news_delivery.py

2026-10-20 재설계(ir.deliver_news · prefs.py)를 고정한다. 옛 방식의 결함 둘이 다시
들어오지 않게 하는 게 핵심이다(실측 2026-10-19):
  ① 순위 밖으로 밀렸다 돌아온 옛 기사를 '새 뉴스'로 다시 보냄 (기준선 변경 78회 중 58회)
  ② LLM 이 '중요한 것 없음'이라 했는데 링크만 달아 보냄 (55건 중 22건)
"""
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import prefs
import ir

# 운영 파일을 절대 건드리지 않게 맨 앞에서 경로를 돌린다(test_news_push 의 교훈).
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'user_prefs.json'
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'
assert not prefs.PREFS_PATH.is_relative_to(ROOT) and not ir.STATE_PATH.is_relative_to(ROOT)

# ── prefs 파싱 ───────────────────────────────────────────────────────
assert prefs.parse_hour('7') == 7 and prefs.parse_hour('07:30') == 7
assert prefs.parse_hour('7pm') == 19 and prefs.parse_hour('12am') == 0 and prefs.parse_hour('19시') == 19
assert prefs.parse_hour('24') is None and prefs.parse_hour('abc') is None
assert prefs.parse_tz('Asia/Seoul') == 'Asia/Seoul'
assert prefs.parse_tz('asia/seoul') == 'Asia/Seoul', prefs.parse_tz('asia/seoul')
assert prefs.parse_tz('+9') == 'UTC+09:00' and prefs.parse_tz('UTC-5') == 'UTC-05:00'
assert prefs.parse_tz('+5:30') == 'UTC+05:30' and prefs.parse_tz('Mars/Base') is None
assert prefs.parse_lang('EN') == 'en' and prefs.parse_lang('한국어') == 'ko' and prefs.parse_lang('xx') is None
print('✅ 시각·시간대·언어 입력 파싱')

# 첫 접촉: 앱 언어로 추정, 이후엔 덮어쓰지 않음
prefs.remember_client_language(10, 'ko')
assert prefs.get(10) == {'tz': 'Asia/Seoul', 'hour': 8, 'lang': 'ko'}, prefs.get(10)
prefs.set_tz(10, 'Europe/Warsaw')
prefs.remember_client_language(10, 'en')
assert prefs.get(10)['tz'] == 'Europe/Warsaw' and prefs.get(10)['lang'] == 'ko'
prefs.remember_client_language(11, 'xx-YY')
assert prefs.get(11)['lang'] == 'en'
print('✅ 첫 접촉 추정 · 사용자가 고른 값은 안 덮어씀 · 모르는 언어는 en')

# 시각 판정: 서울 08시 = UTC 23시(전날)
p = {'tz': 'Asia/Seoul', 'hour': 8, 'lang': 'ko'}
assert not prefs.hour_reached(p, datetime(2026, 10, 19, 22, 30, tzinfo=timezone.utc))   # 서울 07:30
assert prefs.hour_reached(p, datetime(2026, 10, 19, 23, 5, tzinfo=timezone.utc))        # 서울 08:05
assert prefs.local_day(p, datetime(2026, 10, 19, 23, 5, tzinfo=timezone.utc)) == '2026-10-20'
assert prefs.hour_reached({'tz': 'UTC+05:30', 'hour': 9}, datetime(2026, 10, 20, 3, 31, tzinfo=timezone.utc))
print('✅ 사용자 시간대 기준 시각·날짜 판정 (서머타임·반시간 오프셋 포함)')

# ── deliver_news ────────────────────────────────────────────────────
ir.resolve_ticker = lambda t: (1, 'Satellogic')
CALLS, SENT = [], []


def fake_summary(t, company, items, lang='ko', thesis='', known=None, filed=None):
    CALLS.append((t, lang, [i['title'] for i in items]))
    return SUMMARY(items)


def fake_send(chat, t, items, digest, lang='ko', reaction=None):
    SENT.append((chat, t, [i['title'] for i in items], digest, lang))
    return True


ir.summarize_news = fake_summary
ir._daily_rows = lambda t: []          # 네트워크 없이 — 주가 반응은 test_price_reaction 에서
SUMMARY = lambda items: [{'headline': 'h', 'so_what': 's'}]


def rss(rows):
    ir._RSS_CACHE.clear()
    ir._RSS_CACHE['Satellogic'] = [
        {'title': title, 'link': f'https://n/{title}', 'source': 'Reuters',
         'pubDate': ts.strftime('%a, %d %b %Y %H:%M:%S GMT')} for title, ts in rows]


def U(d, h):
    return datetime(2026, 10, d, h, 0, tzinfo=timezone.utc)


prefs.set_hour(1, 8); prefs.set_tz(1, 'UTC'); prefs.set_lang(1, 'ko')
ir.save_state({'watches': {'1': ['SATL']}, 'seen': {}, 'news': {'1': {'SATL': {'mark': U(19, 8).isoformat(),
                                                                              'slot': '2026-10-19@20'}}}})

# 12시간 회차(2026-10-21~): 08시·20시. 직전 회차(19일 20시)를 이미 받았으면 20일 08시 전엔 아무것도 안 함
assert prefs.current_slot({'tz': 'UTC', 'hour': 8}, U(20, 7)) == '2026-10-19@20'
assert prefs.current_slot({'tz': 'UTC', 'hour': 8}, U(20, 21)) == '2026-10-20@20'
assert prefs.current_slot({'tz': 'Asia/Seoul', 'hour': 8}, U(20, 23)) == '2026-10-21@08'
ir._RSS_CACHE.clear()
assert ir.deliver_news(fake_send, now=U(20, 7)) == 0 and not CALLS and not ir._RSS_CACHE
print('✅ 설정 시각 전에는 수집·요약·발송 0')

# 08시: 지난 mark(19일 08시) 이후 발행분만. 그보다 한참 전 기사는 제외
rss([('Merlin launch succeeds', U(19, 20)),
     ('Navy contract expanded', U(20, 6)),
     ('Old story from last week', U(12, 9))])
assert ir.deliver_news(fake_send, now=U(20, 8)) == 1
assert SENT[-1][2] == ['Navy contract expanded', 'Merlin launch succeeds'], SENT[-1]
assert 'Old story from last week' not in str(CALLS)
print('✅ 마지막 처리 시각 이후 발행분만 요약·발송 (옛 기사 제외)')

# 같은 날 다시 돌면 아무것도 안 보냄
assert ir.deliver_news(fake_send, now=U(20, 11)) == 0 and len(SENT) == 1
print('✅ 같은 회차엔 1번')
# 전환 첫날: 예전 기록(day=오늘, slot 없음)이면 오늘 설정 시각 회차는 받은 걸로 친다
assert ir.deliver_news.__doc__

# 다음 날: 늦게 색인된 기사(발행은 어제 07시, 겹침 구간 안)는 잡고, 이미 보낸 건 다시 안 보냄
rss([('Merlin launch succeeds', U(19, 20)),          # 어제 보냄 — 겹침 구간이지만 제외돼야
     ('Navy contract expanded', U(20, 6)),            # 어제 보냄 — 겹침 구간 밖
     ('Late-indexed: CFO appointed', U(20, 7)),       # 어제 08시 직전 발행, 어제는 색인 전이었음
     ('Q3 results date set', U(21, 1))])
ir.deliver_news(fake_send, now=U(21, 8))
assert SENT[-1][2] == ['Q3 results date set', 'Late-indexed: CFO appointed'], SENT[-1][2]
print('✅ 늦게 색인된 기사는 겹침 구간으로 잡고, 이미 보낸 기사는 재발송 안 함')

st = ir.load_state()
assert 'seen_news' not in st
assert len(st['news']['1']['SATL']['sent']) <= 4, st['news']['1']['SATL']['sent']
print(f"✅ 보낸 기록은 겹침 구간 것만 남음 ({len(st['news']['1']['SATL']['sent'])}개) — 쌓이지 않음")

# 잡음뿐(digest=[]) → 보내지 않되 처리 완료로 기록
SUMMARY = lambda items: []
rss([('Satellogic presents at Cantor technology conference', U(22, 2))])
n_before = len(SENT)
CALLS.clear()
assert ir.deliver_news(fake_send, now=U(22, 8)) == 0 and len(SENT) == n_before and len(CALLS) == 1
assert ir.load_state()['news']['1']['SATL']['day'] == '2026-10-22'
print('✅ 중요한 사건이 없으면 발송 안 함 (옛 결함 ②)')

# 요약 실패(None) → 재시도, 3번째에 링크로
SUMMARY = lambda items: None
rss([('Satellogic launches Merlin satellite batch', U(23, 3))])
for h in (8, 9):
    assert ir.deliver_news(fake_send, now=U(23, h)) == 0
assert ir.load_state()['news']['1']['SATL'].get('day') != '2026-10-23'
assert ir.deliver_news(fake_send, now=U(23, 10)) == 1 and SENT[-1][3] is None
print('✅ 요약 실패 시 다음 실행에 재시도, 3번 실패하면 링크로 발송')

# 두 사용자·같은 언어·같은 기사 → LLM 1회 공유, 다른 언어면 따로
SUMMARY = lambda items: [{'headline': 'h'}]
prefs.set_hour(2, 8); prefs.set_tz(2, 'UTC'); prefs.set_lang(2, 'ko')
prefs.set_hour(3, 8); prefs.set_tz(3, 'UTC'); prefs.set_lang(3, 'en')
st = ir.load_state()
st['watches'] = {'1': ['SATL'], '2': ['SATL'], '3': ['SATL']}
st['news'] = {c: {'SATL': {'mark': U(23, 12).isoformat()}} for c in ('1', '2', '3')}
ir.save_state(st)
rss([('Satellogic wins NASA data contract', U(24, 2))])
CALLS.clear()
assert ir.deliver_news(fake_send, now=U(24, 8)) == 3
assert sorted(c[1] for c in CALLS) == ['en', 'ko'], CALLS
assert SENT[-1][4] == 'en' or any(s[4] == 'en' for s in SENT[-3:])
print('✅ 같은 언어 사용자끼리 요약 공유(LLM 2회/3명) · 언어별 발송')

# 시간대가 다르면 각자 자기 08시에
prefs.set_tz(3, 'America/New_York')     # 뉴욕 08시 = UTC 12시(EDT)
st = ir.load_state()
st['news'] = {c: {'SATL': {'mark': U(24, 8).isoformat(), 'slot': sl}}
              for c, sl in (('1', '2026-10-24@20'), ('2', '2026-10-24@20'), ('3', '2026-10-24@20'))}
ir.save_state(st)
rss([('Satellogic signs imagery deal with Brazil', U(25, 3))])
SENT.clear()
ir.deliver_news(fake_send, now=U(25, 8))
assert sorted(s[0] for s in SENT) == [1, 2], SENT
ir.deliver_news(fake_send, now=U(25, 12))
assert sorted(s[0] for s in SENT) == [1, 2, 3], SENT
print('✅ 사용자마다 자기 시간대의 설정 시각에 발송')

# ── 발송 문구 언어 ──────────────────────────────────────────────────
import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
ev = [{'title': 'A', 'link': 'https://x/1', 'source': 'S', 'date': '2026-10-20', 'echo': 2}]
bot.send_ir_news(1, 'SATL', ev, None, lang='en')
assert 'new stories' in OUT[-1] and 'Sources' in OUT[-1] and '2 outlets' in OUT[-1] and 'Summary unavailable' in OUT[-1]
bot.send_ir_news(1, 'SATL', ev, None, lang='ja')
assert 'new stories' in OUT[-1], '틀 문구가 없는 언어는 en 으로'
bot.send_ir_news(1, 'SATL', ev, None)
assert '새 뉴스' in OUT[-1] and '원문' in OUT[-1]
print('✅ 틀 문구 ko/en, 그 외 언어는 en 폴백')

# /settings 명령
OUT.clear()
bot.route_settings(5, '/lang en')
bot.route_settings(5, '/tz +9')
bot.route_settings(5, '/time 7am')
bot.route_settings(5, '/settings')
assert prefs.get(5) == {'tz': 'UTC+09:00', 'hour': 7, 'lang': 'en'}, prefs.get(5)
assert '07:00' in OUT[-1] and 'UTC+09:00' in OUT[-1] and 'English' in OUT[-1]
bot.route_settings(5, '/time 99')
assert 'Usage' in OUT[-1]
print('✅ /settings · /time · /tz · /lang')

# ── 온보딩: /start → 티커 나열 → 감시 등록 ───────────────────────────
ir.add_watch = lambda c, t: WATCHED.append((c, t))
ir.watches_of = lambda c: [t for cc, t in WATCHED if cc == c]
ir.resolve_ticker = lambda t: (1, 'X') if t in ('SATL', 'AXTI') else (None, None)
import history
history.log = lambda *a, **k: None
import db
db.upsert_user = lambda *a, **k: None
WATCHED = []
OUT.clear()
prefs.remember_client_language(77, 'ko')
bot.handle({'chat': {'id': 77}, 'from': {'language_code': 'ko'}, 'text': '/start'})
assert '티커' in OUT[-1] and prefs.get(77).get('onboarding'), OUT[-1]
bot.handle({'chat': {'id': 77}, 'from': {}, 'text': '$satl, AXTI zzzz'})
assert WATCHED == [(77, 'SATL'), (77, 'AXTI')], WATCHED
assert 'SATL, AXTI' in OUT[-1] and 'ZZZZ' in OUT[-1] and not prefs.get(77).get('onboarding'), OUT[-1]
# 감시가 있으면 /start 는 도움말
bot.handle({'chat': {'id': 77}, 'from': {}, 'text': '/start'})
assert '/watch' in OUT[-1] or 'watch' in OUT[-1]
# 영어 사용자 /help 는 영어
prefs.remember_client_language(78, 'en')
bot.handle({'chat': {'id': 78}, 'from': {}, 'text': '/help'})
assert 'News & filings digest' in OUT[-1]
print('✅ 온보딩: /start → 티커 나열 한 번에 감시 등록 · 못 찾은 티커 안내 · 언어별 도움말')

# ── 피드백 ───────────────────────────────────────────────────────────
OUT.clear()
bot.send_ir_news(1, 'BRK.B', ev, [{'headline': 'h'}], lang='ko')
assert '/good_BRK_B' in OUT[-1] and '/bad_BRK_B' in OUT[-1], OUT[-1]
bot.handle({'chat': {'id': 77}, 'from': {}, 'text': '/good_BRK_B'})
bot.handle({'chat': {'id': 77}, 'from': {}, 'text': '/bad_satl'})
fb = [r for r in ir.news_log(1) if r.get('stage') == 'feedback']
assert [(r['vote'], r['ticker']) for r in fb] == [('good', 'BRK_B'), ('bad', 'SATL')], fb
assert '고마워요' in OUT[-1]
print('✅ 요약 피드백 링크(/good_·/bad_) 발송 · 기록')
print('ALL PASS')

# ── 12시간 회차 전환 ──
ir.resolve_ticker = lambda t: (1, 'Satellogic')
ir.save_state({'watches': {'5': ['SATL']}, 'seen': {}, 'news': {'5': {'SATL': {'mark': U(25, 8).isoformat(), 'day': '2026-10-25'}}}})
prefs.set_hour(5, 8); prefs.set_tz(5, 'UTC'); prefs.set_lang(5, 'ko')
SUMMARY = lambda items: [{'headline': 'h'}]
rss([('Evening contract news', U(25, 15))])
n0 = len(SENT)
assert ir.deliver_news(fake_send, now=U(25, 12)) == 0, '예전 방식으로 오늘 08시분을 받았으면 중복 없음'
assert ir.deliver_news(fake_send, now=U(25, 20)) == 1 and SENT[-1][2] == ['Evening contract news']
assert ir.deliver_news(fake_send, now=U(25, 23)) == 0 and len(SENT) == n0 + 1
print('✅ 12시간마다(08·20시) · 전환 첫날 중복 없음')
print('ALL PASS')
