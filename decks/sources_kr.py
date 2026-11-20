# -*- coding: utf-8 -*-
"""한국주식 데이터 소스 — sources.py 와 **같은 함수 이름·같은 반환 형태**.

deck_pages/live 는 시장을 몰라야 한다. 그래서 이 모듈은 sources.py 의 얼굴을 그대로
쓰고, 안에서만 갈라진다:

  · 가격·시총·컨센서스·기관지분 → **Yahoo 그대로 재사용**(아래 재수출 목록).
    실측으로 확인했다 — 005930.KS 는 주가·시총·발행주식수는 물론 애널리스트 35명
    컨센서스와 목표주가까지 준다. 한국이라고 따로 만들 필요가 없었다.
  · 재무제표 → **DART**(SEC XBRL 대체). 여기가 이 파일의 실제 내용이다.

`cik` 자리에는 DART `corp_code`(8자리 문자열)를 넣는다. 이름이 안 맞지만 호출부
시그니처를 US/KR 공통으로 유지하는 편이, 시장마다 다른 인자를 들고 다니는 것보다
깨질 구석이 적다.

⚠️ 한계 (결과를 읽을 때 감안할 것)
  · rnd(연구개발비)·dep(감가상각)·contract_liab 는 DART 주요계정에 표준 항목이
    없다 — 빈 값으로 둔다. 렌더러는 None 을 '—' 로 처리하므로 유령 0 막대는
    생기지 않는다(SNDK 스핀오프 사례에서 이미 검증된 경로).
  · 분기말 날짜는 **결산월(acc_mt)로 유도**한다. 12월 결산을 상수로 박으면 3월
    결산 회사에서 분기가 통째로 한 분기씩 밀린다.
  · DART 는 4분기를 따로 신고하지 않는다(사업보고서=연간). dart_client.statements()
    가 FY−(1~3Q) 로 역산해 주므로 quarterly_filled() 의 US 쪽 역산이 필요 없다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources as _S  # noqa: E402
import dart_client as _D  # noqa: E402

# dart_client 는 stock_screener 레포에서 **바이트 동일**로 가져온 사본이라(.dart_client
# .upstream.sha256 로 드리프트를 잡는다) 그쪽 기준의 상대경로 data/ 를 그대로 들고 온다.
# 그 디렉터리는 여기 없으므로 corp_map 캐시 쓰기가 터진다 — 파일을 고치는 대신
# 모듈 전역만 이 레포의 캐시 폴더로 돌려놓는다(사본을 원본과 다르게 만들지 않는다).
_D.DATA = _S.CACHE
# corp_map(종목코드→corp_code)만은 **캐시가 아니라 레포에 실은 정적 데이터**로 둔다.
# _cache/ 는 gitignore라 러너에선 항상 비어 있고, 그러면 dart_client가 corpCode.zip
# (전 종목 XML) 전체를 받으려 든다 — 이 환경에서 5분이 넘어도 안 끝나는 걸 실측했다.
# 한 종목 카드를 만들려다 거기서 멈추면 러너 시간만 태우고 아무것도 못 낸다.
# 86KB짜리 파일 하나로 그 위험이 사라진다. 상장/폐지 반영은 분기 단위로 충분:
#   python -c "import dart_client as D; D._CORP_CACHE=__import__('pathlib').Path('decks/dart_corpmap.json'); D.corp_map(refresh=True)"
_CORP_MAP_FILE = Path(__file__).resolve().parent / 'dart_corpmap.json'
_D._CORP_CACHE = _CORP_MAP_FILE if _CORP_MAP_FILE.exists() else (_S.CACHE / 'dart_corpmap.json')

# ── Yahoo 계열: 한국 티커(.KS/.KQ)로 그대로 동작하므로 재수출만 한다 ───────
# 여기 있는 이름은 "시장 공통"이라는 뜻이고, 아래에 재정의된 것만 "한국 전용"이다.
consensus = _S.consensus
# ownership 은 아래에서 한국 전용으로 재정의(DART 최대주주 + 수급)
monthly_matrix = _S.monthly_matrix
drawdown = _S.drawdown
weekly_price = _S.weekly_price
technical_snapshot = _S.technical_snapshot
daily_ohlcv = _S.daily_ohlcv
monthly_ohlcv = _S.monthly_ohlcv
leader_photo = _S.leader_photo
yf_chart = _S.yf_chart
yf_summary = _S.yf_summary

# DART 계정명 → sources.TAGS 키. 왼쪽이 dart_client.statements() 의 행 키다.
_KEYMAP = {
    'revenue': 'revenue', 'cogs': 'cogs', 'gross': 'gross', 'sga': 'sga',
    'op_income': 'opinc', 'net_income': 'netinc',
    'op_cf': 'cfo', 'capex': 'capex', 'cash': 'cash',
    'assets': 'assets', 'liabilities': 'liab', 'equity': 'equity',
    'eps': 'eps', 'ar': 'ar', 'inventory': 'inventory', 'ppe': 'ppe',
    'inv_cf': 'inv_cf', 'fin_cf': 'fin_cf',
}

# DART 는 보고서 단위 API라 한 번 훑는 비용이 크다 — 넉넉히 한 번 받아 캐시한다.
# quarter 16 = 4년치(bundle 이 최대 14를 요청), annual 8 = 8년치.
_MAX_ROWS = {'quarter': 16, 'annual': 8}

_corp_cache = {}
_key_warned = [False]


def _has_key() -> bool:
    """DART 키 유무를 **호출 전에** 확인하고, 없으면 딱 한 번 크게 알린다.

    dart_client._acnt_all 은 연결/개별(CFS·OFS)을 차례로 시도하며 예외를 `continue`로
    삼킨다. 그래서 키가 없으면 예외가 위로 안 올라오고 **빈 결과만 조용히** 나온다 —
    카드의 재무 3표가 통째로 비는데 화면에도 로그에도 이유가 없다(실측으로 확인).
    러너에 DART_KEY 시크릿을 안 넣은 경우가 정확히 이 모습이라, 원인을 못 찾는다.
    """
    try:
        _D._key()
        return True
    except Exception:
        if not _key_warned[0]:
            _key_warned[0] = True
            print('[DART] 키 없음 — 한국 종목 재무를 가져올 수 없습니다. '
                  '로컬은 .env 의 DART_KEY, GitHub Actions 는 저장소 시크릿 DART_KEY 확인. '
                  '(가격·컨센서스는 Yahoo라 영향 없음)')
        return False


def module_name(symbol: str) -> str:
    """'247540.KQ' → 'kr247540_data'. **이 규칙의 유일한 출처.**

    한국 티커는 숫자로 시작하고 점이 있어 그대로 모듈명을 만들면 '005930.ks_data' 가
    되고, 파이썬은 이걸 '005930' 패키지의 하위 모듈로 보고 죽는다(실측: 삼성전자
    카드 렌더가 여기서 실패했다).
    autogen_kr(생성)·build(렌더)·check(발행점검) 세 곳이 같은 이름을 만들어야 하는데
    복사해두면 한쪽만 바뀌었을 때 "파일은 있는데 모듈을 못 찾는" 형태로 터진다 —
    금액 포맷터를 두 벌 뒀다가 도넛만 달러로 찍힌 것과 같은 종류의 사고다."""
    return 'kr' + str(symbol).upper().replace('.KS', '').replace('.KQ', '').lower() + '_data'


def to_corp_code(symbol: str):
    """'005930.KS' / '005930' → DART corp_code. 못 찾으면 None."""
    code = str(symbol or '').upper().replace('.KS', '').replace('.KQ', '').strip()
    if not code:
        return None
    if not _corp_cache:
        try:
            _corp_cache.update(_D.corp_map())
        except Exception as e:
            print(f'[DART corp_map 실패] {e}')
            return None
    return _corp_cache.get(code)


_MARKET = {'Y': ('KOSPI', '유가증권시장'), 'K': ('KOSDAQ', '코스닥'),
           'N': ('KONEX', '코넥스'), 'E': ('기타', '기타법인')}


def company_info(corp_code, ttl_h=24 * 30):
    """DART 회사개황. 대표자명·설립일·시장구분·홈페이지·결산월이 한 번에 온다.

    미국판에서 여러 소스를 뒤져 겨우 채우던 것들(CEO 이름은 위임장, 상장시장은
    제출서류, 홈페이지는 죽은 Clearbit)이 한국은 이 한 콜에 다 들어있다."""
    def fetch():
        import requests
        j = requests.get('https://opendart.fss.or.kr/api/company.json',
                         params={'crtfc_key': _D._key(), 'corp_code': corp_code},
                         timeout=20).json()
        return j if j.get('status') == '000' else {}

    try:
        return _S._cached(f'dart_co_{corp_code}', ttl_h, fetch) or {}
    except Exception as e:
        print(f'[DART 회사개황 실패] {corp_code}: {e}')
        return {}


def _acc_month(corp_code) -> int:
    """결산월. 12월 결산을 상수로 박으면 3월 결산 회사(한국에도 존재한다)에서
    분기말 날짜가 통째로 밀린다. 조회 실패 시에만 12로 폴백한다."""
    try:
        return int(company_info(corp_code).get('acc_mt') or 12)
    except (TypeError, ValueError):
        return 12


def _q_end(year: int, q: int, acc_mt: int = 12) -> str:
    """회계 q분기의 **달력상** 종료일.

    회계연도 Y 는 Y년 acc_mt 월 말에 끝난다. q분기말은 거기서 3*(4-q) 개월 앞이고,
    0 이하로 내려가면 전년으로 넘어간다. 3월 결산이면 FY2026 은
    2025-06-30 / 2025-09-30 / 2025-12-31 / 2026-03-31 이 된다 — 1~3분기가 **전년**
    이라는 점이 핵심이다(여기를 틀리면 분기가 통째로 한 해 밀린다)."""
    import calendar
    m, y = acc_mt - 3 * (4 - q), year
    while m <= 0:
        m += 12
        y -= 1
    return f'{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}'


def _rows(corp_code, freq, n, ttl_h=24):
    """DART 재무표 — **반드시 캐시한다.**

    US 쪽은 companyfacts 한 방(_taxonomy_facts)이 캐시돼 있어 annual/quarterly/
    quarterly_filled 를 몇 번을 불러도 네트워크는 1회다. DART 는 보고서 단위 API라
    한 번 훑는 데 (연도 × 보고서 4종 × 연결/개별 2종) 콜이 나가는데, live.bundle()
    은 quarterly 계열을 4번 부른다 — 캐시 없이 돌렸더니 실제로 5분 넘게 안 끝났다.
    항상 **넉넉한 고정 개수**로 받아 캐시하고 호출부가 잘라 쓴다. n 을 캐시 키에
    넣거나 "짧으면 다시 받기"를 하면, 상장한 지 얼마 안 돼 이력이 실제로 짧은
    회사에서 캐시가 영영 안 차 매번 재조회가 난다."""
    if not _has_key():
        return []
    want = _MAX_ROWS.get(freq, 16)
    key = f'dart_stmt_{corp_code}_{freq}'

    def fetch():
        return {'rows': _D.statements(corp_code, freq, want) or []}

    try:
        rows = (_S._cached(key, ttl_h, fetch) if ttl_h else fetch()).get('rows') or []
    except Exception as e:
        print(f'[DART statements 실패] {corp_code} {freq}: {e}')
        return []
    return rows[:n]


def _transpose(rows, period_fn, keys=None):
    """행 리스트 → {sources 키: {기간: 값}}. sources.annual_series 와 같은 형태."""
    want = set(keys) if keys else None
    out = {}
    for r in rows:
        p = period_fn(r.get('period'))
        if p is None:
            continue
        for dk, sk in _KEYMAP.items():
            if want and sk not in want:
                continue
            v = r.get(dk)
            if dk == 'net_income' and v is None:      # 분기·반기 보고서의 순이익 명칭
                v = r.get('net_income_q')
            if v is not None:
                out.setdefault(sk, {})[p] = v
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def annual_series(cik, keys=None, ttl_h=24):
    """{키: {회계연도(int): 값}} — sources.annual_series 와 동일 형태."""
    rows = _rows(cik, 'annual', 6)

    def per(p):
        try:
            return int(str(p)[:4])
        except Exception:
            return None

    return _transpose(rows, per, keys)


def quarterly_series(cik, keys=None, limit=12, ttl_h=24):
    """{키: {'YYYY-MM-DD'(분기말): 값}} — sources.quarterly_series 와 동일 형태."""
    rows = _rows(cik, 'quarter', limit)
    acc = _acc_month(cik)

    def per(p):
        # dart_client 가 '2026.2Q' 형태로 준다
        try:
            y, q = str(p).split('.')
            return _q_end(int(y), int(q[0]), acc)
        except Exception:
            return None

    return _transpose(rows, per, keys)


def quarterly_filled(cik, key: str, limit=10):
    """US 판은 10-K 가 4분기를 따로 안 실어 Q4 를 역산해 채워야 했다. DART 는
    dart_client.statements() 가 이미 FY−(1~3Q) 로 4분기를 만들어 주므로
    quarterly_series 를 그대로 자르면 된다."""
    q = quarterly_series(cik, [key], limit=max(limit + 4, 14)).get(key, {})
    return {k: q[k] for k in sorted(q)[-limit:]}


def company_site(cik, fallback=None):
    """회사 공식 홈페이지. DART 회사개황의 hm_url(스킴 없이 온다)."""
    hm = (company_info(cik).get('hm_url') or '').strip()
    if not hm:
        return fallback
    return hm if hm.startswith('http') else f'https://{hm}'


def insiders(cik, limit_filings=40, ttl_h=24):
    """임원·주요주주 특정증권등 소유상황보고 — 미국 Form 4 자리."""
    if not _has_key():
        return []          # dart_client.insiders 도 예외를 삼키므로 여기서 먼저 건다
    try:
        return _D.insiders(cik, limit_filings) or []
    except Exception as e:
        print(f'[DART insiders 실패] {e}')
        return []


# ── 영업(잠정)실적 공정공시 — 미국 8-K 실적발표의 대응물 ──────────────────
# 한국은 어닝콜 전문을 무료로 공개하지 않는다. 대신 이 공시가 8-K 보다 오히려 낫다:
#   · 표준 양식이라 LLM 없이 결정론으로 파싱된다
#   · QoQ·YoY 증감율을 회사가 이미 계산해서 낸다
#   · **흑자적자전환 여부를 공시가 직접 명시**한다(주도주·CANSLIM 판정을 추정 없이)
#   · 분기보고서보다 2주 이상 빠르다(에코프로비엠 2Q: 잠정 07-31 vs 분기보고서 8월 중순)
_PROV_NAME = '영업(잠정)실적'
# 표의 각 행: {항목} 당해실적 <7토큰> 누계실적 <7토큰>
# 7토큰 = 당기실적 · 전기실적 · 전기대비% · 흑자적자전환 · 전년동기실적 · 전년동기대비% · 흑자적자전환
_TURN_WORDS = ('적자전환', '흑자전환', '적자지속', '흑자지속', '당기흑자', '당기적자')
_TOK = r'(?:-?[\d,]+(?:\.\d+)?|-|' + '|'.join(_TURN_WORDS) + r')'
_PROV_ROW = None      # 최초 사용 시 컴파일
# 공시 표 머리의 '단위 : X원'. 회사마다 다르므로 반드시 읽어서 원 단위로 환산한다.
_UNIT_SCALE = {'원': 1, '천원': 1e3, '백만원': 1e6, '십억원': 1e9, '억원': 1e8, '조원': 1e12}


def _prov_row_re():
    global _PROV_ROW
    if _PROV_ROW is None:
        import re
        _PROV_ROW = re.compile(
            r'([가-힣A-Za-z()·\s]{2,40})당해실적\s*((?:' + _TOK + r'\s+){6}' + _TOK + r')\s*'
            r'누계실적\s*((?:' + _TOK + r'\s+){6}' + _TOK + r')')
    return _PROV_ROW


# 항목명 앞에 딸려오는 잡음. 정규식이 항목명을 '한글/영문/괄호/공백'으로 잡는 탓에
# ①표 헤더 꼬리('…증감율(%) 흑자적자전환여부')가 첫 항목 앞에 ②앞 행의 마지막 토큰이
# 한글 전환어일 때 그게 다음 항목 앞에 붙는다. 둘 다 실측으로 확인된 오염이다.
_NOISE = ('흑자적자전환여부', '전년동기실적', '전년동기대비', '당기실적', '전기실적',
          '누계실적', '당해실적', '증감율', '연결실적내용', '구분') + _TURN_WORDS


def _clean_item(name: str) -> str:
    """잡음 중 **가장 오른쪽** 것 뒤부터가 진짜 항목명이다. 더 못 자를 때까지 반복."""
    s = ' '.join(str(name).split())
    while True:
        cut = max((s.rfind(w) + len(w) for w in _NOISE if w in s), default=-1)
        if cut < 0:
            break
        s = s[cut:].strip()
    return s.lstrip(') %(').strip()


def _num(tok):
    tok = str(tok).strip()
    if tok in ('-', '', '—'):
        return None
    try:
        return float(tok.replace(',', ''))
    except ValueError:
        return None


def provisional_results(corp_code, ttl_h=12):
    """최신 「연결재무제표기준 영업(잠정)실적(공정공시)」. 없으면 None.

    반환 금액 단위는 **원**(공시는 백만원 단위라 1e6을 곱해 맞춘다) — 다른 재무
    경로와 단위를 통일해야 같은 페이지에서 숫자가 어긋나지 않는다.
    """
    def fetch():
        import io
        import re
        import zipfile
        from datetime import datetime as _d, timedelta as _td
        end = _d.now().strftime('%Y%m%d')
        bgn = (_d.now() - _td(days=200)).strftime('%Y%m%d')
        j = _D._get(f'{_D.BASE}/list.json',
                    {'crtfc_key': _D._key(), 'corp_code': corp_code,
                     'bgn_de': bgn, 'end_de': end, 'page_count': 100}).json()
        lst = j.get('list', []) if j.get('status') == '000' else []
        # [기재정정]이 붙은 정정본이 원본보다 최신이면 그쪽이 맞다 — 접수일 최신순 첫 건.
        cand = [x for x in lst if _PROV_NAME in (x.get('report_nm') or '')]
        if not cand:
            return {}
        tgt = sorted(cand, key=lambda x: x.get('rcept_dt', ''), reverse=True)[0]
        r = _D._get(f'{_D.BASE}/document.xml',
                    {'crtfc_key': _D._key(), 'rcept_no': tgt['rcept_no']})
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        xml = zf.read(max(zf.namelist(), key=lambda n: zf.getinfo(n).file_size)).decode('utf-8', 'replace')
        txt = re.sub(r'<[^>]+>', ' ', xml)
        txt = re.sub(r'&[a-zA-Z#0-9]+;', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt)

        # 단위는 **회사가 고른다.** 삼성전자는 '단위 : 조원', 에코프로비엠은 '백만원'
        # (둘 다 실측). 백만원으로 박아뒀더니 삼성 매출 171.5조가 2억으로 찍혔다 —
        # 증감율은 맞고 금액만 6자리 틀리는, 눈으로 안 걸리면 그대로 발행될 오류였다.
        um = re.search(r'단위\s*:?\s*([가-힣]*원)', txt)
        unit_name = um.group(1) if um else '백만원'
        scale = _UNIT_SCALE.get(unit_name)
        if scale is None:
            print(f'[잠정실적] 모르는 단위 "{unit_name}" — 금액을 버린다(틀린 값보다 빈 값)')

        cols = ('당기', '전기', '전기대비', '전기전환', '전년동기', '전년동기대비', '전년동기전환')
        rows = {}
        for m in _prov_row_re().finditer(txt):
            item = _clean_item(m.group(1))
            if not item:
                continue
            for label, toks in (('당해', m.group(2)), ('누계', m.group(3))):
                vals = toks.split()
                if len(vals) != 7:
                    continue
                d = {}
                for c, v in zip(cols, vals):
                    if c.endswith('전환'):
                        d[c] = v if v in _TURN_WORDS else None
                    elif c.endswith('대비'):
                        d[c] = _num(v)                     # 증감율(%)
                    else:
                        n = _num(v)
                        d[c] = None if (n is None or scale is None) else n * scale
                rows.setdefault(item, {})[label] = d

        per = {}
        pm = re.search(r'당기실적\s*([\d\-]{10})\s*~\s*([\d\-]{10})', txt) or \
            re.search(r'실적기간\s*당기실적\s*([\d\-]{10})\s*~\s*([\d\-]{10})', txt)
        if pm:
            per['당기'] = [pm.group(1), pm.group(2)]
        return {'unit': unit_name,
                'rcept_dt': tgt.get('rcept_dt', ''), 'rcept_no': tgt.get('rcept_no', ''),
                'report_nm': ' '.join((tgt.get('report_nm') or '').split()),
                'url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={tgt.get('rcept_no','')}",
                'periods': per, 'rows': rows}

    try:
        out = _S._cached(f'dart_prov_{corp_code}', ttl_h, fetch) if ttl_h else fetch()
    except Exception as e:
        print(f'[DART 잠정실적 실패] {corp_code}: {e}')
        return None
    return out or None


# ── 주주구성 (2026-11-04) — 13F·위임장 자리를 DART 최대주주 현황 + 외국인·기관 수급으로 ──
# 미국식 6p 가 한국 종목에서 'Class A 기준'·'None개 기관 0.00%'를 찍던 문제(PSK·삼성전자 실측).
# 한국에서 '누가 이 회사를 쥐고 있나'의 1차 자료는 13F 가 아니라 사업보고서의 최대주주 표다.
_REPRT_ORDER = ('11014', '11012', '11013', '11011')   # 3분기·반기·1분기·사업 — 최신 보고서 우선
_REPRT_NAME = {'11011': '사업보고서', '11012': '반기보고서', '11013': '1분기보고서', '11014': '3분기보고서'}


def _f(v):
    try:
        return float(str(v).replace(',', '').strip())
    except Exception:
        return None


def parse_major(rows: list) -> dict:
    """DART hyslrSttus.json 의 list → {'rows':[{name,relate,pct,shares}], 'total_pct'}.

    · 보통주만(우선주는 의결권이 없어 '쥐고 있나'와 다르다).
    · '계'·'합계' 행은 합계로만 쓰고 표에서 뺀다. 없으면 직접 더한다.
    · 지분율은 기말(trmend) 기준."""
    out, total = [], None
    for x in rows or []:
        kind = str(x.get('stock_knd') or '')
        if kind and '보통' not in kind and '의결권 있는' not in kind:
            continue
        nm = str(x.get('nm') or '').strip()
        pct = _f(x.get('trmend_posesn_stock_qota_rt'))
        if nm in ('계', '합계', '소계'):
            total = pct if total is None else total
            continue
        if not nm or pct is None:
            continue
        out.append(dict(name=nm, relate=str(x.get('relate') or '').strip(), pct=pct,
                        shares=_f(x.get('trmend_posesn_stock_co'))))
    out.sort(key=lambda r: -r['pct'])
    if total is None and out:
        total = round(sum(r['pct'] for r in out), 2)
    return {'rows': out, 'total_pct': total}


def major_holders(corp_code, ttl_h=24 * 7):
    """최대주주 및 특수관계인 — 가장 최근에 제출된 정기보고서 하나. 못 받으면 {}."""
    import datetime as _dt
    import requests

    def fetch():
        y = _dt.date.today().year
        for yr in (y, y - 1):
            for rc in _REPRT_ORDER:
                try:
                    j = requests.get('https://opendart.fss.or.kr/api/hyslrSttus.json',
                                     params={'crtfc_key': _D._key(), 'corp_code': corp_code,
                                             'bsns_year': str(yr), 'reprt_code': rc}, timeout=20).json()
                except Exception:
                    continue
                if j.get('status') == '000' and j.get('list'):
                    p = parse_major(j['list'])
                    if p['rows']:
                        p['as_of'] = f'{yr} {_REPRT_NAME[rc]}'
                        return p
        return {}
    try:
        return _S._cached(f'dart_major_{corp_code}', ttl_h, fetch) or {}
    except Exception as e:
        print(f'[DART 최대주주 실패] {corp_code}: {e}')
        return {}


def flow_20d(ticker: str):
    """외국인·기관 최근 20거래일 순매수(네이버) — 봇의 ir.kr_flow 를 그대로 쓴다(한 곳에서만 계산)."""
    try:
        root = str(Path(__file__).resolve().parent.parent)
        if root not in sys.path:
            sys.path.insert(0, root)
        import ir as _ir
        return _ir.kr_flow(ticker, max_days=20)
    except Exception as e:
        print(f'[수급 실패] {ticker}: {e}')
        return None


def ownership(ticker: str):
    """US 와 같은 키(Yahoo 기관지분 — 한국은 대개 비어 있음) + 한국 전용 키 2개.
      major : DART 최대주주 현황 {'rows','total_pct','as_of'}
      flow  : 외국인·기관 20거래일 순매수 {'foreign','inst','foreign_amt','inst_amt',...}"""
    try:
        base = _S.ownership(ticker) or {}
    except Exception as e:
        print(f'[Yahoo 지분 실패] {ticker}: {e}')
        base = {}
    cc = to_corp_code(ticker) if _has_key() else None
    base['major'] = major_holders(cc) if cc else {}
    base['flow'] = flow_20d(ticker)
    return base


def beneficial_owners(cik, ttl_h=48):
    """미국은 DEF 14A(위임장)에서 5%+ 주주를 뽑는다. DART 대응물은 '최대주주 현황'
    이지만 스키마가 달라 아직 배선하지 않았다 — **빈 값으로 정직하게 둔다.**
    주주구성 페이지는 Yahoo ownership(기관지분율)만으로 렌더된다."""
    return {}
