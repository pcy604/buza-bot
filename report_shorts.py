"""시황 쇼츠 — 카드뉴스 5장 + 같은 문장을 그대로 읽는다(2026-11-26 차니: "시황 내용만 안정화되면 그대로 읽어도 되지 않나").

새로 쓰는 문장은 없다. 바꾸는 건 두 가지뿐:
  ① 귀로 듣는 숫자 읽기(-0.6% → 마이너스 0.6퍼센트, 11-26 → 11월 26일, 이모지 제거)
  ② 컷마다 길이 제한(쇼츠 60초 안)
사진 = report_album 과 같은 5장(같은 순서) → 1080×1920 프레임(위: 컷 제목·큰 숫자 / 가운데: 사진 / 아래: 자막 = 읽는 문장).

  python -m report_shorts preview daily dash/preview_daily.json   → mp4 를 차니에게만
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw

import report_album as RA
from social import frame as FR
from social import voice as VO

W, H = 1080, 1920
CUT_CHARS = 115          # 한 컷 낭독 상한(한국어 TTS ≈ 초당 7자 → 5컷 ≈ 60초)
_EMOJI = re.compile(r"[🔺🔻▫️📊📰🟢🟡🔴🇰🇷🇺🇸①②③④⑤→]")


def speak(s: str) -> str:
    """귀로 듣는 숫자 읽기 — 뜻은 그대로."""
    s = _EMOJI.sub("", str(s or ""))
    s = s.replace("S&P500", "S&P 500").replace(" · ", ", ").replace("·", ", ").replace("%p", "퍼센트포인트")
    s = re.sub(r"\+(\d+(?:\.\d+)?)%", r"플러스 \1퍼센트", s)
    s = re.sub(r"(?<![\w.])-(\d+(?:\.\d+)?)%", r"마이너스 \1퍼센트", s)
    s = re.sub(r"(\d+(?:\.\d+)?)%", r"\1퍼센트", s)
    s = re.sub(r"\b(\d{1,2})-(\d{1,2})\b", lambda m: f"{int(m.group(1))}월 {int(m.group(2))}일", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    return s


def _cut(s: str, n=CUT_CHARS) -> str:
    """문장 단위로 n자 안까지."""
    out = ""
    for sent in re.split(r"(?<=[.다])\s+", s.replace("\n", ". ")):
        if len(out) + len(sent) > n and out:
            break
        out = (out + " " + sent).strip()
    return out[:n]


def cuts(rec: dict) -> list:
    """[(컷 제목, 큰 숫자, 큰 숫자 설명, 자막/낭독)] — 사진 5장과 같은 순서."""
    f = rec.get("facts") or {}
    n = f.get("narrative") or {}
    kind = rec.get("kind")
    lead = next((x for x in f.get("indices") or [] if x.get("sym") == ("^KS11" if kind == "kr" else "^IXIC")), {})
    bc = (f.get("ctx") or {}).get("breadth") or {}
    first = lambda s: (str(s or "").split("\n") + [""])[0]
    why = (n.get("econ") or [""])[0] or n.get("explain") or ""
    light_word = {"🟢": "초록불", "🟡": "노란불", "🔴": "빨간불"}.get(n.get("light"), "")
    C = [
        (f"{RA.TITLE.get(kind, '시황')} · {rec.get('date')}", f"{lead.get('d1', 0):+.1f}%" if lead else "", lead.get("name", ""),
         _cut(n.get("summary", "").split(". ")[0] + ". " + why)),
        ("투자 신호등", f"{n.get('light', '')} {light_word}", "", _cut(n.get("signal", ""))),
        ("시장 폭 · 52주 신고가·신저가", f"{bc.get('today')}%" if bc else "", "대형주 중 오른 종목 비율",
         _cut(". ".join(str(n.get("breadth", "")).split("\n")[:3]))),
        ("돈의 흐름 · 종목", "", "", _cut(first(n.get("stocks")) + ". " + first(n.get("flow")))),
        ("업종", "", "", _cut(". ".join(str(n.get("sector", "")).split("\n")[:2]))),
    ]
    return C


def frame(title, big, big_label, sub, photo, idx, total) -> Image.Image:
    im = Image.new("RGB", (W, H), FR.BG)
    d = ImageDraw.Draw(im)
    d.text((60, 58), title, font=FR._font(46), fill=FR.INK2)
    d.text((W - 150, 62), f"{idx} / {total}", font=FR._font(32), fill=FR.INK2)
    if big:
        col = FR.ACCENT if big.startswith("-") else FR.POS if big.startswith("+") else FR.INK
        d.text((60, 118), big, font=FR._font(120), fill=col)
        if big_label:
            d.text((62, 262), big_label, font=FR._font(32), fill=FR.INK2)
    top, bot = 330, 520
    mid_h = H - top - bot
    if photo and Path(photo).exists():
        c = Image.open(photo).convert("RGB")
        s = min((W - 40) / c.width, mid_h / c.height)
        c = c.resize((int(c.width * s), int(c.height * s)), Image.LANCZOS)
        im.paste(c, ((W - c.width) // 2, top + (mid_h - c.height) // 2))
    y = H - bot + 40
    for ln in FR._wrap(d, sub, FR._font(42), W - 120)[:6]:
        d.text((60, y), ln, font=FR._font(42), fill=FR.INK)
        y += 58
    d.text((60, H - 70), "사실에서 자동 작성 · 투자 권유 아님", font=FR._font(26, bold=False), fill=FR.INK2)
    return im


def build(rec: dict, photos: list, out_dir: Path) -> Path:
    C = cuts(rec)
    FF = VO.ffmpeg()
    wavs, secs, pngs = [], [], []
    for i, (title, big, lab, sub) in enumerate(C):
        p = out_dir / f"cut{i + 1:02d}.png"
        frame(title, big, lab, sub, photos[i] if i < len(photos) else None, i + 1, len(C)).save(p)
        pngs.append(p)
        w = out_dir / f"cut{i + 1:02d}.wav"
        for attempt in range(6):            # Gemini TTS 무료 = 분당 3건
            try:
                VO.tts(speak(sub), w)
                break
            except Exception as e:
                if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                    raise
                time.sleep(25)
        secs.append(VO.wav_sec(w) + 0.4)
        wavs.append(w)
    lst = out_dir / "_a.txt"
    lst.write_text("\n".join(f"file '{w.as_posix()}'" for w in wavs))
    allwav = out_dir / "all.wav"
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-af", "apad=pad_dur=0.4", str(allwav)],
                   check=True, capture_output=True)
    fl = out_dir / "_v.txt"
    fl.write_text("\n".join([x for i, p in enumerate(pngs) for x in (f"file '{p.as_posix()}'", f"duration {secs[i]:.3f}")]
                            + [f"file '{pngs[-1].as_posix()}'"]))
    out = out_dir / f"sihwang_{rec.get('kind')}_{rec.get('date')}.mp4"
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(fl), "-i", str(allwav), "-c:v", "libx264",
                    "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)],
                   check=True, capture_output=True)
    print(f"쇼츠 {sum(secs):.0f}초 · {out}")
    return out


def send_video(chat, path: Path, caption: str = "") -> bool:
    import requests
    import tg
    with open(path, "rb") as fh:
        r = requests.post(f"{tg.API}/sendVideo", data={"chat_id": chat, "caption": caption[:1000], "supports_streaming": "true"},
                          files={"video": fh}, timeout=300)
    return bool(r.ok and r.json().get("ok"))


def main(argv):
    if len(argv) < 4 or argv[1] != "preview":
        print(__doc__)
        return 2
    rec = json.load(open(argv[3], encoding="utf-8"))
    if not (rec.get("facts") or {}).get("narrative"):
        print("규칙 문장 없음")
        return 1
    import config
    chat = os.environ.get("OWNER_CHAT", "").strip() or str(getattr(config, "OWNER_CHAT", ""))
    photos, _cap, _bad = RA.build_checked(rec)
    for c in cuts(rec):
        print("  ·", speak(c[3]))
    mp4 = build(rec, photos, Path(tempfile.mkdtemp()))
    ok = send_video(chat, mp4, f"[쇼츠 미리보기] {RA.TITLE.get(rec.get('kind'))} · {rec.get('date')}")
    print("쇼츠 보냄 → 소유자만" if ok else "쇼츠 발송 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
