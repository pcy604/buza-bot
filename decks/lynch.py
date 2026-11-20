# -*- coding: utf-8 -*-
"""피터 린치의 6가지 주식 유형 분류 + PEG — 결정론(LLM 0콜).

출처: 피터 린치 『One Up on Wall Street』(1989) 7장 "Six Categories". 유형마다
'무엇을 봐야 하고 언제 이야기가 끝나는지'가 다르다는 게 핵심이다. 그래서 분류
자체보다 **유형별 점검 항목**이 리포트의 본체다.

분류 규칙(위에서부터 먼저 걸리는 것):
  1. 회생주(Turnaround)  — 최근 4분기 영업이익 합계 < 0, 또는 최근 4분기 안에 흑자 전환
  2. 자산주(Asset Play)  — 순현금(현금-부채)이 시가총액의 50% 이상, 또는 PBR < 1
  3. 경기순환주(Cyclical) — 경기민감 업종이면서 5년 영업이익의 부호가 바뀌었거나 변동이 큼
  4. 고성장주(Fast Grower) — 매출 3년 CAGR ≥ 20%
  5. 대형우량주(Stalwart) — 매출 3년 CAGR 8~20% 이고 시총 $10B 이상
  6. 저성장주(Slow Grower) — 그 밖(매출 3년 CAGR < 8%)
  · CAGR 8~20% 인데 시총이 작으면 린치 정의상 대형우량주가 아니다 → '중간 성장'
    표시를 붙여 고성장주 점검 항목으로 본다(그가 "작은 회사의 꾸준한 성장"을
    고성장주 쪽으로 다룬 것과 같다).
문턱값은 린치가 책에서 쓴 숫자(저성장 2~4% · 대형우량 10~12% · 고성장 20~25%)를
경계로 삼아 정했다. 우리 데이터로 고른 값이 아니다.

PEG = PER ÷ 이익성장률(%). 린치 기준: 1 이하 매력, 0.5 이하 매우 매력, 2 이상 부담.
성장률은 컨센서스 다음 해 EPS 성장 → 없으면 최근 3년 순이익 CAGR. 적자면 PEG 정의 불가.
"""

# 반도체(특히 메모리)는 린치가 책에서 경기순환주로 분류한 대표 업종이다 — 2026-10-20 삼성전자가
# 매출 CAGR 3% 로 '저성장주'로 잡혀 추가. 업종명만으론 부족해 아래 이익 변동 조건을 함께 본다.
CYCLICAL_SECTORS = ('energy', 'oil', 'gas', 'basic materials', 'materials', 'steel', 'chemical',
                    'mining', 'metal', 'auto', 'airline', 'semiconductor', 'memory', 'shipping', '반도체', '메모리',
                    '전자', '디스플레이', '조선', '석유화학', '배터리 소재',
                    'homebuild', 'construction', 'paper', 'forest', 'aluminum', 'copper',
                    '에너지', '소재', '철강', '화학', '자동차', '항공', '해운', '건설', '정유', '비철')

TYPES = {
    'turnaround': {
        'ko': '회생주', 'en': 'Turnaround',
        'what': '적자·위기에서 살아나는 회사. 살아나면 크게 오르고, 못 살아나면 0이 된다.',
        'check': ['버틸 현금이 있나 (현금 vs 연간 영업현금 소진)', '부채 만기와 이자 부담',
                  '무엇이 좋아지고 있나 (원가·제품·고객 중 구체적으로)'],
        'sell': '회생이 끝나 시장이 다시 정상 회사로 평가할 때 / 회생 계획이 깨질 때',
    },
    'asset': {
        'ko': '자산주', 'en': 'Asset Play',
        'what': '시장이 놓친 자산(현금·부동산·지분·특허)을 가진 회사.',
        'check': ['자산 가치가 시총 대비 얼마인가', '그 자산을 깎아 먹는 부채·현금 소진은 없나',
                  '가치가 드러날 계기(매각·분할·행동주의)가 있나'],
        'sell': '자산 가치가 주가에 반영됐을 때 / 경영진이 자산을 헐값에 쓰기 시작할 때',
    },
    'cyclical': {
        'ko': '경기순환주', 'en': 'Cyclical',
        'what': '경기와 업황에 따라 이익이 오르내리는 회사. 타이밍이 전부다.',
        'check': ['지금이 업황 사이클의 어디인가 (재고·가동률·가격)', '이익 정점에서 PER 이 가장 낮아 보이는 함정',
                  '불황을 버틸 재무 체력'],
        'sell': '재고가 쌓이고 가격이 꺾일 때 / 이익이 최고치인데 PER 이 낮아 싸 보일 때',
    },
    'fast': {
        'ko': '고성장주', 'en': 'Fast Grower',
        'what': '연 20% 이상 성장하는 작고 공격적인 회사. 린치가 가장 큰 수익을 낸 유형.',
        'check': ['성장할 여지가 아직 남았나 (새 지역·고객·제품)', '성장 속도가 유지되나 (분기 가속·둔화)',
                  'PER 이 성장률을 앞질렀나 (PEG)', '빚으로 성장하고 있지 않나'],
        'sell': '성장이 둔화되거나 확장이 멈출 때 / PEG 가 2를 넘어 기대가 과열될 때',
    },
    'stalwart': {
        'ko': '대형우량주', 'en': 'Stalwart',
        'what': '연 10% 안팎으로 꾸준히 크는 대기업. 큰 하락장의 방어용.',
        'check': ['PER 이 자기 과거 범위 대비 어디인가', '성장률이 10% 아래로 내려오지 않나',
                  '신사업·인수로 본업이 흔들리지 않나'],
        'sell': '30~50% 오르고 PER 이 과거 상단에 닿았을 때 → 다른 대형우량주로 교체',
    },
    'slow': {
        'ko': '저성장주', 'en': 'Slow Grower',
        'what': '경제 성장률 수준으로 크는 성숙 기업. 배당이 주된 이유.',
        'check': ['배당이 꾸준히 지급·증액되나', '배당성향이 감당 가능한가', '시장 점유율을 잃고 있지 않나'],
        'sell': '배당이 줄거나, 성장 없는 사업 다각화를 시작할 때',
    },
}


def _usd(v):
    a = abs(v)
    s = f'${a / 1e9:,.1f}B' if a >= 1e9 else f'${a / 1e6:,.1f}M'
    return ('-' if v < 0 else '') + s


def _cagr(first, last, years):
    if not first or not last or years <= 0 or first <= 0 or last <= 0:
        return None
    return ((last / first) ** (1 / years) - 1) * 100


def _series(d: dict, n: int):
    """{연도: 값} → 최근 n개 [(연도, 값)] 오름차순, None 제외."""
    pts = sorted((int(y), v) for y, v in (d or {}).items() if v is not None and str(y).isdigit())
    return pts[-n:]


def classify(annual: dict, q_opinc: list = None, market_cap=None, cash=None, debt=None,
             equity=None, sector: str = '') -> dict:
    """반환: {'type','ko','en','why','rev_cagr','flags':[...]}.

    annual: {'revenue': {연도: $}, 'opinc': {...}} · q_opinc: 최근 분기 영업이익 [$] 오래된→최신
    market_cap·cash·debt·equity: 달러(원 단위 그대로, SEC XBRL·Yahoo 값)
    """
    rev = _series((annual or {}).get('revenue'), 4)
    op = _series((annual or {}).get('opinc'), 5)
    rev_cagr = _cagr(rev[0][1], rev[-1][1], rev[-1][0] - rev[0][0]) if len(rev) >= 2 else None
    flags = []
    q = [v for v in (q_opinc or []) if v is not None]
    ttm = sum(q[-4:]) if len(q) >= 4 else None

    def out(t, why):
        return {'type': t, 'ko': TYPES[t]['ko'], 'en': TYPES[t]['en'], 'why': why,
                'rev_cagr': rev_cagr, 'flags': flags}

    # 1. 회생주
    if ttm is not None and ttm < 0:
        return out('turnaround', f'최근 4분기 영업이익 합계 {_usd(ttm)} (적자)')
    if len(q) >= 5 and any(v < 0 for v in q[-5:-1]) and q[-1] > 0:
        return out('turnaround', '최근 4분기 안에 영업이익 흑자 전환')
    # 2. 자산주
    if market_cap:
        if cash is not None and debt is not None and (cash - debt) >= 0.5 * market_cap:
            return out('asset', f'순현금 {_usd(cash - debt)} = 시총의 {(cash - debt) / market_cap * 100:.0f}%')
        if equity and equity > 0 and market_cap / equity < 1:
            return out('asset', f'PBR {market_cap / equity:.2f} (장부가 아래)')
    # 3. 경기순환주
    sec = (sector or '').lower()
    if any(k in sec for k in CYCLICAL_SECTORS) and len(op) >= 4:
        vals = [v for _, v in op]
        sign_flip = any(a * b < 0 for a, b in zip(vals, vals[1:]))
        mean = sum(vals) / len(vals)
        swing = (max(vals) - min(vals)) / abs(mean) if mean else 99
        if sign_flip or swing > 1.0:
            return out('cyclical', f'경기민감 업종({sector}) · 5년 영업이익 '
                                   + ('적자·흑자 반복' if sign_flip else f'변동폭 평균의 {swing * 100:.0f}%'))
    # 4~6. 성장 속도
    if rev_cagr is None:
        return out('slow', '매출 이력이 짧아 성장률을 못 잼 — 저성장으로 두고 확인 필요') | {'uncertain': True}
    if rev_cagr >= 20:
        return out('fast', f'매출 {rev[-1][0] - rev[0][0]}년 CAGR {rev_cagr:.0f}%')
    if rev_cagr >= 8:
        if market_cap and market_cap >= 10e9:
            return out('stalwart', f'매출 CAGR {rev_cagr:.0f}% · 시총 {_usd(market_cap)}')
        flags.append('중간 성장(소형) — 고성장주 점검 항목 적용')
        return out('fast', f'매출 CAGR {rev_cagr:.0f}% · 시총 {_usd(market_cap or 0)} (소형)')
    return out('slow', f'매출 CAGR {rev_cagr:.0f}%')


def peg(pe, growth_pct, dividend_yield_pct=0.0):
    """(peg, 판정, 설명). 린치: 1 이하 매력 · 0.5 이하 매우 매력 · 2 이상 부담.
    배당 포함 변형(성장률+배당수익률)/PER 도 같이 본다 — 저성장·대형우량주용."""
    if pe is None or pe <= 0:
        return None, '정의 불가', 'PER 이 없거나 적자'
    if growth_pct is None or growth_pct <= 0:
        return None, '정의 불가', '이익 성장률이 0 이하'
    v = pe / growth_pct
    tag = '매우 매력' if v <= 0.5 else '매력' if v <= 1 else '보통' if v <= 2 else '부담'
    note = f'PER {pe:.1f} ÷ 성장률 {growth_pct:.0f}%'
    if dividend_yield_pct:
        note += f' · 배당 포함 {(growth_pct + dividend_yield_pct) / pe:.2f}'
    return v, tag, note
