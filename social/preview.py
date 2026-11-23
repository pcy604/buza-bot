# -*- coding: utf-8 -*-
"""숏츠 미리보기 GIF — ffmpeg 없이 '움직이는 것'을 먼저 본다 (2026-11-23).

  python -m social.preview content/sihwang_2026-11-20.json

왜 GIF 인가
  이 PC 에 ffmpeg 이 없다(확인: PATH 없음 · cv2/imageio/moviepy 전부 없음). 설치는 차니 몫인데
  그 전에 **흐름이 괜찮은지부터 눈으로 봐야** 한다. PIL 만으로 되는 건 애니메이션 GIF 다.
  컷당 체류 시간은 내레이션 글자 수로 계산한다(한국어 TTS 대략 분당 330자).
  ffmpeg 이 깔리면 같은 프레임 PNG 를 그대로 mp4 로 묶는다 — 이 파일은 그때 버린다.

한계(먼저 적는다)
  · 소리가 없다. 자막으로만 판단해야 한다.
  · GIF 는 256색이라 차트 그라데이션이 뭉친다. 색 판정용이 아니라 **흐름·길이 판정용**이다.
  · 용량 때문에 540×960 으로 줄인다. 글자 크기 판정은 PNG 원본으로 한다.
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / 'social' / 'out' / 'frames'

CPS = 330 / 60          # 한국어 TTS 체감 속도(초당 글자)
MIN_S, MAX_S = 3.0, 9.0


def dwell(say: str) -> float:
    return max(MIN_S, min(MAX_S, len(say or '') / CPS))


def build(doc_path, scale=0.5):
    doc = json.loads(Path(doc_path).read_text(encoding='utf-8'))
    d = FRAMES / doc['slug']
    pngs = sorted(d.glob('cut*.png'))
    if not pngs:
        raise RuntimeError(f'프레임이 없다 — 먼저 `python -m social.frame {doc_path}`')
    cards = doc.get('cards') or []
    frames, durs = [], []
    for i, p in enumerate(pngs):
        im = Image.open(p).convert('RGB')
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        frames.append(im.convert('P', palette=Image.ADAPTIVE, colors=256))
        c = cards[i] if i < len(cards) else {}
        say = c.get('short_say') or c.get('say', '')
        durs.append(int(dwell(say) * 1000))
    out = d / f"{doc['slug']}_preview.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durs, loop=0, optimize=True)
    total = sum(durs) / 1000
    return out, total, durs


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out, total, durs = build(sys.argv[1])
    print(out)
    print(f'— {len(durs)}컷 · 총 {total:.1f}초 · 컷별 ' + ', '.join(f'{x / 1000:.1f}s' for x in durs))
    print(f'  용량 {out.stat().st_size / 1e6:.1f}MB')
