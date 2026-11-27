# -*- coding: utf-8 -*-
"""DELL 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-27 (반영 공시 2026-11-24)
출처 코드
  ANNUAL = 10-K(2026-03-16 제출)
  EARN   = 8-K 공시(2026-11-24)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-11-24'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-27'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '8-K 공시(2026-11-24)',
    'DECK': '8-K 공시(2026-11-24)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'DELL', 'name': 'Dell Technologies Inc.', 'exchange': 'NYSE',
           'sector': 'IT 인프라·AI서버·PC', 'cik': 1571996}

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
CARRIED_OVER = {'HISTORY.listing_type': '2026-11-05', 'LEADERSHIP.rsu_note': '2026-11-05', 'SEGMENTS.competitors': '2026-11-05', 'TAM.estimates': '2026-11-05', 'TAM.note': '2026-11-05'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'AI 최적화 서버(FY26 매출 $24.7B) 및 서버 공급',
    '상업용·소비자용 PC(FY26 매출 $51.0B) 판매',
    '기업용 스토리지 솔루션(FY26 매출 $16.6B) 제공'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 1984,
    'listed': 2016,
    'listing_type': '직상장',
    'listing_date': '',
    'founders': 'Michael S. Dell',
    'timeline': [
        ('1984', 'Michael S. Dell이 Dell Inc. 설립', True),
        ('2016', 'EMC Corporation 인수 합병 완료', True),
        ('2023', 'VMware의 Broadcom 인수 완료 및 파트너십 재편 진행'),
        ('2024', 'VMware 단독 제품 유통에 대한 Commercial Framework Agreement 종결'),
        ('2025', '보안 자회사 Secureworks를 Sophos에 $0.9B 규모로 매각 완료', True)
    ],
    'employees': [('FY2026 10-K (2026년 1월 30일)', 97000)],
    'employee_src': 'FY2026 10-K (2026년 1월 30일) 공식 집계',
    'chart_annotations': [
        (2026, 1, '1 +277% 변동'),
        (2026, 9, '2 -45% 변동')
    ],
    'note': 'FY2026 총매출은 전년 대비 19% 증가한 $113.5B, 영업이익은 31% 증가한 $8.1B를 기록함. AI 최적화 서버 매출이 $24.7B(전년 대비 166% 증가)로 급성장하며 ISG 부문 매출(40% 증가한 $60.8B) 강세를 견인함. 지속적인 사업 현대화 및 비용 관리 조치로 임직원 수가 약 97,000명 수준으로 축소됨.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2026.01→2026.06', "pct": '+277%', "range": '$114.44→$431.46', "reason": 'AI 서버 매출 전망 상향과 대규모 정부 수주가 주가 상승을 견인함.'},
    {"no": 2, "dir": 'down', "period": '2026.09→2026.11', "pct": '-45%', "range": '$537.95→$297.06', "reason": '단일 계기 미확인 — AI 실적 호조 발표 속 주가 하락세 지속됨.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {},
    'ciks': {},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Michael S. Dell', 'role': 'CEO', 'since': 1984,
            'bio': '1984년 회사 설립 이후 CEO로 재직 중이며 2004년 사임 후 2007년 복귀함. Dell Technologies 이사회 의장 겸 CEO로서 글로벌 전략과 운영 전반을 총괄함.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('David W. Dorman', '이사', '센터뷰 캐피털 파트너'),
        ('Egon Durban', '이사', '실버레이크 공동 CEO'),
        ('David Grain', '이사', '그레인 매니지먼트 CEO'),
        ('William D. Green', '이사', '前 액센츄어 회장'),
        ('Ellen J. Kullman', '선임 독립이사', '카본 이사회 의장')
    ],
    'note': '창업자 Michael S. Dell과 관련 신탁이 Class A 주식을 통해 의결권 91.7%를 보유해 지배력을 행사함.',
    'rsu_note': '주식보상은 성과 조건에 따라 최고 수준 달성 시 가치가 산정됩니다. 구체적인 성과 목표(매출, 시총 등) 및 가중치, 기간에 대한 명시는 없습니다. 표준 시간 베스팅 외의 추가적인 성과 조건에 대한 구체적인 정보가 부족합니다.',
}

SHARES = {
    'note': 'Class A 및 Class B 보통주는 Class C 보통주로 1대 1 전환 가능함. 주식보상 플랜에 따라 향후 교부 가능한 미행사 옵션·RSU·DSU 물량은 약 2,200만 주이며 추가 예약 수량은 4,500만 주임.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Infrastructure Solutions Group (ISG)', 25176.5, 53.6), ('Client Solutions Group (CSG)', 21090.0, 44.9)],
    'detail': [
        ('Infrastructure Solutions Group (ISG)',
         'AI 최적화 서버, 전통 서버 및 네트워킹, 기업용 스토리지 솔루션을 개발 및 제공함.', 25176.5, 0),
        ('Client Solutions Group (CSG)',
         '상업용 및 소비자용 데스크톱, 노트북, 워크스테이션 및 브랜드 주변기기를 제공함.', 21090.0, 0)
    ],
    'by_geo': [],
    'competitors': ['HP Inc.', 'Lenovo Group Limited', 'Apple Inc.', 'Microsoft Corporation', 'Amazon Web Services, Inc.', 'Google Cloud', 'International Business Machines Corporation', 'Hewlett Packard Enterprise Company', 'NetApp, Inc.', 'Pure Storage, Inc.', 'Hitachi, Ltd.'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 FY27',
    'kpis': [
        ('매출', '$46.97B', '—', 'flat'),
        ('영업이익', '$5.38B', '—', 'flat'),
        ('순이익', '$4.13B', '—', 'flat'),
        ('영업현금흐름', '$4.08B', '+46% YoY', 'up'),
        ('현금', '$11.57B', '—', 'flat')
    ],
    'facts': [
        ('분기 매출', '사상 최대 분기 총 매출 달성', '$54.9B'),
        ('ISG 매출', '인프라 솔루션 부문 매출 성장', '$42.0B'),
        ('AI 서버', 'AI 최적화 서버 매출 비중 확대', '$22.0B'),
        ('AI 수주잔고', '검증 거친 역대 최대 AI 수주잔고', '$132.3B'),
        ('영업비용률', '매출 대비 비GAAP 영업비용 비중', '7.0%'),
        ('자사주매입', '이사회 추가 승인 자사주 매입 한도', '$25.0B')
    ],
    'quotes': [
        ('CFO David Kennedy', '팀이 매우 훌륭하게 이행하여 $54.9B의 역대 최대 매출, 역대 최대 EPS, 그리고 주주에게 환원된 역대 최대 금액인 $4.9B를 달성했습니다. 매출 대비 영업비용 비중은 계속 감소하여 비GAAP 영업비용은 매출의 7%로 42년 회사 역사상 가장 낮아졌습니다.', 'The team executed exceptionally well, driving record revenue of $54.9 billion, record EPS and a record $4.9 billion returned to shareholders. Operating expenses as a percentage of revenue continues to decline, while non-GAAP operating expenses fell to 7% of revenue, the lowest in our 42-year history.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 0, 'growth_years': 2, 'competitors': 0, 'governance': 5, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '동급 경쟁사(시총 0.05~20배) 매칭 0곳 — 순위 비교 불가로 0점', '20%+ 성장 가능 연수': '2년 (2027 +79% · 2028 +21%) → 4점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 0곳 → 0점', '지배구조 개편': '델라웨어에서 텍사스로 법인 재편 → 5점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 글로벌 탑티어, 신시장 CAGR.'

INCOME_NOTE = '매출액은 2024년 $88.4B까지 하락하였으나 빠르게 회복하여 2026년 $113.5B로 크게 증가함. 순이익 역시 2023년 $2.4B를 저점으로 반등하여 2026년 $5.9B를 기록하며 수익 구조 개선세를 입증함. AI 서버 및 기업용 IT 인프라 수요 확대에 힘입어 외형 성장과 이익 회복이 동반 진행 중.'
BALANCE_NOTE = '현금성 자산은 2022년 $9.5B에서 2025년 $3.6B까지 지속 감소하며 축소 양상을 보임. 2026년 뚜렷한 실적 반등에 힘입어 현금 보유량이 $11.5B로 급증하며 유동성 완충력이 대폭 강화됨.'
CASHFLOW = {
    'note': '영업현금흐름은 2023년 $3.6B 및 2025년 $4.5B로 일시적 둔화를 겪었으나 2026년 $11.2B로 대폭 확충됨. 2022년 수준($10.3B)을 상회하는 영업현금 창출력을 회복하며 안정적인 현금 흐름 기반 구축 완료함.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'enterprise IT hardware 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('Goldman Sachs', 1240.0, 2030.0)
    ],
    'note': '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2027년 Q4', 'Q4 FY27 매출 가이던스 달성 여부', 'Q4 매출 $56.3B 및 비GAAP EPS $8.40 가이던스 달성을 통한 단기 실적 모멘텀 검증', 'high'),
    ('2027년~', '연간 AI 최적화 서버 매출 가이던스 이행', 'FY27 상향 가이던스인 AI 서버 매출 $78.0B 달성을 통한 AI 인프라 사업 확장성 확인', 'high'),
    ('2027년~', '비GAAP 영업비용률 7% 수준 유지', 'AI 서버 매출 확대 속에서도 운영 효율화를 통한 수익성 고도화 지속성 검증', 'mid'),
    ('2027년~', '추가 승인된 $25.0B 자사주 매입 한도 집행', '강력한 영업현금흐름 기반의 주주환원 확대 정책 지속 여부 확인', 'mid'),
    ('2027년 2월', '분기 실적발표 (예정일 추정치)', 'EPS 컨센서스 $8.58 (범위 $8.40~$9.72) 대비 실제치 확인', 'high'),
    ('FY2027', '연간 컨센서스 달성 여부', '매출 $202.9B · EPS $29.87 (애널리스트 24명)', 'high')
]
CHECKPOINT_NOTE = 'AI 최적화 서버 중심의 ISG 부문 폭발적 성장과 $132.3B 수주잔고의 순조로운 매출 전환, 영업비용 효율성 유지가 투자논리의 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': 'IT 인프라 및 서버', 'chain': ['부품·반도체 조달', 'IT장비·서버 제조', '소프트웨어·솔루션', '글로벌 유통·판매', '엔터프라이즈·소비자'], 'position': 1, 'spans': [1, 2, 3], 'position_note': '글로벌 공급망과 자체 및 위탁 제조 시설, 글로벌 영업·채널 망을 기반으로 서버·스토리지·PC 솔루션을 직접 조립·공급함.', 'cycle': 'AI 최적화 서버 및 전통 서버 수요 확대로 ISG 백로그가 증가한 반면 CSG 부문은 상업용 PC 교체 주기 진입으로 수요가 완만히 회복 중임.', 'drivers': ['AI 모델 학습 및 추론용 서버 수요', '기업용 PC 교체 주기', '핵심 부품(메모리·GPU) 수급 및 단가 변동']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '델은 전통 PC 제조사에서 인프라 솔루션(ISG) 중심의 AI 서버 전문 기업으로 체질을 전환했습니다. Q3 FY27 매출 $54.9B 중 ISG 부문이 $42.0B를 차지하며 성장을 주도하고 $132.3B의 AI 수주잔고를 확보했습니다. 영업비용 비중을 역대 최저인 7.0%까지 낮추며 외형 성장과 수익성 개선을 동시에 달성하고 있습니다.', 'must_happen': ['2027년 Q4 매출 $56.3B 달성 성공', 'FY27 연간 AI 최적화 서버 매출 $78.0B 가이던스 충족', '$132.3B AI 수주잔고의 안정적 출하 및 매출 인식'], 'breaks_if': ['AI 서버 신규 수주 둔화로 인한 수주잔고 감소 전환', '비GAAP 영업비용률 7% 대폭 초과로 인한 영업이익률 훼손', 'CSG(클라이언트 솔루션) 부문 수익성 둔화 지속']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2026 매출 $113.5B(전년 대비 +18.8%), 영업이익 $8.1B(OPM 7.2%), 순이익 $5.9B.\n영업이익은 FY2020에 흑자로 전환됨.\n영업활동 현금흐름 $11.2B · 보유 현금 $11.5B.'
