"""IR 발표자료 감시(ir_site.py) 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_ir_site.py

목록 HTML 은 Nasdaq IR(Drupal) 계열 마크업을 본떠 만들었다. 실제 SATL 페이지
(2026-10-20 확인)의 링크 형태 '/static-files/<uuid>'·날짜 'September 18, 2026'·
title 속성의 원래 파일명을 그대로 따랐다. 실서버 마크업과 다르면 러너의
ir_site_state.json 기준선이 비어 있는 것으로 드러난다 — 그때 이 픽스처를 실측으로 바꿀 것.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import ir_site
import prefs
import ir

TMP = Path(tempfile.mkdtemp())
ir_site.STATE_PATH = TMP / 'ir_site_state.json'
prefs.PREFS_PATH = TMP / 'user_prefs.json'
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'

BASE = 'https://investors.satellogic.com'
PAGE = """
<div class="views-row">
  <div class="nir-widget--field nir-widget--event--date-time">September 18, 2026</div>
  <div class="nir-widget--field nir-widget--event--title">Investor Presentation</div>
  <a href="/static-files/4a5e5c3f-6fd0-48a5-89bb-12c5b858579c"
     title="Satellogic_IR_Presentation_September_2026_FINAL v2.pdf">Investor Presentation</a>
</div>
<div class="views-row">
  <div class="date">August 5, 2026</div>
  <h4>Q2 2026 Conference Call Presentation</h4>
  <a class="file-link" href="https://investors.satellogic.com/static-files/da34ff7a-5c0d-46f6-a523-ceaa5501e00f"
     title="SATL_Q2_2026.pdf">Download</a>
</div>
<div class="views-row">
  <div class="date">May 12, 2026</div>
  <a href="/static-files/01d60ebc-0877-4805-b650-f32802b1bb73">Q1 2026 Conference Call &amp; Webcast</a>
  <a href="/static-files/01d60ebc-0877-4805-b650-f32802b1bb73">PDF</a>
</div>
<a href="/news-releases">News</a>
"""

items = ir_site.parse_presentations(PAGE, BASE)
assert [i['date'] for i in items] == ['2026-09-18', '2026-08-05', '2026-05-12'], items
assert items[0]['title'] == 'Investor Presentation'
assert items[1]['title'] == 'Q2 2026 Conference Call Presentation', items[1]
assert items[2]['title'] == 'Q1 2026 Conference Call & Webcast', items[2]
assert items[0]['url'] == BASE + '/static-files/4a5e5c3f-6fd0-48a5-89bb-12c5b858579c'
assert len(items) == 3, '같은 파일 링크가 두 번 잡힘'
print('✅ 발표자료 목록 파싱: 제목(버튼 글자면 앞 제목) · 날짜 · 절대 URL · 중복 제거')

# ── check(): 기준선 → 새 자료 → 비교 요약 → 언어별 발송 ─────────────
ir.save_state({'watches': {'1': ['SATL'], '2': ['SATL']}, 'seen': {}, 'news': {}})
prefs.set_lang(1, 'ko'); prefs.set_lang(2, 'en')
ir.resolve_ticker = lambda t: (1, 'Satellogic Inc.')


class R:
    def __init__(self, text): self.text, self.status_code = text, 200


PAGES = {'cur': PAGE}
ir_site._get = lambda url, **k: R(PAGES['cur'])
TEXTS = {}
ir_site.pdf_text = lambda url, limit: TEXTS.get(url, 'slide text')
CALLS, SENT = [], []
RESULT = {'v': {'headline': 'Backlog up', 'changes': ['Backlog $40M → $55M'], 'key_points': [], 'watch': []}}


def fake_sum(t, company, new, prev, nt, pt, lang='ko'):
    CALLS.append((new['title'], (prev or {}).get('title'), lang))
    return RESULT['v']


ir_site.summarize_deck = fake_sum
send = lambda c, t, item, digest, lang='ko': (SENT.append((c, item['title'], bool(digest), lang)), True)[1]

assert ir_site.check(send) == 0 and not CALLS
st = ir_site.load_state()
assert len(st['decks']['SATL']['seen']) == 3 and st['sites']['SATL']['base'] == BASE
print('✅ 처음 본 날은 기준선만 (지난 자료를 쏟아내지 않음)')

assert ir_site.check(send) == 0 and not SENT
print('✅ 새 자료 없으면 아무것도 안 함')

PAGES['cur'] = """<div><div>October 30, 2026</div><h4>Q3 2026 Conference Call Presentation</h4>
<a href="/static-files/aaaaaaaa-1111-2222-3333-444444444444" title="q3.pdf">Download</a></div>""" + PAGE
assert ir_site.check(send) == 2
assert sorted(CALLS) == [('Q3 2026 Conference Call Presentation', 'Investor Presentation', 'en'),
                         ('Q3 2026 Conference Call Presentation', 'Investor Presentation', 'ko')], CALLS
assert sorted(SENT) == [(1, 'Q3 2026 Conference Call Presentation', True, 'ko'),
                        (2, 'Q3 2026 Conference Call Presentation', True, 'en')], SENT
assert ir_site.load_state()['decks']['SATL']['last']['title'] == 'Q3 2026 Conference Call Presentation'
print('✅ 새 자료: 직전 자료와 비교 요약 · 언어별 1회 · 감시자 전원 발송')

SENT.clear(); CALLS.clear()
assert ir_site.check(send) == 0 and not SENT
print('✅ 보낸 자료는 다시 안 보냄')

# 요약 실패 → 재시도, 3번째에 링크만
PAGES['cur'] = """<div><div>November 12, 2026</div><h4>Conference Deck</h4>
<a href="/static-files/bbbbbbbb-1111-2222-3333-444444444444">Download</a></div>""" + PAGES['cur']
RESULT['v'] = None
assert ir_site.check(send) == 0 and ir_site.check(send) == 0 and not SENT
assert ir_site.check(send) == 2 and all(not s[2] for s in SENT)
print('✅ 요약 실패: 2번 재시도 후 제목·링크만 발송')

# 텍스트를 못 읽는 자료(PPTX·스캔본)는 기다리지 않고 바로 링크로
SENT.clear()
PAGES['cur'] = """<div><div>December 1, 2026</div><h4>Scanned Deck</h4>
<a href="/static-files/cccccccc-1111-2222-3333-444444444444">Download</a></div>""" + PAGES['cur']
TEXTS[BASE + '/static-files/cccccccc-1111-2222-3333-444444444444'] = ''
assert ir_site.check(send) == 2 and all(not s[2] for s in SENT)
print('✅ 본문 없는 자료는 재시도 없이 바로 링크')

# ── 발송 문구 ────────────────────────────────────────────────────────
import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
item = {'url': BASE + '/static-files/x', 'title': 'Q3 <Deck> & more', 'date': '2026-10-30'}
bot.send_ir_deck(1, 'SATL', item, {'headline': 'h', 'changes': ['A → B'], 'key_points': ['k'],
                                   'watch': ['w?']}, lang='ko')
m = OUT[-1]
assert '새 IR 발표자료' in m and '달라진 점' in m and 'A → B' in m and '&lt;Deck&gt; &amp;' in m and 'href=' in m
bot.send_ir_deck(1, 'SATL', item, None, lang='en')
assert 'new investor presentation' in OUT[-1] and 'title and link only' in OUT[-1]
print('✅ 발송 문구: 비교 요약 구성 · HTML 이스케이프 · 언어')
print('ALL PASS')
