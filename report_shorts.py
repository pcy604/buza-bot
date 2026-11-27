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
    # 2026-11-28 발음 사전·숫자 반올림을 sihwang 과 한 곳에서(영문 약어를 철자로 읽던 'AI 낭독 티')
    from social.sihwang import LEX
    for a, b in LEX:
        if a not in ("·", "$", "&", "→", "~"):
            s = s.replace(a, b)
    s = re.sub(r"(\d+\.\d{2,})(?=\s*%)", lambda m: f"{float(m.group(1)):.1f}", s)
    s = re.sub(r"(\d{1,3}(?:,\d{3})+|\d{3,})\.\d+", r"\1", s)
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
    ix = {x.get("sym"): x for x in f.get("indices") or []}
    heads = ("^KS11", "^KQ11") if kind == "kr" else ("^GSPC", "^IXIC", "^DJI")   # 2026-11-28 미국은 3대 지수 다
    big = "\n".join(f"{ix[s_].get('name')} {ix[s_].get('d1', 0):+.1f}%" for s_ in heads if s_ in ix and ix[s_].get("d1") is not None)
    bc = (f.get("ctx") or {}).get("breadth") or {}
    first = lambda s: (str(s or "").split("\n") + [""])[0]
    why = n.get("explain") or (n.get("econ") or [""])[0] or ""
    # 컷 = 사진(SHOTS) 순서: 글로벌 마켓 → 업종 히트맵 → 시장 폭·신고가 → 오늘의 시장. 투자 신호등은 뺐다(차니 11-28)
    C = [
        (f"{RA.TITLE.get(kind, '시황')} · {rec.get('date')}", big, "",
         _cut(n.get("summary", "").split(". ")[0] + ". " + re.sub(r"\[\d+\]", "", why))),
        ("업종 히트맵", "", "", _cut(". ".join(str(n.get("sector", "")).split("\n")[:2]))),
        ("시장 폭 · 52주 신고가·신저가", f"{bc.get('today')}%" if bc.get('today') is not None else "", "오른 종목 비율",
         _cut(". ".join(str(n.get("breadth", "")).split("\n")[:3]))),
        ("오늘의 시장 · 돈이 몰린 종목", "", "", _cut(". ".join(x for x in (first(n.get("stocks")), first(n.get("flow"))) if x.strip()))),
    ]
    return C


def frame(title, big, big_label, sub, photo, idx, total) -> Image.Image:
    im = Image.new("RGB", (W, H), FR.BG)
    d = ImageDraw.Draw(im)
    d.text((60, 58), title, font=FR._font(46), fill=FR.INK2)
    d.text((W - 150, 62), f"{idx} / {total}", font=FR._font(32), fill=FR.INK2)
    if big and "\n" in big:      # 여러 지수 — 줄마다 색
        y0 = 118
        for ln in big.split("\n")[:3]:
            v = ln.rsplit(" ", 1)[-1]
            d.text((60, y0), ln, font=FR._font(64), fill=FR.ACCENT if v.startswith("-") else FR.POS if v.startswith("+") else FR.INK)
            y0 += 72
        big = ""
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


_ENGINE = {"name": None}


def tts(text: str, w: Path, FF: str):
    """Gemini TTS(차니 노트북에서 쓰던 목소리) → 실패하면 edge-tts(무료·키 없음, ko-KR-InJoonNeural).
    2026-11-26 Actions 에서 Gemini TTS 가 400(speechConfig 거부) — 모델·SDK 가 바뀌면 영상이 통째로 멈추지 않게."""
    if _ENGINE["name"] != "edge":
        for attempt in range(4):        # Gemini TTS 무료 = 분당 3건
            try:
                VO.tts(text, w)
                _ENGINE["name"] = "gemini"
                return
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(25)
                    continue
                print(f"  Gemini TTS 실패 → edge-tts: {str(e)[:400]}")
                break
        _ENGINE["name"] = "edge"
    import asyncio
    try:
        import edge_tts
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "edge-tts"], check=True)
        import edge_tts
    # 2026-11-28 'AI 날티' — InJoon 은 낭독체가 강하다. 대화체에 가까운 Hyunsu(다국어 신경망 음성)를 기본으로, 속도는 조금만 올린다.
    # 2026-11-28 차니 '높낮이 없고 속도가 너무 균일' — 문장마다 따로 읽혀 속도·높낮이를 조금씩 바꾸고, 문장 사이에 짧은 쉼.
    #   (edge 는 SSML 스타일을 막아 둬서 문장 단위로 rate·pitch 를 주는 게 할 수 있는 최대치다)
    voice = os.environ.get("TTS_VOICE", "ko-KR-HyunsuMultilingualNeural")
    sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", text) if x.strip()] or [text]
    pros = [("+6%", "+0Hz"), ("+0%", "-4Hz"), ("+10%", "+3Hz"), ("+3%", "-2Hz")]
    parts = []
    for i, sen in enumerate(sents):
        rate, pitch = pros[i % len(pros)]
        if i == 0:
            rate, pitch = "+4%", "+2Hz"          # 첫 문장 = 훅 — 조금 높게
        pm = w.with_name(f"{w.stem}_{i}.mp3")
        asyncio.run(edge_tts.Communicate(sen, voice, rate=rate, pitch=pitch).save(str(pm)))
        pw_ = w.with_name(f"{w.stem}_{i}.wav")
        subprocess.run([FF, "-y", "-i", str(pm), "-ar", "24000", "-ac", "1", "-af", "apad=pad_dur=0.18", str(pw_)],
                       check=True, capture_output=True)
        parts.append(pw_)
    lst = w.with_name(f"{w.stem}_list.txt")
    lst.write_text("\n".join(f"file '{x.as_posix()}'" for x in parts))
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "24000", "-ac", "1", str(w)],
                   check=True, capture_output=True)


def build(rec: dict, photos: list, out_dir: Path) -> Path:
    # 2026-11-28 빈 자막 컷(재료가 비는 날)은 빼고 순서를 당긴다 — 빈 문장을 TTS 에 보내 영상이 통째로 실패했다
    C = [c for c in cuts(rec) if len(re.sub(r"[\s.·,]", "", c[3] or "")) >= 5]
    FF = VO.ffmpeg()
    wavs, secs, pngs = [], [], []
    for i, (title, big, lab, sub) in enumerate(C):
        p = out_dir / f"cut{i + 1:02d}.png"
        ph = photos[i] if i < len(photos) else None
        if ph and title == "업종 히트맵":      # 가로로 긴 히트맵 → 왼쪽·오른쪽 반을 위아래로 이어 세로 화면을 채운다
            try:
                ph = RA._stack([RA._half(str(ph), "L"), RA._half(str(ph), "R")], str(out_dir / "heat_stack.png"))
            except Exception as e:
                print("  히트맵 세로 이어붙이기 실패:", e)
        frame(title, big, lab, sub, ph, i + 1, len(C)).save(p)
        pngs.append(p)
        w = out_dir / f"cut{i + 1:02d}.wav"
        tts(speak(sub), w, FF)
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
    print(f"쇼츠 {sum(secs):.0f}초 · 음성 {_ENGINE['name']} · {out}")
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
    photos = RA.build(rec, Path(tempfile.mkdtemp()), width=600)   # 2026-11-28 쇼츠 전용 600px 캡처(3열·2×4)
    for c in cuts(rec):
        print("  ·", speak(c[3]))
    mp4 = build(rec, photos, Path(tempfile.mkdtemp()))
    ok = send_video(chat, mp4, f"[쇼츠 미리보기] {RA.TITLE.get(rec.get('kind'))} · {rec.get('date')}")
    print("쇼츠 보냄 → 소유자만" if ok else "쇼츠 발송 실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
