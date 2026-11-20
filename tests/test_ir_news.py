"""/ir 뉴스 정제 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_ir_news.py

2026-09-17 구글 뉴스 RSS 실측에서 **실제로 관측된 항목만** 넣었다.
지어낸 사례로 테스트하면 실제로 들어오는 쓰레기는 계속 통과한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir

# ── 잡음 판정 ────────────────────────────────────────────────────────
# 버려야 하는 것 — 전부 AXTI/SATL 검색 결과에 실제로 섞여 있던 것들.
JUNK = [
    # 회사가 아니라 로빈후드 토큰화 주식(RAXTI) 시세 페이지
    {'source': 'MEXC', 'title': 'AXT Inc rStock Price Today: Live RAXTI to USD Price Chart & Market Data'},
    {'source': 'Binance', 'title': 'AXT Inc (Derivatives) Price Today | Live AXTI Price, Chart & Market Data'},
    {'source': 'Bybit', 'title': 'Convert 1 AXTI (AXT Inc • Robinhood Token) to EUR (EUR)'},
    {'source': 'CoinGecko', 'title': 'AXT Inc rStock Price: RAXTI/USD Live Price Chart, Market Cap & News Today'},
    {'source': 'es.beincrypto.com', 'title': 'AXT Inc rStock (RAXTI) información de precios'},
    {'source': 'Moomoo', 'title': '$AXT Inc (AXTI.US)$'},
    # 알고리즘 밸류에이션 팜
    {'source': 'GuruFocus', 'title': 'AXT Inc (AXTI) Stock Down 6.1% but Still Overvalued -- GF Score: 58/100'},
    {'source': 'GuruFocus', 'title': 'SATL Looks 17.3% Undervalued on GF Value™ Amid Unprofitability'},
    # 파생상품 기사 — 이 회사가 아니라 2배 인버스 ETF 얘기
    {'source': '24/7 Wall St.', 'title': 'Tradr’s New AXTQ Pays Double When AXT Falls. The Catch Is the Word Daily'},
    # 같은 기사의 나라별 재게시
    {'source': 'Investing.com Nigeria', 'title': 'Satellogic to launch three satellites in October 2026'},
    {'source': 'Investing.com España', 'title': 'El satélite de Satellogic completa operaciones de proximidad'},
    {'source': 'MarketScreener España', 'title': 'Satellogic lanzará en octubre dos satélites'},
    # 2026-10-11 KEEP 에서 옮겨 옴. 아래 '남겨야 하는 것'의 원칙("논조로 거르면
    # 왜곡이다")은 그대로 유지한다 — 바뀐 건 판단 기준이다.
    #   · 논조가 아니라 **정보량**으로 자른다. 제목만 LLM 에 넣으므로
    #     "왜 떨어졌나"는 이유를 약속만 하고 아무것도 안 알려준다.
    #     등락폭 자체는 사용자가 이미 차트로 본다.
    #   · 상승·하락 동사를 **대칭으로** 담았다(gain·surge·soar / fall·plunge·slump).
    #     악재만 거르는 게 아니므로 왜곡이 아니다.
    #   · 실측 근거: 5종목 174건 중 이 부류가 상위 8건 자리를 잠식해, AXTI 는
    #     7건 중 5건이 사건 아닌 글이었다.
    {'source': 'TIKR.com', 'title': 'Here’s Why AXT Stock Fell 12% Yesterday.'},
]
# 남겨야 하는 것 — 특히 **악재**. 논조로 거르기 시작하면 정제가 아니라 왜곡이다.
KEEP = [
    {'source': 'GlobeNewswire', 'title': 'Satellogic Supports HEO RPO Mission Operations'},
    {'source': 'Investing.com', 'title': 'Satellogic to launch three satellites in October 2026'},
    {'source': 'Seeking Alpha', 'title': 'AXT: Our Most Obvious Sell In Small-Cap Semis (NASDAQ:AXTI)'},
    # 등락이 제목에 있어도 **원인이 같이 적혀 있으면** 사건이다. 이게 위
    # 'Here's Why ... Fell 12%' 와 갈리는 지점이다 — 거기엔 원인이 없다.
    {'source': 'scanx.trade', 'title': 'Corcept Therapeutics shares surge 22% after Q2 beat, guidance raise'},
    {'source': 'marketscreener.com', 'title': 'Satellogic Expands Slingshot III Work with IDT'},
]
for it in JUNK:
    assert ir._news_is_junk(it), f'잡음인데 통과함: {it["source"]} / {it["title"]}'
for it in KEEP:
    assert not ir._news_is_junk(it), f'정상인데 버려짐: {it["source"]} / {it["title"]}'
print(f'✅ 잡음 {len(JUNK)}건 차단 · 정상 {len(KEEP)}건 통과 (악재 포함)')

# ── 사건 묶기 ────────────────────────────────────────────────────────
ITEMS = [
    {'title': 'Satellogic to launch three satellites in October 2026',
     'source': 'Investing.com', 'date': '2026-09-14', 'link': 'l1'},
    {'title': 'Satellogic to Launch Two ISL-Equipped Satellites and Sovereign Mark V in October',
     'source': 'The Manila Times', 'date': '2026-09-14', 'link': 'l2'},
    {'title': 'Satellogic Inc. Expands Slingshot III Work with IDT and U.S. Office of Naval Research',
     'source': 'marketscreener.com', 'date': '2026-09-14', 'link': 'l3'},
    {'title': 'Satellogic Expands Slingshot III Work with IDT and U.S. Office of Naval Research',
     'source': 'GlobeNewswire', 'date': '2026-09-14', 'link': 'l4'},
    {'title': 'NOK, LUNR, SATL Stocks Hit 52-Week Highs Last Week: What Drove Them Higher?',
     'source': 'Stocktwits', 'date': '2026-09-12', 'link': 'l5'},
]
ev = ir._news_cluster(ITEMS, 'Satellogic Inc.')
by_link = {e['link']: e for e in ev}

# l3/l4 는 사실상 같은 제목 → 한 사건. 대표는 1차 소스(GlobeNewswire)여야 한다.
slingshot = [e for e in ev if 'Slingshot' in e['title']]
assert len(slingshot) == 1, f'Slingshot 사건이 {len(slingshot)}개로 쪼개짐'
assert slingshot[0]['source'] == 'GlobeNewswire', f"대표 오선택: {slingshot[0]['source']}"
assert slingshot[0]['echo'] == 2
assert set(slingshot[0]['links']) == {'l3', 'l4'}, '묶인 링크가 다 안 담겼다'

# 날짜가 다른 기사는 절대 합치지 않는다(오합침 방지 규칙).
assert 'l5' in by_link, '다른 날짜 기사가 흡수됨'

# ⚠️ 알려진 한계: 매체가 제목을 평문으로 다시 쓰면 공유 토큰이 0이라 못 묶는다.
#    ('Satellogic Supports HEO RPO Mission Operations' 와
#     'A satellite got within 27 kilometers of a spent rocket in orbit')
#    토큰 유사도로는 원리상 불가능하고, 의미 병합은 LLM(news_digest)이 맡는다.
#    이 테스트는 그 한계를 **고정**해둔다 — 없어지면 설계가 바뀐 것이다.
hard = ir._news_cluster([
    {'title': 'Satellogic Supports HEO RPO Mission Operations', 'source': 'GlobeNewswire',
     'date': '2026-09-14', 'link': 'h1'},
    {'title': 'A satellite got within 27 kilometers of a spent rocket in orbit',
     'source': 'Stock Titan', 'date': '2026-09-14', 'link': 'h2'},
], 'Satellogic Inc.')
assert len(hard) == 2, '토큰 유사도가 의미까지 묶었다면 임계값을 다시 봐야 한다'

print(f'✅ 사건 묶기: {len(ITEMS)}건 → {len(ev)}사건, 1차 소스 대표 선택·링크 보존·날짜 분리 통과')
print('✅ 알려진 한계(평문 재작성은 LLM 담당) 고정됨')

# ── 2026-10-03: 기사가 아닌 것(시세·데이터 페이지)도 막는다 ───────────
# 운영 28회 중 13회가 "요약할 게 없음"으로 끝났고 사유가 전부 이 부류였다.
# LLM 호출 13회를 쓰레기 거르는 데 쓴 셈이라 무료 단계로 옮겼다.
NOT_NEWS = [
    {'source': 'Yahoo', 'title': 'Cadena de opciones de Satellogic Inc. (SATL)'},
    {'source': 'TradingView', 'title': 'Promedio de acciones básicas en circulación de Satellogic Inc.'},
    {'source': 'Yahoo! Finance', 'title': 'Satellogic Inc. (SATLW) Stock Price, News, Quote & History'},
    {'source': 'Intellectia AI', 'title': 'SATL Should I Buy'},
    {'source': 'MarketBeat', 'title': 'Satellogic (NASDAQ:SATL) Shares Down 5.7% - Should You Sell?'},
    {'source': 'TradingView', 'title': 'K7O0 Forecast — Price Target — Prediction for 2027'},
]
# 주가가 움직인 **이유**가 있는 기사는 남겨야 한다 — 'Shares Rise' 만으로 막으면 진짜 뉴스가 사라진다.
STILL_NEWS = [
    {'source': 'marketscreener.com', 'title': 'Satellogic Shares Rise After Launching Merlin Satellite Into Low-Earth Orbit'},
    {'source': 'Stock Titan', 'title': 'Stock awards vest for Satellogic (SATL) CEO, increasing his direct holdings'},
    {'source': 'Seeking Alpha', 'title': 'Satellogic: A Mispriced Cost Moat & Sovereign Demand Play (NASDAQ:SATL)'},
]
for it in NOT_NEWS:
    assert ir._news_is_junk(it), f'기사가 아닌데 통과: {it["title"]}'
for it in STILL_NEWS:
    assert not ir._news_is_junk(it), f'진짜 뉴스인데 차단: {it["title"]}'
print(f'✅ 시세·데이터 페이지 {len(NOT_NEWS)}건 차단 · 사건 있는 기사 {len(STILL_NEWS)}건 통과')
