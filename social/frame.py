# -*- coding: utf-8 -*-
"""숏츠 프레임 생성기 — 카드 PNG + 자막 → 1080×1920 한 장 (2026-11-23).

  python -m social.frame content/sihwang_2026-11-20.json
  python -m social.frame content/sihwang_2026-11-20.json --zoom   # 글자 위주 카드를 꽉 채움

왜 PNG 인가
  ffmpeg 이 아직 이 PC 에 없다. 프레임을 PNG 로 뽑아 두면 **오늘 당장** 캡컷 등에 끌어다
  영상을 만들 수 있고, ffmpeg 이 깔리면 같은 PNG 를 그대로 이어 붙여 자동 조립한다.
  즉 이 단계는 버려지는 작업이 아니다.

프레임 구성 (1080×1920)
  ┌──────────────────┐
  │ 훅 / 컷 제목        │  상단 320
  ├──────────────────┤
  │ 카드 이미지          │  가운데 — 폭 맞춤(기본) 또는 확대(--zoom)
  ├──────────────────┤
  │ 자막 (3~4줄)        │  하단 안전영역 440
  └──────────────────┘
  히트맵·글로벌처럼 가로로 넓은 카드는 확대하면 못 읽으므로 **폭 맞춤 고정**이다.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'social' / 'out' / 'frames'
CARDS = ROOT / 'social' / 'out'

W, H = 1080, 1920
TOP_H, BOT_H = 320, 440
BG = (241, 243, 246)
INK = (15, 23, 42)
INK2 = (71, 85, 105)
ACCENT = (220, 38, 38)
POS = (22, 125, 60)

# 넓은 카드는 확대 금지 — 확대하면 글자가 화면 밖으로 나간다
WIDE = {'global', 'global_risk', 'heatmap'}

_FONTS = [
    r'C:\Windows\Fonts\malgunbd.ttf', r'C:\Windows\Fonts\malgun.ttf',
    '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
]


def _font(sz, bold=True):
    for p in _FONTS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                continue
    raise RuntimeError('한글 폰트를 못 찾았다 — social/frame._FONTS 에 경로를 추가할 것')


def _wrap(draw, text, font, max_w):
    """한국어는 공백이 적어 단어 단위로만 끊으면 넘친다 → 글자 단위로도 끊는다."""
    out, line = [], ''
    for ch in text:
        t = line + ch
        if draw.textlength(t, font=font) > max_w and line:
            out.append(line)
            line = ch.lstrip()
        else:
            line = t
    if line:
        out.append(line)
    return out


def frame(card: dict, hook: str, idx: int, total: int, zoom=False) -> Image.Image:
    im = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(im)

    # ── 상단: 컷 제목 + 오늘의 숫자 하나(크게)
    #   카드 이미지가 가로로 넓어 9:16 에서 위가 크게 빈다. 그 자리를 숫자로 쓴다(2026-11-23).
    f_head, f_big, f_sub = _font(46), _font(132), _font(32)
    d.text((60, 58), card.get('card', ''), font=f_head, fill=INK2)
    big, lab = card.get('big') or '', card.get('big_label') or ''
    if big:
        col = ACCENT if big.startswith('-') or big.startswith('−') else (
            POS if big.startswith('+') else INK)
        d.text((60, 118), big, font=f_big, fill=col)
        if lab:
            d.text((62, 268), lab, font=f_sub, fill=INK2)
    elif idx == 1 and hook:
        y = 124
        for ln in _wrap(d, hook, _font(52), W - 120)[:3]:
            d.text((60, y), ln, font=_font(52), fill=INK)
            y += 64
    d.text((W - 150, 62), f'{idx} / {total}', font=f_sub, fill=INK2)

    # ── 가운데: 카드 이미지
    src = CARDS / f"card_m_{card.get('capture')}.png"
    if not src.exists():
        src = CARDS / f"card_w_{card.get('capture')}.png"
    mid_top, mid_h = TOP_H + 20, H - TOP_H - BOT_H - 40
    if src.exists():
        c = Image.open(src).convert('RGB')
        wide = card.get('capture') in WIDE
        scale = (W - 36) / c.width
        if zoom and not wide:
            scale = min((W - 20) / c.width, mid_h / c.height) * 1.0
        nw, nh = int(c.width * scale), int(c.height * scale)
        if nh > mid_h:                       # 세로가 넘치면 세로 기준으로 다시
            scale = mid_h / c.height
            nw, nh = int(c.width * scale), int(c.height * scale)
        c = c.resize((nw, nh), Image.LANCZOS)
        im.paste(c, ((W - nw) // 2, mid_top + (mid_h - nh) // 2))
    else:
        d.text((60, mid_top + 40), f"(카드 없음: {card.get('capture')})", font=f_sub, fill=ACCENT)

    # ── 하단: 자막 — 음성과 같은 문장을 보여 준다(무음 시청이 많다)
    f_cap = _font(42)
    _all = _wrap(d, card.get('text', ''), f_cap, W - 120)
    lines = _all[:4]
    if len(_all) > 4:                      # 숏츠 자막은 4줄이 한계다 — 넘으면 줄인다
        lines[-1] = lines[-1][:-1] + '…'
    y = H - BOT_H + 40
    for ln in lines:
        d.text((60, y), ln, font=f_cap, fill=INK)
        y += 58
    return im


def build(doc_path, zoom=False):
    doc = json.loads(Path(doc_path).read_text(encoding='utf-8'))
    cards = doc.get('cards') or []
    if not cards:
        raise RuntimeError('cards 가 없다 — social.sihwang 으로 만든 파일인가')
    out = OUT / doc['slug']
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for i, c in enumerate(cards, 1):
        p = out / f'cut{i:02d}_{c.get("capture")}.png'
        frame(c, doc.get('hook', ''), i, len(cards), zoom).save(p)
        made.append(p)
    # 내레이션 대본도 같이 — 캡컷에 붙여 넣거나 TTS 에 먹인다
    script = '\n\n'.join(f"[{i}] {c.get('card')}\n{c.get('say', '')}" for i, c in enumerate(cards, 1))
    (out / 'narration.txt').write_text(script, encoding='utf-8')
    return made, out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    made, out = build(sys.argv[1], '--zoom' in sys.argv)
    for p in made:
        print(p)
    print(f'— {len(made)}장 · 내레이션 {out / "narration.txt"}')
