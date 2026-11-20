"""한국 종목 찾기 — 6자리 종목코드 또는 종목명(한글) → '005930.KS' 같은 야후 심볼.

2026-10-20: 리포트 엔진(autogen_kr·DART)은 한국 종목을 지원하는데, 봇 입구(TICKER_RE)가
'영문자로 시작'만 받아 /report 005930 이 형식 오류로 거절됐다. 코드·이름 둘 다 받는다.

  · 이름 목록: DART corpCode.xml 의 (stock_code, corp_name) — 상장사만. 한 번 받아
    decks/_cache/kr_names.json 에 둔다(30일). 러너는 매 실행 새 컨테이너라 한국 종목
    요청이 올 때만 받는다(수 MB, 수 초).
  · 시장(.KS/.KQ): DART 회사개황 corp_cls (Y=코스피, K=코스닥). 코넥스·기타는 지원 안 함.
"""
import io
import json
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
# ⚠️ 레포 루트에 두고 run.yml 이 커밋한다. 예전엔 decks/_cache(깃 무시)에 둬서 러너가 **매 명령마다**
#    DART corpCode.xml(수 MB, 한국 서버)을 새로 받았고, 재시도까지 겹쳐 /watch 삼성전자 하나에
#    3분 19초가 걸렸다(2026-10-20 실측, 같은 시각 다른 명령은 2초).
CACHE = HERE / 'kr_names.json'
MARKET_CACHE = HERE / 'kr_market.json'      # {코드: 'KS'|'KQ'|'X:사유'} — 시장은 바뀔 일이 드물다
TTL_D = 30
CODE_RE = re.compile(r'^\d{6}$')
KR_SYM_RE = re.compile(r'^\d{6}\.(KS|KQ)$', re.I)


def is_kr_query(s: str) -> bool:
    """6자리 숫자·'005930.KS'·한글이 들어간 입력이면 한국 종목 질의로 본다."""
    s = (s or '').strip()
    return bool(CODE_RE.match(s) or KR_SYM_RE.match(s) or re.search(r'[가-힣]', s))


def _norm(s: str) -> str:
    s = re.sub(r'\(주\)|주식회사|㈜', '', s or '')
    return re.sub(r'[\s·\-_.]', '', s).upper()


def names(refresh=False) -> dict:
    """{종목코드: 회사명}. 실패하면 {}."""
    if not refresh and CACHE.exists() and time.time() - CACHE.stat().st_mtime < TTL_D * 86400:
        try:
            return json.loads(CACHE.read_text(encoding='utf-8'))
        except Exception:
            pass
    try:
        import sys
        sys.path.insert(0, str(HERE / 'decks'))
        import dart_client as D
        r = D._get(f'{D.BASE}/corpCode.xml', {'crtfc_key': D._key()})
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        root = ET.fromstring(zf.read(zf.namelist()[0]).decode('utf-8'))
        m = {}
        for e in root.iter('list'):
            sc = (e.findtext('stock_code') or '').strip()
            nm = (e.findtext('corp_name') or '').strip()
            if sc and CODE_RE.match(sc) and nm:
                m[sc] = nm
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
        return m
    except Exception as e:
        print(f'[KR 종목명 목록 실패] {e}')
        return {}


def search(query: str, limit: int = 6) -> list:
    """[(코드, 이름)] — 코드 정확 일치 > 이름 정확 일치 > 이름 앞부분 일치 > 이름 포함."""
    q = (query or '').strip()
    m = names()
    if KR_SYM_RE.match(q):
        q = q[:6]
    if CODE_RE.match(q):
        return [(q, m.get(q, q))]
    nq = _norm(q)
    if not nq:
        return []
    exact, prefix, contains = [], [], []
    for code, nm in m.items():
        n = _norm(nm)
        if n == nq:
            exact.append((code, nm))
        elif n.startswith(nq):
            prefix.append((code, nm))
        elif nq in n:
            contains.append((code, nm))
    if exact:
        return exact[:limit]
    return sorted(prefix, key=lambda x: len(x[1]))[:limit] + \
        sorted(contains, key=lambda x: len(x[1]))[:max(0, limit - len(prefix))]


def _market_cache() -> dict:
    try:
        return json.loads(MARKET_CACHE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def to_symbol(code: str):
    """'005930' → ('005930.KS', '코스피') · 코스닥은 .KQ. 코넥스·비상장·조회 실패면 (None, 사유).
    한 번 판별한 시장은 kr_market.json 에 남겨 다음부터 DART 를 안 부른다."""
    mc = _market_cache()
    if mc.get(code) in ('KS', 'KQ'):
        return f"{code}.{mc[code]}", '코스피' if mc[code] == 'KS' else '코스닥'
    sym, why = _to_symbol_live(code)
    if sym:
        mc[code] = sym[-2:]
        try:
            MARKET_CACHE.write_text(json.dumps(mc, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        except Exception:
            pass
    return sym, why


def _to_symbol_live(code: str):
    try:
        import sys
        sys.path.insert(0, str(HERE / 'decks'))
        import sources_kr as K
        cc = K.to_corp_code(code)
        if not cc:
            return None, 'DART 에 상장사로 없음'
        cls = (K.company_info(cc).get('corp_cls') or '').upper()
    except Exception as e:
        return None, f'시장 조회 실패: {e}'
    if cls == 'Y':
        return f'{code}.KS', '코스피'
    if cls == 'K':
        return f'{code}.KQ', '코스닥'
    return None, '코넥스·기타 시장은 아직 지원하지 않음'
