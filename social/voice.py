# -*- coding: utf-8 -*-
"""내레이션 음성 + 소리 있는 숏츠 영상 (2026-11-24).

  python -m social.voice content/sihwang_2026-11-20.json
  → <slug>_voiced.mp4   (1080x1920 · 소리 있음)

흐름
  ① 컷마다 Gemini TTS 로 wav 생성 (social/out/frames/<slug>/vo/cut01.wav ...)
  ② 실제 음성 길이를 재서 **컷 체류 시간을 그 길이에 맞춘다**
     — 글자 수 추정으로 맞추면 말이 잘리거나 빈 시간이 생긴다.
  ③ ffmpeg 으로 프레임 PNG + 음성을 묶어 mp4

ffmpeg 위치
  PATH 에 없고 winget 패키지 폴더에 있다(2026-11-24 확인):
  %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\ffmpeg-*\\bin\\ffmpeg.exe
  그래서 찾아 쓴다. PATH 에 있으면 그걸 먼저 쓴다.
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / 'social' / 'out' / 'frames'

VOICE = 'Charon'          # 차분한 남성 — 시황 낭독에 맞는다. 바꾸려면 Gemini 음성 목록 참고
MODEL = 'gemini-2.5-flash-preview-tts'
# 2026-11-28 'AI가 읽는 티' 줄이기 — 앵커 낭독(균일한 속도·억양)이 기계처럼 들렸다.
#   사람 진행자처럼: 핵심 숫자 앞에서 반 박자 쉼, 문장 끝을 내리고, 접속어(그런데·그래서)는 가볍게.
STYLE = ('경제 유튜브 진행자가 친구에게 오늘 시장을 짧게 브리핑하듯 자연스럽게 읽어 주세요. '
         '문장마다 속도를 조금씩 다르게 하고, 핵심 숫자 바로 앞에서 아주 짧게 쉬고, 문장 끝은 내려 주세요. '
         '뉴스 앵커처럼 딱딱하거나 과장된 톤은 피하세요: ')


def ffmpeg() -> str:
    p = shutil.which('ffmpeg')
    if p:
        return p
    base = Path(os.environ['LOCALAPPDATA']) / 'Microsoft' / 'WinGet' / 'Packages'
    for c in base.rglob('ffmpeg.exe'):
        return str(c)
    raise RuntimeError('ffmpeg 을 못 찾았다 — winget install Gyan.FFmpeg')


def tts(text: str, out: Path):
    """Gemini TTS → 16bit PCM wav. 응답은 raw PCM 이라 wav 헤더를 직접 씌운다."""
    import config
    from google import genai
    from google.genai import types
    # 2026-11-28 Actions 에서 400 'Unknown name speechConfig at generation_config' — 음성 출력은 v1beta 에만 있다. 판을 못 박는다.
    cl = genai.Client(api_key=config.GEMINI_KEY, http_options=types.HttpOptions(api_version='v1beta'))
    r = cl.models.generate_content(
        model=MODEL, contents=STYLE + text,
        config=types.GenerateContentConfig(
            response_modalities=['AUDIO'],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE)))))
    pcm = r.candidates[0].content.parts[0].inline_data.data
    with wave.open(str(out), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return out


def wav_sec(p: Path) -> float:
    with wave.open(str(p), 'rb') as w:
        return w.getnframes() / w.getframerate()


def build(doc_path, pad=0.45):
    doc = json.loads(Path(doc_path).read_text(encoding='utf-8'))
    d = FRAMES / doc['slug']
    pngs = sorted(d.glob('cut*.png'))
    if not pngs:
        raise RuntimeError(f'프레임이 없다 — 먼저 `python -m social.frame {doc_path}`')
    vo = d / 'vo'
    vo.mkdir(parents=True, exist_ok=True)
    FF = ffmpeg()

    secs = []
    for i, p in enumerate(pngs):
        c = doc['cards'][i] if i < len(doc['cards']) else {}
        line = c.get('short_say') or c.get('say') or ''
        w = vo / f'cut{i + 1:02d}.wav'
        if not w.exists():
            # Gemini 무료 티어는 TTS 가 **분당 3건**이다(2026-11-24 실측 429).
            #   이미 만든 wav 는 건너뛰므로 중간에 끊겨도 다시 돌리면 이어진다.
            for attempt in range(6):
                try:
                    print(f'  [{i + 1}/{len(pngs)}] 음성 생성…', flush=True)
                    tts(line, w)
                    break
                except Exception as e:
                    m = re.search(r"retryDelay': '(\d+)s", str(e)) or re.search(r'retry in ([\d.]+)s', str(e))
                    if '429' not in str(e) and 'RESOURCE_EXHAUSTED' not in str(e):
                        raise
                    wait = float(m.group(1)) + 3 if m else 25
                    print(f'      한도 — {wait:.0f}초 쉬고 재시도 ({attempt + 1}/6)', flush=True)
                    time.sleep(wait)
            else:
                raise RuntimeError(f'컷 {i + 1} 음성 생성 실패 — 한도가 계속 막는다')
        s = wav_sec(w) + pad          # 말 끝나고 조금 쉰다
        secs.append(s)
        print(f'  컷 {i + 1}: {s:.1f}초  {line[:34]}…', flush=True)

    # 음성 이어 붙이기
    lst = d / '_vo.txt'
    lst.write_text('\n'.join(f"file '{(vo / f'cut{i + 1:02d}.wav').as_posix()}'" for i in range(len(pngs))),
                   encoding='utf-8')
    allwav = d / '_vo_all.wav'
    subprocess.run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', str(lst),
                    '-af', f'apad=pad_dur={pad}', str(allwav)], check=True, capture_output=True)

    # 프레임 목록(컷별 체류 시간 = 그 컷 음성 길이)
    flist = d / '_frames.txt'
    rows = []
    for i, p in enumerate(pngs):
        rows.append(f"file '{p.as_posix()}'")
        rows.append(f'duration {secs[i]:.3f}')
    rows.append(f"file '{pngs[-1].as_posix()}'")      # concat 규격: 마지막 파일 한 번 더
    flist.write_text('\n'.join(rows), encoding='utf-8')

    out = d / f"{doc['slug']}_voiced.mp4"
    subprocess.run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', str(flist),
                    '-i', str(allwav),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-r', '30',
                    '-vf', 'scale=1080:1920:force_original_aspect_ratio=decrease,'
                           'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xF1F3F6',
                    '-c:a', 'aac', '-b:a', '128k', '-shortest', str(out)],
                   check=True, capture_output=True)
    for f in (lst, flist):
        f.unlink(missing_ok=True)
    return out, sum(secs)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    out, total = build(sys.argv[1])
    print(out)
    print(f'— {total:.1f}초 · {out.stat().st_size / 1e6:.1f}MB · 소리 있음')
