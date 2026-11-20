# -*- coding: utf-8 -*-
"""발행 차단 종목을 배치로 되살린다 — "요청했더니 안 나오더라"를 없애기 위한 것.

## 왜 필요한가 (2026-09-06 실측)

`bot.send_deck` 은 데이터가 **없을 때만** autogen 을 돌린다. **낡았을 때는 안 돌린다.**
그래서 한 번 만든 종목은 30일이 지나 `check.py` 신선도 게이트에 걸리는 순간
영구히 발행 불가가 되고, 사람이 로컬에서 `python autogen.py TSLA` 를 돌려 커밋할
때까지 러너는 스스로 못 고친다. 실측 당시 19종 중 6종이 이미 죽어 있었고
(SATL·TSLA·SNDK·AAPL·PLTR·IONQ) 나머지도 09-23 이면 전부 넘어갈 예정이었다.

## 나이가 아니라 게이트 결과로 고른다

"30일 넘은 것"을 고르면 AXTI 를 놓친다 — 27일밖에 안 됐는데 초안 3일 뒤에 새 실적
공시가 나서 차단됐다. 나이와 무관하게 터지는 차단이 있다는 뜻이다. `check.blockers()`
는 LLM 0콜·렌더 0회라 19종을 전부 훑어도 공짜이므로, **게이트가 실제로 막은 것**을
그대로 대상으로 삼는다.

## 하루 1건이면 따라잡힌다

19종을 30일 주기로 유지하는 데 필요한 재생성은 하루 0.63건이다. 하루 1건이면
19일에 한 바퀴 돌아 30일 차단선보다 앞선다. autogen 1건은 Gemini 7~8콜이라
무료 티어 일일 한도 안쪽이고, `deck_live.AUTOGEN_PER_DAY` 2회 중 1회를 배치가
쓰고 나머지 1회는 사용자의 신규 종목 요청 몫으로 남는다.

## 실패한 종목이 쿼터를 갉아먹지 않게

재생성해도 안 풀리는 차단이 있다(데이터 소스가 비었거나 LOCKED 필드가 걸린 경우).
그걸 매일 다시 시도하면 쿼터만 태우고 아무도 그 사실을 모른다. 그래서 종목별로
연속 실패를 세고 MAX_FAILS 회 넘으면 배치에서 제외한다 — 사람이 봐야 할 것으로
분류하는 것이지 조용히 포기하는 게 아니다(`stuck()` 이 목록을 준다).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE_PATH = HERE.parent / 'deck_refresh.json'

# 연속 실패가 이만큼 쌓이면 배치에서 뺀다. 재생성으로 안 풀리는 차단이라는 뜻이라
# 사람이 데이터를 직접 손봐야 한다.
MAX_FAILS = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def save(state: dict):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')


def scan():
    """전 종목을 훑어 차단된 것만 [(티커, [(항목, 사유), ...]), ...] 로 돌려준다.

    LLM 0콜·렌더 0회. 임포트가 깨진 종목도 차단으로 잡힌다(check.blockers 가
    IMPORT 사유를 만든다) — 조용히 빠지면 그 종목만 영원히 안 고쳐진다.
    """
    import check
    out = []
    for tk in check._all_tickers():
        try:
            bl = check.blockers(tk)
        except Exception as e:                       # audit 자체가 죽는 경우
            bl = [('AUDIT', f'점검 중 예외: {type(e).__name__}: {e}')]
        if bl:
            out.append((tk, bl))
    return out


# 2026-10-20: 차단(30일)이 **난 뒤에야** 고치던 것을 그 전에 고친다.
# 실측(10-01~19): 22종을 30일 안에 한 바퀴 돌리려면 하루 0.73건이 필요한데, Gemini 503 으로
# 실제 성공은 19일에 8건(0.42건/일)이었다. 차단 종목이 10-07 1개 → 10-18 6개로 늘었다.
# 그래서 ① 21일 지난 종목도 미리 후보에 넣고 ② 사용자가 감시 중인 종목을 먼저 고친다.
REFRESH_AGE_D = 21


def _built_age(tk):
    """초안 나이(일). 모르면 None."""
    import check
    try:
        mod = check.module_for(tk)
        d = str(check._get(mod, 'BUILT_AT', '') or check._get(mod, 'AS_OF', '') or '')
        return (datetime.now(timezone.utc).date() - datetime.strptime(d, '%Y-%m-%d').date()).days
    except Exception:
        return None


def _watched() -> set:
    try:
        st = json.loads((HERE.parent / 'ir_state.json').read_text(encoding='utf-8'))
        return {t for lst in (st.get('watches') or {}).values() for t in lst}
    except Exception:
        return set()


def due():
    """[(티커, 사유)] — 차단된 것 + 감시 중인데 없는 것 + REFRESH_AGE_D 넘은 것."""
    import check
    out = {tk: bl for tk, bl in scan()}
    have = set(check._all_tickers())
    # 감시 중인데 리포트가 아예 없는 종목 — 사용자가 /report 를 치기 전에 만들어 둔다.
    # 그래야 3~5분 기다리지 않고 즉시 받는다(2026-10-20).
    for tk in sorted(_watched() - have):
        out[tk] = [('NEW', '감시 중인데 리포트가 없음 — 미리 생성')]
    for tk in have:
        if tk in out:
            continue
        age = _built_age(tk)
        if age is not None and age >= REFRESH_AGE_D:
            out[tk] = [('AGE', f'{age}일 — 차단(30일) 전에 미리 갱신')]
    return list(out.items())


def pick():
    """이번에 되살릴 종목 하나. 없으면 None.

    우선순위: ①연속 실패가 MAX_FAILS 미만 ②오늘 아직 안 건드림 ③이미 차단된 것
    ④사용자가 감시 중인 것 ⑤가장 오래 방치된 것. 마지막 시도 기록이 없으면
    '가장 오래됨'으로 본다 — 한 번도 손대지 않은 종목이 먼저 나가야 한 바퀴가 돈다.
    """
    state = load()
    today = _today()
    watched = _watched()
    cands = []
    for tk, bl in due():
        s = state.get(tk) or {}
        if s.get('fails', 0) >= MAX_FAILS:
            continue                                  # 사람이 봐야 하는 것
        last = str(s.get('last_try') or '')
        if last[:10] == today:
            continue                                  # 오늘 이미 시도함
        blocked = not all(item == 'AGE' for item, _ in bl)
        cands.append((0 if blocked else 1, 0 if tk in watched else 1, last or '', tk))
    if not cands:
        return None
    cands.sort()
    return cands[0][-1]


def mark(ticker: str, ok: bool, reasons=None, transient=False):
    """시도 결과를 기록한다. 성공하면 연속 실패를 0으로 되돌린다.

    ⚠️ `transient` 는 **종목 탓이 아닌 실패**를 뜻한다(Gemini 일일 한도 소진, 네트워크
    끊김 등). 이걸 구분하지 않으면 API 가 하루 죽은 날 서로 다른 종목 3개가 나란히
    fails 를 쌓고, 멀쩡한 종목들이 MAX_FAILS 에 걸려 배치에서 영구히 빠진다 —
    원인은 API 인데 벌은 종목이 받는다. 실측(2026-09-06)에서 autogen 이 분당 한도
    재시도를 다 쓰고 SystemExit 으로 죽는 걸 보고 넣었다.
    그래서 transient 일 때는 last_try 만 남기고 fails 는 올리지 않는다.
    """
    state = load()
    s = state.get(ticker) or {}
    s['last_try'] = _now()
    if ok:
        s['fails'] = 0
        s['last_ok'] = _now()
        s.pop('last_reason', None)
    elif transient:
        s['last_error'] = '; '.join(str(r) for r in (reasons or [])[:1]) or 'API/네트워크 실패'
    else:
        s['fails'] = int(s.get('fails', 0)) + 1
        if reasons:
            s['last_reason'] = '; '.join(f'{k}: {v}' for k, v in reasons[:2])
    state[ticker] = s
    save(state)
    return s


def stuck():
    """재생성으로 안 풀려 배치에서 빠진 종목 — 사람이 봐야 할 목록."""
    state = load()
    return {tk: s for tk, s in state.items() if int(s.get('fails', 0)) >= MAX_FAILS}


def summary() -> str:
    """로그 한 줄. 크론 로그만 보고도 재고 상태를 알 수 있게."""
    blocked = scan()
    st = stuck()
    return (f'차단 {len(blocked)}종'
            + (f' (그중 사람 확인 필요 {len(st)}종: {", ".join(sorted(st))})' if st else ''))
