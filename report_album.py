"""장 마감 시황 카드뉴스 — 사이트 화면 + 글을 **한 메시지**로(2026-11-26 차니: "이미지랑 내용까지 다 한 메시지로").

텔레그램 앨범(사진 최대 10장) 한 통 + 첫 사진 캡션(1,024자 한도)에 전체 글.
글은 대시보드 market_narrate 가 사실에서 직접 만든 것(rec.facts.narrative) — 여기서 새로 쓰지 않는다.
사진은 시장별: 한국판 = 한국 화면(한·미가 나란히 그려진 구역은 왼쪽), 미국판 = ?home=US 화면(오른쪽).

  python -m report_album preview kr|daily [미리보기 JSON]   → 차니에게만
"""
import html
import json
import os
import sys
import tempfile
from pathlib import Path

import requests

import config
import tg

RAW = 'https://raw.githubusercontent.com/pcy604/stock-dashboard/main/results/market_report.json'
FLAG = {'kr': '🇰🇷', 'daily': '🇺🇸'}
TITLE = {'kr': '한국 증시 마감', 'daily': '미국 증시 마감'}
# 사진 순서 = 캡션의 ①~⑤. ('a+b' = 두 구역 반쪽을 위아래로 한 장)
# 2026-11-28 대시보드에서 오닐 카드(pulse) 제거 → 그 자리에 실전 규칙 배지(rule). 순서 = 종합 탭 탑다운(지수 → 히트맵 → 폭 → 오늘)
SHOTS = ['global', 'rule', 'heatmap', 'trend+week52', 'today']
HALF = {'week52', 'trend'}


def load(kind: str) -> dict:
    return (requests.get(RAW, timeout=30).json() or {}).get(f'latest_{kind}') or {}


def _e(s):
    return html.escape(str(s or ''), quote=False)


def _first(s: str) -> str:
    """줄이는 단위 — 여러 줄이면 앞 2줄, 한 줄이면 첫 문장."""
    s = str(s or '')
    if '\n' in s:
        return '\n'.join(s.split('\n')[:2])
    i = s.find('. ')
    return s[: i + 1] if i > 0 else s


def caption(rec: dict, limit: int = 1020) -> str:
    """한 통 캡션 — ①~⑤ 가 사진 순서와 같다. 넘치면 우선순위 낮은 문단부터 줄이고, 그래도 넘치면 뺀다."""
    kind = rec.get('kind')
    n = (rec.get('facts') or {}).get('narrative') or {}
    head = f"<b>{FLAG.get(kind, '')} {TITLE.get(kind, '시황')} · {_e(rec.get('date'))}" + (' (현지)' if kind == 'daily' else '') + '</b>'
    why = '\n'.join(x for x in ['📊 ' + _e(e) for e in (n.get('econ') or [])[:3]] +
                    ([_e(n['explain'])] if n.get('explain') else []) +
                    ['· ' + _e(w) for w in (n.get('why') or [])[:2]] if x)
    parts = [('① 오늘 시장', n.get('summary'), 0),
             ('📰 시장을 움직인 재료', why, 1),
             (f"② 투자 신호등 {n.get('light', '')}", n.get('signal'), 0),
             ('③ 시장 폭 · 52주 신고가·신저가', n.get('breadth'), 3),
             ('④ 돈의 흐름 · 종목', '\n'.join(x for x in (n.get('flow'), n.get('stocks')) if x), 4),
             ('⑤ 업종', n.get('sector'), 5)]
    if n.get('ledger'):
        parts.append(('실전 원장', n['ledger'], 2))
    if n.get('checkpoints'):
        parts.append(('체크포인트', '\n'.join(f'{i}. {c}' for i, c in enumerate(n['checkpoints'][:3], 1)), 2))
    foot = '사실에서 자동 작성 · 투자 권유 아님'

    def render(ps):
        out = [head]
        for h, body, _ in ps:
            if body:
                out.append(f'<b>{_e(h)}</b>\n' + (body if h.startswith('📰') else _e(body)))
        out.append(foot)
        return '\n\n'.join(out)

    ps = list(parts)
    for pri in (5, 4, 3, 2, 1):
        if len(render(ps)) <= limit:
            break
        ps = [(h, _first(b) if p_ == pri else b, p_) for h, b, p_ in ps]
    for pri in (5, 4, 3, 2):
        if len(render(ps)) <= limit:
            break
        ps = [x for x in ps if x[2] != pri]
    txt = render(ps)
    return txt if len(txt) <= limit else txt[: limit - 1] + '…'


def quality(rec: dict, photos: list, cap: str) -> list:
    """발송 전 채점 — 빈 목록이면 만점. 2026-11-26 차니: '기준 미달이면 자동으로 고치고 바로 올려야지'."""
    n = (rec.get('facts') or {}).get('narrative') or {}
    bad = []
    if len(photos) < len(SHOTS):
        bad.append(f'사진 {len(photos)}/{len(SHOTS)}')
    for k, lab in (('summary', '① 요약'), ('signal', '② 신호등'), ('breadth', '③ 시장 폭'), ('stocks', '④ 종목'), ('sector', '⑤ 업종')):
        if not n.get(k):
            bad.append(f'{lab} 없음')
    if not n.get('why'):
        bad.append('재료 뉴스 없음')
    for k in ('③', '④', '⑤'):
        if k not in cap:
            bad.append(f'캡션에서 {k} 잘림')
    return bad


def _trim(path: str, pad: int = 14) -> str:
    """사이트 양옆·위아래 빈 공간을 잘라 낸다(2026-11-26 — 사이트는 가운데로 세로로 쌓여 가로 끝이 비어 있다)."""
    from PIL import Image, ImageChops
    im = Image.open(path).convert('RGB')
    bg = Image.new('RGB', im.size, im.getpixel((2, 2)))
    diff = ImageChops.add(ImageChops.difference(im, bg), ImageChops.difference(im, bg), 2.0, -6)   # 배경 회색 vs 흰 카드도 잡게
    box = diff.getbbox()
    if box:
        x0, y0, x1, y1 = box
        im = im.crop((max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, im.width), min(y1 + pad, im.height)))
        im.save(path)
    return path


def _half(path: str, side: str) -> str:
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    out = path.replace('.png', f'_{side}.png')
    im.crop((0, 0, w // 2 + 6, h) if side == 'L' else (w // 2 - 6, 0, w, h)).save(out)
    return out


def _stack(paths: list, out: str) -> str:
    from PIL import Image
    ims = [Image.open(p).convert('RGB') for p in paths]
    w = max(i.width for i in ims)
    canvas = Image.new('RGB', (w, sum(i.height for i in ims) + 16 * (len(ims) - 1)), (240, 242, 246))
    y = 0
    for i in ims:
        canvas.paste(i, (0, y))
        y += i.height + 16
    canvas.save(out)
    return out


def ensure_browser():
    """실제 발송 실행(run.yml)에는 브라우저가 없다 — 보낼 리포트가 있을 때만 설치."""
    import subprocess
    try:
        import playwright  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'playwright'], check=True)
    cache = Path.home() / '.cache' / 'ms-playwright'
    if not (cache.exists() and any(cache.glob('chromium*'))):
        subprocess.run([sys.executable, '-m', 'playwright', 'install', '--with-deps', 'chromium'], check=True)


def build(rec: dict, out_dir: Path) -> list:
    """사진 경로 목록(SHOTS 순서, 실패한 건 빠짐)."""
    from social import shot
    us = rec.get('kind') == 'daily'
    keys = sorted({k for s in SHOTS for k in s.split('+')})
    got = shot.shot_cards(keys, out_dir=out_dir, mkt='US' if us else 'KR',
                          expect=None if os.environ.get('ALBUM_NO_EXPECT') else rec.get('date'))
    side = 'R' if us else 'L'
    out = []
    for s in SHOTS:
        ps = []
        for k in s.split('+'):
            if k in got:
                p = str(got[k])
                p = _half(p, side) if k in HALF else p
                try:
                    p = _trim(p)
                except Exception as e:
                    print(f'[카드뉴스] 여백 자르기 실패 {k}: {e}')
                ps.append(p)
        if not ps:
            continue
        out.append(ps[0] if len(ps) == 1 else _stack(ps, str(out_dir / f'stack_{s.replace("+", "_")}.png')))
    return out


def build_checked(rec: dict, tries: int = 2):
    """채점 → 사진이 모자라면 1분 뒤 다시 찍어 고친다. 글 결함은 대시보드 쪽(재시도·보류)이 고친다 — 여기선 기록만."""
    import time
    best = ([], caption(rec), ['미실행'])
    for i in range(tries):
        photos = build(rec, Path(tempfile.mkdtemp()))
        cap = caption(rec)
        bad = quality(rec, photos, cap)
        if len(photos) >= len(best[0]):
            best = (photos, cap, bad)
        if not any(b.startswith('사진') for b in bad):
            break
        print(f'[카드뉴스 채점] {bad} → 60초 뒤 다시 찍기({i + 1}/{tries})')
        time.sleep(60)
    return best


def send(chat, photos: list, cap: str) -> bool:
    if len(photos) >= 2:
        return bool(tg.send_media_group(chat, photos, cap))
    if photos:
        return bool(tg.send_photo(chat, photos[0], cap))
    return bool(tg.send_message(chat, cap))


def main(argv):
    if len(argv) < 3 or argv[1] != 'preview':
        print(__doc__)
        return 2
    kind = argv[2]
    rec = json.load(open(argv[3], encoding='utf-8')) if len(argv) > 3 else load(kind)
    if not (rec.get('facts') or {}).get('narrative'):
        print(f'⚠️ {kind} 리포트에 규칙 문장(narrative)이 없다 · engine={rec.get("engine")}')
        return 1
    chat = os.environ.get('OWNER_CHAT', '').strip() or str(getattr(config, 'OWNER_CHAT', ''))
    photos, cap, bad = build_checked(rec)
    print(f'{kind} {rec.get("date")} · 사진 {len(photos)}/{len(SHOTS)} · 캡션 {len(cap)}자 · 채점 {bad or "만점"}')
    ok = send(chat, photos, cap)
    en = ((rec.get('facts') or {}).get('narrative_en') or {}).get('text')
    if en:   # 2026-11-26 글로벌판 1단계 미리보기 — 같은 사진에 영어 글(발송 채널은 차니 결정 후)
        ok_en = send(chat, photos, _e(en)[:1020])
        print(f'영어판 {len(en)}자 → 소유자만 {"보냄" if ok_en else "실패"}')
    print('보냄 1통 → 소유자만' if ok else '발송 실패')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
