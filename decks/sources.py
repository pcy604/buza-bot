# -*- coding: utf-8 -*-
"""딥리포트용 데이터 페처 — 전부 무료 공개 소스.

  Yahoo Finance  : crumb 인증을 통과하면 quoteSummary가 열린다(컨센서스·주주구성·펀드보유·시총).
                   fc.yahoo.com에서 쿠키 → /v1/test/getcrumb → crumb 파라미터로 호출.
  SEC XBRL       : data.sec.gov/api/xbrl/companyfacts — 공시 원문 파싱 없이 항목별 전체 시계열.
                   Yahoo의 재무이력은 소형주에서 구멍이 많아(SATL은 FY22·23 누락) 재무는 이쪽이 정답.

모든 반환값은 (값, 출처, 기준일)을 같이 들고 다니는 걸 원칙으로 한다.
"""
import re
import sys
import json
import html
import time
import hashlib
import datetime as dt
from pathlib import Path
from collections import defaultdict

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124 Safari/537.36')
SEC_H = {'User-Agent': config.SEC_UA, 'Accept-Encoding': 'gzip, deflate'}
CACHE = Path(__file__).resolve().parent / '_cache'
CACHE.mkdir(exist_ok=True)

_SESSION = None


def _cached(name: str, ttl_h: int, fn):
    """네트워크 결과 로컬 캐시 — 반복 렌더 때 같은 API를 계속 두드리지 않게(429 방지)."""
    p = CACHE / f'{name}.json'
    if p.exists() and (time.time() - p.stat().st_mtime) < ttl_h * 3600:
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            pass
    data = fn()
    p.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


# ── Yahoo (crumb 인증) ─────────────────────────────────────────────────
def _yf():
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update({'User-Agent': UA})
        try:
            s.get('https://fc.yahoo.com', timeout=10)
        except Exception:
            pass
        s.crumb = s.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10).text.strip()
        _SESSION = s
    return _SESSION


def yf_summary(ticker: str, modules: str, ttl_h=12):
    def go():
        s = _yf()
        r = s.get(f'https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}',
                  params={'modules': modules, 'crumb': s.crumb}, timeout=25)
        j = r.json().get('quoteSummary', {})
        res = j.get('result') or [{}]
        return res[0]
    # 내장 hash()는 문자열에 PYTHONHASHSEED 랜덤 솔트가 들어가 프로세스마다 값이
    # 바뀐다 — 재시작마다 같은 modules 도 새 캐시 파일이 생겨 캐시가 한 번도
    # 재사용되지 않고 쌓이기만 했다(2026-10-25 발견, decks/_cache 140MB).
    # sha1은 프로세스 무관 고정값이라 진짜 캐시 히트가 된다.
    _mkey = hashlib.sha1(modules.encode()).hexdigest()[:10]
    return _cached(f'yf_{ticker}_{_mkey}', ttl_h, go)


def yf_chart(ticker: str, rng='5y', interval='1wk', ttl_h=12):
    def go():
        r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
                         params={'range': rng, 'interval': interval},
                         headers={'User-Agent': UA}, timeout=25).json()
        res = r['chart']['result'][0]
        q = res['indicators']['quote'][0]
        return {'ts': res['timestamp'], 'close': q['close'], 'open': q.get('open'),
                'high': q.get('high'), 'low': q.get('low'), 'volume': q.get('volume'),
                'meta': res['meta']}
    return _cached(f'px_{ticker}_{rng}_{interval}', ttl_h, go)


def _raw(node, *keys):
    for k in keys:
        node = (node or {}).get(k, {})
    return node.get('raw') if isinstance(node, dict) else None


# ── 컨센서스 ───────────────────────────────────────────────────────────
def consensus(ticker: str):
    """애널리스트 컨센서스 — 당해/차년 매출·EPS. 없으면 빈 dict."""
    d = yf_summary(ticker, 'earningsTrend,financialData,defaultKeyStatistics,price')
    out = {'periods': {}, 'analysts': 0}
    for t in (d.get('earningsTrend') or {}).get('trend', []):
        p = t.get('period')
        if p not in ('0y', '+1y'):
            continue
        out['periods'][p] = {
            'end': (t.get('endDate') or '')[:4],
            'eps': _raw(t, 'earningsEstimate', 'avg'),
            'eps_low': _raw(t, 'earningsEstimate', 'low'),
            'eps_high': _raw(t, 'earningsEstimate', 'high'),
            'rev': _raw(t, 'revenueEstimate', 'avg'),
            'rev_low': _raw(t, 'revenueEstimate', 'low'),
            'rev_high': _raw(t, 'revenueEstimate', 'high'),
            'n': _raw(t, 'earningsEstimate', 'numberOfAnalysts'),
        }
        out['analysts'] = max(out['analysts'], out['periods'][p]['n'] or 0)
    ks = d.get('defaultKeyStatistics') or {}
    pr = d.get('price') or {}
    fd = d.get('financialData') or {}
    out['market_cap'] = _raw(pr, 'marketCap')
    out['shares_out'] = _raw(ks, 'sharesOutstanding')
    out['float'] = _raw(ks, 'floatShares')
    out['ev'] = _raw(ks, 'enterpriseValue')
    out['price'] = _raw(pr, 'regularMarketPrice')
    # 애널리스트 목표주가·투자의견 — financialData는 이미 위에서 요청하는 모듈이라
    # 추가 API 호출 없이 그냥 더 뽑아쓰면 됨(따로 함수 만들 필요 없었음).
    out['target_mean'] = _raw(fd, 'targetMeanPrice')
    out['target_high'] = _raw(fd, 'targetHighPrice')
    out['target_low'] = _raw(fd, 'targetLowPrice')
    out['recommendation'] = (fd or {}).get('recommendationKey')
    out['rec_mean'] = _raw(fd, 'recommendationMean')
    out['n_analysts_price'] = (fd or {}).get('numberOfAnalystOpinions', {}).get('raw') \
        if isinstance(fd.get('numberOfAnalystOpinions'), dict) else None
    return out


# ── 주주구성 ───────────────────────────────────────────────────────────
def ownership(ticker: str):
    d = yf_summary(ticker, 'majorHoldersBreakdown,institutionOwnership,fundOwnership,price')
    mh = d.get('majorHoldersBreakdown') or {}
    mcap = _raw(d.get('price') or {}, 'marketCap')

    def rows(node, key):
        out = []
        for h in (node or {}).get('ownershipList', []):
            out.append({
                'name': h.get('organization', ''),
                'pct': _raw(h, 'pctHeld'),
                'shares': _raw(h, 'position'),
                'value': _raw(h, 'value'),
                'date': (h.get('reportDate', {}) or {}).get('fmt', ''),
            })
        return out

    return {
        'insiders_pct': _raw(mh, 'insidersPercentHeld'),
        'institutions_pct': _raw(mh, 'institutionsPercentHeld'),
        'inst_float_pct': _raw(mh, 'institutionsFloatPercentHeld'),
        'inst_count': _raw(mh, 'institutionsCount'),
        'institutions': rows(d.get('institutionOwnership'), 'institutionOwnership'),
        'funds': rows(d.get('fundOwnership'), 'fundOwnership'),
        'market_cap': mcap,
    }


# ── SEC XBRL 재무 시계열 ───────────────────────────────────────────────
# 회사마다 태그가 달라서 후보를 순서대로 시도한다(첫 매치 채택).
TAGS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues',
                'RevenueFromContractWithCustomerIncludingAssessedTax'],
    'cogs': ['CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization',
             'CostOfRevenue', 'CostOfGoodsAndServicesSold', 'CostOfServices'],
    'rnd': ['ResearchAndDevelopmentExpense'],
    'sga': ['SellingGeneralAndAdministrativeExpense', 'GeneralAndAdministrativeExpense'],
    # PLTR처럼 SG&A를 통합 태그 없이 G&A·판매비를 따로 공시하는 회사가 있다 — 'sga'
    # 후보(첫 매치 우선)만 쓰면 판매비가 통째로 빠져 "규모의 경제" 비용 계산이 실제
    # 영업이익과 수백M~1B+ 단위로 안 맞는 문제가 실제로 있었다. annual_series는 후보를
    # 병합이 아니라 대체(fallback)로 처리하므로, 별도 키로 뽑아 호출부에서 합산한다.
    'salesmkt': ['SellingAndMarketingExpense'],
    'dep': ['Depreciation', 'DepreciationDepletionAndAmortization'],
    'opinc': ['OperatingIncomeLoss'],
    'netinc': ['NetIncomeLoss', 'ProfitLoss'],
    'cfo': ['NetCashProvidedByUsedInOperatingActivities',
            'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'],
    'capex': ['PaymentsToAcquirePropertyPlantAndEquipment'],
    'cash': ['CashAndCashEquivalentsAtCarryingValue'],
    'assets': ['Assets'],
    'liab': ['Liabilities'],
    'equity': ['StockholdersEquity'],
    'ar': ['AccountsReceivableNetCurrent'],
    'inventory': ['InventoryNet'],
    'ppe': ['PropertyPlantAndEquipmentNet'],
    'contract_liab': ['ContractWithCustomerLiabilityCurrent'],
    'shares': ['CommonStockSharesOutstanding', 'EntityCommonStockSharesOutstanding'],
    'eps': ['EarningsPerShareDiluted', 'EarningsPerShareBasicAndDiluted'],
}
# 20-F를 내는 외국기업은 us-gaap이 아니라 ifrs-full 택소노미를 쓴다(TSM 실측: us-gaap
# 태그 0개, ifrs-full 334개) — 그대로 두면 재무3표·밸류에이션·CANSLIM이 전부 빈 채로
# 나온다. 후보 목록에 IFRS 대응 태그를 이어붙인다(회사는 둘 중 하나만 쓰므로 충돌 없음).
IFRS_TAGS = {
    'revenue': ['Revenue', 'RevenueFromContractsWithCustomers'],
    'cogs': ['CostOfSales'],
    'rnd': ['ResearchAndDevelopmentExpense'],
    'sga': ['GeneralAndAdministrativeExpense', 'AdministrativeExpense'],
    'salesmkt': ['SellingExpense', 'DistributionCosts'],
    'dep': ['DepreciationAndAmortisationExpense'],
    'opinc': ['ProfitLossFromOperatingActivities'],
    'netinc': ['ProfitLoss'],
    'cfo': ['CashFlowsFromUsedInOperatingActivities'],
    'capex': ['PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities'],
    'cash': ['CashAndCashEquivalents'],
    'assets': ['Assets'],
    'liab': ['Liabilities'],
    'equity': ['Equity', 'EquityAttributableToOwnersOfParent'],
    'ar': ['TradeAndOtherCurrentReceivables'],
    'inventory': ['Inventories'],
    'ppe': ['PropertyPlantAndEquipment'],
    'contract_liab': ['ContractLiabilities', 'CurrentContractLiabilities'],
    'shares': ['NumberOfSharesOutstanding'],
    'eps': ['DilutedEarningsLossPerShare'],
}
for _k, _v in IFRS_TAGS.items():
    TAGS.setdefault(_k, [])
    TAGS[_k] += [t for t in _v if t not in TAGS[_k]]


def _taxonomy_facts(cik: int, ttl_h=24):
    """us-gaap + ifrs-full 병합(같은 이름이면 us-gaap 우선).
    회사는 둘 중 하나만 쓰므로 실제 충돌은 없고, 호출부는 택소노미를 몰라도 된다."""
    f = companyfacts(cik, ttl_h=ttl_h).get('facts', {})
    merged = dict(f.get('ifrs-full') or {})
    merged.update(f.get('us-gaap') or {})
    return merged
DURATION_KEYS = {'revenue', 'cogs', 'rnd', 'sga', 'dep', 'opinc', 'netinc', 'cfo', 'capex', 'eps'}


def companyfacts(cik: int, ttl_h=24):
    return _cached(f'sec_{cik}', ttl_h, lambda: requests.get(
        f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',
        headers=SEC_H, timeout=90).json())


def _pick_unit(concept):
    """USD(또는 주식수/주당USD) 계열만 쓴다.

    예전엔 USD가 없으면 `list(us.values())[0]`로 아무 통화나 집어왔다 — 그러면 TWD·EUR
    매출을 USD 시가총액으로 나눠 PSR·PER이 통째로 틀린 숫자가 된다(대만·유럽 기업에서
    실제로 발생 가능). 틀린 숫자를 보여주느니 비워서 "데이터 없음"으로 두는 게 맞다.
    probe.py가 이 경우를 미리 "보고통화가 USD가 아님"으로 알려준다."""
    us = concept.get('units', {})
    for k in ('USD', 'shares', 'USD/shares'):
        if k in us:
            return us[k]
    return []


def annual_series(cik: int, keys=None, ttl_h=24):
    """회계연도별 값. duration 항목은 ~365일짜리만, instant 항목은 FY 마감일 값만 취한다.

    ttl_h: companyfacts 캐시 유효기간. 기본 24h는 렌더 시점(live.bundle, 자주·자동
    호출됨)엔 적당한데, autogen.py의 신규/갱신 생성(사람이 명시적으로 "최신 데이터
    달라"고 실행하는 드문 동작)에는 실제로 사고가 났다 — PLTR 실적발표 당일 이른
    아침(발표 몇 시간 전)에 캐시가 한 번 채워진 상태로 발표 후 autogen.py를 돌리니
    24시간 캐시가 안 만료돼 구분기 매출($1.63B, Q1)이 신분기(Q2, $1.94B)인 것처럼
    나왔다(어닝콜 발언 기반 facts 표는 원문을 직접 읽어 정확했는데 KPI 타일만 캐시된
    구분기 숫자라 같은 페이지 안에서 숫자가 모순됐음). autogen.py 쪽에서 ttl_h=0으로
    호출해 이 클래스의 문제를 근본 차단한다."""
    facts = _taxonomy_facts(cik, ttl_h=ttl_h)
    out = {}
    for key in (keys or TAGS):
        # 회사가 연도별로 태그를 갈아탄 경우가 있어(SATL 순이익: ProfitLoss→NetIncomeLoss)
        # 첫 매치에서 멈추지 않고 후보를 모두 병합한다. 앞선 태그가 우선.
        byfy = {}
        for tag in TAGS[key]:
            if tag not in facts:
                continue
            pts = _pick_unit(facts[tag])
            for p in pts:
                if p.get('form') not in ('10-K', '20-F'):
                    continue
                fy, end = p.get('fy'), p.get('end')
                if not fy or not end:
                    continue
                if key in DURATION_KEYS:
                    st = p.get('start')
                    if not st:
                        continue
                    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(st)).days
                    if not (330 <= days <= 400):
                        continue
                    if p.get('fp') != 'FY':
                        continue
                # 같은 FY가 여러 번 나오면(재작성 등) 가장 나중 제출본 채택
                fy_end = int(end[:4])
                prev = byfy.get(fy_end)
                if prev is None or p.get('filed', '') >= prev[1]:
                    byfy[fy_end] = (p['val'], p.get('filed', ''), tag)
        if byfy:
            out[key] = {y: v for y, (v, _, _) in sorted(byfy.items())}
    return out


def quarterly_series(cik: int, keys=None, limit=12, ttl_h=24):
    """분기 시계열 — 10-Q(≈90일) + 10-K에서 역산 불가한 4분기는 제외(중복·불일치 방지).
    ttl_h: annual_series와 같은 이유로 노출(캐시 신선도, autogen.py는 0으로 호출)."""
    facts = _taxonomy_facts(cik, ttl_h=ttl_h)
    out = {}
    for key in (keys or TAGS):
        for tag in TAGS[key]:
            if tag not in facts:
                continue
            pts = _pick_unit(facts[tag])
            byend = {}
            for p in pts:
                end = p.get('end')
                if not end:
                    continue
                if key in DURATION_KEYS:
                    st = p.get('start')
                    if not st:
                        continue
                    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(st)).days
                    if not (75 <= days <= 100):
                        continue
                elif p.get('form') not in ('10-Q', '10-K', '20-F'):
                    continue
                prev = byend.get(end)
                if prev is None or p.get('filed', '') >= prev[1]:
                    byend[end] = (p['val'], p.get('filed', ''))
            if byend:
                items = sorted(byend.items())[-limit:]
                out[key] = {e: v for e, (v, _) in items}
                break
    return out


def quarterly_filled(cik: int, key: str, limit=10):
    """분기 시계열에 4분기를 역산해 채운다.

    10-K는 4분기를 따로 보고하지 않고 연간만 싣기 때문에, 그냥 뽑으면 Q4가 빠진 채로
    분기열이 만들어진다 — 이 상태로 '직전 분기 대비'를 계산하면 실제로는 두 분기 건너뛴
    비교가 되어 QoQ·YoY가 전부 틀어진다(실제로 발생한 버그).
    """
    q = quarterly_series(cik, [key], limit=40).get(key, {})
    ann = annual_series(cik, [key]).get(key, {})
    byq = dict(q)
    peryear = defaultdict(list)
    for end in q:
        peryear[int(end[:4])].append(end)
    for fy, total in ann.items():
        ends = sorted(peryear.get(fy, []))
        # 회계연도 마감월(대개 12월)과 같은 달로 끝나는 분기가 이미 있으면 Q4가 존재하는 것
        if len(ends) == 3:
            q4_end = f'{fy}-12-31'
            if q4_end not in byq:
                byq[q4_end] = total - sum(q[e] for e in ends)
    return {k: byq[k] for k in sorted(byq)[-limit:]}


def qoq_yoy(series: dict):
    """분기열(end_date -> 값)에서 직전분기·전년동기 대비 증감률. 날짜로 매칭한다."""
    ends = sorted(series)
    if not ends:
        return None, None, None
    last = ends[-1]
    cur = series[last]
    qoq = ((cur / series[ends[-2]] - 1) * 100) if len(ends) >= 2 and series[ends[-2]] else None
    ly = f'{int(last[:4]) - 1}{last[4:]}'
    prev = series.get(ly)
    if prev is None:                      # 마감일이 하루이틀 다를 수 있어 근접 매칭
        cands = [e for e in ends if e[:4] == ly[:4] and e[5:7] == ly[5:7]]
        prev = series[cands[0]] if cands else None
    yoy = ((cur / prev - 1) * 100) if prev else None
    return cur, qoq, yoy


# ── 가격 파생 지표 ─────────────────────────────────────────────────────
def monthly_matrix(ticker: str, years=6, since=None):
    """연도×월 상승률 행렬 + 월별 평균·승률.

    since: 이 날짜(YYYY-MM-DD) 이전 데이터는 버린다. SPAC 합병 상장 종목은 합병 전
    껍데기(신탁가 ~$10 고정) 시세가 같은 티커로 남아 있어, 그대로 쓰면 '변동 없는 달'이
    잔뜩 섞여 월별 평균·승률이 왜곡된다(SATL 2021년 전체가 실제 사례).

    Yahoo 월봉 타임스탬프는 그 달의 '첫날'이라(예: 2022-01-01), 실제 종가는 월말값인데도
    "since=2022-01-25"처럼 정확한 시각으로 자르면 합병이 있었던 1월 봉 전체가 통째로
    잘려나간다. 그러면 2월 수익률 계산의 기준(1월 종가)도 없어져 3월부터야 데이터가
    시작하는 결과가 났다(실제 발생한 버그). 그래서 연-월 단위로 잘라 전환월 자체는
    남기고(그 달 자체의 수익률만 계산 안 함, 다음 달의 기준값으로는 씀).
    """
    d = yf_chart(ticker, rng=f'{years}y', interval='1mo')
    cut_ym = None
    if since:
        sd = dt.date.fromisoformat(since)
        cut_ym = (sd.year, sd.month)
    rows = defaultdict(dict)
    opens = defaultdict(dict)
    for t, c, o in zip(d['ts'], d['close'], d.get('open') or [None] * len(d['ts'])):
        if c is None:
            continue
        dd = dt.datetime.utcfromtimestamp(t)
        if cut_ym and (dd.year, dd.month) < cut_ym:
            continue
        rows[dd.year][dd.month] = c
        # 그 달의 첫 시가만 기록(이미 있으면 유지) — 상장월 자체 등락률 계산용
        if o is not None and dd.month not in opens[dd.year]:
            opens[dd.year][dd.month] = o
    # 월간 수익률 = 전월 종가 대비
    flat = []
    for y in sorted(rows):
        for m in sorted(rows[y]):
            flat.append(((y, m), rows[y][m]))
    ret = {}
    for i in range(1, len(flat)):
        (y, m), c = flat[i]
        prev = flat[i - 1][1]
        if prev:
            ret[(y, m)] = (c / prev - 1) * 100
    # 맨 첫 달(상장월 등)은 "전월 종가"가 없어 위 루프에서 통째로 빠진다 — 표에서
    # 빈칸으로 남기는 대신, 그 달 자체의 시가 대비 종가로 등락률을 채운다(사용자
    # 지적: "상장월 수치가 매번 없다가 지적한 뒤에만 채워졌다" — 매번 수동 땜질하지
    # 말고 구조적으로 고친다). 시가 데이터 자체가 없으면 그때만 빈칸으로 남음.
    if flat:
        (y0, m0), c0 = flat[0]
        o0 = opens.get(y0, {}).get(m0)
        if o0 and (y0, m0) not in ret:
            ret[(y0, m0)] = (c0 / o0 - 1) * 100
    yrs = sorted({y for y, _ in ret})
    matrix = {y: {m: ret.get((y, m)) for m in range(1, 13)} for y in yrs}
    # 연간 수익률(해당 연도 첫 관측 대비 마지막)
    annual = {}
    for y in yrs:
        vals = [rows[y][m] for m in sorted(rows.get(y, {}))]
        py = [rows[y - 1][m] for m in sorted(rows.get(y - 1, {}))]
        base = py[-1] if py else (vals[0] if vals else None)
        if base and vals:
            annual[y] = (vals[-1] / base - 1) * 100
    avg = {m: _mean([matrix[y][m] for y in yrs if matrix[y][m] is not None]) for m in range(1, 13)}
    win = {}
    for m in range(1, 13):
        vs = [matrix[y][m] for y in yrs if matrix[y][m] is not None]
        win[m] = (sum(1 for v in vs if v > 0) / len(vs) * 100) if vs else None
    return {'years': sorted(yrs, reverse=True), 'matrix': matrix, 'annual': annual,
            'avg': avg, 'win': win}


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def drawdown(ticker: str, years=6, since=None):
    """전고점 대비 낙폭(MDD) 시계열 + 현재/1년/전체 최대낙폭."""
    d = yf_chart(ticker, rng=f'{years}y', interval='1d')
    cut = dt.datetime.fromisoformat(since).timestamp() if since else None
    pts = [(t, c) for t, c in zip(d['ts'], d['close']) if c and not (cut and t < cut)]
    peak, series = 0.0, []
    for t, c in pts:
        peak = max(peak, c)
        series.append((t, (c / peak - 1) * 100))
    cur = series[-1][1] if series else None
    worst = min((v for _, v in series), default=None)
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=365)).timestamp()
    y1 = [v for t, v in series if t >= cutoff]
    # 1년 구간은 그 구간의 자체 고점 기준으로 다시 계산해야 의미가 맞음
    p1 = [(t, c) for t, c in pts if t >= cutoff]
    peak1, dd1 = 0.0, []
    for t, c in p1:
        peak1 = max(peak1, c)
        dd1.append((c / peak1 - 1) * 100)
    return {'series': series, 'current': cur, 'max_all': worst,
            'max_1y': min(dd1) if dd1 else None, 'years': years}


def weekly_price(ticker: str, years=5, since=None):
    d = yf_chart(ticker, rng=f'{years}y', interval='1wk')
    cut = dt.datetime.fromisoformat(since).timestamp() if since else None
    pts = [(t, c) for t, c in zip(d['ts'], d['close']) if c and not (cut and t < cut)]
    return {'points': pts, 'meta': d['meta']}


# ── 내부자 보유현황 (SEC Form 3/4 XML) ─────────────────────────────────
def _f345_parse(xml: str):
    """Form 3/4/5 XML에서 신고인·직위·거래후 보유주식수를 뽑는다."""
    def one(tag, s=xml):
        m = re.search(rf'<{tag}>(.*?)</{tag}>', s, re.S)
        return m.group(1).strip() if m else ''

    def val(block):
        m = re.search(r'<value>([\d.]+)</value>', block)
        return float(m.group(1)) if m else None

    name = one('rptOwnerName')
    title = one('officerTitle')
    if not title:
        roles = []
        if one('isDirector') == '1':
            roles.append('이사')
        if one('isTenPercentOwner') == '1':
            roles.append('10%+ 주주')
        title = ' · '.join(roles)
    # 비파생(보통주) 보유 — 각 거래행의 '거래 후 보유수' 중 마지막 값이 최신 잔고
    holdings = {}
    for blk in re.findall(r'<nonDerivativeTransaction>.*?</nonDerivativeTransaction>|'
                          r'<nonDerivativeHolding>.*?</nonDerivativeHolding>', xml, re.S):
        sec = re.search(r'<securityTitle>\s*<value>(.*?)</value>', blk, re.S)
        sec = sec.group(1).strip() if sec else '보통주'
        post = re.search(r'<sharesOwnedFollowingTransaction>(.*?)</sharesOwnedFollowingTransaction>', blk, re.S)
        own = re.search(r'<directOrIndirectOwnership>\s*<value>(.*?)</value>', blk, re.S)
        v = val(post.group(1)) if post else None
        if v is not None:
            holdings[(sec, (own.group(1).strip() if own else 'D'))] = v
    return {'name': name, 'title': title, 'holdings': holdings,
            'date': one('periodOfReport') or one('signatureDate')}


def insiders(cik: int, limit_filings=40, ttl_h=24):
    """최근 Form 3/4에서 인물별 최신 보유주식수를 집계. 반환: [{name,title,shares,date}]"""
    def go():
        j = requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                         headers=SEC_H, timeout=40).json()
        rec = j['filings']['recent']
        rows = []
        seen = 0
        for form, acc, date, doc in zip(rec['form'], rec['accessionNumber'],
                                        rec['filingDate'], rec['primaryDocument']):
            if form not in ('4', '3', '4/A') or seen >= limit_filings:
                continue
            seen += 1
            base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
            try:
                idx = requests.get(base + '/index.json', headers=SEC_H, timeout=20).json()
                xmls = [i['name'] for i in idx['directory']['item']
                        if i['name'].endswith('.xml') and 'form' in i['name'].lower()]
                if not xmls:
                    continue
                xml = requests.get(f'{base}/{xmls[0]}', headers=SEC_H, timeout=20).text
                p = _f345_parse(xml)
                if p['name']:
                    p['filed'] = date
                    rows.append(p)
                time.sleep(0.12)          # SEC 요청 예의(10 req/s 제한)
            except Exception:
                continue
        # 인물별 최신 1건만
        latest = {}
        for r in rows:
            k = r['name'].upper()
            if k not in latest or r['filed'] > latest[k]['filed']:
                latest[k] = r
        out = []
        for r in latest.values():
            total = sum(v for (sec, own), v in r['holdings'].items())
            if not total:
                continue
            out.append({'name': r['name'], 'title': r['title'], 'shares': total,
                        'date': r['filed'],
                        'detail': {f'{s} ({o})': v for (s, o), v in r['holdings'].items()}})
        return sorted(out, key=lambda x: -x['shares'])
    return _cached(f'insiders_{cik}', ttl_h, go)


# 위임장의 실질보유 섹션 제목은 회사마다 다르다. SATL은 "Common Stock Ownership by
# Directors and Executive Officers", 대부분 회사(예: PLTR)는 SEC 표준 문구인
# "Security Ownership of Certain Beneficial Owners and Management"를 쓴다.
_OWNERSHIP_HEADINGS = [
    r'Security Ownership of Certain Beneficial Owners',
    r'Ownership by Directors and Executive Officers',
    r'Common Stock Ownership by Directors',
    r'Principal (?:Stock)?[Hh]olders',
]


def beneficial_owners(cik: int, ttl_h=48):
    """DEF 14A(위임장)의 '임원·이사 실질보유' 표를 파싱.

    Form 4는 직접보유 보통주만 잡혀서 엔티티 보유·복수 클래스가 누락된다
    (SATL: Form4 합계 1.3% vs 위임장 29.09%). 지분 구조는 위임장이 정답.

    2주식클래스(A/B) 구조는 컬럼을 (주식수,지분율)×2로 그대로 읽지만, 3클래스 이상
    (PLTR의 A/B/F처럼 클래스마다 의결권 배수가 달라 열 구성이 회사마다 제각각)은
    끝자리 숫자만 억지로 끼워맞추면 틀린 값을 만들 위험이 크다. 그래서 클래스가
    2개 넘게 감지되면 "첫 주식수 + 마지막 퍼센트"만 일반형으로 뽑는다 — 정밀한
    클래스별 분해는 포기하되 최소한 사실과 다른 숫자는 안 만든다.
    """
    def go():
        j = requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                         headers=SEC_H, timeout=40).json()
        rec = j['filings']['recent']
        target = None
        for form, acc, date, doc in zip(rec['form'], rec['accessionNumber'],
                                        rec['filingDate'], rec['primaryDocument']):
            if form == 'DEF 14A':
                target = (acc.replace('-', ''), doc, date)
                break
        if not target:
            return {}
        acc, doc, date = target
        url = f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}'
        t = requests.get(url, headers=SEC_H, timeout=60).text

        locs = []
        for pat in _OWNERSHIP_HEADINGS:
            locs += [m.start() for m in re.finditer(pat, t, re.I)]
        if not locs:
            return {}
        seg = t[max(locs):max(locs) + 40000]

        # 헤더 행에서 "Class" 언급 횟수로 몇 클래스 구조인지 판단
        header_area = seg[:4000]
        n_classes = len(set(re.findall(r'Class\s+[A-Z]\b', header_area, re.I)))
        simple = n_classes <= 2

        # 40000자 고정 윈도우가 실제 소유지분 표 경계를 넘어 다음 절(예: "OTHER MATTERS",
        # "Delinquent Section 16(a) Reports")까지 삼키는 경우가 실측으로 확인됨(IONQ) —
        # 그 절 제목들이 표 형태 레이아웃과 우연히 맞아떨어지면 사람 이름 행처럼 파싱된다.
        # 완전한 구조적 수정(표 경계 자체를 정확히 찾기)은 위험도가 커서, 대신 "사람
        # 이름처럼 안 생긴" 행을 걸러내는 안전장치를 추가한다.
        _NON_NAME = re.compile(
            r'^(OTHER MATTERS?|DELINQUENT|SECTION\s*16|ANNUAL REPORT|BENEFICIAL OWNERSHIP|'
            r'PRINCIPAL (STOCKHOLDERS?|SHAREHOLDERS?)|EXECUTIVE (OFFICERS?|COMPENSATION)|'
            r'DIRECTORS? AND EXECUTIVE|\d{4}\b.*REPORT)', re.I)

        # 키워드 블랙리스트만으로는 계속 새 절 제목이 새어 들어온다(실측: 블랙리스트
        # 적용 후에도 "Stockholder Proposals or"·"Availability of Bylaws"가 남음 —
        # 40000자 윈도우가 실제 표 경계를 한참 넘어간다는 게 근본 원인이라 계속 다른
        # 제목이 걸릴 수 있음). 개별 키워드를 계속 추가하는 대신 더 일반적인 신호를
        # 쓴다 — 사람 이름은 "or"·"of"·"and" 같은 전치사/접속사를 단어로 안 포함한다
        # (문장이 잘린 절 제목은 대개 이런 단어로 끝나거나 포함함).
        _STOPWORDS = {'or', 'of', 'and', 'the', 'for', 'to', 'in', 'a', 'an', 'with'}
        # 특정 문구를 계속 블랙리스트에 추가하는 방식은 밑빠진 독(실측: AAPL에서
        # "2026 Proxy Statement"·"Equity compensation plan"이 새로 걸림) — 대신
        # 문서 제목류의 일반적인 생김새 두 가지를 잡는다: (1) 4자리 연도로 시작
        # ("20XX ... Statement/Report" 패턴), (2) 문서/제도 명사로 끝남(사람 성이
        # 될 수 없는 단어들). 실제 사람 이름이 우연히 이 단어로 끝날 일은 없음.
        _DOC_NOUNS = {'statement', 'report', 'plan', 'program', 'policy',
                      'agreement', 'table', 'summary', 'reports'}

        def _looks_like_name(nm):
            if _NON_NAME.match(nm):
                return False
            if re.match(r'^\d{4}\b', nm):
                return False
            words = nm.split()
            if words and words[-1].lower().strip('.,') in _DOC_NOUNS:
                return False
            # "Equity compensation plans approved by shareholders" 같은 절 제목은
            # _DOC_NOUNS가 마지막 단어만 보다 보니 안 걸렸다(실측: AAPL — 마지막
            # 단어가 "shareholders") — 사람 이름이 6단어를 넘는 경우는 사실상 없으니
            # 단어 수 자체로도 거른다.
            if len(words) > 5:
                return False
            # 전부 대문자인 짧은 구문(섹션 제목 스타일)도 걸러낸다 — 회사 임원 이름은
            # 보통 "First Last" 형태로 대소문자가 섞여 있음.
            if nm.isupper() and len(words) <= 6:
                return False
            if any(w.lower() in _STOPWORDS for w in words):
                return False
            return True

        rows = []
        for r in re.findall(r'<tr[^>]*>(.*?)</tr>', seg, re.S):
            cells = [html.unescape(re.sub(r'<[^>]+>', ' ', c)).strip()
                     for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)]
            cells = [re.sub(r'\s+', ' ', c) for c in cells if c.strip() not in ('', '$', '%', '(', ')')]
            if len(cells) < 2 or not re.search(r'[A-Za-z]{3}', cells[0]):
                continue
            if not _looks_like_name(cells[0]):
                continue
            nums = [c for c in cells[1:] if re.fullmatch(r'[\d,]+(\.\d+)?|\*', c)]
            if not nums:
                continue

            def n(v):
                return None if v in (None, '*') else float(v.replace(',', ''))
            name = re.sub(r'\s*\(\d+\)\s*$', '', cells[0]).strip()
            if simple:
                rows.append({'name': name,
                            'a_shares': n(nums[0] if len(nums) > 0 else None),
                            'a_pct': n(nums[1] if len(nums) > 1 else None),
                            'b_shares': n(nums[2] if len(nums) > 2 else None),
                            'b_pct': n(nums[3] if len(nums) > 3 else None)})
            else:
                # 다클래스 — 첫 주식수(대표 보유량) + 마지막 값이 %처럼 보이면 그것만 채택
                last = nums[-1]
                pct = n(last) if (last == '*' or (re.fullmatch(r'\d{1,3}\.\d+', last)
                                                  and float(last) <= 100)) else None
                rows.append({'name': name, 'a_shares': n(nums[0]), 'a_pct': pct,
                            'b_shares': None, 'b_pct': None})
        # 그룹합계 행 문구가 회사마다 다르다 — SATL "All directors and current executive officers",
        # PLTR "All executive officers and directors" 등. "all"로 시작하고 officer/director를
        # 언급하는 행을 그룹행으로 분류(PLTR 검증에서 이 매칭이 좁아 그룹행이 개인 명단에
        # 섞여 들어가는 걸 확인함).
        def _is_group_row(name):
            low = name.lower()
            return low.startswith('all ') and ('director' in low or 'officer' in low)
        people = [r for r in rows if not _is_group_row(r['name'])]
        group = next((r for r in rows if _is_group_row(r['name'])), None)
        return {'as_of': date, 'url': url, 'people': people, 'group': group, 'simple_2class': simple}
    return _cached(f'proxy_{cik}', ttl_h, go)


def technical_snapshot(ticker: str, since=None):
    """현재가·52주 레인지·MA50/200·추세 판정 — 전부 일봉에서 직접 계산.

    처음엔 종목별 데이터 파일(satl16_data.py의 TECH)에 손으로 이 숫자들을 박아뒀는데,
    PLTR 검증 때 그대로 복붙하면 SATL 얘기("하락 추세", 특정 %)를 다른 종목에 그대로
    떠넘기는 꼴이라는 게 드러났다. 종목마다 실제로 계산해야 맞는 말을 한다.
    """
    d = yf_chart(ticker, rng='2y', interval='1d')
    cut = dt.datetime.fromisoformat(since).timestamp() if since else None
    pts = [(t, c) for t, c in zip(d['ts'], d['close']) if c and not (cut and t < cut)]
    if len(pts) < 50:
        return {}
    closes = [c for _, c in pts]
    price = closes[-1]
    cutoff_1y = pts[-1][0] - 365 * 86400
    last_1y = [c for t, c in pts if t >= cutoff_1y]
    hi52, lo52 = max(last_1y), min(last_1y)
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
    vs50 = (price / ma50 - 1) * 100
    vs200 = (price / ma200 - 1) * 100 if ma200 else None
    trend = '상승' if (vs200 is not None and vs50 > 0 and vs200 > 0) else \
            ('하락' if (vs200 is not None and vs50 < 0 and vs200 < 0) else '혼조')
    # 이 가격이 '언제 종가'인지는 여기서만 알 수 있다. 안 돌려주면 카드가 데이터 파일에
    # 박힌 초안 날짜를 대신 쓰게 되고, 그러면 최신 가격에 옛 날짜가 붙는다(2026-08-19 실측:
    # TSLA 카드가 08-18 종가를 찍으면서 부제는 '07-24 종가 기준'이었다).
    last_ts = pts[-1][0]
    return {
        'price': price, 'hi52': hi52, 'lo52': lo52, 'ma50': ma50, 'ma200': ma200,
        'from_high_pct': (price / hi52 - 1) * 100, 'from_low_pct': (price / lo52 - 1) * 100,
        'vs_ma50_pct': vs50, 'vs_ma200_pct': vs200, 'trend': trend,
        'asof': dt.datetime.fromtimestamp(last_ts, dt.timezone.utc).strftime('%Y-%m-%d'),
    }


def _ema(vals, period):
    """지수이동평균 — 첫 값은 초기 SMA로 시드(표준 관행), 이후 표준 EMA 재귀식."""
    if len(vals) < period:
        return [None] * len(vals)
    k = 2 / (period + 1)
    out = [None] * (period - 1)
    seed = sum(vals[:period]) / period
    out.append(seed)
    prev = seed
    for v in vals[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def _rsi(closes, period=14):
    """RSI — Wilder 평활화(단순 이동평균 아님, 표준 RSI 정의)."""
    n = len(closes)
    if n < period + 1:
        return [None] * n
    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]
    out = [None] * period   # 첫 period개는 워밍업 구간이라 계산 불가
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rs = avg_gain / avg_loss if avg_loss else float('inf')
    out.append(100 - 100 / (1 + rs) if avg_loss else 100.0)
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss else float('inf')
        out.append(100 - 100 / (1 + rs) if avg_loss else 100.0)
    return out


def _macd(closes, fast=12, slow=26, signal=9):
    """MACD = EMA(fast)-EMA(slow), 시그널선=MACD의 EMA(signal), 히스토그램=MACD-시그널."""
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [(a - b) if (a is not None and b is not None) else None
                 for a, b in zip(ema_fast, ema_slow)]
    valid = [v for v in macd_line if v is not None]
    sig_valid = _ema(valid, signal)
    sig_full, it = [], iter(sig_valid)
    started = False
    for v in macd_line:
        if v is None:
            sig_full.append(None)
        else:
            started = True
            sig_full.append(next(it))
    hist = [(m - s) if (m is not None and s is not None) else None
            for m, s in zip(macd_line, sig_full)]
    return macd_line, sig_full, hist


def daily_ohlcv(ticker: str, display_days=90, since=None):
    """일봉 OHLCV + RSI(14) + MACD(12,26,9) — 캔들스틱·거래량·오실레이터 페이지용.
    RSI/MACD는 워밍업(최대 26+9=35봉)이 필요해서 1년치를 받아 전체 구간에서 계산한 뒤,
    화면엔 최근 display_days개만 잘라 보여준다(지표 값 자체는 잘리기 전 전체 이력 기준)."""
    d = yf_chart(ticker, rng='1y', interval='1d')
    ts, o, h, lo, c, v = d['ts'], d.get('open'), d['high'], d['low'], d['close'], d.get('volume')
    rows = [(t, oo, hh, ll, cc, vv) for t, oo, hh, ll, cc, vv in zip(ts, o, h, lo, c, v)
            if None not in (oo, hh, ll, cc)]
    if since:
        cut = dt.datetime.fromisoformat(since).timestamp()
        rows = [r for r in rows if r[0] >= cut]
    if len(rows) < 30:
        return {}
    closes = [r[4] for r in rows]
    rsi = _rsi(closes, 14)
    macd_line, sig_line, hist = _macd(closes, 12, 26, 9)
    start = max(0, len(rows) - display_days)
    return {
        'rows': rows[start:], 'rsi': rsi[start:],
        'macd': macd_line[start:], 'signal': sig_line[start:], 'hist': hist[start:],
    }


def _resample_monthly(rows):
    """(ts,o,h,l,c,v) 시계열을 달력월 단위로 강제 리샘플.

    Yahoo가 range=max+interval=1mo 요청에도 실제로는 주봉을 돌려주는 게 실측으로
    확인됨(IONQ: meta.dataGranularity='1wk', 5.5년치에 292개 — 66개여야 할 게 292개).
    "월봉"이라고 요청 파라미터를 믿으면 RSI·MACD "월 단위 계산" 문구가 거짓말이 되고,
    (row 개수)=(개월 수)를 전제하는 계산(예: 상장후 CAGR의 연환산)이 전부 틀어진다 —
    응답이 뭘 자칭하든 실제 타임스탬프의 달력월로 직접 묶어서 진짜 월봉을 만든다."""
    if not rows:
        return rows
    buckets = {}
    order = []
    for t, o, h, l, c, v in rows:
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        key = (d.year, d.month)
        if key not in buckets:
            buckets[key] = [t, o, h, l, c, v or 0]
            order.append(key)
        else:
            b = buckets[key]
            b[0] = t                          # 그 달의 마지막 타임스탬프를 대표값으로
            b[2] = max(b[2], h)
            b[3] = min(b[3], l)
            b[4] = c                          # 마지막으로 덮어써 월말 종가가 남게
            b[5] += (v or 0)
    return [tuple(buckets[k]) for k in order]


def monthly_ohlcv(ticker: str, since=None):
    """월봉 OHLCV + RSI(14)·MACD(12,26,9) — 상장일부터 전체 이력.

    daily_ohlcv(최근 90거래일)는 "몇 달에 한 번 보고 안 봐도 되는" 이 카드의 목적과
    안 맞는다는 지적(3개월 치 일봉은 단타용 그림이지 장기 참고용이 아님) — 월봉으로 바꾸면
    상장 후 전체(수십~백수십개월)를 한 장에 담을 수 있고, RSI·MACD도 월 단위로 계산해
    장기 추세 확인용으로 의미가 맞는다. range='max'가 Yahoo에서 상장일까지 전부 준다."""
    d = yf_chart(ticker, rng='max', interval='1mo')
    ts, o, h, lo, c, v = d['ts'], d.get('open'), d['high'], d['low'], d['close'], d.get('volume')
    rows = [(t, oo, hh, ll, cc, vv) for t, oo, hh, ll, cc, vv in zip(ts, o, h, lo, c, v)
            if None not in (oo, hh, ll, cc)]
    rows = _resample_monthly(rows)
    if since:
        cut = dt.datetime.fromisoformat(since).timestamp()
        rows = [r for r in rows if r[0] >= cut]
    if len(rows) < 12:
        return {}
    closes = [r[4] for r in rows]
    rsi = _rsi(closes, 14)
    macd_line, sig_line, hist = _macd(closes, 12, 26, 9)
    return {'rows': rows, 'rsi': rsi, 'macd': macd_line, 'signal': sig_line, 'hist': hist}


# ── 회사 웹사이트 / 경영진 사진 (best-effort) ──────────────────────────
def company_site(cik: int, fallback=None):
    try:
        j = requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json',
                         headers=SEC_H, timeout=30).json()
        for k in ('website', 'investorWebsite'):
            if j.get(k):
                return j[k]
    except Exception:
        pass
    return fallback


LEADER_PATHS = ['/leadership', '/team', '/about/leadership', '/company/leadership',
                '/about-us/leadership', '/about', '/company/team', '/our-team',
                '/management', '/management.html', '/governance/management-team',
                # 사용자가 IONQ에서 실제로 찾아준 경로 — Q4/EQS 계열 IR 사이트 템플릿이
                # investors.*/governance/board-of-directors 패턴을 많이 씀(default.aspx는
                # 그 플랫폼의 관행적 파일명). leadership류 경로만 훑던 이전 목록엔 없었음.
                '/governance/board-of-directors', '/governance/board-of-directors/default.aspx',
                '/governance/executive-management', '/governance/executive-management/default.aspx',
                '/board-of-directors', '/leadership-team', '/executive-team']


def leader_photo(site: str, person: str, out_path: Path):
    """회사 공식 사이트 경영진 페이지에서 인물 사진 후보를 찾아 저장. 실패하면 None.
    ⚠️ 회사 보도자료용 이미지라도 상업적 재배포는 회색지대 — 사용자가 리스크를 알고 선택함.

    많은 회사가 경영진 소개를 마케팅 사이트가 아니라 IR 서브도메인(investors.*, ir.*)에
    올려둔다(PLTR 실제 사례: investors.palantir.com/management.html). 그래서 주어진
    사이트뿐 아니라 같은 도메인의 investors./ir. 서브도메인도 같이 시도한다.
    """
    if not site or out_path.exists():
        return str(out_path) if out_path.exists() else None
    last = person.split()[-1].lower()
    base = site.rstrip('/')
    m = re.match(r'https?://(?:www\.)?([\w.-]+)', base)
    domain = m.group(1) if m else ''
    bases = [base]
    if domain:
        bases += [f'https://investors.{domain}', f'https://ir.{domain}']
    for base in bases:
        for path in LEADER_PATHS:
            try:
                r = requests.get(base + path, headers={'User-Agent': UA}, timeout=15)
                if r.status_code != 200:
                    continue
                imgs = re.findall(r'<img[^>]+>', r.text, re.I)
                cands = []
                for tag in imgs:
                    src = re.search(r'(?:data-src|srcset|src)=["\']([^"\'\s]+)', tag, re.I)
                    if not src:
                        continue
                    u = src.group(1)
                    blob = tag.lower()
                    if last in blob or last in u.lower():
                        cands.append(u)
                if not cands:
                    continue
                u = cands[0]
                if u.startswith('//'):
                    u = 'https:' + u
                elif u.startswith('/'):
                    u = base + u
                img = requests.get(u, headers={'User-Agent': UA}, timeout=20)
                if img.status_code == 200 and len(img.content) > 3000:
                    out_path.write_bytes(img.content)
                    return str(out_path)
            except Exception:
                continue
    return None


# ── 차트·수급 (오닐·리버모어 페이지용, 2026-10-20) ─────────────────────
def daily_ohlcv(ticker: str, years=2):
    """일봉 [{'t','o','h','l','c','v'}] 오래된→최신. 빈 값(휴장 등)은 뺀다."""
    d = yf_chart(ticker, rng=f'{years}y', interval='1d')
    out = []
    for i, t in enumerate(d['ts']):
        row = {k: (d[src][i] if d.get(src) else None)
               for k, src in (('o', 'open'), ('h', 'high'), ('l', 'low'), ('c', 'close'), ('v', 'volume'))}
        if row['c'] is None:
            continue
        row['t'] = t
        out.append(row)
    return out


def nasdaq_institutional(ticker: str):
    """나스닥 공개 API 의 기관 보유 활동 — 오닐 I(기관 매집)의 '보유 기관 수가 늘고 있나'.

    반환: {'increased','decreased','held','new','soldout' (기관 수), 'pct' (보유 비율 %)}.
    실패하면 {} — 페이지가 '판단 불가'로 표시한다. 데이터센터 IP 차단 가능성이 있어
    러너에서 실측 확인이 필요하다(2026-10-20 신설).
    """
    try:
        r = requests.get(f'https://api.nasdaq.com/api/company/{ticker.upper()}/institutional-holdings',
                         params={'limit': 1, 'type': 'TOTAL', 'sortColumn': 'marketValue'},
                         headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*',
                                  'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'},
                         timeout=20).json()
        d = (r or {}).get('data') or {}
    except Exception as e:
        print(f'[nasdaq 기관] {ticker}: {e}')
        return {}

    def num(s):
        try:
            return float(str(s).replace(',', '').replace('%', '').replace('$', '').strip())
        except Exception:
            return None
    out = {}
    for row in ((d.get('activePositions') or {}).get('rows') or []) + \
               ((d.get('newSoldOutPositions') or {}).get('rows') or []):
        name = str(row.get('positions') or '').lower()
        key = ('increased' if 'increased' in name else 'decreased' if 'decreased' in name else
               'held' if 'held' in name else 'new' if 'new' in name else 'soldout' if 'sold' in name else None)
        if key:
            out[key] = num(row.get('holders'))
    pct = ((d.get('ownershipSummary') or {}).get('SharesOutstandingPCT') or {}).get('value')
    if pct is not None:
        out['pct'] = num(pct)
    return out
