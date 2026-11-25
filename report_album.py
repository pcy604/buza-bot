"""장 마감 시황 — 사이트 화면 + 문장 '카드뉴스'(2026-11-25 차니: "사이트 이미지랑 텍스트를 섞어서").

한 장 = 종합 탭 화면 한 구역(그대로 캡처) + 그 구역을 말하는 문장 2~3줄.
문장은 대시보드 market_narrate 가 사실에서 직접 만든 것(rec.facts.narrative) — 여기서 새로 쓰지 않는다.
같은 묶음이 그대로 인스타 캐러셀·쇼츠 컷의 원재료가 된다.

  python -m report_album preview kr      → 차니에게만(OWNER_CHAT)
  python -m report_album preview daily
  python -m report_album preview kr dash/preview_kr.json   → 발행 전 새 판으로
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

# (캡처 키, 문장 키, 머리말) — 종합 탭 순서
PLAN = {
    'kr': [('global', ('summary',), '오늘 한국 장'), ('pulse', ('direction',), '시장 방향'),
           ('week52', ('week52',), '52주 신고가·신저가'), ('trend', ('breadth',), '시장 폭'),
           ('today', ('flow', 'stocks'), '돈의 흐름과 종목'), ('heatmap', ('sector',), '업종')],
    'daily': [('global', ('summary',), '간밤 미국 장'), ('pulse', ('direction',), '시장 방향'),
              ('week52', ('week52',), '52주 신고가·신저가'), ('trend', ('breadth',), '시장 폭'),
              ('today', ('stocks', 'flow'), '종목과 자산'), ('heatmap', ('sector',), '업종')],
}
_TITLE = {'kr': '한국 장 마감 시황', 'daily': '미국 장 마감 시황'}


def load(kind: str) -> dict:
    db = requests.get(RAW, timeout=30).json()
    return db.get(f'latest_{kind}') or {}


def _e(s):
    return html.escape(str(s or ''))


def captions(rec: dict) -> list:
    """PLAN 순서대로 (캡처 키, 캡션). 첫 장에 제목·날짜·'왜'를 붙인다. 텔레그램 캡션 한도 1024자."""
    kind = rec.get('kind')
    n = (rec.get('facts') or {}).get('narrative') or {}
    out = []
    for i, (shot, keys, head) in enumerate(PLAN.get(kind, [])):
        body = "\n".join(n[k] for k in keys if n.get(k))
        if not body:
            continue
        cap = ''
        if i == 0:
            cap = f"<b>📰 {_TITLE.get(kind, '시황')} · {_e(rec.get('date'))}</b>\n\n"
        cap += f"<b>{i + 1}. {_e(head)}</b>\n{_e(body)}"
        if i == 0 and n.get('why'):
            cap += '\n\n<b>왜 움직였나</b> (뉴스 제목 그대로)\n' + '\n'.join('· ' + _e(w) for w in n['why'][:2])
        out.append((shot, cap[:1020]))
    return out


def closing(rec: dict) -> str:
    n = (rec.get('facts') or {}).get('narrative') or {}
    L = []
    if n.get('ledger'):
        L += ['<b>실전 원장</b> (규칙대로 운용하는 실제 계좌)', _e(n['ledger']), '']
    if n.get('checkpoints'):
        L += ['<b>체크포인트</b>'] + [f'{i}. {_e(c)}' for i, c in enumerate(n['checkpoints'], 1)] + ['']
    L.append(f"<a href=\"{config.DASHBOARD_URL}\">사이트에서 전체 보기</a> · 사실에서 자동 작성 · 투자 권유 아님")
    return '\n'.join(L)


# 2026-11-26 차니: "한국·미국 카드뉴스 보낼 때 종목 각 시장에 맞게" — 한·미가 나란히 그려진 구역은 반쪽만.
#   왼쪽 = 한국(코스피·코스닥 / KR 막대), 오른쪽 = 미국(S&P500·나스닥 / US 막대). 오늘의 시장·히트맵은 토글로 이미 시장별.
HALF = {'pulse', 'week52', 'trend'}


def _half(path: str, side: str) -> str:
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    box = (0, 0, w // 2 + 6, h) if side == 'L' else (w // 2 - 6, 0, w, h)
    out = path.replace('.png', f'_{side}.png')
    im.crop(box).save(out)
    return out


def ensure_browser():
    """실제 발송 실행(run.yml)에는 브라우저가 없다 — 보낼 리포트가 있을 때만 설치(매 실행 설치는 분 낭비)."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'playwright'], check=True)
    marker = Path.home() / '.cache' / 'ms-playwright'
    if not any(marker.glob('chromium*')) if marker.exists() else True:
        import subprocess
        subprocess.run([sys.executable, '-m', 'playwright', 'install', '--with-deps', 'chromium'], check=True)


def build(rec: dict, out_dir: Path) -> list:
    """[(png 경로 또는 None, 캡션)] — 캡처에 실패한 구역은 문장만 보낸다(빈 화면을 보내지 않는다)."""
    from social import shot
    caps = captions(rec)
    us = rec.get('kind') == 'daily'
    got = (shot.shot_cards([k for k, _ in caps], out_dir=out_dir, mkt='US' if us else 'KR',
                           expect=None if os.environ.get('ALBUM_NO_EXPECT') else rec.get('date')) if caps else {})
    out = []
    for k, c in caps:
        png = str(got[k]) if k in got else None
        if png and k in HALF:
            try:
                png = _half(png, 'R' if us else 'L')
            except Exception as e:
                print(f'[카드뉴스] 반쪽 자르기 실패 {k}: {e}')
        out.append((png, c))
    return out


def send(chat, items: list, tail: str) -> int:
    ok = 0
    for png, cap in items:
        ok += bool(tg.send_photo(chat, png, cap) if png else tg.send_message(chat, cap))
    if tail:
        ok += bool(tg.send_message(chat, tail))
    return ok


def main(argv):
    if len(argv) < 3 or argv[1] != 'preview':
        print(__doc__)
        return 2
    kind = argv[2]
    # 세 번째 인자 = 대시보드 미리보기 JSON(발행 안 한 새 판). 없으면 발행된 판
    rec = json.load(open(argv[3], encoding="utf-8")) if len(argv) > 3 else load(kind)
    if not (rec.get('facts') or {}).get('narrative'):
        print(f'⚠️ {kind} 리포트에 규칙 문장(narrative)이 없다 — 대시보드가 새 경로로 만든 판인지 확인 · engine={rec.get("engine")}')
        return 1
    chat = os.environ.get('OWNER_CHAT', '').strip() or str(getattr(config, 'OWNER_CHAT', ''))
    items = build(rec, Path(tempfile.mkdtemp()))
    print(f'{kind} {rec.get("date")} · 이미지 {sum(1 for p, _ in items if p)}/{len(items)}')
    n = send(chat, items, closing(rec))
    print(f'보냄 {n}건 → 소유자만')
    return 0 if n else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
