# -*- coding: utf-8 -*-
"""봇에서 12장 포토카드를 즉석 렌더한다.

## 왜 러너에서 렌더가 되나 (실측)

오래 "검수 때문에 봇으로는 못 준다"고 봤지만, 실측해보니 막는 게 없었다.

| | 실측 |
|---|---|
| `probe.py` 판정 | 8초 · **Gemini 0콜** |
| 12장 렌더 | 24초 · **Gemini 0콜** |
| 렌더가 쓰는 외부 API | SEC EDGAR · Yahoo 차트 · 위키미디어 — 전부 무료·무인증 |
| 한글 폰트 | `deck16 → report._font → card.FONT_CANDIDATES`에 리눅스 nanum 경로 있음 |
| run.yml 예산 | 14분 |

Gemini를 쓰는 건 `autogen`(신규 종목 초안)뿐이다. **데이터 파일이 이미 있으면
렌더는 공짜이고, 덤으로 주가·시총이 오늘 값으로 갱신된다** — file_id 재전송이
발행 당시 그림을 그대로 보내는 것과 다른 점이다.

## 검수는 게이트가 아니라 예외 경로다

`check.py`가 발행 전에 기계로 훑는다(BLOCK/WARN/INFO). 이 게이트는 사람이 12장을
눈으로 봐야만 빈 항목·자리표시자를 찾던 구조 자체를 없애려고 만든 것이다.
그래서 여기서는 BLOCK이 있을 때만 발송을 멈추고 무엇이 막혔는지 알려주며,
WARN은 캡션에 달아 내보낸다. `probe`가 PARTIAL이면 무엇이 빌지 미리 말해준다.

## 신규 종목과 쿼터

데이터 파일이 없으면 `autogen`이 필요하고 그건 Gemini를 8콜쯤 쓴다. 무료 쿼터가
빠듯해서 연속 요청 한 번에 하루치가 날아갈 수 있으므로 하루 상한을 둔다.
상한을 넘으면 만들지 않고 그 사실을 그대로 알린다.
"""
import datetime
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECKS = HERE / 'decks'
QUOTA_PATH = HERE / 'deck_quota.json'
AUTOGEN_PER_DAY = 3          # 신규 종목 초안 생성 하루 상한 (Gemini 8콜/건). 2026-10-20: 2→3 — 재고 갱신 2건 + 사용자 요청 1건

# "오늘"을 사용자의 하루로 고정한다. date.today()는 실행 머신의 로컬 시각이라
# 노트북(KST)과 러너(UTC)가 서로 다른 날짜를 세고, 정작 사용자는 폴란드에 있어
# 셋 다 어긋났다 — 봇이 "오늘 한도를 다 썼어요"라고 한 시점이 사용자에겐
# 막 잠에서 깬 아침이었다.
USER_TZ = 'Europe/Warsaw'


def _now():
    import datetime as _dt
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo(USER_TZ))
    except Exception:            # tzdata가 없는 환경이면 UTC로라도 일관되게
        return _dt.datetime.now(_dt.timezone.utc)


def _today() -> str:
    return _now().date().isoformat()


def quota_reset_in() -> str:
    """다음 리셋까지 남은 시간 — "내일"이라고 뭉개지 않고 실제 시각으로 말한다."""
    import datetime as _dt
    now = _now()
    nxt = (now + _dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    h, m = divmod(int((nxt - now).total_seconds() // 60), 60)
    return f'{h}시간 {m}분 뒤' if h else f'{m}분 뒤'


def _decks_path():
    """decks/ 모듈들은 서로를 최상위 이름으로 임포트해서 경로에 넣어줘야 한다."""
    p = str(DECKS)
    if p not in sys.path:
        sys.path.insert(0, p)


def has_data(ticker: str) -> bool:
    """이 종목의 데이터 파일이 있나 — 있으면 Gemini 없이 렌더된다."""
    _decks_path()
    import build
    cfg = build.TICKERS.get(ticker.upper())
    if cfg:
        return True
    return bool(build._auto_config(ticker.upper()))


def probe(ticker: str) -> dict:
    """LLM 0콜 사전 점검. {'verdict': 'OK'|'PARTIAL'|'NO', ...}"""
    _decks_path()
    import probe as _probe
    return _probe.probe(ticker.upper())


def block_reasons(ticker: str):
    """발행 게이트가 막는 이유들 — [(항목, 설명), ...]. 렌더 0회·Gemini 0콜.

    예전엔 24초짜리 렌더를 끝내야 차단 여부를 알 수 있었다. 그래서 '데이터가 낡아서
    어차피 막힐 종목'에도 매번 렌더를 다 돌리고 나서야 실패를 알렸다. 여기서 미리
    보면 그리기 전에 "재생성부터 할지"를 정할 수 있다.
    """
    _decks_path()
    import check
    return check.blockers(ticker.upper())


# ── autogen 하루 상한 ────────────────────────────────────────────────
def _quota() -> dict:
    if not QUOTA_PATH.exists():
        return {}
    try:
        return json.loads(QUOTA_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}


def autogen_left() -> int:
    today = _today()
    return max(0, AUTOGEN_PER_DAY - _quota().get(today, 0))


def _spend_autogen():
    today = _today()
    q = {today: _quota().get(today, 0) + 1}   # 오늘 것만 남긴다(파일이 안 커지게)
    QUOTA_PATH.write_text(json.dumps(q, ensure_ascii=False), encoding='utf-8')


def _refund_autogen():
    """산출물 없이 끝난 시도는 하루 상한에서 돌려준다.

    2026-09-06 에 하루 상한 2회가 **결과물 0개**로 소진됐다. 한 번은 중간에 취소됐고
    한 번은 Gemini 한도에 걸려 미완주했는데, 두 경우 다 데이터 파일은 그대로인데
    카운터만 깎였다. 그러면 정작 리포트가 필요할 때 "오늘 한도를 다 썼어요"가 뜬다 —
    쓰지도 못한 몫을 잃는 것이다.
    상한의 목적은 **Gemini 무료 쿼터 보호**이고, 실패한 호출도 쿼터를 쓰긴 하므로
    무제한 환불은 위험하다. 그래서 되돌리되 바닥(0) 아래로는 안 내려간다.
    """
    today = _today()
    n = _quota().get(today, 0)
    if n <= 0:
        return
    QUOTA_PATH.write_text(json.dumps({today: n - 1}, ensure_ascii=False), encoding='utf-8')


def _data_stamp(ticker: str):
    """종목 데이터 파일의 지문 — 재생성이 실제로 뭔가 남겼는지 판정하는 데 쓴다."""
    _decks_path()
    tk = ticker.upper()
    try:
        if tk.endswith(('.KS', '.KQ')):
            import sources_kr
            name = sources_kr.module_name(tk)
        else:
            import autogen
            name = autogen._module_name(tk)
        p = DECKS / f'{name}.py'
        return (p.stat().st_mtime, p.stat().st_size) if p.exists() else None
    except Exception:
        return None


def generate(ticker: str) -> bool:
    """신규 종목 초안 생성(Gemini 사용). 상한을 넘으면 False."""
    if autogen_left() <= 0:
        return False
    _decks_path()
    # 임포트가 깨지면 LLM 호출은 한 번도 안 나간 것이므로 쿼터를 깎지 않는다.
    # 실제로 autogen.py의 문법 오류(3.12+ 전용 f-string)로 즉사했는데 하루 상한만
    # 1회 줄어든 적이 있다. 임포트를 통과한 뒤에 깎는다.
    tk = ticker.upper()
    if tk.endswith(('.KS', '.KQ')):
        # 한국 종목은 원문이 다르다(사업보고서·잠정실적공시·임원소유보고). autogen 을
        # 그대로 태우면 ir.resolve_ticker 가 SEC CIK 를 못 찾아 SystemExit 로 죽는다.
        # autogen_kr 은 숫자를 전부 결정론으로 채우고 서사만 Gemini 1콜을 쓴다 —
        # 미국판보다 쿼터를 훨씬 덜 먹는다.
        import autogen_kr
        return _run_autogen(tk, lambda: autogen_kr.write(tk, do_narrate=True))
    import autogen
    return _run_autogen(tk, lambda: autogen.generate(tk, write=True))


def _forget_module(tk: str):
    """재생성 직후 캐시된 옛 데이터 모듈을 버린다.

    ⚠️ 이게 없으면 **성공한 재생성이 실패로 기록된다.** run.py 배치는 한 프로세스에서
    `refresh.pick()`(전 종목 임포트) → `generate()`(파일 새로 씀) → `block_reasons()`
    순으로 도는데, 마지막 검사가 sys.modules 에 남은 **옛 모듈**을 읽는다. 그래서
    방금 고친 종목이 여전히 차단으로 보이고 refresh 가 fails 를 올린다.
    MAX_FAILS=3 이라 세 번 반복되면 멀쩡한 종목이 배치에서 영구히 빠진다.
    실측(2026-09-08): AXTI 가 BUILT_AT=2026-09-06 으로 정상 재생성됐는데
    deck_refresh.json 에는 재생성 *이전* 사유로 fails=1 이 찍혀 있었다.
    """
    import sys as _sys
    _decks_path()
    t = tk.upper()
    try:
        if t.endswith(('.KS', '.KQ')):
            import sources_kr
            name = sources_kr.module_name(t)
        else:
            import autogen
            name = autogen._module_name(t)
    except Exception:
        return
    _sys.modules.pop(name, None)


def _run_autogen(tk: str, fn) -> bool:
    """상한을 깎고 생성을 돌리되, **아무것도 안 남았으면 깎은 걸 돌려준다.**

    ⚠️ BaseException 으로 받는다 — autogen 은 실패 경로에서 SystemExit 을 던지므로
    Exception 만 잡으면 환불 없이 그대로 빠져나간다(실측으로 그렇게 한 칸을 잃었다).
    """
    before = _data_stamp(tk)
    _spend_autogen()
    try:
        fn()
        _forget_module(tk)
    except BaseException:
        if _data_stamp(tk) == before:
            _refund_autogen()
            print(f'[{tk}] 산출물 없이 실패 — 하루 상한 1회 환불')
        raise
    if _data_stamp(tk) == before:
        # 예외 없이 끝났는데 파일이 그대로면 내부에서 조용히 포기한 것이다.
        _refund_autogen()
        print(f'[{tk}] 데이터 파일이 안 바뀜 — 하루 상한 1회 환불')
        return False
    return True


# ── 렌더 + 게이트 ────────────────────────────────────────────────────
def render(ticker: str):
    """12장을 새로 그린다. (paths, n_block) 반환. 실패하면 (None, -1)."""
    _decks_path()
    ticker = ticker.upper()
    try:
        import build
        import check
        # 한국 티커의 '.KQ'가 폴더명에 들어가면 '247540.kq' 처럼 확장자 있는 이름이 돼
        # 도구마다 다르게 해석한다(deck_pages 의 파일 접두어와 같은 규칙으로 맞춘다).
        out = str(DECKS / 'out' / ticker.lower().replace('.ks', '').replace('.kq', ''))
        paths = build.build(ticker, out_dir=out)
        mod = getattr(build, 'data_module', None)
        n_block = check.report(ticker, mod)
        return [str(p) for p in paths], n_block
    except Exception as e:
        print(f'[덱 렌더 실패] {ticker}: {e}')
        import traceback
        traceback.print_exc()
        return None, -1
