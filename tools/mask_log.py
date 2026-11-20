"""공개 레포 Actions 로그용 마스킹 — 2026-11-20. 텔레그램 채팅 ID(8~11자리 숫자)를 가린다.
사용: python run.py 2>&1 | python tools/mask_log.py   (run.yml 은 pipefail 로 run.py 실패를 그대로 전달)"""
import re
import sys

_ID = re.compile(r'(?<![\d.\-:/])(-?\d{8,11})(?![\d.])')


def mask(line: str) -> str:
    # 20261116 같은 날짜형(19xx/20xx 로 시작하는 8자리)은 남긴다
    return _ID.sub(lambda m: m.group(1) if re.fullmatch(r'(19|20)\d{6}', m.group(1)) else m.group(1)[:2] + '***', line)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    for ln in sys.stdin.buffer:
        sys.stdout.write(mask(ln.decode('utf-8', 'replace')))
