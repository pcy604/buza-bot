# -*- coding: utf-8 -*-
"""IONQ 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-18 (반영 공시 2026-11-05)
출처 코드
  ANNUAL = 10-K(2026-02-25 제출)
  EARN   = 10-Q 공시(2026-11-05)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-11-05'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-18'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-11-05)',
    'DECK': '10-Q 공시(2026-11-05)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'IONQ', 'name': 'IonQ, Inc.', 'exchange': 'NYSE',
           'sector': '양자 컴퓨팅·네트워킹', 'cik': 1824920}

# 이 필드는 autogen.py를 다시 돌려도 덮어쓰지 않는다 — 사람이 확인·보정한 값을 지키는
# 장치. 검수하다가 "이 값은 이게 맞다"고 확정한 필드의 경로를 여기 추가하면 된다.
# (경로 형식: 'HISTORY.founded', 'LEADERSHIP.ceo.bio', 'TAM.estimates' …)
# 여기 없어도, 새로 뽑은 값이 비었는데 기존 값이 있으면 기존 값이 자동으로 유지된다.
LOCKED = ['LEADERSHIP.ceo.bio', 'LEADERSHIP.ceo.name', 'LEADERSHIP.rsu_note', 'TAM.estimates', 'TAM.label']

# 이번 재생성에서 **새로 뽑지 못해 옛 값을 그대로 쓴** 필드와, 그 값이 만들어진 날.
# 비어 있으면 이 파일의 모든 값이 이번 생성분이라는 뜻이다.
# 예전에는 이 정보가 콘솔에만 찍혀서, 파일은 BUILT_AT=오늘 인데 내용의 절반이
# 한 달 전 값인 상태를 아무도 알 수 없었다(러너 실행분은 로그도 안 본다).
# 완전히 새로 뽑고 싶으면: python decks/autogen.py TICKER --fresh
CARRIED_OVER = {'LEADERSHIP.ceo.name': 'LOCKED', 'LEADERSHIP.ceo.since': '2026-10-27', 'LEADERSHIP.rsu_note': 'LOCKED', 'TAM.estimates': 'LOCKED', 'TAM.label': 'LOCKED'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    '트레이딩 심볼 IONQ로 뉴욕증권거래소 상장 기업임',
    '이온 트랩 방식 양자 컴퓨터 및 클라우드 액세스(QCaaS) 제공',
    '2025년 기준 누적 순손실 $1,194.1M 기록함'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2015,
    'listed': 2021,
    'listing_type': 'SPAC합병',
    'listing_date': '2021-10-04',
    'founders': 'Chris Monroe, Jungsang Kim',
    'timeline': [
        ('2015', 'Legacy IonQ 델라웨어주 법인 설립'),
        ('2021', 'dMY Technology Group III와 합병 상장', True),
        ('2025', 'Oxford Ionics 및 Lightsynq Technologies 인수', True)
    ],
    'employees': [('December 31, 2025', 1132)],
    'employee_src': 'December 31, 2025 공식 집계',
    'chart_annotations': [
        (2024, 6, '1 +580% 변동'),
        (2021, 12, '2 -74% 변동')
    ],
    'note': '이온 트랩 기반 양자 컴퓨팅 하드웨어 개발에 집중하는 중임. 다수의 기업 인수(옥스퍼드 아이오닉스, 라이트싱크 등)를 통해 양자 네트워킹과 센싱 역량을 확장함. 지속적인 연구개발 투자로 영업손실이 확대되는 국면임.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2024.06→2024.12', "pct": '+580%', "range": '$7.03→$47.77', "reason": '단일 계기 미확인 — 큐비텍 인수, 기술 혁신 및 파트너십 확대 지속됨'},
    {"no": 2, "dir": 'down', "period": '2021.12→2022.06', "pct": '-74%', "range": '$16.70→$4.39', "reason": '공매도 보고서 피격 및 기술주 전반의 하락세 영향임.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'RGTI': 'Rigetti Computing, Inc.', 'XNDU': 'Xanadu Quantum Technologies Ltd', 'QNT': 'Quantinuum Inc.'},
    'ciks': {'RGTI': 1838359, 'XNDU': 2097163, 'QNT': 2110105},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Niccolo M. de Masi', 'role': 'CEO', 'since': 2019,
            'bio': '기술 기업 경영 경력을 보유하며 회사 성장을 총괄함.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Inder M Singh', 'CFO · COO', ''),
        ('Paul T Dacier', 'CAO · CLO · 이사회 서기', ''),
        ('Scott Francis Millard', 'CBO', ''),
        ('Rima Alameddine', 'CRO', ''),
        ('Dean P. Acosta', 'CCA · GRO', '')
    ],
    'note': '2025년 경영진 및 이사회 구성원의 유의미한 변동이 발생함.',
    'rsu_note': 'CEO 2025년 LTI(장기성과보상) $27.0M(3년 PSU, 2025~2027 성과기간)의 실제 베스팅 조건: 매출 목표 달성도(가중치 90%) + "Algorithmic Qubits"(양자컴퓨팅 기술 성능 지표) 목표 달성도(가중치 10%) — 3년 후 목표 대비 0~200% 범위로 지급. 정확한 3년 매출 목표액 자체는 경쟁상 민감정보로 위임장에 비공개(금액 없음, 찾다 만 게 아니라 원래 공개 안 함). 참고: 이와 별개인 2025년 연간 보너스의 매출 목표는 중간값 $85M·상단 $95M로 공시됨. 주가는 조건이 아니라 목표 주식수 산정에만 쓰임($27M÷당시 주가). 별도로 연간 보너스도 현금 50%·주식 50% 지급.',
}

SHARES = {
    'note': '보통주 1주당 $11.50에 행사 가능한 Warrants(IONQ WS) 존재함',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Quantum Computing and Related Products and Services', None, None)],
    'detail': [
        ('Quantum Computing and Related Products and Services',
         '특수 양자 컴퓨팅 하드웨어 판매 및 클라우드 기반 양자 컴퓨팅 접근성(QCaaS) 제공', None, 0)
    ],
    'by_geo': [],
    'competitors': ['Amazon', 'Google', 'IBM', 'Intel', 'Microsoft', 'Rigetti Computing', 'PsiQuantum', 'Xanadu', 'Quantinuum Ltd.', 'Alpine Quantum Technologies GmbH', 'D-Wave', 'QuEra'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 2026',
    'kpis': [
        ('매출', '$173.8M', '+336% YoY', 'up'),
        ('영업이익', '$-433.1M', '-157% YoY', 'dn'),
        ('순이익', '$564.0M', '+153% YoY', 'up'),
        ('영업현금흐름', '$-151.0M', '-357% YoY', 'dn'),
        ('현금', '$209.5M', '-39% YoY', 'dn')
    ],
    'facts': [
        ('분기 매출', '전년 동기 대비 급증한 분기 매출액', '$173.8M'),
        ('영업 손실', 'R&D 및 M&A 관련 비용 증가', '$433.1M'),
        ('당기 순익', '파생상품 평가이익 반영 흑자 전환', '$563.1M'),
        ('수주 잔고', '미이행 계약 잔여 성능의무 총액', '$1.17B'),
        ('현금 자산', '현금성 자산 및 투자자산 합계', '$1.66B'),
        ('연간 가이드', '상향 조정된 연간 매출 목표', '$505.0M~$515.0M'),
        ('증자 대금', '주식 및 워런트 공모 순유입금', '$1.99B')
    ],
    'quotes': [
        
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 10, 'growth_years': 3, 'competitors': 12, 'governance': 0, 'market_cagr': 37.0}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 3곳 중 시총 1위($11.5B) → 10점', '20%+ 성장 가능 연수': '3년 (2026 +293% · 2027 +71% · 과거 2023~2025 CAGR +143%) → 6점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 12곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '시장조사기관 헤드라인 기준 시장 CAGR 37.0% → 18점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함.'

INCOME_NOTE = '2021년 $2.1M에 불과했던 매출이 2025년 $130.0M까지 급증하며 가파른 외형 성장세 시현. 같은 기간 순손실은 -$106.2M에서 -$512.1M로 확대되며 연구개발 및 운영 비용 증가에 따른 적자 구조 고착화.'
BALANCE_NOTE = '현금성 자산은 2023년 $35.7M까지 감소했으나, 2025년 대규모 자본 유입을 통해 $1,030.9B로 급증하며 유동성 확보. 공격적인 기술 투자와 사업 확장을 뒷받침할 재무적 완충력 확보.'
CASHFLOW = {
    'note': '영업활동 현금흐름은 2021년 -$26.5M에서 2025년 -$283.2M로 적자 폭이 매년 지속 확대. 양자 컴퓨팅 상용화 초기 단계의 구조적 현금 유출 지속.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': '양자컴퓨팅(2035년 기준)',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('Market Research Future', 14.19, 27.04),
        ('Precedence Research', 19.44, 29.73),
        ('Insightace Analytics', 40.45, 36.0),
        ('Market.us', 50.4, 37.0)
    ],
    'note': '제3자 컨설팅 보고서 인용 향후 10년간 최대 $2.0T 경제적 가치 추정' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2026년 Q4', 'Elisity 인수 완료 및 보안 사업 회계 통합', '고마진 구독형 소프트웨어 매출 비중 확대 여부 검증', 'high'),
    ('2026년 Q4', '2026년 연간 매출 가이던스 상단($515.0M) 달성', '6분기 연속 성장을 바탕으로 한 가이던스 이행 신뢰성 입증', 'high'),
    ('2027년 Q1~', 'SkyWater 파운드리 백오피스 및 원가 구조 통합 완료', '고정비 절감 및 2027년 수익성 개선 기반 마련 확인', 'mid'),
    ('2027년~', '6세대 Superion 256 시스템 전량 완판분 인도', '차세대 퀀텀 컴퓨팅 칩의 실제 상업적 인도 및 매출 인식 확인', 'high'),
    ('2026년 11월', '분기 실적발표', 'EPS 컨센서스 $-0.39 (범위 $-0.59~$-0.19) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $510.5M · EPS $-2.23 (애널리스트 7명)', 'high')
]
CHECKPOINT_NOTE = '2027년 Superion 256 출하와 SkyWater/Elisity 인수를 통한 하드웨어 제조 내재화 및 고마진 소프트웨어 매출 전환이 투자논리의 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '양자 컴퓨팅', 'chain': ['부품·소재 공급', 'QPU 제조', '양자 시스템 조립', '클라우드 서비스', '정부·기업 고객'], 'position': 2, 'spans': [1, 2, 3], 'position_note': '특화된 이온 트랩 하드웨어와 전용 제어 시스템을 직접 설계·제조하며 플랫폼 생태계를 구축함.', 'cycle': '', 'drivers': ['정부 및 민간 연구 예산', '하드웨어 큐비트 확장 속도', '양자 오류 정정 기술 진척']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': 'IonQ는 양자 컴퓨팅 하드웨어 판매, QCaaS 클라우드 서비스, 그리고 파운드리 제조 서비스(SkyWater)를 통해 매출을 창출함. 2026년 Q3 매출이 전년 동기 대비 336% 증가한 $173.8M를 기록하고 2027년용 Superion 256 생산 용량이 완판되는 등 양자 하드웨어 수요가 폭발하는 단계에 진입함. 파운드리 자체 소유와 Elisity 인수를 통해 하드웨어 생산 내재화와 양자 보안 분야 고마진 구독 매출 구조를 동시에 구축 중임.', 'must_happen': ['2026년 Q4 연간 매출 가이던스 상단인 $515.0M 달성', '2027년 Q1까지 SkyWater 파운드리 통합을 통한 원가 및 백오피스 비용 구조 효율화 완수', '2027년 6세대 Superion 256 시스템의 차질 없는 전량 인도 및 매출 인식'], 'breaks_if': ['RPO(수주잔고)가 2분기 연속 감소세로 전환', 'SkyWater Foundry Services 세그먼트 영업손실이 2027년 상반기까지 확대 지속', '2027년 Superion 256 시스템의 납기 지연 또는 기술적 칩 결함 발생']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $130.0M(전년 대비 +201.9%), 영업이익 $-633.7M(OPM -487.4%), 순이익 $-512.1M.\n매출은 최근 5개 회계연도 연속 증가.\n영업활동 현금흐름 $-283.2M · 보유 현금 $1.0B.'
