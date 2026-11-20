# -*- coding: utf-8 -*-
"""SNDK 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-02 (반영 공시 2026-10-30)
출처 코드
  ANNUAL = 10-K(2026-08-17 제출)
  EARN   = 10-Q 공시(2026-10-30)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-10-30'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-02'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-10-30)',
    'DECK': '10-Q 공시(2026-10-30)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'SNDK', 'name': 'Sandisk Corp', 'exchange': 'Nasdaq',
           'sector': 'NAND플래시·스토리지·반도체', 'cik': 2023554}

# 이 필드는 autogen.py를 다시 돌려도 덮어쓰지 않는다 — 사람이 확인·보정한 값을 지키는
# 장치. 검수하다가 "이 값은 이게 맞다"고 확정한 필드의 경로를 여기 추가하면 된다.
# (경로 형식: 'HISTORY.founded', 'LEADERSHIP.ceo.bio', 'TAM.estimates' …)
# 여기 없어도, 새로 뽑은 값이 비었는데 기존 값이 있으면 기존 값이 자동으로 유지된다.
LOCKED = []

# 이번 재생성에서 **새로 뽑지 못해 옛 값을 그대로 쓴** 필드와, 그 값이 만들어진 날.
# 비어 있으면 이 파일의 모든 값이 이번 생성분이라는 뜻이다.
# 예전에는 이 정보가 콘솔에만 찍혀서, 파일은 BUILT_AT=오늘 인데 내용의 절반이
# 한 달 전 값인 상태를 아무도 알 수 없었다(러너 실행분은 로그도 안 본다).
# 완전히 새로 뽑고 싶으면: python decks/autogen.py TICKER --fresh
CARRIED_OVER = {'HISTORY.founded': '2026-10-12', 'HISTORY.founders': '2026-10-12', 'LEADERSHIP.ceo.bio': '2026-10-12', 'LEADERSHIP.ceo.since': '2026-10-12', 'LEADERSHIP.rsu_note': '2026-10-12', 'SHARES.note': '2026-10-12', 'TAM.estimates': '2026-10-12', 'TAM.note': '2026-10-12'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'NAND 플래시 기반 SSD 및 스토리지 솔루션 제조',
    'FY2026 매출 $20.2B 달성(Datacenter·Edge·Consumer)',
    'Kioxia 합작법인(Flash Ventures) 통해 웨이퍼 조달'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 1988,
    'listed': 2025,
    'listing_type': '스핀오프',
    'listing_date': '',
    'founders': '엘리 하라리·산제이 메로트라·잭 위안(1988년 원조 SanDisk 창업)',
    'timeline': [
        ('2023.10', 'WDC 이사회, Sandisk 분리 및 독립 상장 추진 계획 승인'),
        ('2025.01', '중국 시장 판매 확대를 위해 Unis Venture 지분 48% 양수 계약 체결'),
        ('2025.02', 'WDC로부터 스핀오프 완료 및 Nasdaq(SNDK) 상장, $2.0B Term Loan B 실행', True),
        ('2026.01', 'Kioxia와 Flash Ventures 합작 기간 2034년 12월 31일까지 연장 합의', True),
        ('2026.03', 'Nanya Technology 지분 투자 및 Term Loan B $2.0B 잔액 조기 전액 상환'),
        ('2026.04', '이사회의 $6.0B 자사주 매입 프로그램 승인(8월 $14.0B 추가 승인)', True)
    ],
    'employees': [('FY2026 10-K (2026년 7월)', 11100)],
    'employee_src': 'FY2026 10-K (2026년 7월) 공식 집계',
    'chart_annotations': [
        (2025, 7, '1 +1243% 변동'),
        (2026, 6, '2 -49% 변동')
    ],
    'note': '2025년 2월 21일 WDC(Western Digital)로부터 스핀오프되어 독립 상장법인으로 전환됨. FY2026 연간 매출액 $20.2B(전년 대비 175% 증가) 및 영업이익 $12.4B를 달성하며 AI 데이터센터 및 에지 시장 수요 급증 수혜를 입음. Kioxia와의 합작법인(Flash Ventures) 계약을 2034년 12월까지 연장하여 안정적인 NAND 웨이퍼 공급 기반을 확보함. $2.0B 규모의 Term Loan B 차입금을 조기 전액 상환하고 총 $20.0B 규모의 자사주 매입 프로그램을 승인하여 재무 구조 안정화 및 주주환원 단계 진입함.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2025.07→2026.01', "pct": '+1243%', "range": '$42.92→$576.25', "reason": 'AI 및 클라우드 수요 폭증에 따른 2분기 어닝 서프라이즈와 폭발적 가이던스가 주가를 견인함.'},
    {"no": 2, "dir": 'down', "period": '2026.06→2026.10', "pct": '-49%', "range": '$2273.73→$1150.89', "reason": '단일 계기 미확인 — AI 수요 및 호실적 보도 속 일부 차익 실현 나타남.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'KXIAY': 'Kioxia Holdings Corporation/ADR', 'MU': 'MICRON TECHNOLOGY INC', 'SKHY': 'SK hynix Inc.'},
    'ciks': {'KXIAY': 2053383, 'MU': 723125, 'SKHY': 2120882},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'David Goeckeler', 'role': 'CEO', 'since': 2025,
            'bio': 'David V. Goeckeler는 2025년 2월부터 SanDisk의 CEO를 맡고 있습니다. 그의 이전 경력에 대한 자세한 내용은 "기업 지배 구조-이사 선출" 섹션에 나와 있습니다.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Bernard Shek', 'CLO · Secty', ''),
        ('Ilkbahar Alper', 'EVP · CTO', ''),
        ('Luis Felipe Visoso', 'EVP · Chief Financial Office', ''),
        ('Michael Pokorny', 'VP · CAO', '')
    ],
    'note': 'CISO(25년 이상 경력) 및 CIO 주도의 정보보안 체계와 이사회 감사위원회의 분기별 사이버보안 리스크 감독 거버넌스를 운용함.',
    'rsu_note': 'WDC PSU 상이 분리 과정에서 성과 기반 베스팅 조건을 더 이상 적용받지 않는 시간 기반 SanDisk RSU로 전환되었습니다. 이러한 상은 2025년 8월 20일과 2026년 8월 25일에 베스팅될 예정입니다.',
}

SHARES = {
    'note': '희석 주식수는 2026년 기준 기본 주식수 147M주 대비 155M주로 8M주 희석 발생.\n이는 주로 종업원 주식보상제도(Restricted Stock Unit awards)에 따른 미행사 주식으로 인한 것임.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Datacenter', 2801.9, 25.4), ('Edge', 6629.6, 60.1), ('Consumer', 1599.5, 14.5)],
    'detail': [
        ('Datacenter',
         '퍼블릭·프라이빗 클라우드 및 데이터센터용 고성능 엔터프라이즈 SSD 및 소프트웨어 솔루션을 공급함.', 2801.9, 0),
        ('Edge',
         'PC, 모바일, 게이밍, 전장, 물리적 AI 및 산업용 기기 OEM·채널 고객용 플래시 스토리지를 공급함.', 6629.6, 0),
        ('Consumer',
         '소비자용 리테일 SSD, 이동식 메모리카드, USB 플래시 드라이브 등 브랜드 제품을 공급함.', 1599.5, 0)
    ],
    'by_geo': [],
    'competitors': ['Kioxia', 'Micron Technology, Inc.', 'Samsung Electronics Co., Ltd.', 'SK Hynix, Inc.', 'Yangtze Memory Technologies Co., Ltd.'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q1 2027',
    'kpis': [
        ('매출', '$11.03B', '+378% YoY', 'up'),
        ('영업이익', '$8.78B', '+4889% YoY', 'up'),
        ('순이익', '$8.10B', '+7133% YoY', 'up'),
        ('영업현금흐름', '$6.36B', '+1204% YoY', 'up'),
        ('현금', '$5.14B', '+256% YoY', 'up')
    ],
    'facts': [
        ('총매출액', 'AI 인프라 수요 폭증에 따른 분기 매출 급증', '$11.0B'),
        ('영업이익', '단가 상승 및 출하량 증가로 영업이익 급증', '$8.8B'),
        ('순이익', '매출총이익률 개선 및 지분평가익 반영', '$8.1B'),
        ('영업현금', '수익성 개선에 따른 분기 영업활동 현금흐름', '$6.4B'),
        ('수주잔고', '장기계약 NBM 기반 잔여 이행 의무 총액', '$88.9B'),
        ('자사주매입', '잉여현금 환원 정책에 따른 분기 자사주 매입', '$5.0B'),
        ('DC매출', 'AI 데이터센터용 플래시 제품 분기 매출', '$4.8B'),
        ('현금성자산', '분기말 보유 현금 및 현금성자산 잔액', '$5.1B')
    ],
    'quotes': [
        ('경영진', 'AI 인프라의 급격한 성장이 고성능 스토리지 수요를 견인하고 있으며, 이러한 AI 주도 수요는 2027년 이후까지 지속될 것으로 예상합니다.', 'We continued to observe that the rapid growth of AI infrastructure is driving demand for high-performance storage products... We expect AI-driven demand to persist through calendar year 2027 and beyond.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 5, 'growth_years': 3, 'competitors': 5, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 3곳 중 시총 3위($163.8B) → 5점', '20%+ 성장 가능 연수': '3년 (2027 +144% · 2028 +22% · 과거 2024~2026 CAGR +74%) → 6점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 5곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 신시장 CAGR.'

INCOME_NOTE = '2023년 매출 $6.1B에서 2025년 $7.4B로 완만하게 성장한 후 2026년 $20.2B로 급증함. 순이익은 2023년 -$2.1B 및 2025년 -$1.6B 등 적자를 지속하다가 2026년 $11.4B로 대폭 흑자 전환함.'
BALANCE_NOTE = '현금 자산은 2024년 $328.0M에서 2025년 $1.5B로 확충된 후 2026년 $4.8B 수준까지 유동성 급증함. 턴어라운드 실적에 기반한 유동성 확보로 재무 안정성 대폭 개선됨.'
CASHFLOW = {
    'note': '영업현금흐름은 2023년 -$713.0M, 2024년 -$309.0M 유출에서 2025년 $84.0M로 양수 전환 성공함. 2026년 영업현금흐름이 $11.7B로 폭발적으로 늘어나 유기적 현금 창출력 강화됨.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'NAND flash storage 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('Barchart.com', 72.6, 2030.0)
    ],
    'note': '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2026년 11월', '8대 1 주식분할 단행 및 신주 상장', '유통 주식수 확대로 개인 투자자 접근성 개선 및 단기 유동성 변화 확인', 'mid'),
    ('2027년 Q2', '가이던스 매출 $12.2B~$12.6B 및 Non-GAAP EPS $55~$57 달성', '초과 수요 국면에서 분기 실적 연속 성장 및 마진 방어력 검증', 'high'),
    ('2027년', 'AI 추론용 신규 아키텍처 HBF 첫 샘플 공급', 'DRAM 대체 성격의 차세대 플래시 메모리 시장 선점 여부 확인', 'high'),
    ('2027년 Q3', '비수기 진입에 따른 분기 매출 감소폭 방어', '과거 QoQ -19%를 기록했던 계절적 비수기를 NBM 장기계약 구조로 상쇄하는지 확인', 'mid'),
    ('2026년 10월', '분기 실적발표', 'EPS 컨센서스 $57.18 (범위 $56.00~$60.12) 대비 실제치 확인', 'high'),
    ('FY2027', '연간 컨센서스 달성 여부', '매출 $49.4B · EPS $226.85 (애널리스트 18명)', 'high')
]
CHECKPOINT_NOTE = '$88.9B 규모 NBM 장기 수주잔고의 차질 없는 매출 전환과 신규 HBF 아키텍처 샘플 공급을 통한 시장 선점이 핵심 투자논리의 전부를 구성함.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': 'NAND 플래시 스토리지', 'chain': ['칩 설계·IP', '전공정 웨이퍼 제조', '후공정 패키징·테스트', 'SSD·스토리지 제조', '데이터센터·고객사 공급'], 'position': 3, 'spans': [0, 1, 2, 3], 'position_note': 'Kioxia 합작법인을 통한 웨이퍼 공동 생산부터 칩 설계, 후공정, SSD 시스템 개발까지 전 과정을 수직계열화함.', 'cycle': 'AI 인프라 구축 확대로 고성능 NAND 스토리지 수요 증가 및 메모리 가격 상승 국면 진행 중.', 'drivers': ['AI 데이터센터 투자 및 데이터 생성량 성장세', 'NAND 웨이퍼 수급 및 공급업체 가동률', 'PC·모바일·에지 기기 교체 주기']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '데이터센터와 엣지 디바이스용 NAND 플래시 메모리를 설계 및 제조해 판매한다. 과거 메모리 업황 변동성에 노출되었던 스팟 거래 구조에서 벗어나 다년간 물량과 가격을 묶어두는 NBM 장기계약 방식으로 사업 모델을 전면 개편했다. 그 결과 AI 인프라 확충 수요와 맞물리며 분기 매출이 $11.0B로 전년 대비 급증하고 수주잔고 $88.9B를 확보했다.', 'must_happen': ['2027년 Q2 가이던스 매출 상단 $12.6B 달성', '2027년 내 AI 추론용 차세대 HBF 첫 고객사 샘플 공급 완료', '향후 12개월 동안 NBM 잔여 이행 의무의 20% 이상을 실제 매출로 실현'], 'breaks_if': ['2027년 Q3 QoQ 매출 역성장 폭이 과거 평균(-19%) 이상으로 확대', 'NBM 고객사 채무 불이행 또는 $12.8B 규모 금융 담보 청구 사태 발생', '미국 무역확장법 232조 및 301조 조사로 인한 관세 면제 취소 및 원가율 상승']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2026 매출 $20.2B(전년 대비 +175.3%), 영업이익 $12.4B(OPM 61.2%), 순이익 $11.4B.\n영업이익은 FY2026에 흑자로 전환됨.\n영업활동 현금흐름 $11.7B · 보유 현금 $4.8B.'
