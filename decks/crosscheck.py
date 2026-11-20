# -*- coding: utf-8 -*-
"""같은 지표가 두 군데에 다른 값으로 적히는 것을 찾아 **고친다**.

    python crosscheck.py WDAY          # 진단만
    python crosscheck.py WDAY --fix    # 파일을 고침
    python crosscheck.py --all [--fix]

왜 필요한가 (2026-08-17 WDAY 실측)
  RESULTS.kpis   ('영업이익', '$338.0M', '+767% YoY', 'up')
  RESULTS.facts  ('GAAP 영업이익', '전년비 762% 증가', '$338M')
  같은 2p 안에 767%와 762%가 나란히 찍혔다. EDGAR로 계산하면 338/39−1 = +766.7%
  이므로 767%가 맞다. 독자가 페이지 한 장만 봐도 발견하는 종류의 오류다.

어느 쪽이 원천인가
  `autogen._kpi_rows()`는 **LLM을 안 쓰고** XBRL 분기 시계열에서 직접 계산한다.
  반면 `facts`는 LLM B가 쓴 서술이다. 그래서 **kpis가 원천이고 facts를 교정한다.**

안전장치 — 자동 수정은 아래를 모두 만족할 때만 한다.
  · facts의 금액과 kpis의 금액이 (1% 이내로) 같다 → 같은 지표를 말하는 게 확실
  · 양쪽 다 퍼센트를 갖고 있고, 그 값이 0.5%p 넘게 다르다
  · 원문에서 교체 대상 문자열이 정확히 한 번만 나온다
  금액 자체가 다르면(예: $338M vs $340M) 어느 쪽이 맞는지 단정할 수 없으므로
  **고치지 않고 보고만** 한다 — 같은 라벨이라도 GAAP/Non-GAAP처럼 다른 지표일 수 있다.
"""
import importlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MONEY = re.compile(r'\$\s*(-?[\d,]+(?:\.\d+)?)\s*([BMK]?)', re.I)
PCT = re.compile(r'([+-]?\d+(?:\.\d+)?)\s*%')
MULT = {'B': 1e9, 'M': 1e6, 'K': 1e3, '': 1.0}


def _money(text):
    """문자열에서 첫 금액을 숫자로. '$338.0M' → 338000000.0"""
    m = MONEY.search(str(text or ''))
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', '')) * MULT[m.group(2).upper()]
    except Exception:
        return None


def _pct(text):
    m = PCT.search(str(text or ''))
    return float(m.group(1)) if m else None


def _same_money(a, b, tol=0.01):
    if a is None or b is None or a == 0:
        return False
    return abs(a - b) / abs(a) <= tol


# 라벨에서 수식어를 걷어내고 남는 핵심어로 "같은 지표인가"를 본다.
_STRIP = ('GAAP', 'Non-GAAP', 'non-gaap', '총', '연결', '분기', '당기', '전사', ' ', '·')


def _key(label):
    s = str(label or '')
    for w in _STRIP:
        s = s.replace(w, '')
    return s.strip()


def _same_metric(klabel, flabel):
    """금액이 우연히 비슷한 다른 지표를 같은 것으로 보지 않기 위한 게이트.

    2026-08-17 실측: AAPL에서 kpis '영업현금흐름 $53.92B'와 facts 'iPhone 매출
    $54.3B'가 금액 차이 0.70%로 1% 허용치에 걸려 매칭됐다. 라벨 검사가 없으면
    자동 수정이 멀쩡한 iPhone 매출 증가율을 80%로 덮어쓴다 — 실제로 그럴 뻔했다.
    금액 일치만으로는 절대 부족하다.
    """
    a, b = _key(klabel), _key(flabel)
    if not a or not b:
        return False
    return a in b or b in a


def scan(mod):
    """[(종류, 메시지, 원문문자열, 교체문자열)] — 교체문자열이 None이면 수정 불가."""
    R = getattr(mod, 'RESULTS', {}) or {}
    kpis = R.get('kpis') or []
    facts = R.get('facts') or []
    out = []

    for f in facts:
        f = list(f)
        # facts 행은 (라벨, 설명, 값) 형태. 금액은 보통 마지막 칸에 있다.
        fval = next((_money(x) for x in reversed(f) if _money(x) is not None), None)
        if fval is None:
            continue
        for k in kpis:
            kval = _money(k[1] if len(k) > 1 else '')
            if not _same_money(kval, fval):
                continue
            if not _same_metric(k[0], f[0]):
                continue
            kp, fp = _pct(k[2] if len(k) > 2 else ''), None
            fi = None
            for i, x in enumerate(f):
                if _pct(x) is not None and _money(x) is None:
                    fp, fi = _pct(x), i
                    break
            if kp is None or fp is None:
                continue
            if abs(kp - fp) <= 0.5:
                continue
            old = str(f[fi])
            # 퍼센트 숫자만 갈아끼운다 — 나머지 문장은 그대로 둔다
            new = PCT.sub(lambda m: f'{kp:+.0f}%'.lstrip('+') if not str(m.group(1)).startswith(('+', '-'))
                          else f'{kp:+.0f}%', old, count=1)
            out.append(('mismatch',
                        f"{k[0]} — kpis {kp:+.0f}% vs facts {fp:+.0f}% "
                        f"(금액 {k[1]} 일치) → kpis 값으로 교정",
                        old, new))
            break
    return out


def report(ticker, do_fix=False):
    try:
        import autogen
        name = autogen._module_name(ticker)
    except Exception:
        name = f'{ticker.lower()}_data'
    mod = importlib.import_module(name)
    rows = scan(mod)
    if not rows:
        return 0
    path = Path(mod.__file__)
    src = io.open(path, encoding='utf-8').read()
    fixed = 0
    print(f'\n── {ticker} 교차검증 ' + '─' * 40)
    for kind, msg, old, new in rows:
        print(f'  [X] {msg}')
        if not do_fix:
            continue
        if src.count(old) != 1:
            print(f'      ↳ 원문에서 {src.count(old)}번 나와 자동수정 보류 — 손으로 고칠 것')
            continue
        src = src.replace(old, new, 1)
        print(f'      ↳ 수정: {old!r} → {new!r}')
        fixed += 1
    if do_fix and fixed:
        io.open(path, 'w', encoding='utf-8').write(src)
        print(f'  → {path.name} {fixed}건 수정 완료')
    return len(rows) - fixed


if __name__ == '__main__':
    args = [a for a in sys.argv[1:]]
    do_fix = '--fix' in args
    args = [a for a in args if not a.startswith('-')]
    if args and args[0].lower() != 'all':
        sys.exit(1 if report(args[0].upper(), do_fix) else 0)
    import check
    left = 0
    for t in check._all_tickers():
        try:
            left += report(t, do_fix)
        except Exception as e:
            print(f'  {t}: 검사 실패 {e}')
    print('\n남은 불일치:', left)
    sys.exit(1 if left else 0)
