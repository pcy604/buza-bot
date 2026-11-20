# -*- coding: utf-8 -*-
"""LLY 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-12 (반영 공시 2026-10-29)
출처 코드
  ANNUAL = 10-K(2026-02-12 제출)
  EARN   = 10-Q 공시(2026-10-29)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-10-29'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-12'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-10-29)',
    'DECK': '10-Q 공시(2026-10-29)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'LLY', 'name': 'ELI LILLY & Co', 'exchange': 'NYSE',
           'sector': '제약·바이오', 'cik': 59478}

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
    'Mounjaro·Zepbound 중심 의약품 개발·판매',
    '2025년 매출 $65.2B 중 비만·당뇨약 비중 56%',
    '미국 3대 도매상이 유통의 상당 부분 차지'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 1876,
    'listed': 1984,
    'listing_type': '',
    'listing_date': '',
    'founders': 'Eli Lilly',
    'timeline': [
        ('1876', 'Colonel Eli Lilly가 인디애나주 인디애나폴리스에서 창업'),
        ('1901', '인디애나주에서 법인 설립 완료'),
        ('2022', '미국 인플레이션 감축법(IRA) 제정으로 약가 인하 영향 개시'),
        ('2023', '미국 HHS, Jardiance를 Medicare 약가 인하 대상 선정'),
        ('2024', 'Morphic Holding 인수 완료 및 개발 파이프라인 강화'),
        ('2025', '미국 정부와 약가 인하 및 비만 치료제 접근성 자발적 협약 체결', True),
        ('2026', '미국 HHS, Trulicity 및 Verzenio를 약가 인하 대상 지정', True)
    ],
    'employees': [('2025년 말', 50000)],
    'employee_src': '2025년 말 공식 집계',
    'chart_annotations': [
        (2022, 12, '1 +208% 변동'),
        (2007, 6, '2 -49% 변동')
    ],
    'note': '2025년 Mounjaro($23.0B) 및 Zepbound($13.5B)의 수요 폭증에 힘입어 전년 대비 45% 증가한 $65.2B의 매출을 기록함. 급증하는 인크레틴 제품 수요에 대응하기 위해 2025년 $7.8B 규모의 설비투자(Capex)를 집행하며 글로벌 생산 역량을 대폭 확장 중임. 한편 미국 인플레이션 감축법(IRA)에 따른 약가 설정 대상 선정 및 2025년 11월 미국 정부와의 약가 인하 자발적 협약 체결 등 규제 리스크 관리가 주요 과제로 부상함.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2022.12→2024.06', "pct": '+208%', "range": '$311.22→$960.02', "reason": '단일 계기 미확인 — 당뇨·비만치료제 매출 호조와 R&D 성과가 주가를 견인함.'},
    {"no": 2, "dir": 'down', "period": '2007.06→2008.12', "pct": '-49%', "range": '$57.35→$29.38', "reason": '단일 계기 미확인 — 지프렉사 관련 FDA 증언 및 법적 분쟁 등 리스크 부각됨.'}
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
    'ceo': {'name': 'David A Ricks', 'role': 'CEO', 'since': 2017,
            'bio': '보유 555,278주(2026-11-03 기준)'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Patrik Jonsson', "EVP · 사장 · LLY Int'l", ''),
        ('Daniel Skovronsky', 'EVP · CS · PO · Pres. LRL', ''),
        ('Anat Hakim', 'EVP · GC · 이사회 서기', ''),
        ('Lucas Montarce', 'EVP · CFO', ''),
        ('Edgardo Hernandez', 'EVP · Pres. · Mfg. Operations', '')
    ],
    'note': '경영진 다수가 회사 내 15~35년 장기 근무 경력을 보유하고 있으며, 2024~2025년에 걸쳐 심혈관대사, 면역, 뇌질환 등 핵심 질환 사업부 수장을 재편함.',
    'rsu_note': '',
}

SHARES = {
    'note': '연차보고서에서 전환사채·워런트 등 별도 희석요인은 확인되지 않음',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Human Pharmaceutical Products', 24397.0, 100)],
    'detail': [
        ('Human Pharmaceutical Products',
         '당뇨·비만, 항암, 면역, 뇌질환 치료제 등 인체 의약품의 연구개발, 제조, 마케팅 및 판매를 전담하는 단일 사업 부문임.', 24397.0, 0)
    ],
    'by_geo': [],
    'competitors': [],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q3 2026',
    'kpis': [
        ('매출', '$24.40B', '+39% YoY', 'up'),
        ('순이익', '$6.45B', '+16% YoY', 'up'),
        ('영업현금흐름', '$5.33B', '+220% YoY', 'up'),
        ('현금', '$4.88B', '-50% YoY', 'dn')
    ],
    'facts': [
        ('분기 매출', '인크레틴 처방 호조에 따른 총매출', '$24.4B'),
        ('분기 순이익', '매출총이익 개선 반영 분기 순이익', '$6.5B'),
        ('마운자로매출', '글로벌 시장 중심 주요 제품 매출', '$10.7B'),
        ('젭바운드매출', '미국 시장 비만치료제 주요 매출', '$5.4B'),
        ('매출총이익률', '생산원가 개선 및 믹스 효과 반영 비율', '83.9%'),
        ('연구개발비', '파이프라인 임상 투자 확대 비용', '$4.2B'),
        ('총부채 규모', '인수합병 관련 자금 조달 총부채', '$49.5B')
    ],
    'quotes': [
        ('경영진', 'Mounjaro, Zepbound, Foundayo가 올해 9개월 매출의 66%를 차지했고, 앞으로도 심대사 질환 제품군이 당사 사업과 매출 성장을 주도할 것입니다.', 'Mounjaro, Zepbound, and Foundayo accounted for 66 percent of our total revenue for the nine months ended September 30, 2026, and we expect cardiometabolic health products will continue to represent a significant and growing portion of our business, revenue, and prospects.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 0, 'growth_years': 2, 'competitors': 0, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '동급 경쟁사(시총 0.05~20배) 매칭 0곳 — 순위 비교 불가로 0점', '20%+ 성장 가능 연수': '2년 (2026 +41% · 과거 2023~2025 CAGR +38%) → 4점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 0곳 → 0점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 글로벌 탑티어, 신시장 CAGR.'

INCOME_NOTE = '2021년 $28.3B 수준이던 매출이 2025년 $65.2B로 급증하며 가파른 외형 성장 시현. 순이익 역시 2021년 $5.6B에서 2025년 $20.6B로 폭발적 증가 추세 기록.'
BALANCE_NOTE = '2021년 $3.8B이던 현금성 자산이 2022년 $2.1B로 감소했으나, 2025년에는 $7.3B로 대폭 확충되며 재무 유연성 강화. 이익 체력 확대로 자본 건전성 동반 개선.'
CASHFLOW = {
    'note': '영업현금흐름은 2021년 $7.4B에서 2023년 $4.2B로 일시적 저점을 기록했으나, 2025년 $16.8B로 급반등하며 현금 창출력 대폭 제고.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'pharmaceuticals 시장',
    'estimates': [],  # ⚠️ 자동생성: 뉴스 검색에서도 명확한 시장규모 숫자를 못 찾음
    'note': '' or '',

}

CHECKPOINTS = [
    ('2027년 12월', 'Medicare GLP-1 Bridge 할인 프로그램 종료', '종료 후 메디케어 정규 등재 및 본인 부담금 변화에 따른 비만 치료제 수용량 영향 확인', 'high'),
    ('2028년 5월', 'Verzenio 특허침해 소송(Cipla) 재판 개시', '제네릭 진입 차단으로 주요 항암제 매출 보호 여부 결정', 'mid'),
    ('2028년~', 'IRA 적용에 따른 Trulicity 및 Verzenio 강제 약가 인하 시점', '미국 정부 지정 약가 적용으로 당뇨/항암 핵심 제품 매출할인율 확대', 'high'),
    ('2028년 12월', '베링거인겔하임 Jardiance 제휴 계약 종료', '제휴 수익 배분 종료에 따른 영업이익률 및 커미션 매출 변동', 'mid'),
    ('2026년 10월', '분기 실적발표', 'EPS 컨센서스 $11.23 (범위 $10.37~$12.42) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $91.8B · EPS $35.35 (애널리스트 26명)', 'high')
]
CHECKPOINT_NOTE = '경구용 비만 치료제 Foundayo의 글로벌 적응증 승인과 2028년 IRA 약가 강제 인하 대응력이 투자논리의 핵심임.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': '글로벌 제약', 'chain': ['후보물질 발굴', '임상 개발', '품목 허가', '의약품 제조', '유통 및 판매'], 'position': 4, 'spans': [0, 1, 2, 3, 4], 'position_note': '후보물질 발굴부터 임상, 글로벌 제조 및 유통망까지 전 과정을 수직계열화하여 의약품 품질 관리 및 특허 기반 가격 결정력 확보함.', 'cycle': '비만·당뇨 치료제 수요 폭증에 따른 생산 능력 확충 국면이나, 정부 약가 규제 및 유통 채널 압박 증가함.', 'drivers': ['비만·당뇨 치료제 수요 및 임상 성과', '미국 IRA 등 정부 약가 인하 규제', '글로벌 의약품 생산 능력 및 공급망 확보']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '일라이 릴리는 Mounjaro와 Zepbound 등 GLP-1 계열 치료제를 앞세워 당뇨 및 비만 시장을 주도한다. 2026년 Q3 매출 $24.4B 중 인크레틴 제품군 비중이 급증하며 매출총이익률 83.9%를 달성하는 강력한 외형 성장을 보여준다. 향후 경구용 치료제 Foundayo 상용화와 자체 공장 증설을 통해 공급 확대를 추진 중이다.', 'must_happen': ['2026년 Q4 경구용 비만 치료제 Foundayo(orforglipron) 미국/유럽 적응증 추가 승인', '2027년 Q1 증설 중인 인크레틴 전용 생산 인프라의 상업 가동 착수', '2027년 Q4 메디케어(Medicare) 당국의 비만 치료제 장기 보험 등재 승인'], 'breaks_if': ['2026년 Q4 Mounjaro 및 Zepbound 관련 제네릭 ANDA 특허 소송 패소', '2027년 Q2 인크레틴 제품군 분기 매출 성장률 전년 대비 10% 이하로 급감', '2028년 IRA 법안 시행으로 Verzenio 및 Trulicity 약가 30% 이상 강제 인하']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $65.2B(전년 대비 +44.7%), 순이익 $20.6B.\n순이익은 FY2018에 흑자로 전환됨.\n영업활동 현금흐름 $16.8B · 보유 현금 $7.3B.'
