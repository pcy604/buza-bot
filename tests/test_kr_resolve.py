"""한국 종목 입력(코드·이름) 회귀 테스트 — 네트워크 없이 돈다.

    python tests/test_kr_resolve.py
"""
import sys
import tempfile
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
NAMES = {'005930': '삼성전자', '005935': '삼성전자우', '000660': 'SK하이닉스', '247540': '에코프로비엠',
         '086520': '에코프로', '035420': 'NAVER'}
kr.names = lambda refresh=False: NAMES
MARKET = {'005930': '005930.KS', '000660': '000660.KS', '247540': '247540.KQ', '086520': '086520.KQ'}
kr.to_symbol = lambda code: (MARKET[code], '') if code in MARKET else (None, '코넥스·기타 시장은 아직 지원하지 않음')

assert kr.is_kr_query('005930') and kr.is_kr_query('삼성전자') and kr.is_kr_query('247540.KQ')
assert not kr.is_kr_query('TSLA') and not kr.is_kr_query('BRK.B')
assert kr.search('005930') == [('005930', '삼성전자')]
assert kr.search('005930.KS') == [('005930', '삼성전자')]
assert kr.search('삼성전자') == [('005930', '삼성전자')], '정확 일치가 있으면 그것만'
assert kr.search('sk 하이닉스') == [('000660', 'SK하이닉스')], '띄어쓰기·대소문자 무시'
assert [c for c, _ in kr.search('에코프로')] == ['086520'], kr.search('에코프로')
assert [c for c, _ in kr.search('에코')] == ['086520', '247540']
print('✅ 코드·심볼·이름(정확·앞부분·포함, 띄어쓰기 무시) 검색')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
DECK = []
bot.send_deck = lambda chat, tk: (DECK.append(tk), True)[1]
import os; os.environ['OWNER_CHAT'] = '3'   # 한국 리포트는 소유자만(2026-10-23) — 이 테스트는 소유자로 본다
H = lambda t: bot.handle({'chat': {'id': 3}, 'from': {'language_code': 'ko'}, 'text': t})
H('/report 삼성전자')
assert DECK[-1] == '005930.KS' and '삼성전자' in OUT[-1], (DECK, OUT[-1])
H('/report 247540')
assert DECK[-1] == '247540.KQ'
H('/report sk 하이닉스')
assert DECK[-1] == '000660.KS'
n = len(DECK)
H('/report 에코')
assert len(DECK) == n and '/report_086520' in OUT[-1] and '/report_247540' in OUT[-1], OUT[-1]
H('/report_247540')
assert DECK[-1] == '247540.KQ', '목록에서 눌러 고르기'
H('/report NAVER')
assert DECK[-1] != '035420' and 'TSLA' not in OUT[-1]
H('/report 존재안함')
assert '못 찾았어요' in OUT[-1]
H('/dd 삼성전자')
assert '/report 삼성전자' in OUT[-1]
H('/ir 삼성전자')
assert '미국 종목 전용' in OUT[-1]
print('✅ /report 코드·이름 → 한국 리포트 · 여러 개면 골라 누르기 · /dd 는 /report 안내 · /ir 은 미국 전용 안내')
print('ALL PASS')
