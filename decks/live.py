# -*- coding: utf-8 -*-
"""종목별 라이브 데이터 번들 — sources.py의 개별 페처를 한 dict로 조립.

이 모듈이 만드는 dict + IR 문서에서 뽑은 정적 사실(satl16_data.py)이 페이지 렌더의 입력.
다른 종목으로 확장할 때 여기는 티커/CIK만 바꾸면 그대로 돌아간다.
"""
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources as S  # noqa: E402

_KR_SUFFIXES = ('.KS', '.KQ')


def source_for(ticker: str):
    """티커가 속한 시장의 데이터 소스 모듈. sources_kr 은 sources 와 같은 함수
    이름·같은 반환 형태를 갖고, Yahoo 계열(가격·컨센서스·기관지분)은 그대로 재수출한다
    — 그래서 bundle() 은 이 한 줄 말고는 시장을 몰라도 된다.

    sources_kr import 실패(DART 키 없음 등)는 **조용히 US 로 폴백하지 않는다.**
    폴백하면 한국 종목에 SEC를 물어보게 되고, 빈 재무제표가 '데이터 없음'처럼
    보여서 원인을 못 찾는다."""
    if str(ticker or '').upper().endswith(_KR_SUFFIXES):
        import sources_kr
        return sources_kr
    return S

CACHE = Path(__file__).resolve().parent / '_cache'
WIKI_UA = 'buza-alarm-bot/1.0 (contact via Telegram @buza_alarm_bot) requests/python'
_ICON_SKIP = re.compile(
    r'oojs|commons-logo|wiktionary|wikidata|edit-|question_book|padlock|folder|ambox|'
    r'flag_of|symbol_|disambig|wiki_letter|semi-protection|nuvola|crystal_clear', re.I)


_LOGO_TAG = re.compile(r'<img\b[^>]*>', re.I)
_ATTR = lambda name: re.compile(name + r'\s*=\s*["\']([^"\']+)["\']', re.I)


def _logo_candidates(html: str, base: str) -> list:
    """회사 홈페이지 HTML → 로고 이미지 URL 후보(우선순위 순). 2026-10-23 한국 종목용.
    위키백과에 없는 코스닥 중소형주(피에스케이홀딩스)는 표지가 '피' 글자 동그라미였다."""
    from urllib.parse import urljoin
    out = []
    for tag in _LOGO_TAG.findall(html or ''):
        src = (_ATTR('src').search(tag) or _ATTR('data-src').search(tag))
        if not src:
            continue
        blob = tag.lower()
        if 'logo' in blob or 'ci' in re.findall(r'[a-z]+', blob):
            u = urljoin(base, src.group(1))
            if not u.lower().split('?')[0].endswith(('.svg', '.gif', '.ico')):
                out.append(u)
    # 헤더 로고가 흰색(어두운 배경용)이면 아래에서 걸러지고, 그때 쓸 예비 후보
    for rel in ('apple-touch-icon', 'icon'):
        m = re.search(r'<link[^>]+rel=["\'][^"\']*' + rel + r'[^"\']*["\'][^>]*>', html or '', re.I)
        if m and _ATTR('href').search(m.group(0)):
            u = urljoin(base, _ATTR('href').search(m.group(0)).group(1))
            if not u.lower().split('?')[0].endswith(('.svg', '.ico')):
                out.append(u)
    seen = set()
    return [u for u in out if not (u in seen or seen.add(u))][:8]


def _usable_logo(content: bytes):
    """표지(흰 배경)에 쓸 수 있는 로고인가 — 너무 작거나, 거의 흰색(어두운 헤더용)이면 버린다."""
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(content)).convert('RGBA')
    except Exception:
        return None
    if im.width < 100 or im.height < 28:
        return None
    px = [p for p in im.resize((min(im.width, 200), max(1, int(im.height * min(im.width, 200) / im.width)))).getdata() if p[3] > 40]
    if len(px) < 50:
        return None
    lum = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b, _ in px) / len(px)
    return None if lum > 235 else im


def site_logo(site: str, out: Path):
    """회사 홈페이지에서 로고를 찾아 PNG 로 저장. 실패하면 None."""
    if not site:
        return None
    try:
        r = requests.get(site, headers={'User-Agent': 'Mozilla/5.0 (buza-alarm-bot logo)'}, timeout=15)
        if r.status_code != 200:
            return None
        r.encoding = r.encoding or 'utf-8'
        for u in _logo_candidates(r.text, r.url):
            try:
                b = requests.get(u, headers={'User-Agent': 'Mozilla/5.0', 'Referer': r.url}, timeout=15)
                im = _usable_logo(b.content) if b.status_code == 200 else None
                if im is not None:
                    bbox = im.getbbox()
                    (im.crop(bbox) if bbox else im).save(out)
                    return str(out)
            except Exception:
                continue
    except Exception as e:
        print(f'[홈페이지 로고 실패] {site}: {e}')
    return None


# 한국 종목 로고 — 증권 앱 공개 아이콘(정사각 타일). 회사 홈페이지는 해외 IP 를 막는 곳이 많다
#   (2026-10-23 pskholding.com → 러너에서 403 호스팅 차단). 실측: 토스 481px · 알파스퀘어 280px.
_KR_ICON_URLS = ('https://static.toss.im/png-icons/securities/icn-sec-fill-{code}.png',
                 'https://file.alphasquare.co.kr/media/images/stock_logo/kr/{code}.png')


def kr_icon_logo(code: str, out: Path):
    from PIL import Image, ImageDraw
    import io
    for u in _KR_ICON_URLS:
        try:
            r = requests.get(u.format(code=code), headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if r.status_code != 200 or not r.headers.get('content-type', '').startswith('image/'):
                continue
            im = Image.open(io.BytesIO(r.content)).convert('RGBA')
            if im.width < 200:
                continue
            # 앱 아이콘처럼 둥근 모서리 — 사각 배경이 표지 흰 바탕에서 덜 튄다
            m = Image.new('L', im.size, 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=int(im.width * 0.22), fill=255)
            im.putalpha(m)
            im.save(out)
            return str(out)
        except Exception as e:
            print(f'[한국 로고 실패] {u}: {e}')
    return None


def hi_res_logo(ticker: str, company: str, wiki_file='', width=1000, site=''):
    """표지 중앙 배치용 고해상도 로고.

    wiki_file(정확한 commons 경로)을 알면 그대로 쓰고, 모르면(대부분의 경우)
    ir.company_logo()와 같은 방식으로 회사명 검색 → pageimages/images 탐색까지
    직접 수행한다 — PLTR 검증 때 wiki_file 없이는 항상 실패해 모노그램으로만
    떨어지던 문제를 잡음(티커로 Special:FilePath를 바로 찌르면 애초에 그런
    파일명이 존재하지 않아 100% 실패).
    """
    hi = CACHE / f'logo_{ticker}_hi.png'
    if hi.exists():
        return str(hi)

    def _fetch(fname):
        for u in (f'https://upload.wikimedia.org/wikipedia/commons/{fname}' if '/' in fname else None,
                 # en.wikipedia.org의 썸네일 서비스는 이 세션에서 반복 요청으로 429가 걸렸는데,
                 # commons.wikimedia.org는 별도 요청제한 버킷을 써서 같은 시점에도 정상 응답함
                 # (실제로 확인함 — 같은 파일, 같은 서비스인데 도메인만 다름).
                 f'https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(fname)}?width={width}'):
            if not u:
                continue
            try:
                r = requests.get(u, headers={'User-Agent': WIKI_UA}, timeout=25)
                if r.status_code == 200 and len(r.content) > 5000:
                    hi.write_bytes(r.content)
                    return str(hi)
            except Exception:
                pass
            time.sleep(1)
        return None

    if wiki_file:
        r = _fetch(wiki_file)
        if r:
            return r
    # 한국 종목은 홈페이지가 먼저다 — 영문 위키 검색에 한글 사명을 넣으면 엉뚱한 문서의 그림을 잡을 수 있다
    if ticker.upper().endswith(('.KS', '.KQ')):
        r = site_logo(site, hi) or kr_icon_logo(ticker[:6], hi)
        if r:
            return r

    try:
        s = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'list': 'search', 'srsearch': company, 'format': 'json', 'srlimit': 1,
        }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
        hits = s.get('query', {}).get('search', [])
        if hits:
            title = hits[0]['title']
            tokens = [w.lower() for w in re.split(r'\W+', company) if len(w) > 2]

            def score(fn):
                low = fn.lower()
                return 2 if 'logo' in low else (1 if any(t in low for t in tokens) else 0)

            # images 목록에서 "logo" 파일명을 먼저 찾는다 — pageimages(문서 대표사진)만
            # 믿으면 PLTR처럼 대표사진이 로고가 아닌 인물/이벤트 사진인 경우를 놓친다
            # (실제로 PLTR 위키 대표사진은 로고가 아니라 2018년 사무실 사진이었음).
            filename = None
            im = requests.get('https://en.wikipedia.org/w/api.php', params={
                'action': 'query', 'titles': title, 'prop': 'images', 'imlimit': 30, 'format': 'json',
            }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
            cands = []
            for pg in im.get('query', {}).get('pages', {}).values():
                for img in pg.get('images', []):
                    if not _ICON_SKIP.search(img['title']):
                        cands.append(img['title'].split(':', 1)[-1])
            cands.sort(key=score, reverse=True)
            if cands and score(cands[0]) >= 2:
                filename = cands[0]

            if not filename:
                p = requests.get('https://en.wikipedia.org/w/api.php', params={
                    'action': 'query', 'titles': title, 'prop': 'pageimages', 'piprop': 'name', 'format': 'json',
                }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
                for pg in p.get('query', {}).get('pages', {}).values():
                    if pg.get('pageimage'):
                        filename = pg['pageimage']
                        break
            if not filename and cands:
                filename = cands[0]   # logo는 아니어도 스킵필터 통과한 최선의 후보
            if filename:
                r = _fetch(filename.replace(' ', '_'))
                if r:
                    return r
    except Exception as e:
        print(f'[로고 검색 실패] {ticker}: {e}')

    # 위키에 없으면 회사 홈페이지 로고(한국 중소형주 대부분이 여기로 온다)
    r = site_logo(site, hi)
    if r:
        return r
    low = Path(__file__).resolve().parent.parent / 'logos' / f'{ticker}.png'
    return str(low) if low.exists() else None


def wiki_person_photo(person: str, out_path: Path):
    """회사 사이트에서 인물 사진을 못 찾았을 때(예: PLTR IR 사이트가 JS 렌더링이라
    <img> 태그가 0개) 위키피디아 인물 문서의 대표사진으로 폴백.

    로고 검색과 달리 인물 문서의 pageimages(대표사진)는 보통 본인 얼굴이 맞으므로
    먼저 시도하고, 없으면 images 목록에서 성(last name)이 파일명에 들어간 것을 찾는다.
    """
    if out_path.exists():
        return str(out_path)
    try:
        s = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'list': 'search', 'srsearch': person, 'format': 'json', 'srlimit': 1,
        }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
        hits = s.get('query', {}).get('search', [])
        if not hits:
            return None
        title = hits[0]['title']
        last = person.split()[-1].lower()

        filename = None
        p = requests.get('https://en.wikipedia.org/w/api.php', params={
            'action': 'query', 'titles': title, 'prop': 'pageimages', 'piprop': 'name', 'format': 'json',
        }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
        for pg in p.get('query', {}).get('pages', {}).values():
            if pg.get('pageimage'):
                filename = pg['pageimage']
                break

        if not filename:
            im = requests.get('https://en.wikipedia.org/w/api.php', params={
                'action': 'query', 'titles': title, 'prop': 'images', 'imlimit': 30, 'format': 'json',
            }, headers={'User-Agent': WIKI_UA}, timeout=15).json()
            cands = []
            for pg in im.get('query', {}).get('pages', {}).values():
                for img in pg.get('images', []):
                    if not _ICON_SKIP.search(img['title']):
                        cands.append(img['title'].split(':', 1)[-1])
            cands.sort(key=lambda fn: 1 if last in fn.lower() else 0, reverse=True)
            if cands:
                filename = cands[0]

        if not filename:
            return None
        fname = filename.replace(' ', '_')
        for u in (f'https://upload.wikimedia.org/wikipedia/commons/{fname}' if '/' in fname else None,
                 f'https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(fname)}?width=600'):
            if not u:
                continue
            try:
                r = requests.get(u, headers={'User-Agent': WIKI_UA}, timeout=25)
                if r.status_code == 200 and len(r.content) > 3000:
                    out_path.write_bytes(r.content)
                    return str(out_path)
            except Exception:
                pass
    except Exception as e:
        print(f'[인물 사진 검색 실패] {person}: {e}')
    return None


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        print(f'[수집 실패] {e}')
        return default


def bundle(ticker: str, cik: int, peers: dict, site: str, ceo: str, wiki_file='',
           listing_date=None, company=None):
    SRC = source_for(ticker)
    ann = SRC.annual_series(cik)
    qtr = SRC.quarterly_series(cik, ['revenue', 'cogs', 'opinc', 'netinc', 'cfo', 'cash',
                                   'equity', 'assets', 'liab'], limit=14)
    cons = SRC.consensus(ticker)
    own = SRC.ownership(ticker)

    peer_fin = {}
    peer_failed = {}
    for pt, pcik in peers.items():
        try:
            pa = SRC.annual_series(pcik, ['revenue', 'cogs', 'opinc', 'netinc'])
            pc = SRC.consensus(pt)
            peer_fin[pt] = {'ann': pa, 'mktcap': pc.get('market_cap'), 'price': pc.get('price')}
        except Exception as e:
            # ⚠️ 2026-10-03: SMTOY·KXIAY 가 'Expecting value: line 1 column 1' 로 죽었다.
            #    티커가 잘못된 게 아니라 **외국 기업 ADR 이라 SEC companyfacts 가 없는** 것이다
            #    (20-F 만 내거나 아예 안 낸다). 빈 응답을 json 이 파싱하다 나는 오류라
            #    메시지만 보면 버그처럼 읽힌다.
            #    그리고 더 나쁜 건, 이 peer 가 **밸류에이션 비교에서 조용히 빠진다**는 것이다.
            #    비교 대상이 둘인 줄 알고 보는데 실제론 하나로 그려진다.
            why = ('SEC 재무데이터 없음(해외 ADR 등 — 20-F/미제출)'
                   if 'Expecting value' in str(e) else f'{type(e).__name__}: {e}')
            peer_failed[pt] = why
            print(f'[peer 제외] {pt}: {why}')

    ceo_photo = None
    ceo_photo_source = None
    try:
        ceo_photo = SRC.leader_photo(site, ceo, CACHE / f'ceo_{ticker}.jpg')
        if ceo_photo:
            ceo_photo_source = f'{company or ticker} 공식 홈페이지 경영진 페이지'
    except Exception:
        pass
    # 2026-11-04: 한국 종목은 위키 이름 검색 사진을 쓰지 않는다 — '박경수'(PSK 대표)로 찾았더니
    #   동명 문서의 TV 그림이 CEO 사진 자리에 실렸다(fixture 렌더 실측). 틀린 얼굴보다 이니셜이 낫다.
    if not ceo_photo and not str(ticker).upper().endswith(_KR_SUFFIXES):
        ceo_photo = wiki_person_photo(ceo, CACHE / f'ceo_{ticker}_wiki.jpg')
        if ceo_photo:
            ceo_photo_source = 'Wikipedia'

    return {
        'ticker': ticker, 'cik': cik,
        # 비교에서 빠진 peer 와 그 이유 — 9p 가 "비교가 불완전하다"를 드러내는 근거다.
        'peer_failed': peer_failed,
        'annual': ann, 'quarterly': qtr, 'consensus': cons, 'ownership': own,
        'q_revenue': SRC.quarterly_filled(cik, 'revenue', 9),
        'q_opinc': SRC.quarterly_filled(cik, 'opinc', 9),
        # 은행(JPM)·리츠(O) 등은 OperatingIncomeLoss 태그를 아예 안 낸다 — 실측 확인.
        # 영업이익이 없으면 순이익으로 대체해야 CANSLIM C·A와 밸류에이션 분기가
        # "태그가 없다"는 이유로 0점/적자 판정이 되는 걸 막을 수 있다.
        'q_netinc': SRC.quarterly_filled(cik, 'netinc', 9),
        # 6년 고정이었더니 오래된 종목(AAPL 등)에서 "월간 퀀트·MDD"가 최근 6년만
        # 보여줘 역사적 낙폭·계절성 패턴을 거의 못 봤다(실제 지적: 최소 2017년
        # 1월 이후는 보고 싶다는데 6년으론 어림도 없음). MDD(낙폭 라인차트)는
        # 수십 년을 한 선으로 그려도 문제없어 30년으로 늘렸다. 히트맵(연도×월
        # 표)은 한 해가 한 행이라 그대로 늘리면 페이지가 푸터 밖으로 넘쳤다
        # (실제 발견) — p15_quant에서 row_h를 줄이고 MDD 차트 높이를 살짝
        # 줄여 10년(요청한 2017년~)이 들어가게 맞춤. 어린 종목(IONQ·SATL 등)은
        # since=listing_date로 실제 상장 이후만 남으니 둘 다 부작용 없음.
        'monthly': SRC.monthly_matrix(ticker, 10, since=listing_date),
        'drawdown': SRC.drawdown(ticker, 30, since=listing_date),
        'weekly': SRC.weekly_price(ticker, 5, since=listing_date),
        'technical': SRC.technical_snapshot(ticker, since=listing_date),
        'ohlcv': _safe(lambda: SRC.monthly_ohlcv(ticker, since=listing_date), {}),
        'listing_date': listing_date,
        # 오닐·리버모어 페이지(2026-10-20): 일봉 2년 + 시장(SPY) + 분기 EPS·주식수 + 기관 활동
        'daily': _safe(lambda: S.daily_ohlcv(ticker, 2), []),
        # 시장 기준: 미국=S&P500(SPY), 한국=코스피(^KS11) — 오닐 M·상대강도용
        'spy_daily': _safe(lambda: S.daily_ohlcv('^KS11' if ticker.upper().endswith(_KR_SUFFIXES) else 'SPY', 2), []),
        'q_eps': _safe(lambda: SRC.quarterly_series(cik, ['eps', 'shares'], limit=12), {}),
        # 산업 지도 — 비교 기업 1년 종가(업종 안 주가 강도 순위)
        'peer_px': {pt: _safe(lambda pt=pt: [r['c'] for r in S.daily_ohlcv(pt, 1)], [])
                    for pt in (peers or {})},
        'inst_activity': _safe(lambda: S.nasdaq_institutional(ticker), {})
        if not ticker.upper().endswith(_KR_SUFFIXES) else {},
        'peers': peer_fin,
        'proxy': _safe(lambda: SRC.beneficial_owners(cik), {}),
        'ceo_photo': ceo_photo,
        'ceo_photo_source': ceo_photo_source,
        'logo_hi': hi_res_logo(ticker, company or ticker, wiki_file, site=site),
    }


# ── 오프라인 렌더용 고정 데이터(fixture) ──────────────────────────────
# 2026-10-20: 리포트 페이지를 고칠 때마다 러너에서만 확인할 수 있었다(개발 환경은
# SEC·Yahoo 접속이 막힘). 러너에서 한 번 받아 둔 라이브 번들을 피클로 저장해 두고,
# 개발 환경에서는 그걸로 렌더해 눈으로 확인한다. 피클인 이유: 연도 키가 int 라
# JSON 으로 저장하면 문자열이 되어 페이지가 깨진다.
#   LIVE_FIXTURE_DIR=decks/fixtures LIVE_DUMP=1  → 받아서 저장(러너, fixture.yml)
#   LIVE_FIXTURE_DIR=decks/fixtures              → 저장본으로 렌더(개발 환경)
import os as _os
import pickle as _pickle

_bundle_live = bundle


def bundle(ticker: str, cik: int, *args, **kwargs):
    fx = _os.environ.get('LIVE_FIXTURE_DIR')
    path = Path(fx) / f'{ticker.lower().replace(".", "_")}_live.pkl' if fx else None
    if path and path.exists() and not _os.environ.get('LIVE_DUMP'):
        d = _pickle.loads(path.read_bytes())
        for k, v in list(d.items()):            # 함께 저장한 이미지(로고·CEO 사진) 경로 복원
            if isinstance(v, str) and v.startswith('fixture:'):
                d[k] = str(path.parent / v[len('fixture:'):])
        return d
    d = _bundle_live(ticker, cik, *args, **kwargs)
    if path and _os.environ.get('LIVE_DUMP'):
        path.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        d = dict(d)
        for k, v in list(d.items()):
            if isinstance(v, str) and v.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and Path(v).exists():
                name = f'{path.stem}_{k}{Path(v).suffix.lower()}'
                shutil.copyfile(v, path.parent / name)
                d[k] = 'fixture:' + name
        path.write_bytes(_pickle.dumps(d))
        print(f'[fixture] 저장 {path} ({path.stat().st_size // 1024}KB)')
    return d
