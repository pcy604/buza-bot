# -*- coding: utf-8 -*-
"""13장 리포트 **페이지별** 검증 — 어느 장이 비었는지 장 단위로 말한다.

    python decks/pagecheck.py            # 전 종목 요약 매트릭스
    python decks/pagecheck.py SATL       # 한 종목 상세
    python decks/pagecheck.py --live SATL  # live 데이터 페이지까지 (SEC·Yahoo 왕복, 느림)

## 왜 따로 만들었나

check.py 의 audit() 은 **데이터 필드 단위**로 말한다("SEGMENTS.by_line 이 빔").
그래서 "그래서 몇 번째 장이 이상한 건데?" 에 답을 못 한다. 13장을 눈으로 훑는
수밖에 없었고, 그게 '페이지별 검증 필요' 로 남아 있던 이유다.

여기서는 **PAGES 순서 그대로** 장에 붙여서 말한다. 필드가 아니라 장이 단위다.

## 정직하게 알아둘 것 — 모듈만으로 검증되지 않는 장이 있다

deck_pages 의 재무제표·밸류에이션·퀀트 페이지는 종목 데이터 모듈이 아니라
**렌더 시점에 SEC/Yahoo 에서 받아오는 live 번들(deck_pages.L)** 을 읽는다.
즉 데이터 모듈을 아무리 들여다봐도 그 장이 빌지 안 빌지 알 수 없다.
그런 장을 "이상 없음"으로 찍으면 검증한 척하는 것이라, 기본 모드에서는
`live?` 로 **미검증**임을 드러낸다. --live 를 주면 실제로 번들을 받아 확인한다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import check  # noqa: E402

BLOCK, WARN, INFO = check.BLOCK, check.WARN, check.INFO

# ── 장 순서: deck_pages.PAGES 와 **같은 순서**여야 한다 ─────────────────
# (이 파일이 PAGES 를 직접 임포트하지 않는 이유: deck_pages 임포트는 무겁고
#  configure() 전엔 전역이 비어 있어 import 자체가 부작용을 낸다.)
PAGES = [
    ('1p', '표지 · 종합평가', 'module'),
    ('2p', '전망 · 체크포인트', 'module'),
    ('3p', '실적 하이라이트', 'module'),
    ('4p', '연혁 · 주가 이정표', 'module'),
    ('5p', 'CEO · 경영진', 'module'),
    ('6p', '사업부문 · 매출구성', 'module'),
    ('7p', '퀀트 스코어', 'live'),
    ('8p', 'CANSLIM', 'module'),
    ('9p', '밸류에이션', 'live'),
    ('10p', '연간 손익', 'live'),
    ('11p', '분기 손익', 'live'),
    ('12p', '재무상태표', 'live'),
    ('13p', '현금흐름', 'live'),
]
PAGE_NO = {p[0]: i for i, p in enumerate(PAGES)}


def _g(mod, path, default=None):
    return check._get(mod, path, default)


def _txt(mod, path):
    return str(_g(mod, path, '') or '').strip()


# ── 장별 규칙 ────────────────────────────────────────────────────────
# 각 함수는 (등급, 설명) 리스트를 돌려준다. mod=데이터 모듈, L=live 번들(없으면 None).
def _p1(mod, L):
    out = []
    if not _txt(mod, 'SUMMARY'):
        out.append((BLOCK, '종합평가 문단이 통째로 빔'))
    biz = [b for b in (_g(mod, 'BUSINESS', []) or []) if b]
    if len(biz) < 3:
        out.append((BLOCK, f'표지 3줄(무엇을/누가/어떻게) 중 {len(biz)}줄만 있음'))
    if not _txt(mod, 'COMPANY.exchange'):
        out.append((WARN, '거래소 표기가 비어 표지에 빈칸으로 노출'))
    # BUILT_AT 은 항상 오늘로 갱신되므로 "최신"처럼 보인다. 실제로는 추출이 빈
    # 필드를 옛 값으로 메운 게 섞여 있을 수 있다 — autogen 이 CARRIED_OVER 에
    # 적어두므로 여기서 드러낸다(적어만 두고 아무도 안 보면 안 적은 것과 같다).
    co = _g(mod, 'CARRIED_OVER', {}) or {}
    old_vals = {k: v for k, v in co.items() if v != 'LOCKED'}
    if old_vals:
        when = sorted({str(v) for v in old_vals.values()})
        out.append((WARN, f'{len(old_vals)}개 필드가 이전 생성분({", ".join(when)}) 값 — '
                          f'BUILT_AT 은 최신인데 내용 일부는 그때 것: '
                          f'{", ".join(sorted(old_vals)[:4])}'
                          + (' 외' if len(old_vals) > 4 else '')))
    return out


def _p2(mod, L):
    out = []
    if not (_g(mod, 'CHECKPOINTS', []) or []):
        out.append((BLOCK, '체크포인트 타임라인이 빔 — 장 전체가 빈 페이지'))
    if not _txt(mod, 'CHECKPOINT_NOTE'):
        out.append((WARN, '체크포인트 해설 박스가 빔'))
    return out


def _p3(mod, L):
    out = []
    if not (_g(mod, 'RESULTS.kpis', []) or []):
        out.append((BLOCK, 'KPI 타일이 통째로 빔'))
    if not (_g(mod, 'RESULTS.facts', []) or []):
        out.append((WARN, '어닝콜 핵심 숫자 표가 빔'))
    return out


def _p4(mod, L):
    out = []
    if not (_g(mod, 'HISTORY.timeline', []) or []):
        out.append((WARN, '연혁 타임라인이 빔'))
    if not _g(mod, 'HISTORY.founded'):
        out.append((WARN, '창업연도 미확인 — "창업" 타일이 안 나옴'))
    listed = _g(mod, 'HISTORY.listed')
    # listing_date(YYYY-MM-DD)가 채워져 있으면 연도만 있다는 경고는 틀린 말이다.
    # 이 검사는 listed(연도)만 보고 있어서, listing.py 로 월·일을 확정해 넣어도
    # 경고가 그대로 떴다 — 고쳐도 안 꺼지는 경고는 사람이 곧 무시하게 된다.
    exact = str(_g(mod, 'HISTORY.listing_date', '') or '')
    if len(exact) == 10 and exact[4] == '-' and exact[7] == '-':
        listed = exact
    if not listed:
        out.append((WARN, '상장연도 미확인 — "상장" 타일·상장후 CAGR 안 나옴'))
    elif len(str(listed)) == 4:
        # 연도만 있으면 1월 1일로 취급돼 상장 전 주가가 차트에 들어온다.
        # ⚠️ 2026-10-03 전수 확인: **23종목 전부** 연도만이다. 그래서 전부 같은 등급으로
        #    띄우면 아무 신호도 안 된다 — 실제로 틀리는 경우만 올린다.
        #    · IPO: 1월 1일로 당겨도 그 전엔 거래 자체가 없어 차트가 안 틀린다(AAPL 1980).
        #    · SPAC합병·스핀오프: 같은 티커로 **상장 전 셸/모회사 주가가 존재**한다.
        #      그게 차트에 들어오고 상장후 CAGR 의 기준가가 된다.
        #      실측: SATL 이 2021 로 적혀 있는데 실제 상장은 2022년 — 사용자가
        #      "3P에 상장 전 주가 억지로 표현"이라고 지적한 바로 그 건이다.
        kind = str(_g(mod, 'HISTORY.listing_type', '') or '')
        risky = any(k in kind for k in ('SPAC', '스핀오프', '직상장'))
        out.append((WARN if risky else INFO,
                    (f'상장일이 연도({listed})뿐인데 {kind} — 상장 전 셸/모회사 주가가 '
                     f'차트와 상장후 CAGR 에 섞인다. 월·일까지 필요')
                    if risky else
                    f'상장일이 연도({listed})뿐 — {kind or "IPO"} 라 차트 영향은 없으나 표기는 부정확'))
    for mv in (_g(mod, 'PRICE_MOVES', []) or []):
        if '미확인' in str(mv.get('reason', '')):
            out.append((INFO, f'{mv.get("period")} 구간 등락 이유 미확인'))
    return out


def _p5(mod, L):
    out = []
    ceo = _g(mod, 'LEADERSHIP.ceo', {}) or {}
    if str(ceo.get('name', '')).startswith('('):
        out.append((BLOCK, 'CEO 실명 대신 자리표시자가 그대로 노출'))
    if not ceo.get('since'):
        out.append((WARN, 'CEO 취임연도 미확인 — 재임기간이 안 나옴'))
    if not ceo.get('bio'):
        out.append((WARN, 'CEO 약력이 빔 — 프로필 박스가 헐거워짐'))
    if not (_g(mod, 'LEADERSHIP.people', []) or []):
        out.append((WARN, '경영진 명단이 빔 — 표가 통째로 생략'))
    return out


def _p6(mod, L):
    out = []
    if not (_g(mod, 'SEGMENTS.by_line', []) or []):
        out.append((WARN, '부문별 매출 도넛이 빔(전사 총매출로만 표시)'))
    if not (_g(mod, 'SEGMENTS.competitors', []) or []):
        out.append((INFO, '10-K가 경쟁사를 구체적으로 안 듦 — 비교표 생략'))
    return out


def _p8(mod, L):
    out = []
    n = _g(mod, 'CANSLIM_N', {}) or {}
    scored = [k for k in ('top_tier', 'growth_years', 'governance') if n.get(k)]
    if not scored and not n.get('market_cagr'):
        out.append((WARN, 'N 항목이 전부 0/None — 총점이 사실상 C+A뿐'))
    if n and not (_g(mod, 'CANSLIM_N_DETAIL', {}) or {}):
        out.append((WARN, 'N 점수는 있는데 근거 문장이 없음 — 지어낸 점수와 구분 불가'))
    if not _txt(mod, 'CANSLIM_NOTE'):
        out.append((INFO, '채점 방식 각주가 빔'))
    return out


def _live_series(L, group, key):
    """live 번들에서 연도별 값 목록. 번들 구조가 바뀌면 조용히 빈 리스트."""
    try:
        d = ((L or {}).get(group) or {}).get(key) or {}
        return [v for v in d.values() if v is not None]
    except Exception:
        return []


def _p7(mod, L):
    if L is None:
        return []
    return [] if _live_series(L, 'annual', 'revenue') else [(WARN, '퀀트 스코어 기반 재무가 비어 점수가 안 잡힘')]


def _p9(mod, L):
    out = []
    if not (_g(mod, 'PEERS', {}) or {}):
        out.append((WARN, '비교 대상(PEERS)이 없어 배수 비교가 단독값만 나옴'))
    # 설정은 돼 있는데 실제로 못 가져온 peer. 조용히 빠지면 독자는 비교 대상이
    # 둘인 줄 알고 하나짜리 차트를 본다.
    pf = (L or {}).get('peer_failed') or {}
    if pf:
        # 사유를 중간에서 자르면 괄호가 깨져 더 읽기 나쁘다 — 짧은 말로 요약해 붙인다.
        def _short(v):
            v = str(v)
            return 'SEC 재무데이터 없음' if '재무데이터 없음' in v else v.split(':')[0][:24]
        out.append((WARN, f'비교 대상 {len(pf)}곳이 빠진 채 그려짐 — '
                          + ', '.join(f'{k}({_short(v)})' for k, v in list(pf.items())[:3])))
    if L is not None and not _live_series(L, 'annual', 'revenue'):
        out.append((WARN, '밸류에이션 계산에 쓰는 매출 시계열이 빔'))
    return out


def _p10(mod, L):
    out = []
    if not _txt(mod, 'INCOME_NOTE'):
        out.append((WARN, '연간 손익 해설 박스가 빔 — 차트만 남음'))
    if L is not None and not _live_series(L, 'annual', 'revenue'):
        out.append((BLOCK, '연간 매출 시계열이 비어 차트가 안 그려짐'))
    return out


def _p11(mod, L):
    if L is None:
        return []
    return [] if _live_series(L, 'quarterly', 'revenue') else [(WARN, '분기 매출 시계열이 빔')]


def _p12(mod, L):
    out = []
    if not _txt(mod, 'BALANCE_NOTE'):
        out.append((WARN, '재무상태표 해설 박스가 빔 — 차트만 남음'))
    if L is not None and not _live_series(L, 'annual', 'cash'):
        out.append((WARN, '현금 시계열이 빔'))
    return out


def _p13(mod, L):
    out = []
    if not (_g(mod, 'CASHFLOW', {}) or {}):
        out.append((WARN, '현금흐름 보조 데이터가 빔'))
    if L is not None and not _live_series(L, 'annual', 'cfo'):
        out.append((BLOCK, '영업현금흐름 시계열이 비어 차트가 안 그려짐'))
    return out


RULES = {'1p': _p1, '2p': _p2, '3p': _p3, '4p': _p4, '5p': _p5, '6p': _p6,
         '7p': _p7, '8p': _p8, '9p': _p9, '10p': _p10, '11p': _p11,
         '12p': _p12, '13p': _p13}


def check_ticker(ticker: str, live: bool = False):
    """{'1p': [(등급, 설명), ...], ...} 또는 {'_error': 설명}."""
    try:
        mod = check.module_for(ticker)
    except Exception as e:
        return {'_error': f'데이터 모듈을 못 읽음: {e}'}
    L = None
    if live:
        try:
            L = _load_live(ticker)
        except Exception as e:
            return {'_error': f'live 번들 로드 실패: {e}'}
    out = {}
    for code, _label, _kind in PAGES:
        try:
            out[code] = RULES[code](mod, L)
        except Exception as e:
            out[code] = [(BLOCK, f'검사 자체가 실패함: {type(e).__name__}: {e}')]
    # 자리표시자 문구는 장을 가리지 않고 나올 수 있어 따로 훑는다.
    for lvl, item, msg in check.audit(mod, ticker):
        if '검수용 문구' in msg:
            out.setdefault('1p', []).append((BLOCK, f'{item}: {msg}'))
    return out


def _load_live(ticker: str):
    """build.build 와 같은 경로로 configure 까지만 가고 live 번들을 받는다(렌더는 안 함)."""
    import importlib
    import build as B
    import deck_pages as P
    import live

    cfg = B.TICKERS.get(ticker) or B._auto_config(ticker)
    if not cfg:
        raise RuntimeError('TICKERS 미등록이고 데이터 모듈도 없음')
    dm = importlib.import_module(cfg['data_module'])
    cik = cfg['cik'] if cfg['cik'] is not None else getattr(dm, 'COMPANY', {}).get('cik')
    kw = P.configure(data_module=dm, ticker=ticker, name=cfg['name'], exchange=cfg['exchange'],
                     sector=cfg['sector'], cik=cik, peers=cfg['peers'],
                     site=cfg['site'], ceo=cfg['ceo'], wiki_file=cfg.get('wiki_file', ''))
    return live.bundle(ticker, cik, cfg['peers'], kw['site'], kw['ceo'],
                       wiki_file=kw.get('wiki_file', ''))


def print_ticker(ticker: str, live: bool = False):
    res = check_ticker(ticker, live=live)
    print(f'\n── {ticker} 13장 페이지별 점검 ' + '─' * 32)
    if '_error' in res:
        print(f'  X {res["_error"]}')
        return 1
    icon = {BLOCK: 'X', WARN: '!', INFO: '·'}
    nblock = 0
    skipped = 0
    for code, label, kind in PAGES:
        rows = res.get(code) or []
        nblock += sum(1 for lv, _ in rows if lv == BLOCK)
        if not rows:
            seen = kind == 'module' or live
            skipped += 0 if seen else 1
            mark = '  ' if seen else '?'
            note = '' if seen else '  (live 데이터 미확인 — --live 필요)'
            print(f'  {mark} {code:<4} {label}{note}')
            continue
        print(f'    {code:<4} {label}')
        for lv, msg in rows:
            print(f'       {icon[lv]} {msg}')
    # "차단 0건"만 찍으면 --live 없이 돈 7장짜리 사각지대가 통과로 읽힌다.
    # 몇 장을 실제로 봤는지 같이 말하지 않으면 이 줄이 거짓말이 된다.
    if skipped:
        print(f'  → 차단 {nblock}건  ⚠️ {len(PAGES)}장 중 {len(PAGES) - skipped}장만 검사'
              f'(나머지 {skipped}장은 --live 필요)')
    else:
        print(f'  → 차단 {nblock}건  ({len(PAGES)}장 전부 검사)')
    return nblock


def print_all(live: bool = False):
    tickers = check._all_tickers()
    print(f'13장 페이지별 점검 — {len(tickers)}종목' + ('' if live else ' (live 페이지 제외)'))
    print()
    head = '종목      ' + ' '.join(f'{c:>4}' for c, _, _ in PAGES)
    print(head)
    print('-' * len(head))
    worst = []
    for t in tickers:
        res = check_ticker(t, live=live)
        if '_error' in res:
            print(f'{t:<9} ' + f'!! {res["_error"][:50]}')
            continue
        cells, nb = [], 0
        for code, _l, kind in PAGES:
            rows = res.get(code) or []
            if any(lv == BLOCK for lv, _ in rows):
                cells.append('   X')
                nb += 1
            elif any(lv == WARN for lv, _ in rows):
                cells.append('   !')
            elif rows:
                cells.append('   ·')
            elif kind == 'live' and not live:
                cells.append('   ?')
            else:
                cells.append('   .')
        print(f'{t:<9} ' + ' '.join(cells))
        if nb:
            worst.append((nb, t))
    print()
    print('X=차단  !=경고  ·=참고  .=이상없음  ?=live 데이터라 미검증')
    if worst:
        worst.sort(reverse=True)
        print('\n차단 있는 종목: ' + ', '.join(f'{t}({n}장)' for n, t in worst))
    else:
        print('\n차단 없음')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--live']
    use_live = '--live' in sys.argv[1:]
    if args:
        raise SystemExit(1 if print_ticker(args[0].upper(), live=use_live) else 0)
    print_all(live=use_live)
