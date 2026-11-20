# -*- coding: utf-8 -*-
"""CRWV 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-11-09 (반영 공시 2026-08-12)
출처 코드
  ANNUAL = 10-K(2026-03-02 제출)
  EARN   = 10-Q 공시(2026-08-12)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-08-12'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-11-09'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-08-12)',
    'DECK': '10-Q 공시(2026-08-12)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'CRWV', 'name': 'CoreWeave, Inc.', 'exchange': 'Nasdaq',
           'sector': 'AI 클라우드 인프라', 'cik': 1769628}

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
CARRIED_OVER = {'TAM.note': '2026-10-19'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'NVIDIA GPU 기반 AI 전용 클라우드 인프라 및 소프트웨어 제공함',
    '마이크로소프트 등 대형 고객과 장기 확정 계약(take-or-pay) 체결함',
    '2025년 기준 최대 고객사(Microsoft) 매출 비중 67% 기록함'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2017,
    'listed': 2025,
    'listing_type': 'IPO',
    'listing_date': '',
    'founders': 'Michael Intrator, Brian Venturo, Brannin McBee',
    'timeline': [
        ('2017', 'CoreWeave 설립'),
        ('2020', 'CoreWeave Cloud 플랫폼 공식 출시', True),
        ('2025', 'Nasdaq 상장(IPO) 완료', True),
        ('2025', 'Weights & Biases, OpenPipe, Marimo, Monolith AI 인수', True),
        ('2025', '뉴저지 케닐워스 데이터센터 캠퍼스 개발 합작법인(JV) 설립'),
        ('2025', 'OpenAI와 최대 $6.5B 규모 장기 서비스 계약 체결', True),
        ('2025', 'Meta와 최대 $14.2B 규모 장기 서비스 계약 체결', True),
        ('2026', 'NVIDIA와 글로벌 AI 확산 위한 협력 프레임워크 발표')
    ],
    'employees': [('2025년 12월 31일', 2189)],
    'employee_src': '2025년 12월 31일 공식 집계',
    'chart_annotations': [
        (2025, 3, '1 +340% 변동'),
        (2026, 5, '2 -58% 변동')
    ],
    'note': '2017년 설립 후 암호화폐 채굴 사업에서 AI 전용 클라우드 인프라 기업으로 전환함. NVIDIA 최신 GPU 수급과 전력 용량을 빠르게 확보하며 매출이 2023년 $229.0M에서 2025년 $5.1B로 성장함. Microsoft, Meta, OpenAI 등과 대규모 장기 계약을 체결하여 2025년 말 잔여이행의무(RPO) $60.7B를 달성함. 데이터센터 및 GPU 설비 투자 확대 여파로 2025년 $1.2B 순손실을 기록하며 대규모 자본 지출 국면에 위치함.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2025.03→2025.06', "pct": '+340%', "range": '$37.08→$163.06', "reason": '단일 계기 미확인 — 1분기 호실적, 대형 계약 및 구글·OpenAI 공급 호재가 반영됨.'},
    {"no": 2, "dir": 'down', "period": '2026.05→2026.11', "pct": '-58%', "range": '$109.53→$46.40', "reason": '마이크로소프트 설비투자 하회, AI 우려 및 데이터센터 악재로 급락함.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'ORCL': 'ORACLE CORP'},
    'ciks': {'ORCL': 1341439},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Michael N Intrator', 'role': 'CEO', 'since': 2017,
            'bio': 'CoreWeave의 공동 창업자이자 CEO, 사장 및 이사회 의장임. 2017년 회사를 창업한 이후 대규모 가속 컴퓨팅 인프라 확장 및 성장 전략을 총괄함.'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Sachin Jain', 'COO', ''),
        ('Brannin McBee', 'Chief Development Officer', ''),
        ('Chen Goldberg', 'EVP · Product · Engineering', ''),
        ('Jeff Baker', 'Principal Accounting Officer', ''),
        ('Nitin Agrawal', 'CFO', '')
    ],
    'note': '공동 창업자 3인(Michael Intrator, Brian Venturo, Brannin McBee)이 각각 CEO, CSO, CDO 직책을 맡아 사업 및 기술 전략을 주도함.',
    'rsu_note': '',
}

SHARES = {
    'note': '임직원 주식보상(RSU, RSA, 스톡옵션) 및 인프라 투자 목적의 자산 담보 부채·전환사채 조달에 따른 잠재적 주식 희석 위험 존재함.',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('Infrastructure Services', None, None), ('Managed Software Services', None, None), ('Application Software Services', None, None)],
    'detail': [
        ('Infrastructure Services',
         'GPU 클러스터, 고밀도 데이터센터, 고속 네트워크 및 전용 저장소 인프라 제공함.', None, 0),
        ('Managed Software Services',
         'CoreWeave Mission Control 및 SUNK 등 오케스트레이션, 모니터링 소프트웨어 제공함.', None, 0),
        ('Application Software Services',
         'Weights & Biases 등 AI 모델·에이전트 개발, 평가, 튜닝 소프트웨어 도구 제공함.', None, 0)
    ],
    'by_geo': [],
    'competitors': ['Amazon', 'Google', 'Microsoft', 'Oracle'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q2 2026',
    'kpis': [
        ('매출', '$2.58B', '+112% YoY', 'up'),
        ('영업이익', '$-49.0M', '-358% YoY', 'dn'),
        ('순이익', '$-626.0M', '-116% YoY', 'dn'),
        ('영업현금흐름', '$2.98B', '+4792% YoY', 'up'),
        ('현금', '$5.52B', '+379% YoY', 'up')
    ],
    'facts': [
        ('매출액', '기존 및 신규 고객 계약 확장 달성', '$2.58B'),
        ('수주잔고', '미충족 잔여 이행 의무 총액', '$103.7B'),
        ('영업손실', '인프라 감가상각 및 임차료 증가', '$49.0M'),
        ('순손실', '이자비용 및 인프라 투자 지속', '$626.0M'),
        ('현금성자산', '기말 현금 및 현금성 자산 보유액', '$5.52B'),
        ('영업현금흐름', '6개월 누적 영업활동 현금흐름', '$3.66B'),
        ('연간매출목표', '상향 조정 연간 매출 가이던스', '$12.4B~$13.2B'),
        ('연간CapEx', '상향 조정 연간 자본지출 가이던스', '$35.0B~$39.0B')
    ],
    'quotes': [
        ('CEO', 'CoreWeave는 회사 역사상 그 어느 때보다 강력한 모멘텀을 가지고 하반기에 진입하고 있습니다.', 'CoreWeave enters the second half of the year with more momentum than at any point in our history.')
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 3, 'growth_years': 3, 'competitors': 4, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 1곳 중 시총 2위($25.6B) → 3점', '20%+ 성장 가능 연수': '3년 (2026 +151% · 2027 +105% · 과거 2023~2025 CAGR +373%) → 6점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 4곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 신시장 CAGR.'

INCOME_NOTE = '매출액이 2023년 $229.0M에서 2024년 $1.9B, 2025년 $5.1B로 급격한 외형 성장을 달성함. 반면 순손실은 2023년 -$594.0M에서 2024년 -$863.0M, 2025년 -$1.2B로 적자 폭이 확대되며 수익성 확보 과제 지속됨.'
BALANCE_NOTE = '현금 보유액이 2023년 $217.0M에서 2024년 $1.4B, 2025년 $3.1B로 크게 증대됨. 적자 누적에도 불구하고 가용 현금을 대폭 확충하며 AI 인프라 확장을 위한 유동성 기반을 강화하는 모습임.'
CASHFLOW = {
    'note': '영업현금흐름이 2023년 $1.8B에서 2024년 $2.7B, 2025년 $3.1B로 우상향 추세를 유지함. 순손실 지속 상태에서도 영업 활동을 통한 현금 창출력은 고성장을 이어나가며 사업 운영을 뒷받침함.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'AI cloud infrastructure 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('Yahoo Finance', 923.05, 2035),
        ('IDC', 1000.0, 2029),
        ('Precedence Research', 518.26, 2035)
    ],
    'note': '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2026년 Q4', '2026년 연간 매출 가이던스 달성 여부', '상향된 매출 가이던스($12.4B~$13.2B) 달성 시 외형 성장의 정당성이 확보되나 미달 시 고성장 프리미엄 훼손', 'high'),
    ('2026년 Q4', '2026년 연간 CapEx 집행 완수 및 데이터센터 인도', '$35.0B~$39.0B CapEx 집행을 통한 전력 및 GPU 인프라 전개 성공 시 수주 이행 가속화, 지연 시 고객 이탈 및 래비뉴 차질 발생', 'high'),
    ('2026년 Q4', '매니지드 인퍼런스 ARR $0.25B 돌파 여부', 'ARR $0.25B 달성 성공 시 소프트웨어 및 인퍼런스 중심의 수익원 다각화 검증', 'mid'),
    ('2026년~', '대규모 차입금 및 채권 이자비용 통제 능력', '부채 조달을 통한 인프라 확장이 고금리 이자비용 부담으로 이어져 영업손실 폭을 확대하는지 여부 확인 필요', 'high'),
    ('2026년 11월', '분기 실적발표', 'EPS 컨센서스 $-1.21 (범위 $-1.62~$-0.21) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $12.9B · EPS $-5.19 (애널리스트 23명)', 'high')
]
CHECKPOINT_NOTE = '대규모 CapEx 집행을 통한 2026년 연간 매출 가이던스 달성과 이자비용 통제 여부가 핵심 투자논리를 구성함.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': 'AI 클라우드 인프라', 'chain': ['전력·용지', 'GPU·반도체', '데이터센터', '클라우드 셋업', '오케스트레이션', 'AI 소프트웨어'], 'position': 3, 'spans': [2, 3, 4, 5], 'position_note': 'NVIDIA GPU 인프라와 자체 오케스트레이션 소프트웨어를 수직 통합하여 초고성능 AI 연산 병목을 해결함.', 'cycle': 'AI 모델 대형화 및 추론 수요 급증으로 전력 및 가속 컴퓨팅 인프라의 공급 부족 국면 지속 중.', 'drivers': ['AI 모델 학습·추론 수요', 'GPU 및 고밀도 전력 수급', '데이터센터 확장 속도']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': 'CoreWeave는 AI 전용 클라우드 인프라와 소프트웨어를 빅테크 및 AI 연구소에 대여하여 돈을 번다. Q2 2026 매출은 전년 동기 대비 112% 증가한 $2.58B를 기록하며 전력 확보와 하드웨어 배치를 급격히 늘리고 있다. 7월 25% 가격 인상과 매니지드 인퍼런스 서비스 확대로 기여 마진과 수익 구조 개편을 추진 중이다.', 'must_happen': ['2026년 Q4까지 연간 매출 가이던스 하단인 $12.4B 이상 달성', '2026년 Q4까지 매니지드 인퍼런스 ARR $0.25B 이상 달성', '2026년 Q4까지 $35.0B~$39.0B 자본지출을 집행하여 계획된 데이터센터 증설 완료'], 'breaks_if': ['데이터센터 공급 지연으로 수주잔고($103.7B)의 매출 전환이 무산되는 경우', '막대한 부채에 따른 이자비용 증가로 영업손실 및 순손실 폭이 급격히 확대되는 경우', '25% 가격 인상 이후 고객 이탈이 발생하여 마진 개선 목표가 좌절되는 경우']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $5.1B(전년 대비 +167.9%), 영업이익 $-46.0M(OPM -0.9%), 순이익 $-1.2B.\n영업이익은 FY2025에 적자로 돌아섬.\n영업활동 현금흐름 $3.1B · 보유 현금 $3.1B.'
