"""영상 요약 ↔ 종목 감시 연결 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_yt_watch_link.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir
import prefs

# ⚠️ 맨 앞에서 운영 파일 경로를 전부 임시로 돌린다. 2026-10-20 에 prefs 를 빠뜨려
#    bot.handle 이 운영 user_prefs.json 에 테스트 사용자(chat 9)를 써 넣었고, 그게 커밋됐다.
TMP = Path(tempfile.mkdtemp())
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'
prefs.PREFS_PATH = TMP / 'user_prefs.json'
ir.save_state({'watches': {'9': ['SATL']}, 'seen': {}, 'news': {}})
import engine

row = {'video_id': 'abcdefghijk', 'title': 't', 'analysis': {'one_liner': 'x', 'tickers': [
    {'name': 'Satellogic', 'ticker': 'SATL', 'view': '긍정'}, {'name': 'Tesla', 'ticker': 'TSLA'},
    {'name': '삼성전자', 'ticker': '005930'}, {'name': 'VIX', 'ticker': ''}]}}
m = engine.build_message(row, 'ch', chat=9)
assert '⭐🟢' in m, '감시 중인 종목 표시 없음'
tail = m.split('감시 추가:')[1]
assert '/watch_TSLA' in tail and 'SATL' not in tail and '005930' not in tail and 'VIX' not in tail
assert '감시 추가' not in engine.build_message(row, 'ch'), '받는 사람 모를 땐 감시 링크 없음'
print('✅ 영상 요약: 감시 중 종목 ⭐ · 미감시 미국 종목만 /watch_ 링크')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
bot.db.upsert_user = lambda *a, **k: None
bot.history.log = lambda *a, **k: None
ir.resolve_ticker = lambda t: (1, 'Tesla') if t == 'TSLA' else (None, None)
ir.latest_filing = lambda cik, **k: None
bot.handle({'chat': {'id': 9}, 'from': {}, 'text': '/watch_tsla'})
assert 'TSLA' in ir.watches_of(9), ir.load_state()
print('✅ /watch_TSLA 한 번 눌러 감시 등록')
assert not prefs.PREFS_PATH.is_relative_to(ROOT) and not ir.STATE_PATH.is_relative_to(ROOT)
print('ALL PASS')
