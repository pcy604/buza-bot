"""사용자 명령 히스토리 — 로컬 JSON 로그 (/recap 요약용)."""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

LOG_PATH = Path(__file__).parent / 'cmd_log.json'
MAX_ENTRIES = 3000


def _load() -> list:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    return []


def log(chat_id: int, cmd: str, arg: str = ''):
    entries = _load()
    entries.append({'chat': chat_id, 'ts': datetime.now(timezone.utc).isoformat(), 'cmd': cmd, 'arg': arg})
    LOG_PATH.write_text(json.dumps(entries[-MAX_ENTRIES:], ensure_ascii=False), encoding='utf-8')


def recent(chat_id: int, days: int = 7) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for e in _load():
        if e.get('chat') != chat_id:
            continue
        try:
            if datetime.fromisoformat(e['ts']) >= cutoff:
                out.append(e)
        except Exception:
            continue
    return out
