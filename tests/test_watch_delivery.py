"""공시 알림 전달 회귀 테스트 (2026-10-21) — 네트워크·LLM 없이 돈다.

    python tests/test_watch_delivery.py

고정하는 결함:
  ① 감시자 한 명이 봇을 차단(403)하면 기준선이 안 넘어가 나머지가 같은 공시를 매 실행마다 다시 받음
  ② 일시 실패 뒤 재시도에서 이미 받은 사람이 또 받음(중복)
  ③ 미국 공시를 '최신 1건'만 비교해 6시간 사이 2건이면 앞의 것이 누락
  ④ 감시 경로에서 요약 실패 시 사용자에게 '티커를 확인해 주세요' 오류문 반복 · 요약이 계속 실패하면 영영 미발송
  ⑤ 같은 공시 카드를 감시자 수만큼 LLM 으로 생성
"""
import os
import sys
import tempfile
from pathlib import Path

for k, v in {'SUPABASE_URL': 'https://dummy.supabase.co', 'SUPABASE_KEY': 'dummy',
             'TELEGRAM_TOKEN': '0:dummy', 'GEMINI_KEY': 'x'}.items():
    os.environ.setdefault(k, v)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import ir  # noqa: E402
import tg  # noqa: E402

TMP = Path(tempfile.mkdtemp())
ir.STATE_PATH = TMP / 'ir_state.json'


def fail(code, desc):
    tg.LAST_ERR.clear()
    tg.LAST_ERR.update(code=code, desc=desc)
    return False


def ok():
    tg.LAST_ERR.clear()
    return True


# ── ① 차단한 사용자 때문에 다른 사람이 반복 수신하지 않는다 (한국 공시) ──
st = ir.load_state()
st['watches'] = {'1': ['005930.KS'], '2': ['005930.KS']}
st['seen'] = {'005930.KS': '20261020000001'}
ir.save_state(st)
FS = [{'rcept_no': '20261021000009', 'report_nm': '단일판매ㆍ공급계약체결', 'rcept_dt': '20261021',
       'major': True, 'fold': False, 'url': 'u'}]
ir.kr_filings = lambda t, days=14: FS
GOT = []


def send_kr(c, t, new):
    if c == 1:
        return fail(403, 'Forbidden: bot was blocked by the user')
    GOT.append(c)
    return ok()


assert ir.check_kr_filings(send_kr) == 1
assert GOT == [2] and ir.load_state()['seen']['005930.KS'] == '20261021000009', (GOT, ir.load_state())
GOT.clear()
assert ir.check_kr_filings(send_kr) == 0 and GOT == [], '다음 실행에 다시 보내면 안 됨'
print('✅ 차단(403) 사용자는 받은 것으로 처리 — 나머지에게 한 번만, 기준선 진행')

# ── ② 일시 실패한 사람에게만 다시 보낸다 ──
FS[0] = dict(FS[0], rcept_no='20261021000010')
DOWN = {2}


def send_kr2(c, t, new):
    if c in DOWN:
        return fail(None, '')          # 네트워크 오류 같은 일시 실패
    GOT.append(c)
    return ok()


ir.check_kr_filings(send_kr2)
assert GOT == [1] and ir.load_state()['seen']['005930.KS'] == '20261021000009', '일시 실패면 기준선 유지'
DOWN.clear()
GOT.clear()
ir.check_kr_filings(send_kr2)
assert GOT == [2] and ir.load_state()['seen']['005930.KS'] == '20261021000010', GOT
print('✅ 일시 실패 → 다음 실행에 못 받은 사람에게만(중복 없음)')

# ── ③ 미국: 기준선 이후 2건이면 최신은 카드, 앞의 것은 같은 메시지에 목록 ──
st = ir.load_state()
st['watches'] = {'1': ['SATL'], '2': ['SATL']}
st['seen'] = {'SATL': 'A0'}
st['dlv'] = {}
ir.save_state(st)
ir.resolve_ticker = lambda t: (123, 'Satellogic')
H = [{'form': '8-K', 'acc': 'A2', 'date': '2026-10-21', 'primary': 'b.htm', 'items': '8.01'},
     {'form': '10-Q', 'acc': 'A1', 'date': '2026-10-21', 'primary': 'a.htm', 'items': ''},
     {'form': '8-K', 'acc': 'A0', 'date': '2026-10-01', 'primary': 'z.htm', 'items': ''}]
ir.filing_history = lambda cik, limit=24: H
CALLS = []


def card(c, t, also=None, quiet=False, text_only=False):
    CALLS.append((c, [f['acc'] for f in (also or [])], quiet, text_only))
    return ok()


ir.check_watches(card)
assert [x[1] for x in CALLS] == [['A1'], ['A1']] and all(x[2] for x in CALLS), CALLS
assert ir.load_state()['seen']['SATL'] == 'A2'
CALLS.clear()
ir.check_watches(card)
assert CALLS == [], '같은 공시 두 번 안 보냄'
print('✅ 미국 공시: 6시간 사이 2건 → 최신 카드 + 앞의 10-Q 목록 (누락 없음)')

# ── ④ 요약이 계속 실패하면 DLV_MAX_FAILS 회 뒤 텍스트로라도 보낸다 ──
H.insert(0, {'form': '8-K', 'acc': 'A3', 'date': '2026-10-22', 'primary': 'c.htm', 'items': '2.02'})
SUMMARY_OK = {'v': False}


def card2(c, t, also=None, quiet=False, text_only=False):
    CALLS.append(text_only)
    return ok() if (text_only or SUMMARY_OK['v']) else fail(None, '')


for _ in range(ir.DLV_MAX_FAILS):
    ir.check_watches(card2)
assert ir.load_state()['seen']['SATL'] == 'A2' and not any(CALLS), CALLS
CALLS.clear()
ir.check_watches(card2)
assert CALLS == [True, True] and ir.load_state()['seen']['SATL'] == 'A3', CALLS
print(f'✅ 요약 {ir.DLV_MAX_FAILS}회 실패 → 텍스트(종류·날짜·원문 링크)로 대체 발송, 누락 없음')

# ── ⑤ bot.send_ir_card: 한 실행에 카드 1회 생성 · 감시 경로는 오류문 안 보냄 ──
import bot  # noqa: E402

OUT = []
tg.send_message = lambda c, t, **k: (OUT.append((c, t)), ok())[1]
tg.send_photo = lambda c, p, cap='': (OUT.append((c, cap)), ok())[1]
bot.card.render_png = lambda c, png: Path(png).write_bytes(b'x')
N = {'n': 0}


def summ(ticker, earnings_only=False):
    N['n'] += 1
    return ({'doc_title': '실적', 'one_liner': 'x'}, H[0])


ir.summarize_filing = summ
bot._IR_CARD.clear()
assert bot.send_ir_card(1, 'SATL', also=H[1:2], quiet=True) and bot.send_ir_card(2, 'SATL', quiet=True)
assert N['n'] == 1, f'LLM {N["n"]}회 — 감시자 수만큼 부르면 안 됨'
assert '함께 나온 공시 1건' in OUT[0][1], OUT[0]
bot._IR_CARD.clear()
OUT.clear()
ir.summarize_filing = lambda ticker, earnings_only=False: (None, None)
assert not bot.send_ir_card(1, 'SATL', quiet=True) and OUT == [], '감시 경로는 사용자에게 오류문 금지'
assert not bot.send_ir_card(1, 'SATL') and '실패' in OUT[-1][1], '/ir 직접 요청은 오류문 그대로'
print('✅ 카드 1회 생성 후 팬아웃 · 감시 경로 요약 실패는 조용히 재시도')
print('ALL PASS')
