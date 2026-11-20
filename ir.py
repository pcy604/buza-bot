"""IR 파이프라인 — EDGAR 공시 감지 · 본문 추출 · Gemini 요약 · 카드 발송."""
import re
import json
import html
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import config
import analyzer

STATE_PATH = Path(__file__).parent / 'ir_state.json'
CIK_CACHE = Path(__file__).parent / 'cik_map.json'
FIN_CACHE_PATH = Path(__file__).parent / 'ir_financials.json'
PROFILE_CACHE_PATH = Path(__file__).parent / 'ir_profile.json'
TRANSCRIPT_CACHE_PATH = Path(__file__).parent / 'ir_transcript.json'
CIK_TTL = 7 * 86400
TEXT_LIMIT = 250_000
EXTRA_TEXT_LIMIT = 15_000
SEC_HEADERS = {'User-Agent': config.SEC_UA, 'Accept-Encoding': 'gzip, deflate'}


def _load_json_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save_json_cache(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')


def _load_fin_cache() -> dict:
    return _load_json_cache(FIN_CACHE_PATH)


def _save_fin_cache(c: dict):
    _save_json_cache(FIN_CACHE_PATH, c)


# ── 상태 (로컬 JSON — MVP 단일 프로세스 전제) ────────────────────────
def load_state() -> dict:
    st = {'watches': {}, 'seen': {}, 'news': {}}
    if STATE_PATH.exists():
        try:
            st.update(json.loads(STATE_PATH.read_text(encoding='utf-8')))
        except Exception:
            pass
    st.setdefault('news', {})
    st.setdefault('dlv', {})
    # 옛 방식(링크 누적 기준선)의 잔재. 상위 15건으로 매번 덮어써서, 순위 밖으로 밀렸다
    # 돌아온 기사를 '새 뉴스'로 다시 보냈다(2026-10-19 실측: 기준선 변경 78회 중 58회).
    st.pop('seen_news', None)
    return st


def save_state(st: dict):
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def add_watch(chat_id: int, ticker: str):
    st = load_state()
    lst = st['watches'].setdefault(str(chat_id), [])
    if ticker not in lst:
        lst.append(ticker)
    # 등록 시점의 최신 공시를 기준선으로 — 다음 '신규'부터 푸시
    try:
        if is_kr(ticker):
            fs = kr_filings(ticker)
            if fs:
                st['seen'][ticker] = fs[0]['rcept_no']
        else:
            cik, company = resolve_ticker(ticker)
            latest = latest_filing(cik)
            if latest:
                st['seen'][ticker] = latest['acc']
    except Exception as e:
        print(f'[감시 기준선 실패] {ticker}: {e} — 첫 공시 체크 때 잡는다')
    # 뉴스는 시각 기준이다. 등록 시각을 기준점으로 잡으면 첫 요약은 '등록 후 나온 것'만
    # 담는다 — 과거 30일치가 한꺼번에 쏟아지지 않는다.
    st.setdefault('news', {}).setdefault(str(chat_id), {})[ticker] = {
        'mark': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    save_state(st)


def remove_watch(chat_id: int, ticker: str):
    st = load_state()
    lst = st['watches'].get(str(chat_id), [])
    if ticker in lst:
        lst.remove(ticker)
    st.get('news', {}).get(str(chat_id), {}).pop(ticker, None)
    save_state(st)


def watches_of(chat_id: int) -> list:
    return load_state()['watches'].get(str(chat_id), [])


# ── 티커 → CIK ──────────────────────────────────────────────────────
def _cik_map() -> dict:
    if CIK_CACHE.exists() and time.time() - CIK_CACHE.stat().st_mtime < CIK_TTL:
        return json.loads(CIK_CACHE.read_text(encoding='utf-8'))
    r = requests.get('https://www.sec.gov/files/company_tickers.json', headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    m = {v['ticker'].upper(): {'cik': v['cik_str'], 'name': v['title']} for v in r.json().values()}
    CIK_CACHE.write_text(json.dumps(m, ensure_ascii=False), encoding='utf-8')
    return m


def resolve_ticker(ticker: str):
    """(cik:int, 회사명) 또는 (None, None)."""
    e = _cik_map().get(ticker.upper())
    return (e['cik'], e['name']) if e else (None, None)


# ── 한국 종목 감시 (2026-10-20) ──────────────────────────────────────
# 감시 목록엔 '005930.KS' 형태로 들어간다. 공시는 SEC 대신 DART, 뉴스는 한국어 구글 뉴스,
# 주가 반응은 야후(.KS/.KQ 그대로 된다), 수급은 네이버 증권(외국인·기관 순매수).
KR_SYM = re.compile(r'^(\d{6})\.(KS|KQ)$', re.I)


def is_kr(ticker: str) -> bool:
    return bool(KR_SYM.match(str(ticker or '')))


def kr_name(ticker: str) -> str:
    try:
        import kr
        return kr.names().get(str(ticker)[:6]) or str(ticker)[:6]
    except Exception:
        return str(ticker)[:6]


def watch_company(ticker: str):
    """감시 경로용 (id, 회사명). 미국은 (cik, 이름), 한국은 ('005930', '삼성전자')."""
    if is_kr(ticker):
        return ticker[:6], kr_name(ticker)
    return resolve_ticker(ticker)


def display_name(ticker: str) -> str:
    """알림 머리에 쓸 이름. 한국 종목은 코드만 보면 뭔지 모른다 → '삼성전자(005930)'."""
    return f'{kr_name(ticker)}({ticker[:6]})' if is_kr(ticker) else ticker.upper()


DART_LIST = 'https://opendart.fss.or.kr/api/list.json'
# 주가에 바로 영향이 큰 공시 — 알림에서 ★ 로 위에 올린다. DART 공시명(report_nm)에서 실측으로 흔한 것만.
KR_FILING_MAJOR = re.compile(
    r'잠정|영업실적|매출액또는손익구조|단일판매|공급계약|유상증자|무상증자|전환사채|신주인수권|교환사채|'
    r'자기주식|합병|분할|영업양수|영업양도|자산양수|자산양도|최대주주변경|소송|부도|감자|상장폐지|관리종목|'
    r'불성실공시|거래정지|매매거래정지|투자판단|타법인주식|신규시설투자|현금ㆍ현물배당|주식배당|공개매수')
# 같은 종류가 하루 수십 건씩 쏟아지는 공시 — 없애지 않고 '외 N건'으로 접는다(내부자 매매 기사와 같은 이유).
KR_FILING_FOLD = re.compile(r'임원ㆍ주요주주특정증권등소유상황보고서|주식등의대량보유상황보고서|'
                            r'증권발행실적보고서|투자설명서|일괄신고추가서류|특수관계인')


def kr_filings(ticker: str, days: int = 14) -> list:
    """DART 최근 공시 [{'rcept_no','report_nm','rcept_dt','flr_nm','major','fold','url'}] 최신순."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent / 'decks'))
    import sources_kr as K
    import dart_client as D
    cc = K.to_corp_code(ticker)
    if not cc:
        return []
    end = datetime.now(timezone.utc) + timedelta(hours=9)
    j = requests.get(DART_LIST, params={'crtfc_key': D._key(), 'corp_code': cc,
                                        'bgn_de': (end - timedelta(days=days)).strftime('%Y%m%d'),
                                        'end_de': end.strftime('%Y%m%d'), 'page_count': 100},
                     timeout=20).json()
    if j.get('status') not in ('000', '013'):      # 013 = 조회된 데이터 없음
        raise RuntimeError(f'DART list {j.get("status")} {j.get("message")}')
    out = []
    for x in j.get('list') or []:
        nm = re.sub(r'\s+', ' ', x.get('report_nm', '')).strip()
        out.append({'rcept_no': x['rcept_no'], 'report_nm': nm, 'rcept_dt': x.get('rcept_dt', ''),
                    'flr_nm': x.get('flr_nm', ''),
                    'major': bool(KR_FILING_MAJOR.search(nm.replace(' ', ''))),
                    'fold': bool(KR_FILING_FOLD.search(nm.replace(' ', ''))),
                    'url': f'https://dart.fss.or.kr/dsaf001/main.do?rcpNo={x["rcept_no"]}'})
    out.sort(key=lambda f: f['rcept_no'], reverse=True)
    return out


# 감시자별 전달 기록 (2026-10-21) ──────────────────────────────────────
# 예전엔 `all(send(c) for c in watchers)` 하나로 판정했다. 결함 둘:
#   ① 한 명이 봇을 차단하면(영구 실패) 기준선이 영영 안 넘어가 나머지가 같은 공시를 매 실행마다 다시 받음
#   ② 앞사람 성공·뒷사람 일시 실패면 다음 실행에 앞사람이 또 받음(중복)
# 이제 (종목, 공시 묶음 key)마다 '받은 사람'을 기억하고, 못 받은 사람에게만 다시 보낸다.
# 영구 실패(tg.permanent_fail)는 받은 것으로 친다 — 차단한 사람 때문에 다른 사람이 피해 보지 않게.
DLV_MAX_FAILS = 3      # 일시 실패가 이만큼 쌓이면 호출부가 가벼운 대체 경로(텍스트)로 보낸다


def deliver(st: dict, t: str, key: str, watchers: list, fn) -> bool:
    """watchers 에게 fn(chat, fails) 로 보낸다. 모두 끝났으면 True(기록 삭제), 아니면 False(다음 실행에 남은 사람만)."""
    import tg
    d = st['dlv'].get(t)
    if not d or d.get('key') != key:
        d = {'key': key, 'done': [], 'fails': 0}
    for c in watchers:
        if str(c) in d['done']:
            continue
        if fn(c, d['fails']):
            d['done'].append(str(c))
        elif tg.permanent_fail():
            print(f'  [{t}] {c} 영구 실패({tg.LAST_ERR.get("desc", "")[:40]}) → 받은 것으로 처리')
            d['done'].append(str(c))
    if all(str(c) in d['done'] for c in watchers):
        st['dlv'].pop(t, None)
        return True
    d['fails'] += 1
    st['dlv'][t] = d
    return False


# 이번 실행에서 종목별 조회가 실패한 목록 — run.py 가 health 로 넘긴다(조용한 실패 방지, 2026-10-21)
WATCH_ERRORS = []


def check_kr_filings(send) -> int:
    """한국 감시 종목의 새 DART 공시를 보낸다. **매 크론마다** 부른다 — 잠정실적·수주 공시는
    장중에 나와 바로 주가에 반영되므로 6시간 게이트에 두면 늦다. 종목당 DART 1콜이라 싸다.
    처음 보는 종목은 기준선만 잡고 보내지 않는다(과거 2주치가 쏟아지지 않게)."""
    st = load_state()
    tickers = sorted({t for lst in st['watches'].values() for t in lst if is_kr(t)})
    n = 0
    for t in tickers:
        try:
            fs = kr_filings(t)
        except Exception as e:
            print(f'  [{t}] DART 공시 조회 실패: {e}')
            WATCH_ERRORS.append(f'KR {t}: {str(e)[:60]}')
            continue
        last = st['seen'].get(t)
        if not fs:
            continue
        if not last:
            st['seen'][t] = fs[0]['rcept_no']
            save_state(st)
            continue
        new = [f for f in fs if f['rcept_no'] > last]
        if not new:
            continue
        watchers = [int(c) for c, lst in st['watches'].items() if t in lst]
        print(f'  [{t}] 새 DART 공시 {len(new)}건')
        if deliver(st, t, new[0]['rcept_no'], watchers, lambda c, _f: send(c, t, new)):
            st['seen'][t] = new[0]['rcept_no']
            for f in new[:10]:
                note_filed(st, t, f.get('report_nm', ''))
            n += 1
        save_state(st)
    return n


NAVER_TREND = 'https://m.stock.naver.com/api/stock/{code}/trend'


def _num(v):
    try:
        return float(str(v).replace(',', '').replace('+', ''))
    except Exception:
        return None


def kr_flow(ticker: str, since: datetime = None, max_days: int = 5):
    """외국인·기관 순매수(주식 수·추정 금액) — 네이버 증권 모바일 API.

    반환 {'days','foreign','inst','foreign_amt','inst_amt','f_streak','i_streak'} 또는 None.
      *_amt   순매수 주식 수 × 그날 종가(원). 거래소 공식 순매수 '금액'과 조금 다르다(추정).
      *_streak 최근일부터 같은 방향(+순매수/-순매도)이 이어진 날 수, 부호 포함.
    since 가 있으면 그 이후 거래일만(최소 1일), 없으면 최근 max_days 일.
    """
    code = str(ticker)[:6]
    r = requests.get(NAVER_TREND.format(code=code), params={'pageSize': 20},
                     headers={'User-Agent': NEWS_UA, 'Referer': 'https://m.stock.naver.com/'}, timeout=15)
    r.raise_for_status()
    rows = r.json()
    if isinstance(rows, dict):
        rows = rows.get('result') or rows.get('trends') or []
    data = []
    for x in rows:
        d = str(x.get('bizdate') or x.get('localTradedAt') or '')[:10].replace('-', '')
        f = _num(x.get('foreignerPureBuyQuant'))
        i = _num(x.get('organPureBuyQuant'))
        px = _num(x.get('closePrice'))
        if len(d) == 8 and f is not None and i is not None:
            data.append((d, f, i, px or 0))
    if not data:
        return None
    data.sort(reverse=True)                     # 최신 먼저
    if since:
        cut = (since + timedelta(hours=9)).strftime('%Y%m%d')
        win = [x for x in data if x[0] > cut][:max_days] or data[:1]
    else:
        win = data[:max_days]

    def streak(k):
        s0 = 1 if data[0][k] > 0 else -1 if data[0][k] < 0 else 0
        if not s0:
            return 0
        n = 0
        for x in data:
            if (x[k] > 0) - (x[k] < 0) != s0:
                break
            n += 1
        return n * s0

    return {'days': len(win), 'from': win[-1][0], 'to': win[0][0],
            'foreign': sum(x[1] for x in win), 'inst': sum(x[2] for x in win),
            'foreign_amt': sum(x[1] * x[3] for x in win), 'inst_amt': sum(x[2] * x[3] for x in win),
            'f_streak': streak(1), 'i_streak': streak(2)}


# ── EDGAR 공시 ──────────────────────────────────────────────────────
def filing_history(cik: int, limit: int = 24) -> list:
    """관심 폼(config.IR_FORMS)에 해당하는 공시를 최신순으로 최대 limit개."""
    if not cik:
        return []
    r = requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', headers=SEC_HEADERS, timeout=30)
    r.raise_for_status()
    rec = r.json()['filings']['recent']
    items_all = rec.get('items', [''] * len(rec['form']))
    out = []
    for i in range(len(rec['form'])):
        form = rec['form'][i]
        if form not in config.IR_FORMS:
            continue
        out.append({'form': form, 'acc': rec['accessionNumber'][i], 'date': rec['filingDate'][i],
                    'primary': rec['primaryDocument'][i], 'items': items_all[i]})
        if len(out) >= limit:
            break
    return out


def _is_earnings_form(f: dict) -> bool:
    return f['form'] in ('10-Q', '10-K', '20-F', '6-K') or (f['form'] == '8-K' and '2.02' in (f.get('items') or ''))


def latest_filing(cik: int, earnings_only: bool = False):
    """관심 폼 중 최신 1건 {form, acc, date, primary, items}.

    earnings_only=True면 실적성 공시(10-Q/K·20-F·6-K·8-K Item 2.02) 우선, 없으면 최신 아무거나.
    """
    hist = filing_history(cik, limit=24)
    if not hist:
        return None
    if not earnings_only:
        return hist[0]
    return next((f for f in hist if _is_earnings_form(f)), hist[0])


def _strip_html(raw: str) -> str:
    raw = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', raw)
    # inline XBRL(iXBRL) 숨김 메타데이터 블록 — 화면엔 안 보이지만 텍스트 추출엔 그대로 섞여
    # 실제 본문(Item 1 등) 앞에 수만 자 쓰레기로 끼어듦. 10-K/20-F에서 특히 큼(SATL 기준 136KB).
    raw = re.sub(r'(?is)<ix:header\b.*?</ix:header>', ' ', raw)
    raw = re.sub(r'(?i)</(p|div|tr|table|li|h\d)>', '\n', raw)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    txt = html.unescape(raw)
    txt = re.sub(r'[ \t\xa0]+', ' ', txt)
    return re.sub(r'\n\s*\n+', '\n', txt).strip()


def filing_text(cik: int, filing: dict) -> str:
    """주 문서 + EX-99 첨부(실적 보도자료·주주서한)를 합쳐 텍스트로."""
    acc = filing['acc'].replace('-', '')
    base = f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}'
    docs = [filing['primary']]
    try:
        idx = requests.get(f'{base}/index.json', headers=SEC_HEADERS, timeout=30).json()
        for it in idx.get('directory', {}).get('item', []):
            n = it.get('name', '')
            if re.search(r'(?i)(ex[-_]?99|exhibit99)', n) and n.endswith(('.htm', '.html')) and n not in docs:
                docs.append(n)
    except Exception as e:
        print(f'[index 실패] {e}')
    parts = []
    for d in docs[:4]:
        try:
            r = requests.get(f'{base}/{d}', headers=SEC_HEADERS, timeout=60)
            parts.append(_strip_html(r.text))
            time.sleep(0.3)  # SEC rate limit 예의
        except Exception as e:
            print(f'[문서 실패] {d}: {e}')
    return '\n\n===== 문서 구분 =====\n\n'.join(parts)[:TEXT_LIMIT]


# ── 구글 뉴스 (공시에 안 잡히는 언론보도 — 무료, Gemini 미사용) ──────────
NEWS_LOCALES = [('en-US', 'US'), ('es-419', 'AR')]  # 국제 금융언론 + 중남미 현지언론(스몰캡 커버리지 보완)
NEWS_LOCALES_KR = [('ko', 'KR')]                     # 한국 종목: 국내 언론
NEWS_DAYS = 30
NEWS_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

# ── 뉴스 정제 ───────────────────────────────────────────────────────
# 2026-09-17 실측: SATL 30건 중 9/14 하루치 20건이 **사건 4개**의 재탕이었고,
# AXTI 30건에는 회사와 무관한 항목이 섞여 있었다. 링크만 보내면 이 쓰레기가
# 그대로 사용자에게 간다. 아래는 전부 실제로 관측된 것만 막는다.
#
# ⚠️ 차단목록은 유지보수 부채다. 새 콘텐츠 팜이 생기면 또 뚫린다.
#    그래서 "이 회사 기사가 아닌 것"만 막고, 논조(강세·약세)로는 절대 거르지 않는다.
#    나쁜 뉴스를 걸러내면 그건 정제가 아니라 왜곡이다.

# 회사가 아니라 **다른 금융상품**을 다루는 출처. AXTI 검색에 로빈후드 토큰화 주식
# 'AXT Inc rStock (RAXTI)' 시세 페이지가 잡혔다 — 이 회사 뉴스가 아니다.
NEWS_JUNK_SOURCES = ('mexc', 'binance', 'bybit', 'coingecko', 'beincrypto',
                     'moomoo', 'crypto.com', 'gurufocus',
                     # 2026-10-03 추가: 자동생성 시세·투자의견 페이지만 내보내는 곳.
                     'marketbeat', 'intellectia')
# 제목만 봐도 기사가 아닌 것(시세 위젯·환산 페이지) 또는 파생상품 기사.
NEWS_JUNK_TITLE = re.compile(
    r'(?i)(\brstock\b|robinhood token|cryptocom:|\bconvert \d|price today|'
    r'live .{0,20}price chart|market cap.{0,20}chart|\btradr\b|'
    r'\b[23]x\b|\bleveraged etf|\binverse etf|gf value|gf score|'
    # ── 2026-10-03 추가 ──────────────────────────────────────────────
    # 운영 28회 중 **13회**가 "요약할 게 없음"으로 끝났는데, 사유를 보니 전부
    # 단순 시세·목표가·타사 기사였다. 즉 LLM 호출 13회를 **쓰레기 걸러내는 데** 썼다.
    # 무료 단계에서 막으면 그 호출이 그대로 절약된다.
    # 회사명이 제목에 있어도 기사가 아닌 것들 — 실측 제목에서만 뽑았다.
    r'stock price.{0,30}(quote|history)|options? chain|cadena de opciones|'
    r'shares outstanding|acciones b[aá]sicas en circulaci[oó]n|'
    r'should i buy|should you (buy|sell)|'
    r'price target\s*[—-]\s*prediction|forecast\s*[—-]\s*price target|'
    # ── 2026-10-11 추가 ──────────────────────────────────────────────
    # 사용자 지적("오래된 뉴스도 막 요약하고 분석 퀄리티도 별로")을 받고
    # 5종목 174건을 실제로 받아 세어보니 **현 필터를 통과한 것의 15%**가
    # 사건이 아닌 글이었다. 아래 패턴은 그 174건에서만 뽑았다 — 지어낸 패턴을
    # 넣으면 진짜 뉴스를 죽인다. 전수 확인 결과 21건이 걸리고 그중 20건이
    # 확실한 잡음, 1건만 아까웠다(주가 헤드라인 뒤에 묻힌 Sovereign AI 계약 —
    # 같은 사건이 다른 기사로도 들어와 손실이 상쇄된다).
    #
    # 프롬프트는 이미 "주가 등락·목표가는 사건이 아니다"라고 쓰고 있었다.
    # 그런데 걸러내지 않고 넣어주니, **LLM 호출을 쓰레기 버리는 데 썼다.**
    r'is it too late to (buy|sell)|'
    r'why .{0,45}\b(stock|shares)\b.{0,25}'
    r'(gain|jump|surg|soar|slip|plunge|fell|fall|ris|rall|pop|sink|drop|climb|tumbl|power|spike|slid)|'
    r'\b(is|are|was|were) (up|down) \d+(\.\d+)?%|'
    r'price target|bulls and bears|back in focus|'
    r'tokenized|xstock|'
    r'better .{0,40}\bstock\b|'
    r'\bvs\.?\s+\w+\s*:|'
    # 2차 실측(위 패턴 적용 후 남은 것). AXTI 는 7건 중 5건이 이 부류였다.
    # 자동생성 예측글·포럼·스페인어 시세페이지·법무법인 모집공고가 주범이다.
    r'\bstock forecasts?\b|stock forum|forum & discussion|'
    r'\bai predicts\b|predicts .{0,25}stock price|'
    r'precio de las acciones|cotizaci[oó]n e historial|gr[aá]ficos.{0,20}capitalizaci[oó]n|'
    r'\bslumps? \d+%|shares fall more than \d+%|'
    r'\b(rose|fell|gained|lost) \d+(\.\d+)?% in the\b|'
    r'movements inform|risk allocation model|'
    r'analyst blog|stock of the day|'
    r'investigates claims on behalf|'
    # 파생·암호화폐 심볼 페이지: 'Lumentum Holdings (Derivatives) LITE39944 (LITE39944-USD)'
    r'\(derivatives\)|-usd\)|\(cryptocurrency)')

# 내부자 매매 기사 — **없애지 않고 한 줄로 접는다.** 정보이긴 한데 양이 문제다:
# CORT 38건 중 13건(34%)이 이것이었고, 같은 거래 하나가 매체마다 다른 문장으로
# 적혀 사건 묶기도 안 걸렸다(Sean Maduck $2.9M 한 건이 제목 4개).
# 그대로 두면 limit 자리를 다 먹어 CHMP 승인 같은 진짜 사건이 밀려난다.
# 다른 4종목은 0% 였다 — 종목 따라 터지는 문제라 상한으로 막는 게 맞다.
NEWS_INSIDER = re.compile(
    r'(?i)(\bsells?\b.{0,30}(shares|stock|\$)|\bsold\b.{0,25}(shares|worth)|'
    r'insider (sold|sale|buy|bought)|form 4|10b5-1|stock option exercis|'
    r'offloads|share sale|gifts shares|'
    # Form 4 를 사람이 풀어 쓴 제목. 'An officer reports 12,191 shares…' 가
    # 위 패턴에 안 걸려 접기를 빠져나갔다.
    r'officer reports|reports [\d,]{3,} shares)')

# ⚠️ 폐기한 규칙 — "제목에 회사명도 티커도 없으면 버린다"
#
# 2026-10-11 에 넣었다가 같은 날 뺐다. 5종목 174건으로 검증했을 때 오탐이
# 0 이었다(걸린 3건이 전부 Jim Cramer 코너·Barron's 라운드업·스페인어 정치
# 칼럼이었다). 그런데 **검증 표본에 SATL 이 없었다.**
#
# SATL 30일치 33건에 걸어보니 오탐이 3건 나왔다. 전부 진짜 사건이다:
#   · A satellite network is on track to map the whole Earth daily in H2 2027
#   · Six more satellites are planned for a U.S. program to monitor maritime…
#   · A satellite got within 27 kilometers of a spent rocket in orbit
# 소형주는 회사명 없이 **사건만 쓰는** 헤드라인이 흔하다. 174건에서 3건
# 거르자고 SATL 에서 9%(3/33)를 죽이는 건 손해다.
#
# 다시 넣으려면 '제목에 이름이 없다'만으로 버리지 말고, 다른 잡음 신호와
# 같이 걸릴 때만 버려야 한다. 지금은 규칙을 걷어낸다.
NEWS_INSIDER_KEEP = 1        # 내부자 매매는 최신 1건만 남기고 나머지는 건수로
# 같은 기사를 나라별로 복제하는 매체. 'Investing.com' 은 두고 'Investing.com Nigeria' 만 버린다
# (기본판이 이미 목록에 있고, 나머지는 같은 기사의 번역·재게시다).
NEWS_LOCALE_CLONE = re.compile(r'(?i)^(investing\.com|marketscreener|stock titan|tradingview)\s+\S')
# 사건 동일성 판정에서 뺄 단어 — 회사명·매체 상용구는 어느 기사에나 있어 유사도를 뭉갠다.
NEWS_STOPWORDS = frozenset('''a an the and or of for to in on at by with from as is are was were
be been will its it this that stock stocks share shares inc corp co ltd plc holdings therapeutics
today yesterday news update report reports said says why how what more amid after before
nasdaq nyse com'''.split())


def _news_tokens(title: str, company: str) -> frozenset:
    """제목 → 사건 식별용 토큰 집합. 회사명·불용어·숫자단위는 뺀다."""
    # 한글도 토큰으로 친다(2026-10-20 한국 종목 감시). 한글 낱말은 2자도 뜻이 있다(수주·증설).
    t = re.sub(r'[^a-z0-9가-힣 ]+', ' ', title.lower())
    drop = set(NEWS_STOPWORDS)
    drop |= {w for w in re.sub(r'[^a-z가-힣 ]+', ' ', company.lower()).split() if w}
    return frozenset(_stem(w) for w in t.split()
                     if (len(w) > 2 or (len(w) == 2 and re.match(r'[가-힣]', w))) and w not in drop)


def _stem(w: str) -> str:
    """꼬리만 떼는 아주 얕은 스테밍. launch / launches / launching 이 서로 다른
    토큰이 되면 같은 사건이 안 묶인다(SATL Merlin 발사 실측)."""
    if re.match(r'[가-힣]', w):
        # 한국어는 조사가 낱말에 붙는다('시장에서'·'버즈를'). 떼지 않으면 같은 사건이 안 묶인다.
        if len(w) >= 3:
            for p in KR_PARTICLES:
                if w.endswith(p) and len(w) - len(p) >= 2:
                    return w[:-len(p)]
        return w
    for suf in ('ing', 'es', 'ed', 's'):
        if len(w) > 4 and w.endswith(suf):
            return w[:-len(suf)]
    return w


KR_PARTICLES = ('에서', '으로', '에게', '부터', '까지', '하며', '했다', '한다',
                '은', '는', '이', '가', '을', '를', '의', '에', '로', '와', '과', '도', '만')


def _news_is_junk(item: dict) -> bool:
    src = (item.get('source') or '').lower()
    if any(j in src for j in NEWS_JUNK_SOURCES):
        return True
    if NEWS_LOCALE_CLONE.match(item.get('source') or ''):
        return True
    t = item.get('title') or ''
    return bool(NEWS_JUNK_TITLE.search(t) or NEWS_JUNK_TITLE_KR.search(t))


# 한국어 기사 중 이 회사의 사건이 아닌 것 — 사진·인사·부고, 그리고 여러 종목을 나열하는 시황·순위 기사.
# '[특징주]'는 남긴다: 왜 움직였는지를 적은 기사라 사건 단서가 된다.
NEWS_JUNK_TITLE_KR = re.compile(
    r'\[(포토|사진|인사|부고|게시판|오늘의 ?운세|날씨|표)\]|'
    r'(개장|마감|오전|오후) ?시황|증시 ?(마감|출발)|(코스피|코스닥).{0,20}(마감|출발|개장)|'
    r'(순매수|순매도|상승률|하락률|거래량|거래대금|시가총액) ?상위|'
    r'오늘의 ?(증시|종목|주요 ?일정)|주요 ?공시 ?모음|\[공시 ?모음\]|목표 ?주가.{0,6}(상향|하향|유지)')


# 1차 소스(보도자료 배포망). 같은 사건의 대표 기사로 우선 뽑는다.
# ⚠️ 한계: 회사 보도자료는 좋은 소식만 낸다. 그래서 '대표 선택'에만 쓰고
#    '수집 대상'을 여기로 좁히지는 않는다 — 좁히면 악재가 통째로 사라진다.
NEWS_WIRES = ('globenewswire', 'business wire', 'businesswire', 'pr newswire', 'prnewswire')


MIN_SHARED = 3        # 같은 사건으로 보려면 공통 토큰이 이만큼은 있어야 한다

# ── 2026-10-24 뉴스 파이프라인 개편: '기사'가 아니라 '사건'을 센다 ──────────────────
# ① 지문(숫자) 묶기 ② 출처 등급 ③ 중요도 점수로 줄 세운 뒤 자르기 ④ 이미 보낸 사건 기억(deliver_news)
# ⑤ 공시로 이미 알린 사건 제외(summarize_news). 실측 근거는 claude/18 운영 점검 문서.

_NUM_RE = re.compile(r'(\$?\d[\d,]*(?:\.\d+)?)\s*(%|퍼센트|조|억|만|원|달러|bn|billion|b\b|million|m\b|k\b)?', re.I)


def _num_sig(title: str) -> frozenset:
    """제목의 '핵심 숫자' 지문 — 같은 사건은 매체가 제목을 바꿔 써도 숫자는 같다($16.8B·4,140억·+37%).
    연도·작은 정수(단위 없는 1~2자리)·분기 표기는 뺀다(어느 기사에나 있어 지문이 안 됨)."""
    out = set()
    for num, unit in _NUM_RE.findall(title or ''):
        n = num.replace(',', '').replace('$', '')
        if not n or n.count('.') > 1:
            continue
        try:
            v = float(n)
        except ValueError:
            continue
        u = (unit or '').lower()
        if not u and (1900 <= v <= 2100 or v < 100):
            continue
        out.add(f'{v:g}{u}')
    return frozenset(out)


# 출처 등급(높을수록 믿을 만한 원천). 같은 사건이면 높은 등급이 대표가 된다.
NEWS_TIER3 = ('reuters', 'bloomberg', 'wall street journal', 'wsj', 'financial times', 'cnbc', 'barron',
              'associated press', 'ap news', 'nikkei', 'the information', 'axios',
              '연합뉴스', '연합인포맥스', '한국경제', '매일경제', '머니투데이', '서울경제', '조선비즈', '이데일리',
              '뉴스1', '뉴시스', '파이낸셜뉴스', '아시아경제', '헤럴드경제', '전자신문', '디일렉', 'thelec',
              '조선일보', '중앙일보', '동아일보', '한겨레', 'kbs', 'mbc', 'sbs', 'ytn')
NEWS_TIER1 = ('tradingview', 'marketscreener', 'stocksbnb', 'stock titan', '24/7 wall st', 'motley fool', 'fool.com',
              'zacks', 'insider monkey', 'investorplace', 'simply wall st', 'tipranks', 'benzinga', 'seeking alpha',
              'yahoo finance video', 'finviz', 'nasdaq.com', 'aol', 'msn')


def _tier(source: str) -> int:
    s = (source or '').lower()
    if any(w in s for w in NEWS_WIRES):
        return 4
    if any(w in s for w in NEWS_TIER3):
        return 3
    if any(w in s for w in NEWS_TIER1):
        return 1
    return 2


# 사건 유형(제목 키워드) — 프롬프트의 1~3순위와 같은 기준. 자르기 전에 기계적으로 줄을 세운다.
NEWS_P1 = re.compile(r'(?i)\b(earnings|results|quarter(ly)?|q[1-4]\b|revenue|guidance|outlook|merger|acquisition|'
                     r'acquire[sd]?|buyout|takeover|agree[sd]? to buy|deal|contract|order[s]?\b|award(ed)?|offering|buyback|'
                     r'repurchase|dividend|split|spin-?off|ipo|bankrupt\w*|delist\w*)|'
                     r'실적|영업이익|매출|잠정|가이던스|합병|인수|매각|분할|계약|수주|공급|증자|자사주|배당|상장|공시|부도|상폐')
NEWS_P2 = re.compile(r'(?i)\b(lawsuit|sue[sd]?|probe|investigat\w*|sec\b|ftc|doj|recall|regulat\w*|approv\w*|fda|'
                     r'ceo|cfo|resign\w*|appoint\w*|layoff\w*|plant|factory|production|launch\w*|unveil\w*)|'
                     r'소송|제재|조사|리콜|규제|승인|허가|대표이사|사임|선임|공장|증설|감산|생산|출시|양산')
NEWS_SOFT = re.compile(r'(?i)(should you|is it time|buy now|prediction|could\b|might\b|\?$|top \d+ stocks|vs\.?\b|'
                       r'what to expect|here\'s why|estimates\s[–-]|keeps its|reiterat\w*)|관련주|주목|전망은|이유는|추도식|기념식|봉사|나눔|기부|사회공헌|캠페인|시상식|미담|후원')


def _materiality(item: dict) -> float:
    t = item.get('title') or ''
    sc = 3.0 if NEWS_P1.search(t) else 1.5 if NEWS_P2.search(t) else 0.0
    tier = _tier(item.get('source'))
    if tier == 1:
        sc *= 0.4   # 재가공·의견 사이트는 제목에 'Q3'가 있어도 사건 보도가 아니다(10-24 실측: Seeking Alpha 의견 7건이 로이터·블룸버그보다 위)
    elif tier >= 3 and sc == 0:
        sc = 1.0    # 주요 매체는 제목에 키워드가 없어도 사건일 가능성이 높다
    if NEWS_SOFT.search(t):
        sc -= 1.5
    sc += min(item.get('echo', 1), 8) ** 0.5          # 받아쓴 매체 수(체감 감소)
    sc += (tier - 2) * 0.8                              # 출처 등급
    return sc


def _iso_day(d: str):
    try:
        return datetime.strptime(d, '%Y-%m-%d')
    except Exception:
        return datetime(1970, 1, 1)


def _news_cluster(items: list, company: str, thresh: float = 0.7) -> list:
    """같은 사건을 다룬 기사들을 묶어 대표 1건만 남긴다.

    제목 완전일치로만 중복을 걸렀더니 'Satellogic to launch three satellites in
    October 2026' 와 'Three Satellogic satellites will launch in October' 가
    따로 남았다. 토큰 자카드 유사도로 묶는다.

    ⚠️ 깨지는 경우: 같은 고유명사를 공유하는 **서로 다른 사건**(예: 같은 주에
       'Slingshot III 확장'과 'Slingshot III 계약 해지')은 오합쳐질 수 있다.
       그래서 날짜가 같은 것끼리만 묶고, 임계값을 0.5 로 느슨하지 않게 잡는다.
    반환 항목에 'echo'(몇 개 매체가 받아썼는지)를 붙인다 — 받아쓴 매체 수가
    그 사건의 주목도 신호다.
    """
    # 한국어 기사는 같은 사건도 제목 표현이 훨씬 제각각이다(실측 2026-10-20 삼성전자 '갤럭시 버즈 온'
    # 8건이 영어 기준 3개·0.7 로는 하나도 안 묶였다). 2개·0.5 로 낮춰도 삼성전자·에코프로비엠
    # 30건에서 잘못 묶인 것이 없었다. 영어 기준은 그대로 둔다.
    min_shared = MIN_SHARED
    if re.search(r'[가-힣]', company):
        min_shared, thresh = 2, min(thresh, 0.5)
    clusters = []
    for it in items:
        toks = _news_tokens(it['title'], company)
        if not toks:
            continue
        hit = None
        nums = _num_sig(it['title'])
        for c in clusters:
            inter = len(toks & c['toks'])
            # 숫자 지문: 핵심 숫자가 같고 공통 낱말이 하나라도 있으면 같은 사건(하루 경계를 넘어도) — 2026-10-24
            if nums and (nums & c['nums']) and inter >= 1 and abs((_iso_day(c['date']) - _iso_day(it['date'])).days) <= 1:
                hit = c
                break
            if c['date'] != it['date']:
                continue  # 다른 날이면 다른 사건으로 본다(오합침 방지)
            # 자카드가 아니라 **겹침계수**(짧은 쪽 기준)다. 자카드는 제목
            # 길이가 다르면 불리해서, 같은 사건인데도 안 묶인다. 실측(SATL
            # 10-02 Merlin 위성 발사): 'Satellogic Inc. Announces the Successful
            # Satellite Launch of Its First Merlin.01…' 과 'Satellogic launches
            # first Merlin satellite constellation' 이 자카드 0.3 으로 갈라져
            # 상위 8칸 중 4칸을 한 사건이 먹었다.
            #
            # 대신 짧은 제목 둘이 흔한 단어 두어 개로 합쳐지는 걸 막으려고
            # **공통 토큰 3개 이상**을 같이 요구한다. 174+33건에 걸어 과합침이
            # 없는 선으로 잡았다.
            if inter >= min_shared and inter / min(len(toks), len(c['toks'])) >= thresh:
                hit = c
                break
        if hit:
            hit['echo'] += 1
            hit['toks'] |= toks
            hit['links'].append(it['link'])
            hit['nums'] |= nums
            # 대표는 출처 등급이 높은 기사(보도자료·통신사·주요 경제지), 같으면 먼저 본 것
            if _tier(it.get('source')) > _tier(hit['item'].get('source')):
                hit['item'] = it
        else:
            clusters.append({'toks': set(toks), 'item': it, 'echo': 1, 'nums': set(nums),
                             'date': it['date'], 'links': [it['link']]})
    out = []
    for c in clusters:
        rep = dict(c['item'])
        rep['echo'] = c['echo']
        rep['links'] = c['links']
        out.append(rep)
    return out


_RSS_CACHE = {}   # 한 실행 안에서 같은 회사 RSS 를 사용자 수만큼 다시 받지 않게


def _rss_items(company: str, locales=None) -> list:
    """구글 뉴스 RSS 원본(기간·잡음 필터 전). 한 실행 동안만 캐시한다."""
    locales = locales or NEWS_LOCALES
    ck = company if locales == NEWS_LOCALES else (company, tuple(locales))   # 기본 로케일은 예전 키 그대로
    if ck in _RSS_CACHE:
        return _RSS_CACHE[ck]
    rows = []
    q = urllib.parse.quote(f'"{company}"')
    for hl, gl in locales:
        url = f'https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}'
        try:
            r = requests.get(url, headers={'User-Agent': NEWS_UA}, timeout=15)
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f'[뉴스RSS 실패] {company} {hl}/{gl}: {e}')
            continue
        for item in root.findall('.//item'):
            src_el = item.find('source')
            rows.append({'title': (item.findtext('title') or '').strip(),
                         'link': item.findtext('link') or '',
                         'pubDate': item.findtext('pubDate'),
                         'source': (src_el.text or '').strip() if src_el is not None else ''})
    _RSS_CACHE[ck] = rows
    return rows


def company_news(company: str, days: int = NEWS_DAYS, limit: int = 8, raw: bool = False,
                 since: datetime = None, exclude: set = None, locales=None, rank: bool = False) -> list:
    """구글 뉴스 RSS로 회사 관련 최근 보도 수집. 영어+스페인어 로케일 병합, 잡음·중복·기간 필터.

    반환: [{'title','link','source','date','echo','links'}], 최신순.
      echo  — 같은 사건을 받아쓴 매체 수(주목도 신호)
      links — 그 사건으로 묶인 모든 기사 링크(감시 기준선 저장용)

    raw=True 면 사건 묶음을 하지 않고 낱개로 준다.

    since   — 이 시각 이후 발행분만(감시 뉴스: '지난번 보낸 뒤 나온 것'). 주어지면 days 대신 쓴다.
    exclude — 링크나 't:'+소문자 제목 집합. 겹침 구간에서 이미 보낸 기사를 뺀다.
              **묶기 전에** 뺀다 — 묶은 뒤 빼면 이미 보낸 기사가 새 기사의 대표로 남는다.
    """
    cutoff = since or (datetime.now(timezone.utc) - timedelta(days=days))
    exclude = exclude or set()
    seen, out = set(), []
    for row in _rss_items(company, locales):
        title = row['title']
        if not title:
            continue
        try:
            pub = datetime.strptime(row['pubDate'], '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if pub < cutoff:
            continue
        source = row['source']
        if source and title.endswith(f' - {source}'):
            title = title[:-(len(source) + 3)].strip()
        # 매체명을 뗀 **뒤** 소문자로 비교한다. 떼기 전 제목으로 비교하면
        # 같은 기사가 매체마다 다른 키가 되고, 대소문자만 다른 재게시도
        # 따로 센다 — 실측: AXTI 의 'Stock Forecasts'/'Stock forecasts' 가
        # 둘 다 상위 8건에 들어와 자리를 하나 더 먹었다.
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        if row['link'] in exclude or ('t:' + key) in exclude:
            continue
        it = {'title': title, 'link': row['link'],
              'source': source, 'date': pub.strftime('%Y-%m-%d'),
              'ts': pub.isoformat()}
        if _news_is_junk(it):
            continue
        out.append(it)
    out.sort(key=lambda x: x['ts'], reverse=True)
    if raw:
        return out[:limit]
    # 같은 사건의 재탕을 묶는다. 묶은 뒤 자르는 게 중요하다 — 먼저 자르면
    # limit 자리를 한 사건의 복제본이 다 차지한다(실측: SATL 상위 8건이 사건 2개였다).
    out = _news_cluster(out, company)
    out.sort(key=lambda x: (x['date'], x['echo']), reverse=True)
    out = _fold_insider(out)
    if rank:
        # 감시 뉴스(2026-10-24): 재가공 사이트의 '추정치·등급 유지' 류는 버리고, 중요도 점수로 줄 세운 뒤 자른다.
        #   예전엔 최신순으로 15건을 잘라, 한두 매체만 쓴 중요한 기사가 AI 에 닿지도 못했다.
        pool = [x for x in out if not (_tier(x.get('source')) == 1 and NEWS_SOFT.search(x.get('title') or ''))]
        for x in pool:
            x['score'] = round(_materiality(x), 2)
        pool.sort(key=lambda x: (x['score'], x['date']), reverse=True)
        for x in pool:
            x['_pool'] = len(pool)
        return pool[:limit]
    return out[:limit]


NEWS_FRESH_DAYS = 7          # "새로 나온"이라고 말해도 되는 선
NEWS_MIN_ITEMS = 5           # 이보다 적으면 창을 넓힌다(빈손보다는 낫다)
# 처음엔 3 이었는데 SATL 에서 드러났다 — 7일 안에 딱 3건이 있어서 창을 안
# 넓혔고, 그 3건이 CFO 보너스·IR 컨퍼런스 공지·옵션체인(잡음)이었다.
# 같은 달에 Merlin 위성 발사 성공, 국방·해양 계약 확대, Slingshot III 6기
# 확대가 다 있었는데 전부 가려졌다. **건수가 적다 = 그 주에 일이 없었다**
# 이므로, 적을수록 더 넓게 봐야 한다.


def fresh_news(company: str, limit: int = 8):
    """(items, window_days) — 최근 7일을 먼저 보고, 모자라면 30일로 넓힌다.

    프롬프트는 "**새로 나온** 언론보도"라고 쓰는데 창은 30일이었다. 바쁜
    종목은 티가 안 난다(PLTR·LITE·BE 는 받은 40건이 전부 7일 이내였다).
    문제는 조용한 종목이다 — CORT 는 진짜 사건인 CHMP 승인 권고가 23일 전
    것이었고, AXT 는 16건 중 7건만 7일 이내였다. 그게 "오래된 뉴스도 막
    요약한다"로 보인다.

    그래서 창을 좁히되 **빈손으로 두지는 않는다.** 넓혔으면 넓혔다고 말할
    수 있게 실제 사용한 창을 같이 돌려준다 — 호출부가 그걸 그대로 표기해야
    '새 소식'과 '이번 달 소식'이 뒤섞이지 않는다.
    """
    items = company_news(company, days=NEWS_DAYS, limit=max(limit * 3, 24))
    cut = (datetime.now(timezone.utc) - timedelta(days=NEWS_FRESH_DAYS)).strftime('%Y-%m-%d')
    recent = [n for n in items if n.get('date', '') >= cut]
    if len(recent) >= NEWS_MIN_ITEMS:
        return recent[:limit], NEWS_FRESH_DAYS
    return items[:limit], NEWS_DAYS


def _fold_insider(items: list) -> list:
    """내부자 매매 기사를 최신 1건으로 접고, 접힌 건수를 그 항목에 적어 둔다.

    버리지 않는 이유: 내부자 매도가 몰리는 것 자체가 신호다. 접는 이유: 거래
    한 건이 제목 네 개로 들어와 limit 자리를 다 먹기 때문이다(CORT 실측).
    """
    ins = [x for x in items if NEWS_INSIDER.search(x.get('title') or '')]
    if len(ins) <= NEWS_INSIDER_KEEP:
        return items
    keep = set(id(x) for x in ins[:NEWS_INSIDER_KEEP])
    ins[0]['insider_folded'] = len(ins)
    return [x for x in items
            if not NEWS_INSIDER.search(x.get('title') or '') or id(x) in keep]


# ── Gemini 요약 → 카드 데이터 ────────────────────────────────────────
IR_PROMPT = """당신은 기관 수준의 주식 애널리스트입니다. {company}({ticker})의 SEC 공시({form}, {date}) 원문입니다.
투자자용 요약 카드 데이터를 한국어로 만드세요. 순수 JSON만 출력:

{{
  "doc_title": "자료 성격 한 줄 (예: Q1 2026 실적 발표)",
  "one_liner": "이 공시의 핵심 한 문장 (60자 이내)",
  "kpis": [{{"label":"지표명(짧게)","value":"수치","delta":"YoY 변화 등 짧게","dir":"up|dn|flat"}}],
  "current": ["현재 상태 핵심 (각 70자 이내)"],
  "outlook": ["향후 전망·가이던스 (각 70자 이내)"],
  "tam": ["TAM·시장규모 관련 언급 (각 70자 이내)"],
  "notes": ["주요사항·리스크 (각 70자 이내)"],
  "news_digest": [{{"headline":"사건 한 줄(40자 이내)","so_what":"투자자에게 왜 중요한지(60자 이내)","date":"YYYY-MM-DD"}}]
}}

규칙:
- kpis: 원문에 재무 수치가 있으면 4~6개, 실적 공시가 아니라 수치가 없으면 빈 배열 [].
- current/outlook/notes 각 2~4개 (해당 내용이 없는 섹션은 빈 배열). 반드시 원문에 있는 내용만, 추측 금지.
- tam: 원문에 시장규모·TAM 언급이 명시된 경우에만. 없으면 빈 배열 [].
- 숫자는 원문 단위 그대로 ($6.1M, 21.1% 등). dir은 좋은 방향이면 up, 나쁘면 dn.
- 비현금·일회성 항목이 헤드라인을 왜곡하면 notes에 반드시 짚을 것.

news_digest 규칙 (아래 [최근 언론보도]에 대해서만 적용):
- 3~5개. 언론보도가 없으면 빈 배열 [].
- **같은 사건을 다룬 기사는 반드시 하나로 합칠 것.** 매체마다 제목을 다시 쓰기 때문에
  단어가 전혀 겹치지 않아도 같은 사건일 수 있다(예: "HEO RPO 임무 지원"과
  "위성이 로켓 잔해 27km까지 접근" 은 같은 사건). 내용으로 판단하라.
- 위 공시 요약에서 이미 다룬 내용과 겹치면 제외 — 카드 안에서 같은 말을 두 번 하지 않는다.
- 내부자 매도·매수 보도가 여러 건이면 개별 나열하지 말고 "내부자 매도 N건" 처럼 한 줄로 묶을 것.
- 주가 등락 자체("왜 오늘 올랐나")나 애널리스트 목표가 조정은 사건이 아니다 — 제외.
- so_what 은 기사 제목을 다시 쓰는 게 아니라 **그래서 뭐가 달라지는지**를 적을 것.
- ⚠️ 언론보도는 공시 원문이 아니다. news_digest 외의 다른 필드(kpis/current/outlook/tam/notes)에
  언론보도 내용을 절대 섞지 말 것 — 그 필드들은 공시 원문만 근거로 한다.

[공시 원문]
{body}

[최근 언론보도 — 공시 원문이 아님. news_digest 작성에만 사용]
{news}
"""


def summarize_filing(ticker: str, earnings_only: bool = False):
    """(card_dict, filing) 또는 (None, None). card_dict는 card.render 입력."""
    cik, company = resolve_ticker(ticker)
    if not cik:
        return None, None
    filing = latest_filing(cik, earnings_only=earnings_only)
    if not filing:
        return None, None
    body = filing_text(cik, filing)
    if len(body) < 200:
        print(f'[IR] {ticker} 본문 추출 실패')
        return None, filing
    # 뉴스는 **같은 호출**에 얹는다 — 별도 LLM 호출을 만들면 /ir 한 번에 쿼터를 2개
    # 먹는다. 제목만 넣으므로 프롬프트 증가분은 수백 토큰 수준이다.
    # 무료 정제(_news_is_junk·_news_cluster)로 먼저 줄인 뒤 넣는다.
    try:
        news = company_news(company, days=NEWS_DAYS, limit=16)
    except Exception as e:
        print(f'[IR] {ticker} 뉴스 수집 실패(요약은 계속): {e}')
        news = []
    news_text = chr(10).join(
        f"- {n['date']} [{n['source']}] {n['title']}"
        + (f" (매체 {n['echo']}곳 보도)" if n.get('echo', 1) > 1 else '')
        for n in news) or '(없음)'
    prompt = IR_PROMPT.format(company=company, ticker=ticker.upper(),
                              form=filing['form'], date=filing['date'], body=body,
                              news=news_text)
    client = analyzer._client()
    card = analyzer._parse(analyzer._generate(client, prompt).text)
    if card.get('_parse_error') or not (card.get('one_liner') or card.get('current') or card.get('notes')):
        print(f'[IR] {ticker} 요약 파싱 실패')
        return None, filing
    card.update({'ticker': ticker.upper(), 'company': company,
                 'form': filing['form'], 'date': filing['date']})
    # 요약이 실패하거나 비면 정제된 원본 헤드라인으로 폴백한다 — 뉴스 칸을
    # 통째로 비우는 것보다는 제목이라도 보여주는 편이 낫다.
    if not card.get('news_digest'):
        card['news'] = news[:5]
    return card, filing


# ── 분기별 재무 트렌드 (공시별 개별 추출 → accession 키로 캐시) ──────────
FIN_PROMPT = """당신은 재무 데이터 추출기입니다. {company}({ticker})의 SEC 공시({form}, 접수일 {date}) 원문에서
해당 공시가 다루는 회계기간의 핵심 재무 지표만 정확히 추출하세요. 순수 JSON만 출력:

{{
  "period": "회계기간 — 반드시 이 형식만 사용: 분기는 \\"Q1 2026\\" 같은 형태, 연간은 \\"FY2026\\"(공백 없이).
    다른 표현(예: \\"fiscal year ended...\\", \\"December 31, 2025\\") 금지, 위 두 형식 중 하나로 반드시 변환",
  "revenue": "총매출 — 반드시 실제 스케일로 환산해 $X.XM 또는 $X.XB 형식으로 통일 (예: $6.1M, $22.4B).
    SEC 재무제표는 흔히 '(in thousands)' 단위 테이블이라 원문 숫자가 6,107처럼 나올 수 있는데,
    이런 경우 6,107 thousand = $6.107M 로 반드시 환산할 것 — 원문 raw 숫자를 그대로 베끼지 말 것.
    범위로만 제시된 잠정치(가이던스 등, 예: \\"$3.4M~$3.8M\\")는 확정 실적이 아니므로 \\"—\\"",
  "gross_margin": "매출총이익률 %. 원문에 직접 없으면 매출총이익/매출로 계산. 불가하면 \\"—\\"",
  "operating_income": "영업이익(손실) — revenue와 동일하게 $X.XM/$X.XB로 단위 환산. 손실은 마이너스 부호",
  "fcf": "잉여현금흐름 — 단위 환산 동일 적용. 원문에 명시된 값 우선. 없으면 영업활동현금흐름-자본적지출로 계산. 둘 다 불가하면 \\"—\\"",
  "net_income": "순이익(손실) — 단위 환산 동일 적용",
  "cash": "기말 현금 및 현금성자산(단기투자 포함 시 그 값) — 단위 환산 동일 적용",
  "shares_out": "공시 시점 발행주식수 — 표지(cover page)에 보통 명시됨(예: \\"As of ... there were N shares outstanding\\"). 정수만(콤마 없이, 예: 134582901). 없으면 null"
}}

규칙: 반드시 원문 수치만 사용, 추측 금지. 해당 항목이 원문에 없으면 "—" (shares_out은 null).
모든 금액 필드는 반드시 $ + 숫자 + M 또는 B 접미사 형식만 사용 — 콤마 섞인 raw 숫자(예: "$6,107")나
단위 없는 숫자를 절대 출력하지 말 것.

[공시 원문]
{body}
"""

TREND_METRICS = [('revenue', '매출'), ('gross_margin', '총마진'), ('operating_income', '영업이익'),
                  ('fcf', 'FCF'), ('net_income', '순이익'), ('cash', '현금')]


def _parse_money(s) -> float:
    """"$6.1M"/"-$118.3M"/"22.4B"/"(4.2)"/"73.2%" 형태 문자열 → 숫자. 파싱 불가하면 None.

    %는 배수 없이 그 숫자 그대로 반환(마진 지표용) — $/M/B와 섞이지 않도록 주의해서 사용할 것.
    """
    if s is None or s == '—':
        return None
    s = str(s).replace(',', '').replace('$', '').strip()
    if not s:
        return None
    # ⚠️ 예전엔 lstrip('-(').rstrip(')') 였는데, 괄호 **뒤에 단위가 붙는** 표기를
    #    못 읽었다: '$(9.515)M' → '9.515)M' (rstrip 은 끝이 'M' 이라 ')' 를 못 뗌) → None.
    #    '($49.6M)' 는 통과하고 '$(9.515)M' 는 실패하는 비대칭이었고, 실패한 값은
    #    차트(_metric_series)에서 조용히 사라졌다(2026-09-17 SATL 영업이익에서 발견).
    #    괄호는 위치와 무관하게 음수 표시로 보고 전부 제거한다.
    neg = s.startswith('-') or '(' in s
    s = s.replace('(', '').replace(')', '').lstrip('-').rstrip('%').strip()
    mult = 1.0
    if s and s[-1] in 'BbMmKk':
        mult = {'b': 1e9, 'm': 1e6, 'k': 1e3}[s[-1].lower()]
        s = s[:-1]
    try:
        v = float(s) * mult
        return -v if neg else v
    except ValueError:
        return None


def _fmt_cell(v: float, unit: str) -> str:
    """숫자 → 추이표 한 칸. 단위는 행 전체가 공유한다(_normalize_row 가 정함).

    ⚠️ 아래쪽 _fmt_money(v) 와 헷갈리지 말 것. 그건 **값마다** 단위를 따로 골라서
       ($22,387M 옆에 $28.24B 처럼) 한 행 안에서 단위가 섞이는 원인이다.
       처음에 이 함수를 같은 이름으로 만들었다가 뒤 정의에 덮여 TypeError 가 났다.
    """
    div = {'B': 1e9, 'M': 1e6, 'K': 1e3, '': 1.0}[unit]
    x = v / div
    s = f'{abs(x):.2f}' if abs(x) < 10 else f'{abs(x):.1f}'
    return f'{"-" if v < 0 else ""}${s}{unit}'


def _normalize_row(values: list, key: str, ticker: str, label: str) -> list:
    """한 행의 값 표기를 통일한다.

    분기별 추출은 **공시 한 건씩 따로** LLM에 물어보기 때문에, 같은 행인데도
    옆 분기가 뭘로 적었는지 모른 채 각자 포맷을 고른다. 2026-09-17 실측:
      · TSLA 매출  $22.5B | $28.1B | $24.9B | **$22,387M** | $28.24B  ← 한 칸만 M
      · SATL 영업이익 $(9.515)M | $-6.3M | **-$8.082M**              ← 음수 표기 3종
    사람 눈에는 이게 "데이터가 틀렸다"로 읽힌다. 실제 숫자는 맞는데 표기만 다르다.
    그래서 FIN_PROMPT(추출 시점)에 맡기지 않고 **출력 시점에** 통일한다 —
    추출은 공시별로 독립이라 원천에서는 애초에 통일이 불가능하다.

    ⚠️ 파싱 실패값은 '—' 로 떨군다. AXTI 매출의 '$22.5M-$23.5M' 같은 **가이던스
       범위**가 확정 실적인 척 섞여 있었는데, 차트(_metric_series)는 이미 이걸
       버리고 있어서 표와 차트가 서로 다른 말을 하고 있었다. 표를 차트에 맞춘다.
       대가: 숫자인데 파서가 모르는 표기('$1.2 billion' 등)도 같이 사라진다.
       그래서 조용히 버리지 않고 로그를 남긴다.
    """
    if key == 'gross_margin':
        out = []
        for v in values:
            n = _parse_money(v)
            # '%' 없이 소수 비율(0.634)로 저장된 경우 → 63.4%. 그냥 찍으면 '0.6%' 가 되는데
            # 그건 "마진이 0.6%" 라는 **완전히 다른 사실**이라 눈치채기 어렵다.
            # '%' 가 붙어 있으면 손대지 않는다(진짜 0.5% 마진을 뻥튀기하지 않으려고).
            if n is not None and 0 < n <= 1 and '%' not in str(v):
                n *= 100
            out.append('—' if n is None else f'{n:.1f}%')
        return out
    nums = [_parse_money(v) for v in values]
    for raw, n in zip(values, nums):
        if n is None and raw != '—':
            print(f'[표기 불명] {ticker} {label}: {raw!r} → 표에서 제외')
    mag = max((abs(n) for n in nums if n is not None), default=0)
    unit = 'B' if mag >= 1e9 else 'M' if mag >= 1e6 else 'K' if mag >= 1e3 else ''
    return ['—' if n is None else _fmt_cell(n, unit) for n in nums]


def quarterly_trend(ticker: str, cik: int, company: str, n: int = 5):
    """최근 n개 분기(회계기간 중복 제거)의 표준 재무지표.

    각 공시는 accession 번호로 캐시되어 이미 처리한 분기는 재요청하지 않음.
    반환: (periods_오래된순, rows, collected) — rows=[{'label':..., 'values':[...]}],
    collected={period: raw_dict} (shares_out 등 원시값 접근용)
    """
    hist = filing_history(cik, limit=24)
    earnings = [f for f in hist if _is_earnings_form(f)]
    cache = _load_fin_cache()
    tcache = cache.setdefault(ticker, {})
    collected, order = {}, []
    for f in earnings:
        acc = f['acc']
        if acc not in tcache:
            body = filing_text(cik, f)
            if len(body) < 200:
                continue
            prompt = FIN_PROMPT.format(company=company, ticker=ticker.upper(),
                                       form=f['form'], date=f['date'], body=body)
            try:
                client = analyzer._client()
                data = analyzer._parse(analyzer._generate(client, prompt).text)
            except Exception as e:
                print(f'[분기추출 실패] {ticker} {f["form"]} {f["date"]}: {e}')
                continue
            finally:
                time.sleep(4)  # 분당 요청 한도 방어 — 캐시 안 된 분기가 여러개면 연속호출 몰림
            tcache[acc] = data
            _save_fin_cache(cache)
        data = tcache[acc]
        period = (data.get('period') or '').strip() or f['date']
        # ⚠️ 연간 합계(FY####)는 **분기** 추이 표에 섞지 않는다.
        #    _metric_series 는 이미 include_fy=False 로 같은 판단을 하고 있었는데
        #    (주석: "연간 합계는 분기 QoQ 비교에 섞으면 스케일이 달라 방향성이 왜곡됨")
        #    그 판단이 계산에만 적용되고 **사람이 보는 표에는 적용되지 않았다.**
        #    실측(2026-09-17 SATL): Q2'25 · Q3'25 · **FY2025** · Q1'26 · Q2'26 으로
        #    연간 열이 분기 사이에 끼었고, 그 열은 6행 중 4행이 '—' 였다. 매출만
        #    $17.7M 으로 찍혀 옆 분기($3.6M)의 5배라 추세를 오독하게 만든다.
        #    ⚠️ 대가: 미국은 4분기를 10-K(FY)로만 싣는 경우가 있어 Q4 열이 빠질 수 있다.
        #       값이 반쯤 빈 가짜 열보다 없는 편이 낫다고 판단했다.
        if period.upper().startswith('FY'):
            continue
        if period in collected:
            continue  # 같은 분기가 8-K·10-Q 중복 공시된 경우 최신 것만
        collected[period] = data
        order.append(period)
        if len(order) >= n:
            break
    order.reverse()  # 오래된 → 최신
    rows = [{'label': label,
             'values': _normalize_row([collected[p].get(key) or '—' for p in order],
                                      key, ticker, label)}
            for key, label in TREND_METRICS]
    # 값이 하나도 없는 열은 뺀다. FY 열을 지운 이유와 같다 — 열 제목만 있고 칸이 전부
    # 비어 있으면 "데이터가 없다"가 아니라 "봇이 고장났다"로 읽힌다.
    # 실측(2026-09-17 AXTI): 8-K 가이던스 범위($22.5M-$23.5M)만 있던 Q4 2025 는
    # 정규화에서 그 한 칸마저 떨어져 6칸 전부 '—' 인 열이 됐다.
    keep = [i for i in range(len(order))
            if any(r['values'][i] != '—' for r in rows)]
    if len(keep) < len(order):
        dropped = [order[i] for i in range(len(order)) if i not in keep]
        print(f'[빈 열 제거] {ticker}: {dropped}')
        order = [order[i] for i in keep]
        for r in rows:
            r['values'] = [r['values'][i] for i in keep]
    return order, rows, collected


def _metric_series(periods: list, collected: dict, key: str, include_fy: bool = True):
    series, labels = [], []
    for p in periods:
        if not include_fy and p.upper().startswith('FY'):
            continue  # 연간 합계는 분기 QoQ 비교에 섞으면 스케일이 달라 방향성이 왜곡됨
        v = _parse_money(collected.get(p, {}).get(key))
        if v is None:
            continue
        # 주의: 배수 기반 이상치 필터는 넣지 않음 — 실제로 SATL 순이익처럼 비현금성
        # 재평가로 진짜 30배씩 튀는 분기가 존재해서 진짜 데이터를 오탐 제거한 적 있음.
        # 단위 파싱 오류(예: "$6,107"→"천단위 raw"를 "$6.1M"로 환산 안 됨)는 FIN_PROMPT에서
        # 원천 차단(스케일 통일 지시) — 여기서 사후 필터링하지 않는다.
        series.append(v)
        labels.append(p)
    return series, labels


def compute_vectors(periods: list, collected: dict) -> dict:
    """지표별 방향성(벡터) — 최신 스칼라값이 아니라 궤적(방향+가속도)을 계산.

    QoQ·방향·궤적은 **분기만**(FY 제외) 비교해서 계산 — 연간 합계를 분기와 나란히
    비교하면 스케일이 달라 방향성이 왜곡됨. 단, series/labels 자체는 차트용으로
    FY 포함 전체를 담아 반환(막대그래프에서 FY를 다른 색으로 구분해 같이 보여줄 수 있게).

    반환: {metric_key: {'series':[숫자,...](FY포함), 'labels':[기간,...](FY포함),
                        'dir':'up'|'dn'|'flat', 'qoq_pct':최근 QoQ 변화율(%) 또는 None,
                        'trajectory':한글 설명}}
    """
    out = {}
    for key, label in TREND_METRICS:
        full_series, full_labels = _metric_series(periods, collected, key, include_fy=True)
        q_series, _ = _metric_series(periods, collected, key, include_fy=False)
        if len(q_series) < 2:
            out[key] = {'label': label, 'series': full_series, 'labels': full_labels, 'dir': 'flat',
                        'qoq_pct': None, 'trajectory': '데이터 부족'}
            continue
        qoq = []
        for i in range(1, len(q_series)):
            prev, cur = q_series[i - 1], q_series[i]
            qoq.append(None if prev == 0 else (cur - prev) / abs(prev) * 100)
        valid = [q for q in qoq if q is not None]
        latest_qoq = valid[-1] if valid else None
        direction = 'flat'
        if latest_qoq is not None:
            direction = 'up' if latest_qoq > 1 else ('dn' if latest_qoq < -1 else 'flat')
        trajectory = '데이터 부족'
        if len(valid) >= 2:
            prev_qoq, cur_qoq = valid[-2], valid[-1]
            if prev_qoq * cur_qoq < 0:
                trajectory = '방향전환'
            elif cur_qoq > prev_qoq:
                trajectory = '가속' if cur_qoq > 0 else '낙폭축소'
            elif cur_qoq < prev_qoq:
                trajectory = '둔화' if cur_qoq > 0 else '낙폭확대'
            else:
                trajectory = '일정한 흐름'
        elif len(valid) == 1:
            trajectory = '상승 전환' if valid[0] > 0 else ('하락 전환' if valid[0] < 0 else '횡보')
        out[key] = {'label': label, 'series': q_series, 'labels': [p for p in full_labels if not p.upper().startswith('FY')],
                    'dir': direction, 'qoq_pct': latest_qoq, 'trajectory': trajectory,
                    'full_series': full_series, 'full_labels': full_labels}
    return out


def valuation_snapshot(periods: list, collected: dict, price: dict):
    """최근 발행주식수 × 현재가 = 시가총액(매일 갱신), TTM 매출로 P/S 계산. 무료·결정론적, LLM 미사용.

    발행주식수는 분기마다 크게 안 변하므로 최근 공시 캐시값 재사용, 가격만 매번 새로 조회하면
    시가총액은 사실상 매일 갱신 가능 — 실적(분기)과 가격(일간) 업데이트 주기가 다를 뿐.
    """
    if not price or not periods:
        return None
    shares = None
    for p in reversed(periods):  # 최신 공시부터 shares_out 있는 걸 찾음
        v = collected.get(p, {}).get('shares_out')
        try:
            shares = float(v) if v not in (None, '', '—', 'null') else None
        except (TypeError, ValueError):
            shares = None
        if shares:
            break
    if not shares:
        return None
    market_cap = shares * price['price']
    ttm_rev, count = 0.0, 0
    for p in reversed(periods):
        d = collected.get(p, {})
        if str(d.get('period', '')).upper().startswith('FY'):
            continue  # 연간 합계는 TTM 이중계산 방지 위해 제외
        v = _parse_money(d.get('revenue'))
        if v is None:
            continue
        ttm_rev += v
        count += 1
        if count >= 4:
            break
    ps = market_cap / ttm_rev if count >= 4 and ttm_rev > 0 else None
    return {'market_cap': market_cap, 'shares_out': shares,
            'ttm_revenue': ttm_rev if count >= 4 else None, 'ps_ratio': ps}


def _fmt_money(v: float) -> str:
    if v is None:
        return '—'
    a = abs(v)
    if a >= 1e9:
        return f'{"-" if v < 0 else ""}${a/1e9:.2f}B'
    if a >= 1e6:
        return f'{"-" if v < 0 else ""}${a/1e6:.1f}M'
    return f'{"-" if v < 0 else ""}${a:,.0f}'


# ── IR 다이제스트 (/ir 명령용 — 최근 여러 공시 종합 + 분기 트렌드) ───────
DIGEST_PROMPT = """당신은 기관 수준의 주식 애널리스트입니다. {company}({ticker})의 최근 SEC 공시 자료 모음입니다({span}).
아래 주 자료와 최근 추가 공시를 종합해 투자자용 요약 카드 데이터를 한국어로 만드세요. 순수 JSON만 출력:

{{
  "doc_title": "이 다이제스트가 다루는 기간·성격 한 줄 (예: Q1 2026 실적 + 최근 주요 공시 종합)",
  "one_liner": "최근 흐름을 종합한 핵심 한 문장 (60자 이내)",
  "current": ["현재 상태 핵심 (각 70자 이내, 3~5개)"],
  "outlook": ["향후 전망·가이던스 (각 70자 이내, 2~4개)"],
  "tam": ["TAM·시장규모 관련 언급 — 원문에 명시된 경우에만, 없으면 빈 배열"],
  "notes": ["주요사항·리스크 — 실적 발표 이후 별도 공시(계약·임원변경 등)도 반영 (각 70자 이내, 2~4개)"],
  "news_digest": [{{"headline":"사건 한 줄(40자 이내)","so_what":"투자자에게 왜 중요한지(60자 이내)","date":"YYYY-MM-DD"}}]
}}

규칙: 반드시 원문에 있는 내용만, 추측 금지. 여러 문서에 걸친 정보를 종합해도 좋음.
- 아래 [최근 뉴스 헤드라인]은 제목만 있고 본문은 없음 — 헤드라인에 적힌 사실 그대로만 참고 가능,
  헤드라인에 없는 세부내용을 추측해서 채우지 말 것.

news_digest 규칙 ([최근 뉴스 헤드라인]에 대해서만 적용):
- 3~5개. 뉴스가 없으면 빈 배열 [].
- **같은 사건을 다룬 기사는 반드시 하나로 합칠 것.** 매체마다 제목을 다시 쓰기 때문에
  단어가 전혀 겹치지 않아도 같은 사건일 수 있다(예: "HEO RPO 임무 지원"과
  "위성이 로켓 잔해 27km까지 접근" 은 같은 사건). 내용으로 판단하라.
- current/outlook/notes 에서 이미 다룬 내용과 겹치면 제외 — 카드 안에서 같은 말을 두 번 하지 않는다.
- 내부자 매도·매수 보도가 여러 건이면 개별 나열하지 말고 "내부자 매도 N건" 처럼 한 줄로 묶을 것.
- 주가 등락 자체("왜 오늘 올랐나")나 애널리스트 목표가 조정은 사건이 아니다 — 제외.
- so_what 은 기사 제목을 다시 쓰는 게 아니라 **그래서 뭐가 달라지는지**를 적을 것.
- ⚠️ 뉴스는 공시 원문이 아니다. news_digest 외의 필드에 뉴스 내용을 근거로 수치를 적지 말 것.

[주 자료: {anchor_form} {anchor_date}]
{anchor_body}

[최근 추가 공시]
{extra_body}

[최근 뉴스 헤드라인]
{news_ctx}
"""


def build_digest(ticker: str, n_quarters: int = 5):
    """/ir 명령 — 최근 IR 공시+뉴스 종합 요약 + 분기 재무 트렌드. (card_dict, anchor_filing) 또는 (None, None)."""
    cik, company = resolve_ticker(ticker)
    if not cik:
        return None, None
    hist = filing_history(cik, limit=8)
    if not hist:
        return None, None
    anchor = next((f for f in hist if _is_earnings_form(f)), hist[0])
    anchor_body = filing_text(cik, anchor)
    if len(anchor_body) < 200:
        print(f'[IR 다이제스트] {ticker} 주자료 추출 실패')
        return None, anchor

    extras = [f for f in hist if f['acc'] != anchor['acc']][:3]
    extra_parts = []
    for f in extras:
        t = filing_text(cik, f)[:EXTRA_TEXT_LIMIT]
        if t:
            extra_parts.append(f'--- {f["form"]} {f["date"]} ---\n{t}')
    extra_body = '\n\n'.join(extra_parts) or '(추가 공시 없음)'
    span = f'{hist[-1]["date"]} ~ {hist[0]["date"]}' if len(hist) > 1 else anchor['date']

    # company_news 가 이미 잡음 제거·사건 묶기를 끝낸 목록을 준다(무료 단계).
    # echo=그 사건을 받아쓴 매체 수 → 모델이 주목도를 판단하는 재료로 넘긴다.
    news, win = fresh_news(company, limit=16)
    news_ctx = '\n'.join(
        f'- [{n["date"]}] {n["title"]} ({n["source"]}'
        + (f', 매체 {n["echo"]}곳 보도)' if n.get('echo', 1) > 1 else ')')
        + (f'  ※ 내부자 매매 기사 {n["insider_folded"]}건을 이 한 줄로 접음'
           if n.get('insider_folded') else '')
        for n in news) or '(최근 뉴스 없음)'
    # 창을 넓혔으면 모델에게도 알려준다. 안 그러면 3주 전 사건을 '새 소식'으로 쓴다.
    news_ctx = f'(최근 {win}일 보도)\n' + news_ctx

    prompt = DIGEST_PROMPT.format(company=company, ticker=ticker.upper(), span=span,
                                  anchor_form=anchor['form'], anchor_date=anchor['date'],
                                  anchor_body=anchor_body, extra_body=extra_body, news_ctx=news_ctx)
    client = analyzer._client()
    card = analyzer._parse(analyzer._generate(client, prompt).text)
    if card.get('_parse_error') or not (card.get('one_liner') or card.get('current')):
        print(f'[IR 다이제스트] {ticker} 요약 파싱 실패')
        return None, anchor

    time.sleep(3)  # 분당 요청 한도 방어
    periods, trend_rows, _ = quarterly_trend(ticker, cik, company, n=n_quarters)
    card.update({'ticker': ticker.upper(), 'company': company, 'form': anchor['form'], 'date': anchor['date'],
                 'trend': {'periods': periods, 'rows': trend_rows} if periods else None})
    # news_digest 가 나오면 그걸 쓰고, 실패했을 때만 정제된 헤드라인으로 떨어진다.
    # 예전엔 'news' 를 항상 넣었는데, 이제 카드가 digest 를 우선 렌더하므로
    # 둘 다 넣어두면 어느 쪽이 나갈지 코드만 봐서는 알 수 없다. 여기서 못박는다.
    if not card.get('news_digest'):
        card['news'] = news[:5]
    return card, anchor


def filing_url(ticker: str, filing: dict) -> str:
    cik, _ = resolve_ticker(ticker)
    acc = filing['acc'].replace('-', '')
    return f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{filing["primary"]}'


YF_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
_DAILY_CACHE = {}


def _daily_rows(ticker: str):
    """최근 6개월 일봉 [(ts, o, h, l, c, v)] — 한 실행 안에서는 종목당 1회만 받는다."""
    if ticker in _DAILY_CACHE:
        return _DAILY_CACHE[ticker]
    rows = []
    try:
        r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}',
                         params={'range': '6mo', 'interval': '1d'}, headers={'User-Agent': YF_UA}, timeout=15)
        res = r.json()['chart']['result'][0]
        q = res['indicators']['quote'][0]
        for k, ts in enumerate(res['timestamp']):
            c = q['close'][k]
            if c is None:
                continue
            rows.append((ts, q['open'][k] or c, q['high'][k] or c, q['low'][k] or c, c, q['volume'][k] or 0))
    except Exception as e:
        print(f'[일봉 실패] {ticker}: {e}')
    _DAILY_CACHE[ticker] = rows
    return rows


MOVE_PCT = 10      # 뉴스가 '잡음뿐'이어도 알릴 만한 하루 등락
MOVE_VOL = 2.0     # 그때 거래량이 50일 평균의 몇 배 이상이어야 하나


def price_reaction(ticker: str, since: datetime):
    """지난 요약 이후 주가 반응 — 오닐('뉴스는 가격·거래량으로 확인될 때만 의미')·이선엽('반등의 질:
    장 마감까지 유지되나') 관점. 반환 dict 또는 None.

      chg       지난 요약 직전 종가 → 최근 종가 (%)
      big       기간 중 가장 크게 움직인 날: {'date','ret','vol_x','gap','held'}
                held = 그날 종가가 고가·저가 범위의 위쪽 40% 안이면 True(마감까지 유지)
      notable   |ret| ≥ MOVE_PCT 이고 거래량 ≥ MOVE_VOL 배
    """
    rows = _daily_rows(ticker)
    if len(rows) < 30:
        return None
    cut = since.timestamp()
    before = [r for r in rows if r[0] < cut]
    after = [(i, r) for i, r in enumerate(rows) if r[0] >= cut]
    if not before or not after:
        return None
    base = before[-1][4]
    last = rows[-1][4]
    first_i = after[0][0]
    vols = [r[5] for r in rows[max(0, first_i - 50):first_i] if r[5]]
    v50 = sum(vols) / len(vols) if vols else 0
    big = None
    for i, r in after:
        prev = rows[i - 1][4] if i > 0 else r[1]
        ret = (r[4] / prev - 1) * 100 if prev else 0
        if big is None or abs(ret) > abs(big['ret']):
            rng = r[2] - r[3]
            pos = (r[4] - r[3]) / rng if rng else 0.5
            big = {'date': datetime.fromtimestamp(r[0], timezone.utc).strftime('%m/%d'), 'ret': ret,
                   'vol_x': (r[5] / v50) if v50 else None, 'gap': (r[1] / prev - 1) * 100 if prev else 0,
                   'held': pos >= 0.6 if ret > 0 else pos <= 0.4}
    notable = bool(big and abs(big['ret']) >= MOVE_PCT and (big['vol_x'] or 0) >= MOVE_VOL)
    return {'chg': (last / base - 1) * 100, 'big': big, 'notable': notable}


# ── 회사 개요 (처음 보는 기업용 — 사업 설명 + 세그먼트별 매출 비중) ────────
PROFILE_PROMPT = """당신은 기업 개황 요약가입니다. {company}({ticker})의 연차보고서(10-K/20-F) 원문에서
이 회사를 처음 접하는 투자자가 알아야 할 기본 정보만 뽑아 한국어로 정리하세요. 순수 JSON만 출력:

{{
  "business": "이 회사가 어떤 사업을 하는지 2~3문장 — 전문용어 최소화, 처음 보는 사람 기준으로 쉽게",
  "segments": [{{"name": "사업부문명", "pct": 매출 비중 숫자(0~100), 없으면 null}}],
  "founded_hq": "설립연도·본사 위치 — 원문에 있으면, 없으면 빈 문자열"
}}

규칙:
- segments: 원문의 사업부문별 매출 breakdown(세그먼트 보고 각주 등)을 최대한 활용.
  세그먼트 구분이 없는 단일사업 기업이면 빈 배열 []로 두고 business에서 그 사실을 설명할 것.
- 정확한 비중 숫자가 없으면 세그먼트 이름만 나열하고 pct는 null.
- 반드시 원문에 있는 내용만 사용, 추측 금지.

[연차보고서 원문]
{body}
"""


def company_profile(ticker: str, cik: int, company: str):
    """회사 개요 — 최근 10-K/20-F 기준. accession으로 캐시되어 같은 연차보고서면 재추출 안 함."""
    hist = filing_history(cik, limit=24)
    annual = next((f for f in hist if f['form'] in ('10-K', '20-F')), None)
    if not annual:
        return None
    cache = _load_json_cache(PROFILE_CACHE_PATH)
    tcache = cache.setdefault(ticker, {})
    if annual['acc'] in tcache:
        return tcache[annual['acc']]
    body = filing_text(cik, annual)
    if len(body) < 200:
        print(f'[회사개요] {ticker} 연차보고서 본문 추출 실패')
        return None
    prompt = PROFILE_PROMPT.format(company=company, ticker=ticker.upper(), body=body)
    try:
        client = analyzer._client()
        data = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[회사개요 실패] {ticker}: {e}')
        return None
    if data.get('_parse_error') or not data.get('business'):
        print(f'[회사개요] {ticker} 파싱 실패')
        return None
    tcache[annual['acc']] = data
    _save_json_cache(PROFILE_CACHE_PATH, cache)
    return data


# ── 어닝콜 하이라이트 (Motley Fool 무료 전문 — 티커로 URL 자동탐색) ──────
FOOL_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'


def _find_transcript_url(ticker: str):
    """종목 페이지에 임베드된 JSON에서 최신 어닝콜 transcript 경로 탐색. nasdaq→nyse 순 시도."""
    for exch in ('nasdaq', 'nyse'):
        try:
            r = requests.get(f'https://www.fool.com/quote/{exch}/{ticker.lower()}/',
                             headers={'User-Agent': FOOL_UA}, timeout=15)
            if r.status_code != 200:
                continue
            m = re.search(r'\\"path\\":\\"(/earnings/call-transcripts/[^\\"]+)\\"', r.text)
            if m:
                return 'https://www.fool.com' + m.group(1)
        except Exception as e:
            print(f'[어닝콜 URL탐색 실패] {ticker}/{exch}: {e}')
    return None


def _fool_transcript_text(url: str) -> str:
    """페이지 chrome(내비·광고·관련기사)를 걷어내고 실제 통화 본문만 추출."""
    r = requests.get(url, headers={'User-Agent': FOOL_UA}, timeout=30)
    txt = _strip_html(r.text)
    start = txt.find('Welcome to')
    if start < 0:
        start = 0
    end = txt.find('Motley Fool Transcribing')  # 최초 출현 = 실제 본문 직후 "Read Next" 블록 시작
    if end < 0 or end <= start:
        end = len(txt)
    return txt[start:end].strip()


TRANSCRIPT_PROMPT = """당신은 기관 애널리스트입니다. {company}({ticker})의 최근 실적발표 어닝콜(컨퍼런스콜) 전문입니다.
경영진(CEO·CFO 등)이 직접 언급한 내용 중 투자자가 알아야 할 핵심만 뽑아 한국어로 정리하세요. 순수 JSON만 출력:

{{
  "highlights": ["경영진 발언 기반 핵심 포인트 — 가이던스·전략방향·주요 코멘트 (각 80자 이내, 3~5개)"],
  "qna_notable": ["Q&A에서 나온 의미있는 질문/답변 요지 — 없으면 빈 배열 (각 80자 이내, 0~3개)"],
  "tone": "경영진 어조 한 줄 — 자신감/신중/방어적 등, 근거가 되는 표현과 함께"
}}

규칙: 반드시 원문에 실제로 언급된 내용만, 추측 금지. 원문에 없으면 각 배열을 비워둘 것.

[어닝콜 전문]
{body}
"""


def earnings_transcript(ticker: str, company: str):
    """최신 어닝콜 하이라이트. (data, url) 또는 (None, None) — 커버리지 없거나 아직 미발행이면 조용히 None.

    URL 단위로 캐시 — 같은 분기 재조회 시 재호출 안 함.
    """
    url = _find_transcript_url(ticker)
    if not url:
        return None, None
    cache = _load_json_cache(TRANSCRIPT_CACHE_PATH)
    tcache = cache.setdefault(ticker, {})
    if url in tcache:
        return tcache[url], url
    try:
        body = _fool_transcript_text(url)
    except Exception as e:
        print(f'[어닝콜] {ticker} 본문 추출 실패: {e}')
        return None, url
    if len(body) < 500:
        return None, url
    prompt = TRANSCRIPT_PROMPT.format(company=company, ticker=ticker.upper(), body=body[:TEXT_LIMIT])
    try:
        client = analyzer._client()
        data = analyzer._parse(analyzer._generate(client, prompt).text)
    except Exception as e:
        print(f'[어닝콜] {ticker} 요약 실패: {e}')
        return None, url
    if data.get('_parse_error'):
        return None, url
    tcache[url] = data
    _save_json_cache(TRANSCRIPT_CACHE_PATH, cache)
    return data, url


_WIKI_UA = 'buza-alarm-bot/1.0 (https://github.com/; contact via Telegram @buza_alarm_bot) requests/python'
_WIKI_ICON_SKIP = re.compile(
    r'oojs|commons-logo|wiktionary|wikidata|edit-|question_book|padlock|folder|ambox|'
    r'flag_of|symbol_|disambig|wiki_letter|semi-protection|nuvola|crystal_clear',
    re.I)


def company_logo(ticker: str, company: str):
    """위키피디아에서 로고 이미지를 찾아 로컬에 캐시하고 경로를 반환. 못 찾으면 None
    (report.py가 모노그램 배지로 대체)."""
    LOGO_DIR.mkdir(exist_ok=True)
    cached = list(LOGO_DIR.glob(f'{ticker.upper()}.*'))
    if cached:
        return str(cached[0])
    try:
        s = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'list': 'search', 'srsearch': company, 'format': 'json', 'srlimit': 1,
        }, headers={'User-Agent': _WIKI_UA}, timeout=15).json()
        hits = s.get('query', {}).get('search', [])
        if not hits:
            return None
        title = hits[0]['title']

        filename = None
        p = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'titles': title, 'prop': 'pageimages', 'piprop': 'name', 'format': 'json',
        }, headers={'User-Agent': _WIKI_UA}, timeout=15).json()
        pages = p.get('query', {}).get('pages', {})
        for pg in pages.values():
            if pg.get('pageimage'):
                filename = 'File:' + pg['pageimage']
                break

        if not filename:
            im = requests.get('https://en.wikipedia.org/w/api.php', params={
                'action': 'query', 'titles': title, 'prop': 'images', 'imlimit': 20, 'format': 'json',
            }, headers={'User-Agent': _WIKI_UA}, timeout=15).json()
            candidates = []
            for pg in im.get('query', {}).get('pages', {}).values():
                for img in pg.get('images', []):
                    if not _WIKI_ICON_SKIP.search(img['title']):
                        candidates.append(img['title'])
            # 일반 포털/토픽 아이콘(예: RocketSunIcon.svg)도 스킵 필터를 통과하는 경우가 있어서,
            # 파일명에 "logo"나 회사명이 들어간 것을 최우선으로 고른다 — 아니면 첫 후보로 폴백.
            name_tokens = [w.lower() for w in re.split(r'\W+', company) if len(w) > 2]
            def _score(fname):
                low = fname.lower()
                if 'logo' in low:
                    return 2
                if any(tok in low for tok in name_tokens):
                    return 1
                return 0
            candidates.sort(key=_score, reverse=True)
            if candidates:
                filename = candidates[0]

        if not filename:
            return None

        fname = filename.split(':', 1)[1].replace(' ', '_')
        thumb = requests.get(f'https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(fname)}',
                             params={'width': 300}, headers={'User-Agent': _WIKI_UA}, timeout=15)
        if thumb.status_code != 200 or not thumb.content:
            return None
        ext = '.png' if 'png' in thumb.headers.get('content-type', '') else '.jpg'
        path = LOGO_DIR / f'{ticker.upper()}{ext}'
        path.write_bytes(thumb.content)
        return str(path)
    except Exception as e:
        print(f'[로고 실패] {ticker}: {e}')
        return None


# ── 감시 체크 (크론) ─────────────────────────────────────────────────


# ── 뉴스 푸시 계측 ───────────────────────────────────────────────────
# ⚠️ 이게 없어서 "뉴스 요약이 실제로 나갔는지, 폴백으로 링크만 나갔는지"를
#    사후에 알 방법이 없었다(2026-09-22 자가점검에서 드러남). seen_news 가 변한 걸로
#    '경로가 돌았다'까지만 알 수 있었고 결과는 몰랐다.
#    CARRIED_OVER 때 "남기기만 하고 아무도 안 보면 안 남긴 것과 같다"고 적어놓고
#    정작 새 기능엔 아예 안 남긴 셈이라, 같은 실수를 반복하지 않으려고 붙인다.
NEWS_LOG_PATH = Path(__file__).parent / 'news_log.json'
NEWS_LOG_KEEP = 200


def note_news(rec: dict):
    """뉴스 푸시 한 건의 결과를 남긴다. 실패해도 본 흐름을 막지 않는다."""
    try:
        log = _load_json_cache(NEWS_LOG_PATH)
        if not isinstance(log, list):
            log = log.get('items', []) if isinstance(log, dict) else []
        rec = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), **rec}
        log.append(rec)
        NEWS_LOG_PATH.write_text(json.dumps(log[-NEWS_LOG_KEEP:], ensure_ascii=False, indent=1),
                                 encoding='utf-8')
    except Exception as e:
        print(f'[뉴스 로그 기록 실패] {e}')


def news_log(days: int = 7) -> list:
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        log = json.loads(NEWS_LOG_PATH.read_text(encoding='utf-8')) if NEWS_LOG_PATH.exists() else []
    except Exception:
        return []
    return [r for r in log if isinstance(r, dict) and str(r.get('at', '')) >= cut]

# ── 감시 푸시용 뉴스 요약 ────────────────────────────────────────────
NEWS_ONLY_PROMPT = """당신은 주식 애널리스트입니다. {company}({ticker}) 관련 **새로 나온** 언론보도 목록입니다.
투자자가 이 종목을 들고 있다고 할 때, 알아야 할 것만 추려주세요. 순수 JSON만 출력:
**headline·so_what·skip_reason 은 반드시 {lang_name}로 쓸 것** (회사명·티커·고유명사는 원문 표기 유지).

{{
  "digest": [{{"headline":"사건 한 줄(짧게, 한국어 기준 40자 분량)","so_what":"그래서 뭐가 달라지는지(한국어 기준 60자 분량)","date":"YYYY-MM-DD","src":[근거 기사 번호],"followup":false}}],
  "skip_reason": "추릴 게 없으면 그 이유 한 줄, 있으면 빈 문자열"
}}

규칙:
- 최대 4개. 중요한 게 없으면 digest=[] 로 두고 skip_reason 을 적어라 — 억지로 채우지 말 것.
- **중요도 순으로 고르고 정렬할 것**(2026-10-24 실측: TSLA 'SpaceX 합병 협상·3분기 실적' 기사를 두고
  '호주 사이버트럭 철수'를 1번으로 올렸다):
    1순위 실적 발표·가이던스·실적 발표 예정일 · 합병/인수/분할 · 대형 계약·수주 · 증자·자사주·배당
    2순위 규제·소송·리콜·경영진 변화 · 신제품·생산 계획 변경
    3순위 그 밖의 사업 소식. 행사·사회공헌·추도식·업계 일반론·'주목할 종목' 류는 넣지 말 것.
  'Key facts'·'요약' 류 제목에 1순위 사건이 섞여 있으면 그 사건을 꺼내 쓴다.
- 각 항목의 "src" 에 근거가 된 기사 번호(목록의 [n])를 적어라. 합친 사건이면 여러 개.
- so_what 은 **기사 제목·요약에 있는 사실에서 바로 따라나오는 것만**. 근거 없는 전망
  ("~기대", "~전략입니다", "경쟁력 강화")은 쓰지 말 것. 따라나오는 게 없으면 so_what 을 빈 문자열로.
- **같은 사건을 다룬 기사는 하나로 합칠 것.** 매체마다 제목을 다시 쓰기 때문에 단어가
  겹치지 않아도 같은 사건일 수 있다. 내용으로 판단하라.
- 제목만 있고 본문은 없다. **제목에 적힌 사실 그대로만** 쓰고 세부를 추측해 채우지 말 것.
- 주가 등락 자체("왜 올랐나")·애널리스트 목표가 조정·내부자 매매 개별 건은 사건이 아니다.
  내부자 매매가 여러 건이면 "내부자 매도 N건"으로 한 줄만.
- 숫자가 제목에 있으면 그대로 옮기되, 회사 규모에 비해 터무니없으면 빼라.
- so_what 은 제목을 바꿔 쓰는 게 아니라 **보유자 관점에서 뭐가 달라지는지**를 적어라.
- 목록 맨 위에 적힌 기간이 7일보다 길면 **오래된 소식이 섞여 있다는 뜻**이다.
  그런 항목은 date 를 반드시 적고, 지금 막 일어난 일처럼 쓰지 말 것.

{known_block}{thesis_block}[보도 목록]
{items}
"""


KNOWN_BLOCK = """[이미 알린 사건 — 같은 사건이면 다시 쓰지 말 것]
{known}
- 위 사건을 다른 매체가 다시 쓴 기사는 넣지 않는다.
- 단, 그 사건에 **새 사실**(숫자 변경·확정·철회·후속 조치)이 있으면 넣고 "followup": true 로 표시하고,
  headline 에 무엇이 새로운지 쓴다.

"""


THESIS_BLOCK = """[보유자가 적어 둔 투자 근거 — 판단 기준으로만 쓸 것]
{thesis}
- 각 digest 항목에 "thesis" 키를 넣어라: 이 사건이 위 근거를 뒷받침하면 "지지", 근거를 약화·반박하면 "반대",
  상관없으면 "무관". 근거에 적힌 '깨지는 조건'에 해당하면 반드시 "반대".
- 매수·매도를 권하지 말 것. 근거와의 관계만 표시한다.

"""


def _norm_title(t: str) -> str:
    return re.sub(r'[^0-9a-z가-힣]+', '', (t or '').lower())


def _enrich_snippets(ticker: str, events: list):
    """구글뉴스 RSS 는 제목뿐이라 요약이 제목 바꿔쓰기·추측이 됐다(2026-10-24 실측). 미국 종목은
    야후 파이낸스 종목 RSS 의 기사 요약문(description)을 제목이 같은 기사에 붙인다. LLM 0콜."""
    if is_kr(ticker) or not events:
        return
    r = requests.get('https://feeds.finance.yahoo.com/rss/2.0/headline',
                     params={'s': ticker.upper(), 'region': 'US', 'lang': 'en-US'},
                     headers={'User-Agent': NEWS_UA}, timeout=12)
    if r.status_code != 200:
        return
    import html as _h
    snip = {}
    for it in re.findall(r'<item>(.*?)</item>', r.text, re.S):
        ti = re.search(r'<title>(.*?)</title>', it, re.S)
        de = re.search(r'<description>(.*?)</description>', it, re.S)
        if ti and de:
            d = re.sub(r'<[^>]+>', '', _h.unescape(_h.unescape(de.group(1)))).strip()
            if d:
                snip[_norm_title(_h.unescape(ti.group(1)))] = d[:280]
    for n in events:
        k = _norm_title(n.get('title', '').rsplit(' - ', 1)[0])
        hit = snip.get(k) or next((v for t, v in snip.items() if len(k) > 20 and (k[:40] in t or t[:40] in k)), None)
        if hit:
            n['snippet'] = hit


def summarize_news(ticker: str, company: str, events: list, lang: str = 'ko', thesis: str = '',
                   known: list = None, filed: list = None):
    """새 뉴스 묶음 → [{'headline','so_what','date'}]. 실패하면 None(호출부가 링크로 폴백).

    ⚠️ 호출 1회를 쓴다. 제목만 넣으므로 수백 토큰 수준이고, **새 사건이 있을 때만**
       부른다. 감시 1종목·6시간 주기면 하루 최대 4회다.
       실패·쿼터소진이면 None 을 돌려 원래의 링크 목록으로 떨어진다 — 요약을 못 한다고
       뉴스 자체가 사라지면 안 된다.
    """
    if not events:
        return None
    t0 = time.time()
    dates = [n.get('date', '') for n in events if n.get('date')]
    span = 0
    if dates:
        try:
            span = (datetime.now(timezone.utc).date()
                    - datetime.strptime(min(dates), '%Y-%m-%d').date()).days
        except Exception:
            span = 0
    try:
        _enrich_snippets(ticker, events)
    except Exception as e:
        print(f'  [{ticker}] 기사 요약문 보강 실패(제목만으로 진행): {e}')
    lines = f'(최근 {max(span, 1)}일 보도)' + chr(10) + chr(10).join(
        f'[{i}] ({n.get("date","")}) {n.get("title","")} ({n.get("source","")}'
        + (f', 매체 {n["echo"]}곳 보도)' if n.get('echo', 1) > 1 else ')')
        + (f'  ※ 내부자 매매 기사 {n["insider_folded"]}건을 이 한 줄로 접음'
           if n.get('insider_folded') else '')
        + (chr(10) + f'    요약: {n["snippet"]}' if n.get('snippet') else '')
        for i, n in enumerate(events, 1))
    import prefs
    kn = [f'- (지난 요약) {k}' for k in (known or [])][-12:] + [f'- (공시 알림) {f}' for f in (filed or [])][-8:]
    prompt = NEWS_ONLY_PROMPT.format(company=company, ticker=ticker.upper(), items=lines,
                                     lang_name=prefs.LANGS.get(lang, prefs.LANGS['en']),
                                     known_block=KNOWN_BLOCK.format(known=chr(10).join(kn)) if kn else '',
                                     thesis_block=THESIS_BLOCK.format(thesis=thesis) if thesis else '')
    try:
        client = analyzer._client()
        resp = analyzer._generate(client, prompt)
        data = analyzer._parse(resp.text)
        model = getattr(resp, 'model_version', '?')
    except Exception as e:
        print(f'  [{ticker}] 뉴스 요약 실패(링크로 발송): {e}')
        note_news({'ticker': ticker, 'events': len(events), 'result': 'error',
                   'why': str(e)[:120], 'sec': round(time.time() - t0, 1)})
        return None
    if data.get('_parse_error'):
        print(f'  [{ticker}] 뉴스 요약 파싱 실패(링크로 발송)')
        note_news({'ticker': ticker, 'events': len(events), 'result': 'parse_error',
                   'model': model, 'sec': round(time.time() - t0, 1)})
        return None
    digest = data.get('digest') or []
    # 기계적 2차 방어 — LLM 이 '이미 알린 사건'을 그대로 다시 낸 경우(후속 표시 없이) 뺀다
    if known:
        kt = [(_news_tokens(k, company), _num_sig(k)) for k in known]
        keep = []
        for d in digest:
            if d.get('followup'):
                keep.append(d)
                continue
            ht, hn = _news_tokens(d.get('headline', ''), company), _num_sig(d.get('headline', ''))
            dup = any((hn and (hn & kn_)) or (len(ht & kt_) >= 2 and len(ht & kt_) / max(1, min(len(ht), len(kt_))) >= 0.6)
                      for kt_, kn_ in kt)
            if dup:
                print(f'  [{ticker}] 이미 알린 사건 제외: {d.get("headline", "")[:40]}')
            else:
                keep.append(d)
        digest = keep
    for d in digest:   # 근거 기사 번호 → 링크(헤드라인을 그 기사로 연결)
        idx = [int(x) for x in (d.get('src') or []) if str(x).isdigit() and 1 <= int(x) <= len(events)]
        d['links'] = [events[i - 1]['link'] for i in idx if events[i - 1].get('link')]
    if not digest and data.get('skip_reason'):
        print(f'  [{ticker}] 요약할 만한 뉴스 없음: {data["skip_reason"]}')
    note_news({'ticker': ticker, 'lang': lang, 'events': len(events), 'result': 'ok' if digest else 'empty',
               'digest': len(digest), 'model': model, 'sec': round(time.time() - t0, 1),
               'why': (data.get('skip_reason') or '')[:120]})
    return digest

def check_watches(send_card, send_news=None):
    """신규 공시 감시 — 6시간 게이트 안에서 돈다. 공시는 시각을 기다릴 이유가 없어 바로 보낸다.

    뉴스는 2026-10-20 부터 여기서 하지 않는다 → deliver_news (사용자별 시각·언어).
    send_news 인자는 옛 호출부 호환용으로만 남겨 둔다.
    """
    st = load_state()
    tickers = sorted({t for lst in st['watches'].values() for t in lst if not is_kr(t)})
    if tickers:
        print(f'🔎 IR 공시 감시 {len(tickers)}종목')
    for t in tickers:
        watchers = [int(c) for c, lst in st['watches'].items() if t in lst]
        cik, company = resolve_ticker(t)
        try:
            hist = filing_history(cik, limit=24)
            if not hist or hist[0]['acc'] == st['seen'].get(t):
                continue
            # 2026-10-21: 예전엔 '최신 1건'만 비교해, 6시간 사이에 공시가 2건 나오면 앞의 것이 빠졌다.
            # 기준선 이후 전부를 모아 최신 1건은 카드로, 나머지는 같은 메시지에 목록으로 단다.
            accs = [f['acc'] for f in hist]
            seen = st['seen'].get(t)
            new = hist[:accs.index(seen)] if seen in accs else hist[:1]
            print(f'  [{t}] 신규 공시 {len(new)}건 — 최신 {new[0]["form"]} {new[0]["date"]}')
            ok = deliver(st, t, new[0]['acc'], watchers,
                         lambda c, fails: send_card(c, t, also=new[1:], quiet=True,
                                                    text_only=fails >= DLV_MAX_FAILS))
            if ok:
                st['seen'][t] = new[0]['acc']
                for f in new[:6]:
                    its = ' · '.join(SEC_8K_ITEMS.get(x.strip(), '') for x in str(f.get('items') or '').split(',') if SEC_8K_ITEMS.get(x.strip()))
                    note_filed(st, t, f"{f.get('form', '')} {f.get('date', '')} {its}".strip())
            save_state(st)
        except Exception as e:
            print(f'  [{t}] 공시 체크 실패: {e}')
            WATCH_ERRORS.append(f'US {t}: {str(e)[:60]}')


# ── 감시 뉴스: 사용자별 하루 1번 ─────────────────────────────────────
# 2026-10-20 재설계. 예전 방식의 결함 둘(실측 2026-10-19):
#   ① '새 뉴스' = 30일 창 안에서 기준선(상위 15건 링크)에 없는 것. 기준선을 매번 덮어써서
#      순위 밖으로 밀렸다 돌아온 옛 기사를 다시 보냈다(기준선 변경 78회 중 58회에 재등장).
#   ② LLM 이 '중요한 것 없음'(digest=[])이라 판정해도 링크만 달아 그대로 보냈다(55건 중 22건).
# 지금 방식:
#   · 기준은 **시각**이다. (사용자, 종목)마다 '마지막으로 처리한 시각(mark)'만 둔다.
#     다음 실행은 그 뒤에 발행된 기사만 본다. 같은 곳을 같은 방법으로 검색하므로
#     그 이전 발행분은 이미 처리했다.
#   · 구글 뉴스는 기사를 늦게 색인하기도 해서(발행 10시 → 검색 노출 15시) mark 에서 정확히
#     자르면 그런 기사가 영영 빠진다. NEWS_OVERLAP_H 만큼 겹쳐 보고, **겹친 구간에서만**
#     이미 보낸 기사(sent)를 뺀다. sent 는 겹침 구간 밖으로 나가면 지운다 — 쌓이지 않는다.
#   · 사용자 시간대의 설정 시각이 지났고 오늘 아직 안 받았으면 보낸다(prefs.hour_reached).
#   · digest=[] 면 보내지 않는다. 요약 실패(None)면 mark 를 안 옮기고 다음 실행에 재시도,
#     같은 날 NEWS_MAX_FAILS 번 실패하면 그때만 링크로 보낸다.
NEWS_OVERLAP_H = 12
NEWS_FIRST_LOOKBACK_H = 24     # mark 가 없을 때(기존 감시 종목) 처음 볼 범위
NEWS_MAX_LOOKBACK_D = 7        # 오래 못 받았어도 이보다 옛 것은 '새 뉴스'로 안 친다
NEWS_MAX_FAILS = 3


def _iso(s):
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def news_window(rec: dict, now: datetime):
    """(since, exclude) — 이번에 볼 발행 시각 하한과, 겹침 구간에서 이미 보낸 것."""
    mark = _iso(rec.get('mark') or '') or (now - timedelta(hours=NEWS_FIRST_LOOKBACK_H))
    mark = max(mark, now - timedelta(days=NEWS_MAX_LOOKBACK_D))
    since = mark - timedelta(hours=NEWS_OVERLAP_H)
    exclude = {k for k, ts in (rec.get('sent') or {}).items() if (_iso(ts) or now) >= since}
    return since, exclude


def _after_delivery(rec: dict, items: list, now: datetime, day: str):
    """mark 를 옮기고, 다음 겹침 구간에 걸릴 수 있는 것만 sent 에 남긴다."""
    nxt_since = now - timedelta(hours=NEWS_OVERLAP_H)
    sent = {k: ts for k, ts in (rec.get('sent') or {}).items() if (_iso(ts) or now) >= nxt_since}
    for it in items:
        ts = it.get('ts') or now.isoformat()
        for l in (it.get('links') or [it['link']]):
            sent[l] = ts
        sent['t:' + it['title'].lower()] = ts
    sent = {k: ts for k, ts in sent.items() if (_iso(ts) or now) >= nxt_since}
    rec.update(mark=now.isoformat(timespec='seconds'), slot=day, day=day[:10], sent=sent, fails=0)


def deliver_news(send_news, now: datetime = None) -> int:
    """설정 시각이 된 사용자에게 감시 종목 뉴스 요약을 보낸다. 매 크론 실행마다 부른다.
    보낸 메시지 수를 돌려준다. 시각이 안 된 사용자는 네트워크도 LLM 도 안 쓴다."""
    import prefs
    now = now or datetime.now(timezone.utc)
    st = load_state()
    nst = st.setdefault('news', {})
    cache = {}       # (종목, 언어, 기사 묶음) → digest. 같은 걸 받는 사용자끼리 LLM 1회 공유
    sent_msgs = 0
    for chat, tickers in st['watches'].items():
        p = prefs.get(chat)
        if not tickers:
            continue
        # 회차(slot) = 'YYYY-MM-DD@HH'. 2026-10-21 하루 1번 → 12시간마다로 바꾸며 'day' 대신 쓴다.
        day = prefs.current_slot(p, now)
        for t in tickers:
            rec = nst.setdefault(chat, {}).setdefault(t, {})
            if rec.get('slot') == day:
                continue
            # 전환 첫날: 예전 방식으로 오늘 설정 시각 회차를 이미 받았으면 같은 회차로 친다(중복 발송 방지)
            if not rec.get('slot') and rec.get('day') == day[:10] and int(day[11:]) == int(p.get('hour', 8)):
                rec['slot'] = day
                continue
            cik, company = watch_company(t)
            if not company:
                continue
            since, exclude = news_window(rec, now)
            try:
                items = company_news(company, limit=NEWS_DIGEST_LIMIT, since=since, exclude=exclude,
                                     locales=NEWS_LOCALES_KR if is_kr(t) else None, rank=True)
            except Exception as e:
                print(f'  [{t}] 뉴스 수집 실패({chat}): {e}')
                continue
            if not items:
                print(f'  [{t}] {chat} 새 뉴스 0건 — 보낼 것 없음')
                _after_delivery(rec, [], now, day)
                save_state(st)
                continue
            th = ''   # /thesis 는 2026-10-21 제거(사용 0건). 요약 프롬프트의 근거 칸은 비워 둔다.
            # 근거가 있는 사용자는 요약을 따로 만든다(근거마다 판단이 달라서). 없으면 같은 언어끼리 공유.
            known = [e['h'] for e in (rec.get('events') or []) if (_iso(e.get('ts', '')) or now) >= now - timedelta(days=NEWS_EVENT_MEMORY_D)]
            filed = [f['t'] for f in (st.get('filed', {}).get(t) or []) if (_iso(f.get('ts', '')) or now) >= now - timedelta(days=3)]
            key = (t, p['lang'], th, tuple(sorted(i['link'] for i in items)), tuple(known), tuple(filed))
            digest = cache[key] if key in cache else summarize_news(t, company, items, lang=p['lang'], thesis=th,
                                                                  known=known, filed=filed)
            if digest is not None:
                cache[key] = digest
            if digest is None:
                rec['fails'] = (rec.get('fails', 0) + 1) if rec.get('fail_day') == day else 1
                rec['fail_day'] = day
                if rec['fails'] < NEWS_MAX_FAILS:
                    print(f'  [{t}] {chat} 요약 실패 {rec["fails"]}회 — 다음 실행에 재시도')
                    save_state(st)
                    continue
                print(f'  [{t}] {chat} 요약 {rec["fails"]}회 실패 — 링크로 보냄')
            mark_dt = _iso(rec.get('mark') or '') or (now - timedelta(hours=NEWS_FIRST_LOOKBACK_H))
            try:
                react = price_reaction(t, mark_dt)
            except Exception as e:
                print(f'  [{t}] 주가 반응 계산 실패: {e}')
                react = None
            if is_kr(t):
                # 한국은 '누가 샀나'가 가격만큼 말해준다(외국인·기관 수급). 실패해도 요약은 보낸다.
                try:
                    fl = kr_flow(t, since=mark_dt)
                    if fl:
                        react = dict(react or {}, flow=fl)
                except Exception as e:
                    print(f'  [{t}] 수급 조회 실패: {e}')
            if digest == []:
                # 잡음뿐이어도 주가가 거래량을 동반해 크게 움직였으면 알린다 — 뉴스가 없는 큰 움직임이
                # 오히려 더 봐야 할 신호다(오닐: 가격·거래량이 먼저 말한다).
                if react and react.get('notable'):
                    if send_news(int(chat), t, items, [], lang=p['lang'], reaction=react):
                        sent_msgs += 1
                        _after_delivery(rec, items, now, day)
                        save_state(st)
                    continue
                print(f'  [{t}] {chat} {len(items)}건 모두 잡음 — 보내지 않음')
                note_news({'ticker': t, 'stage': 'skip', 'events': len(items)})
                _after_delivery(rec, items, now, day)
                save_state(st)
                continue
            if send_news(int(chat), t, items, digest, lang=p['lang'], reaction=react):
                sent_msgs += 1
                _after_delivery(rec, items, now, day)
                _remember_events(rec, digest or [], now)
                save_state(st)
    return sent_msgs


NEWS_DIGEST_LIMIT = 30       # 2026-10-24: 15 → 30. 중요도 점수로 줄 세운 뒤 자르므로 많이 넣어도 잡음이 앞에 안 온다
NEWS_EVENT_MEMORY_D = 4      # 이미 알린 사건을 기억하는 기간 — 다른 매체가 며칠 뒤 다시 써도 재발송 안 함


def _remember_events(rec: dict, digest: list, now: datetime):
    cut = now - timedelta(days=NEWS_EVENT_MEMORY_D)
    ev = [e for e in (rec.get('events') or []) if (_iso(e.get('ts', '')) or now) >= cut]
    ev += [{'h': d.get('headline', ''), 'ts': now.isoformat(timespec='seconds')} for d in digest if d.get('headline')]
    rec['events'] = ev[-20:]


SEC_8K_ITEMS = {'1.01': '중요 계약 체결', '1.02': '계약 해지', '2.01': '인수·매각 완료', '2.02': '실적 발표',
                '2.03': '채무 발생', '3.02': '주식 발행', '5.02': '임원 변경', '7.01': 'IR 자료', '8.01': '기타 주요 사항'}


def note_filed(st: dict, ticker: str, title: str):
    """공시로 이미 알린 사건 — 뉴스 요약이 같은 사건을 또 쓰지 않게(2026-10-24). 3일만 기억."""
    now = datetime.now(timezone.utc)
    lst = [f for f in (st.setdefault('filed', {}).get(ticker) or []) if (_iso(f.get('ts', '')) or now) >= now - timedelta(days=3)]
    lst.append({'t': str(title)[:120], 'ts': now.isoformat(timespec='seconds')})
    st['filed'][ticker] = lst[-15:]
