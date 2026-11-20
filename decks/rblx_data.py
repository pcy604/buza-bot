# -*- coding: utf-8 -*-
"""RBLX 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-16 (반영 공시 2026-10-29)
출처 코드
  ANNUAL = 10-K(2026-02-11 제출)
  EARN   = 10-Q 공시(2026-10-29)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-10-29'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-16'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-10-29)',
    'DECK': '10-Q 공시(2026-10-29)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'RBLX', 'name': 'Roblox Corp', 'exchange': 'NYSE',
           'sector': '메타버스·온라인 게임 플랫폼', 'cik': 1315098}

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
CARRIED_OVER = {}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'FY2025 DAU 1억 2,700만 명 대상 3D 플랫폼 운영함',
    'Robux 가상화폐 결제 수수료 중심 수익 창출함',
    'FY2025 크리에이터 보상 집행액 $1,503.1M 기록함'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2004,
    'listed': 2021,
    'listing_type': '',
    'listing_date': '',
    'founders': 'David Baszucki',
    'timeline': [
        ('2004', '델라웨어주에서 법인 설립함', True),
        ('2019', '텐센트 계열사와 중국 합작법인(Roblox China Holding Corp) 설립함'),
        ('2020', "중국 정부로부터 'Luobulesi' 판호(Publishing License) 획득함"),
        ('2022', '개발자 환전 프로그램(DevEx) 최소 신청 기준 50,000 Robux로 인하함'),
        ('2023', 'DevEx 최소 신청 기준 30,000 Robux로 추가 인하함'),
        ('2025', '네바다주로 법인 재조정(Reincorporation) 완료함', True),
        ('2025', '크리에이터 보상 프로그램(Creator Rewards Program) 신규 출시함'),
        ('2025', "가상 3D 콘텐츠 생성형 AI 시스템 'Roblox Cube' 공개함"),
        ('2025', '플랫폼 전반 연령 확인(Age-check) 시스템 도입 시작함'),
        ('2026', '채팅 기능 이용 지역 대상 의무 연령 확인 시스템 본격 시행함')
    ],
    'employees': [('2025년 12월 31일', 3065)],
    'employee_src': '2025년 12월 31일 공식 집계',
    'chart_annotations': [
        (2025, 3, '1 +136% 변동'),
        (2021, 11, '2 -74% 변동')
    ],
    'note': 'FY2025 평균 DAU 1억 2,700만 명, 연간 총 이용시간 1,239억 시간 달성하며 글로벌 사용자 기반 확장 지속함. 고연령층 확장, 3D 생성형 AI(Roblox Cube) 도입 및 광고 수익화 확대를 추진 중임. 지속적 기술·인프라 및 안전 조치 투자로 FY2025 순손실 $1,065.1M 기록, 누적 결손금은 $5,060.7M 수준임.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2025.03→2025.07', "pct": '+136%', "range": '$52.96→$125.03', "reason": '단일 계기 미확인 — 실적 호조, 이용자 26% 급증 및 IP 파트너십 확장에 기인함.'},
    {"no": 2, "dir": 'down', "period": '2021.11→2022.05', "pct": '-74%', "range": '$113.79→$30.00', "reason": '단일 계기 미확인 — 코로나 효과 감소로 인한 매출 타격과 성장 둔화 우려가 반영됨.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'TME': 'Tencent Music Entertainment Group', 'U': 'Unity Software Inc.', 'NTES': 'NetEase, Inc.'},
    'ciks': {'TME': 1744676, 'U': 1810806, 'NTES': 1110646},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'David Baszucki', 'role': 'CEO', 'since': 0,
            'bio': 'Roblox 창업자이자 대표이사(CEO) 및 이사회 의장임. 2004년 창업 이래 플랫폼 기술 개발과 크리에이터 중심 생태계 구축 전략을 총괄 주도함.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Amy Marie Rawlings', 'CAO', ''),
        ('Mark Reinstra', 'Chief Legal Off. · Corp. Sec.', ''),
        ('Sean Jack Buckley', 'Chief People · Systems Officer', ''),
        ('Matthew D Kaufman', 'Chief Safety Officer', ''),
        ('Naveen K. Chopra', 'CFO', '')
    ],
    'note': '창업자 David Baszucki가 Class B 차등의결권 주식을 보유하여 이사회 구성 및 주요 경영 사안에 대한 독점적 의결권을 행사함.',
    'rsu_note': '',
}

SHARES = {
    'note': '주식기준보상(RSU/스톡옵션) 행사 및 잠재적 주식 발행에 따른 기존 주주지분 희석 가능성이 원문에 기술됨.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Roblox Platform', 1572.0, 100.0)],
    'detail': [
        ('Roblox Platform',
         '3D 가상 경험 탐색 및 크리에이터 콘텐츠 개발·수익화를 지원하는 단일 통합 메타버스 플랫폼 운영함', 1572.0, 0)
    ],
    'by_geo': [],
    'competitors': ['Amazon', 'Apple', 'Meta Platforms', 'Google', 'Microsoft', 'Tencent', 'Epic Games', 'Unity', 'Valve', 'Electronic Arts', 'Take-Two', 'NetEase', 'YouTube', 'TikTok', 'Discord', 'Snap'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 2026',
    'kpis': [
        ('매출', '$1.57B', '+16% YoY', 'up'),
        ('영업이익', '$-283.0M', '+4% YoY', 'up'),
        ('순이익', '$-227.0M', '+11% YoY', 'up'),
        ('영업현금흐름', '$629.0M', '+42% YoY', 'up'),
        ('현금', '$1.09B', '+7% YoY', 'up')
    ],
    'facts': [
        ('분기 매출', '전년 동기 대비 16% 증가한 GAAP 기준 매출액', '$1.57B'),
        ('분기 부킹', '유저 결제액 기반 비GAAP 부킹 실적', '$1.70B'),
        ('일평균유저', '플랫폼 접속 일일 활성 사용자 수', '138.0M'),
        ('조정EBITDA', '소송 충당금 및 주식보상비 제외 비GAAP 이익', '$138.0M'),
        ('개발자수수료', '크리에이터 대상 획득 로벅스 보상 지급액', '$403.0M'),
        ('잉여현금흐름', '9개월 누적 기준 잉여현금흐름 창출액', '$1.25B'),
        ('자사주매입', '9개월 누적 자사주 매입 및 소각 금액', '$580.0M')
    ],
    'quotes': [
        
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 5, 'growth_years': 2, 'competitors': 16, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 3곳 중 시총 2위($35.7B) → 5점', '20%+ 성장 가능 연수': '2년 (2026 +43% · 과거 2023~2025 CAGR +32%) → 4점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 16곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 신시장 CAGR.'

INCOME_NOTE = '매출은 2021년 $1.92B에서 2025년 $4.89B로 2배 이상 지속 성장함. 반면 순손실은 2021년 -$503.5M에서 2023년 -$1.16B까지 확대된 후 2025년 -$1.07B를 기록하며 외형 확대 대비 적자 구조가 정체 상태임.'
BALANCE_NOTE = '현금 자산은 2021년 $3.00B에서 2023년 $678.5M 수준으로 급감함. 2025년 $1.21B로 재차 회복세를 나타냈으나 과거 대비 현금 유동성 변동폭이 큰 편임.'
CASHFLOW = {
    'note': '영업현금흐름은 2022년 $369.3M으로 둔화된 이후 2025년 $1.80B로 대폭 개선됨. 순손실 지속에도 불구하고 로벅스 결제 기반의 플랫폼 특성에 힘입어 영업 현금 창출력은 유의미하게 반등함.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'metaverse platform 시장',
    'estimates': [],  # ⚠️ 자동생성: 뉴스 검색에서도 명확한 시장규모 숫자를 못 찾음
    'note': '' or '',

}

CHECKPOINTS = [
    ('2026년 Q4', 'GTA 신작 출전에 따른 부킹 가이던스 방어 여부', 'Q4 부킹 YoY 10~15% 감소 하향 가이던스 제시 상황에서 추가 이탈 여부 확인 필요', 'high'),
    ('2026년 Q4', 'FTC 및 미 주정부 아동보호법(COPPA) 소송 향방', '법적 충당금 추가 발생 및 아동 안전 기능 강제 변경 시 유저 이탈 가능성 존재', 'high'),
    ('2027년 1월', 'EU VLOP(대형 온라인 플랫폼) 규제 이행 시작', '연례 감사 및 위험 평가 의무화에 따른 유럽 지역 운영 비용 증가 가능성', 'mid'),
    ('2027년~', 'Universal Player 및 앱스토어 직접 출판 프레임워크 정식 도입', '외부 PC·콘솔 IP 흡수를 통한 18세 이상 성인 유저 층 확장 달성의 핵심 관건', 'high'),
    ('2026년 10월', '분기 실적발표', 'EPS 컨센서스 $-0.50 (범위 $-0.52~$-0.44) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $7.0B · EPS $-1.43 (애널리스트 25명)', 'high')
]
CHECKPOINT_NOTE = 'Q4 GTA 신작 출시에 따른 부킹 역성장 가이던스 방어와 2027년 Universal Player를 통한 18세 이상 성인 유저층 확장 성공 여부가 투자논리의 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '메타버스 및 게임 플랫폼', 'chain': ['클라우드 인프라', '개발자·제작자', '플랫폼·클라우드', '유저 커뮤니티'], 'position': 2, 'spans': [1, 2], 'position_note': 'Roblox Client, Studio, Cloud를 통합 운영하며 사용자 생성 콘텐츠(UGC) 생태계 제어 및 가상화폐(Robux) 결제 수수료 독점 구조 확보함.', 'cycle': '', 'drivers': ['일간 활성 사용자 수(DAU)', '유저당 평균 예약금(ABPDAU)', '크리에이터 보상 및 생태계 확산']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': 'Roblox는 유저 생성 콘텐츠 플랫폼 상에서 가상화폐(Robux) 판매와 광고로 수익을 창출함. Q3 2026 기준 일일 활성 유저 수 138.0M과 부킹 $1.70B를 기록하며 플랫폼 세력을 유지 중임. 향후 AI 자동화 도구와 외부 게임 이식(Universal Player)을 통해 18세 이상 유저 층으로 영역을 확장하는 단계임.', 'must_happen': ['2026년 Q4 부킹 $1.50B 이상 달성으로 하향 가이던스 방어', '2027년 Q2까지 Universal Player 기반 타사 대형 IP 게임 이식 10건 이상 완료', '2027년 Q4 기준 18세 이상 유저 비중 60% 이상 달성'], 'breaks_if': ['2분기 연속 일일 활성 사용자 수(DAU) 130.0M 미만으로 하락', 'FTC 및 주정부 소송 관련 일회성 법적 충당금 $300.0M 이상 추가 발생', '2026년 Q4 부킹 YoY 감소율 20% 초과']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $4.9B(전년 대비 +35.8%), 영업이익 $-1.2B(OPM -25.2%), 순이익 $-1.1B.\n매출은 최근 6개 회계연도 연속 증가.\n영업활동 현금흐름 $1.8B · 보유 현금 $1.2B.'
