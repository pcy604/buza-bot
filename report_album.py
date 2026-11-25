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
SHOTS = ['global', 'pulse', 'trend+week52', 'today', 'heatmap']
HALF = {'pulse', 'week52', 'trend'}


def load(kind: str) -> dict:
    return (requests.get(RAW, timeout=30).json() or {}).get(f'latest_{kind}') or {}


def _e(s):
    return html.escape(str(s or ''), quote=False)


def _first(s: str) -> str:
    """문단의 첫 문장(마침표까지) — 캡션 한도를 넘을 때 줄이는 단위."""
    s = str(s or '')
    i = s.find('. ')
    return s[: i + 1] if i > 0 else s


def caption(rec: dict, limit: int = 1020) -> str:
    """한 통 캡션. 우선순위 낮은 문단부터 첫 문장만 남기고, 그래도 넘치면 뺀다."""
    kind = rec.get('kind')
    n = (rec.get('facts') or {}).get('narrative') or {}
    head = f"<b>{FLAG.get(kind, '')} {TITLE.get(kind, '시황')} · {_e(rec.get('date'))}" + (' (현지)' if kind == 'daily' else '') + '</b>'
    why = [_e(w) for w in (n.get('why') or [])[:2]]
    # (머리, 본문, 우선순위 — 클수록 먼저 줄인다)
    parts = [('', n.get('summary'), 0),
             ('📰 시장을 움직인 재료', '\n'.join('· ' + w for w in why) if why else '', 1),
             (f"② 투자 신호등 {n.get('light', '')}", n.get('signal'), 0),
             ('③ 시장 폭 · 52주 신고가·신저가', n.get('breadth'), 3),
             ('④ 돈의 흐름 · 종목', ' '.join(x for x in (n.get('flow'), n.get('stocks')) if x), 4),
             ('⑤ 업종', n.get('sector'), 5)]
    if n.get('ledger'):
        parts.append(('실전 원장', n['ledger'], 2))
    if n.get('checkpoints'):
        parts.append(('체크포인트', '\n'.join(f'{i}. {c}' for i, c in enumerate(n['checkpoints'][:3], 1)), 2))
    foot = '사실에서 자동 작성 · 투자 권유 아님'

    def render(ps):
        out = [head]
        for h, body, _ in ps:
            if not body:
                continue
            b = body if h.startswith('📰') else _e(body)
            out.append((f'<b>{_e(h) if not h.startswith("📰") else h}</b>\n' if h else '') + b)
        out.append(foot)
        return '\n\n'.join(out)

    ps = list(parts)
    for pri in (5, 4, 3, 2, 1):        # 1단계: 첫 문장만
        if len(render(ps)) <= limit:
            break
        ps = [(h, _first(b) if p_ == pri and not h.startswith('📰') else b, p_) for h, b, p_ in ps]
    for pri in (5, 4, 3, 2):           # 2단계: 통째로 빼기
        if len(render(ps)) <= limit:
            break
        ps = [x for x in ps if x[2] != pri]
    txt = render(ps)
    return txt if len(txt) <= limit else txt[: limit - 1] + '…'


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
                ps.append(_half(p, side) if k in HALF else p)
        if not ps:
            continue
        out.append(ps[0] if len(ps) == 1 else _stack(ps, str(out_dir / f'stack_{s.replace("+", "_")}.png')))
    return out


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
    photos = build(rec, Path(tempfile.mkdtemp()))
    cap = caption(rec)
    print(f'{kind} {rec.get("date")} · 사진 {len(photos)}/{len(SHOTS)} · 캡션 {len(cap)}자')
    ok = send(chat, photos, cap)
    print('보냄 1통 → 소유자만' if ok else '발송 실패')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
