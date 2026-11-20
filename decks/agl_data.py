# -*- coding: utf-8 -*-
"""AGL 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-08 (반영 공시 2026-11-04)
출처 코드
  ANNUAL = 10-K(2026-02-25 제출)
  EARN   = 10-Q 공시(2026-11-04)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-11-04'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-08'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-11-04)',
    'DECK': '10-Q 공시(2026-11-04)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'AGL', 'name': 'agilon health, inc.', 'exchange': 'NYSE',
           'sector': '시니어 가치기반 의료 플랫폼', 'cik': 1831097}

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
CARRIED_OVER = {'LEADERSHIP.ceo.bio': '2026-10-18', 'LEADERSHIP.rsu_note': '2026-10-18', 'TAM.estimates': '2026-10-18', 'TAM.note': '2026-10-18'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    '1차 진료의 중심 VBC 플랫폼 운영함',
    '28개 앵커그룹 및 30개 지역 진출',
    'MA 회원 51.1만 명 및 FFS 11.4만 명 관리'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2016,
    'listed': 2021,
    'listing_type': 'IPO',
    'listing_date': '2021-02-10',
    'founders': '',
    'timeline': [
        ('2016', 'agilon health 설립'),
        ('2017', '첫 번째 앵커 의사그룹과 파트너십 구축'),
        ('2023', 'CMS ACO REACH 모델 참여 개시'),
        ('2025-07', 'Steven Sell CEO 사임 및 최고경영자 탐색 착수', True),
        ('2025-11', '주가 $1.00 미만으로 NYSE 상장요건 미달 통지 수령', True),
        ('2026-03', 'NYSE 상장요건 회복을 위한 주식병합 승인 주주총회 개최 예정', True)
    ],
    'employees': [('FY2025 10-K (2025년 12월 31일)', 856)],
    'employee_src': 'FY2025 10-K (2025년 12월 31일) 공식 집계',
    'chart_annotations': [
        (2026, 3, '1 +934% 변동'),
        (2025, 4, '2 -81% 변동')
    ],
    'note': '2016년 설립 후 2017년 첫 앵커 의사그룹 파트너십을 구축하며 2025년 말 기준 30개 지역, 28개 앵커 그룹, 약 51.1만 명의 MA 회원 및 11.4만 명의 메디케어 FFS 수혜자를 관리하는 규모로 확장함.\n2025년 11월 30일 평균 주가 $1.00 미만으로 NYSE 상장요건 미달 통지를 받아 2026년 3월 주주총회를 통해 주식병합(Reverse Stock Split) 승인을 추진 중임.\n2025년 7월 Steven Sell CEO 사임 후 후임 선임 절차가 진행 중이며 ACO REACH 모델의 2027년 LEAD 모델 전환 등 사업 환경 변화에 대응 중임.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2026.03→2026.06', "pct": '+934%', "range": '$10.74→$111.01', "reason": '1분기 어닝 서프라이즈 실적 발표, 신임 CEO 선임 소식이 호재로 작용함.'},
    {"no": 2, "dir": 'down', "period": '2025.04→2025.10', "pct": '-81%', "range": '$104.00→$19.92', "reason": '단일 계기 미확인 — 주가 급락에 따른 로펌 조사 및 투자자 경보 위주로 보도됨.'}
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
    'ceo': {'name': "Timothy Patrick O'Rourke", 'role': 'CEO', 'since': 0,
            'bio': '2025년 7월 29일 최고경영자(CEO), 사장 및 이사회 이사직에서 공식 사임함. 원문상 구체적 취임 연도 및 이전 상세 이력은 미기재되었으며 사임 시 퇴직 패키지가 지급됨. 현재 공석 상태로 이사회에서 후임 CEO 선임 절차를 진행 중임.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Denise Zamore', 'CLO', ''),
        ('Jeffrey A. Schwaneke', 'CFO', ''),
        ('Timothy Gertsch', 'CAO', ''),
        ('Girish Venkatachaliah', 'CTO', ''),
        ('Benjamin Shaker', 'Chief Markets Officer', '')
    ],
    'note': '2025년 7월 Steven Sell CEO 사임 이후 후임 CEO 선임 절차가 진행 중이며 경영진 리더십 교체 국면에 있음.',
    'rsu_note': '직원 인센티브로 미리 정해진 재무 목표 달성 성과에 따라 부여되는 스톡옵션 및 제한적 주식 단위(RSU) 제공함.',
}

SHARES = {
    'note': 'NYSE 계속상장 요건 충족을 위해 2026년 3월 주주총회에서 주식병합(Reverse Stock Split) 승인을 추진 중임.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('글로벌 캡itation 및 가치기반 의료 사업', 1519.5, 100)],
    'detail': [
        ('글로벌 캡itation 및 가치기반 의료 사업',
         'RBE를 통해 MA 보험사와 PMPM 계약을 체결하고 앵커 의사그룹과 협력하여 총 의료비를 관리함.', 1519.5, 0)
    ],
    'by_geo': [],
    'competitors': [],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 2026',
    'kpis': [
        ('매출', '$1.52B', '+6% YoY', 'up'),
        ('영업이익', '$24.1M', '+118% YoY', 'up'),
        ('순이익', '$34.9M', '+132% YoY', 'up'),
        ('영업현금흐름', '$23.7M', '+174% YoY', 'up'),
        ('현금', '$174.4M', '+2% YoY', 'up')
    ],
    'facts': [
        ('총매출', '3분기 연결 총영업 매출액', '$1,519.5M'),
        ('의료매출', '메디케어 어드밴티지 캡티션 수입', '$1,517.8M'),
        ('순이익', '3분기 연결 당기순이익', '$34.9M'),
        ('조정EBITDA', '일회성 항목 제외 영업이익', '$63.7M'),
        ('의료손해율', '의료비용 대 매출 비율', '88.5%'),
        ('MA회원수', '플랫폼 등재 메디케어 회원 수', '453,600명'),
        ('기말현금', '현금 및 제한 현금성 자산', '$246.4M')
    ],
    'quotes': [
        ('경영진', '우리는 주치의가 지역 사회의 의료 품질과 비용, 환자 경험에서 의미 있는 변화를 이끌어낼 수 있는 가장 좋은 위치에 있다고 믿습니다.', 'We believe that PCPs, with their intimate patient-physician relationships, are best positioned to drive meaningful change in quality, cost, and patient experience when provided with the right infrastructure and payment model.'),
        ('경영진', '현재 확보된 데이터에 따르면 2026년 3분기 의료비용 추세는 당사의 기존 예상치에 부합하는 수준을 유지하고 있습니다.', 'Based on our current available data, cost trends for the three months ended September 30, 2026 remained in line with our expectations.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 0, 'growth_years': 0, 'competitors': 0, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '동급 경쟁사(시총 0.05~20배) 매칭 0곳 — 순위 비교 불가로 0점', '20%+ 성장 가능 연수': '컨센서스·실적 어디서도 20%+ 성장 근거 없음 → 0점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 0곳 → 0점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 글로벌 탑티어, 성장 가능 연수, 신시장 CAGR.'

INCOME_NOTE = '매출은 2021년 $1.5B에서 2024년 $6.1B까지 급격히 성장했으나 2025년 $5.9B로 소폭 감소함. 순손실은 2022년 -$106.9M로 축소된 이후 2025년 -$391.3M까지 다시 확대되며 5년 연속 적자 구조 지속 중.'
BALANCE_NOTE = '현금 자산은 2021년 $1.0B에서 2023년 $107.6M로 급감함. 2024년 $188.2M, 2025년 $173.7M 수준을 유지 중이나 지속된 순 손실로 인해 초기의 풍부한 현금 기반이 크게 약화됨.'
CASHFLOW = {
    'note': '영업현금흐름은 2021년 -$148.2M에서 2025년 -$105.8M를 기록하며 5년 연속 음수(-) 상태 지속됨. 2024년 -$57.8M 수준까지 유출 폭이 줄었으나 2025년 다시 현금 유출이 확대되며 현금 창출력 부친 지속 중.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'value based healthcare 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('Yahoo Finance', 1.5, 2030),
        ('MarketsandMarkets', 42.62, 2031)
    ],
    'note': '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2026년 Q4', '증권 집단소송(Consolidated Securities Matter) 진행 및 이사회 관련 법원 판단', '소송 결과에 따른 대규모 배상금 발생 위험 및 법적 불확실성 해소 여부 확인 필요', 'high'),
    ('2026년 Q4~', '일일 최소 현금 잔액 $50.0M 유지 및 신용공여 약정(Credit Facility) 준수', '약정 위반 시 대출금 즉시 상환 요구 발생으로 유동성 위험 직면', 'high'),
    ('2026년 Q4~', '주요 임원진의 Rule 10b5-1 매도 계획 실행에 따른 물량 소화', '경영진 지분 매각에 따른 주가 오버행 및 투자 심리 영향 점검', 'mid'),
    ('2027년 Q4~', '수익성 저해 지불자(Payor) 계약 재협상 및 비수익 시장 철수 효과', '회원 수 감소에도 불구하고 의료 손해율(MSER) 80%대 유지 여부 검증', 'high'),
    ('2026년 11월', '분기 실적발표', 'EPS 컨센서스 $-2.98 (범위 $-4.36~$-2.11) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $5.8B · EPS $-1.79 (애널리스트 11명)', 'high')
]
CHECKPOINT_NOTE = '비수익성 지불자 계약 구조조정을 통한 MSER 80%대 안착과 일일 최소 현금 잔액 약정 준수가 재무 정상화의 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '가치기반 헬스케어', 'chain': ['정부(CMS)', '보험사(MA)', '플랫폼/RBE', '앵커 의사그룹', '환자(Medicare)'], 'position': 2, 'spans': [2], 'position_note': '보험사와의 글로벌 캡itation 계약 및 의사그룹과의 20년 장기 계약을 체결하여 가치사슬 내 총의료비 관리 및 절감액 배분 주도권을 보유함.', 'cycle': 'CMS의 메디케어 어드밴티지(MA) 요율 조정 및 ACO REACH 모델의 2027년 LEAD 모델 전환 등 규제 개편 국면임.', 'drivers': ['CMS 메디케어 벤치마크 요율 및 위험조정지수(RAF)', 'MA 가입자 수 및 앵커 의사그룹 진출 확대', '의료 서비스 이용률 및 의료비 지출 추이']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '동사는 1차 진료 의사 그룹과 파트너십을 맺고 메디케어 어드밴티지 가입자의 의료비를 포괄 관리하는 플랫폼을 운영함. 2026년 3분기 MA 회원 수가 453,600명으로 전년 대비 10% 감소했으나 비수익 계약 철수로 의료손해율(MSER)을 88.5%로 대폭 개선함. 3분기 조정 EBITDA $63.7M 및 당기순이익 $34.9M를 기록하며 적자 구조에서 흑자 전환함.', 'must_happen': ['2026년 Q4 의료서비스 비용비율(MSER) 90.0% 이하 유지', '2026년 Q4 영업활동 현금흐름 연간 누적 플러스(+) 달성', '2027년 Q1 메디케어 어드밴티지 PMPM 캡티션 단가 상승세 유지'], 'breaks_if': ['2026년 Q4 일일 최소 현금 잔액이 $50.0M 미만으로 하락하여 대출 약정 위반 발생', '2026년 Q4 MSER이 100.0%를 다시 초과하여 영업 적자 전환', '진행 중인 증권 집단소송에서 패소하여 대규모 손해배상금 부과']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $5.9B(전년 대비 -2.1%), 영업이익 $-463.2M(OPM -7.8%), 순이익 $-391.3M.\n영업활동 현금흐름 $-105.8M · 보유 현금 $173.7M.'
