"""한국 종목 감시(/watch) 회귀 테스트 — 네트워크 없이 돈다.

    python tests/test_kr_watch.py

DART 공시 알림(★ 주요 공시 · 지분 보고 접기 · 첫 등록 기준선), 네이버 수급 파싱,
한국어 뉴스 잡음 필터·사건 묶기, /watch 삼성전자 등록 흐름을 고정한다.
"""
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import kr
import prefs
import ir

TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'user_prefs.json'
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'
kr.names = lambda refresh=False: {'005930': '삼성전자', '000660': 'SK하이닉스'}
kr.to_symbol = lambda code: ({'005930': '005930.KS', '000660': '000660.KS'}[code], '')

assert ir.is_kr('005930.KS') and ir.is_kr('247540.kq') and not ir.is_kr('TSLA') and not ir.is_kr('005930')
assert ir.display_name('005930.KS') == '삼성전자(005930)' and ir.display_name('tsla') == 'TSLA'
assert ir.watch_company('005930.KS') == ('005930', '삼성전자')
print('✅ 한국 심볼 판별·표시 이름')

# ── DART 공시 ─────────────────────────────────────────────────────────
DART = {'list': []}


class R:
    def __init__(self, j):
        self._j = j

    def json(self):
        return self._j

    def raise_for_status(self):
        pass


import types
sys.path.insert(0, str(ROOT / 'decks'))
import sources_kr
import dart_client
sources_kr.to_corp_code = lambda s: '00126380'
dart_client._key = lambda: 'k'
CALLS = []


def fake_get(url, params=None, **k):
    CALLS.append(url)
    if 'opendart' in url:
        return R({'status': '000' if DART['list'] else '013', 'list': DART['list']})
    if 'naver' in url:
        return R(NAVER)
    raise AssertionError(url)


ir.requests.get = fake_get


def row(no, nm, dt='20261020'):
    return {'rcept_no': no, 'report_nm': nm, 'rcept_dt': dt, 'flr_nm': '삼성전자'}


DART['list'] = [row('20261019000100', '임원ㆍ주요주주특정증권등소유상황보고서'),
                row('20261018000050', '분기보고서 (2026.06)')]
fs = ir.kr_filings('005930.KS')
assert fs[0]['rcept_no'] == '20261019000100' and fs[0]['fold'] and not fs[0]['major']
assert '20261019000100' in fs[0]['url']

SENT = []
ir.add_watch(7, '005930.KS')
st = ir.load_state()
assert st['seen']['005930.KS'] == '20261019000100', '등록 시점 최신 공시가 기준선'
assert ir.check_kr_filings(lambda c, t, new: (SENT.append((c, t, new)), True)[1]) == 0 and not SENT

DART['list'] = [row('20261020000300', '연결재무제표기준영업(잠정)실적(공정공시)'),
                row('20261020000200', '단일판매ㆍ공급계약체결'),
                row('20261020000150', '기업설명회(IR)개최(안내공시)'),
                row('20261020000120', '임원ㆍ주요주주특정증권등소유상황보고서'),
                row('20261020000110', '임원ㆍ주요주주특정증권등소유상황보고서')] + DART['list']
assert ir.check_kr_filings(lambda c, t, new: (SENT.append((c, t, new)), True)[1]) == 1
c, t, new = SENT[-1]
assert c == 7 and t == '005930.KS' and len(new) == 5, '기준선 이후 것만'
assert [f['major'] for f in new] == [True, True, False, False, False]
assert ir.load_state()['seen']['005930.KS'] == '20261020000300'
assert ir.check_kr_filings(lambda *a: (SENT.append(a), True)[1]) == 0, '같은 공시 두 번 안 보냄'
print('✅ DART: 첫 등록은 기준선만 · 새 공시만 · ★ 주요 공시 판별 · 중복 없음')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
bot.send_kr_filings(7, '005930.KS', new)
m = OUT[-1]
assert m.startswith('📑 <b>삼성전자(005930)</b> 새 공시 5건'), m
assert m.index('잠정') < m.index('기업설명회'), '★ 주요 공시가 위'
assert '지분 변동·발행 보고 2건' in m and m.count('임원ㆍ주요주주') == 0, m
print('✅ 공시 알림 메시지: ★ 위로 · 지분 보고 접기')

# ── 수급 ─────────────────────────────────────────────────────────────
NAVER = [{'bizdate': '20261020', 'foreignerPureBuyQuant': '+1,000,000', 'organPureBuyQuant': '-200,000', 'closePrice': '60,000'},
         {'bizdate': '20261019', 'foreignerPureBuyQuant': '+500,000', 'organPureBuyQuant': '+100,000', 'closePrice': '59,000'},
         {'bizdate': '20261016', 'foreignerPureBuyQuant': '+300,000', 'organPureBuyQuant': '-50,000', 'closePrice': '58,000'},
         {'bizdate': '20261015', 'foreignerPureBuyQuant': '-10,000', 'organPureBuyQuant': '-50,000', 'closePrice': '57,000'}]
fl = ir.kr_flow('005930.KS', since=datetime(2026, 10, 18, 10, tzinfo=timezone.utc))
assert fl['days'] == 2 and fl['foreign'] == 1_500_000 and fl['inst'] == -100_000, fl
assert fl['foreign_amt'] == 1_000_000 * 60000 + 500_000 * 59000 and fl['f_streak'] == 3 and fl['i_streak'] == -1
line = bot.flow_line(fl, 'ko')
assert line == '🏦 수급(2일): 외국인 +895억원 · 기관 -61억원 · 외국인 3일 연속 순매수', line
assert ir.kr_flow('005930.KS', since=datetime(2026, 10, 25, tzinfo=timezone.utc))['days'] == 1, '최소 1일'
assert bot.reaction_line({'flow': fl}, 'ko') == line, '주가 반응 없이 수급만 있어도 한 줄'
print('✅ 수급: 기간 합산·연속일·억원 표기')

# ── 한국어 뉴스 ──────────────────────────────────────────────────────
J = lambda t: ir._news_is_junk({'title': t, 'source': '연합뉴스'})
assert J('[포토] 삼성전자 신제품 공개') and J('외국인 순매수 상위 종목') and J('코스피, 외국인 매수에 2,700 마감')
assert J('[마감시황] 반도체 강세') and J('삼성전자 목표주가 상향…"HBM 기대"')
assert not J('[특징주] 삼성전자, HBM4 엔비디아 공급 소식에 5% 급등')
assert not J('삼성전자, 3분기 영업이익 12조…시장 예상 상회')
items = [{'title': '삼성전자 3분기 영업이익 12조원 잠정 집계', 'link': 'a', 'source': 'A', 'date': '2026-10-08'},
         {'title': '삼성전자, 3분기 영업이익 12조원…잠정 집계 결과', 'link': 'b', 'source': 'B', 'date': '2026-10-08'},
         {'title': '삼성전자 평택 4공장 증설 착수', 'link': 'c', 'source': 'C', 'date': '2026-10-08'}]
cl = ir._news_cluster(items, '삼성전자')
assert len(cl) == 2 and max(x['echo'] for x in cl) == 2, [(x['title'], x['echo']) for x in cl]
print('✅ 한국어 뉴스: 시황·순위·사진 기사 거름 · [특징주] 유지 · 같은 사건 묶음')

# ── /watch 흐름 ──────────────────────────────────────────────────────
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
H = lambda t: bot.handle({'chat': {'id': 9}, 'from': {'language_code': 'ko'}, 'text': t})
H('/watch 삼성전자')
assert '005930.KS' in ir.watches_of(9) and '감시 시작' in OUT[-1] and 'DART' in OUT[-1], OUT[-1]
H('/watchlist')
assert '삼성전자(005930)' in OUT[-1], OUT[-1]
H('/unwatch 005930')
assert '005930.KS' not in ir.watches_of(9) and '감시 해제' in OUT[-1]
H('/unwatch 삼성전자')
assert '감시 중인 한국 종목이 아니에요' in OUT[-1]
# 온보딩에서 한국 종목명 섞어 입력
prefs.set_onboarding(9, True)
bot.onboard_watch(9, 'TSLA 삼성전자')
assert '005930.KS' in ir.watches_of(9), ir.watches_of(9)
print('✅ /watch 삼성전자 · /watchlist 이름 표시 · /unwatch 코드 · 온보딩 혼합 입력')
# ── 한국인 베타 온보딩(2026-10-21): /start 후 한글 이름·6자리 코드만 보내도 감시 등록 ──
H2 = lambda t: bot.handle({'chat': {'id': 11}, 'from': {'language_code': 'ko'}, 'text': t})
H2('/start')
assert prefs.get(11).get('onboarding') and '한글 이름' in OUT[-1] and '/terms' in OUT[-1], OUT[-1]
H2('삼성전자 000660')
assert {'005930.KS', '000660.KS'} <= set(ir.watches_of(11)), ir.watches_of(11)
assert '감시 시작' in OUT[-1] and not prefs.get(11).get('onboarding'), OUT[-1]
H2('/terms')
assert '투자 권유가 아니며' in OUT[-1] and '이해상충' in OUT[-1] and '15분' in OUT[-1], OUT[-1]
H2('/help')
assert '/terms' in OUT[-1]
print('✅ 베타 온보딩: /start → 한글 이름·6자리 코드 등록 · /terms 면책 · /help 연결')
print('ALL PASS')
