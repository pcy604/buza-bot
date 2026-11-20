"""실적 발표 하루 전 알림 — 네트워크 없이 (2026-11-12)."""
import sys, tempfile
from datetime import date, datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import earnings
earnings.STATE_PATH = Path(tempfile.mkdtemp()) / 'e.json'
J = {'data': {'rows': [
    {'symbol': 'TSLA', 'name': 'Tesla', 'time': 'time-after-hours', 'epsForecast': '$0.55', 'fiscalQuarterEnding': 'Sep/2026'},
    {'symbol': 'NVDA', 'name': 'NVIDIA', 'time': 'time-pre-market', 'epsForecast': '', 'fiscalQuarterEnding': 'Oct/2026'}]}}
cal = earnings.parse(J)
assert [r['symbol'] for r in cal] == ['TSLA', 'NVDA']
assert earnings.parse({'data': None}) == [] and earnings.parse({}) == []
assert earnings.next_us_day(date(2026, 11, 13)) == date(2026, 11, 16)   # 금 → 월
W = {'2': ['TSLA', '005930.KS'], '3': ['AAPL'], '4': ['nvda', 'TSLA']}
OUT = []
send = lambda c, t: (OUT.append((c, t)), True)[1]
early = datetime(2026, 11, 12, 8, tzinfo=timezone.utc)                  # KST 17시 → 아직
assert earnings.run(send, W, now=early, cal=cal) == 0
now = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)                   # KST 19시, ET 11-12 → 11-13
assert earnings.run(send, W, now=now, cal=cal) == 2
d = dict(OUT)
assert 'TSLA' in d['2'] and '장 마감 후' in d['2'] and '/report_TSLA' in d['2'] and '005930' not in d['2']
assert 'NVDA' in d['4'] and '개장 전' in d['4'] and 'TSLA' in d['4']
assert earnings.run(send, W, now=now, cal=cal) == 0                     # 같은 날 두 번 안 보냄
print('ALL PASS')
