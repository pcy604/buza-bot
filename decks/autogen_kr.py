# -*- coding: utf-8 -*-
"""한국 종목 {ticker}_data.py 초안 생성기.

    python autogen_kr.py 247540.KQ            # 결정론 필드만 (LLM 0콜)
    python autogen_kr.py 247540.KQ --narrate  # + 서사 필드 LLM 생성

autogen.py(미국)와 **같은 스키마**를 쓴다 — build.py/deck_pages.py는 데이터 파일이
어느 시장에서 왔는지 몰라도 된다.

## 왜 별도 파일인가

autogen.py는 10-K/DEF 14A/Form 4/어닝콜 원문을 전제로 짜여 있다. 한국은 원문 자체가
다르고(사업보고서·잠정실적공시·임원소유보고), 무엇보다 **미국에서 LLM으로 캐내던 값 중
상당수를 DART가 구조화 필드로 그냥 준다**:

    미국                              한국
    위임장에서 CEO 이름 추출(LLM)  →  company.json ceo_nm
    제출서류에서 상장시장 추정      →  company.json corp_cls (Y=코스피 K=코스닥)
    죽은 Clearbit → 위키 로고 탐색  →  company.json hm_url
    8-K 원문을 LLM으로 읽어 실적    →  잠정실적 공정공시 표(결정론 파싱)

그래서 LLM이 필요한 자리가 미국판보다 훨씬 좁다. 좁은 만큼 명시적으로 나눈다 —
`build_deterministic()`은 LLM을 **한 번도** 부르지 않고, 서사는 `--narrate`에서만.

## 안 채우는 것을 안 채운다고 쓴다

TAM·경쟁사·타임라인처럼 근거 없이 지어낼 수 있는 자리는 빈 값 + 자리표시자로 둔다.
check.py가 그걸 '대기'로 잡아 발행을 막는다 — 비어 있어서 못 내보내는 건 괜찮지만,
지어낸 값으로 나가는 건 안 된다.
"""
import io
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sources_kr as K  # noqa: E402
import sources as S  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))

PLACEHOLDER = '(확인 필요)'


def _today():
    return datetime.now(KST).strftime('%Y-%m-%d')


def _dt(s):
    """DART 날짜(YYYYMMDD) → YYYY-MM-DD. 빈 값은 빈 문자열."""
    s = str(s or '').strip()
    return f'{s[:4]}-{s[4:6]}-{s[6:8]}' if len(s) == 8 and s.isdigit() else ''


def _ceo_name(raw: str) -> str:
    """DART ceo_nm은 '각자 대표이사 최문호, 김장우'처럼 직함과 복수 이름이 섞여 온다.

    첫 사람만 골라 이름만 남긴다 — 카드의 CEO 칸은 한 명을 전제로 그려진다.
    복수 대표는 leadership note에 원문 그대로 남겨 정보를 잃지 않는다."""
    s = ' '.join(str(raw or '').split())
    for title in ('각자 대표이사', '공동대표이사', '대표이사 사장', '대표이사 회장',
                  '대표집행임원', '대표이사', '사내이사', '회장', '사장'):
        s = s.replace(title, ' ')
    first = s.replace(',', ' ').split()
    return first[0] if first else ''


def _pct(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    if prev < 0:
        return '흑자전환' if cur > 0 else None
    return (cur / prev - 1) * 100


def _fmt_delta(v):
    if v is None:
        return ''
    return v if isinstance(v, str) else f'{v:+.0f}% YoY'


def gather(symbol: str):
    """한 종목의 원자재를 전부 모은다. LLM 0콜."""
    corp = K.to_corp_code(symbol)
    if not corp:
        raise SystemExit(f'{symbol}: DART corp_code를 못 찾음 — 종목코드 확인 필요')
    info = K.company_info(corp)
    if not info:
        raise SystemExit(f'{symbol}: DART 회사개황 조회 실패')
    ann = K.annual_series(corp)
    qtr = K.quarterly_series(corp, limit=14)
    prov = K.provisional_results(corp)
    cons = S.consensus(symbol) or {}
    tech = S.technical_snapshot(symbol) or {}
    insiders = K.insiders(corp, 15)
    return dict(symbol=symbol.upper(), corp=corp, info=info, ann=ann, qtr=qtr,
                prov=prov, cons=cons, tech=tech, insiders=insiders)


# ── RESULTS: 잠정실적 공정공시에서 결정론으로 ──────────────────────────
def _results(raw):
    """미국판은 8-K 원문을 LLM으로 읽어 KPI를 뽑는다. 한국은 잠정실적 공시가
    표준 표로 오므로 **LLM 없이** 같은 것을 만든다. 게다가 회사가 증감율과
    흑자적자전환 여부를 직접 계산해 실어준다."""
    prov = raw['prov']
    if not prov or not prov.get('rows'):
        return None
    per = (prov.get('periods') or {}).get('당기') or []
    label = ''
    if len(per) == 2:
        end = per[1]
        m = int(end[5:7])
        label = f'{end[:4]} {m // 3}Q' if m in (3, 6, 9, 12) else f'{end[:4]}.{end[5:7]}'

    want = [('매출액', '매출'), ('영업이익', '영업이익'),
            ('법인세비용차감전계속사업이익', '세전이익'), ('당기순이익', '순이익')]
    kpis = []
    for src_name, disp in want:
        d = (prov['rows'].get(src_name) or {}).get('당해')
        if not d or d.get('당기') is None:
            continue
        yoy, turn = d.get('전년동기대비'), d.get('전년동기전환')
        sub = turn if turn else (f'{yoy:+.0f}% YoY' if yoy is not None else '')
        arrow = 'up' if (yoy or 0) > 0 or turn == '흑자전환' else (
            'dn' if (yoy is not None and yoy < 0) or turn == '적자전환' else 'flat')
        kpis.append((disp, d['당기'], sub, arrow))

    facts = []
    for src_name, disp in want:
        d = (prov['rows'].get(src_name) or {}).get('당해')
        if not d or d.get('당기') is None:
            continue
        qoq = d.get('전기대비')
        why = (d.get('전년동기전환') or
               (f'직전 분기 대비 {qoq:+.1f}%' if qoq is not None else '전기 대비 미표시'))
        facts.append((disp, why, d['당기']))
    return {'period': label, 'kpis': kpis, 'facts': facts,
            'rcept_dt': _dt(prov.get('rcept_dt')), 'url': prov.get('url', ''),
            'unit': prov.get('unit', '')}


def _results_from_qtr(raw):
    """잠정실적 공시가 없는 회사(코스닥 중소형주 다수 — 2026-10-23 피에스케이홀딩스)의 2p KPI.
    DART 정기보고서 분기 재무(raw['qtr'])의 **최근 분기**를 쓴다. 전년 동기(4분기 전)와 비교해
    YoY, 부호가 바뀌면 흑자/적자전환. 공시 표를 그대로 옮기는 것이라 LLM 0콜·지어낸 값 0."""
    q = raw.get('qtr') or {}
    rev = q.get('revenue') or {}
    if not rev:
        return None
    end = sorted(rev)[-1]
    y, mo = int(end[:4]), int(end[5:7])
    prev_end = next((e for e in sorted(rev) if e.startswith(f'{y - 1}-{end[5:7]}')), None)
    label = f'{y} {mo // 3}Q' if mo in (3, 6, 9, 12) else f'{y}.{end[5:7]}'
    kpis, facts = [], []
    for key, disp in (('revenue', '매출'), ('opinc', '영업이익'), ('netinc', '순이익')):
        ser = q.get(key) or {}
        cur = ser.get(end)
        if cur is None:
            continue
        pv = ser.get(prev_end) if prev_end else None
        turn = ('흑자전환' if pv is not None and pv < 0 <= cur else
                '적자전환' if pv is not None and pv >= 0 > cur else None)
        yoy = (cur / pv - 1) * 100 if (pv and pv > 0 and cur >= 0) else None
        sub = turn or (f'{yoy:+.0f}% YoY' if yoy is not None else '')
        arrow = 'up' if (yoy or 0) > 0 or turn == '흑자전환' else (
            'dn' if (yoy is not None and yoy < 0) or turn == '적자전환' else 'flat')
        kpis.append((disp, cur, sub, arrow))
        ends = sorted(ser)
        i = ends.index(end)
        qp = ser.get(ends[i - 1]) if i > 0 else None
        why = turn or (f'직전 분기 대비 {(cur / qp - 1) * 100:+.1f}%' if (qp and qp > 0 and cur >= 0) else '전기 대비 미표시')
        facts.append((disp, why, cur))
    if not kpis:
        return None
    return {'period': label, 'kpis': kpis, 'facts': facts, 'rcept_dt': None, 'url': '',
            'unit': '원', 'from_qtr': True}


def _summary(raw):
    """이 파일에 이미 있는 숫자만 종합 — 새 주장을 만들지 않는다(LLM 0콜)."""
    ann, lines = raw['ann'], []
    yrs = sorted(ann.get('revenue', {}))
    if yrs:
        y = yrs[-1]
        rev = ann['revenue'][y]
        prev = ann['revenue'].get(yrs[-2]) if len(yrs) >= 2 else None
        g = _pct(rev, prev)
        op = ann.get('opinc', {}).get(y)
        opm = (op / rev * 100) if (op is not None and rev) else None
        ni = ann.get('netinc', {}).get(y)
        g_txt = ('' if g is None else
                 f'(전년 대비 {g})' if isinstance(g, str) else f'(전년 대비 {g:+.1f}%)')
        parts = [f'FY{y} 매출 {rev / 1e8:,.0f}억원' + g_txt]
        if op is not None:
            parts.append(f'영업이익 {op / 1e8:,.0f}억원' + (f'(OPM {opm:.1f}%)' if opm is not None else ''))
        if ni is not None:
            parts.append(f'순이익 {ni / 1e8:,.0f}억원')
        lines.append(', '.join(parts) + '.')
        # 흑자·적자 전환 시점은 연간 계열에서 직접 읽는다(판단이 아니라 사실).
        # **가장 최근 전환 한 번만** 쓴다 — 에코프로비엠처럼 FY2024 적자전환 →
        # FY2025 흑자전환이 연달아 있으면 둘 다 나열해봐야 "그래서 지금 뭐냐"가 흐려진다.
        ops = [(v, ann.get('opinc', {}).get(v)) for v in yrs if ann.get('opinc', {}).get(v) is not None]
        turns = [(y1, '흑자' if v0 < 0 <= v1 else '적자')
                 for (y0, v0), (y1, v1) in zip(ops, ops[1:])
                 if (v0 < 0 <= v1) or (v0 >= 0 > v1)]
        if turns:
            y1, kind = turns[-1]
            lines.append(f'영업이익은 FY{y1}에 {kind}로 돌아섬.')
    q = raw['qtr']
    cfo_ends = sorted(q.get('cfo', {}))
    cash_ends = sorted(q.get('cash', {}))
    if cfo_ends and cash_ends:
        lines.append(f'최근 분기 영업활동 현금흐름 {q["cfo"][cfo_ends[-1]] / 1e8:,.0f}억원 · '
                     f'보유 현금 {q["cash"][cash_ends[-1]] / 1e8:,.0f}억원.')
    return '\n'.join(lines)


def _checkpoints(raw):
    """지어내지 않고 **컨센서스에 실제로 있는 숫자**만 체크포인트로 만든다."""
    out, cons = [], raw['cons']
    p = (cons.get('periods') or {}).get('0y') or {}
    if p.get('rev') or p.get('eps'):
        bits = []
        if p.get('rev'):
            bits.append(f'매출 {p["rev"] / 1e8:,.0f}억원')
        if p.get('eps'):
            bits.append(f'EPS {p["eps"]:,.0f}원')
        out.append((f'FY{p.get("end", "")}', '연간 컨센서스 달성 여부',
                    ' · '.join(bits) + f' (애널리스트 {cons.get("analysts", "—")}명)', 'high'))
    tm, px = cons.get('target_mean'), cons.get('price')
    if tm and px:
        out.append(('상시', '목표주가 괴리 해소 여부',
                    f'현재 {px:,.0f}원 → 목표 {tm:,.0f}원 ({(tm / px - 1) * 100:+.0f}%)', 'mid'))
    return out


def build_deterministic(symbol: str):
    """LLM을 한 번도 부르지 않고 채울 수 있는 전부를 채운 dict."""
    raw = gather(symbol)
    info, ann, qtr = raw['info'], raw['ann'], raw['qtr']
    corp_cls = (info.get('corp_cls') or '').upper()
    exchange = K._MARKET.get(corp_cls, ('기타', ''))[0]
    res = _results(raw) or _results_from_qtr(raw)
    as_of = (res or {}).get('rcept_dt') or _today()
    ceo_raw = info.get('ceo_nm') or ''
    return dict(
        raw=raw,
        AS_OF=as_of,
        BUILT_AT=_today(),
        SRC={'PR': (f'영업(잠정)실적 공정공시({as_of})' if res and not res.get('from_qtr') else
                    f'DART 정기보고서 분기 재무({res["period"]})' if res else 'DART 분기보고서'),
             'DECK': 'DART 사업보고서',
             'YF': 'Yahoo Finance chart API'},
        # 표지 회사명은 stock_name('에코프로비엠')을 쓴다. corp_name은 법인등기명이라
        # '(주)'가 붙어('(주)에코프로비엠') 카드 제목으로는 어색하다.
        COMPANY={'ticker': raw['symbol'],
                 'name': info.get('stock_name') or info.get('corp_name') or raw['symbol'],
                 'legal_name': info.get('corp_name') or '',
                 'exchange': exchange, 'sector': PLACEHOLDER, 'cik': raw['corp']},
        SITE=K.company_site(raw['corp'], fallback=''),
        HISTORY_founded=int(_dt(info.get('est_dt'))[:4]) if _dt(info.get('est_dt')) else None,
        CEO_NAME=_ceo_name(ceo_raw),
        CEO_RAW=ceo_raw,
        RESULTS=res,
        SUMMARY=_summary(raw),
        CHECKPOINTS=_checkpoints(raw),
        INSIDERS=raw['insiders'],
        ANN=ann, QTR=qtr,
    )


# ── 데이터 파일 쓰기 ───────────────────────────────────────────────────
def _py(v, indent=0):
    """파이썬 리터럴로 직렬화. repr을 쓰되 한글이 \\uXXXX로 깨지지 않게."""
    pad = ' ' * indent
    if isinstance(v, dict):
        if not v:
            return '{}'
        items = [f'{pad}    {_py(k)}: {_py(x, indent + 4)},' for k, x in v.items()]
        return '{\n' + '\n'.join(items) + f'\n{pad}}}'
    if isinstance(v, (list, tuple)):
        if not v:
            return '[]' if isinstance(v, list) else '()'
        o, c = ('[', ']') if isinstance(v, list) else ('(', ')')
        items = [f'{pad}    {_py(x, indent + 4)},' for x in v]
        return o + '\n' + '\n'.join(items) + f'\n{pad}{c}'
    if isinstance(v, str):
        return "'" + v.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n') + "'"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def _employees(nar):
    n, asof = nar.get('employee_count'), (nar.get('employee_asof') or '').strip()
    return [(asof or '사업보고서 기준', int(n))] if n else []


def _by_line(nar):
    """부문별 매출 도넛용 (부문명, 금액, 비중). 사업보고서는 비중만 밝히는 일이 흔해
    금액은 None으로 둔다 — deck_pages가 전사 매출×비중으로 환산한다."""
    return [(name, None, pct) for name, _desc, pct in (nar.get('segments') or []) if pct]


def _detail(nar):
    return [(name, desc or '', None, 0) for name, desc, _pct in (nar.get('segments') or [])]


# 모듈명 규칙은 sources_kr 이 유일한 출처다(build·check 도 같은 함수를 쓴다).
module_name = K.module_name


def render_file(d: dict, nar: dict = None) -> str:
    c = dict(d['COMPANY'])
    nar = nar or {}
    res = d['RESULTS'] or {'period': '', 'kpis': [], 'facts': [], 'url': ''}
    ph = PLACEHOLDER
    if nar.get('sector'):
        c['sector'] = nar['sector']

    def won(v):   # 1조 이상은 조 단위 — '1,950,000억원' 대신 '195.0조원'(2026-10-23 삼성전자 2p)
        return f'{v / 1e12:,.1f}조원' if abs(v) >= 1e12 else f'{v / 1e8:,.0f}억원'
    kpis = [(name, won(val), sub, arrow) for name, val, sub, arrow in res['kpis']]
    facts = [(name, why, won(val)) for name, why, val in res['facts']]
    ceo = d['CEO_NAME']
    people = []
    seen = set()
    for r in d['INSIDERS']:
        nm, pos = (r.get('name') or '').strip(), (r.get('position') or '').strip()
        if nm and nm != ceo and pos not in ('', '-') and nm not in seen:
            seen.add(nm)
            people.append((nm, pos, ''))
    body = f'''# -*- coding: utf-8 -*-
"""{c['name']} ({c['ticker']}) — autogen_kr.py 자동 초안.

⚠️ 아래 항목은 **아직 사람이 채워야 한다**(자동으로는 지어낼 수 없는 것들):
     COMPANY['sector'] · BUSINESS · HISTORY['timeline'] · SEGMENTS · TAM ·
     LEADERSHIP['ceo']['bio'] · PEERS · CANSLIM_N
   check.py 가 '{ph}'와 빈 값을 발행 차단 사유로 잡는다.

숫자는 전부 DART·Yahoo 원본에서 결정론으로 왔다(LLM 0콜):
   재무 = DART 재무제표 API · 최근실적 = {res.get('rcept_dt', '')} 영업(잠정)실적 공정공시
   가격·컨센서스 = Yahoo Finance
"""
AS_OF = {_py(d['AS_OF'])}          # 반영한 최신 공시일(표지 라벨)
BUILT_AT = {_py(d['BUILT_AT'])}       # 초안 생성일(신선도 게이트·차트 기준연도)

SRC = {_py(d['SRC'])}

COMPANY = {_py(c)}

LOCKED = []

# 표지 '- ' 짧은 줄 2~3개 — 이 회사에만 해당하는 구체 사실(2026-10-23 개정, 뻔한 줄은 deck_pages 가 거른다).
BUSINESS = {_py(nar.get('business_model') or [])}

HISTORY = {{
    'founded': {_py(d['HISTORY_founded'])},
    'listed': {_py(nar.get('listed_year'))},
    'listing_type': {_py(nar.get('listing_type') or '')},
    'listing_date': '',
    'founders': '',
    'timeline': {_py(nar.get('timeline') or [])},
    'employees': {_py(_employees(nar))},
    'employee_src': {_py((nar.get('employee_asof') or '') and 'DART 사업보고서')},
    'chart_annotations': [],
    'note': {_py(nar.get('history_note') or '')},
}}

PRICE_MOVES = []

LEADERSHIP = {{
    'ceo': {{'name': {_py(ceo)}, 'role': '대표이사',
             'since': {_py(nar.get('ceo_since'))}, 'bio': {_py(nar.get('ceo_bio') or '')}}},
    # DART 임원·주요주주 소유상황보고에 이름이 오른 사람들 — 직위는 원문 그대로.
    'people': {_py(people[:6])},
    'note': {_py('대표이사 공시 원문: ' + d['CEO_RAW'] if d['CEO_RAW'] else '')},
    'rsu_note': '',
}}

SHARES = {{'note': '', 'dilution': [], 'src': SRC['PR']}}

SEGMENTS = {{
    'by_line': {_py(_by_line(nar))},
    'detail': {_py(_detail(nar))},
    'by_geo': [],
    'competitors': {_py(nar.get('competitors') or [])},
    'note': '', 'src': SRC['DECK'],
}}

RESULTS = {{
    'period': {_py(res['period'])},
    'kpis': {_py(kpis)},
    'facts': {_py(facts)},
    # 한국은 어닝콜 전문이 무료 공개되지 않는다 — 경영진 발언 인용은 비워 둔다.
    'quotes': [],
    'src': SRC['PR'],
    'url': {_py(res.get('url', ''))},
}}

# C·A는 canslim.py가 render 시점에 재무로 직접 계산 — N만 여기서 채운다.
CANSLIM_N = {{}}
CANSLIM_N_DETAIL = {{}}
CANSLIM_NOTE = ''

INCOME_NOTE = {_py(nar.get('income_note') or '')}
BALANCE_NOTE = {_py(nar.get('balance_note') or '')}
CASHFLOW = {{'note': {_py(nar.get('cashflow_note') or '')}, 'src': 'DART 재무제표 API'}}

# estimates는 **항상 빈 배열**로 둔다. 시장조사기관 수치는 사업보고서에 금액으로
# 실리는 일이 드물고, 없는 걸 채우면 지어낸 값이 된다 — note에 원문 서술만 남긴다.
TAM = {{'label': {_py(nar.get('tam_label') or '')}, 'estimates': [],
       'note': {_py(nar.get('tam_note') or '')},
       'src': {_py(('DART 사업보고서' if nar.get('tam_note') else ''))}}}

CHECKPOINTS = {_py(d['CHECKPOINTS'])}
CHECKPOINT_NOTE = ''
# 위 체크포인트는 실적 공시가 아니라 **애널리스트 컨센서스**에서 유도했다.
CHECKPOINT_SRC = 'Yahoo Finance 애널리스트 컨센서스'

PEERS = {{'names': {{}}, 'ciks': {{}}}}

SITE = {_py(d['SITE'])}

SUMMARY = {_py(d['SUMMARY'])}
'''
    return body


# ── 서사 생성 (LLM 1콜) ────────────────────────────────────────────────
# 미국판 STATIC_PROMPT는 10-K 전제라 절 이름("Item 1. Business", "Competition")이
# 박혀 있다. 한국 사업보고서는 목차가 달라 그 지시가 통째로 헛돈다 — 여기서 다시 쓴다.
# 규율은 그대로: **원문에 없으면 생성 금지.** 특히 TAM은 사업보고서가 스스로 밝힌
# 시장규모만 쓰고, 없으면 빈 배열로 둔다(시장조사 수치를 지어내면 이 제품의 존재
# 이유가 무너진다).
NARRATE_PROMPT = """당신은 15년 경력의 셀사이드 애널리스트입니다. 아래는 {company}({ticker})의
**DART 사업보고서 원문**입니다. 여기에 **실제로 적힌 내용만으로** 아래 JSON을 채우세요.

문체 규칙:
 · 개조식 — "~함/~됨/~중"으로 끝냄. "~합니다/~됩니다" 금지.
 · 클리셰 금지("혁신적인", "선도하는", "글로벌 리더", "무한한 가능성").
 · 금액은 "1,234억원"·"1.2조원" 표기. 원문 단위(백만원 등)를 그대로 베끼지 말 것.
 · 원문에 근거가 없으면 그 필드는 빈 문자열/빈 배열로 두세요. **추측 금지.**
   비어 있는 건 검수자가 채웁니다. 지어낸 값이 훨씬 나쁩니다.

business_model 작성 규칙(2026-10-23 개정): 표지에 '- ' 로 붙는 짧은 줄 2~3개.
- 각 줄은 이 회사에만 해당하는 구체 사실이어야 한다: 대표 제품명·주요 고객사명·점유율·세계 순위·매출 비중.
- 어느 회사에나 붙는 뻔한 말은 쓰지 말 것: "고객 주문에 따라 제조·납품해 매출을 올림",
  "제품 판매로 수익 창출", "다양한 고객에게 공급" 같은 줄은 차라리 빼라(줄 수가 줄어도 된다).
- 업계 용어 그대로 X, 홍보 문구 X. 원문에서 확인 안 되면 빈 배열.

순수 JSON만 출력:

{{
  "sector": "이 회사를 한 줄로 규정하는 업종(12자 내외). 예: '2차전지 양극재'",
  "business_model": ["이 회사가 뭘 하는지 짧은 한 줄(25자 이내) — 구체 제품·고객·점유율·숫자 중 하나는 꼭 들어갈 것",
                     "두 번째 핵심 사실(25자 이내, 없으면 생략)", "세 번째 핵심 사실(25자 이내, 없으면 생략)"],
  "listed_year": 상장연도(정수) 또는 null,
  "listing_type": "IPO/스팩합병/재상장/분할상장 중 원문 근거 있는 값, 없으면 빈 문자열",
  "employee_count": 최신 임직원수(정수) 또는 null,
  "employee_asof": "임직원수 기준일(원문 표기 그대로)",
  "ceo_since": CEO 취임연도(정수) 또는 null,
  "ceo_bio": "CEO 2~3문장 — 취임연도·이전 이력. 원문에 없으면 빈 문자열",
  "timeline": [["연도(문자열)", "그 해 있었던 핵심 사건 — 60자 이내", true_or_false_강조여부]],
  "segments": [["부문명", "이 부문이 무엇을 하는지 30자 이내", 매출비중_퍼센트_또는_null]],
  "_segments_rule": "보고 부문이 1개(단일 부문)면 부문 대신 '주요 제품 등의 현황'(주요 제품 매출 비중) 표의 제품·품목별 비중을 segments 로 채울 것. 경쟁사는 '경쟁 현황'·'시장점유율' 절에 실명이 있으면 그대로(해외 기업 포함)",
  "competitors": ["사업보고서가 실명으로 지목한 경쟁사만. 없으면 빈 배열"],
  "tam_label": "사업보고서가 언급한 시장의 이름(예: '글로벌 양극재 시장'). 없으면 빈 문자열",
  "tam_note": "사업보고서가 밝힌 시장규모·성장률 서술 1~2문장. 없으면 빈 문자열",
  "history_note": "지금 이 회사가 어떤 국면에 있는지 3~4문장(전문투자자 톤, 원문 숫자 인용)",
  "income_note": "손익 추세 해석 2문장 — 아래 '최근 재무'의 숫자만 인용",
  "balance_note": "재무구조 해석 2문장 — 아래 '최근 재무'의 숫자만 인용",
  "cashflow_note": "현금흐름 해석 2문장 — 아래 '최근 재무'의 숫자만 인용"
}}

[최근 재무 — 해석 노트는 이 숫자만 인용할 것]
{fin}

[DART 사업보고서 원문]
{doc}
"""


def _fin_brief(d):
    """해석 노트가 인용할 숫자를 프롬프트에 명시적으로 넣는다. 이렇게 안 하면 LLM이
    본문 어딘가의 다른 숫자를 끌어와 카드의 표와 어긋나는 서술을 쓴다."""
    ann, out = d['ANN'], []
    for key, label in (('revenue', '매출'), ('opinc', '영업이익'), ('netinc', '순이익'),
                       ('equity', '자본총계'), ('cash', '현금')):
        ser = ann.get(key) or {}
        if ser:
            yrs = sorted(ser)[-4:]
            out.append(f'{label}: ' + ' · '.join(f'FY{y} {ser[y] / 1e8:,.0f}억원' for y in yrs))
    q = d['QTR'].get('cfo') or {}
    if q:
        ends = sorted(q)[-4:]
        out.append('분기 영업현금흐름: ' + ' · '.join(f'{e[:7]} {q[e] / 1e8:,.0f}억원' for e in ends))
    return '\n'.join(out)


def narrate(d, max_chars=60000):
    """사업보고서 원문 → 서사 필드. **Gemini 1콜.** 실패해도 초안은 그대로 쓸 수 있다."""
    import analyzer
    doc = None
    try:
        import dart_client as _D
        doc = _D.business_text(d['raw']['corp'], max_chars=max_chars)
    except Exception as e:
        print(f'[사업보고서 원문 조회 실패] {e}')
    if not doc:
        print('사업보고서 원문을 못 받아 서사 생성을 건너뜀 — 초안은 그대로 유효')
        return {}
    prompt = NARRATE_PROMPT.format(
        company=d['COMPANY']['name'], ticker=d['COMPANY']['ticker'],
        fin=_fin_brief(d), doc=doc[:max_chars])
    try:
        client = analyzer._client()
        out = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[서사 생성 실패] {e} — 초안은 그대로 유효(서사 칸만 빔)')
        return {}
    if out.get('_parse_error'):
        print('[서사 생성] JSON 파싱 실패 — 초안은 그대로 유효')
        return {}
    # 프롬프트만 믿지 않는다. "없으면 비워라"를 어기고 0짜리·빈 행을 끼워 넣는 걸
    # 미국판에서 실제로 겪었다(TAM estimates) — 파이썬에서 한 번 더 거른다.
    out['timeline'] = [tuple(t) for t in (out.get('timeline') or [])
                       if isinstance(t, (list, tuple)) and len(t) == 3 and str(t[0]).strip()]
    out['segments'] = [tuple(s) for s in (out.get('segments') or [])
                       if isinstance(s, (list, tuple)) and len(s) == 3 and str(s[0]).strip()]
    out['competitors'] = [c for c in (out.get('competitors') or []) if str(c).strip()]
    out.pop('_segments_rule', None)
    # 비중 검산(2026-11-12 R&D 4): 퍼센트가 0~100 밖이거나 합이 60% 미만·130% 초과면 숫자를 버리고 이름만 남긴다.
    #   (부문 간 내부거래로 합이 100을 조금 넘는 건 정상 — 삼성전자 108.9%) 틀린 비중보다 빈 비중이 낫다.
    ps = [s[2] for s in out['segments'] if isinstance(s[2], (int, float))]
    if ps and (any(p < 0 or p > 100 for p in ps) or not 60 <= sum(ps) <= 130):
        print(f'  ⚠️ 부문 비중 검산 실패(합 {sum(ps):.1f}%) — 비중 비움')
        out['segments'] = [(a, b, None) for a, b, _ in out['segments']]
    # 한국 사업보고서는 시장 규모를 '50.5억 달러'로 적는다 — 그대로 옮기면 check.py 금액 표기 규칙
    # ($X.XB)에 막힌다(2026-10-23 피에스케이홀딩스 TAM.note). 미국판과 같은 기계적 변환을 건다.
    from autogen import _fix_money_units
    return _fix_money_units(out)


def write(symbol: str, out_dir=None, do_narrate=False):
    d = build_deterministic(symbol)
    nar = narrate(d) if do_narrate else {}
    path = Path(out_dir or OUT_DIR) / f'{module_name(symbol)}.py'
    io.open(path, 'w', encoding='utf-8', newline='\n').write(render_file(d, nar))
    return path, d, nar


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    sym = args[0] if args else '247540.KQ'
    do_nar = '--narrate' in sys.argv
    p, d, nar = write(sym, do_narrate=do_nar)
    print(f'생성: {p}')
    print(f"  회사={d['COMPANY']['name']} · {d['COMPANY']['exchange']} · CEO={d['CEO_NAME']}")
    print(f"  AS_OF={d['AS_OF']}  BUILT_AT={d['BUILT_AT']}")
    if nar:
        got = [k for k in ('sector', 'business_model', 'timeline', 'segments',
                           'competitors', 'ceo_bio', 'tam_note') if nar.get(k)]
        print(f'  서사 생성(Gemini 1콜) — 채워진 항목: {", ".join(got) or "없음"}')
    else:
        print('  ⚠️ 서사 미생성 — sector·BUSINESS·timeline·SEGMENTS·TAM은 비어 있음')
    print('  → 발행 전 `python check.py ' + sym + '` 로 남은 차단 사유 확인할 것')
