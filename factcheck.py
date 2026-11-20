# -*- coding: utf-8 -*-
"""생성 시점 사실 검사 — 잘못된 걸 **나가기 전에** 잡는다.

quality.py 는 이미 나간 걸 사후에 채점하는 도구다. 그건 "지난주에 틀린 게
나갔다"를 알려줄 뿐 사용자가 받은 건 이미 틀린 채로 받았다. 이 모듈은 같은
검사를 **저장 직전**에 돌려서, 고칠 수 있는 건 고치고 못 고치는 건 기록한다.

두 부류를 나눈 게 핵심이다.

  ① 결정적으로 고칠 수 있는 것 → **고친다.**
     존재하지 않는 티커 코드가 붙으면 카드의 종목 링크가 엉뚱한 회사로 간다.
     회사 이름은 맞는데 코드만 틀린 경우가 대부분이라, **코드만 비운다**.
     이름을 지우면 정보가 사라지고, 코드를 남기면 사용자를 틀린 곳으로 보낸다.

  ② 고칠 수 없는 것 → **기록만 한다.**
     "5년간 7,000억 달러" 가 과장인지 받아쓰기 오류인지 여기서는 알 수 없다.
     본문을 임의로 지우면 원래 발언까지 없애는 셈이라 손대지 않고, 플래그를
     남겨 주간 브리핑에서 사람이 보게 한다.

⚠️ 여기서 LLM 을 호출하지 않는다. 검사가 쿼터를 먹으면 검사 때문에 요약을
   못 만드는 상황이 생긴다.
"""
import re

# ── 금액 이상치 ──────────────────────────────────────────────────────
# 단일 기업 거래로는 비현실적인 선. 실제 사례: "SK하이닉스, 엔비디아와 5년간
# 7,000억 달러 HBM 공급" — 엔비디아 연매출의 5배가 넘는다.
# ⚠️ 전체 시장규모 얘기("시장 1.5조 달러")엔 오탐이 난다. 그래서 차단이 아니라 플래그다.
_AMT_USD = re.compile(r'([\d,]+(?:\.\d+)?)\s*(억|조)\s*달러')
_AMT_KRW = re.compile(r'([\d,]+(?:\.\d+)?)\s*조\s*원')
USD_LIMIT_BN = 300       # $300B 초과
KRW_LIMIT_TRN = 400      # 400조원 초과

# SEC 회사 목록에 없는 게 **정상**인 식별자 — 지수·통화·원자재·암호화폐.
NOT_A_COMPANY = frozenset('''KOSPI KOSDAQ SPX IXIC DJI SOX VIX
USDJPY JPY USD EUR KRW XAU XAG WTI BRENT
BTC ETH SOL ARB ONDO'''.split())
# 티커 자리에 국가·일반명사를 넣은 것 — 눌러도 아무 데도 안 가는 확실한 오류.
NOT_A_TICKER = frozenset('''US CN KR JP EU LP ETF REIT'''.split())

_US_MAP = None


def us_ticker_known(sym: str):
    """미국 심볼이 SEC 등록 목록에 있는지. 목록을 못 읽으면 None(모름).

    ⚠️ ir 을 **함수 안에서** 임포트한다. analyzer 가 이 모듈을 쓰는데
       ir 은 analyzer 를 임포트하므로 모듈 최상단에 두면 순환이 된다.
    """
    global _US_MAP
    if _US_MAP is None:
        try:
            import ir
            _US_MAP = set(ir._cik_map())
        except Exception as e:
            print(f'[티커 목록 없음 — 코드 검사 생략] {e}')
            _US_MAP = set()
    return sym in _US_MAP if _US_MAP else None


def implausible_amount(s: str) -> bool:
    for m in _AMT_USD.finditer(s or ''):
        try:
            v = float(m.group(1).replace(',', ''))
        except ValueError:
            continue
        if v * (1000 if m.group(2) == '조' else 0.1) > USD_LIMIT_BN:  # 1조달러=$1,000B
            return True
    for m in _AMT_KRW.finditer(s or ''):
        try:
            if float(m.group(1).replace(',', '')) > KRW_LIMIT_TRN:
                return True
        except ValueError:
            continue
    return False


def classify_ticker(code: str) -> str:
    """'ok' | 'index'(회사 아님·정상) | 'bad'(확실한 오류) | 'unknown'(판정 불가)."""
    c = (code or '').strip().upper()
    if not c:
        return 'ok'
    if c in NOT_A_TICKER:
        return 'bad'
    if c in NOT_A_COMPANY:
        return 'index'
    if re.fullmatch(r'\d{6}', c):
        return 'ok'                      # 한국 — 형식만 본다
    if re.fullmatch(r'[A-Z][A-Z.\-]{0,9}', c):
        known = us_ticker_known(c)
        if known is None:
            return 'unknown'             # 목록을 못 읽음 — 멀쩡한 걸 지우지 않는다
        return 'ok' if known else 'bad'
    return 'unknown'


def _walk_strings(o, depth: int = 0):
    """중첩 dict/list 안의 문자열을 전부 뽑는다. _flags 자신은 건너뛴다."""
    if depth > 6:
        return
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if str(k).startswith('_'):
                continue
            yield from _walk_strings(v, depth + 1)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _walk_strings(v, depth + 1)


def sanitize(a: dict) -> dict:
    """분석 결과를 제자리에서 손본다. 반환값은 같은 dict.

    · 틀린 티커 코드는 **코드만** 비운다(이름은 남긴다).
    · 금액 이상치는 손대지 않고 a['_flags'] 에 기록한다.
    """
    if not isinstance(a, dict):
        return a
    fixed, flagged = [], []
    for t in (a.get('tickers') or []):
        if not isinstance(t, dict):
            continue
        code = str(t.get('ticker') or '').strip()
        if not code:
            continue
        kind = classify_ticker(code)
        if kind == 'bad':
            # 이름은 맞고 코드만 틀린 경우가 대부분 — 링크만 없앤다.
            t['ticker'] = ''
            fixed.append(f'{t.get("name")}:{code}')
        elif kind == 'index':
            t['ticker'] = ''             # 지수·통화는 종목 링크를 걸 대상이 아니다
    # 금액 검사는 **필드 이름을 안 가리고** 문자열을 전부 훑는다.
    # _parse 는 유튜브 요약뿐 아니라 /ir 공시 카드·딥다이브도 거치는데, 그쪽은
    # summary/key_points 가 아니라 one_liner·current·notes·news_digest 에 글이 있다.
    # 필드명을 열거하면 카드 구조가 바뀔 때마다 검사가 조용히 비어버린다.
    for s in _walk_strings(a):
        if implausible_amount(s):
            flagged.append(s[:120])
    if fixed or flagged:
        f = a.setdefault('_flags', {})
        if fixed:
            f['ticker_cleared'] = fixed
            print(f'[사실검사] 잘못된 티커 코드 {len(fixed)}건 제거: {", ".join(fixed)}')
        if flagged:
            f['amount_suspect'] = flagged
            print(f'[사실검사] 금액 이상치 {len(flagged)}건 — 본문은 유지, 확인 필요')
    return a
