"""회사 IR 사이트의 발표자료(PDF)를 감시하고, 새 자료가 올라오면 '지난 자료 대비 바뀐 것'을 요약한다.

2026-10-20 신설. 왜 필요한가:
  SEC 공시·구글 뉴스로는 IR 발표자료(가이던스·수주잔고·로드맵 슬라이드)를 못 본다.
  8-K 에 첨부되지 않는 자료도 많다(컨퍼런스 발표 등). 그런데 소형주 보유자에게는 이게
  가장 밀도 높은 1차 자료다.

방식:
  · 회사마다 크롤러를 따로 짜지 않는다. 미국 상장사 IR 사이트는 소수의 공용 플랫폼
    (Nasdaq IR / Notified 계열: Drupal + /static-files/ + /rss/*.xml)이 다수다.
    플랫폼 단위로 찾고, 못 찾으면 그 종목은 조용히 건너뛴다(상태에 'none' 으로 남김).
  · 처음 찾은 날은 기준선만 잡는다 — 지난 자료를 한꺼번에 쏟아내지 않는다.
  · 새 자료가 오면 그 PDF 와 직전 자료의 텍스트를 같이 넣어 LLM 1회(언어별)로 비교 요약.

상태: ir_site_state.json (실행 끝에 레포로 커밋)
  {"sites": {"SATL": {"base": "https://investors.satellogic.com", "pres": "/news-events/presentations",
                      "checked": iso}},
   "decks": {"SATL": {"seen": [url, ...], "last": {"url":..., "title":..., "date":...}}}}
"""
import io
import json
import re
import html as _html
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

STATE_PATH = Path(__file__).parent / 'ir_site_state.json'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124 Safari/537.36'}

# 사람이 확인한 IR 주소(자동 탐색이 틀리거나 못 찾을 때). 실측: SATL 은 Nasdaq IR 계열.
KNOWN = {'SATL': 'https://investors.satellogic.com'}
PRES_PATHS = ['/news-events/presentations', '/events-and-presentations/presentations',
              '/news-and-events/presentations', '/events-presentations', '/presentations',
              '/news-events/events-presentations', '/investors/presentations']
REDISCOVER_D = 7          # 못 찾은 종목은 일주일에 한 번만 다시 찾아본다
MAX_PDF_MB = 25
NEW_CHARS, PREV_CHARS = 40_000, 20_000

_MONTHS = ('January|February|March|April|May|June|July|August|September|October|'
           'November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec')
_DATE_RE = re.compile(rf'\b({_MONTHS})\.?\s+(\d{{1,2}}),\s+(20\d\d)\b')
_A_RE = re.compile(r'<a\b([^>]*?)href="([^"]*?/static-files/[0-9a-fA-F-]{20,}[^"]*)"([^>]*)>(.*?)</a>',
                   re.S | re.I)


def load_state() -> dict:
    try:
        st = json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception:
        st = {}
    st.setdefault('sites', {})
    st.setdefault('decks', {})
    return st


def save_state(st: dict):
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def _get(url: str, **kw):
    return requests.get(url, headers=UA, timeout=kw.pop('timeout', 25), **kw)


def _text(s: str) -> str:
    return re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', ' ', s or ''))).strip()


def _iso_date(s: str):
    m = _DATE_RE.search(s or '')
    if not m:
        return ''
    mon = m.group(1)[:3].title()
    try:
        return datetime.strptime(f'{mon} {m.group(2)} {m.group(3)}', '%b %d %Y').date().isoformat()
    except ValueError:
        return ''


def parse_presentations(page_html: str, base: str) -> list:
    """발표자료 목록 페이지 → [{'url','title','date'}], 페이지 순서 유지(보통 최신이 위).

    제목은 링크 글자 → title 속성(원래 파일명) 순으로 쓴다. 'Download'·'View' 같은 버튼
    글자면 앞쪽 400자 안의 마지막 굵은/제목 텍스트로 대신한다. 날짜는 링크 앞 600자 안에서
    가장 가까운 'September 18, 2026' 형태.
    """
    out, seen = [], set()
    for m in _A_RE.finditer(page_html or ''):
        attrs = (m.group(1) or '') + ' ' + (m.group(3) or '')
        href = _html.unescape(m.group(2))
        url = href if href.startswith('http') else base.rstrip('/') + '/' + href.lstrip('/')
        url = url.split('#')[0]
        if url in seen:
            continue
        seen.add(url)
        title = _text(m.group(4))
        if not title or title.lower() in ('download', 'view', 'pdf', 'view presentation',
                                          'download presentation', 'presentation', 'slides'):
            ta = re.search(r'title="([^"]+)"', attrs)
            before = page_html[max(0, m.start() - 400):m.start()]
            heads = re.findall(r'<(?:h\d|strong|b)[^>]*>(.*?)</(?:h\d|strong|b)>', before, re.S | re.I)
            title = (_text(heads[-1]) if heads else '') or (_text(ta.group(1)) if ta else '') or title
        before = _text(page_html[max(0, m.start() - 600):m.start()])
        dates = list(_DATE_RE.finditer(before))
        date = _iso_date(dates[-1].group(0)) if dates else ''
        out.append({'url': url, 'title': title[:160], 'date': date})
    return out


def _candidates(ticker: str) -> list:
    if ticker in KNOWN:
        return [KNOWN[ticker]]
    try:
        import ir
        import sys
        sys.path.insert(0, str(Path(__file__).parent / 'decks'))
        from sources import company_site
        cik, _ = ir.resolve_ticker(ticker)
        site = company_site(cik) if cik else None
    except Exception:
        site = None
    if not site:
        return []
    m = re.match(r'https?://(?:www\.)?([\w.-]+)', site if '://' in site else 'https://' + site)
    if not m:
        return []
    d = m.group(1)
    return [f'https://investors.{d}', f'https://ir.{d}', f'https://investor.{d}']


def discover(ticker: str, st: dict, now=None):
    """IR 사이트 base 와 발표자료 경로. 못 찾으면 None (상태에 남겨 일주일간 재시도 안 함)."""
    now = now or datetime.now(timezone.utc)
    rec = st['sites'].get(ticker) or {}
    if rec.get('base') and rec.get('pres'):
        return rec
    if rec.get('none') and rec.get('checked', '') > (now - timedelta(days=REDISCOVER_D)).isoformat():
        return None
    for base in _candidates(ticker):
        for path in PRES_PATHS:
            try:
                r = _get(base + path)
            except Exception:
                continue
            if r.status_code == 200 and parse_presentations(r.text, base):
                rec = {'base': base, 'pres': path, 'checked': now.isoformat(timespec='seconds')}
                st['sites'][ticker] = rec
                return rec
    st['sites'][ticker] = {'none': True, 'checked': now.isoformat(timespec='seconds')}
    return None


def pdf_text(url: str, limit: int) -> str:
    """PDF 본문 텍스트(앞에서부터 limit 자). PDF 가 아니거나 너무 크면 ''."""
    try:
        r = _get(url, timeout=60, stream=True)
        if r.status_code != 200:
            return ''
        data = r.raw.read(MAX_PDF_MB * 1024 * 1024 + 1, decode_content=True)
        if len(data) > MAX_PDF_MB * 1024 * 1024 or not data.startswith(b'%PDF'):
            return ''
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        parts, n = [], 0
        for i, pg in enumerate(rd.pages):
            t = (pg.extract_text() or '').strip()
            if t:
                parts.append(f'[p{i + 1}] {t}')
                n += len(t)
            if n >= limit:
                break
        return '\n'.join(parts)[:limit]
    except Exception as e:
        print(f'[IR 자료 PDF 실패] {url}: {e}')
        return ''


DECK_PROMPT = """You are an equity analyst. {company} ({ticker}) just posted a new investor presentation on its IR site.
Compare it with the previous presentation and tell a shareholder what is new or different.
Write every string value in **{lang_name}** (keep company names, tickers and product names as written).
Output pure JSON only:

{{
  "headline": "one line: what this deck is and the single most important takeaway",
  "changes": ["what changed vs the previous deck — guidance, backlog, customers, timelines, financing, strategy (max 5)"],
  "key_points": ["other important facts stated in the new deck (max 4)"],
  "watch": ["at most 2 things a holder should verify or watch next, stated as questions, not advice"]
}}

Rules:
- Use only what is written in the decks. Copy numbers exactly; give units and periods.
- If a number or target moved, show both: "X → Y".
- If there is no previous deck text, leave "changes" empty and put the facts in key_points.
- No buy/sell/hold opinions, no price targets.

[NEW DECK — "{new_title}" {new_date}]
{new_text}

[PREVIOUS DECK — "{prev_title}" {prev_date}]
{prev_text}
"""


def summarize_deck(ticker, company, new, prev, new_text, prev_text, lang='ko'):
    import analyzer
    import prefs
    prompt = DECK_PROMPT.format(company=company, ticker=ticker,
                                lang_name=prefs.LANGS.get(lang, 'English'),
                                new_title=new.get('title', ''), new_date=new.get('date', ''),
                                new_text=new_text or '(text unavailable)',
                                prev_title=(prev or {}).get('title', ''), prev_date=(prev or {}).get('date', ''),
                                prev_text=prev_text or '(none)')
    try:
        resp = analyzer._generate(analyzer._client(), prompt)
        data = analyzer._parse(resp.text)
    except Exception as e:
        print(f'  [{ticker}] IR 자료 요약 실패: {e}')
        return None
    if data.get('_parse_error') or not data.get('headline'):
        return None
    return data


def check(send_deck, now=None) -> int:
    """감시 종목의 IR 발표자료를 확인하고 새 자료가 있으면 감시자에게 보낸다. 보낸 수를 돌려준다.
    6시간 주기작업 안에서 돈다. 실패는 종목 단위로 삼키고 다음 실행에 다시 본다."""
    import ir
    import prefs
    now = now or datetime.now(timezone.utc)
    ist = ir.load_state()
    tickers = sorted({t for lst in ist['watches'].values() for t in lst})
    st = load_state()
    sent = 0
    for t in tickers:
        watchers = [c for c, lst in ist['watches'].items() if t in lst]
        site = discover(t, st, now)
        save_state(st)
        if not site:
            continue
        try:
            items = parse_presentations(_get(site['base'] + site['pres']).text, site['base'])
        except Exception as e:
            print(f'  [{t}] IR 자료 목록 실패: {e}')
            continue
        if not items:
            continue
        drec = st['decks'].setdefault(t, {})
        if 'seen' not in drec:                       # 처음 본 날: 기준선만
            drec['seen'] = [i['url'] for i in items]
            drec['last'] = items[0]
            save_state(st)
            print(f'  [{t}] IR 자료 기준선 {len(items)}건 ({site["base"]})')
            continue
        new = [i for i in items if i['url'] not in drec['seen']]
        if not new:
            continue
        item = new[0]                                # 가장 위(최신) 1건만 — 나머지는 본 것으로
        prev = drec.get('last')
        _, company = ir.resolve_ticker(t)
        new_text = pdf_text(item['url'], NEW_CHARS)
        prev_text = pdf_text(prev['url'], PREV_CHARS) if prev and new_text else ''
        cache = {}
        for lang in dict.fromkeys(prefs.get(c)['lang'] for c in watchers):
            cache[lang] = summarize_deck(t, company or t, item, prev, new_text, prev_text, lang) \
                if new_text else None
        # 요약 실패(LLM)는 다음 실행에 재시도, 3번째엔 제목·링크만이라도 보낸다.
        # PDF 텍스트가 없는 경우(PPTX·스캔본)는 기다려도 안 나오므로 바로 링크로 보낸다.
        if new_text and any(v is None for v in cache.values()):
            drec['tries'] = drec.get('tries', 0) + 1
            save_state(st)
            if drec['tries'] < 3:
                print(f'  [{t}] IR 자료 요약 실패 {drec["tries"]}회 — 다음 실행에 재시도')
                continue
        ok_all = True
        for c in watchers:
            ok_all &= bool(send_deck(int(c), t, item, cache[prefs.get(c)['lang']],
                                     lang=prefs.get(c)['lang']))
        if ok_all:
            sent += len(watchers)
            drec['seen'] = list(dict.fromkeys([i['url'] for i in new] + drec['seen']))[:200]
            drec['last'] = item
            drec['tries'] = 0
            save_state(st)
    return sent
