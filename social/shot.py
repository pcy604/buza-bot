"""대시보드 화면 캡처 — 포토카드·숏츠 배경의 원천.

Streamlit Cloud 는 래퍼 페이지 안에 iframe 으로 앱을 띄우므로 래퍼가 아니라 iframe 주소(`/~/+/`)를 직접 연다.

사용:
  python -m social.shot cards                 → 🏠 종합 탭 카드 전부 (social/out/card_*.png)
  python -m social.shot cards breadth flow    → 지정한 카드만
  python -m social.shot cards --mobile        → 세로(1080×1920) — 숏츠 배경용
  python -m social.shot list                  → 지금 화면에 있는 카드 제목을 찍어 본다(선택자 디버깅)
  python -m social.shot top SOXX              → 종목 분석 상단
  python -m social.shot cycle SOXX            → 사이클·낙폭 섹션

2026-11-22 고장 수리
  `_page` 가 `text=종목명 또는 코드` 가 **보일 때까지** 기다렸는데, 11-16 '검색 줄 38px 정렬'
  작업에서 그 라벨이 `label_visibility="collapsed"` 가 됐다(dashboard.py:6137 · ui_cycle.py:31).
  DOM 에는 있지만 숨어 있어 영원히 visible 이 되지 않고 2분 뒤 타임아웃으로 죽었다.
  마지막 성공 캡처가 11-15 다.
  → 라벨 대신 **① Streamlit 실행 표시가 사라졌는지 ② 호출자가 원하는 요소가 떴는지** 를 본다.
     라벨은 `label_visibility` 로 언제든 숨겨질 수 있으므로 다시는 기준으로 쓰지 않는다.
"""
import sys
import time
from pathlib import Path

import config

APP = config.DASHBOARD_URL.rstrip('/') + '/~/+/'
OUT = Path('social/out')

# 카드 키 → 그 카드 <h5> 제목에 들어 있는 글자. ui_home.py 가 <div class='hm-box'><h5>제목</h5> 로 그린다.
#   제목은 사람이 읽는 문구라 label_visibility 같은 것에 숨지 않는다.
CARDS = {
    'breadth':       '시장 폭',
    'flow':          '수급',
    'sector_strong': '강한 업종',
    'sector_weak':   '약한 업종',
    'theme':         '강세 테마',
    'newhigh':       '52주 신고가',
    'featured':      '특징주',
    'bigcap':        '대형주 상승 상위',
}
# 카드가 아니라 구역 단위로 잡는 것
REGIONS = {
    'global':  ('.hm-grid', 0),      # 글로벌 마켓 14칸 (첫 번째 그리드)
    'heatmap': ('.js-plotly-plot', -1),   # 업종 히트맵 (마지막 plotly — 종합 탭에서 히트맵이 맨 아래)
}


def _settle(p, timeout=180_000, min_wait=8):
    """Streamlit 이 다 그릴 때까지.

    ⚠️ 2026-11-22: 처음엔 '실행 표시(stStatusWidget)가 사라지면 끝' 으로 판정했는데,
    그 위젯은 **처음부터 안 뜰 때가 있다**(캐시된 페이지). count()==0 으로 즉시 빠져나와
    4초만 기다렸고, 그 시점엔 카드가 0개였다(실측: +4초 0개 → +10초 9개).
    '없음'을 '끝났음'으로 읽은 것이다. → 본문 길이가 **더 이상 늘지 않을 때까지** 기다린다.
    """
    p.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=timeout)
    end, last, stable = time.time() + timeout / 1000, -1, 0
    t0 = time.time()
    while time.time() < end:
        time.sleep(1.5)
        try:
            n = len(p.inner_text('body'))
        except Exception:
            continue
        stable = stable + 1 if n == last else 0
        last = n
        if stable >= 3 and time.time() - t0 >= min_wait:   # 3회 연속 그대로 + 최소 대기
            break
    time.sleep(3)          # plotly·폰트 렌더 여유


def _page(pw, url, width=1300, height=1100, mobile=False, ready=None):
    b = pw.chromium.launch()
    kw = dict(viewport={'width': width, 'height': height}, device_scale_factor=2, locale='ko-KR')
    if mobile:             # 모바일 UA 를 줘야 대시보드가 IS_MOBILE 분기로 세로 레이아웃을 그린다
        kw['user_agent'] = ('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 '
                            '(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36')
        kw['is_mobile'] = True
        kw['has_touch'] = True
    ctx = b.new_context(**kw)
    p = ctx.new_page()
    p.goto(url, wait_until='domcontentloaded', timeout=120_000)
    _settle(p)
    if ready:
        p.wait_for_selector(ready, timeout=120_000)
        time.sleep(2)
    return b, p


def _save(loc, out: Path, pad=10):
    """요소 하나를 파일로. locator.screenshot 이 스크롤·클리핑을 알아서 한다."""
    loc.scroll_into_view_if_needed(timeout=30_000)
    time.sleep(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    loc.screenshot(path=str(out))
    return out


def list_cards(mobile=False) -> list:
    """지금 화면에 실제로 있는 카드 제목을 돌려준다. 선택자가 안 맞을 때 먼저 이걸 본다."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, p = _page(pw, APP, **({'width': 1080, 'height': 1920, 'mobile': True} if mobile else {}))
        got = []
        box = p.locator('div.hm-box')
        for i in range(box.count()):
            try:
                got.append(box.nth(i).locator('h5').inner_text(timeout=3_000).strip())
            except Exception:
                got.append('(제목 없음)')
        extra = {k: p.locator(s).count() for k, (s, _) in REGIONS.items()}
        b.close()
        return got, extra


def shot_cards(keys=None, mobile=False, out_dir: Path = OUT) -> dict:
    """🏠 종합 탭 카드를 키별 PNG 로. 돌려주는 값 {키: 경로} — 못 찾은 키는 빠진다."""
    from playwright.sync_api import sync_playwright
    want = list(keys) if keys else list(CARDS) + list(REGIONS)
    done, miss = {}, []
    with sync_playwright() as pw:
        # ⚠️ 뷰포트를 아주 길게 잡는다(2026-11-22). 짧은 뷰포트에서는 요소를 스크롤해 찍는데,
        #    Streamlit 의 고정 헤더가 요소 윗부분을 덮어 **글로벌 마켓 첫 줄의 지수명과 종가가
        #    통째로 잘렸다**(−3.70% 만 남고 'S&P500 6,910.39' 가 사라짐).
        #    전부 화면 안에 들어오게 해 두면 스크롤이 필요 없어 잘릴 일이 없다. shot_cycle 과 같은 수법.
        size = ({'width': 1080, 'height': 6000, 'mobile': True} if mobile
                else {'width': 1300, 'height': 6000})
        # 카드 하나라도 떠야 의미가 있다
        b, p = _page(pw, APP, ready='div.hm-box', **size)
        tag = 'm' if mobile else 'w'
        for k in want:
            try:
                if k in REGIONS:
                    sel, idx = REGIONS[k]
                    loc = p.locator(sel)
                    n = loc.count()
                    if n == 0:
                        miss.append(f'{k}(요소 0개)')
                        continue
                    loc = loc.nth(idx if idx >= 0 else n + idx)
                else:
                    loc = p.locator('div.hm-box').filter(has_text=CARDS[k]).first
                    if loc.count() == 0:
                        miss.append(f'{k}("{CARDS[k]}" 없음)')
                        continue
                done[k] = _save(loc, out_dir / f'card_{tag}_{k}.png')
            except Exception as e:
                miss.append(f'{k}({type(e).__name__})')
        if miss:                                   # 실패해도 전체 화면은 남긴다 — 왜 못 찾았는지 눈으로 본다
            out_dir.mkdir(parents=True, exist_ok=True)
            p.screenshot(path=str(out_dir / f'card_{tag}_FAIL_fullpage.png'), full_page=True)
        b.close()
    if miss:
        print('못 찾음:', ', '.join(miss), f'(전체 화면은 {out_dir}/card_*_FAIL_fullpage.png)', file=sys.stderr)
    return done


def shot_top(sym: str, out: Path) -> Path:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # 라벨이 아니라 **입력창 자체**를 기다린다. label_visibility 와 무관하다.
        b, p = _page(pw, f'{APP}?sym={sym}', ready='input[aria-label*="종목명"], [data-testid="stTextInput"] input')
        p.screenshot(path=str(out), clip={'x': 0, 'y': 0, 'width': 1300, 'height': 1100})
        b.close()
    return out


def shot_cycle(sym: str, out: Path) -> Path:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # Streamlit 은 window 가 아니라 내부 컨테이너가 스크롤된다 → 뷰포트를 길게 잡아 전부 보이게 하고 좌표로 자른다
        # (중간에 viewport 를 바꾸면 Streamlit 이 전부 다시 그려서 요소 핸들이 떨어져 나간다)
        b, p = _page(pw, f'{APP}?sym={sym}', height=9000,
                     ready='input[aria-label*="종목명"], [data-testid="stTextInput"] input')

        def _box(needle):
            loc = p.locator(f'text={needle}')
            for k in range(loc.count()):
                bb = loc.nth(k).bounding_box()
                if bb and bb['width'] > 0:
                    return bb
            return None

        log = []
        for bt in p.get_by_role('button', name='히스토리').all():
            try:
                bt.scroll_into_view_if_needed(timeout=5_000)
                bt.click(timeout=5_000)
                p.wait_for_selector('text=사이클·낙폭', timeout=20_000)
            except Exception as e:
                log.append(f'skip: {type(e).__name__}')
                continue
            time.sleep(6)
            hb, ub = _box('사이클·낙폭'), _box('상승 구간 (저점 → 고점)')
            log.append(f'hb={hb} ub={ub}')
            if hb:
                y0 = max(0, hb['y'] - 16)
                y1 = (ub['y'] - 8) if ub else hb['y'] + 900
                p.screenshot(path=str(out), clip={'x': 0, 'y': y0, 'width': 1300, 'height': max(400, y1 - y0)})
                b.close()
                return out
        p.screenshot(path=str(out.with_name(out.stem + '_fail.png')))
        b.close()
        raise RuntimeError('사이클 섹션 캡처 실패: ' + ' | '.join(log))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    argv = [a for a in sys.argv[1:] if a != '--mobile']
    mob = '--mobile' in sys.argv
    cmd = (argv[0] if argv else 'cards').lower()
    OUT.mkdir(parents=True, exist_ok=True)

    if cmd == 'list':
        titles, extra = list_cards(mobile=mob)
        print(f'hm-box {len(titles)}개:')
        for t in titles:
            print('  -', t)
        print('구역:', extra)
    elif cmd == 'cards':
        got = shot_cards(argv[1:] or None, mobile=mob)
        for k, v in got.items():
            print(f'{k:14s} {v}')
        print(f'— {len(got)}장')
        sys.exit(0 if got else 1)
    elif cmd == 'top':
        print(shot_top((argv[1] if len(argv) > 1 else 'SOXX').upper(), OUT / 'shot_top.png'))
    elif cmd == 'cycle':
        s = (argv[1] if len(argv) > 1 else 'SOXX').upper()
        print(shot_cycle(s, OUT / f'shot_{s.lower()}_cycle.png'))
    else:
        print(__doc__)
        sys.exit(2)
