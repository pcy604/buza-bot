# -*- coding: utf-8 -*-
"""콘텐츠 숫자 대조 — 발행 전 필수 (2026-11-22)

content/*.json 에 적힌 성과 수치가 stock_screener 의 현행 산출물과 맞는지 본다.
2026-11-16 에 v1.9 수치가 20.66% → 17.16% → 17.73% 로 두 번 바뀌었는데
(선택 편향 제거 · 거래정지 손절 버그), 그 전에 쓴 콘텐츠가 옛 숫자를 들고 있다.

  python tools/content_numbers_audit.py            # 표로 보고
  python tools/content_numbers_audit.py --strict   # 폐기 수치가 있으면 exit 1 (발행 게이트용)

새 폐기 수치가 생기면 SUPERSEDED 에 (옛값, 현행값, 설명) 한 줄을 추가한다.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENER = os.path.join(os.path.dirname(ROOT), 'stock_screener')

# (정규식, 현행값, 왜 폐기됐나)
SUPERSEDED = [
    (r'20\.(?:7|66|85|9)\s*%?',  '17.73%',  'v1.9 CAGR — 재무 선택 편향 약 10%p 포함(2026-11-16)'),
    (r'−?-?27\.(?:6|65)\s*%?',   '-29.70%', 'v1.9 MDD — 같은 편향 · 거래정지 손절 버그(2026-11-20)'),
    (r'17\.16\s*%?',           '17.73%',  'v1.9 CAGR — 거래정지 주 손절이 가격 0 에 체결된 버그(2026-11-20)'),
    (r'−?-?32\.47\s*%?',       '-29.70%', 'v1.9 MDD — 같은 버그'),
    # 9.9% 는 '코스피' 가 같은 줄에 있을 때만 잡는다 — 미국 지수 설명에도 9.9% 가 나와
    # warmup_v7_bearhigh 에서 오탐이 났다(2026-11-22).
    (r'코스피[^\n]{0,30}9\.9\s*%?',  '8.83%',   '코스피 CAGR — 비교 기간·지수 기준 변경'),
    (r'10\.51\s*%?',           '8.83%',   '코스피 CAGR — 2026-11 이전 값'),
    (r'−?-?38\.69\s*%?',       '-44.11%', '코스피 MDD — 2026-11 이전 값'),
    (r'\b382\s*건',            '457건',   'v1.9 매도 건수 — 기간·패널 변경'),
]


def current():
    """현행 공표값. 콘텐츠가 참조해야 하는 유일한 원천."""
    p = os.path.join(SCREENER, 'results', 'v19_bt.json')
    d = json.load(open(p, encoding='utf-8'))
    return {k: d.get(k) for k in ('CAGR', 'MDD', 'BM_CAGR', 'BM_MDD', 'start', 'end', 'sells', 'win')}


def scan(path):
    """그 파일의 모든 문자열 값을 이어 붙여 폐기 수치를 찾는다."""
    d = json.load(open(path, encoding='utf-8'))
    blob = []

    def walk(v):
        if isinstance(v, str):
            blob.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(d)
    text = '\n'.join(blob)
    hits = []
    for rx, now, why in SUPERSEDED:
        seen = set()
        for m in re.finditer(r'.{0,45}(' + rx + r').{0,45}', text):
            tok = m.group(1)
            if tok in seen:                      # 같은 숫자는 한 번만
                continue
            seen.add(tok)
            hits.append(dict(found=tok, now=now, why=why,
                             context=m.group(0).replace('\n', ' ')))
    pcts = sorted(set(re.findall(r'−?-?\d+\.?\d*\s*%', text)))
    return hits, pcts


def main():
    strict = '--strict' in sys.argv
    cur = current()
    print('현행 공표값 (results/v19_bt.json):')
    for k, v in cur.items():
        print(f'  {k:9s} {v}')
    cdir = os.path.join(ROOT, 'content')
    bad, clean = [], []
    for f in sorted(os.listdir(cdir)):
        if not f.endswith('.json') or f.startswith('ledger_'):
            continue
        hits, pcts = scan(os.path.join(cdir, f))
        (bad if hits else clean).append((f, hits, pcts))

    print(f'\n{"="*78}\n🔴 폐기된 수치가 든 콘텐츠 — 발행 전 수정 필수 ({len(bad)}건)\n{"="*78}')
    for f, hits, _ in bad:
        print(f'\n{f}')
        for h in hits:
            print(f'   {h["found"]:>10s} → 현행 {h["now"]:>9s}   {h["why"]}')
            if h['context']:
                print(f'              …{h["context"]}…')

    print(f'\n{"="*78}\n⚪ 폐기 수치는 없음 — 다만 아래 퍼센트는 사람이 눈으로 볼 것 ({len(clean)}건)\n{"="*78}')
    for f, _, pcts in clean:
        print(f'  {f:34s} {" ".join(pcts[:12]) if pcts else "(수치 없음)"}')

    print(f'\n합계: 전체 {len(bad) + len(clean)}건 · 수정 필요 {len(bad)}건 · 자동검사 통과 {len(clean)}건')
    print('※ "통과" 는 알려진 폐기 수치가 없다는 뜻이다. 모든 숫자가 맞다는 보증이 아니다.')
    if strict and bad:
        print('\n::error::폐기된 수치가 든 콘텐츠가 있다 — 발행 중단')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
