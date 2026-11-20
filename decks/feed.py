# -*- coding: utf-8 -*-
"""스크리너 신호 → 딥리포트 제작 큐.

    python feed.py              # 아직 안 만든 종목 중 상위 후보
    python feed.py --all        # 이미 만든 종목도 같이 보기
    python feed.py --json       # 기계용 출력

stock_screener(깃허브 레포명은 stock-dashboard)가 뱉는 신호 파일을 읽어
"다음에 어느 종목 리포트를 만들 것인가"를 정해준다. 이 한 칸이 비어 있어서,
신호는 매일 자동으로 쌓이는데 리포트 종목은 손으로 골라 손으로 돌리고 있었다.

## 입력 파일 — leaders_signal.json이 1순위

2026-08-05에 스크리너가 `leaders_v2.json`(팩터 나열식)에서
`leaders_signal.json`(검증판 규칙⑤)으로 갈아탔고 옛 파일은 삭제됐다.
초판 feed.py는 옛 파일만 보고 있어서 이틀간 조용히 죽어 있었다 — 그래서
지금은 새 파일을 먼저 보고, 없으면 옛 파일, 그것도 없으면 CANSLIM으로
내려가면서 **어떤 파일을 썼는지 항상 출력한다.** 입력이 바뀌었는데 아무 말도
없이 도는 게 제일 나쁘다.

`leaders_signal`의 candidates는 이미 스크리너 쪽 규칙을 통과한 종목들이다.
그래서 여기서의 점수는 자격 판정이 아니라 **읽는 순서**다. 사용자의 투자
철학(구조적 성장주의 흑자전환 포착)에 따라 흑자전환 트리거에 가장 큰 가중을
준다. 매수 신호가 아니다.

**규칙 문구를 여기 베껴 적지 않는다.** 규칙은 스크리너가 소유하고 파일의 `rule`
필드가 들고 있으며, 우리는 그걸 그대로 출력만 한다. 예전에 독스트링에
`PSR < 3`을 박아뒀다가 스크리너가 그 조건을 `OPM > 0`으로 갈아치웠는데도 문서만
옛말을 하고 있었다. 남의 규칙을 내 파일에 복사하면 반드시 낡는다.

## 의도적으로 안 하는 것

자동 생성도 자동 발행도 하지 않는다. autogen 초안은 검수가 필수고(AAPL에서
30건 넘게 나왔다) 검수 없는 자동 발행은 오보를 뿌린다. 이 스크립트의 책임은
'만들 것 목록'까지고, 그 다음은 사람이 잇는다:

    feed.py → autogen.py → (검수) → check.py → build.py → publish.py

데이터 출처는 기본이 로컬 경로다(두 레포가 같은 Desktop에 나란히 있다).
SCREENER_RESULTS 환경변수로 덮어쓸 수 있다.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 흑자전환이 이 전략의 핵심이라 가중이 가장 크다. 나머지는 이익의 질.
TRIGGER_PTS = {
    '흑자전환': 30,
    '영업익 신고점': 10,
    '순익 신고점': 10,
    '영업익 QoQ+50%': 10,
    'OPM QoQ+3%p': 10,
}


def _results_dir():
    env = os.environ.get('SCREENER_RESULTS')
    if env:
        return Path(env)
    # buza-bot/decks/feed.py → buza-bot → Desktop → Desktop/stock_screener/results
    return HERE.parents[1] / 'stock_screener' / 'results'


def _load(name):
    path = _results_dir() / name
    if not path.exists():
        return None
    with open(path, encoding='utf-8') as fp:
        return json.load(fp)


def built_tickers():
    """이미 데이터 파일이 있는 종목. satl은 satl_data.py와 satl16_data.py가
    둘 다 있는 식으로 접미사가 붙기도 해서 앞의 알파벳만 떼어 본다."""
    out = set()
    for p in HERE.glob('*_data.py'):
        stem = p.stem[:-len('_data')]
        out.add(''.join(c for c in stem if c.isalpha()).upper())
    return out


def sanity(r):
    """입력값이 물리적으로 말이 되는지 본다. 이상하면 이유 목록을 돌려준다.

    스크리너가 `PSR < 3`을 `OPM > 0`으로 바꾼 뒤 OSCR이 **영업이익률 12313%**,
    **OPM QoQ +16036%p**, PSR 112.94로 통과해 상위에 올라왔다. 영업이익률이 매출의
    100%를 넘을 수는 없으므로 이건 종목 발굴이 아니라 계산 사고다(매출 분모가
    0에 가깝거나 단위가 어긋난 쪽이 유력).

    이런 값을 조용히 순위에 태우면 그 종목으로 리포트를 만들게 되고, 잘못된
    숫자가 발행 직전까지 간다. 여기서 잡아 세우는 게 훨씬 싸다. 원인 수정은
    스크리너 쪽 몫이라 여기서는 고치지 않고 드러내기만 한다."""
    bad = []
    opm = r.get('opm')
    if isinstance(opm, (int, float)) and abs(opm) > 100:
        bad.append(f'OPM {opm:,.0f}% (영업이익률이 매출의 100%를 넘을 수 없음)')
    qoq = r.get('opm_qoq')
    if isinstance(qoq, (int, float)) and abs(qoq) > 100:
        bad.append(f'OPM QoQ {qoq:,.0f}%p')
    psr = r.get('psr')
    if isinstance(psr, (int, float)) and psr > 50:
        bad.append(f'PSR {psr:,.1f}')
    return bad


def _from_signal(doc, watched):
    """leaders_signal.json — 규칙 통과 종목만 들어 있다."""
    rows = []
    for r in doc.get('candidates', []):
        trg = r.get('triggers') or []
        pts = sum(TRIGGER_PTS.get(t, 5) for t in trg)
        rs = r.get('rs_13w') or 0
        pts += max(0, (rs - 1.5)) * 20          # 규칙 하한(1.5) 위로 얼마나 강한가
        psr = r.get('psr')
        if psr is not None and psr < 1:
            pts += 10                            # 같은 조건이면 싼 쪽 먼저
        why = list(trg)
        if rs:
            why.append(f'RS{rs:.2f}')
        if psr is not None:
            why.append(f'PSR{psr:.2f}')
        rows.append({
            'sym': r['sym'], 'name': r.get('name', ''),
            'sector': '', 'marcap': (r.get('marcap_b') or 0) * 1e9 or None,
            'score': round(pts, 1), 'why': why,
            'watched': r['sym'] in watched, 'suspect': sanity(r),
        })
    return rows


def _from_leaders_v2(doc, _watched):
    """구 형식 — 혹시 되살아나면 계속 읽되, 점수 체계는 그때 것을 유지한다."""
    rows = []
    for r in doc.get('all', []):
        if r.get('market') != 'US':
            continue
        pts, why = 0, []
        if r.get('inflection'):
            pts += 40
            why.append('변곡')
        if r.get('rev_accel'):
            pts += 20
            why.append('매출가속')
        rs = r.get('rs') or 0
        pts += rs * 0.3
        if rs >= 95:
            why.append(f'RS{rs:.0f}')
        rows.append({'sym': r['sym'], 'name': r.get('name', ''),
                     'sector': r.get('sector', ''), 'marcap': r.get('marcap'),
                     'score': round(pts, 1), 'why': why, 'watched': False})
    return rows


def _from_canslim(doc, _watched):
    """최후 폴백 — 자격 필터가 약하므로 RS 순으로만 세운다."""
    rows = []
    for r in doc.get('stocks', []):
        rs = r.get('rs_pct') or 0
        rows.append({'sym': r['sym'], 'name': r.get('name', ''), 'sector': '',
                     'marcap': r.get('marcap'), 'score': round(rs * 0.5, 1),
                     'why': [f'RS{rs:.0f}', 'CANSLIM'], 'watched': False})
    return rows


SOURCES = [
    ('leaders_signal.json', _from_signal, '검증판 규칙⑤'),
    ('leaders_v2.json', _from_leaders_v2, '구 팩터판'),
    ('canslim_us_latest.json', _from_canslim, 'CANSLIM 폴백'),
]


def collect(include_built=False):
    for fname, parser, label in SOURCES:
        doc = _load(fname)
        if not doc:
            continue
        watched = set()
        paper = (doc.get('paper') or {}).get('open') or []
        watched = {p.get('sym') for p in paper}
        rows = parser(doc, watched)
        if not rows:
            continue
        done = built_tickers()
        for r in rows:
            r['built'] = r['sym'] in done
            r.setdefault('suspect', [])
        if not include_built:
            rows = [r for r in rows if not r['built']]
        # 입력이 수상한 종목은 점수가 높아도 뒤로 보낸다. 순위표 위쪽은 바로
        # 만들어도 되는 것만 있어야 한다.
        rows.sort(key=lambda x: (bool(x['suspect']), -x['score']))
        meta = {
            'file': fname, 'label': label,
            'generated': (doc.get('generated') or '?')[:16],
            'rule': doc.get('rule'), 'funnel': doc.get('funnel'),
        }
        return rows, meta
    sys.exit(f'스크리너 신호를 못 찾음: {_results_dir()}\n'
             f'찾아본 파일: ' + ', '.join(f for f, _, _ in SOURCES) + '\n'
             'SCREENER_RESULTS로 경로를 지정하거나 스크리너를 먼저 돌릴 것.')


def main():
    args = sys.argv[1:]
    rows, meta = collect(include_built='--all' in args)
    if '--json' in args:
        print(json.dumps({'meta': meta, 'rows': rows}, ensure_ascii=False, indent=2))
        return

    print(f"입력: {meta['file']} ({meta['label']}) · 신호 {meta['generated']}")
    if meta['rule']:
        print(f"  규칙: {meta['rule']}")
    if meta['funnel']:
        print('  깔때기: ' + ' → '.join(f'{n}' for _, n in meta['funnel']))
    print()
    if not rows:
        print('새로 만들 후보 없음 — 규칙 통과 종목은 이미 다 리포트가 있다.')
        return

    clean = [r for r in rows if not r['suspect']]
    suspect = [r for r in rows if r['suspect']]

    print(f'{"":3}{"티커":<7}{"점수":>6}  {"시총":>8}  근거')
    for i, r in enumerate(clean[:15], 1):
        cap = f'{r["marcap"] / 1e9:.1f}B' if r.get('marcap') else '-'
        mark = '✓' if r.get('built') else ('·' if r.get('watched') else ' ')
        print(f'{i:>2}{mark} {r["sym"]:<7}{r["score"]:>6}  {cap:>8}  {", ".join(r["why"])}')
    print('\n  ✓ 리포트 있음   · 페이퍼 포지션 보유 중')

    if suspect:
        print('\n⚠ 입력이 수상해 순위에서 뺀 종목 — 스크리너 쪽 계산을 봐야 한다')
        for r in suspect:
            print(f'   {r["sym"]:<7} {"; ".join(r["suspect"])}')

    if not clean:
        print('\n만들 만한 종목이 없다 — 남은 후보가 전부 입력 이상이다.')
        return
    top = clean[0]['sym']
    print(f'\n다음 한 종목: python autogen.py {top}  →  검수  →  '
          f'python check.py {top}  →  python build.py {top}  →  python publish.py {top}')


if __name__ == '__main__':
    main()
