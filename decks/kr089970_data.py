# -*- coding: utf-8 -*-
"""브이엠 (089970.KQ) — autogen_kr.py 자동 초안.

⚠️ 아래 항목은 **아직 사람이 채워야 한다**(자동으로는 지어낼 수 없는 것들):
     COMPANY['sector'] · BUSINESS · HISTORY['timeline'] · SEGMENTS · TAM ·
     LEADERSHIP['ceo']['bio'] · PEERS · CANSLIM_N
   check.py 가 '(확인 필요)'와 빈 값을 발행 차단 사유로 잡는다.

숫자는 전부 DART·Yahoo 원본에서 결정론으로 왔다(LLM 0콜):
   재무 = DART 재무제표 API · 최근실적 = None 영업(잠정)실적 공정공시
   가격·컨센서스 = Yahoo Finance
"""
AS_OF = '2026-11-13'          # 반영한 최신 공시일(표지 라벨)
BUILT_AT = '2026-11-13'       # 초안 생성일(신선도 게이트·차트 기준연도)

SRC = {
    'PR': 'DART 정기보고서 분기 재무(2026 3Q)',
    'DECK': 'DART 사업보고서',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {
    'ticker': '089970.KQ',
    'name': '브이엠',
    'legal_name': '브이엠(주)',
    'exchange': 'KOSDAQ',
    'sector': '반도체 식각장비 제조',
    'cik': '00544577',
}

LOCKED = []

# 표지 '- ' 짧은 줄 2~3개 — 이 회사에만 해당하는 구체 사실(2026-10-23 개정, 뻔한 줄은 deck_pages 가 거른다).
BUSINESS = [
    'SK하이닉스향 300mm Poly Etcher 주요 공급',
    '300mm 실리콘·금속막 식각장비 매출 비중 98.8%',
    '주력 제품: Leo WH, Leo NK I-C, Nardo-M',
]

HISTORY = {
    'founded': 2002,
    'listed': 2018,
    'listing_type': 'IPO',
    'listing_date': '',
    'founders': '',
    'timeline': [
    (
        '2002',
        '어댑티브플라즈마테크놀러지 주식회사 설립',
        False,
    ),
    (
        '2006',
        '에이피티씨 주식회사로 상호 변경 및 이천 본사 이전',
        False,
    ),
    (
        '2016',
        '300mm Poly Etcher Leo NK I SK하이닉스 양산판매 성공',
        True,
    ),
    (
        '2018',
        '코스닥시장 상장',
        True,
    ),
    (
        '2020',
        '300mm Metal Etcher Nardo-M 양산판매 성공',
        True,
    ),
    (
        '2024',
        '브이엠 주식회사로 상호 변경',
        False,
    ),
],
    'employees': [],
    'employee_src': '',
    'chart_annotations': [],
    'note': 'FY2022 매출 1,414억원에서 FY2023 260억원으로 감소하며 영업적자를 기록했으나, FY2025 매출 1,444억원 및 영업이익 247억원으로 실적 턴어라운드를 달성함. 주력 고객사인 SK하이닉스향 300mm Poly Etcher 및 Metal Etcher 공급 물량 회복이 실적 상승을 견인함. 차세대 Poly Etcher(Leo WS) 및 산화막 식각장비(Oxide Etcher) 개발을 진행하며 라인업 다변화를 추진 중임.',
}

PRICE_MOVES = []

LEADERSHIP = {
    'ceo': {'name': '최우형', 'role': '대표이사',
             'since': 2018, 'bio': '2018년 11월 최우형 대표이사 취임 후 2024년 3월 임종필 대표이사 공동 취임함. 최우형 대표는 2025년 9월 최대주주로 변경됨.'},
    # DART 임원·주요주주 소유상황보고에 이름이 오른 사람들 — 직위는 원문 그대로.
    'people': [
    (
        '이상우',
        '사장',
        '',
    ),
    (
        '장휘곤',
        '담당',
        '',
    ),
    (
        '정구현',
        '담당',
        '',
    ),
    (
        '김승록',
        '담당',
        '',
    ),
    (
        '서정우',
        '담당',
        '',
    ),
    (
        '이재윤',
        '담당',
        '',
    ),
],
    'note': '대표이사 공시 원문: 최우형, 임종필 (각자 대표이사)',
    'rsu_note': '',
}

SHARES = {'note': '', 'dilution': [], 'src': SRC['PR']}

SEGMENTS = {
    'by_line': [
    (
        '300mm Poly Etcher 외',
        None,
        100,
    ),
],
    'detail': [
    (
        '300mm Poly Etcher 외',
        '반도체 식각장비 및 Parts 제조·판매',
        None,
        0,
    ),
],
    'by_geo': [],
    'competitors': [],
    'note': '', 'src': SRC['DECK'],
}

RESULTS = {
    'period': '2026 3Q',
    'kpis': [
    (
        '매출',
        '849억원',
        '+133% YoY',
        'up',
    ),
    (
        '영업이익',
        '299억원',
        '+231% YoY',
        'up',
    ),
    (
        '순이익',
        '178억원',
        '+57% YoY',
        'up',
    ),
],
    'facts': [
    (
        '매출',
        '직전 분기 대비 +17.4%',
        '849억원',
    ),
    (
        '영업이익',
        '직전 분기 대비 +49.1%',
        '299억원',
    ),
    (
        '순이익',
        '직전 분기 대비 -0.8%',
        '178억원',
    ),
],
    # 한국은 어닝콜 전문이 무료 공개되지 않는다 — 경영진 발언 인용은 비워 둔다.
    'quotes': [],
    'src': SRC['PR'],
    'url': '',
}

# C·A는 canslim.py가 render 시점에 재무로 직접 계산 — N만 여기서 채운다.
CANSLIM_N = {}
CANSLIM_N_DETAIL = {}
CANSLIM_NOTE = ''

INCOME_NOTE = 'FY2022 매출 1,414억원, 영업이익 309억원에서 FY2023 매출 260억원, 영업손실 110억원으로 악화됨. FY2025 매출 1,444억원, 영업이익 247억원, 순이익 261억원을 기록하며 턴어라운드에 성공함.'
BALANCE_NOTE = '자본총계는 FY2022 1,179억원에서 FY2025 1,772억원으로 지속 확대됨. 현금성자산 역시 FY2022 481억원에서 FY2025 1,305억원으로 꾸준히 증가하여 안정적인 재무 구조를 유지 중임.'
CASHFLOW = {'note': '분기 영업현금흐름은 2025년 12월 -9억원에서 2026년 3월 145억원, 6월 357억원, 9월 362억원으로 개선됨. 영업실적 회복에 맞춰 현금 유출입 상태가 크게 정상화됨.', 'src': 'DART 재무제표 API'}

# estimates는 **항상 빈 배열**로 둔다. 시장조사기관 수치는 사업보고서에 금액으로
# 실리는 일이 드물고, 없는 걸 채우면 지어낸 값이 된다 — note에 원문 서술만 남긴다.
TAM = {'label': '', 'estimates': [],
       'note': '',
       'src': ''}

CHECKPOINTS = [
    (
        'FY2026',
        '연간 컨센서스 달성 여부',
        '매출 2,647억원 · EPS 2,394원 (애널리스트 3명)',
        'high',
    ),
    (
        '상시',
        '목표주가 괴리 해소 여부',
        '현재 41,700원 → 목표 118,000원 (+183%)',
        'mid',
    ),
]
CHECKPOINT_NOTE = ''
# 위 체크포인트는 실적 공시가 아니라 **애널리스트 컨센서스**에서 유도했다.
CHECKPOINT_SRC = 'Yahoo Finance 애널리스트 컨센서스'

PEERS = {'names': {}, 'ciks': {}}

SITE = 'https://www.vmsemi.com'

SUMMARY = 'FY2025 매출 1,444억원(전년 대비 +105.5%), 영업이익 247억원(OPM 17.1%), 순이익 261억원.\n영업이익은 FY2025에 흑자로 돌아섬.\n최근 분기 영업활동 현금흐름 362억원 · 보유 현금 2,231억원.'
