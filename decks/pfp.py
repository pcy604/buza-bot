# -*- coding: utf-8 -*-
"""stock_studian 인스타 프로필 사진 — 브랜드 마크(B안: 링 다이얼+돌파)를 고해상도·연두색으로.

인스타는 정사각으로 업로드받아 원형으로 크롭해 보여주므로, 마크를 캔버스
중앙에 여유를 두고 배치해 원형 크롭에서 잘리지 않게 한다.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brandmark as BM  # noqa: E402

# 연두색(spring/yellow-green) — 기존 브랜드의 amber를 이걸로 교체
GREEN = (0x7c, 0xb3, 0x42)
INK = (0x1a, 0x1d, 0x22)
WHITE = (0xff, 0xff, 0xff)


def render(size=1024, margin_ratio=0.16, bg=WHITE):
    """margin_ratio: 마크 바깥 여백 비율 — 원형 크롭 시 마크 끝(화살촉 등)이 안 잘리게."""
    im = Image.new('RGB', (size, size), bg)
    dr = ImageDraw.Draw(im)
    mark_size = size * (1 - margin_ratio * 2)
    off = (size - mark_size) / 2
    BM.mark_b(dr, off, off, mark_size, fg=GREEN, ink=INK)
    return im


if __name__ == '__main__':
    out = Path(__file__).resolve().parent / 'assets' / 'stock_studian_pfp.png'
    render().save(out)
    print(out)
