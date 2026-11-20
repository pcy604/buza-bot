# -*- coding: utf-8 -*-
"""사전 점검 — "이 티커, 돌려도 되나?"를 LLM 호출 0번으로 먼저 답한다.

    python probe.py NVDA
    python probe.py NVDA JPM O TSM ARM        # 여러 개 한 번에

왜 필요한가: `autogen.py`는 Gemini 무료 쿼터를 8콜 쓴다. 그런데 종목에 따라 아예
불가능하거나(한국 상장·ETF), 절반만 되는(외국기업 IFRS 공시 → us-gaap 태그 없음)
경우가 있다. 8콜을 다 태우고 나서 "빈 표만 나오네"를 알게 되면 그날 쿼터가 날아간다.
이 스크립트는 EDGAR·Yahoo만 찔러보고(전부 무료·무제한) 무엇이 되고 무엇이 안 되는지
먼저 말해준다.

판정
  OK      전 페이지 정상 생성 가능
  PARTIAL 일부 섹션이 빈 채로 나옴 — 무엇이 빌지 목록으로 알려줌
  NO      구조적으로 불가 — 이유와 함께
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ir            # noqa: E402
import sources as S  # noqa: E402


def _probe_kr(t: str, out: dict) -> dict:
    """한국 종목 사전 점검 — 미국판과 **같은 계약**(blockers/gaps/info)으로 답한다.
    LLM 0콜. 여기서 막히는 조건은 '자료를 못 만든다'는 것만 담고, '내용이 부족하다'는
    gaps 로 보낸다(막을 일이 아니라 알릴 일)."""
    try:
        import sources_kr as K
    except Exception as e:
        out['blockers'].append(f'한국 데이터 모듈 로드 실패: {e}')
        return out

    corp = K.to_corp_code(t)
    if not corp:
        out['blockers'].append('DART에 없는 종목코드 — 상장폐지이거나 오타일 수 있어요 '
                               '(예: 삼성전자는 005930.KS, 에코프로비엠은 247540.KQ)')
        return out
    info = K.company_info(corp)
    if not info:
        # 키 미등록이 가장 흔한 원인이고, 그때 sources_kr 이 사유를 콘솔에 찍는다.
        out['blockers'].append('DART 회사개황 조회 실패 — DART_KEY 설정을 확인해주세요')
        return out
    out['company'], out['cik'] = info.get('stock_name') or t, corp
    out['info'].append(f'{info.get("stock_name", t)} · '
                       f'{K._MARKET.get((info.get("corp_cls") or "").upper(), ("기타", ""))[0]}')

    ann = K.annual_series(corp, ['revenue'])
    yrs = sorted((ann or {}).get('revenue', {}))
    if not yrs:
        out['blockers'].append('DART 연간 재무를 못 읽었어요 — 재무 3표를 그릴 수 없습니다')
        return out
    out['info'].append(f'연간 재무 {yrs[0]}~{yrs[-1]} ({len(yrs)}개년)')

    if not K.provisional_results(corp):
        out['gaps'].append('영업(잠정)실적 공정공시가 최근 200일 내에 없어 '
                           '"최근 실적" 페이지가 비어요')
    cons = S.consensus(t) or {}
    if not cons.get('price'):
        out['blockers'].append(f'Yahoo Finance에서 {t} 시세를 못 받았어요 — 티커 접미사'
                               '(.KS=코스피 / .KQ=코스닥)가 맞는지 확인해주세요')
        return out
    if not cons.get('analysts'):
        out['gaps'].append('애널리스트 커버리지가 없어 목표주가·컨센서스 칸이 비어요')
    out['info'].append(f'현재가 {cons["price"]:,.0f}원')
    # 한국은 어닝콜 전문이 무료 공개되지 않는다 — 없는 게 정상이라 gap 으로만 알린다.
    out['gaps'].append('한국 상장사는 어닝콜 전문을 공개하지 않아 경영진 발언 인용이 없어요')
    return out


def probe(ticker: str) -> dict:
    t = ticker.upper()
    out = {'ticker': t, 'blockers': [], 'gaps': [], 'info': []}

    # 한국 종목(.KS/.KQ)은 SEC에 있을 리 없다. 아래 SEC 검사를 그대로 태우면
    # "SEC EDGAR에 없는 티커"로 **즉시 차단**돼 봇이 "지원할 수 없어요"만 답한다.
    if t.endswith(('.KS', '.KQ')):
        return _probe_kr(t, out)

    # ① SEC에 등록된 티커인가 — 여기서 걸리면 그 뒤는 볼 것도 없다.
    try:
        cik, company = ir.resolve_ticker(t)
    except Exception as e:
        out['blockers'].append(f'SEC 티커 조회 실패: {e}')
        return out
    if not cik:
        out['blockers'].append('SEC EDGAR에 없는 티커 — 미국 상장(NYSE/NASDAQ)이 아니거나 '
                               'ETF/지수. 이 파이프라인은 SEC 공시가 원천이라 지원 불가')
        return out
    out['company'], out['cik'] = company, cik

    # ② 연차보고서 — 10-K(국내기업) / 20-F·40-F(외국기업)
    try:
        hist = ir.filing_history(cik, limit=40)
    except Exception as e:
        out['blockers'].append(f'공시 이력 조회 실패: {e}')
        return out
    forms = [f['form'] for f in hist]
    annual = next((f for f in hist if f['form'] in ('10-K', '20-F', '40-F')), None)
    if not annual:
        out['blockers'].append(f'연차보고서(10-K/20-F/40-F)가 최근 40건 공시에 없음 '
                               f'— 상장 직후(S-1만 있음)이거나 공시 형태가 다름. 최근 폼: '
                               f'{", ".join(dict.fromkeys(forms))[:60]}')
        return out
    out['annual_form'] = f"{annual['form']}({annual['date']})"
    if annual['form'] in ('20-F', '40-F'):
        out['info'].append(f"{annual['form']} 제출 외국기업 — 재무 태그가 IFRS일 수 있음(아래 확인)")

    # ③ XBRL 재무 — 9·10·11p(재무3표)와 7p(CANSLIM)·8p(밸류에이션)의 원천
    try:
        facts = S.companyfacts(cik).get('facts', {})
    except Exception as e:
        out['blockers'].append(f'XBRL companyfacts 조회 실패: {e}')
        return out
    taxos = [k for k in facts if facts[k]]
    out['info'].append(f'XBRL 택소노미: {", ".join(taxos) or "(없음)"}')
    if 'us-gaap' not in facts and 'ifrs-full' not in facts:
        out['blockers'].append('us-gaap·ifrs-full 태그가 둘 다 없음 — 재무3표·밸류에이션·'
                               'CANSLIM이 전부 빈 채로 나옴')
        return out

    # 보고통화 — USD 수치가 없으면 재무 숫자를 못 쓴다(USD 시총과 섞으면 PSR·PER이
    # 통째로 틀린 숫자가 되므로 sources._pick_unit이 아예 비운다).
    merged = {**(facts.get('ifrs-full') or {}), **(facts.get('us-gaap') or {})}
    rev_c = next((merged[t] for t in ('RevenueFromContractWithCustomerExcludingAssessedTax',
                                      'Revenues', 'Revenue') if t in merged), None)
    if rev_c and 'USD' not in (rev_c.get('units') or {}):
        cur = ', '.join((rev_c.get('units') or {}).keys()) or '(불명)'
        out['blockers'].append(f'XBRL에 USD 수치가 없음(보고통화: {cur}) — USD 시가총액과 '
                               f'단위가 안 맞아 재무·밸류에이션 전부 사용 불가')
        return out

    ann = S.annual_series(cik, ['revenue', 'opinc', 'netinc', 'cfo', 'cash', 'assets', 'equity'])
    # `if v`로 거르면 **매출 0을 "태그 없음"으로 오판**한다(VKTX 실측: 개발단계 바이오라
    # 매출을 0으로 정직하게 공시하는데 probe가 "매출 태그를 못 찾음"으로 차단해버렸다).
    # 0과 None은 완전히 다른 사실 — 프로젝트에서 여러 번 반복된 버그 클래스다.
    rev_all = {y: v for y, v in (ann.get('revenue') or {}).items() if v is not None}
    rev_yrs = sorted(rev_all)
    if not rev_yrs:
        out['blockers'].append('연간 매출 태그를 하나도 못 찾음 — 태그가 특수하거나 '
                               '매출 개념 자체가 없는 공시 구조')
    elif not any(rev_all.values()):
        out['gaps'].append('전 기간 매출 0(개발단계 기업) — PSR·부문별매출·GPM 등 매출 기반 '
                           '지표가 전부 의미 없음. 5p 사업부문·8p 밸류에이션 ①이 사실상 빔')
        out['fy'] = f'{rev_yrs[0]}~{rev_yrs[-1]} ({len(rev_yrs)}개년, 전부 0)'
    else:
        out['fy'] = f'{rev_yrs[0]}~{rev_yrs[-1]} ({len(rev_yrs)}개년)'
        if len(rev_yrs) < 3:
            out['gaps'].append(f'연간 매출이 {len(rev_yrs)}개년뿐 — 밸류에이션 3년 차트와 '
                               f'CANSLIM A(3년 CAGR)가 축소됨')
    has_op = any((ann.get('opinc') or {}).values())
    has_ni = any((ann.get('netinc') or {}).values())
    if not has_op and has_ni:
        # 은행·리츠는 OperatingIncomeLoss를 아예 안 낸다 — 렌더러가 순이익으로 대체하므로
        # 결함이 아니라 표기 차이다. "비어 나옴"이라고 하면 오해를 부른다.
        out['info'].append('영업이익 태그 없음(은행·리츠 등에서 흔함) — 밸류에이션·CANSLIM이 '
                           '순이익 기준으로 자동 대체됨')
    elif not has_op and not has_ni:
        out['gaps'].append('영업이익·순이익 태그가 둘 다 없음 — CANSLIM C·A가 0점, '
                           '8p 밸류에이션 ②가 장부가(PBR) 기준으로 대체됨')
    for key, label in (('cfo', '영업현금흐름'), ('equity', '자기자본')):
        if not any((ann.get(key) or {}).values()):
            out['gaps'].append(f'{label} 태그 없음 — 관련 차트·점수 비어 나옴')

    # ④ 주가 — 3p 캔들차트·상장후CAGR·급등락 자동탐지·6p 퀀트의 원천
    try:
        px = S.monthly_ohlcv(t)
        rows = (px or {}).get('rows') or []
    except Exception as e:
        rows = []
        out['gaps'].append(f'주가 조회 실패({e}) — 3p 차트·CAGR·6p 퀀트 비어 나옴')
    if rows:
        import datetime as _dt
        y0 = _dt.datetime.fromtimestamp(rows[0][0], _dt.timezone.utc).year
        out['px'] = f'{y0}~ ({len(rows)}개월)'
        if len(rows) < 24:
            out['gaps'].append(f'주가 이력이 {len(rows)}개월뿐 — 상장 2년 미만이라 CAGR 대신 '
                               f'누적수익률로 표시되고 6p 퀀트 히트맵이 얇음')
    elif 'px' not in out:
        out['gaps'].append('Yahoo에 월봉 이력이 없음 — 3p 차트·CAGR 비어 나옴')

    # ⑤ 컨센서스 — 1p 목표주가, 8p 미래 2개년 막대
    try:
        cons = S.consensus(t)
    except Exception:
        cons = {}
    if not (cons.get('periods') or {}):
        out['gaps'].append('애널리스트 컨센서스 없음(커버리지 부족) — 8p 미래 2개년이 빈 칸, '
                           '1p 목표주가 타일 생략')
    if not cons.get('market_cap'):
        out['gaps'].append('시가총액 조회 실패 — 표지·PSR·경쟁사 비교가 비어 나옴')

    # ⑥ 위임장 — 4p CEO 약력·주요 경영진·RSU·내부자 지분
    # filing_history(limit=40)로 보면 대형주는 8-K·Form 4가 워낙 많아 최근 40건에
    # DEF 14A가 안 들어와 "위임장 없음"이라는 오탐이 난다(NVDA·JPM·O·MRNA 전부 오탐).
    # autogen._fetch_proxy_excerpts와 똑같이 submissions 전체 목록에서 확인한다.
    has_proxy = False
    try:
        j = ir.requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                            headers=ir.SEC_HEADERS, timeout=40).json()
        has_proxy = 'DEF 14A' in (j.get('filings', {}).get('recent', {}).get('form') or [])
    except Exception as e:
        out['gaps'].append(f'위임장 확인 실패({e})')
        has_proxy = True   # 확인 실패를 "없음"으로 단정하지 않는다
    if not has_proxy:
        out['gaps'].append('DEF 14A(위임장)가 최근 공시에 없음 — 4p CEO 약력·경영진 명단·'
                           'RSU 성과조건·내부자 지분이 비어 나옴(외국기업에서 흔함)')
    return out


def report(tickers) -> int:
    worst = 0
    for tk in tickers:
        r = probe(tk)
        if r['blockers']:
            verdict, code = 'NO', 2
        elif r['gaps']:
            verdict, code = 'PARTIAL', 1
        else:
            verdict, code = 'OK', 0
        worst = max(worst, code)
        head = f"{r['ticker']:<6} {verdict:<8}"
        print(f"\n{head} {r.get('company', '')}")
        for k in ('annual_form', 'fy', 'px'):
            if r.get(k):
                print(f'         · {k}: {r[k]}')
        for m in r['info']:
            print(f'         · {m}')
        for m in r['blockers']:
            print(f'         [X] {m}')
        for m in r['gaps']:
            print(f'         [!] {m}')
    return worst


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용법: python probe.py TICKER [TICKER ...]')
        sys.exit(1)
    sys.exit(report([a.upper() for a in sys.argv[1:]]))
