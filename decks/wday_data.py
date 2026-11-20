# -*- coding: utf-8 -*-
"""WDAY 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-10 (반영 공시 2026-09-29)
출처 코드
  ANNUAL = 10-K(2026-03-06 제출)
  EARN   = 8-K 공시(2026-09-29)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-09-29'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-10'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '8-K 공시(2026-09-29)',
    'DECK': '8-K 공시(2026-09-29)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'WDAY', 'name': 'Workday, Inc.', 'exchange': 'Nasdaq',
           'sector': '클라우드 인사·재무 AI', 'cik': 1327811}

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
CARRIED_OVER = {'TAM.estimates': '2026-10-20', 'TAM.note': '2026-10-20'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'Fortune 500의 65% 이상을 고객사로 보유',
    '구독 매출 $8.83B 기록, 전체 매출의 92% 비중',
    '11,500개 이상 기업에 HCM·재무 SaaS 공급'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2005,
    'listed': 2012,
    'listing_type': 'IPO',
    'listing_date': '',
    'founders': 'David Duffield, Aneel Bhusri',
    'timeline': [
        ('2005년', 'David Duffield와 Aneel Bhusri가 클라우드 HCM 전용 기업 Workday 설립'),
        ('2022년', '$3.0B 규모 선순위 채권 발행으로 장기 운용 자금 조달'),
        ('2025년', 'AI 채용 플랫폼 Paradox($1.1B) 및 지식관리 AI 기업 Sana($1.1B) 인수', True),
        ('2025년', '인력 7.5% 감축을 포함한 구조조정(Fiscal 2026 Restructuring Plan) 시행'),
        ('2026년', 'Workday Build 및 Data Cloud 공개, 인력 2% 추가 감축 계획 발표', True)
    ],
    'employees': [('2026년 1월 31일', 21070)],
    'employee_src': '2026년 1월 31일 공식 집계',
    'chart_annotations': [
        (2020, 3, '1 +84% 변동'),
        (2025, 10, '2 -49% 변동')
    ],
    'note': 'FY2026 매출 $9.55B(전년 대비 13% 증가), 구독 매출 $8.83B(전년 대비 14% 증가)를 기록하며 견조한 성장세를 유지 중임. GAAP 영업이익률 7.5%($721.0M), Non-GAAP 영업이익률 29.6%($2.82B)를 기록하며 구조적 수익성 개선이 진행되는 국면임. FY2026 중 $303.0M 규모의 구조조정 비용(인력 7.5% 감축 등)을 반영했음에도 연간 $2.78B의 자유현금흐름(FCF)을 창출함. Paradox 및 Sana 등 AI 전문 기업 인수를 지속하며 에이전트 기반 enterprise AI 플랫폼으로의 가치 재평가 단계에 위치함.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2020.03→2020.08', "pct": '+84%', "range": '$130.22→$239.71', "reason": '클라우드 애플리케이션의 강한 수요로 매출이 급증했기 때문'},
    {"no": 2, "dir": 'down', "period": '2025.10→2026.04', "pct": '-49%', "range": '$239.92→$122.40', "reason": '단일 계기 미확인 — 분기 실적 발표, AI 채용 차별 소송 리스크 및 AI 관련 보도가 이어짐.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'ORCL': 'ORACLE CORP', 'NOW': 'ServiceNow, Inc.'},
    'ciks': {'ORCL': 1341439, 'NOW': 1373715},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Aneel Bhusri', 'role': 'CEO', 'since': 2026,
            'bio': '공동 창업자로서 Executive Chair를 거쳐 2026년 2월 CEO로 복귀함. 회사의 창업기부터 주식 의결권의 과반 이상을 동업자 David Duffield와 함께 보유하며 경영 및 이사회를 총괄해옴.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Mark S. Garfield', 'CAO', ''),
        ('Gerrit S Kazmaier', '사장 · Prod. · Tech.', ''),
        ('Zane Rowe', 'CFO', ''),
        ('Robert Enslin', '사장 · CCO', ''),
        ('Richard Harry Sauer', 'CLO · Secty', '')
    ],
    'note': '공동 창업자인 David Duffield와 Aneel Bhusri가 10:1 의결권의 Class B 주식을 통해 대다수의 의결권을 독점적으로 보유 및 지배함.',
    'rsu_note': '',
}

SHARES = {
    'note': '총 $3.0B 규모의 선순위 채권(Senior Notes, 만기 2027/2029/2032년)을 보유 중임. $1.0B 회전신용공여(Revolving Credit Facility) 한도를 보유하고 있으나 미인출 상태임. 별도 전환사채는 없으나 임직원 주식보상(RSU) 및 인수 관련 주식 교부에 따른 발행주식수 증가 요인이 존재함.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('구독 서비스 (Subscription Services)', 2450.3, 92.5), ('전문 서비스 (Professional Services)', 198.7, 7.5)],
    'detail': [
        ('구독 서비스 (Subscription Services)',
         '클라우드 애플리케이션 접속 권한, AI 에이전트 솔루션 및 표준/강화 고객 지원 서비스 제공함', 2450.3, 0),
        ('전문 서비스 (Professional Services)',
         '시스템 구축 컨설팅, 통합 배치 최적화 및 고객/파트너 대상 교육 서비스 제공함', 198.7, 0)
    ],
    'by_geo': [],
    'competitors': ['Oracle', 'SAP', 'Anaplan', 'ADP', 'Coupa Software', 'Dayforce', 'Microsoft', 'NetSuite', 'ServiceNow', 'UKG'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q2 FY27',
    'kpis': [
        ('매출', '$2.65B', '+13% YoY', 'up'),
        ('영업이익', '$313.0M', '+26% YoY', 'up'),
        ('순이익', '$632.0M', '+177% YoY', 'up'),
        ('영업현금흐름', '$696.0M', '+52% YoY', 'up'),
        ('현금', '$661.0M', '-48% YoY', 'dn')
    ],
    'facts': [
        ('인력 감축 비율', '제품 및 기술 부문 중심 재편', '2.5%'),
        ('구독 매출 전망', 'FY27 구독 매출 가이던스', '$9.94B ~ $9.95B'),
        ('AI ARR 성과', 'AI 연간 반복 매출 규모', '$600.0M'),
        ('구조조정 비용', '총 재편 관련 예상 수반 비용', '$65.0M ~ $80.0M'),
        ('AI ACV 비중', '신규 ACV 내 AI 비중', '25%+'),
        ('영업이익률 목표', 'FY27 비GAAP 영업이익률 목표', '31.0%')
    ],
    'quotes': [
        
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 3, 'growth_years': 0, 'competitors': 10, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 2곳 중 시총 3위($45.8B) → 3점', '20%+ 성장 가능 연수': '컨센서스·실적 어디서도 20%+ 성장 근거 없음 → 0점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 10곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 성장 가능 연수, 신시장 CAGR.'

INCOME_NOTE = '2022년 $5.1B에서 2026년 $9.6B로 외형 성장이 지속됨. 순이익은 2023년 -$367.0M의 적자 전환 이후 2024년 $1.4B로 급증했으나 이후 $526.0M과 $693.0M을 기록하며 변동성 노출.'
BALANCE_NOTE = '보유 현금은 2023년 $1.9B로 정점을 찍은 뒤 2026년 $1.5B 수준으로 완만한 감소세 보임. 자산 유동성 관리가 안정적으로 유지되는 국면.'
CASHFLOW = {
    'note': '영업현금흐름이 2022년 $1.7B에서 2026년 $2.9B까지 매년 우상향함. 본업에서의 현금 창출력이 뚜렷한 확장세를 보이며 재무 건전성 뒷받침.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'cloud enterprise software 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('EIN News', 396.7, 2030)
    ],
    'note': '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2027년 Q3', '구조조정 관련 비용 인식 및 GAAP 영업이익률 영향 반영', 'GAAP 실적에 약 $55.0M~$70.0M 비용 반영 및 non-GAAP 대비 마진 갭 20~21%p 확대 영향 검증', 'high'),
    ('2027년 Q4', '임차 사무공간 감축 재편 완료 및 추가 비용 인식', '사무공간 감축 완료 및 잔여 $10.0M 구조조정 비용 인식 후 비GAAP 마진 성장 궤도 유지 판단', 'mid'),
    ('2028년 Q1', '인력 구조조정 완료 및 생산성 향상 검증', '2.5% 인력 감축 완료 후 신규 인력 증원 없이 AI 활용 기반 효율성 개선 입증 여부 확인', 'high'),
    ('2028년~', 'FY28 비GAAP 영업이익률 2%p 이상 추가 확장 달성', '내부 AI 도입에 따른 비용 효율화로 경영진이 제시한 마진 확장 가이던스 달성 여부 확인', 'high'),
    ('2026년 11월', '분기 실적발표', 'EPS 컨센서스 $2.74 (범위 $2.54~$2.92) 대비 실제치 확인', 'high'),
    ('FY2027', '연간 컨센서스 달성 여부', '매출 $10.7B · EPS $11.09 (애널리스트 41명)', 'high')
]
CHECKPOINT_NOTE = '2027년 Q3부터 2028년 Q1까지 진행되는 구조조정 비용 집행 마무리와 함께 AI 내부 효율화로 FY28 비GAAP 영업이익률 2%p 추가 확장을 달성하는지가 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '클라우드 엔터프라이즈 SW', 'chain': ['인프라·클라우드', '코어 SaaS 개발', 'AI·플랫폼 확장', '직판·파트너 유통', '엔터프라이즈 고객'], 'position': 1, 'spans': [1, 2, 3], 'position_note': 'Fortune 500 기업 65% 이상을 고객으로 확보하여 인사·재무 데이터에 대한 높은 전환비용과 가격 결정력을 보유함.', 'cycle': '거시경제 불확실성 및 관세·인플레이션 여파로 신규 수주 검토 심화 및 영업 주기 연장 국면임.', 'drivers': ['기업 IT 및 AI 투자 예산', '글로벌 고용 및 백하우스(Headcount) 변동']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': 'Workday는 인사 및 재무 SaaS 솔루션을 제공하며 AI 에이전트 도입을 통해 매출 성장을 가속화하고 있음. Q2 신규 ACV의 25% 이상인 $100.0M+를 AI 제품이 창출했고 AI ARR은 전년 대비 200% 증가한 $600.0M을 기록함. 인력 2.5% 감축과 내부 AI 활용 확대를 통해 FY28 비GAAP 영업이익률 2%p 추가 개선을 추진 중임.', 'must_happen': ['FY27 구독 매출 $9.94B ~ $9.95B 달성', '2028년 Q1까지 2.5% 인력 구조조정 완료', 'FY28 비GAAP 영업이익률 최소 2.0%p 이상 추가 확장'], 'breaks_if': ['구조조정 예상 비용이 상한선인 $80.0M을 크게 초과', 'AI 에이전트 이용 고객 수가 5,500개 미만으로 감소 전환', 'FY28 구독 매출 성장률이 제시치인 11.0%를 하회']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2026 매출 $9.6B(전년 대비 +13.1%), 영업이익 $721.0M(OPM 7.5%), 순이익 $693.0M.\n영업이익은 FY2024에 흑자로 전환됨.\n영업활동 현금흐름 $2.9B · 보유 현금 $1.5B.'
