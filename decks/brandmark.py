# -*- coding: utf-8 -*-
"""부자알람 브랜드 마크 시안 — Pillow 벡터식 직접 그리기.

요구조건: ①흰 배경/어두운 배경 양쪽에서 성립 ②40px로 줄여도 형태가 읽힘
③단색(액센트 1도)로도 성립 ④주식/알람이라는 정체성이 형태에 보일 것.
"""
import sys, math
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from report import _font  # noqa: E402

AMBER = (0xb8, 0x6a, 0x00)
INK = (0x1a, 0x1d, 0x22)
WHITE = (0xff, 0xff, 0xff)
GREEN = (0x1a, 0x8a, 0x4c)


def _rr(dr, box, r, **kw):
    dr.rounded_rectangle(box, radius=r, **kw)


# ── A. 알람 종 + 상승 화살 ──────────────────────────────────────────────
def mark_a(dr, x, y, s, fg=AMBER, ink=INK):
    """종(bell) 실루엣 안에 상승 화살표 — '오르면 울린다'."""
    u = s / 100
    cx = x + s / 2
    # 종 몸통
    dr.pieslice([x + 18 * u, y + 12 * u, x + 82 * u, y + 84 * u], 180, 360, fill=fg)
    dr.rectangle([x + 18 * u, y + 48 * u, x + 82 * u, y + 72 * u], fill=fg)
    # 종 하단 립
    _rr(dr, [x + 10 * u, y + 70 * u, x + 90 * u, y + 80 * u], int(5 * u), fill=fg)
    # 종 추
    dr.ellipse([cx - 7 * u, y + 82 * u, cx + 7 * u, y + 96 * u], fill=fg)
    # 상승 화살 (음각)
    pts = [(x + 34 * u, y + 62 * u), (x + 47 * u, y + 44 * u),
           (x + 56 * u, y + 53 * u), (x + 70 * u, y + 33 * u)]
    dr.line(pts, fill=WHITE, width=max(2, int(7 * u)), joint='curve')
    dr.polygon([(x + 60 * u, y + 30 * u), (x + 73 * u, y + 28 * u), (x + 71 * u, y + 41 * u)], fill=WHITE)


# ── B. 링 다이얼 + 노치 ─────────────────────────────────────────────────
def mark_b(dr, x, y, s, fg=AMBER, ink=INK):
    """알람시계 다이얼 링을 열어 상승 화살이 뚫고 나가는 형태."""
    u = s / 100
    box = [x + 12 * u, y + 12 * u, x + 88 * u, y + 88 * u]
    dr.ellipse(box, outline=fg, width=max(2, int(11 * u)))
    # 우상단을 비워 화살이 지나갈 길
    dr.pieslice(box, -62, -8, fill=WHITE)
    pts = [(x + 30 * u, y + 66 * u), (x + 48 * u, y + 48 * u), (x + 60 * u, y + 58 * u), (x + 86 * u, y + 22 * u)]
    dr.line(pts, fill=ink, width=max(2, int(9 * u)), joint='curve')
    dr.polygon([(x + 72 * u, y + 18 * u), (x + 92 * u, y + 14 * u), (x + 88 * u, y + 34 * u)], fill=ink)


# ── C. 상승 캔들 + 알림 도트 ────────────────────────────────────────────
def mark_c(dr, x, y, s, fg=AMBER, ink=INK):
    """점점 커지는 캔들 3개 + 우상단 알림 도트."""
    u = s / 100
    bars = [(20, 62, 84), (42, 42, 84), (64, 26, 84)]
    for i, (bx, top, bot) in enumerate(bars):
        c = ink if i < 2 else fg
        _rr(dr, [x + bx * u, y + top * u, x + (bx + 17) * u, y + bot * u], int(4 * u), fill=c)
        # 심지
        dr.line([(x + (bx + 8.5) * u, y + (top - 9) * u), (x + (bx + 8.5) * u, y + (bot + 6) * u)],
                fill=c, width=max(1, int(3 * u)))
    dr.ellipse([x + 66 * u, y + 6 * u, x + 92 * u, y + 32 * u], fill=fg)
    dr.ellipse([x + 71 * u, y + 11 * u, x + 87 * u, y + 27 * u], fill=WHITE)
    dr.ellipse([x + 75 * u, y + 15 * u, x + 83 * u, y + 23 * u], fill=fg)


# ── D. 라운드 스퀘어 모노그램 ───────────────────────────────────────────
def mark_d(dr, x, y, s, fg=AMBER, ink=INK):
    """앱 아이콘형: 라운드 사각 배경 + 상승 라인 + B 각인."""
    u = s / 100
    _rr(dr, [x + 6 * u, y + 6 * u, x + 94 * u, y + 94 * u], int(24 * u), fill=fg)
    pts = [(x + 24 * u, y + 66 * u), (x + 42 * u, y + 48 * u), (x + 54 * u, y + 58 * u), (x + 76 * u, y + 30 * u)]
    dr.line(pts, fill=WHITE, width=max(2, int(8 * u)), joint='curve')
    dr.polygon([(x + 64 * u, y + 27 * u), (x + 82 * u, y + 24 * u), (x + 79 * u, y + 42 * u)], fill=WHITE)
    for i, bx in enumerate((26, 44, 62)):
        h = 10 + i * 6
        _rr(dr, [x + bx * u, y + (80 - h) * u, x + (bx + 11) * u, y + 80 * u], int(3 * u),
            fill=(255, 255, 255, 90) if False else WHITE)


MARKS = [('A. 알람 종 + 상승화살', mark_a), ('B. 링 다이얼 + 돌파', mark_b),
         ('C. 상승 캔들 + 알림', mark_c), ('D. 앱아이콘형 모노그램', mark_d)]


def lockup(dr, x, y, s, fn, fg=AMBER, ink=INK, word=True):
    """마크 + 워드마크 가로 조합."""
    fn(dr, x, y, s, fg, ink)
    if word:
        f1 = _font(True, int(s * 0.42))
        f2 = _font(False, int(s * 0.20))
        dr.text((x + s * 1.18, y + s * 0.16), '부자알람', font=f1, fill=ink)
        dr.text((x + s * 1.20, y + s * 0.64), 'buza_alarm_bot', font=f2, fill=(0x96, 0x9d, 0xa6))


def sheet(path):
    W, H = 1500, 1180
    im = Image.new('RGB', (W, H), WHITE)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, W, 8], fill=AMBER)
    dr.text((60, 40), '부자알람 브랜드 마크 시안', font=_font(True, 40), fill=INK)
    dr.text((60, 96), '각 행: 락업(마크+워드마크) · 마크 단독 96px · 축소 40px · 어두운 배경 반전',
            font=_font(False, 18), fill=(0x96, 0x9d, 0xa6))
    y = 160
    for name, fn in MARKS:
        dr.text((60, y), name, font=_font(True, 22), fill=AMBER)
        yy = y + 36
        lockup(dr, 60, yy, 96, fn)
        fn(dr, 620, yy, 96)
        fn(dr, 760, yy + 28, 40)
        # 어두운 배경 반전
        dr.rounded_rectangle([840, yy - 10, 1010, yy + 106], radius=14, fill=(0x14, 0x18, 0x1e))
        fn(dr, 866, yy + 6, 84, fg=(0xf0, 0xa5, 0x2a), ink=WHITE)
        # 단색(먹1도)
        fn(dr, 1060, yy, 96, fg=INK, ink=INK)
        dr.text((1180, yy + 34), '단색 1도', font=_font(False, 17), fill=(0x96, 0x9d, 0xa6))
        y += 250
        dr.line([(60, y - 40), (W - 60, y - 40)], fill=(0xe2, 0xe4, 0xe8), width=1)
    im.save(path)
    return path


if __name__ == '__main__':
    print(sheet(str(Path(__file__).resolve().parent / 'assets' / 'brandmark_concepts.png')))
