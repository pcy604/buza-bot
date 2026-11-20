"""실적 발표 하루 전 알림 — 감시 종목(미국) (2026-11-12, 백로그 8).

왜: 10-24 점검에서 '다음 주 실적 슈퍼위크'를 뉴스 요약이 놓쳤다. 실적일은 뉴스가 아니라 '일정'이라
뉴스 선별로는 잡히지 않는다. 일정표에서 직접 가져와 전날 알린다.

원천: Nasdaq 실적 캘린더 공개 API(api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD) — 키 불필요, 날짜별 전 종목.
  미국 동부 날짜 기준. 'time-pre-market'(개장 전)·'time-after-hours'(마감 후)·'time-not-supplied'.
한국: DART '기업설명회(IR)개최(안내공시)'·잠정실적은 이미 공시 알림(check_kr_filings)으로 바로 간다 — 여기선 안 다룬다.

발송: 하루 한 번, KST 18시 이후 첫 크론 → 미국 '다음 거래일' 실적 발표 감시 종목. 같은 (chat, 종목, 날짜)는 한 번만.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

STATE_PATH = Path(__file__).parent / 'earnings_state.json'
URL = 'https://api.nasdaq.com/api/calendar/earnings?date={d}'
TIME_KO = {'time-pre-market': '개장 전', 'time-after-hours': '장 마감 후', 'time-not-supplied': '시각 미정'}


def next_us_day(today_et: date) -> date:
    d = today_et + timedelta(days=1)
    while d.weekday() >= 5:          # 토·일 건너뜀(공휴일은 캘린더가 비어서 자연히 0건)
        d += timedelta(days=1)
    return d


def fetch(d: date) -> list:
    import requests
    r = requests.get(URL.format(d=d.isoformat()), timeout=20,
                     headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    r.raise_for_status()
    return parse(r.json())


def parse(j: dict) -> list:
    rows = ((j or {}).get('data') or {}).get('rows') or []
    out = []
    for r in rows:
        sym = str(r.get('symbol') or '').strip().upper()
        if sym:
            out.append({'symbol': sym, 'name': r.get('name') or '', 'time': r.get('time') or '',
                        'eps': r.get('epsForecast') or '', 'q': r.get('fiscalQuarterEnding') or ''})
    return out


def plan(watches: dict, cal: list, d: date, sent: set) -> dict:
    """{chat: [행,…]} — 순수 함수. watches: {chat: [티커]} (한국 .KS/.KQ 는 무시)."""
    by = {r['symbol']: r for r in cal}
    out = {}
    for chat, tks in (watches or {}).items():
        for tk in tks or []:
            t = str(tk).upper()
            if '.' in t or t not in by:
                continue
            key = f'{chat}|{t}|{d.isoformat()}'
            if key in sent:
                continue
            out.setdefault(str(chat), []).append(by[t])
    return out


def text(d: date, rows: list) -> str:
    wd = '월화수목금토일'[d.weekday()]
    L = [f'🗓️ <b>내일 실적 발표</b> · {d.month}/{d.day}({wd}) 미국 동부 기준']
    for r in rows:
        when = TIME_KO.get(r['time'], '시각 미정')
        tail = ' · '.join(x for x in [f"EPS 예상 {r['eps']}" if r['eps'] else '', r['q']] if x)
        L.append(f"• <b>{r['symbol']}</b> {when}" + (f' — {tail}' if tail else '')
                 + f"  /report_{r['symbol']}")
    L.append('<i>장 마감 후 발표는 한국 시간 다음 날 아침이에요. 발표 뒤 공시(8-K)는 바로 따로 알려 드려요.</i>')
    return '\n'.join(L)


def _load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def run(send, watches: dict, now=None, cal=None) -> int:
    """KST 18시 이후 하루 한 번. send(chat, text) → bool."""
    now = now or datetime.now(timezone.utc)
    kst = now + timedelta(hours=9)
    st = _load()
    if kst.hour < 18 or st.get('day') == kst.date().isoformat():
        return 0
    et = (now - timedelta(hours=5)).date()
    d = next_us_day(et)
    if cal is None:
        try:
            cal = fetch(d)
        except Exception as e:
            print(f'[실적 캘린더 실패] {type(e).__name__}: {str(e)[:80]}')
            return 0              # day 를 찍지 않는다 — 다음 크론에서 다시 시도
    sent = set(st.get('sent', []))
    n = 0
    for chat, rows in plan(watches, cal, d, sent).items():
        if send(chat, text(d, rows)):
            sent |= {f"{chat}|{r['symbol']}|{d.isoformat()}" for r in rows}
            n += 1
    cut = (d - timedelta(days=14)).isoformat()
    st = {'day': kst.date().isoformat(), 'cal_n': len(cal),
          'sent': sorted(k for k in sent if k.rsplit('|', 1)[-1] >= cut)}
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    return n
