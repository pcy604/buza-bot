# -*- coding: utf-8 -*-
"""MRNA 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, 2026-10-26 (반영 공시 2026-07-31)
출처 코드
  ANNUAL = 10-K(2026-02-20 제출)
  EARN   = 10-Q 공시(2026-07-31)
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = '2026-07-31'          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = '2026-10-26'       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {
    'PR': '10-Q 공시(2026-07-31)',
    'DECK': '10-Q 공시(2026-07-31)',
    'YF': 'Yahoo Finance chart API',
}

COMPANY = {'ticker': 'MRNA', 'name': 'Moderna, Inc.', 'exchange': 'Nasdaq',
           'sector': 'mRNA 백신·치료제', 'cik': 1682852}

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
CARRIED_OVER = {'LEADERSHIP.ceo.bio': '2026-09-26', 'SHARES.note': '2026-09-26', 'TAM.note': '2026-09-26'}

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    'Spikevax·mRESVIA로 FY2025 매출 $1.9B 달성',
    'U.S. 소매 채널 주력 코로나 백신 mNEXSPIKE 보유',
    '감염병·항암·희귀질환 35개 파이프라인 보유'
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {
    'founded': 2009,
    'listed': 2018,
    'listing_type': 'IPO',
    'listing_date': '',
    'founders': 'Flagship Pioneering',
    'timeline': [
        ('2009', 'Flagship Pioneering에 의해 Newco LS18으로 설립', True),
        ('2016', 'Merck와 맞춤형 암 백신(intismeran) 공동개발 계약 체결'),
        ('2018', 'Moderna, Inc.로 사명 변경 및 나스닥 상장'),
        ('2020', '코로나19 백신(Spikevax) 개발 및 FDA 긴급사용승인 획득', True),
        ('2024', 'RSV 백신 mRESVIA FDA 승인 획득'),
        ('2025', '차세대 코로나 백신 mNEXSPIKE FDA 승인 및 U.S. 출시', True),
        ('2026', 'Recordati와 희귀질환 치료제(mRNA-3927) 상업화 협력 체결')
    ],
    'employees': [('2025년 12월 31일', 4700)],
    'employee_src': '2025년 12월 31일 공식 집계',
    'chart_annotations': [
        (2026, 4, '1 +338% 변동'),
        (2024, 5, '2 -70% 변동')
    ],
    'note': '코로나19 팬데믹 기간 Spikevax 상업화 성공으로 급성장했으나, 팬데믹 종료 후 백신 수요 급감으로 매출 조정기를 겪음. FY2025 매출 $1.9B을 기록하고 영업손실이 지속되는 가운데 구조적 비용 절감 및 현금 손익분기 달성을 추진 중임. 차세대 코로나 백신 mNEXSPIKE, RSV 백신 mRESVIA 및 머크(Merck) 공동개발 암백신 intismeran autogene 등 후기 파이프라인 상업화에 집중하고 있음.',
}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {"no": 1, "dir": 'up', "period": '2026.04→2026.10', "pct": '+338%', "range": '$45.37→$198.85', "reason": 'UAE 투자 협상과 암 백신 기대감 및 나스닥 100 지수 편입으로 급등함'},
    {"no": 2, "dir": 'down', "period": '2024.05→2024.11', "pct": '-70%', "range": '$142.55→$43.06', "reason": '유럽 판매 부진과 미국 백신 시장 악화로 가이던스를 하향 조정함.'}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {
    'names': {'PFE': 'PFIZER INC', 'BNTX': 'BioNTech SE', 'SNY': 'Sanofi'},
    'ciks': {'PFE': 78003, 'BNTX': 1776985, 'SNY': 1121404},
}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = ''

LEADERSHIP = {
    'ceo': {'name': 'Stephane Bancel', 'role': 'CEO', 'since': 2011,
            'bio': '보유 6,440,260주(2026-08-06 기준)'},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        ('Stephen Hoge', '사장', ''),
        ('Soria Ester Banque', 'Chief Commercial Officer', ''),
        ('James M Mock', 'CFO', ''),
        ('Shannon Thyme Klinger', 'CLO', '')
    ],
    'note': '전 임직원 대상 주식보상(RSU/스톡옵션) 제도를 운영하여 주주 가치와 성과를 연계함.',
    'rsu_note': '',
}

SHARES = {
    'note': '연차보고서에서 전환사채·워런트 등 별도 희석요인은 확인되지 않음',
    'dilution': [],
    'src': SRC['PR'],
}

SEGMENTS = {
    'by_line': [('감염병 백신 (Infectious Disease)', 145.0, 100.0), ('항암 치료제 (Oncology)', None, None), ('희귀질환 치료제 (Rare Disease)', None, None)],
    'detail': [
        ('감염병 백신 (Infectious Disease)',
         'Spikevax, mNEXSPIKE, mRESVIA 등 상업화 백신 및 호흡기·잠복 바이러스 백신 개발.', 145.0, 0),
        ('항암 치료제 (Oncology)',
         '머크 공동개발 intismeran autogene 및 암 항원 치료제(mRNA-4359) 임상 진행 중.', None, 0),
        ('희귀질환 치료제 (Rare Disease)',
         '프로피온산혈증(mRNA-3927) 및 메틸말론산혈증(mRNA-3705) 치료제 임상 진행 중.', None, 0)
    ],
    'by_geo': [],
    'competitors': ['Pfizer', 'BioNTech', 'Sanofi', 'Novavax', 'GlaxoSmithKline'],
    'note': '부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — 부문별 전년동기 비교는 공시에 없어 미표시',
    'src': SRC['DECK'],
}

RESULTS = {
    'period': 'Q2 2026',
    'kpis': [
        ('매출', '$145.0M', '+2% YoY', 'up'),
        ('영업이익', '$-815.0M', '+10% YoY', 'up'),
        ('순이익', '$-782.0M', '+5% YoY', 'up'),
        ('영업현금흐름', '$-630.0M', '+39% YoY', 'up'),
        ('현금', '$1.72B', '+35% YoY', 'up')
    ],
    'facts': [
        ('총 매출', '전년 동기 대비 증가한', '$145.0M'),
        ('제품 매출', '코로나 및 RSV 백신 판매를 포함한', '$94.0M'),
        ('영업 손실', '연구개발 및 판관비 반영에 따른', '$815.0M'),
        ('순손실', '당기 총비용 반영에 따른', '$782.0M'),
        ('현금 및 투자', '현금·현금성 자산과 단기·장기 투자금 합계', '$6.91B'),
        ('연구개발비', '임상 프로그램 및 파이프라인 집행 비용', '$651.0M'),
        ('판관비', '비용 통제 기조가 반영된 운영비', '$216.0M')
    ],
    'quotes': [
        
    ],
    'src': SRC['PR'],
}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {'top_tier': 5, 'growth_years': 0, 'competitors': 5, 'governance': 0, 'market_cagr': None}
CANSLIM_N_DETAIL = {'글로벌 탑티어': '10-K가 지목한 동급 경쟁사 3곳 중 시총 3위($79.4B) → 5점', '20%+ 성장 가능 연수': '컨센서스·실적 어디서도 20%+ 성장 근거 없음 → 0점', '경쟁기업 수': '10-K Competition 절에 언급된 경쟁사 5곳 → -2점', '지배구조 개편': '최근 중대한 지배구조 개편 근거 없음 → 0점', 'New Market CAGR': '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'}
CANSLIM_NOTE = 'N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함. 근거를 못 찾아 0점 처리한 항목: 성장 가능 연수, 신시장 CAGR.'

INCOME_NOTE = '2021년 $18.5B에 달했던 매출이 백신 수요 급감으로 2025년 $1.9B까지 급감. 순이익 역시 2021년 $12.2B 흑자에서 2023년 -$,4.7B 적자로 전환된 이후 2024년 -$3.6B, 2025년 -$2.8B로 적자 지속.'
BALANCE_NOTE = '보유 현금은 2021년 $6.8B에서 2024년 $1.9B까지 감소했으나, 2025년 들어 $2.6B로 일부 회복. 대규모 적자 장기화로 자본 건전성 하방 압력 지속.'
CASHFLOW = {
    'note': '2021년 $13.6B를 기록했던 영업현금흐름이 2023년 -$3.1B로 마이너스 전환. 이후 2024년 -$3.0B, 2025년 -$1.8B로 영업활동 현금 유출 지속.',
    'src': 'SEC XBRL companyfacts',
}

TAM = {
    'label': 'mRNA therapeutics 시장',
    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님
        ('BioSpace', 83.49, 2035),
        ('Yahoo Finance UK', 20.99, 2035),
        ('Vision Research Reports', 45.04, 2034)
    ],
    'note': '노로바이러스의 글로벌 경제적 영향은 연간 $60B로 추정됨 (출처: 원문).' or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',

}

CHECKPOINTS = [
    ('2026년 Q4', 'mRNA-4157 3상 흑색종 데이터 발표', '온콜로지 파이프라인 가치 입증 여부 판가름', 'high'),
    ('2026년 Q4', 'mRNA-3927 PA 치료제 등록 연구 데이터 확인', '희귀질환 상업화 역량 검증', 'mid'),
    ('2026년 Q4', '노로바이러스 추가 코호트 모집 완료 및 후속 데이터', '백신 파이프라인 리스크 해소 여부 확인', 'mid'),
    ('2026년 11월', '분기 실적발표', 'EPS 컨센서스 $-1.35 (범위 $-3.28~$-0.80) 대비 실제치 확인', 'high'),
    ('FY2026', '연간 컨센서스 달성 여부', '매출 $2.1B · EPS $-8.49 (애널리스트 21명)', 'high'),
    ('FY2027', '차년 성장 전망', '매출 $2.4B(+16%) · EPS $-4.89', 'mid')
]
CHECKPOINT_NOTE = 'mRNA-1010 허가와 흑색종 3상 데이터가 향후 주가 방향성을 결정함.'

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {'industry': 'mRNA 바이오의약품', 'chain': ['mRNA·LNP 연구', '임상·비임상 개발', '원제·완제 제조', '유통·공급망', '정부·의료기관 고객'], 'position': 2, 'spans': [0, 1, 2, 3], 'position_note': 'LNP 및 mRNA 관련 핵심 특허 보유와 자체 생산 시설(MTC 등) 수직계열화로 의약품 개발·상업화의 병목을 통제함.', 'cycle': '코로나19 백신 수요 감소에 따른 매출 조정기이며, 후기 임상 파이프라인 다변화를 통한 재도약 준비 국면.', 'drivers': ['호흡기 백신 수요 및 정부 구매 계약', '항암·희귀질환 후기 임상 성과', '생산 플랫폼 효율화 및 비용 절감']}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {'story': '모더나는 메신저 리보핵산(mRNA) 플랫폼 기술을 기반으로 호흡기 백신, 항암 백신, 희귀질환 치료제를 개발하는 바이오 기업이다. 코로나19 엔데믹 전환에 따른 백신 매출 감소를 극복하기 위해 독감, RSV, 복합 백신 및 항암 치료제로 포트폴리오를 다변화하고 있다. 최근 아르부투스 특허 소송 합의금 등 일회성 비용이 반영되었으나, 비용 효율화와 신규 파이프라인 상업화를 추진 중이다.', 'must_happen': ['2026년 8월 mRNA-1010 최종 승인 획득', '2026년 Q4 intismeran 3상 흑색종 데이터 공개', '2026년 현금 비용 가이던스 $4.0B 달성'], 'breaks_if': ['mRNA-1010 승인 거절 또는 지연', 'intismeran 3상 흑색종 유효성 입증 실패', '현금 소모 가속화로 유동성 위기 발생']}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \n으로 줄바꿈.
SUMMARY = 'FY2025 매출 $1.9B(전년 대비 -39.9%), 영업이익 $-3.1B(OPM -158.1%), 순이익 $-2.8B.\n영업이익은 FY2023에 적자로 돌아섬.\n영업활동 현금흐름 $-1.9B · 보유 현금 $2.6B.'
