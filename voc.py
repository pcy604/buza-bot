"""VOC(사용자 의견) 수집 — /voc <내용> (2026-10-21).

왜 이 구조인가
- 취합이 복잡해지지 않게 **한 곳(voc_log.json)** 에만 쌓는다. cmd_log.json 처럼 매 실행 끝에 레포로 커밋된다(run.yml).
- 받는 즉시 소유자에게 텔레그램으로 그대로 넘긴다 → 따로 모아 볼 필요 없이 '알림 = 수신함'.
- 소유자는 /voc list(열린 것) · /voc done <번호>(처리 완료) 로만 관리한다. 번호는 1부터 증가, 지워지지 않는다.
- kpi.kpi_voice 가 이번 달 외부 건수를 센다(소유자 본인 건은 따로 표시 — 본인 테스트가 KPI 를 부풀리지 않게).
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / 'voc_log.json'
MAX_LEN = 1500        # 한 건 최대 글자 수(텔레그램 4096 안에서 소유자 알림 머리말까지 들어가게)


def _load() -> list:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding='utf-8')) or []
        except Exception:
            pass
    return []


def _save(rows: list):
    LOG_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding='utf-8')


def add(chat, username, text: str, is_owner: bool = False) -> dict:
    rows = _load()
    row = {'id': (max((r.get('id', 0) for r in rows), default=0) + 1),
           'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'chat': chat, 'user': username or '', 'owner': bool(is_owner),
           'text': (text or '').strip()[:MAX_LEN], 'status': 'open'}
    rows.append(row)
    _save(rows)
    return row


def open_items(limit: int = 20) -> list:
    return [r for r in _load() if r.get('status') == 'open'][-limit:]


def close(vid: int):
    """처리 완료로 바꾸고 그 행을 돌려준다(없으면 None) — 호출부가 원래 보낸 사람에게 알린다."""
    rows = _load()
    for r in rows:
        if r.get('id') == vid and r.get('status') == 'open':
            r['status'] = 'done'
            r['done_ts'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            _save(rows)
            return r
    return None


def month_counts(now=None) -> dict:
    """이번 달(UTC) 건수 — 외부/본인/열린 것."""
    now = now or datetime.now(timezone.utc)
    ym = now.strftime('%Y-%m')
    rows = [r for r in _load() if str(r.get('ts', '')).startswith(ym)]
    return {'external': sum(1 for r in rows if not r.get('owner')),
            'owner': sum(1 for r in rows if r.get('owner')),
            'open': sum(1 for r in _load() if r.get('status') == 'open')}
