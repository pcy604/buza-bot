# -*- coding: utf-8 -*-
"""경영진 명단을 SEC Form 4에서 결정론으로 뽑는다 — LLM 0콜.

## 왜

12장 리포트의 발행 필수 항목 6개 중 4개가 LLM 산출물이라, 신규 종목 하나에
Gemini를 8콜씩 쓴다. 무료 쿼터가 빠듯해 분당 한도에 걸려 단계마다 59초씩
대기하는 일이 실제로 벌어졌다. 그 4개를 하나씩 결정론으로 옮기는 작업의 첫 칸.

`LEADERSHIP.ceo.name`은 원래 LLM A(10-K 본문)와 LLM D(위임장 발췌)가 채웠는데,
**Form 4(내부자 거래 신고)에 직함이 구조화된 XML로 들어있다.** 파싱만 하면 된다.

    <rptOwnerName>Thakar Sumedh S</rptOwnerName>
    <officerTitle>CEO &amp; PRESIDENT</officerTitle>

실측(QLYS): CEO·CFO·CLO가 최근 6건 안에서 전부 잡혔다. 덤으로
`LEADERSHIP.people`(주요 경영진 표, 지금은 비면 WARN)까지 같은 소스로 채워진다.

## 한계 — 반드시 알고 쓸 것

- **최근 N건만 보면 CEO가 안 나올 수 있다.** IONQ는 최근 6건이 전부 CFO였다.
  그래서 기본 스캔 폭을 넉넉히 잡고, 못 찾으면 못 찾았다고 말한다(지어내지 않는다).
- **Form 4를 안 내는 회사는 빈다.** 외국기업(20-F)은 임원 신고 의무가 달라
  아예 없을 수 있다. 그 경우는 기존 LLM 경로가 폴백이다.
- **이름 표기가 "성 이름 중간이름" 순서**다(SEC 서식). 보기 좋게 뒤집어 주지만
  한국·인도계 이름은 어느 쪽이 성인지 서식만으론 확신할 수 없어, 원문도 같이 남긴다.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / 'officers.json'
UA = 'buza-alarm/1.0 (contact: pcy604604@gmail.com)'   # SEC는 UA 없으면 차단한다
CEO_RE = re.compile(r'chief\s+executive|(?<![a-z])ceo(?![a-z])', re.I)


def _get(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            return urllib.request.urlopen(req, timeout=25).read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


# 성에 붙는 소문자 접두사. 'de Masi Niccolo'를 'Masi Niccolo de'로 뒤집던 버그가
# 실제로 났다(IONQ CEO). 이런 토큰은 뒤따르는 토큰까지 묶어서 성으로 본다.
# 법인·펀드로 보이는 이름은 사람 이름 규칙을 적용하지 않는다.
_ENTITY_RE = re.compile(
    r'(ltd|llc|l\.p|lp|inc|corp|company|holdings?|partners?|'
    r'capital|fund|trust|management|ventures?|group|associates)\.?', re.I)

_PARTICLES = {'de', 'del', 'della', 'di', 'da', 'dos', 'van', 'von', 'der', 'ten',
              'ter', 'la', 'le', 'du', 'bin', 'ibn', 'al', 'mac', 'mc', 'st'}


def _pretty(raw: str) -> str:
    """SEC 서식 'Thakar Sumedh S' → 'Sumedh S Thakar'.

    첫 토큰을 성으로 본다(서식이 그렇게 정의돼 있다). 단 'de'·'van' 같은 접두사면
    다음 토큰까지 성에 포함한다. 전부 대문자면 보기 좋게 낮춘다.
    한국·인도계 이름은 서식만으로 성을 확신할 수 없으므로 호출부는 raw도 받는다."""
    parts = [p for p in re.split(r'\s+', raw.strip()) if p]
    if len(parts) < 2:
        return raw.strip()
    # Form 4 신고자는 사람만이 아니다 — 펀드·지주회사도 5% 이상 보유자로 신고한다.
    # 법인명을 '성 이름' 규칙으로 뒤집으면 'Thermopylae Holdings Ltd.'가
    # 'Holdings Ltd. Thermopylae'가 된다(실제 발생, ABCL 최대주주).
    if _ENTITY_RE.search(raw):
        return raw.strip()
    n = 2 if (parts[0].lower().strip('.') in _PARTICLES and len(parts) > 2) else 1
    surname, given = ' '.join(parts[:n]), parts[n:]
    out = ' '.join(given + [surname])
    if out.isupper():
        out = ' '.join(w.capitalize() for w in out.split())
    return out


# 일부 발행사(팔란티어 등)는 officerTitle에 "See Remarks"만 넣고 실제 직함을
# remarks에 "Officer title: Chief Technology Officer ..." 형태로 적는다.
# 이걸 안 보면 PLTR처럼 임원이 전부 "See Remarks"로 잡혀 CEO를 못 찾는다.
_REMARK_TITLE = re.compile(r'officer\s+title\s*:\s*(.+?)(?:\.\s|\.$|$)', re.I | re.S)


def _resolve_title(title: str, remarks: str) -> str:
    t = (title or '').strip()
    if t and not re.fullmatch(r'see\s+remarks\.?', t, re.I):
        return t
    m = _REMARK_TITLE.search(remarks or '')
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else t


# Form 4의 직함은 'CHIEF FINANCIAL OFFICER'처럼 길고 전부 대문자로 온다. 카드의
# 기존 표기는 'CFO'·'창업자 · CEO'처럼 짧아서, 그대로 쓰면 한 표 안에서 톤이 어긋난다.
# 아는 것만 축약하고 모르는 건 손대지 않는다(임의로 줄이면 뜻이 바뀐다).
_ABBR = [
    (r'chief\s+executive\s+officer', 'CEO'),
    (r'chief\s+financial\s+officer', 'CFO'),
    (r'chief\s+operating\s+officer', 'COO'),
    (r'chief\s+technology\s+officer', 'CTO'),
    (r'chief\s+legal\s+officer', 'CLO'),
    (r'chief\s+accounting\s+officer', 'CAO'),
    (r'chief\s+revenue\s+officer', 'CRO'),
    (r'chief\s+business\s+officer', 'CBO'),
    (r'chief\s+marketing\s+officer', 'CMO'),
    (r'chief\s+information\s+officer', 'CIO'),
    (r'chief\s+product\s+officer', 'CPO'),
    (r'chief\s+scientist', '수석과학자'),
    (r'executive\s+vice\s+president', 'EVP'),
    (r'senior\s+vice\s+president', 'SVP'),
    (r'vice\s+president', 'VP'),
    (r'general\s+counsel', '법무총괄'),
    (r'\bpresident\b', '사장'),
    (r'\bsecretary\b', '이사회 서기'),
    (r'\btreasurer\b', '재무담당'),
]


def normalize_title(t: str) -> str:
    """길고 대문자인 공시 직함을 카드 표기에 맞게 줄인다."""
    s = re.sub(r'\s+', ' ', (t or '').strip())
    for pat, short in _ABBR:
        s = re.sub(pat, short, s, flags=re.I)
    s = re.sub(r'\s*(?:&|and)\s*', ' · ', s)        # 'CFO & COO' → 'CFO · COO'
    s = re.sub(r'\s*,\s*', ' · ', s)
    # 축약이 안 된 잔여 영문이 통째로 대문자면 보기 좋게 낮춘다
    if re.fullmatch(r'[A-Z ·\.\-]+', s) and not re.fullmatch(r'[A-Z· ]{2,5}', s):
        s = ' '.join(w if len(w) <= 4 and w.isupper() else w.capitalize() for w in s.split())
    return s.strip(' ·')


# Form 4 거래코드. 이걸 안 가르면 "내부자가 샀다"가 완전히 잘못 읽힌다 —
# 스톡옵션 부여(A)나 베스팅은 본인이 돈을 낸 게 아니고, 세금 원천징수 매도(F)는
# 파는 의사가 있어서 판 게 아니다. **투자 신호가 되는 건 공개시장 매수(P)/매도(S)뿐.**
_CODE_KIND = {
    'P': 'buy',      # 공개시장 매수 — 자기 돈으로 샀다
    'S': 'sell',     # 공개시장 매도
    'A': 'grant',    # 부여(RSU·옵션) — 보상이지 매수가 아님
    'M': 'exercise', # 옵션 행사
    'F': 'tax',      # 세금 납부용 원천징수 매도 — 매도 의사와 무관
    'G': 'gift',
}


def _first(doc, tag):
    m = re.search(rf'<{tag}>(.*?)</{tag}>', doc, re.S)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''


def _collect_trades(doc: str, owner: str, trades: list, owned: dict):
    """Form 4 한 건에서 거래 내역과 거래 후 보유주식수를 뽑는다.

    이미 내려받은 XML을 한 번 더 훑는 것뿐이라 **추가 네트워크 요청이 없다.**
    비파생(nonDerivative) 거래만 본다 — 옵션·워런트는 주식 수와 단위가 달라
    같은 표에 더하면 숫자가 뒤섞인다."""
    for blk in re.findall(r'<nonDerivativeTransaction>(.*?)</nonDerivativeTransaction>', doc, re.S):
        code = _first(blk, 'transactionCode')
        sh = _first(blk, 'transactionShares')
        px = _first(blk, 'transactionPricePerShare')
        ad = _first(blk, 'transactionAcquiredDisposedCode')
        dt = _first(blk, 'transactionDate')
        post = _first(blk, 'sharesOwnedFollowingTransaction')
        try:
            sh_n = float(re.sub(r'[^\d.]', '', sh)) if sh else None
        except ValueError:
            sh_n = None
        try:
            px_n = float(re.sub(r'[^\d.]', '', px)) if px else None
        except ValueError:
            px_n = None
        if sh_n is None or not dt:
            continue
        trades.append({'owner': owner, 'date': dt[:10], 'code': code,
                       'kind': _CODE_KIND.get(code, 'other'),
                       'shares': sh_n, 'price': px_n,
                       'dir': 'in' if ad == 'A' else 'out'})
        if post:
            try:
                n = float(re.sub(r'[^\d.]', '', post))
            except ValueError:
                continue
            prev = owned.get(owner)
            if not prev or dt[:10] >= prev['date']:
                owned[owner] = {'shares': n, 'date': dt[:10]}


def _load_cache() -> dict:
    if not CACHE.exists():
        return {}
    try:
        return json.loads(CACHE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_cache(data: dict):
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def fetch(cik: int, scan: int = 40, use_cache: bool = True) -> dict:
    """Form 4들을 훑어 {이름: 직함} 을 만든다. LLM 0콜.

    scan은 훑어볼 Form 4 개수. CEO가 최근 몇 건에 안 나오는 회사가 있어서
    (IONQ 실측) 기본값을 넉넉히 둔다. 결과는 파일에 캐시한다 — 경영진은
    자주 바뀌지 않고, EDGAR를 매번 수십 번 두드릴 이유가 없다."""
    key = str(cik)
    cache = _load_cache()
    if use_cache and key in cache:
        return cache[key]

    sub = json.loads(_get(f'https://data.sec.gov/submissions/CIK{int(cik):010d}.json'))
    rec = sub['filings']['recent']
    idxs = [i for i, f in enumerate(rec['form']) if f == '4'][:scan]

    people, trades, owned = {}, [], {}
    for i in idxs:
        acc = rec['accessionNumber'][i].replace('-', '')
        try:
            idx = json.loads(_get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json'))
            xmls = [x['name'] for x in idx['directory']['item'] if x['name'].endswith('.xml')]
            if not xmls:
                continue
            doc = _get(f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{xmls[0]}').decode('utf-8', 'replace')
        except Exception:
            continue
        name = re.search(r'<rptOwnerName>(.*?)</rptOwnerName>', doc, re.S)
        if not name:
            continue
        _collect_trades(doc, name.group(1).strip(), trades, owned)
        title = re.search(r'<officerTitle>(.*?)</officerTitle>', doc, re.S)
        remarks = re.search(r'<remarks>(.*?)</remarks>', doc, re.S)
        raw = name.group(1).strip()
        t = _resolve_title(re.sub(r'&amp;', '&', title.group(1)) if title else '',
                           re.sub(r'&amp;', '&', remarks.group(1)) if remarks else '')
        if not t:
            continue
        # 같은 사람이 여러 건 신고 — 최근 것(먼저 만나는 것)을 남긴다
        people.setdefault(raw, t)
        time.sleep(0.12)                      # SEC 예의: 초당 10건 이하

    out = {
        'cik': int(cik),
        # title은 카드 표기용으로 줄인 것, title_raw는 공시 원문 그대로.
        # 축약 규칙이 틀렸을 때 원문으로 되짚을 수 있어야 한다.
        'people': [{'raw': r, 'name': _pretty(r),
                    'title': normalize_title(t), 'title_raw': t}
                   for r, t in people.items()],
        'scanned': len(idxs),
        'fetched': time.strftime('%Y-%m-%d'),
        'trades': trades,          # 거래 내역(코드별) — 추가 요청 없이 같은 XML에서
        'owned': owned,            # 사람별 최신 보유 주식수
    }
    cache[key] = out
    _save_cache(cache)
    return out


def ceo(cik: int, scan: int = 40):
    """(표시용 이름, 직함, 원문이름). 못 찾으면 (None, None, None) — 지어내지 않는다."""
    data = fetch(cik, scan=scan)
    for p in data['people']:
        if CEO_RE.search(p['title']):
            return p['name'], p['title'], p['raw']
    return None, None, None


def executives(cik: int, scan: int = 40, limit: int = 6):
    """CEO를 뺀 주요 경영진 — 4p '주요 경영진' 표(LEADERSHIP.people)용."""
    data = fetch(cik, scan=scan)
    return [p for p in data['people'] if not CEO_RE.search(p['title'])][:limit]


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # ir.py는 레포 루트
    import ir  # noqa: E402  티커 → CIK
    for tk in (sys.argv[1:] or ['QLYS']):
        cik, name = ir.resolve_ticker(tk.upper())
        if not cik:
            print(f'{tk}: SEC에 없음')
            continue
        n, t, raw = ceo(cik)
        print(f'\n{tk} ({name}) CIK {cik}')
        print(f'  CEO: {n or "못 찾음"}  [{t or "-"}]  (원문 {raw or "-"})')
        for p in executives(cik):
            print(f'   ·   {p["name"]:<26} {p["title"]}')


def insider_flow(cik: int, months: int = 12, scan: int = 40) -> dict:
    """최근 N개월 내부자 매매 요약 — 투자 판단에 실제로 쓰이는 형태로.

    핵심은 **공개시장 매수/매도(P/S)만 신호로 센다**는 것이다. 부여(A)·베스팅·
    세금 원천징수 매도(F)를 섞으면 "내부자가 대량 매도" 같은 잘못된 그림이 나온다.
    보상으로 받은 주식은 산 게 아니고, 세금 내려고 판 건 판 의사가 아니다."""
    import datetime as _dt
    data = fetch(cik, scan=scan)
    cutoff = (_dt.date.today() - _dt.timedelta(days=int(months * 30.4))).isoformat()
    buy = sell = 0.0
    n_buy = n_sell = 0
    grant = 0.0
    for t in data.get('trades', []):
        if t['date'] < cutoff:
            continue
        if t['kind'] == 'buy':
            buy += t['shares']; n_buy += 1
        elif t['kind'] == 'sell':
            sell += t['shares']; n_sell += 1
        elif t['kind'] in ('grant', 'exercise'):
            grant += t['shares']
    return {'months': months, 'buy_shares': buy, 'sell_shares': sell,
            'buy_n': n_buy, 'sell_n': n_sell, 'grant_shares': grant,
            'net_shares': buy - sell}


def holdings(cik: int, scan: int = 40) -> list:
    """사람별 최신 보유 주식수(거래 후 잔량). 많은 순."""
    data = fetch(cik, scan=scan)
    owned = data.get('owned') or {}
    by_name = {p['raw']: p for p in data.get('people', [])}
    out = []
    for raw, rec in owned.items():
        p = by_name.get(raw, {})
        out.append({'name': p.get('name') or _pretty(raw), 'title': p.get('title', ''),
                    'shares': rec['shares'], 'as_of': rec['date']})
    return sorted(out, key=lambda r: -r['shares'])


def tenure(cik: int, name_like: str, scan: int = 40):
    """이 사람이 임원으로 처음 신고된 해 — 취임 시점의 결정론적 근거.

    Form 3(최초 신고)·Form 4의 가장 이른 거래일을 쓴다. 위임장 산문에서 "2013년부터"
    같은 문장을 LLM에 뽑게 하면 실제로 틀린다(ABCL: 초안 2013 vs 실제 2012).
    공시 제출 이력은 날짜 자체가 사실이라 틀릴 수가 없다.

    다만 **상장 전 재직분은 안 잡힌다** — Form 3는 상장(또는 임원 취임) 시점부터라
    창업자가 그 전부터 CEO였어도 상장연도로 나온다. 그래서 '~부터 재직'이 아니라
    '공시 기준 ~년부터'라고 표기해야 거짓이 안 된다."""
    data = fetch(cik, scan=scan)
    key = (name_like or '').split()[-1].lower()
    dates = [t['date'] for t in data.get('trades', [])
             if key and key in t['owner'].lower()]
    return min(dates)[:4] if dates else None


def profile_line(cik: int, name: str, scan: int = 40) -> str:
    """CEO 약력 자리에 넣을 결정론 한 줄 — 지어낼 여지가 없는 사실만.

    산문 약력은 LLM이 다른 사람 이력을 붙이는 사고가 반복됐다(ABCL: Alnylam,
    재생성 시엔 AgJunction). 위임장 발췌에도 약력 문장이 없어 인용조차 불가능하다.
    그래서 '어떤 사람인가'를 산문 대신 **공시에서 확인되는 사실**로 답한다 —
    투자자가 실제로 궁금한 것도 재직 기간과 자기 회사 주식 보유량이다."""
    # 취임연도는 **넣지 않는다.** Form 4를 최근 N건만 훑으므로 그 창의 최소 날짜가
    # 나올 뿐이고, 실제 취임과 무관하다 — Karp(팔란티어 창업자)에게 "2026년부터"가
    # 찍혔다. 근거가 못 되는 값을 그럴듯하게 쓰는 건 지어내는 것과 다르지 않다.
    # 제대로 하려면 Form 3(최초 신고)를 따로 조회해야 하고, 그건 다음 작업이다.
    bits = []
    for h in holdings(cik, scan=scan):
        if name and h['name'] == name:
            bits.append(f"보유 {h['shares']:,.0f}주({h['as_of']} 기준)")
            break
    return ' · '.join(bits)
