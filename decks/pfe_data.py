# -*- coding: utf-8 -*-
"""PFE 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-21 (반영 공시 2026-11-03)
출처 코드
  ANNUAL = 10-K(2026-02-26 제출)
  EARN   = 10-Q 공시(2026-11-03)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-11-03'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-21'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-11-03)',
    'DECK': '10-Q 공시(2026-11-03)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'PFE', 'name': 'PFIZER INC', 'exchange': 'NYSE',
           'sector': '제약·바이오', 'cik': 78003}

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
CARRIED_OVER = {'SHARES.note': '2026-10-30'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    '글로벌 연구 기반 바이오제약 기업으로 2025년 총매출 $62.6B 기록',
    'Eliquis(매출 비중 13%), Prevnar, Comirnaty 등 주요 의약품 제조 및 판매',
    '전 세계 약 200개 국가 및 영토에 의약품 및 백신 공급'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 1849,
    'listed': 2026,
    'listing_type': '',
    'listing_date': '2026-11-16',
    'founders': 'Charles Pfizer, Charles F. Erhart',
    'timeline': [
        ('1842', '미국 델라웨어주 법률에 따라 기업 설립'),
        ('2020', 'BioNTech와 공동 개발한 COVID-19 백신 Comirnaty 긴급사용승인 획득'),
        ('2023', '종양학 치료제 전문 기업 Seagen 인수 완료'),
        ('2025', '비만 및 심장대사질환 치료제 개발 기업 Metsera 인수 완료')
    ],
    'employees': [('2025년 12월 31일', 75000)],
    'employee_src': '2025년 12월 31일 공식 집계',
    'chart_annotations': [
        
    ],
    'note': '현재 글로벌 제약 시장에서 주요 블록버스터 제품의 특허 만료에 따른 제네릭 및 바이오시밀러 경쟁 가속화 국면에 직면해 있음. COVID-19 관련 제품 매출의 감소 추세를 상쇄하기 위해 2023년 Seagen 인수 및 2025년 Metsera 인수 등 대규모 M&A를 단행하며 종양학과 비만·대사질환 포트폴리오를 확장함. 동시에 전사적 비용 절감 프로그램(Realigning Our Cost Base Program)을 통해 비용 구조 개선 및 R&D 생산성 향상을 추진 중임.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'ABBV': 'AbbVie Inc.', 'AMGN': 'AMGEN INC', 'AZN': 'ASTRAZENECA PLC'},
    'ciks': {'ABBV': 1551152, 'AMGN': 318154, 'AZN': 901832},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Albert Bourla', 'role': 'CEO', 'since': 2019,
            'bio': '2019년 최고경영자(CEO)로 취임함. 2018년 최고운영책임자(COO)를 역임했으며, 1993년 피바스(Pfizer) 합류 이후 백신 및 종양학 부문 그룹 사장을 거치며 글로벌 사업을 총괄함.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Jennifer B. Damico', 'SVP · Controller', '')
    ],
    'note': '최고경영자 Albert Bourla를 필두로 R&D, 상업 운영, 재무, 법무 등 핵심 부문별 전문성을 갖춘 경영진으로 구성됨.',
    'rsu_note': '',
}

SHARES = {
    'note': '연차보고서에서 전환사채·워런트 등 별도 희석요인은 확인되지 않음',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Biopharma', None, None), ('PC1', None, None), ('Pfizer Ignite', None, None)],
    'detail': [
        ('Biopharma',
         '혁신 과학 기반의 바이오제약 제품 전 세계 연구, 개발, 제조, 마케팅, 판매 및 유통 담당', None, 0),
        ('PC1',
         '계약개발제조(CDMO) 및 특수 활성 제약 성분(API) 공급', None, 0),
        ('Pfizer Ignite',
         '선별된 혁신 바이오텍 대상 전략적 자문 및 R&D 서비스 제공 (2025년 사업 철수 결정 및 정리 중)', None, 0)
    ],
    'by_geo': [],
    'competitors': ['AbbVie Inc.', 'Amgen Inc.', 'AstraZeneca PLC', 'Bristol-Myers Squibb Company', 'Eli Lilly and Company', 'GSK plc', 'Johnson & Johnson', 'Merck & Co., Inc.', 'Novartis AG', 'Novo Nordisk', 'Roche Holding AG', 'Sanofi'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 2026',
    'kpis': [
        ('매출', '$22.64B', '-6% YoY', 'dn'),
        ('순이익', '$3.24B', '-8% YoY', 'dn'),
        ('영업현금흐름', '$2.62B', '+12% YoY', 'up'),
        ('현금', '$1.82B', '+36% YoY', 'up')
    ],
    'facts': [
        ('총 매출액', '코로나 제품 제외 시 7% 증대', '$16.6B'),
        ('순이익', 'GAAP 기준 당분기 순이익', '$3.2B'),
        ('조정 EPS', '비GAAP 희석 주당순이익', '$0.87'),
        ('Eliquis매출', '미국 내 약가 및 글로벌 수요 증가', '$2.5B'),
        ('Padcev매출', '1선 방광암 점유율 확대 영향', '$720M'),
        ('비용절감목표', '2029년까지 누적 순절감 목표', '$6.7B'),
        ('자산손상차손', 'sigvotatug vedotin 임상 실패 반영', '$3.8B')
    ],
    'quotes': [
        ('경영진', '코로나19 제품군 매출 감소에도 불구하고, Eliquis와 Padcev 등 핵심 신약의 강력한 성장세에 힘입어 비코로나 부문 매출 성장을 이어가고 있습니다.', 'Excluding contributions from Comirnaty and Paxlovid, Total revenues increased 7% operationally, driven by an increase in revenues for Eliquis, Padcev, and the Vyndaqel family.'),
        ('경영진', '미국 정부와 최종 승인 계약을 체결하여 약가 인하 방안을 이행하는 대신 섹션 232 의약품 관세율 0%를 2029년 초까지 유지하기로 확정했습니다.', 'Under these agreements, we have voluntarily committed to implement measures designed to make certain drug prices more comparable... the applicable tariff rate under the Section 232 Executive Order for Pfizer products will be zero until January 20, 2029.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 3, 'growth_years': 0, 'competitors': 12, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 3곳 중 시총 4위($156.2B) → 3점', '20%+ 성장 가능 연수': '컨센서스·실적 어디서도 20%+ 성장 근거 없음 → 0점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 12곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 성장 가능 연수, 신시장 CAGR.'

INCOME_NOTE = '매출은 2022년 $101.2B로 정점을 기록한 후 백신 수요 감소로 인해 2023년 $59.6B로 급감함. 순이익 역시 2022년 $31.4B에서 2023년 $2.2B까지 크게 줄었으나, 2024년 $8.1B 및 2025년 $7.8B 수준을 기록하며 기저효과 이후 점진적 안정화 진행 중.'
BALANCE_NOTE = '현금 자산은 2021년 $1.9B에서 2022년 $416.0M 수준으로 크게 축소됨. 2023년 $2.9B로 일시 반등했으나 2024년 $1.0B 및 2025년 $1.1B를 기록하며 타이트한 현금 유동성 기조를 유지함.'
CASHFLOW = {
    'note': '영업현금흐름은 팬데믹 매출 극대화 시기인 2021년 $32.9B 및 2022년 $29.3B에서 2023년 $8.7B로 하락함. 이후 2024년 $12.7B 및 2025년 $11.7B 수준을 회복하며 정상화된 창출력을 보여줌.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'biopharmaceutical 시장',
    'estimates': [],  # ⚠️ 자동생성: 뉴스 검색에서도 명확한 시장규모 숫자를 못 찾음
    'note': '' or '',

}

CHECKPOINTS = [
    ('2026년~', '비용 절감 프로그램 $1.0B 추가 절감 실행', '판관비 축소를 통한 영업이익률 방어 및 판관비율 개선 여부 검증', 'high'),
    ('2026년 Q4', 'Metsera 인수 파이프라인 GLP-1/아밀린 임상 진행', '비만 치료제 후발주자로서 개발 마일스톤 달성 및 상업성 입증 여부 확인', 'high'),
    ('2027년 1월', 'HHS 340B 시범 프로그램 시행에 따른 약가 영향', 'Eliquis, Ibrance, Xtandi 등 주요 제품의 실질 매출할인율 상승 위험 진단', 'mid'),
    ('2026년~2030년', '특허 만료(LOE)에 따른 연간 $1.1B 매출 감소 상쇄', '신약 성장 속도가 특허 만료로 인한 매출 절벽을 상쇄할 수 있는지 평가', 'high'),
    ('2027년 2월', '분기 실적발표 (예정일 추정치)', 'EPS 컨센서스 $0.68 (범위 $0.63~$0.83) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $63.1B · EPS $3.05 (애널리스트 23명)', 'high')
]
CHECKPOINT_NOTE = '비용 절감 프로그램의 차질 없는 이행과 Metsera 기반 비만 파이프라인 성과가 특허 만료에 따른 매출 손실을 상쇄하는 것이 핵심 투자논리임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '바이오의약품', 'chain': ['기초 연구·발굴', '임상 개발', '의약품 제조', '마케팅·유통', '정부·의료기관'], 'position': 0, 'spans': [0, 1, 2, 3, 4], 'position_note': '연구개발부터 글로벌 유통까지 전 단계를 수직계열화하여 핵심 파이프라인의 가격 결정력과 마켓 리더십을 확보함.', 'cycle': '특허 만료와 제네릭·바이오시밀러 경쟁 심화로 주요 품목의 매출 감소 국면 진행 중', 'drivers': ['신약 파이프라인 임상 성공률', '특허 보호 기간 및 만료 여부', '정부 약가 규제 및 보험 등재']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '화이자는 코로나19 관련 제품 매출 감소를 기존 항암제 및 신약 성장으로 전환하는 과도기를 지나고 있다. Q3 2026 총 매출은 $16.6B로 전년 수준을 유지했으나 코로나 제품을 제외한 매출은 7% 성장했다. 2029년까지 $6.7B의 누적 비용 절감을 추진하며 Metsera 인수를 통해 비만 치료제 시장 진입을 모색 중이다.', 'must_happen': ['2026년 비코로나 제품군 매출 7% 이상 연간 성장률 유지', '2026년 말까지 Metsera 연간 비용 시너지 $600M 창출 달성', '2027년까지 구조조정을 통한 누적 비용 절감 목표 순조로운 진행'], 'breaks_if': ['Vyndaqel 및 Eliquis 등 핵심 비코로나 품목 성장률 5% 미만 저하', '특허 만료에 따른 연간 매출 감소 규모가 $1.1B 초과 발생', 'Metsera GLP-1 파이프라인 임상 실패 및 파이프라인 자산 추가 손상 발생']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $62.6B(전년 대비 -1.6%), 순이익 $7.8B.\n영업활동 현금흐름 $11.7B · 보유 현금 $1.1B.'
