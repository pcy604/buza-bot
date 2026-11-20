"""운영 장애 알림 회귀 테스트 (2026-10-21) — 네트워크 없이 돈다.

    python tests/test_health.py
"""
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import health  # noqa: E402

health.STATE = Path(tempfile.mkdtemp()) / 'job_state.json'
health.STATE.write_text('{"last_job_run": "x"}', encoding='utf-8')
SENT = []
note = lambda t: (SENT.append(t), True)[1]          # noqa: E731
T0 = datetime(2026, 10, 21, 0, 0, tzinfo=timezone.utc)

# 1·2회 실패는 조용히, 3회째 1번 알림
for i in range(2):
    assert health.update({'한국 공시 감시': 'ConnectTimeout'}, note, T0 + timedelta(hours=i)) == []
assert len(health.update({'한국 공시 감시': 'ConnectTimeout'}, note, T0 + timedelta(hours=2))) == 1
assert '3회 연속' in SENT[-1] and 'ConnectTimeout' in SENT[-1]
# 계속 실패해도 12시간 안엔 다시 안 알림, 12시간 지나면 1번 더
for i in range(3, 14):
    health.update({'한국 공시 감시': 'ConnectTimeout'}, note, T0 + timedelta(hours=i))
assert len(SENT) == 1, SENT
health.update({'한국 공시 감시': 'ConnectTimeout'}, note, T0 + timedelta(hours=14, minutes=1))
assert len(SENT) == 2
# 이번 실행에서 안 돈 단계는 연속 횟수에 영향 없음, 다른 단계 성공은 무관
health.update({'감시 뉴스': None}, note, T0 + timedelta(hours=15))
assert len(SENT) == 2
# 복구 시 1번
health.update({'한국 공시 감시': None}, note, T0 + timedelta(hours=16))
assert len(SENT) == 3 and '복구' in SENT[-1]
health.update({'한국 공시 감시': None}, note, T0 + timedelta(hours=17))
assert len(SENT) == 3
# 알리지 않은 채 회복(1~2회 실패)이면 '복구' 알림도 없음
health.update({'IR 공시 감시': 'HTTP 403'}, note, T0)
health.update({'IR 공시 감시': None}, note, T0 + timedelta(hours=6))
assert len(SENT) == 3
# 발송 실패면 다음 실행에 다시 시도
fail = lambda t: False                               # noqa: E731
for i in range(3):
    health.update({'팬아웃': 'boom'}, fail, T0 + timedelta(hours=i))
assert len(health.update({'팬아웃': 'boom'}, note, T0 + timedelta(hours=3))) == 1
# 기존 job_state 키는 보존
import json  # noqa: E402
assert json.loads(health.STATE.read_text(encoding='utf-8'))['last_job_run'] == 'x'
# HTML 이스케이프
health.update({'x': '<bad & tag>'}, note, T0)
health.update({'x': '<bad & tag>'}, note, T0 + timedelta(hours=1))
health.update({'x': '<bad & tag>'}, note, T0 + timedelta(hours=2))
assert '&lt;bad &amp; tag&gt;' in SENT[-1]
print('✅ 3회 연속 실패 시 1번 · 12시간마다 재알림 · 복구 1번 · 발송 실패 재시도 · 상태 보존')
print('ALL PASS')
