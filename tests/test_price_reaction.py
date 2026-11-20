"""감시 뉴스의 주가·거래량 반응 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_price_reaction.py

오닐: 뉴스는 가격·거래량으로 확인될 때 의미가 있다. 이선엽: 반등의 질은 장 마감까지
유지되는지로 본다. 잡음뿐인 날이라도 거래량 실린 큰 움직임은 알린다.
"""
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir
import prefs

TMP = Path(tempfile.mkdtemp())
ir.STATE_PATH = TMP / 'ir_state.json'
ir.NEWS_LOG_PATH = TMP / 'news_log.json'
prefs.PREFS_PATH = TMP / 'user_prefs.json'

D0 = datetime(2026, 7, 1, 20, tzinfo=timezone.utc)
rows = [((D0 + timedelta(days=k)).timestamp(), 10, 10.2, 9.8, 10, 1000) for k in range(80)]
# 마지막 날: 갭 +8% 로 시작해 +15% 마감, 고가 근처 마감, 거래량 4배
rows.append(((D0 + timedelta(days=80)).timestamp(), 10.8, 11.6, 10.7, 11.5, 4000))
ir._daily_rows = lambda t: rows
r = ir.price_reaction('X', D0 + timedelta(days=79, hours=12))
assert r and round(r['chg']) == 15 and r['notable'], r
b = r['big']
assert round(b['ret']) == 15 and round(b['vol_x']) == 4 and round(b['gap']) == 8 and b['held'], b
print('✅ 지난 요약 이후 등락 · 가장 큰 날 · 거래량 배수 · 갭 · 마감까지 유지')

rows2 = rows[:-1] + [((D0 + timedelta(days=80)).timestamp(), 10.8, 11.6, 9.9, 10.1, 1200)]
ir._daily_rows = lambda t: rows2
r2 = ir.price_reaction('X', D0 + timedelta(days=79, hours=12))
assert not r2['notable'] and not r2['big']['held'] is None
print('✅ 작은 움직임은 notable 아님')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
ev = [{'title': 'Some article', 'link': 'https://x/1', 'source': 'S', 'date': '2026-09-19'}]
bot.send_ir_news(1, 'X', ev, [{'headline': 'h'}], lang='ko', reaction=r)
m = OUT[-1]
assert '📊 주가: 지난 요약 이후 +15.0%' in m and '거래량 평소 4.0배' in m and '갭 +8.0%' in m and '마감까지 유지' in m, m
bot.send_ir_news(1, 'X', ev, [], lang='en', reaction=r)
assert 'moved sharply on heavy volume' in OUT[-1] and 'volume 4.0×' in OUT[-1]
print('✅ 메시지 한 줄 표기(ko/en) · 잡음뿐인 날 큰 움직임 안내')

# deliver_news: 잡음뿐 + 큰 움직임 → 발송, 잡음뿐 + 작은 움직임 → 미발송
prefs.set_hour(1, 8); prefs.set_tz(1, 'UTC'); prefs.set_lang(1, 'ko')
ir.resolve_ticker = lambda t: (1, 'Xco')
ir.summarize_news = lambda *a, **k: []
SENT = []
send = lambda c, t, items, digest, lang='ko', reaction=None: (SENT.append(reaction), True)[1]
mark = (D0 + timedelta(days=79, hours=12))
now = D0 + timedelta(days=80, hours=13)
ir._RSS_CACHE.clear()
ir._RSS_CACHE['Xco'] = [{'title': 'Xco option chain', 'link': 'https://n/1', 'source': 'S',
                         'pubDate': (now - timedelta(hours=3)).strftime('%a, %d %b %Y %H:%M:%S GMT')},
                        {'title': 'Xco analyst reiterates rating', 'link': 'https://n/2', 'source': 'S',
                         'pubDate': (now - timedelta(hours=2)).strftime('%a, %d %b %Y %H:%M:%S GMT')}]
for big_rows, expect in ((rows, 1), (rows2, 0)):
    ir._daily_rows = lambda t, br=big_rows: br
    ir.save_state({'watches': {'1': ['X']}, 'seen': {}, 'news': {'1': {'X': {'mark': mark.isoformat()}}}})
    SENT.clear()
    n = ir.deliver_news(send, now=now)
    assert n == expect, (n, expect)
print('✅ 잡음뿐인 날: 거래량 실린 큰 움직임만 발송')
print('ALL PASS')
