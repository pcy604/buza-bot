"""봇 ↔ 대시보드 연결 회귀 테스트 — 네트워크·LLM 없이 돈다 (2026-10-20).

    python tests/test_dashboard_link.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir
import prefs

TMP = Path(tempfile.mkdtemp())                   # 운영 상태 파일을 건드리지 않는다
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'
prefs.PREFS_PATH = TMP / 'user_prefs.json'
ir.save_state({'watches': {}, 'seen': {}, 'news': {}})

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
import config
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
ir.resolve_ticker = lambda t: (1, 'Tesla') if t in ('TSLA', 'SATL') else (None, None)
ir.latest_filing = lambda cik, **k: None

config.DASHBOARD_URL = 'https://dash.example'
assert bot.dash_link('tsla') == '<a href="https://dash.example/?sym=TSLA">📊 대시보드에서 보기</a>', bot.dash_link('tsla')
assert '?watch=SATL,TSLA' in bot.dash_link(watch=['SATL', 'TSLA'])
assert bot.dash_link('<x>') == bot.dash_link('X'), '티커에 HTML 이 섞이지 않는다'
config.DASHBOARD_URL = ''
assert bot.dash_link('TSLA') == '', 'URL 이 비면 링크 없음'
config.DASHBOARD_URL = 'https://dash.example'
print('✅ 딥링크: ?sym= · ?watch= · 비우면 생략')

# 대시보드의 '봇에서 감시' → t.me/<봇>?start=watch_TSLA → '/start watch_TSLA'
bot.handle({'chat': {'id': 7}, 'from': {}, 'text': '/start watch_TSLA'})
assert 'TSLA' in ir.watches_of(7), ir.load_state()
print('✅ /start watch_TSLA 로 감시 등록')

OUT.clear()
bot.handle({'chat': {'id': 7}, 'from': {}, 'text': '/watchlist'})
assert OUT and '?watch=TSLA' in OUT[-1], OUT
print('✅ /watchlist 에 대시보드 감시 목록 링크')

OUT.clear()
bot.send_ir_news(7, 'TSLA', [{'link': 'https://n', 'title': 't', 'source': 's', 'date': 'd'}],
                 digest=[{'headline': 'h', 'so_what': 'w'}])
assert '?sym=TSLA' in OUT[-1] and '/good_TSLA' in OUT[-1], OUT[-1]
print('✅ 감시 뉴스 요약 꼬리에 대시보드 링크')
assert not prefs.PREFS_PATH.is_relative_to(ROOT) and not ir.STATE_PATH.is_relative_to(ROOT)
print('ALL PASS')
