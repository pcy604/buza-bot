# -*- coding: utf-8 -*-
"""신규 종목 데이터 파일 자동 초안 생성기.

    python autogen.py TICKER [PEER1=CIK1 PEER2=CIK2 ...]

satl16_data.py/pltr_data.py/tsla_data.py와 같은 스키마의 `{ticker}_data.py`를
자동으로 써서 decks/ 밑에 저장한다. 이후 build.py는 손으로 쓴 데이터 파일과 완전히
동일하게 취급 — 자동생성이라고 렌더러가 다르게 굴지 않는다.

설계 원칙(왜 완전 zero-touch가 아닌가):
  - 가격·재무제표·기술적지표·퀀트·기관/내부자 지분은 이미 100% 라이브 자동 계산
    (live.py/sources.py, XBRL·Yahoo 기반) — 여기서 손댈 필요 없음.
  - 서사(연혁·CEO·사업부문 설명·최근실적 코멘트·체크포인트)만 LLM이 채우는데,
    반드시 실제 공시원문(10-K/20-F, 최신 실적 8-K, 어닝콜)에 있는 내용만 쓰게 강제한다
    (ir.py의 PROFILE_PROMPT·TRANSCRIPT_PROMPT와 같은 "원문에 없으면 생성 금지" 규율).
  - TAM(시장규모)은 예외 — Grand View Research 같은 시장조사 수치는 유료 검색 그라운딩
    없이는 안전하게 자동화 불가(추정치를 지어내면 #6 요구사항 정면 위반). 연차보고서
    자체가 언급한 시장규모만 쓰고, 없으면 빈 배열 + "사용자 보충 필요" 노트로 정직하게
    비워둔다 — 없는 걸 있는 척하지 않는 게 있는 걸 못 채우는 것보다 낫다.
  - peers(경쟁사 티커→CIK)는 판단이 필요해 자동 선택 안 함 — 10-K "Competition"
    절에서 언급된 이름만 후보로 뽑아 출력, 실제 등록은 사용자가 build.py에 확정.
"""
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ir  # noqa: E402
import analyzer  # noqa: E402
import sources as S  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent


def _resolve_competitor_ciks(names: list, target_mcap, max_n=3):
    """10-K가 실제로 이름을 언급한 경쟁사를 SEC 티커로 매칭 + 시총으로 필터.

    이름만 보고 자동 등록하면 Amazon·Google·IBM처럼 "우리 칩이 그 클라우드 위에서
    도는" 플랫폼 대기업이 먼저 걸려(정확 매칭이 더 쉬움) 정작 비교 의미 있는
    동급 소형 경쟁사(예: Rigetti·D-Wave)가 밀려난다 — 시총이 타깃 종목과 비슷한
    자릿수(0.05~20배)인 후보만 남겨 "판단"을 시총 비교라는 결정론적 기준으로 대체."""
    if not names or not target_mcap:
        return {}
    try:
        cik_map = ir._cik_map()
    except Exception as e:
        print(f'[경쟁사 CIK 조회 실패] {e}')
        return {}

    def norm(s):
        s = re.sub(r'[.,]', '', s.lower())
        for suf in (' inc', ' corp', ' corporation', ' ltd', ' llc', ' plc', ' company', ' co'):
            if s.endswith(suf):
                s = s[:-len(suf)]
        return s.strip()

    by_name = {}
    for tk, info in cik_map.items():
        by_name.setdefault(norm(info['name']), tk)

    out = {}
    for nm in names:
        key = norm(nm)
        tk = by_name.get(key)
        if not tk:
            for k2, v2 in by_name.items():
                if key and len(key) > 3 and (key in k2 or k2 in key):
                    tk = v2
                    break
        if not tk or tk in out:
            continue
        try:
            mcap = S.consensus(tk).get('market_cap')
        except Exception:
            mcap = None
        if not mcap or not (0.05 <= mcap / target_mcap <= 20):
            continue  # 체급 차이 너무 크면(플랫폼 대기업 등) 비교 의미 없어 제외
        # mcap도 보관 — CANSLIM N ①(글로벌 탑티어)을 "동종 경쟁사 대비 시총 순위"라는
        # 결정론적 기준으로 채점하는 데 재사용한다(여기서 이미 조회했으니 추가 요청 없음).
        out[tk] = {'cik': cik_map[tk]['cik'], 'name': cik_map[tk]['name'], 'mcap': mcap}
        if len(out) >= max_n:
            break
    return out


def _detect_price_moves(rows, top_n=2):
    """월봉에서 등락률이 가장 큰 구간(상승 1개+하락 1개)을 결정론적으로 탐색.
    "왜 올랐는지"는 여기서 판단 안 함 — _call_price_moves가 실제 뉴스 검색 결과로만 채움.

    오래 상장된 종목(46년치 등)은 등락'률'만 보면 상장 초기 주가가 몇 센트~몇 달러
    수준이던 시절의 잡음이 압도적으로 이긴다(실제 발견: AAPL — 자동 탐지가 2000년대
    초반 닷컴버블 시기의 +383%/-73%를 골랐는데, 사용자 입장에선 "애플 역사에 대해
    아무것도 알 수 없는" 구간이었음. 반면 최근 20년엔 아이폰 랠리·2008 금융위기·
    코로나 충격처럼 실제로 유명하고 투자적으로 의미 있는 급등락이 있다). 전체 이력이
    20년(240개월)을 넘으면 최근 20년으로 탐색범위를 좁힌다 — 어린 종목(IONQ·SATL
    등, 전체 이력 자체가 20년 미만)은 원래 동작 그대로."""
    if len(rows) < 6:
        return []
    # 행 개수가 아니라 실제 달력 연수로 잘라야 한다 — Yahoo의 오래된 월봉은 최근보다
    # 표본 밀도가 성겨서(실측: AAPL 42년치가 168개월 rows뿐, 1행=1달 가정이 안 맞음)
    # 행 개수 기준 슬라이스는 원하는 만큼 옛날 구간을 못 걸러냈다.
    cutoff = rows[-1][0] - 20 * 365 * 86400
    recent = [r for r in rows if r[0] >= cutoff]
    if len(recent) >= 6:
        rows = recent
    closes = [(r[0], r[4]) for r in rows]
    best_up, best_dn = None, None
    for i in range(len(closes)):
        for j in range(i + 1, min(i + 7, len(closes))):   # 최대 6개월 창
            t0, c0 = closes[i]
            t1, c1 = closes[j]
            if not c0:
                continue
            pct = (c1 / c0 - 1) * 100
            if pct > 0 and (best_up is None or pct > best_up[2]):
                best_up = (t0, t1, pct, c0, c1)
            if pct < 0 and (best_dn is None or pct < best_dn[2]):
                best_dn = (t0, t1, pct, c0, c1)
    out = []
    for mv in (best_up, best_dn):
        if mv is None:
            continue
        t0, t1, pct, c0, c1 = mv
        d0 = datetime.fromtimestamp(t0, timezone.utc)
        d1 = datetime.fromtimestamp(t1, timezone.utc)
        out.append({'dir': 'up' if pct > 0 else 'down', 'pct': pct,
                    'start': d0, 'end': d1, 'c0': c0, 'c1': c1})
    return out[:top_n]


def _historical_news(company: str, start: datetime, end: datetime, limit=10):
    """구글뉴스 RSS의 after:/before: 검색연산자로 특정 과거 구간 헤드라인 조회 —
    ir.company_news()는 "최근 N일"만 되고 과거 임의 구간은 안 돼서 별도 구현.
    API 키 불필요(무료 RSS), Gemini 그라운딩이 막힌 것과 달리 이 경로는 실제로 됨
    (직접 확인함)."""
    import requests
    import urllib.parse
    import xml.etree.ElementTree as ET
    q = urllib.parse.quote(f'"{company}" after:{start.date()} before:{end.date()}')
    url = f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    try:
        r = requests.get(url, headers={'User-Agent': ir.SEC_UA if hasattr(ir, "SEC_UA") else
                                       'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f'[과거뉴스 조회 실패] {company}: {e}')
        return []
    out = []
    for item in root.findall('.//item')[:limit]:
        title = (item.findtext('title') or '').strip()
        if title:
            out.append(title)
    return out


def _market_size_headlines(query: str, limit=15):
    """TAM(시장규모) 자동화 — 유료 검색 그라운딩 없이는 안 된다고 봤었는데(사용자가
    재차 요청, "TAM 자동화 어떻게 할 거야"), 급등락 이유 조사에 이미 쓰던 구글뉴스
    RSS 기법을 그대로 재활용할 수 있다는 걸 확인함(실측: "smartphone market size
    billion forecast" 검색 시 "Smartphones Market to Garner US$ 747.53 Billion by
    2035 - Astute Analytica" 같은 시장조사기관 보도자료 헤드라인이 실제로 잡힘 —
    이런 보도자료는 헤드라인 자체에 숫자·기관명·목표연도를 박아넣는 게 업계 관행이라
    본문을 못 읽어도 헤드라인만으로 추출 가능). API 키 불필요, 날짜 제한 없이 검색."""
    import requests
    import urllib.parse
    import xml.etree.ElementTree as ET
    q = urllib.parse.quote(query)
    url = f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                         timeout=15)
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f'[시장규모 뉴스 조회 실패] {query}: {e}')
        return []
    return [t for item in root.findall('.//item')[:limit]
            if (t := (item.findtext('title') or '').strip())]


TAM_PROMPT = """당신은 기관 애널리스트입니다. 아래는 "{query}" 검색으로 나온 구글뉴스
헤드라인(실제 검색 결과, 시장조사기관 보도자료 다수 포함)입니다. 각 헤드라인에 시장규모
숫자(예: "$747.53 Billion by 2035")가 명시적으로 있는 것만 골라 추출하세요.

규칙: 헤드라인에 숫자가 없으면 절대 만들어내지 말 것 — 그 헤드라인은 그냥 버릴 것.
같은 기관이 여러 헤드라인에 나오면 하나만. 최대 5개. 숫자가 하나도 없으면 빈 배열.
순수 JSON만 출력:

{{"estimates": [["기관명(간단히)", 시장규모_숫자_10억달러_단위(float), 목표연도_또는_CAGR퍼센트(float, 없으면 0)]],
 "cagr": 헤드라인에 "CAGR of X%"·"growing at X% annually"처럼 **연평균 성장률이 명시된 것만**의
         대표값(float, 여러 개면 중앙값에 가까운 하나). 명시된 게 하나도 없으면 null.
         시장규모 숫자를 성장률로 착각해서 넣지 말 것.}}

[헤드라인]
{headlines}
"""


_TAM_STOP = {'market', 'size', 'billion', 'forecast', 'global', 'industry', 'report',
             'share', 'growth', 'analysis', 'trends', 'and', 'the', 'for', 'of',
             'services', 'service', 'solutions', 'systems', 'technology', 'us', 'u.s',
             # 아래는 어느 산업 이름에나 붙는 수식어라 일치 근거가 못 된다.
             # 'value-based care'의 'based'가 'CRISPR-based Gene Editing'과 맞아
             # 유전자편집 시장이 통과했다(실측).
             'based', 'driven', 'enabled', 'powered', 'oriented', 'centric',
             'advanced', 'digital', 'smart', 'next', 'generation', 'new'}


def _filter_industry(headlines, industry_en: str):
    """검색이 물어온 헤드라인 중 **이 산업이 실제로 언급된 것만** 남긴다.

    구글뉴스 RSS는 질의를 느슨하게 매칭해서 전혀 다른 시장 보도자료를 섞어 준다.
    실측(AGL, 질의 'value-based care market size billion forecast'):

        Patient Engagement Solutions Market ... USD 98.46 Bn   ← 다른 시장
        North America Healthcare IT Market $529.06 billion     ← 다른 시장
        U.S. Digital Health Market USD 713.36 Billion          ← 다른 시장
        Pet Care Market Size, Share                            ← 반려동물
        Wound Care Market Size & Share                         ← 상처치료

    LLM에는 "숫자 있는 헤드라인만 골라라"라고만 시켰지 "이 산업이 맞느냐"는 안
    물었기 때문에, 위 숫자들이 그대로 TAM으로 실렸다. 산업 일치는 문자열로 확인
    가능한 문제라 LLM에 맡길 이유가 없다.

    판정: 산업어에서 불용어를 뺀 핵심 토큰이 헤드라인에 하나라도 있어야 한다.
    (하이픈·공백 표기 차이는 흡수 — 'value-based' vs 'Value Based')
    """
    core = [t for t in re.split(r'[^a-z0-9]+', (industry_en or '').lower())
            if t and t not in _TAM_STOP and len(t) > 2]
    if not core:
        return headlines
    # 토큰을 개수로 세면 안 된다 — 흔한 단어와 특이한 단어가 같은 무게가 되기
    # 때문이다. 'value-based care'에서 'care'는 반려동물·상처치료·홈케어 시장에도
    # 다 들어있고, 실제로 그 시장들이 통과해 남의 숫자가 카드에 실렸다.
    #
    # 대신 **가장 희소한 토큰**을 요구한다. 이번 검색 결과 안에서 몇 개
    # 헤드라인에 나오는지(문서빈도)를 세어 가장 드문 것이 그 산업을 가장 잘
    # 특정한다 — 'value'는 2건, 'care'는 6건이면 'value'를 요구하는 게 맞다.
    # 부분문자열이 아니라 단어 경계로 본다('care'가 'healthcare'에 걸리지 않게).
    # 헤드라인 아무 자리가 아니라 **시장 이름 안**에서 찾는다. 'Market' 앞부분이
    # 그 보도자료가 말하는 시장의 이름이고, 뒤쪽은 수식·기관명·부제라 무관한 단어가
    # 섞인다. 이 구분을 안 하면 'CRISPR-based Gene Editing Market ... value'처럼
    # 본문 어딘가에 걸려 통과한다(실측).
    def _market_name(h):
        m = re.split(r'\bmarket\b', h.lower(), maxsplit=1)
        return re.sub(r'[^a-z0-9]+', ' ', m[0] if len(m) > 1 else h.lower())

    flats = [_market_name(h) for h in headlines]

    def _df(tok):
        return sum(1 for f in flats if re.search(rf'\b{re.escape(tok)}\b', f))

    key = min(core, key=_df)
    if _df(key) == 0:                       # 어느 헤드라인에도 없으면 특정 불가
        return []
    return [h for h, f in zip(headlines, flats)
            if re.search(rf'\b{re.escape(key)}\b', f)]


def _call_tam(raw, static):
    # 처음엔 segments[0](제품명, 예: "iPhone")을 검색어로 썼다가 결과가 하나도 안
    # 걸렸다(실측) — "iPhone market size"는 시장조사기관이 안 쓰는 표현이라(그들은
    # "smartphone market"으로 리포트를 냄). STATIC_PROMPT에 별도로 받은 영어 산업
    # 카테고리(industry_en)를 대신 쓴다.
    industry_en = static.get('industry_en') or raw['company']
    query = f'{industry_en} market size billion forecast'
    headlines = _market_size_headlines(query)
    headlines = _filter_industry(headlines, industry_en)
    if not headlines:
        # 이 산업의 시장규모 헤드라인을 못 찾은 것이다. **빈 채로 두는 게 맞다** —
        # 예전엔 검색이 느슨하게 물어온 남의 시장 숫자가 그대로 실렸다
        # (AGL은 가치기반 의료 회사인데 반려동물·상처치료·디지털헬스 시장이 후보에
        # 올랐고 실제로 바이오 시장 $713B가 카드에 찍혔다).
        print(f'[{raw["ticker"]}] TAM: "{industry_en}" 관련 시장규모 헤드라인 없음 — 비워둔다')
        return [], None
    prompt = TAM_PROMPT.format(query=query, headlines='\n'.join(f'- {h}' for h in headlines))
    try:
        client = analyzer._client()
        data = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[TAM 추출 실패] {e}')
        return [], None
    if data.get('_parse_error'):
        return [], None
    ests = data.get('estimates') or []
    # LLM이 "숫자 없으면 버려라" 지시를 안 지키고 값 0짜리 행을 끼워 넣는 경우가
    # 실측으로 있었다(헤드라인에 실제 숫자가 없는데도 행 자체는 만듦) — 프롬프트
    # 신뢰만으로 안 되니 파이썬에서 한 번 더 거른다.
    ests = [tuple(e) for e in ests if len(e) == 3 and e[1] and e[1] > 0][:5]
    # 기관마다 "시장"의 정의가 달라 편차가 크긴 한데, 30배 넘게 벌어지면(PLTR 실측:
    # $53B·$72B 사이에 $1,833B가 끼어 막대 3개 중 2개가 보이지도 않음) 같은 시장을
    # 재고 있는 게 아니라 훨씬 넓은 상위 시장을 잡은 것 — 중앙값의 8배를 넘으면 버린다.
    if len(ests) >= 3:
        mid = sorted(e[1] for e in ests)[len(ests) // 2]
        kept = [e for e in ests if e[1] <= mid * 8]
        if len(kept) != len(ests):
            print(f'[TAM] 시장 정의가 다른 이상치 {len(ests)-len(kept)}건 제외(중앙값 {mid:.0f}B의 8배 초과)')
        ests = kept
    # CAGR도 같은 이유로 재검증 — 시장규모($747B)를 성장률 칸에 넣는 혼동이 실제로
    # 나올 수 있어서 상식 범위(0~100%)를 벗어나면 버린다.
    cagr = data.get('cagr')
    try:
        cagr = float(cagr) if cagr is not None else None
    except (TypeError, ValueError):
        cagr = None
    if cagr is not None and not (0 < cagr <= 100):
        cagr = None
    return ests, cagr


# ── 2c. CANSLIM N 자동 채점 (계산 가능한 건 계산, 판단만 LLM) ──────────────
def _score_canslim_n(raw, peers: dict, tam_cagr, governance: dict = None, competitors: list = None):
    """N 5개 항목을 최대한 결정론적으로 채운다.

    예전엔 top_tier·growth_years·governance·market_cagr를 전부 0/None으로 비워둔 채
    파일을 뽑았고, 그러면 종목마다 사람이 손으로 채워야 했다("N 항목은 미입력이 아니라
    네가 분석해서 점수를 줘야지" — 실제 지적). 그런데 지금 이미 확보한 데이터만으로도
    4개 중 3개는 근거 있게 계산된다:

      ① 글로벌 탑티어  : 10-K가 지목한 동종 경쟁사(시총 0.05~20배로 이미 걸러진
                         '체급이 비슷한 회사'들) 대비 시총 순위. 1위=10 / 중간=5 /
                         최하위=3 / 비교군 없음=0(추측 대신 0).
      ② 20%+ 성장 연수 : 컨센서스로 확인되는 미래 20%+ 매출성장 연수(0~2, 무료
                         데이터가 2년까지만 줌) + 최근 3년 실적 매출 CAGR도 20% 이상이면
                         '증명된 지속력'으로 +1. 최대 3.
      ③ 경쟁기업 수    : 이미 자동(10-K가 이름을 든 경쟁사 수).
      ④ 지배구조 개편  : 판단 영역이라 LLM(위임장 근거)에 맡기고, 근거 문장이 없으면 0.
      ⑤ New Market CAGR: TAM 검색 헤드라인에 CAGR이 명시된 경우만.

    반환: (canslim.score_n에 넣을 kwargs, 각 항목의 근거 문장 dict)
    근거를 같이 돌려주는 게 핵심 — 점수만 있고 왜 그 점수인지 없으면 지어낸 것과 구분이 안 된다.
    """
    detail = {}
    cons = raw.get('cons') or {}
    mcap = cons.get('market_cap')

    # ① 글로벌 탑티어
    peer_caps = {tk: (info or {}).get('mcap') for tk, info in (peers or {}).items()}
    peer_caps = {k: v for k, v in peer_caps.items() if v}
    if mcap and peer_caps:
        bigger = [k for k, v in peer_caps.items() if v > mcap]
        rank = len(bigger) + 1
        n_all = len(peer_caps) + 1
        top_tier = 10 if rank == 1 else (3 if rank == n_all else 5)
        detail['글로벌 탑티어'] = (f'10-K가 지목한 동급 경쟁사 {len(peer_caps)}곳 중 시총 '
                              f'{rank}위(${mcap/1e9:.1f}B) → {top_tier}점')
    else:
        top_tier = 0
        detail['글로벌 탑티어'] = '동급 경쟁사(시총 0.05~20배) 매칭 0곳 — 순위 비교 불가로 0점'

    # ② 20%+ 성장 가능 연수
    ann_rev = (raw.get('ann_series') or {}).get('revenue', {}) or {}
    # 0과 None을 구분한다 — `if v`로 거르면 매출 0을 공시하는 개발단계 기업에서
    # 연도 자체가 사라져 성장률 계산이 엉뚱해진다(probe에서 같은 버그를 실측함).
    yrs = sorted(y for y, v in ann_rev.items() if v)
    periods = cons.get('periods') or {}
    fwd = 0
    base = ann_rev.get(yrs[-1]) if yrs else None
    fwd_bits = []
    for k in ('0y', '+1y'):
        est_rev = (periods.get(k) or {}).get('rev')
        if base and est_rev:
            g = (est_rev / base - 1) * 100
            if g >= 20:
                fwd += 1
                fwd_bits.append(f'{(periods.get(k) or {}).get("end", k)} {g:+.0f}%')
            base = est_rev
    hist_bonus = 0
    if len(yrs) >= 3:
        f, l = ann_rev[yrs[-3]], ann_rev[yrs[-1]]
        if f and l and f > 0 and l > 0:
            hist_cagr = ((l / f) ** (1 / (yrs[-1] - yrs[-3])) - 1) * 100
            if hist_cagr >= 20:
                hist_bonus = 1
                fwd_bits.append(f'과거 {yrs[-3]}~{yrs[-1]} CAGR {hist_cagr:+.0f}%')
    growth_years = min(3, fwd + hist_bonus)
    detail['20%+ 성장 가능 연수'] = (f'{growth_years}년 ({" · ".join(fwd_bits)}) → {growth_years * 2}점'
                              if fwd_bits else '컨센서스·실적 어디서도 20%+ 성장 근거 없음 → 0점')

    # ③ 경쟁기업 수 — 채점 기준(2개 이하 0점 / 3개 이상 -2점)은 "경쟁이 얼마나 붐비나"를
    #    보는 항목이라, 시총으로 걸러낸 비교군(peers)이 아니라 10-K가 실제로 이름을 든
    #    경쟁사 전체 수를 써야 맞다.
    n_comp = len(competitors or [])
    detail['경쟁기업 수'] = (f'10-K Competition 절에 언급된 경쟁사 {n_comp}곳 → '
                       f'{0 if n_comp <= 2 else -2}점')

    # ④ 지배구조 개편
    gv = governance or {}
    gv_note = (gv.get('note') or '').strip()
    gv_pt = 5 if (gv.get('changed') and gv_note) else 0
    detail['지배구조 개편'] = f'{gv_note} → {gv_pt}점' if gv_pt else (gv_note or '최근 중대한 지배구조 개편 근거 없음 → 0점')

    # ⑤ New Market CAGR
    if tam_cagr:
        detail['New Market CAGR'] = f'시장조사기관 헤드라인 기준 시장 CAGR {tam_cagr:.1f}% → {round(tam_cagr/2)}점'
    else:
        detail['New Market CAGR'] = '뉴스 검색에서 시장 CAGR 명시된 헤드라인 못 찾음 → 0점'

    return (dict(top_tier=top_tier, growth_years=growth_years, competitors=n_comp,
                 governance=gv_pt, market_cagr=tam_cagr),
            detail)


PRICE_MOVE_PROMPT = """당신은 기관 애널리스트입니다. {company}({ticker})의 주가가 {period}
사이에 {pct:+.0f}% 움직였습니다({c0} → {c1}). 아래는 그 기간 헤드라인(구글뉴스, 실제 검색
결과)입니다. 이 구간 등락의 이유를 헤드라인에서만 근거를 찾아 한국어로 짧게 설명하세요.

규칙: 헤드라인에 명확한 계기가 없으면 지어내지 말고 반드시 "단일 계기 미확인 — [헤드라인
경향 요약]"처럼 정직하게 쓸 것. 개조식("~함/~됨"), **반드시 1문장, 60자 이내**(카드형
UI에 들어가는 텍스트라 길면 잘림 — 여러 이유를 다 나열하지 말고 가장 중요한 것 하나만
콤마로 짧게). 순수 JSON만 출력:

{{"reason": "위 규칙을 따른 60자 이내 한 문장"}}

[헤드라인]
{headlines}
"""


def _call_price_move_reason(raw, mv):
    headlines = _historical_news(raw['company'], mv['start'], mv['end'])
    period = f'{mv["start"].strftime("%Y.%m")}→{mv["end"].strftime("%Y.%m")}'
    if not headlines:
        return {'period': period, 'reason': '단일 계기 미확인 — 이 구간 관련 뉴스 검색 결과 없음'}
    prompt = PRICE_MOVE_PROMPT.format(company=raw['company'], ticker=raw['ticker'], period=period,
                                      pct=mv['pct'], c0=f'${mv["c0"]:.2f}', c1=f'${mv["c1"]:.2f}',
                                      headlines='\n'.join(f'- {h}' for h in headlines))
    try:
        client = analyzer._client()
        data = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[가격변동 이유 생성 실패] {e}')
        return {'period': period, 'reason': '단일 계기 미확인 — 자동 분석 실패'}
    reason = data.get('reason') if not data.get('_parse_error') else None
    return {'period': period, 'reason': reason or '단일 계기 미확인'}


def _listing_date_from_sec(cik: int):
    """SPAC 합병 종목은 상장일(개명일) 이전 SPAC 껍데기 시세가 Yahoo에 같은 티커로
    남아있어(IONQ 실측: 2021-01부터 $11 근방 평평한 시세 — 실제 사명변경은 10-04),
    그대로 쓰면 차트·CAGR이 SPAC 시절부터 계산돼 틀린다. SEC formerNames의 마지막
    개명일을 상장일 근사치로 쓴다 — organic IPO는 formerNames가 비어있어 그냥 None.

    실제 발견한 버그(AAPL): formerNames가 SPAC merger가 아니라 그냥 오래된 회사의
    일반적인 사명변경 이력(1994 "APPLE COMPUTER INC" → 2007 "APPLE INC" 등)일 때도
    이 로직이 그대로 발동해, 1980년 IPO한 회사인데 formerNames의 (날짜순 정렬도
    안 된) 리스트 마지막 항목("APPLE COMPUTER INC/ FA", 1997-07-28라는 하루짜리
    행정상 별칭)을 "상장일"로 잘못 채택했다 — 그 결과 차트·CAGR·MDD가 전부 1997년
    이후로만 계산되면서 "1980년 상장 종가 대비 CAGR"이라는 라벨과 실제 계산 기간이
    안 맞는 거짓말이 됐다. SPAC 합병은 보통 사명변경이 딱 한 번뿐(껍데기명→운영사명)
    이라 — formerNames가 여러 번(=오래된 회사의 복잡한 개명 이력)이면 이 휴리스틱
    자체를 안 믿는다(None 반환 → 상장일 제한 없이 실제 보유 데이터 전부 사용)."""
    try:
        r = ir.requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                            headers=ir.SEC_HEADERS, timeout=30)
        former = r.json().get('formerNames') or []
        if len(former) != 1:
            return None
        return former[0]['to'][:10]
    except Exception as e:
        print(f'[상장일 조회 실패] {e}')
        return None


def _exchange_from_sec(cik: int):
    """SEC submissions API의 exchanges 필드 — LLM 호출 없이 그냥 원문 그대로.
    AAPL 검증 중 COMPANY['exchange']가 render_data_file에서 늘 빈 문자열로
    하드코딩돼 있던 걸 발견(연혁 페이지 "상장" 타일에 빈칸으로 노출) — 이미
    가져오던 submissions JSON에 실제로 들어있는 값이라 추가 호출 없이 채운다."""
    try:
        r = ir.requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                            headers=ir.SEC_HEADERS, timeout=30)
        exch = [e for e in (r.json().get('exchanges') or []) if e]
        return exch[0] if exch else ''
    except Exception as e:
        print(f'[거래소 조회 실패] {e}')
        return ''


def _fetch_proxy_excerpts(cik: int):
    """DEF 14A(위임장) 원문에서 CEO 약력·보수구조 관련 대목만 발췌.

    IONQ 세션에서 실제로 겪은 문제: 10-K엔 CEO 실명이 아예 없고(Part III가 위임장에
    위임됨), RSU/PSU 베스팅 조건도 CD&A에만 나온다 — 그때는 사람이 직접 검색해서
    찾았는데, 매번 그럴 수 없으니 패턴을 일반화한다. 위임장 전체(20만자+)를 프롬프트에
    넣으면 비싸니, 실제 정보가 몰려있는 문맥(직함 언급·베스팅 조건 서술)만 정규식으로
    추려 12000자 이내로 제한."""
    try:
        j = ir.requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                            headers=ir.SEC_HEADERS, timeout=40).json()
        rec = j['filings']['recent']
        target = None
        for form, acc, doc in zip(rec['form'], rec['accessionNumber'], rec['primaryDocument']):
            if form == 'DEF 14A':
                target = (acc.replace('-', ''), doc)
                break
        if not target:
            return ''
        acc, doc = target
        url = f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}'
        t = ir.requests.get(url, headers=ir.SEC_HEADERS, timeout=60).text
        t2 = re.sub(r'<[^>]+>', ' ', t)
        t2 = re.sub(r'&#8217;', "'", t2)
        t2 = re.sub(r'&#8220;|&#8221;', '"', t2)
        t2 = re.sub(r'&#8212;|&#8211;', '-', t2)
        t2 = re.sub(r'&nbsp;|&#160;', ' ', t2)
        t2 = re.sub(r'\s+', ' ', t2)
        excerpts, seen = [], set()
        # 'Chief Financial Officer'·'Executive Officers' 대목을 추가로 발췌 — 예전엔
        # CEO 관련 문맥만 뽑아서 LEADERSHIP['people'](주요 경영진 표)이 모든 종목에서
        # 영구히 빈 배열이었고, 그래서 4p가 매번 "내용이 부실하다"는 지적을 받았다.
        # 'Corporate Governance'는 CANSLIM N ④(지배구조 개편) 판정 근거용.
        for kw in ('Chief Executive Officer', 'Chief Financial Officer', 'Executive Officers',
                   'Corporate Governance', 'vesting condition', 'performance condition',
                   'Earnout opportunity', 'revenue goal'):
            for m in list(re.finditer(re.escape(kw), t2))[:2]:
                i = m.start()
                if any(abs(i - s) < 300 for s in seen):   # 겹치는 발췌 중복 방지
                    continue
                seen.add(i)
                excerpts.append(t2[max(0, i - 150):i + 500])
        return '\n---\n'.join(excerpts)[:12000]
    except Exception as e:
        print(f'[위임장 발췌 실패] {e}')
        return ''


# ── 1. 원자재 수집 (전부 결정론적 — LLM 호출 없음) ────────────────────────
def _gather_raw(ticker: str):
    cik, company = ir.resolve_ticker(ticker)
    _t = ticker.upper()
    if not cik:
        raise SystemExit(f'{ticker}: SEC CIK를 못 찾음(티커 오타 또는 비상장)')
    listing_date = _listing_date_from_sec(cik)
    exchange = _exchange_from_sec(cik)

    hist = ir.filing_history(cik, limit=24)
    annual = next((f for f in hist if f['form'] in ('10-K', '20-F')), None)
    if not annual:
        raise SystemExit(f'{ticker}: 10-K/20-F를 못 찾음')
    annual_text = ir.filing_text(cik, annual)

    earnings = next((f for f in hist if ir._is_earnings_form(f)), None)
    earnings_text = ir.filing_text(cik, earnings) if earnings else ''

    profile = ir.company_profile(ticker, cik, company)
    transcript, _url = ir.earnings_transcript(ticker, company)

    # ttl_h=0 — 24h 캐시를 그대로 두면 "실적 발표 당일 캐시가 발표 몇 시간 전에
    # 채워진 뒤 발표 후 autogen.py를 돌리는" 실제 사고가 난다(PLTR 실측: KPI 타일이
    # 구분기 $1.63B, 어닝콜 facts 표는 원문을 직접 읽어 신분기 $1.94B — 같은 페이지
    # 안에서 숫자가 모순됨). autogen.py는 "최신 데이터 달라"는 명시적 요청이라 캐시를
    # 신뢰하지 말고 항상 새로 받는다(이 fetch가 캐시도 갱신해 이어지는 build.py
    # 렌더도 자동으로 최신 데이터를 씀).
    ann_series = S.annual_series(cik, ['revenue', 'netinc', 'cfo', 'cash', 'opinc'], ttl_h=0)
    qtr_series = S.quarterly_series(cik, ['revenue', 'opinc', 'netinc', 'cfo', 'cash'], limit=8, ttl_h=0)
    cons = S.consensus(ticker)
    own = S.ownership(ticker)
    proxy = S.beneficial_owners(cik)
    proxy_excerpts = _fetch_proxy_excerpts(cik)
    ohlcv = S.monthly_ohlcv(ticker, since=listing_date)
    site = S.company_site(cik, fallback='')

    return dict(ticker=_t, cik=cik, company=company, hist=hist, annual=annual, annual_text=annual_text,
                earnings=earnings, earnings_text=earnings_text, profile=profile,
                transcript=transcript, ann_series=ann_series, qtr_series=qtr_series,
                cons=cons, own=own, proxy=proxy, listing_date=listing_date, exchange=exchange,
                proxy_excerpts=proxy_excerpts, ohlcv=ohlcv, site=site)


# ── 2. LLM 호출 A: 10-K 기반 정적 서사 (연혁·CEO·RSU·사업부문·TAM) ────────
STATIC_PROMPT = """당신은 15년 경력의 셀사이드 애널리스트입니다. {company}({ticker})의 연차보고서
(10-K/20-F) 원문에서 아래 항목을 한국어로 채우세요. 문체는 보고서용 — 클리셰("혁신적인",
"선도하는", "무한한 가능성") 절대 금지, 숫자와 사실 위주로 짧게. 모든 서술형 필드(note류·
bio·segments 설명 등)는 개조식으로 — "~함/~됨/~중" 종결, "~습니다/~합니다/~됩니다" 금지
(예: "손실을 예상하고 있습니다"(X) → "손실 예상"(O)). 금액은 항상 "$XXX.XB"·"$XXX.XM"
표기(예: "$416.2B"(O) — "4,161억 6,100만 달러"·"416,161.0백만 달러"(X), 원문 단위 그대로
베끼지 말 것). 순수 JSON만 출력:

{{
  "sector": "이 회사를 한 줄로 규정하는 업종(예: '전기차·에너지저장·AI/로보틱스') — 12자 내외, 없으면 빈 문자열",
  "value_chain": {{
    "industry": "산업 이름(예: '지구관측 위성 데이터') — 15자 이내",
    "chain": ["산업의 밸류체인 단계 4~6개를 상류→하류 순서로, 각 10자 이내(예: '부품·발사체', '위성 제조', '위성 운용', '데이터 처리·분석', '정부·기업 고객')"],
    "position": "이 회사가 주로 있는 단계의 0부터 센 번호(정수). 여러 단계면 가장 매출이 큰 곳",
    "spans": "이 회사가 걸쳐 있는 단계 번호 목록(정수 배열)",
    "position_note": "그 위치가 왜 중요한지 — 가격 결정력·병목·수직계열화 관점 1문장, 원문 근거",
    "cycle": "업황 사이클 국면 1문장 — 원문에 수요·가격·재고·수주 언급이 있을 때만, 없으면 빈 문자열",
    "drivers": ["이 산업의 업황을 움직이는 변수 2~3개(예: '각국 국방 예산', '발사 비용')"]
  }},
  "industry_en": "이 회사의 핵심 산업을 구글 검색에 넣기 좋은 영어 1~3단어(예: 'smartphone',"
                 " 'cloud software', 'quantum computing', 'electric vehicle') — TAM 시장규모"
                 " 뉴스 검색에 쓰임. 제품명(예: 'iPhone')이 아니라 산업 카테고리로 쓸 것.",
  "business_model": ["이 회사가 뭘 하는지 짧은 한 줄(25자 이내) — 구체 제품·고객·점유율·숫자 중 하나는 꼭 들어갈 것",
                     "두 번째 핵심 사실(25자 이내, 없으면 생략)", "세 번째 핵심 사실(25자 이내, 없으면 생략)"],
  "founded_year": 설립연도(정수) 또는 null,
  "listed_year": 상장연도(정수) 또는 null,
  "listing_type": "IPO/SPAC합병/직상장/스핀오프 중 원문 근거 있는 값(예: 모회사에서"
                  " 분리돼 상장했으면 '스핀오프' — 'IPO'로 뭉뚱그리지 말 것, 신주모집"
                  " 없이 기존 주주에게 지분 배분한 거면 스핀오프가 맞음), 없으면 빈 문자열",
  "founders": "공동창업자 이름, 없으면 빈 문자열",
  "history_note": "지금 이 회사가 어떤 국면에 있는지 3~4문장 해석(전문투자자 톤, 숫자 인용)",
  "timeline": [["연도(문자열)", "그 해 있었던 핵심 '사건' — 60자 이내(넘으면 축약)", true_or_false_강조여부]],
  "employee_count": 최신 임직원수(정수) 또는 null,
  "employee_count_asof": "임직원수 기준일(원문에 나온 날짜 그대로, 예 'FY2025 10-K')",
  "ceo_name": "CEO 실명(영문 그대로) — 원문에 반드시 있음, 빈 문자열 금지",
  "ceo_since": CEO_취임연도(정수) 또는 null,
  "ceo_bio": "CEO 2~3문장 소개 — 취임연도·이전 이력",
  "leadership_note": "경영진 구성에서 투자자가 알아야 할 특이점 1~2문장(없으면 빈 문자열)",
  "rsu_note": "테슬라 일론 머스크 패키지(시총 X달러 달성 등)처럼 '성과 조건'이 실제로"
              " 걸린 주식보상만 적을 것 — 매출목표·시총목표·주가목표·기술마일스톤 등"
              " 구체적 조건이 원문에 있을 때만. 그냥 '4년 근속 베스팅' 같은 표준 시간베스팅뿐이면"
              " 정보가치가 없으니 빈 문자열로 둘 것(성과조건 없음 ≠ 특이 베스팅).",
  "segments": [["부문명", "이 부문이 무슨 사업인지 1~2문장", 매출비중_숫자_또는_null]],
  "competitors": ["원문 Competition/Business 절에 실제로 이름이 언급된 경쟁사만, 없으면 빈 배열"],
  "tam_note": "원문에 시장규모(TAM) 추정치가 있으면 그 숫자와 출처를 그대로, 없으면 빈 문자열(지어내지 말 것)",
  "dilution_note": "전환사채·워런트 등 잠재 희석요인이 원문에 언급돼 있으면 요약, 없으면 빈 문자열"
}}

규칙: 모든 필드는 반드시 원문에 실제로 있는 내용만. 확실하지 않으면 null/빈 문자열/빈 배열로 비울 것 — 추측 금지.

business_model 작성 규칙(2026-10-23 개정): 표지에 '- ' 로 붙는 짧은 줄 2~3개.
- 각 줄은 이 회사에만 해당하는 구체 사실이어야 한다: 대표 제품명·주요 고객사명·점유율·세계 순위·매출 비중.
- 어느 회사에나 붙는 뻔한 말은 쓰지 말 것: "고객 주문에 따라 제조·납품해 매출을 올림",
  "제품 판매로 수익 창출", "다양한 고객에게 공급" 같은 줄은 차라리 빼라(줄 수가 줄어도 된다).
- 업계 용어 그대로 X, 홍보 문구 X. 원문에서 확인 안 되면 빈 배열.

timeline 작성 규칙(중요):
- "사건"만 넣는다 — 창업·상장·제품출시·M&A·중대 계약·규제승인·기술 마일스톤 등.
- "OO년 순손실 X달러 기록"처럼 매출/손익 숫자만 되풀이하는 항목은 절대 넣지 말 것
  (그 숫자는 재무제표 페이지에 이미 나옴 — 여기 또 넣으면 의미 없는 반복).
- 항목이 여러 개(예: 5개 회사 인수) 나열형으로 길어지면 전부 쓰지 말고
  "OO 등 N개사 인수"처럼 압축할 것 — 60자를 넘기지 말 것(렌더 시 잘림).

[연차보고서 원문]
{body}
"""


def _call_static(raw):
    prompt = STATIC_PROMPT.format(company=raw['company'], ticker=raw['ticker'],
                                   body=raw['annual_text'][:ir.TEXT_LIMIT])
    client = analyzer._client()
    data = analyzer._parse(analyzer._generate(client, prompt).text)
    if data.get('_parse_error'):
        raise SystemExit(f'[정적 서사 생성 실패] 파싱 오류: {data}')
    return _fix_money_units(data)


# ── 3. LLM 호출 B: 최근 실적 + 어닝콜 기반 (RESULTS·CHECKPOINTS) ─────────
RECENT_PROMPT = """당신은 기관 애널리스트입니다. {company}({ticker})의 최근 실적 공시 원문과
(있다면) 어닝콜 하이라이트를 보고 아래를 한국어로 채우세요. 클리셰 금지, 숫자 위주.
checkpoint_note는 개조식("~함/~됨") — "~습니다" 금지. quotes는 실제 발언 번역이라 예외
(자연스러운 구어체 유지). 금액은 항상 "$XXX.XB"·"$XXX.XM" 표기(예: "$109.4B"(O) —
"$109,417백만"·"1,094억 1,700만 달러"(X)). 순수 JSON만:

{{
  "period": "실적 기준 분기 — 예 'Q2 2026'",
  "facts": [["항목명(6자 이내)", "구(phrase)로 — 완전한 문장 금지, 조사로 끝내지 말 것, 30자 이내", "금액·수치"]] ,
  "quotes": [["직함(예: CEO)", "한국어 번역", "영문 원문"]],
  "checkpoints": [["시점 — 타이밍만 짧게, 형식 통일할 것(뒤섞으면 타임라인이 지저분해짐):"
                  " 구체월 알면 'YYYY년 M월', 분기면 'YYYY년 QN', 그 분기 이후 지속이면"
                  " 'YYYY년 QN~', 특정 연도부터 쭉이면 'YYYY년~', 외부 판결/결정처럼 날짜"
                  " 자체를 모르면 '~시'(예: '대법원 판결시'). 10자 이내, 사건 설명은 절대"
                  " 넣지 말 것(그건 다음 칸에 씀 — 여기 넣으면 타임라인에서 옆으로 잘림)",
                  "확인할 이벤트", "왜 중요한지 — 확인되면/무너지면 투자논리에 어떤 영향", "high_또는_mid"]],
  "checkpoint_note": "체크포인트 중 핵심 1~2개가 사실상 투자논리 전부라는 걸 짚는 한 문장",
  "lynch": {{
    "story": "피터 린치식 '2분 설명' — 이 회사가 무엇으로 돈을 벌고, 지금 무엇이 달라지고 있는지 3문장. 숫자 1~2개 포함, 수식어 금지",
    "must_happen": ["이 이야기가 맞으려면 일어나야 할 일 3개 — 확인 가능한 사건·숫자·시점으로(예: '2026년 Q4 Merlin.01 발사 성공')"],
    "breaks_if": ["이야기가 깨졌다고 판단할 신호 3개 — 역시 확인 가능한 형태로(예: '수주잔고 2분기 연속 감소')"]
  }}
}}

규칙: facts·quotes·checkpoints 전부 원문(공시·어닝콜)에 실제 언급된 내용만. checkpoints는
경영진이 실제로 언급한 로드맵/가이던스에서 도출 — 없는 이벤트를 지어내지 말 것. 개수는
facts 4~8개, quotes 1~3개, checkpoints 4~7개.
facts의 "내용" 칸은 표 한 줄에 들어가야 하므로 반드시 짧은 구로 쓸 것 — 예시(길이 참고):
"주권국 방위고객에 궤도상 NewSat 위성 소유권 이전" (O, 구) vs
"2026년 1분기 총 매출은 전년 동기 대비 755% 증가한" (X, 문장이고 숫자가 금액칸과 중복)
— 금액·수치는 "금액·수치" 칸에만 쓰고 "내용" 칸에서 반복하지 말 것.

[실적 공시 원문]
{body}

[어닝콜 하이라이트]
{transcript}
"""


# ── 3b. LLM 호출 C: 재무3표 해석 + CANSLIM N 참고자료 (숫자는 이미 계산됨) ─
NOTES_PROMPT = """당신은 기관 애널리스트입니다. {company}({ticker})의 최근 5개 회계연도
재무 수치(이미 계산됨, 아래 표)를 보고 해석 문장을 한국어로 쓰세요. 클리셰 금지,
표에 있는 숫자를 실제로 인용할 것. 개조식("~함/~됨/~중")으로 — "~습니다/~합니다" 금지
(예: "마진 압박이 심화되고 있습니다"(X) → "마진 압박 심화"(O)). 아래 표는 이미 $M
단위인데 그대로 인용할 땐 "$XXX.XB"·"$XXX.XM"로 변환해서 쓸 것(예: 표의 416,161.0 →
"$416.2B"(O), "416,161.0백만 달러"(X) — 표 단위를 그대로 베끼지 말 것). 순수 JSON만 출력:

{{
  "income_note": "손익계산서 해석 2~3문장 — 매출성장·마진 추세",
  "balance_note": "대차대조표 해석 2~3문장 — 현금·자본 추세",
  "cashflow_note": "현금흐름표 해석 2~3문장 — 영업현금흐름 추세",
  "canslim_n_detail": {{
    "글로벌 탑티어": "이 회사가 속한 산업에서의 위치 1문장",
    "20%+ 성장 가능 연수": "성장 지속 가능성에 대한 근거 1문장",
    "경쟁기업 수": "주요 경쟁사 구도 1문장",
    "지배구조 개편": "최근 지배구조 변화가 있으면 1문장, 없으면 '해당 없음'",
    "New Market CAGR": "이 회사가 진출한 신규시장이 있으면 1문장, 없으면 '해당 없음'"
  }}
}}

규칙: 표에 있는 숫자만 인용, 지어내지 말 것. 표에 없는 내용은 회사 개요를 참고해 합리적 범위에서만.

[회사 개요]
{profile}

[연간 재무 요약 ($M)]
{table}
"""


# ── LLM 출력 후처리: 금액 단위 강제 통일 ────────────────────────────────
_MONEY_UNITS = {'조': 1e12, '억': 1e8, '천만': 1e7, '백만': 1e6}
_MONEY_RE = re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만)\s*달러')


def _fmt_usd(v: float) -> str:
    for div, suf in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M')):
        if abs(v) >= div:
            return f'${v/div:.1f}{suf}'
    return f'${v:,.0f}'


def _fix_money_units(obj):
    """"130.0백만 달러"·"1.5억 달러"·"2조 달러" → "$130.0M"·"$150.0M"·"$2.0T".

    프롬프트에 "$XXX.XB/$XXX.XM만 쓸 것"을 네 군데나 박아뒀는데도 LLM이 계속 한국식
    단위로 쓴다(PLTR·TSLA·IONQ·SNDK 전부에서 재발). 단순한 표기 취향 문제가 아니라
    실제로 틀린 숫자가 된다 — "$1.5B"를 "1.5억 달러"로 쓰면 10배 차이고, 같은 카드
    안의 재무제표 표와 대놓고 어긋난다. 변환 자체는 판단이 필요 없는 기계적 작업이라
    프롬프트에 기대지 말고 파이썬에서 확정한다."""
    if isinstance(obj, str):
        def rep(m):
            try:
                return _fmt_usd(float(m.group(1).replace(',', '')) * _MONEY_UNITS[m.group(2)])
            except (ValueError, KeyError):
                return m.group(0)
        return _MONEY_RE.sub(rep, obj)
    if isinstance(obj, dict):
        return {k: _fix_money_units(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_money_units(v) for v in obj]
    return obj


def _fin_table(raw):
    ann = raw['ann_series']
    yrs = sorted(set().union(*[ann.get(k, {}).keys() for k in ('revenue', 'netinc', 'cfo', 'cash')])) or []
    yrs = yrs[-5:]
    lines = ['연도  매출  순이익  영업현금흐름  현금']
    for y in yrs:
        r = ann.get('revenue', {}).get(y)
        n = ann.get('netinc', {}).get(y)
        c = ann.get('cfo', {}).get(y)
        h = ann.get('cash', {}).get(y)
        fmt = lambda v: f'{v/1e6:,.1f}' if v is not None else '—'
        lines.append(f'{y}  {fmt(r)}  {fmt(n)}  {fmt(c)}  {fmt(h)}')
    return '\n'.join(lines)


def _call_notes(raw):
    profile_text = (raw.get('profile') or {}).get('business', '') or raw['company']
    prompt = NOTES_PROMPT.format(company=raw['company'], ticker=raw['ticker'],
                                  profile=profile_text, table=_fin_table(raw))
    client = analyzer._client()
    data = analyzer._parse(analyzer._generate(client, prompt).text)
    if data.get('_parse_error'):
        print(f'[재무해석 생성 실패] 파싱 오류 — 빈 노트로 대체: {data}')
        return {}
    return _fix_money_units(data)


# ── 3c. LLM 호출 D: 위임장 발췌 기반 CEO·RSU 정보 (10-K에 없는 것들) ─────
PROXY_PROMPT = """당신은 15년 경력의 셀사이드 애널리스트입니다. {company}({ticker})의 위임장
(DEF 14A) 발췌문에서 CEO 정보와 장기 주식보상 구조를 확인하세요. 발췌문이라 문맥이 끊길 수
있음 — 확실한 내용만 채우고 나머지는 비우세요. 모든 값은 한국어로 쓸 것(ceo_name 제외).
순수 JSON만 출력:

{{
  "ceo_name": "CEO 실명(영문 그대로) — 발췌문에서 확인되면, 안 보이면 빈 문자열",
  "ceo_since": CEO 취임연도(정수) 또는 null,
  "ceo_bio": "CEO 이전 경력·취임연도 등 실제 약력 정보 2~3문장(한국어로 요약) — 주주총회
             초대장·인사말·연혁 없이 발췌문에 진짜 약력이 있을 때만. 발췌문이 회의 안내·
             인사말 같은 약력이 아닌 내용이면(예: 'join us for the Annual Meeting') 절대
             그대로 베끼지 말고 빈 문자열로 둘 것",
  "rsu_note": "테슬라 일론 머스크 패키지처럼 '성과 조건'이 실제로 걸린 주식보상만(예:"
              " 매출목표·시총목표·기술마일스톤, 가중치, 기간). 표준 시간베스팅(예: '4년"
              " 근속')뿐이면 빈 문자열 — 정보가치 없음. 확실하지 않아도 빈 문자열.",
  "executives": [["이름(영문 그대로)", "직책(한국어, 예: 'CFO'·'COO'·'사장')",
                 "한 줄 이력 — 20자 이내(예: '前 구글 부사장', '창업 멤버'). 모르면 빈 문자열"]],
  "governance_changed": true_또는_false,
  "governance_note": "최근 3년 내 '중대한' 지배구조 변화가 발췌문에 실제로 있으면 30자 이내로"
                    " (예: '차등의결권 폐지', '창업자 이사회 의장 사임', '지주회사 전환')."
                    " 통상적인 이사 재선임·감사인 선임 같은 정기 안건은 변화가 아님 —"
                    " 그런 경우 governance_changed는 false, note는 빈 문자열."
}}

규칙: 발췌문에 명시적으로 없는 내용은 절대 만들지 말 것(추측 금지). 확실하지 않으면 빈 값으로.
발췌문 원문(특히 영어)을 그대로 복사하지 말 것 — 반드시 요약해서 한국어로.

[위임장 발췌]
{excerpt}
"""


def _call_proxy(raw):
    if not raw.get('proxy_excerpts'):
        return {}
    prompt = PROXY_PROMPT.format(company=raw['company'], ticker=raw['ticker'],
                                  excerpt=raw['proxy_excerpts'])
    client = analyzer._client()
    data = analyzer._parse(analyzer._generate(client, prompt).text)
    if data.get('_parse_error'):
        print(f'[위임장 정보 추출 실패] 파싱 오류 — 빈 값으로 대체: {data}')
        return {}
    return _fix_money_units(data)


# ── 3d. LLM 호출 G: 종합 정성 평가(SUMMARY) — 이미 확보된 사실만 종합 ────
# p05_outlook()의 "종합평가" 페이지가 읽는 필드인데, 이 파일(autogen.py)이 지금까지
# 아예 안 만들고 있었다(render_data_file 출력에 SUMMARY 자체가 없었음 — AAPL 검증
# 중 발견, 1페이지가 통째로 빈 걸 사용자가 지적함). 새 사실을 조사하는 게 아니라
# 이미 다른 LLM 호출·XBRL로 확보된 숫자만 종합하는 것이라 추측 금지 원칙과 충돌 없음.
SUMMARY_PROMPT = """당신은 15년 경력의 셀사이드 애널리스트입니다. 오늘은 {as_of}입니다.
{company}({ticker})에 대해 아래 이미 확인된 사실만 근거로 "종합 정성 평가"를 한국어
3~5줄로 쓰세요. 각 줄은 개조식("~함/~됨/~중")으로 끝나는 독립된 한 문장, 줄바꿈으로
구분. 클리셰 금지. 아래 제공된 것 외의 새로운 사실을 추가하지 말 것 — 종합·해석만 할 것.

금액 표기(중요): 반드시 "$XXX.XB"·"$XXX.XM" 형식만 쓸 것. 한국식 억/조 단위 절대 금지 —
"28.6억 달러"(X) → "$2.9B"(O). 아래 표는 $M 단위이므로 1,000 이상이면 B로 바꿔 쓸 것
(예: 표의 2,866.0 → "$2.9B"). 단위를 잘못 쓰면 같은 카드의 재무제표 표와 숫자가 어긋난다.

시제 주의: 아래 표의 연도가 오늘({as_of}) 기준으로 이미 지난 회계연도면 반드시 과거형
("~함/~됨")으로 쓸 것 — "2025년에 반등할 것으로 전망됨"(X, 2025년이 이미 지났는데
미래형) → "2025년 반등함"(O). 아직 안 온 연도(예: 2027년)만 미래·전망형 허용.

포함할 내용(가능한 범위에서 자연스럽게): 이 회사가 어떤 사업으로 돈을 버는지, 최근
매출/이익 추세, 밸류에이션이 싼지 비싼지에 대한 판단(멀티플 추세 근거), 지금 가장
중요한 리스크나 변수. 좋은 점과 우려되는 점을 균형 있게 — 한쪽으로 치우친 홍보성
요약 금지.

순수 JSON만 출력: {{"summary": "줄1\\n줄2\\n줄3"}}

[회사 개요]
{profile}

[최근 실적 핵심]
{kpis}

[연간 매출·이익 추세 ($M)]
{fin_table}

[밸류에이션]
{valuation}

[핵심 체크포인트]
{checkpoints}
"""


def _call_summary(raw, recent, notes=None):
    profile_text = (raw.get('profile') or {}).get('business', '') or raw['company']
    kpis = recent.get('facts') or []
    kpi_text = '\n'.join(f'- {f[0]}: {f[1]} ({f[2]})' for f in kpis[:6]) or '(없음)'
    cons = raw.get('cons') or {}
    mc, tm, price = cons.get('market_cap'), cons.get('target_mean'), cons.get('price')
    val_parts = []
    if price:
        val_parts.append(f'현재가 ${price:.2f}')
    if tm and price:
        val_parts.append(f'애널리스트 목표주가 ${tm:.2f} ({(tm / price - 1) * 100:+.0f}%)')
    if mc:
        val_parts.append(f'시가총액 ${mc / 1e9:.1f}B')
    cps = recent.get('checkpoints') or []
    cp_text = '\n'.join(f'- {c[1]}: {c[2]}' for c in cps[:3]) or '(없음)'
    prompt = SUMMARY_PROMPT.format(company=raw['company'], ticker=raw['ticker'],
                                   as_of=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                                   profile=profile_text, kpis=kpi_text, fin_table=_fin_table(raw),
                                   valuation=' · '.join(val_parts) or '(컨센서스 없음)', checkpoints=cp_text)
    try:
        client = analyzer._client()
        data = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[종합평가 생성 실패] {e}')
        return ''
    if data.get('_parse_error'):
        print(f'[종합평가 생성 실패] 파싱 오류: {data}')
        return ''
    return _fix_money_units(data.get('summary') or '')


def _call_recent(raw):
    tx = raw['transcript']
    tx_text = json.dumps(tx, ensure_ascii=False, indent=1) if tx else '(어닝콜 하이라이트 없음)'
    body = raw['earnings_text'][:ir.TEXT_LIMIT] if raw['earnings_text'] else '(실적 공시 본문 추출 실패)'
    prompt = RECENT_PROMPT.format(company=raw['company'], ticker=raw['ticker'], body=body, transcript=tx_text)
    client = analyzer._client()
    data = analyzer._parse(analyzer._generate(client, prompt).text)
    if data.get('_parse_error'):
        raise SystemExit(f'[최근실적 생성 실패] 파싱 오류: {data}')
    return _fix_money_units(data)


# ── 4. 결정론적 숫자 (LLM 없이 XBRL·Yahoo에서 직접) ───────────────────────
def _kpi_rows(raw):
    """RESULTS.kpis — 매출/영업이익/순이익/영업현금흐름/현금, 전년동기 대비. LLM 미사용.

    S.qoq_yoy()의 yoy는 cur/prior 비율 기반이라 적자가 적자로 더 깊어질 때(둘 다 음수,
    비율은 1보다 커짐) "+259% YoY"처럼 실제로는 악화인데 양수·상승 화살표로 나오는
    버그가 실제로 있었다(IONQ 검증: 영업손실 -$75.7M→-$271.5M을 "+259%"로 표시).
    canslim.py의 growth_pct()가 이미 쓰는 (cur-prior)/|prior| 방식으로 통일 — 이건
    부호가 바뀌어도 "값이 늘었나 줄었나"를 항상 올바르게 반영한다."""
    labels = {'revenue': '매출', 'opinc': '영업이익', 'netinc': '순이익', 'cfo': '영업현금흐름', 'cash': '현금'}
    rows = []
    for key, label in labels.items():
        series = raw['qtr_series'].get(key, {})
        ends = sorted(series)
        if not ends:
            continue
        cur = series[ends[-1]]
        ly = f'{int(ends[-1][:4]) - 1}{ends[-1][4:]}'
        prior = series.get(ly)
        if prior is None:
            cands = [e for e in ends if e[:4] == ly[:4] and e[5:7] == ly[5:7]]
            prior = series[cands[0]] if cands else None
        yoy = ((cur - prior) / abs(prior) * 100) if prior else None
        chg = f'{yoy:+.0f}% YoY' if yoy is not None else '—'
        # 방향 표시는 "값이 늘었나 줄었나"만 본다 — "적자 축소가 좋은 신호"류 판단은
        # 종목 맥락에 따라 다르므로(성장기 투자 확대 vs 실적 부진) 여기서 함부로 안 한다.
        direction = 'up' if (yoy or 0) > 0 else ('dn' if (yoy or 0) < 0 else 'flat')
        val = f'${cur/1e6:,.1f}M' if abs(cur) < 1e9 else f'${cur/1e9:,.2f}B'
        rows.append((label, val, chg, direction))
    return rows


def _latest_revenue_m(raw):
    """가장 최근 분기 매출($M) — 세그먼트 pct를 실제 금액으로 환산하는 데만 사용."""
    series = raw['qtr_series'].get('revenue', {})
    if not series:
        return None
    cur, _, _ = S.qoq_yoy(series)
    return (cur / 1e6) if cur is not None else None


# ── 5. 파일 렌더 — 사람이 쓴 것과 동일한 형식의 .py 소스로 출력 ───────────
# ── 5b. 재생성 시 사람이 보정한 값 보존 ────────────────────────────────
# autogen.py를 다시 돌리면 손으로 채운 값(예: IONQ의 실제 RSU 성과조건, AAPL의 창업연도)이
# 통째로 날아갔다. 그래서 "고쳤는데 다음에 또 원위치"가 반복됐다. 두 겹으로 막는다:
#   ① 데이터 파일의 LOCKED 목록 — 사람이 "이건 확정"이라고 박은 필드는 절대 안 덮어씀.
#   ② 무조건 손실 방지 — LOCKED에 없어도, 새 값이 비었는데 옛 값이 있으면 옛 값을 지킴.
# 반대로 시간이 지나면 반드시 바뀌어야 하는 것(실적·체크포인트·종합평가·가격)은 이 보존
# 대상에서 제외한다 — 그건 낡은 값을 지키는 게 오히려 사고다.
def _dotted(mod, path, default=None):
    cur = getattr(mod, path.split('.')[0], None) if mod else None
    for k in path.split('.')[1:]:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def _blank(v):
    return v is None or v == '' or v == [] or v == {} or v == 0


def _module_name(ticker: str) -> str:
    """이 티커의 데이터 모듈 이름 — build.py가 실제로 렌더에 쓰는 것과 반드시 같아야 한다.

    SATL은 손으로 만든 파일이 `satl16_data.py`인데 autogen은 `satl_data.py`에 썼다.
    그래서 `autogen.py SATL`을 돌려도 `build.py SATL`은 예전 파일을 렌더했다 — "고쳤는데
    반영이 안 된다"의 조용한 원인. build.TICKERS에 등록된 모듈명을 그대로 따른다."""
    try:
        import build
        cfg = build.TICKERS.get(ticker.upper())
        if cfg and cfg.get('data_module'):
            return cfg['data_module']
    except Exception:
        pass
    return f'{ticker.lower()}_data'



HISTORY_DIR = OUT_DIR / 'history'


def _archive(ticker: str, path):
    """덮어쓰기 전에 직전 데이터 파일을 decks/history/ 로 복사해 둔다.

    재생성 결과가 직전과 뭐가 다른지 볼 방법이 없었다. 파일은 하나뿐이고
    덮어쓰니, 새로 만든 게 실제로 뭘 바꿨는지 확인하려면 git 이력을 뒤져야 했다
    (러너가 자동 커밋한 것들 사이에 섞여 찾기 어렵다).

    이름에 **티커와 직전 생성일**을 넣는다 — 같은 날 두 번 돌리면 덮어쓰는데,
    그날의 최신본만 남기면 되므로 의도된 동작이다.

    ⚠️ 용량: 데이터 파일 하나는 10~30KB다. 렌더된 13장 PNG(종목당 수 MB)는
       여기 넣지 않는다 — 그건 언제든 build.py 로 다시 그릴 수 있고,
       쌓이면 예전에 정리한 용량이 그대로 되돌아온다.
    """
    if not path.exists():
        return
    try:
        import re as _re
        txt = path.read_text(encoding='utf-8')
        m = _re.search(r"^BUILT_AT\s*=\s*'([\d-]+)'", txt, _re.M)
        stamp = (m.group(1) if m else 'unknown').replace('-', '')
        HISTORY_DIR.mkdir(exist_ok=True)
        dest = HISTORY_DIR / f'{ticker.lower()}_{stamp}_data.py'
        dest.write_text(txt, encoding='utf-8')
        print(f'[{ticker}] 직전본 보관: {dest.name}')
    except Exception as e:
        # 보관 실패가 생성을 막으면 안 된다 — 보관은 편의지 필수가 아니다.
        print(f'[{ticker}] 직전본 보관 실패(계속 진행): {e}')

def load_existing(ticker: str):
    """이미 있는 데이터 모듈을 읽어온다(없으면 None)."""
    import importlib
    try:
        m = importlib.import_module(_module_name(ticker))
        return importlib.reload(m)
    except Exception:
        return None


def _merger(prev, fresh: bool = False):
    """재생성 시 옛 값을 얼마나 지킬지 정한다.

    fresh=False(기본) — 빈 값 보호를 켠다. 새로 뽑은 값이 비면 옛 값을 지킨다.
    fresh=True         — 빈 값 보호를 **끈다**. LOCKED(사람이 확정한 값)만 지키고
                         나머지는 이번 추출 결과 그대로 간다. 비면 빈 채로 남는다.

    ⚠️ fresh 를 기본으로 두지 않는 이유: 추출이 한 번 실패하면 그 페이지가 통째로
       비고, autogen 은 하루 2회 상한이라 그날 안에 되돌리기 어렵다.
       반대로 기본(병합)의 대가는 **낡은 값이 새 값인 척 남는 것**이다. 그래서
       무엇이 보존됐는지를 파일에 CARRIED_OVER 로 적어 눈에 보이게 만든다
       (예전엔 콘솔에만 찍혀서 러너에서 돌면 아무도 못 봤다).
    """
    locked = set(getattr(prev, 'LOCKED', []) or []) if prev is not None else set()
    kept, carried = [], {}
    prev_built = str(getattr(prev, 'BUILT_AT', '') or '') if prev is not None else ''

    def pick(path, new):
        old = _dotted(prev, path)
        if path in locked and not _blank(old):
            kept.append(f'{path}(LOCKED)')
            carried[path] = 'LOCKED'
            return old
        if not fresh and _blank(new) and not _blank(old):
            kept.append(path)
            carried[path] = prev_built or '이전 생성분'
            return old
        return new
    pick.kept = kept
    pick.carried = carried
    pick.locked = locked
    return pick


def render_data_file(ticker: str, raw: dict, static: dict, recent: dict, notes: dict = None,
                     peers: dict = None, price_moves: list = None, summary: str = '',
                     tam_estimates: list = None, tam_cagr=None, canslim_n: dict = None,
                     canslim_detail: dict = None, prev=None, fresh: bool = False) -> str:
    notes = notes or {}
    pick = _merger(prev, fresh=fresh)
    peers = peers or {}
    price_moves = price_moves or []
    tam_estimates = tam_estimates or []
    company = raw['company']
    # 날짜는 셋이 서로 다르고, 하나로 뭉치면 반드시 거짓말이 된다(2026-08-19 실측).
    #   built_at  초안을 만든 날 — 게이트의 신선도 판정·차트의 '올해'가 이걸 본다.
    #   as_of     이 리포트가 반영한 최신 실적 공시일 — 표지에 찍혀 독자가 보는 날짜.
    #   가격 날짜  렌더할 때마다 달라지므로 여기 안 적는다(deck_pages._px_asof가 유도).
    built_at = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    as_of = ((raw.get('earnings') or {}).get('date')
             or (raw.get('annual') or {}).get('date') or built_at)
    src_earnings = f"{raw['earnings']['form']} 공시({raw['earnings']['date']})" if raw['earnings'] else '실적 공시'
    src_annual = f"{raw['annual']['form']}({raw['annual']['date']} 제출)"

    emp_count = pick('HISTORY.employees', static.get('employee_count'))
    if isinstance(emp_count, list):     # 보존된 옛 값은 [(기준일, 인원)] 형태
        emp_count = (emp_count[-1][1] if emp_count and len(emp_count[-1]) > 1 else None)
    emp_asof = static.get('employee_count_asof') or src_annual
    emp_src = f'{emp_asof} 공식 집계' if emp_count else '[자동생성] 확인 필요'

    # 가격변동 구간(자동탐지+뉴스RSS 기반 이유) — 차트 배지용 짧은 라벨과 카드용
    # 상세 항목(PRICE_MOVES) 둘 다 여기서 만든다.
    arrow_kr = {'up': '▲', 'down': '▼'}
    # 라벨을 f-string 안에서 또 f-string으로 만들면 같은 따옴표가 중첩되는데,
    # 그 문법은 Python 3.12(PEP 701)부터만 된다. GitHub Actions 러너는 3.11이라
    # 여기서 SyntaxError가 나 autogen이 통째로 죽었다(폰에서 /report CORT 실패).
    # 로컬 3.14로는 통과해서 안 보였던 자리라, 라벨을 먼저 만들어 두고 꽂는다.
    annot_lines = ',\n        '.join(
        '({}, {}, {!r})'.format(mv['yr'], mv['mo'],
                                '{} {} 변동'.format(mv['no'], mv['pct']))
        for mv in price_moves)
    moves_lines = ',\n    '.join(
        f'{{"no": {mv["no"]}, "dir": {mv["dir"]!r}, "period": {mv["period"]!r}, '
        f'"pct": {mv["pct"]!r}, "range": {mv["range"]!r}, "reason": {mv["reason"]!r}}}'
        for mv in price_moves)

    timeline = pick('HISTORY.timeline', static.get('timeline') or [])
    timeline_lines = ',\n        '.join(
        f'({t[0]!r}, {t[1]!r}' + (f', {bool(t[2])!r})' if len(t) > 2 and t[2] else ')')
        for t in timeline)

    segments = static.get('segments') or []
    total_rev_m = _latest_revenue_m(raw)
    # pct만 원문 근거가 있고 부문별 절대매출·전년동기는 없음 — 전사 최근분기매출×pct로
    # 절대값을 역산하고, prior=cur로 둬 렌더러의 (cur-prior)/prior 나눗셈이 0으로
    # 나뉘어 죽는 걸 막는다(0% YoY로 표시되지만 note에서 "확인 필요" 명시).
    def _seg_rev(pct):
        # 비중을 모르면 절대매출도 모른다 — 0.0으로 채우면 "매출 0"이라는 거짓
        # 주장이 된다. None을 그대로 넘겨 렌더러가 정직하게 생략하게 한다.
        if total_rev_m is None or pct is None:
            return None
        return round(total_rev_m * pct / 100, 1)
    # 이 문구는 5p 카드에 그대로 찍힌다 — 예전 기본값이 "[자동생성] ... 채워넣기 필요"라
    # 검수용 내부 표시가 그대로 발행물에 노출됐다(실제 발생). 독자에게 의미 있는
    # 출처·한계 설명으로 바꾼다.
    seg_note = ('부문 비중은 최근 분기 공시 기준, 절대금액은 전사 매출×비중으로 환산한 값 — '
                '부문별 전년동기 비교는 공시에 없어 미표시'
                if segments else '공시에 부문별 매출 구분이 없어 전사 매출로만 표시')
    # 비중을 모를 때(LLM이 null을 준 경우) 0으로 바꿔 쓰면 안 된다. 0은 "이 부문
    # 매출이 0이다"라는 **사실 주장**이고, None은 "모른다"다. ABCL에서 두 부문이
    # 전부 0.0으로 찍혀 렌더러가 "부문별 비중 데이터 없음"으로 숨겼는데, 실제로는
    # Partner-led가 전사 매출의 100%였다 — 아는 값을 0으로 감춘 셈이다.
    # 이 프로젝트에서 반복해 나온 버그 클래스(유령 0-막대, 히트맵 None 표시)와 같다.
    seg_by_line = ', '.join(f'({s[0]!r}, {_seg_rev(s[2])}, {s[2]!r})' for s in segments)
    # 네 번째 값은 '전년동기 매출'인데 공시에서 못 얻는다. 예전엔 prior=cur로 채워
    # 렌더러가 "(+0%)"라는 있지도 않은 증감률을 찍었다(실제로 성장한 부문에도 +0%) —
    # 0으로 두면 렌더러의 `if cur and prior` 가드에 걸려 증감률 자체를 안 그린다.
    seg_detail = ',\n        '.join(
        f'({s[0]!r},\n         {s[1]!r}, {_seg_rev(s[2])}, 0)' for s in segments)

    kpis = _kpi_rows(raw)
    kpi_lines = ',\n        '.join(repr(k) for k in kpis)

    # p03_holders()가 LEADERSHIP['ceo']['name'].split()[-1]을 호출 — 빈 문자열이면
    # IndexError로 렌더가 통째로 죽는다. 원문에서 못 뽑았으면 최소 자리표시자라도 넣는다.
    ceo_name = pick('LEADERSHIP.ceo.name', static.get('ceo_name')) or '(CEO 성명 확인 필요)'
    # 예전엔 취임연도를 못 찾으면 `or static['listed_year']`로 상장연도를 대신 넣었다 —
    # 그러면 4p에 "2020년부터 6년째 재임 중"이라고 **확인된 적 없는 사실이 단정형으로**
    # 찍힌다. 모르면 0으로 두고 렌더러가 "재임연도 미확인"으로 표시하게 하는 게 맞다.
    ceo_since = pick('LEADERSHIP.ceo.since', static.get('ceo_since')) or 0
    ceo_bio = pick('LEADERSHIP.ceo.bio', static.get('ceo_bio', ''))
    # 병합(pick) 뒤에 한 번 더 접지한다. 생성 단계에서 지어낸 약력을 버려 빈 값이
    # 되면, pick이 "새 값 없음"으로 보고 **옛 파일의 지어낸 약력을 복원**한다.
    # ABCL에서 실제로 그랬다 — 새 환각(AgJunction)은 걸렀는데 옛 환각(Alnylam)이
    # 되살아났다. 최종 값에도 같은 잣대를 대야 한 번 걸러진 게 다시 안 들어온다.
    ceo_bio = _ground_bio(ceo_bio, raw.get('proxy_excerpts') or raw.get('annual_text') or '')
    if not ceo_bio:
        # 산문 약력을 버렸으면 빈칸으로 두지 말고 공시에서 확인되는 사실로 채운다.
        # 위임장 발췌가 보상 조항 위주라 약력 문장 자체가 없는 회사가 많아(ABCL 실측)
        # 인용조차 불가능하다 — 지어내느니 '보유 주식수' 같은 확인 가능한 사실이 낫다.
        try:
            import officers as _off
            ceo_bio = _off.profile_line(raw['cik'], ceo_name) or ''
            if ceo_bio:
                print(f'[{ticker}] CEO 약력 결정론 대체(LLM 0콜): {ceo_bio}')
        except Exception as _e:
            print(f'[{ticker}] CEO 약력 대체 실패: {_e}')

    # 경영진 명단 — 예전엔 전 종목 영구히 빈 배열이었다(4p "내용이 부실"의 직접 원인).
    # 위임장 발췌에서 뽑은 [이름, 직책, 한 줄 이력]을 그대로 싣되, CEO 본인은 이미 위
    # 프로필 카드에 크게 나오므로 중복 제거.
    execs = [tuple(e[:3]) for e in (static.get('executives') or [])
             if isinstance(e, (list, tuple)) and len(e) >= 2 and e[0]
             and e[0].split()[-1].lower() not in (ceo_name or '').lower()][:5]
    execs = pick('LEADERSHIP.people', execs)
    exec_lines = ',\n        '.join(repr(tuple(e)) for e in execs)

    # 상장연도 폴백 — LLM이 못 잡아도 SEC 상장일(formerNames)이나 실제 시세 첫 해로
    # 채울 수 있다. 0으로 넘기면 3p에 "상장 0년 · 2027년차"라는 헛소리가 찍힌다
    # (창업→상장→CEO재임 순으로 세 번 재발한 그 버그).
    # 우선순위가 중요하다. LLM이 10-K 본문에서 뽑은 연도는 자주 틀린다 — PLTR 실측:
    # 2020-09-30 NYSE 직상장인데 `listed_year: 2011`을 반환했고, 그 결과 같은 페이지
    # 안에서 타일은 "2011년 상장 · 16년차"인데 바로 아래 차트는 2020.09부터 시작하고
    # CAGR 라벨도 "2011년 상장 종가 대비"라는 거짓말이 됐다. **실제 거래 시세가 시작된
    # 해**는 하드 팩트이므로 그걸 1순위로 쓰고, LLM 값은 시세가 없을 때만 쓴다.
    px_year = None
    prows = (raw.get('ohlcv') or {}).get('rows') or []
    if prows:
        try:
            px_year = datetime.fromtimestamp(prows[0][0], timezone.utc).year
        except (TypeError, ValueError, OSError, IndexError):
            px_year = None
    sec_year = None
    ld = (raw.get('listing_date') or '')[:4]
    if ld.isdigit():
        sec_year = int(ld)
    llm_year = static.get('listed_year')
    listed_year = px_year or sec_year or llm_year or 0
    if px_year and llm_year and abs(px_year - llm_year) > 1:
        print(f'[{ticker}] 상장연도 불일치 — 10-K 추출 {llm_year} vs 실제 시세 시작 {px_year}: '
              f'시세를 채택(차트·CAGR과 같은 근거를 쓰기 위함)')
    listed_year = pick('HISTORY.listed', listed_year)
    # SEC formerNames 기반 상장일도 같은 이유로 검증한다 — PLTR은 개명 이력 1건이
    # 2011년이라 '2011-09-07'이 상장일로 잡혔는데 실제 상장은 2020-09-30이다. 시세
    # 시작연도와 1년 넘게 어긋나면 상장일로 쓰지 않는다(차트 구간 필터로도 쓰이는 값).
    listing_date = raw.get('listing_date') or ''
    if listing_date and px_year and abs(int(listing_date[:4]) - px_year) > 1:
        listing_date = ''
    founded_year = pick('HISTORY.founded', static.get('founded_year') or 0)

    # 비전문가용 3줄 — "이 회사 뭐 하는 회사인가"(무엇을 파나 / 누가 사나 / 어떻게 버나).
    business = [str(b) for b in (static.get('business_model') or []) if str(b).strip()][:3]
    business = pick('BUSINESS', business)
    business_lines = ',\n    '.join(repr(b) for b in business)

    facts = recent.get('facts') or []
    fact_lines = ',\n        '.join(repr(tuple(f)) for f in facts)

    quotes = recent.get('quotes') or []
    quote_lines = ',\n        '.join(repr(tuple(q)) for q in quotes)

    checkpoints = recent.get('checkpoints') or []
    cp_lines = ',\n    '.join(repr(tuple(c)) for c in checkpoints)

    # 기본 문구가 "자동생성 초안 — … 확인 필요"였는데 이게 4p 카드에 그대로 찍혔다.
    # 검수용 내부 표시를 발행물에 노출하지 말 것 — 못 찾았으면 못 찾았다고 독자에게
    # 말이 되는 문장으로 쓴다.
    dilution_note = pick('SHARES.note', static.get('dilution_note')) or \
        '연차보고서에서 전환사채·워런트 등 별도 희석요인은 확인되지 않음'
    tam_note = pick('TAM.note', static.get('tam_note')) or ''
    tam_estimates = pick('TAM.estimates', tam_estimates)
    # TAM 라벨도 늘 빈 문자열이라 5p 헤더가 "시장규모"만 덩그러니 떴다 —
    # LLM이 이미 준 영어 산업 카테고리로 채운다(예: 'quantum computing 시장').
    tam_label = pick('TAM.label', (f'{static["industry_en"]} 시장'
                                   if static.get('industry_en') else ''))
    if tam_estimates:
        # 구글뉴스 검색으로 실제 찾은 시장조사기관 헤드라인 기반(지어낸 값 아님) —
        # 기관마다 시장 정의가 크게 달라 편차가 흔하다는 걸 명시.
        est_lines = ',\n        '.join(repr(tuple(e)) for e in tam_estimates)
        tam_block = (
            f"    'estimates': [   # 구글뉴스 검색(시장조사기관 보도자료 헤드라인)에서 실제 추출 — 지어낸 값 아님\n"
            f"        {est_lines}\n"
            f"    ],\n"
            f"    'note': {tam_note!r} or '기관마다 시장 정의·방법론이 달라 추정치 편차가 큼 — 참고용',\n"
        )
    else:
        tam_block = (
            f"    'estimates': [],  # ⚠️ 자동생성: 뉴스 검색에서도 명확한 시장규모 숫자를 못 찾음\n"
            # ⚠️ 예전 폴백은 '시장규모 리서치 필요 …' 였다. 그런데 check.py 의 자리표시자
            #    금지어 목록에 '리서치 필요' 가 들어 있어서, **TAM 을 못 찾은 종목은
            #    autogen 이 만드는 순간 영구 발행 불가**가 됐다. 같은 레포의 두 모듈이
            #    서로 싸운 것이다(2026-09-11 LMB 실측: 차단 1건이 이것뿐이었다).
            #    못 찾았으면 카드에 아무 말도 안 쓴다 — estimates 가 비면 렌더러가
            #    그 섹션을 통째로 생략하고, '없다'는 사실은 check 의 INFO 로 남는다.
            f"    'note': {tam_note!r} or '',\n"
        )

    # CANSLIM C·A는 render 시점에 XBRL로 라이브 계산됨(canslim.py) — 여기 필요한 건 N뿐.
    # 예전엔 5개 항목 중 competitors만 채우고 나머지를 0/None으로 비워뒀는데, 그러면
    # 종목마다 사람이 손으로 채워야 했다. 지금은 _score_canslim_n()이 근거와 함께
    # 계산해서 넘겨준다(계산 불가한 것만 0 — 여전히 지어내지는 않음).
    canslim_n = canslim_n or dict(top_tier=0, growth_years=0,
                                  competitors=len(static.get('competitors') or []),
                                  governance=0, market_cagr=None)
    canslim_n = pick('CANSLIM_N', canslim_n)
    # LLM 서술(notes)과 계산 근거(canslim_detail)를 합친다 — 계산 근거가 우선.
    canslim_n_detail = dict(notes.get('canslim_n_detail') or {})
    canslim_n_detail.update({k: v for k, v in (canslim_detail or {}).items() if v})
    canslim_n_detail = pick('CANSLIM_N_DETAIL', canslim_n_detail)
    _unscored = [k for k, v in (('글로벌 탑티어', canslim_n.get('top_tier')),
                                ('성장 가능 연수', canslim_n.get('growth_years')),
                                ('신시장 CAGR', canslim_n.get('market_cagr'))) if not v]
    canslim_note = pick('CANSLIM_NOTE',
                        ('N은 계산 가능한 항목만 자동 채점 — 각 항목의 근거는 위 표에 그대로 표기함.'
                         + (f' 근거를 못 찾아 0점 처리한 항목: {", ".join(_unscored)}.' if _unscored else '')))

    src = f'''# -*- coding: utf-8 -*-
"""{ticker} 딥리포트 데이터셋 — autogen.py 자동 초안(⚠️ 검수 전 발행 금지).

TECH·VALUATION·QUANT 섹션은 라이브 계산이라 이 파일엔 없음
(deck_pages.py의 live.technical_snapshot / _valuation_note / _quant_note 참고).

생성: autogen.py, {built_at} (반영 공시 {as_of})
출처 코드
  ANNUAL = {src_annual}
  EARN   = {src_earnings}
  YF     = Yahoo Finance 비공식 chart API
"""

AS_OF = {as_of!r}          # 반영한 최신 실적 공시일(표지 라벨)
BUILT_AT = {built_at!r}       # 초안 생성일(신선도 게이트·차트 기준연도)
# PRICE_ASOF 는 더 쓰지 않는다 — 가격은 렌더 시점에 새로 받아오므로 날짜도 그때 유도한다.
# 여기 박아두면 최신 가격에 옛 날짜가 붙는다(TSLA 실측 25일, 발행된 IONQ 11일 어긋남).

SRC = {{
    'PR': {src_earnings!r},
    'DECK': {src_earnings!r},
    'YF': 'Yahoo Finance chart API',
}}

COMPANY = {{'ticker': {ticker.upper()!r}, 'name': {company!r}, 'exchange': {pick('COMPANY.exchange', raw.get('exchange', ''))!r},
           'sector': {pick('COMPANY.sector', static.get('sector', ''))!r}, 'cik': {raw['cik']!r}}}

# 이 필드는 autogen.py를 다시 돌려도 덮어쓰지 않는다 — 사람이 확인·보정한 값을 지키는
# 장치. 검수하다가 "이 값은 이게 맞다"고 확정한 필드의 경로를 여기 추가하면 된다.
# (경로 형식: 'HISTORY.founded', 'LEADERSHIP.ceo.bio', 'TAM.estimates' …)
# 여기 없어도, 새로 뽑은 값이 비었는데 기존 값이 있으면 기존 값이 자동으로 유지된다.
LOCKED = {sorted(getattr(prev, 'LOCKED', []) or [])!r}

# 이번 재생성에서 **새로 뽑지 못해 옛 값을 그대로 쓴** 필드와, 그 값이 만들어진 날.
# 비어 있으면 이 파일의 모든 값이 이번 생성분이라는 뜻이다.
# 예전에는 이 정보가 콘솔에만 찍혀서, 파일은 BUILT_AT=오늘 인데 내용의 절반이
# 한 달 전 값인 상태를 아무도 알 수 없었다(러너 실행분은 로그도 안 본다).
# 완전히 새로 뽑고 싶으면: python decks/autogen.py TICKER --fresh
CARRIED_OVER = '__CARRIED_OVER__'

# 비전문가용 3줄 — 무엇을 파나 / 누가 사나 / 어떻게 돈을 버나. 1p 종합평가 맨 위에 뜬다.
BUSINESS = [
    {business_lines}
]

# ⚠️ 자동생성 초안 — 아래 전 항목 사람 검수 필요(특히 timeline·note류)
HISTORY = {{
    'founded': {founded_year!r},
    'listed': {listed_year!r},
    'listing_type': {pick('HISTORY.listing_type', static.get('listing_type', ''))!r},
    'listing_date': {listing_date!r},
    'founders': {pick('HISTORY.founders', static.get('founders', ''))!r},
    'timeline': [
        {timeline_lines}
    ],
    'employees': [({emp_asof!r}, {emp_count or 0!r})],
    'employee_src': {emp_src!r},
    'chart_annotations': [
        {annot_lines}
    ],
    'note': {pick('HISTORY.note', static.get('history_note', ''))!r},
}}

# 급등/급락 구간 자동탐지(가격만) + 과거 뉴스RSS 검색(구글뉴스 after:/before: 연산자,
# API 키 불필요)으로 이유 추정 — reason이 "단일 계기 미확인"이면 뉴스에서 명확한
# 계기를 못 찾았다는 뜻(지어내지 않음).
PRICE_MOVES = [
    {moves_lines}
]

# 경쟁사 CIK — 10-K 언급 이름 중 시총이 비슷한 자릿수(0.05~20배)인 후보만 자동 매칭
# (판단이 필요한 부분을 시총비교라는 결정론적 기준으로 대체). 후보가 없으면 빈 dict —
# 그러면 사업부문 페이지의 경쟁사 비교 섹션이 조용히 생략됨(가짜 비교 안 보여줌).
# 'ciks'는 build.py가 자동등록 시 peers=로 그대로 넘길 CIK 맵.
PEERS = {{
    'names': {{{', '.join(f'{tk!r}: {info["name"]!r}' for tk, info in peers.items())}}},
    'ciks': {{{', '.join(f'{tk!r}: {info["cik"]!r}' for tk, info in peers.items())}}},
}}

# build.py 자동등록용 메타(웹사이트·CEO명) — 로고·CEO 사진 검색에 쓰임.
SITE = {(raw.get('site') or '')!r}

LEADERSHIP = {{
    'ceo': {{'name': {ceo_name!r}, 'role': 'CEO', 'since': {ceo_since!r},
            'bio': {ceo_bio!r}}},
    # 위임장(DEF 14A) 'Executive Officers' 대목에서 자동 추출 — 못 찾으면 빈 배열이고
    # 그러면 4p의 '주요 경영진' 표가 통째로 생략된다(가짜 명단 안 만듦).
    'people': [
        {exec_lines}
    ],
    'note': {pick('LEADERSHIP.note', static.get('leadership_note', ''))!r},
    'rsu_note': {pick('LEADERSHIP.rsu_note', static.get('rsu_note', ''))!r},
}}

SHARES = {{
    'note': {dilution_note!r},
    'dilution': {pick('SHARES.dilution', [])!r},
    'src': SRC['PR'],
}}

SEGMENTS = {{
    'by_line': [{seg_by_line}],
    'detail': [
        {seg_detail}
    ],
    'by_geo': {pick('SEGMENTS.by_geo', [])!r},
    'competitors': {pick('SEGMENTS.competitors', static.get('competitors', []))!r},
    'note': {pick('SEGMENTS.note', seg_note)!r},
    'src': SRC['DECK'],
}}

RESULTS = {{
    'period': {recent.get('period', '')!r},
    'kpis': [
        {kpi_lines}
    ],
    'facts': [
        {fact_lines}
    ],
    'quotes': [
        {quote_lines}
    ],
    'src': SRC['PR'],
}}

# C·A는 canslim.py가 render 시점에 XBRL로 직접 계산 — N만 여기서 채운다.
# 각 항목의 산출 근거는 CANSLIM_N_DETAIL에 문장으로 남아 카드에 그대로 표시된다
# (점수만 있고 근거가 없으면 지어낸 것과 구분이 안 되므로).
CANSLIM_N = {canslim_n!r}
CANSLIM_N_DETAIL = {canslim_n_detail!r}
CANSLIM_NOTE = {canslim_note!r}

INCOME_NOTE = {pick('INCOME_NOTE', notes.get('income_note', ''))!r}
BALANCE_NOTE = {pick('BALANCE_NOTE', notes.get('balance_note', ''))!r}
CASHFLOW = {{
    'note': {pick('CASHFLOW.note', notes.get('cashflow_note', ''))!r},
    'src': 'SEC XBRL companyfacts',
}}

TAM = {{
    'label': {tam_label!r},
{tam_block}
}}

CHECKPOINTS = [
    {cp_lines}
]
CHECKPOINT_NOTE = {recent.get('checkpoint_note', '')!r}

# 산업 지도(deck_guru.industry_page) — 밸류체인 위치·업황 국면. 업종 내 순위는 렌더 시 결정론 계산.
VALUE_CHAIN = {pick('VALUE_CHAIN', static.get('value_chain') if isinstance(static.get('value_chain'), dict) else dict())!r}

# 피터 린치 2분 점검(deck_guru.lynch_page) — 이야기·맞으려면·깨지는 신호. 유형·PEG 는 렌더 시 결정론 계산.
LYNCH = {pick('LYNCH', recent.get('lynch') or dict())!r}

# 종합평가 — 이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음). \\n으로 줄바꿈.
SUMMARY = {pick('SUMMARY', summary)!r}
'''
    # ⚠️ 여기서 바꿔 끼운다. 템플릿 전체가 하나의 f-string 이라 CARRIED_OVER 자리가
    #    평가되는 시점엔 아래쪽 pick() 들이 아직 안 돌아 목록이 비어 있다.
    src = src.replace("CARRIED_OVER = '__CARRIED_OVER__'",
                      f'CARRIED_OVER = {dict(sorted(pick.carried.items()))!r}', 1)
    if pick.kept:
        print(f'[{ticker}] 기존 값 보존 {len(pick.kept)}건: ' + ', '.join(sorted(set(pick.kept))))
    elif fresh:
        print(f'[{ticker}] --fresh — 빈 값 보호 없이 이번 추출 결과 그대로')
    return src


# ── 6. 진입점 ──────────────────────────────────────────────────────────
def _norm_for_match(s: str) -> str:
    """대조용 정규화 — 따옴표 종류·공백·대소문자 차이로 헛되이 어긋나지 않게."""
    s = re.sub(r'[‘’“”`´]', "'", s or '')
    s = re.sub(r'[–—−]', '-', s)
    s = re.sub(r'&(amp|nbsp|#39|quot);', ' ', s)
    return re.sub(r'\s+', ' ', s).strip().lower()


def _ground_quotes(quotes, *sources):
    """영문 원문이 실제 공시 텍스트에 있는 인용문만 남긴다.

    프롬프트가 요구하는 형식이 ["직함", "한국어 번역", "영문 원문"]이라 3번째 칸이
    원문이다. 그 원문의 앞부분이 공시 텍스트에 그대로 있는지 본다 — 있으면 진짜
    발언이고, 없으면 만들어진 것이다.

    앞 60자만 보는 이유: LLM이 뒷부분을 줄이거나 말줄임표로 끝내는 일이 잦은데,
    도입부가 일치하면 원문에 근거한 것으로 볼 수 있다. 너무 짧게 자르면(예: 20자)
    흔한 상투구가 우연히 맞아버린다."""
    hay = ' '.join(_norm_for_match(s) for s in sources if s)
    if not hay:
        return list(quotes)          # 원문을 못 받았으면 판정 불가 — 있는 그대로 둔다
    out = []
    for q in quotes:
        en = q[2] if isinstance(q, (list, tuple)) and len(q) > 2 else ''
        needle = _norm_for_match(en)[:60]
        if len(needle) < 20:         # 원문 칸이 비었거나 너무 짧으면 판정 못 함
            out.append(q)
            continue
        if needle in hay:
            out.append(q)
        else:
            print(f'   ✗ 원문 미확인 인용문 제거: {en[:70]!r}')
    return out


def _ground_bio(bio: str, source: str) -> str:
    """약력에 등장하는 고유명사가 원문에 없으면 그 문장을 통째로 버린다.

    ABCL에서 CEO 약력에 'Alnylam Pharmaceuticals 공동설립', 'Millennium
    Pharmaceuticals 부사장'이 붙었는데 위임장 원문 어디에도 없었다 — 다른 사람의
    이력이었다. 실존 인물에 대한 허위 서술이라 가장 위험한 오류 클래스다.

    회사명처럼 보이는 영문 고유명사(대문자로 시작하는 2단어 이상)를 뽑아
    원문 대조한다. 하나라도 원문에 없으면 그 약력은 신뢰할 수 없다."""
    if not bio or not source:
        return bio
    hay = _norm_for_match(source)
    ents = re.findall(r'\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,3})\b', bio)
    STOP = {'ph d', 'inc', 'llc', 'ltd'}
    for e in ents:
        n = _norm_for_match(e)
        if n in STOP or len(n) < 6:
            continue
        if n not in hay:
            print(f'   ✗ 원문에 없는 고유명사 {e!r} — CEO 약력 폐기(지어낸 이력 방지)')
            return ''
    return bio


def _sanitize_rows(rows, n):
    """LLM이 JSON 배열-of-배열 스키마를 어기고 가끔 항목 하나를 dict나 길이
    부족한 리스트로 반환하는 경우가 실제로 있었다(PLTR 실측: checkpoints 항목 중
    하나가 리스트가 아니어서 c[1] 인덱싱이 KeyError로 죽고, autogen.py 전체가
    산출물 하나 없이 통째로 실패함 — 항목 하나의 형식 오류가 전체를 죽이면 안 됨).
    형식에 안 맞는 항목만 조용히 버리고 나머지는 살린다."""
    out = []
    for r in (rows or []):
        if isinstance(r, (list, tuple)) and len(r) >= n:
            out.append(list(r))
    return out


def _ckpt_path(ticker: str):
    return OUT_DIR / '_cache' / f'autogen_ckpt_{ticker}.json'


def _load_ckpt(ticker: str, max_age_h=24):
    """LLM 호출 결과 체크포인트.

    무료 쿼터가 중간에 끊기면(IONQ 실측: 8콜 중 2콜만 성공하고 429로 죽음) 성공한
    호출까지 통째로 버리고 EDGAR 수집부터 다시 해야 했다 — 쿼터가 빠듯한 날엔 영영
    못 끝낸다. 성공한 단계를 저장해두고 재실행 때 건너뛴다."""
    p = _ckpt_path(ticker)
    try:
        if p.exists() and (time.time() - p.stat().st_mtime) < max_age_h * 3600:
            return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def _save_ckpt(ticker: str, ck: dict):
    try:
        p = _ckpt_path(ticker)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(ck, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f'[체크포인트 저장 실패] {e}')


def generate(ticker: str, write: bool = True, fresh: bool = False):
    ticker = ticker.upper()
    prev = load_existing(ticker)
    if prev is not None:
        print(f'[{ticker}] 기존 데이터 파일 발견 — 사람이 보정한 값은 보존하며 병합'
              f'(LOCKED {len(getattr(prev, "LOCKED", []) or [])}건)')
    # 사전 점검 — LLM 쿼터를 8콜 태운 뒤에 "이 종목은 애초에 안 되는 거였네"를 알게
    # 되면 그날 쿼터가 통째로 날아간다. EDGAR·Yahoo만 찔러보는 무료 점검을 먼저 돌린다.
    import probe as _probe
    pr = _probe.probe(ticker)
    if pr['blockers']:
        for m in pr['blockers']:
            print(f'[{ticker}] 지원 불가 — {m}')
        raise SystemExit(f'{ticker}: 사전 점검에서 차단됨(LLM 호출 0회, 쿼터 소모 없음)')
    for m in pr['gaps']:
        print(f'[{ticker}] 참고 — {m}')

    ck = _load_ckpt(ticker)
    if ck:
        print(f'[{ticker}] 이전 실행 체크포인트 발견 — 완료된 단계 {sorted(ck)} 건너뜀')

    def step(key, label, fn):
        if key in ck:
            print(f'[{ticker}] {label} — 체크포인트 재사용')
            return ck[key]
        print(f'[{ticker}] {label}...')
        val = fn()
        ck[key] = val
        _save_ckpt(ticker, ck)
        time.sleep(3)   # 분당요청한도 순간소진 방지(ir.py와 동일 패턴)
        return val

    print(f'[{ticker}] 원자재 수집(EDGAR·Yahoo)...')
    raw = _gather_raw(ticker)
    static = step('static', 'LLM A: 정적 서사(연혁·CEO·사업부문)', lambda: _call_static(raw))
    recent = step('recent', 'LLM B: 최근실적·체크포인트', lambda: _call_recent(raw))
    recent['checkpoints'] = _sanitize_rows(recent.get('checkpoints'), 4)
    recent['facts'] = _sanitize_rows(recent.get('facts'), 3)
    recent['quotes'] = _sanitize_rows(recent.get('quotes'), 2)
    _ly = recent.get('lynch') if isinstance(recent.get('lynch'), dict) else {}
    recent['lynch'] = {'story': str(_ly.get('story') or '')[:400],
                       'must_happen': [str(x) for x in (_ly.get('must_happen') or []) if str(x).strip()][:3],
                       'breaks_if': [str(x) for x in (_ly.get('breaks_if') or []) if str(x).strip()][:3]} if _ly else {}

    # ── 인용문 접지(grounding): 원문에 실제로 있는 문장만 남긴다 ──
    # ABCL에서 존재하지 않는 CEO 발언이 만들어졌다 — "총 $655.0M의 가용 유동성을
    # 확보하여…"는 8-K 보도자료 원문 어디에도 없고, 실제 수치는 "over $675 million"
    # 이었다. 실존 인물의 발언을 지어낸 것이라 발행되면 안 되는 종류의 오류다.
    # 원문은 이미 raw에 들어 있으므로 문자열 대조로 걸러낼 수 있다.
    kept = _ground_quotes(recent.get('quotes') or [],
                          raw.get('earnings_text') or '',
                          json.dumps(raw.get('transcript') or '', ensure_ascii=False))
    if len(kept) != len(recent.get('quotes') or []):
        print(f'[{ticker}] 원문에서 확인 안 되는 인용문 '
              f'{len(recent["quotes"]) - len(kept)}건 제거(지어낸 발언 방지)')
    recent['quotes'] = kept

    # ── 체크포인트: 일정·컨센서스로 보강 (LLM 0콜) ──
    # CHECKPOINTS가 비면 발행이 막힌다(BLOCK). QLYS가 실제로 여기서 막혔다 —
    # autogen은 다 돌았는데 분당 한도 재시도 중 이 항목만 빈 채로 넘어갔다.
    # LLM 한 콜에 발행 가능 여부가 걸려 있는 구조였다.
    #
    # LLM이 쓴 것(투자 논리의 분기점)이 질은 더 높으므로 앞에 두고, 달력·컨센서스
    # 항목을 뒤에 붙인다. 둘은 성격이 달라 거의 안 겹친다. LLM이 비었으면
    # 결정론만으로도 발행은 막히지 않는다.
    try:
        import checkpoints as _cp
        cal = (S.yf_summary(ticker, 'calendarEvents') or {}).get('calendarEvents') or {}
        det_cp = _cp.build(ticker, raw.get('cons') or {}, raw.get('ann_series') or {}, cal)
        llm_cp = [tuple(c) for c in (recent.get('checkpoints') or []) if c]
        if det_cp:
            print(f'[{ticker}] 체크포인트 결정론 {len(det_cp)}건 보강(LLM 0콜)')
        # LLM은 '앞으로 볼 것'과 '방금 있었던 일'을 자주 헷갈린다 — AGL은 6건 중
        # 4건이 지난 분기 실적 요약이었다. 시점을 파싱해 과거는 기계가 거른다.
        llm_cp = _cp.drop_past(llm_cp, static.get('as_of') or recent.get('as_of'))
        recent['checkpoints'] = (llm_cp[:4] + det_cp)[:6]
    except Exception as e:
        print(f'[{ticker}] 체크포인트 보강 실패(기존 값 유지): {e}')
    notes = step('notes', 'LLM C: 재무해석·CANSLIM 참고자료', lambda: _call_notes(raw))
    # ── 종합평가: 숫자 조립으로 (LLM 0콜) ──
    # SUMMARY_PROMPT가 LLM에게 시킨 일이 원래 "이미 이 파일에 있는 숫자만 종합,
    # 새 주장 없음"이었다. 새 주장을 만들지 말라는 지시였으니 템플릿이 할 수 있는
    # 일이었고, 입력(ann_series=XBRL, cons=Yahoo)도 전부 결정론이다.
    # 숫자가 없어 한 줄도 못 만들 때만 LLM으로 물러난다.
    summary = ''
    try:
        import summarize
        summary = summarize.build(raw)
        if summary:
            print(f'[{ticker}] 종합평가 결정론 조립(LLM 0콜) — {len(summary.splitlines())}줄')
    except Exception as e:
        print(f'[{ticker}] 종합평가 조립 실패 → LLM 경로로: {e}')
    if not summary:
        summary = step('summary', 'LLM G: 종합평가(SUMMARY)', lambda: _call_summary(raw, recent, notes))
    # ── CEO·경영진: 먼저 Form 4에서 결정론으로 (LLM 0콜) ──
    # 발행 필수 항목 6개 중 4개가 LLM 산출물이라 신규 종목 하나에 Gemini를 8콜씩
    # 썼고, 무료 쿼터의 분당 한도에 걸려 단계마다 59초씩 대기하는 일이 실제로 났다.
    # 그 4개를 하나씩 결정론으로 옮기는 중이고, `LEADERSHIP.ceo.name`이 첫 칸이다.
    # Form 4에는 직함이 구조화된 XML로 들어있어 파싱만 하면 된다(officers.py).
    # 실측 5/5: QLYS·IONQ·PLTR·SATL·AAPL 전부 CEO와 경영진 표까지 확보.
    det_ceo = det_execs = None
    try:
        import officers
        _cik = raw['cik']                    # generate()에 cik 지역변수는 없다 — raw에서 꺼낸다
        det_ceo = officers.ceo(_cik)[0:2]
        det_execs = [[p['name'], p['title'], ''] for p in officers.executives(_cik)]
        if det_ceo[0]:
            print(f'[{ticker}] CEO 결정론 확보(Form 4, LLM 0콜): {det_ceo[0]} — {det_ceo[1]}')
    except Exception as e:
        print(f'[{ticker}] Form 4 경영진 조회 실패 → LLM 경로로: {e}')

    # 결정론으로 CEO와 경영진을 둘 다 얻었으면 LLM D는 부르지 않는다.
    # RSU·지배구조 서술만 남는데, 그건 없으면 WARN이지 BLOCK이 아니다.
    need_proxy = not (det_ceo and det_ceo[0] and det_execs)
    if need_proxy:
        proxy_info = step('proxy', 'LLM D: 위임장(CEO·경영진·RSU·지배구조)', lambda: _call_proxy(raw))
    else:
        print(f'[{ticker}] LLM D 건너뜀 — Form 4로 충분(쿼터 1콜 절약)')
        proxy_info = {}

    # 10-K 기반(static)이 CEO 실명을 못 찾는 경우가 실제로 있었다(IONQ: Part III가
    # 위임장에 위임돼 10-K엔 이름 자체가 없음) — 위임장 발췌에서 나온 값이 있으면
    # 그걸로 보강/대체.
    for k in ('ceo_name', 'ceo_since', 'ceo_bio', 'rsu_note'):
        if proxy_info.get(k) and not static.get(k):
            static[k] = proxy_info[k]
    # 경영진 명단은 10-K엔 거의 없고 위임장에만 있다 — static에 합류시켜 렌더러로 넘김.
    if proxy_info.get('executives'):
        static['executives'] = proxy_info['executives']

    # Form 4 결과를 최종 권위로 둔다. 공시 서식에서 직접 읽은 값이라
    # 본문에서 추론한 LLM 값보다 신뢰도가 높다(PLTR은 10-K/위임장 문장보다
    # Form 4의 remarks가 정확했다).
    if det_ceo and det_ceo[0]:
        static['ceo_name'] = det_ceo[0]
    if det_execs and not static.get('executives'):
        static['executives'] = det_execs

    # CEO 약력도 원문 대조 — 다른 사람 이력이 붙는 사고가 실제로 났다(ABCL).
    static['ceo_bio'] = _ground_bio(static.get('ceo_bio') or '',
                                    raw.get('proxy_excerpts') or raw.get('annual_text') or '')

    # 경쟁사 CIK 자동 매칭(시총 필터로 판단을 결정론적 기준으로 대체) — LLM 호출 아님.
    target_mcap = raw['cons'].get('market_cap')
    peers = _resolve_competitor_ciks(static.get('competitors') or [], target_mcap)
    print(f'[{ticker}] 경쟁사 자동 매칭: {peers or "(체급 맞는 후보 없음)"}')

    # 가격 급등/급락 구간 자동 탐지 + 과거 뉴스RSS 검색으로 이유 추정(LLM 호출 E,F —
    # 구간마다 하나씩, 최대 2개).
    price_moves = []
    rows = (raw.get('ohlcv') or {}).get('rows') or []
    detected = _detect_price_moves(rows)
    for idx, mv in enumerate(detected, 1):
        info = step(f'move{idx}', f'LLM {chr(68+idx)}: 가격변동 {idx} 뉴스검색·이유추정',
                    lambda mv=mv: _call_price_move_reason(raw, mv))
        price_moves.append({'no': idx, 'dir': mv['dir'], 'period': info['period'],
                            'pct': f'{mv["pct"]:+.0f}%', 'range': f'${mv["c0"]:.2f}→${mv["c1"]:.2f}',
                            'reason': info['reason'],
                            'yr': mv['start'].year, 'mo': mv['start'].month})

    tam_estimates, tam_cagr = step('tam', 'LLM H: TAM(시장규모) 뉴스검색·추출',
                                   lambda: _call_tam(raw, static))
    print(f'[{ticker}] TAM 추출 결과: {tam_estimates or "(못 찾음, 정직하게 비움)"} '
          f'/ 시장 CAGR {f"{tam_cagr:.1f}%" if tam_cagr else "(헤드라인에 명시 없음)"}')

    # CANSLIM N 자동 채점 — LLM 호출 없음(위임장 기반 지배구조 판정만 이미 받아둔 값 재사용).
    canslim_n, canslim_detail = _score_canslim_n(
        raw, peers, tam_cagr,
        governance={'changed': proxy_info.get('governance_changed'),
                    'note': proxy_info.get('governance_note', '')},
        competitors=static.get('competitors'))
    print(f'[{ticker}] CANSLIM N 자동채점: {canslim_n}')

    src = render_data_file(ticker, raw, static, recent, notes, peers=peers, price_moves=price_moves,
                           summary=summary, tam_estimates=tam_estimates, tam_cagr=tam_cagr,
                           canslim_n=canslim_n, canslim_detail=canslim_detail, prev=prev, fresh=fresh)
    if write:
        path = OUT_DIR / f'{_module_name(ticker)}.py'
        _archive(ticker, path)
        path.write_text(src, encoding='utf-8')
        print(f'[{ticker}] 저장: {path}')
        # 끝까지 갔으면 체크포인트는 역할이 끝났다 — 남겨두면 다음 실행이 낡은 LLM
        # 결과를 재사용해 "실적 발표했는데 왜 그대로냐"가 된다.
        try:
            _ckpt_path(ticker).unlink(missing_ok=True)
        except Exception:
            pass
    return src, dict(cik=raw['cik'], company=raw['company'])


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용법: python autogen.py TICKER [--fresh]')
        print('  --fresh : 빈 값 보호 없이 완전히 새로 뽑는다(LOCKED 만 유지).')
        print('            직전 파일은 decks/history/ 에 자동 보관된다.')
        sys.exit(1)
    tk = sys.argv[1].upper()
    fresh = '--fresh' in sys.argv[2:]
    try:
        generate(tk, fresh=fresh)
    except analyzer.QuotaExhausted as e:
        # 40줄짜리 traceback 대신 "지금 뭘 해야 하는지"를 말해준다.
        print(f'\n[{tk}] 중단 — {e}')
        print(f'  · 여기까지 성공한 단계는 저장돼 있음: {_ckpt_path(tk).name}')
        print(f'  · 쿼터가 풀린 뒤 `python autogen.py {tk}`를 다시 돌리면 남은 단계부터 이어서 진행됨')
        print(f'  · 급하면 기존 데이터로 렌더만 하는 건 지금도 가능: `python build.py {tk}`')
        sys.exit(2)