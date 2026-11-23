# -*- coding: utf-8 -*-
"""숏츠 영상 파일 만들기 — ffmpeg 없이 (2026-11-24).

  python -m social.render content/sihwang_2026-11-20.json
  → social/out/frames/<slug>/<slug>.webm   (1080x1920 · 재생 가능한 진짜 영상 파일)

왜 이렇게 하나
  이 PC 에 ffmpeg 이 없다(PATH·Program Files·scoop·chocolatey 전부 확인). 설치는 차니 몫인데
  그 전에 **볼 수 있는 영상 파일**이 필요했다. GIF 도 웹 재생기도 "영상"이 아니었다.
  Playwright 는 이미 깔려 있고 **브라우저 녹화**를 지원한다 → 프레임을 전체화면으로
  넘기는 페이지를 띄워 놓고 그 화면을 그대로 녹화한다. 새로 받는 것이 하나도 없다.

  결과는 .webm 이다. 윈도우 11·크롬·엣지에서 바로 재생되고 유튜브·인스타가 받는다.
  ffmpeg 을 깔면 mp4 로 바꾸는 한 줄만 더 붙이면 된다(프레임은 그대로 쓴다).

한계(먼저 적는다)
  · 소리가 없다. TTS 는 다음 단계다.
  · 브라우저 녹화라 프레임 전환 순간에 한두 프레임이 흐를 수 있다. 정지컷 영상이라 티는 안 난다.
"""
import base64
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / 'social' / 'out' / 'frames'

W, H = 1080, 1920
CPS = 330 / 60
MIN_S, MAX_S = 3.0, 9.0


def dwell(say: str) -> float:
    return max(MIN_S, min(MAX_S, len(say or '') / CPS))


PAGE = """<title>r</title><style>
 html,body{margin:0;padding:0;background:#F1F3F6;overflow:hidden;width:%dpx;height:%dpx}
 img{position:absolute;inset:0;width:100%%;height:100%%;object-fit:cover;opacity:0}
 img.on{opacity:1}
</style><div id=s></div><script>
const C=__CUTS__, s=document.getElementById('s');
C.forEach(c=>{const i=document.createElement('img');i.src=c.img;s.appendChild(i);});
const im=[...s.children];
let k=0;
function show(i){im.forEach((x,j)=>x.classList.toggle('on',j===i));}
function step(){ show(k); if(k<C.length-1){ const d=C[k].sec*1000; k++; setTimeout(step,d); }
                 else { setTimeout(()=>{window.__done=true;}, C[k].sec*1000); } }
window.__start=()=>{window.__done=false;step();};
show(0);
</script>"""


def build(doc_path):
    from playwright.sync_api import sync_playwright
    doc = json.loads(Path(doc_path).read_text(encoding='utf-8'))
    d = FRAMES / doc['slug']
    pngs = sorted(d.glob('cut*.png'))
    if not pngs:
        raise RuntimeError(f'프레임이 없다 — 먼저 `python -m social.frame {doc_path}`')

    cuts = []
    for i, p in enumerate(pngs):
        c = doc['cards'][i] if i < len(doc['cards']) else {}
        cuts.append(dict(sec=round(dwell(c.get('short_say') or c.get('say', '')), 1),
                         img='data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode()))
    total = sum(c['sec'] for c in cuts)

    html = (PAGE % (W, H)).replace('__CUTS__', json.dumps(cuts))
    page_file = d / '_render.html'
    page_file.write_text(html, encoding='utf-8')

    vdir = d / '_vid'
    shutil.rmtree(vdir, ignore_errors=True)
    vdir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': W, 'height': H},
                            record_video_dir=str(vdir),
                            record_video_size={'width': W, 'height': H})
        p = ctx.new_page()
        p.goto(page_file.as_uri(), wait_until='load', timeout=120_000)
        time.sleep(1.5)                       # 첫 프레임이 뜬 상태로 시작하게
        p.evaluate('window.__start()')
        p.wait_for_function('window.__done === true', timeout=int((total + 30) * 1000))
        time.sleep(0.6)
        ctx.close()                           # close 해야 영상이 파일로 떨어진다
        b.close()

    src = next(iter(sorted(vdir.glob('*.webm'))), None)
    if not src:
        raise RuntimeError('녹화 파일이 안 생겼다 — playwright 버전 확인')
    out = d / f"{doc['slug']}.webm"
    if out.exists():
        out.unlink()
    shutil.move(str(src), str(out))
    shutil.rmtree(vdir, ignore_errors=True)
    page_file.unlink(missing_ok=True)
    return out, total


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out, total = build(sys.argv[1])
    print(out)
    print(f'— {total:.1f}초 · {out.stat().st_size / 1e6:.1f}MB · webm (윈도우·크롬·유튜브 모두 재생)')
