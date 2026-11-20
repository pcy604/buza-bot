"""생성 시점 사실 검사 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_factcheck.py

2026-09-17 채점·정성 심사에서 **실제로 나갔던 오류만** 넣었다.
지어낸 사례로 테스트하면 실제로 나가는 오류는 계속 통과한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import factcheck as F

# ── 금액 이상치 ──────────────────────────────────────────────────────
BAD = ['엔비디아와 5년간 7,000억 달러 (약 1024조원) 규모의 HBM3E 공급',
       '연간 900조 원 규모 확정 이익']
OK = ['엔비디아와 5년간 2000억 달러 규모의 공급 계약',        # $200B — 크지만 가능한 선
      '장기 계약 확정 영업이익 연간 220조 원',                 # 의심스럽지만 임계 아래
      '과거 최고 영업이익 60조 원',
      '매출 $15.9M, 영업이익 $0.3M',
      '목표주가 360만 원']
for s in BAD:
    assert F.implausible_amount(s), f'이상치인데 통과: {s}'
for s in OK:
    assert not F.implausible_amount(s), f'정상인데 걸림: {s}'
print(f'✅ 금액: 이상치 {len(BAD)}건 탐지 · 정상 {len(OK)}건 통과')

# ── 티커 분류 ────────────────────────────────────────────────────────
assert F.classify_ticker('US') == 'bad', '국가명이 티커로 통과'
assert F.classify_ticker('CN') == 'bad'
assert F.classify_ticker('LP') == 'bad'
assert F.classify_ticker('KOSPI') == 'index', '지수를 오류로 셈'
assert F.classify_ticker('VIX') == 'index'
assert F.classify_ticker('USDJPY') == 'index'
assert F.classify_ticker('005930') == 'ok', '한국 6자리가 막힘'
assert F.classify_ticker('') == 'ok'
print('✅ 티커 분류: 국가명=오류 · 지수/통화=정상제외 · 한국코드=통과')

# ── sanitize: 코드만 비우고 이름은 남긴다 ────────────────────────────
a = {'summary': ['엔비디아와 5년간 7,000억 달러 규모 공급'],
     'tickers': [{'name': '미국', 'ticker': 'US', 'view': '긍정'},
                 {'name': 'KOSPI', 'ticker': 'KOSPI', 'view': '중립'},
                 {'name': '삼성전자', 'ticker': '005930', 'view': '긍정'}]}
F.sanitize(a)
assert a['tickers'][0]['ticker'] == '' and a['tickers'][0]['name'] == '미국', '이름까지 지워짐'
assert a['tickers'][1]['ticker'] == '', '지수에 종목 링크가 남음'
assert a['tickers'][2]['ticker'] == '005930', '멀쩡한 코드가 지워짐'
assert a['_flags']['ticker_cleared'], '수정 기록이 없음'
assert a['_flags']['amount_suspect'], '금액 플래그가 없음'
assert a['summary'][0].startswith('엔비디아'), '본문을 임의로 고쳤다'
print('✅ sanitize: 코드만 제거·이름 보존·본문 무수정·플래그 기록')

# ── 필드 이름을 안 가리는지(= /ir 카드도 검사되는지) ─────────────────
card = {'one_liner': '계약 규모 900조 원', 'news_digest': [{'headline': '정상', 'so_what': '정상'}]}
F.sanitize(card)
assert card.get('_flags', {}).get('amount_suspect'), '/ir 카드 필드가 검사에서 빠짐'
print('✅ 카드 구조(one_liner/news_digest)도 같은 검사를 받음')
