# -*- coding: utf-8 -*-
"""커밋 전 러너 조건 사전 점검 — "로컬에서 되네"를 완료 신호로 쓰지 않기 위해.

    python decks/preflight.py

## 왜 만들었나

2026-08-11~15 사이에 사용자가 폰에서 리포트를 받으려다 연달아 실패했다. 원인을
분류하니 새로운 이유가 매번 생긴 게 아니라 **같은 세 종류가 반복**됐다:

| 유형 | 실제 사례 |
|---|---|
| 로컬 ≠ 러너 | 3.14로 쓴 f-string이 러너(3.11)에서 SyntaxError · `probe.py` 미커밋 · 브랜드 로고가 gitignore된 `out/`에 있어 import가 죽음 |
| 모른다 ≠ 0 | autogen이 `None`을 `0`으로 바꿔 써서 매출 100% 부문이 "데이터 없음"으로 숨겨짐 |
| 실패가 조용함 | 워크플로는 초록불인데 사용자는 "실패했어요"만 받음 |

공통점은 **검증 지점이 틀렸다**는 것이다. 로컬 성공을 완료로 삼았는데 로컬은
러너를 대변하지 못한다. 사고가 날 때마다 CI에 가드를 하나씩 붙였지만 그건
사후 대응이고, 그때는 이미 사용자가 폰 앞에서 기다린 뒤다.

이 스크립트는 그 가드들을 **커밋 전에 한 번에** 돌린다. 여기서 통과해야
"됐다"고 말할 수 있다.

## 검사 항목

1. 러너와 같은 파이썬(3.11)으로 전 파일 컴파일 — 버전 전용 문법 차단
2. 러너가 실제로 임포트하는 목록 그대로 임포트 — 미커밋 모듈 차단
3. 코드가 여는 파일이 git에 없는지 — gitignore된 자산 참조 차단
4. 종목 데이터의 유령 0 스캔 — "모른다"를 0으로 쓴 자리 차단
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / 'decks'
PY311 = Path(r'C:\Users\lg\AppData\Local\Python\pythoncore-3.11-64\python.exe')

# run.yml의 임포트 검사와 **같은 목록**이어야 한다. 여기서 통과하고 러너에서
# 죽으면 이 스크립트의 존재 이유가 없어진다.
ROOT_MODS = ['bot', 'run', 'deck_live', 'deck_store', 'brief']
DECK_MODS = ['probe', 'build', 'check', 'autogen', 'autogen_kr', 'sources_kr', 'deck_pages',
             'officers', 'summarize', 'checkpoints', 'refresh']

fails, warns = [], []

# 이 PC의 기본 콘솔은 CP949라 아래 출력의 ✓·─ 에서 UnicodeEncodeError로 죽는다.
# 그러면 검사 결과를 보기도 전에 스크립트가 끝나 게이트가 통과인지 실패인지 알 수 없다 —
# 환경 때문에 못 도는 게이트는 없는 게이트와 같으므로 출력 인코딩을 먼저 고정한다.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def _run(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', cwd=str(ROOT), **kw)


def check_compile():
    """러너 파이썬으로 전 파일 컴파일."""
    py = str(PY311) if PY311.exists() else sys.executable
    r = _run(py, '-m', 'compileall', '-q', '.', '-x', r'(\.venv|__pycache__|node_modules)')
    if r.returncode:
        fails.append(('문법(러너 3.11)', (r.stdout + r.stderr).strip()[:400]))
    else:
        print(f'  ✓ 문법 — 러너와 같은 파이썬으로 전 파일 컴파일')


def check_imports():
    """러너가 임포트하는 것을 그대로 임포트."""
    py = str(PY311) if PY311.exists() else sys.executable
    code = (f'import sys; sys.path.insert(0, "decks");'
            f'import {", ".join(ROOT_MODS)};'
            f'import {", ".join(DECK_MODS)}')
    r = _run(py, '-c', code)
    if r.returncode:
        fails.append(('임포트(모듈 누락)', (r.stdout + r.stderr).strip()[-400:]))
    else:
        print(f'  ✓ 임포트 — 루트 {len(ROOT_MODS)}개 · decks {len(DECK_MODS)}개')


def check_tracked_assets():
    """코드가 여는 파일이 git에 실제로 있나.

    브랜드 로고가 gitignore된 `out/`에 있어 러너에서 `import deck_pages`가
    통째로 죽은 적이 있다. 소스에서 열리는 경로 문자열을 뽑아 추적 여부를 본다."""
    tracked = set(_run('git', 'ls-files').stdout.split('\n'))
    pat = re.compile(r"""parent\s*/\s*'([^']+)'\s*/\s*'([^']+)'""")
    bad = []
    for f in sorted(DECKS.glob('*.py')) + sorted(ROOT.glob('*.py')):
        src = f.read_text(encoding='utf-8', errors='replace')
        for m in pat.finditer(src):
            rel = f'{f.parent.name}/{m.group(1)}/{m.group(2)}'
            if not (ROOT / rel).exists():
                continue
            if rel not in tracked:
                bad.append(f'{f.name} → {rel} (파일은 있는데 git에 없음)')
    if bad:
        fails.append(('추적 안 되는 자산', '\n'.join(bad)))
    else:
        print('  ✓ 자산 — 코드가 여는 파일이 전부 git에 있음')


def check_ghost_zeros():
    """종목 데이터에서 '모른다'를 0으로 써둔 자리."""
    bad = []
    for f in sorted(DECKS.glob('*_data.py')):
        src = f.read_text(encoding='utf-8', errors='replace')
        m = re.search(r"'by_line':\s*\[(.*?)\]", src, re.S)
        if not m:
            continue
        vals = re.findall(r"\(\s*'[^']*'\s*,\s*([^,]+),", m.group(1))
        nums = [v.strip() for v in vals]
        if nums and all(re.fullmatch(r'0(\.0+)?', v) for v in nums):
            bad.append(f'{f.name}: 부문 {len(nums)}개가 전부 0 — 모르면 None')
    if bad:
        fails.append(('유령 0', '\n'.join(bad)))
    else:
        print('  ✓ 유령 0 — 종목 데이터에 전부-0 부문 없음')


def check_vendored_dart():
    """decks/dart_client.py 는 stock_screener 레포에서 가져온 **사본**이다.

    사본은 반드시 드리프트한다 — 그게 이 방식의 알려진 대가다. 대가를 치르되
    조용히 치르지는 않는다: 원본이 옆에 있으면 해시를 대조하고, 없으면(러너 등)
    사본 자신의 무결성만 확인한다. 원본 부재는 실패가 아니다 — 그걸 실패로 잡으면
    러너에서 항상 빨간불이 떠서 아무도 안 보게 된다.
    """
    import hashlib

    def _norm_sha(path):
        """**줄바꿈을 정규화한 뒤** 해시한다. 원시 바이트로 재면 윈도(CRLF)에서 기록한
        해시가 우분투 러너(LF 체크아웃)에서 항상 어긋나, 매 CI 실행마다 빨간불이 뜬다
        — 실제로 그렇게 만들었다가 잡았다. 항상 틀리는 게이트는 아무도 안 본다."""
        crlf, lf = bytes([13, 10]), bytes([10])
        return hashlib.sha256(path.read_bytes().replace(crlf, lf)).hexdigest()

    vend = DECKS / 'dart_client.py'
    sidecar = DECKS / '.dart_client.upstream.sha256'
    if not vend.exists():
        fails.append(('이식 DART', 'decks/dart_client.py 없음 — 한국주식 재무 전체가 죽는다'))
        return
    if not sidecar.exists():
        fails.append(('이식 DART', '.dart_client.upstream.sha256 없음 — 드리프트를 잴 기준이 없다'))
        return
    cur = _norm_sha(vend)
    if cur != sidecar.read_text(encoding='utf-8').strip():
        fails.append(('이식 DART',
                      '사본이 기록된 해시와 다름 — 사본을 직접 고쳤다는 뜻이다. '
                      'stock_screener/dart_client.py 에 먼저 고치고 다시 복사할 것.'))
        return
    up = ROOT.parent / 'stock_screener' / 'dart_client.py'
    if not up.exists():
        print('  ✓ 이식 DART — 사본 무결(원본 없는 환경이라 상류 대조는 생략)')
    elif _norm_sha(up) != cur:
        fails.append(('이식 DART',
                      '상류(stock_screener)가 앞서 있음 — decks/dart_client.py 재복사 필요. '
                      'cp 후 sha256 을 .dart_client.upstream.sha256 에 다시 기록할 것.'))
    else:
        print('  ✓ 이식 DART — 상류와 바이트 동일')


def main():
    print('러너 조건 사전 점검\n' + '─' * 52)
    check_compile()
    check_imports()
    check_tracked_assets()
    check_ghost_zeros()
    check_vendored_dart()
    print('─' * 52)
    if not fails:
        print('통과 — 커밋해도 러너에서 같은 이유로 죽지 않는다')
        return 0
    for name, detail in fails:
        print(f'\n✗ {name}')
        for line in str(detail).splitlines()[:8]:
            print(f'    {line}')
    print(f'\n실패 {len(fails)}건 — 고치기 전엔 "됐다"고 말하지 않는다')
    return 1


if __name__ == '__main__':
    sys.exit(main())
