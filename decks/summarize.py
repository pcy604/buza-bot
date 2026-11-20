# -*- coding: utf-8 -*-
"""종합평가(SUMMARY)를 숫자만으로 조립한다 — LLM 0콜.

## 왜 이게 가능한가

`SUMMARY_PROMPT`가 LLM에게 시키는 일이 원래 이거였다:

    "이미 이 파일에 있는 숫자만 종합(LLM 호출 G, 새 주장 없음)"

즉 새 주장을 만들지 말고 있는 숫자를 문장으로 엮으라는 지시다. 실제 산출물도
그랬다(QLYS): 매출·순이익·영업현금흐름을 나열하고, 시총 대비 목표주가 괴리를
언급하는 정도. **그건 템플릿이 할 수 있는 일이다.**

입력도 이미 전부 결정론이다 — `ann_series`는 XBRL, `cons`는 Yahoo다.
LLM을 태울 이유가 없었다.

## 규칙

- **산술로 나오는 것만 쓴다.** 전망·해석·"견조하다" 같은 형용은 넣지 않는다.
  판단이 필요한 자리는 애초에 이 함수의 몫이 아니다.
- **없는 값은 그 문장을 통째로 뺀다.** 억지로 채우면 "데이터 없음"이 "0"으로
  둔갑한다 — 이 프로젝트에서 반복해서 나온 버그 클래스다.
- 금액은 카드 표기 규칙($X.XB / $X.XM)을 따른다. check.py가 이걸 검사한다.
"""
import re


def _money(v):
    """$X.XB / $X.XM 규칙. 카드 전체가 이 표기로 통일돼 있고 게이트가 검사한다."""
    if v is None:
        return None
    a = abs(v)
    if a >= 1e9:
        return f'${v / 1e9:,.1f}B'
    if a >= 1e6:
        return f'${v / 1e6:,.1f}M'
    if a >= 1e3:
        return f'${v / 1e3:,.1f}K'
    return f'${v:,.0f}'


def _pct(new, old):
    """전년 대비 증감률. 부호가 바뀌면(적자→흑자 등) 비율이 무의미하므로 None."""
    if new is None or old is None or old == 0:
        return None
    if (new < 0) != (old < 0):
        return None
    return (new / old - 1) * 100


def _last_two(series: dict):
    """(최신연도, 최신값, 전년값). 값이 있는 해만 본다."""
    if not series:
        return None, None, None
    yrs = sorted(y for y, v in series.items() if v is not None)
    if not yrs:
        return None, None, None
    y = yrs[-1]
    prev = series.get(yrs[-2]) if len(yrs) > 1 else None
    return y, series[y], prev


def _last_sign_change(series: dict):
    """부호가 마지막으로 바뀐 (연도, 방향). 방향은 'up'(흑자전환) 또는 'down'(적자전환).

    **첫 전환만 찾으면 안 된다.** ABCL은 FY2020에 흑자 전환했다가 FY2023부터 다시
    적자인데, 첫 전환만 보는 코드가 "영업이익은 FY2020에 흑자로 전환됨"이라고 써서
    같은 페이지의 '순이익 -$146.4M'과 정면으로 모순됐다. 실제 발행 직전까지 갔다.
    지금 상태를 말하려면 **마지막** 전환을 봐야 한다."""
    if not series:
        return None, None
    yrs = sorted(y for y, v in series.items() if v is not None)
    last = (None, None)
    for a, b in zip(yrs, yrs[1:]):
        if series[a] < 0 <= series[b]:
            last = (b, 'up')
        elif series[b] < 0 <= series[a]:
            last = (b, 'down')
    return last


def _streak_up(series: dict) -> int:
    """최신 연도부터 몇 해 연속 증가했나."""
    yrs = sorted(y for y, v in series.items() if v is not None)
    n = 0
    for a, b in zip(reversed(yrs[:-1]), reversed(yrs[1:])):
        # b가 최신 쪽
        if series[b] > series[a]:
            n += 1
        else:
            break
    return n


def build(raw) -> str:
    """종합평가 문단. 각 줄은 숫자에서 직접 유도된 사실만 담는다."""
    ann = raw.get('ann_series') or {}
    cons = raw.get('cons') or {}
    lines = []

    # ① 최근 회계연도 실적
    y, rev, prev_rev = _last_two(ann.get('revenue') or {})
    if y and rev is not None:
        part = f'FY{y} 매출 {_money(rev)}'
        g = _pct(rev, prev_rev)
        if g is not None:
            part += f'(전년 대비 {g:+.1f}%)'
        op = (ann.get('opinc') or {}).get(y)
        ni = (ann.get('netinc') or {}).get(y)
        if op is not None:
            opm = op / rev * 100 if rev else None
            part += f', 영업이익 {_money(op)}' + (f'(OPM {opm:.1f}%)' if opm is not None else '')
        if ni is not None:
            part += f', 순이익 {_money(ni)}'
        lines.append(part + '.')

    # ② 손익 전환 — 사용자의 투자 철학상 가장 중요한 사실.
    # 방향을 그대로 말한다. 흑자 전환만 말하고 그 뒤 적자 재전환을 숨기면 거짓이 된다.
    said = False
    for key, label in (('opinc', '영업이익'), ('netinc', '순이익')):
        yr, direction = _last_sign_change(ann.get(key) or {})
        if not yr:
            continue
        word = '흑자로 전환됨' if direction == 'up' else '적자로 돌아섬'
        lines.append(f'{label}은 FY{yr}에 {word}.')
        said = True
        break
    if not said:
        n = _streak_up(ann.get('revenue') or {})
        if n >= 2:
            lines.append(f'매출은 최근 {n}개 회계연도 연속 증가.')

    # ③ 현금
    _, cfo, _ = _last_two(ann.get('cfo') or {})
    _, cash, _ = _last_two(ann.get('cash') or {})
    if cfo is not None or cash is not None:
        bits = []
        if cfo is not None:
            bits.append(f'영업활동 현금흐름 {_money(cfo)}')
        if cash is not None:
            bits.append(f'보유 현금 {_money(cash)}')
        lines.append(' · '.join(bits) + '.')

    # ④ 밸류에이션은 **여기에 쓰지 않는다.**
    #
    # 처음엔 현재가·시총·PSR·목표주가를 이 문단에 넣었다. 그런데 이 함수는
    # autogen(생성 시점)에 돌아 결과가 데이터 파일에 문자열로 굳는 반면, 카드의
    # 밸류에이션 박스는 render 시점에 live.bundle()이 새로 가져온다. 두 시점이
    # 다르면 값도 다르다 — ABCL에서 **같은 페이지 안에** '현재가 $10.22'(박스)와
    # '현재가 $10.16'(이 문장)이 나란히 찍혔고, PSR도 41.5/41.7/42 세 값이 됐다.
    # 처음 보는 독자가 "출처 있음 ≠ 숫자가 서로 맞음"이라며 신뢰를 접은 지점이다.
    #
    # 원칙: **시세처럼 변하는 값은 렌더 시점에 한 곳에서만 만든다.** 데이터 파일에
    # 굳히면 그 순간부터 반드시 어긋난다. 재무(XBRL)는 분기마다만 바뀌므로 여기 남긴다.
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import sources as S
    import ir
    for tk in (sys.argv[1:] or ['QLYS']):
        cik, name = ir.resolve_ticker(tk.upper())
        if not cik:
            print(f'{tk}: SEC에 없음')
            continue
        raw = {'ann_series': S.annual_series(cik), 'cons': S.consensus(tk.upper())}
        print(f'\n=== {tk} ({name})')
        print(build(raw) or '  (숫자가 없어 요약 불가)')
