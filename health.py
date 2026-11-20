"""운영 장애 알림 (2026-10-21, 지인 베타 전) — 조용히 실패하는 단계를 운영자에게 알린다.

run.py 는 단계마다 try/except 로 오류를 삼키고 실행 자체는 '성공'으로 끝난다 — 한 단계가 죽어도
나머지는 돌아야 하니 그 구조는 맞다. 문제는 **아무도 모른다**는 것: SEC 차단·Gemini 쿼터 소진·DART
불통이 며칠씩 이어져도 Actions 는 초록불이다.

  · 단계(name)마다 연속 실패 횟수를 job_state.json['health'] 에 둔다(러너는 매번 새 컨테이너 → 커밋되는 상태 파일).
  · STREAK 회 연속 실패하면 운영자에게 1번 알리고, 그 뒤엔 REPEAT_H 시간마다 한 번만 다시 알린다.
  · 다시 성공하면 '복구' 1번.
  · 한 번 실패는 알리지 않는다 — 외부 소스는 원래 가끔 끊긴다(DART 해외 접속 등). 소음이 경보를 죽인다.

받는 사람 = OWNER_CHAT 환경변수 → config.OWNER_CHAT (brief._owner_chat, 2026-10-23 첫 가입자 추측 폐기).
봇이 **아예 안 도는** 고장(Actions 한도 소진·크론 정지)은 여기서 못 본다 — 그건 stock-dashboard 의
bot-watchdog 워크플로가 바깥에서 본다.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

STATE = Path(__file__).parent / 'job_state.json'
STREAK = 3
REPEAT_H = 12


def _now():
    return datetime.now(timezone.utc)


def _load():
    try:
        return json.loads(STATE.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def update(results: dict, notify=None, now=None) -> list:
    """results = {단계 이름: None(성공) 또는 오류 문자열}. 이번 실행에서 돈 단계만 넣는다.
    보낸(보낼) 메시지 목록을 돌려준다. notify(text) 가 없으면 운영자에게 텔레그램."""
    now = now or _now()
    s = _load()
    h = s.setdefault('health', {})
    msgs = []
    for name, err in results.items():
        r = h.get(name) or {'streak': 0}
        if err is None:
            if r.get('alerted'):
                msgs.append(f'✅ <b>복구</b> · {name} — {r["streak"]}회 연속 실패 뒤 정상')
            h.pop(name, None)
            continue
        r['streak'] = r.get('streak', 0) + 1
        r['last'] = str(err)[:160]
        r.setdefault('since', now.isoformat(timespec='minutes'))
        last_alert = r.get('alerted')
        due = (r['streak'] >= STREAK and
               (not last_alert or now - datetime.fromisoformat(last_alert) >= timedelta(hours=REPEAT_H)))
        if due:
            msgs.append(f'🔴 <b>장애</b> · {name} — {r["streak"]}회 연속 실패 (시작 {r["since"][5:16]}Z)\n'
                        f'<code>{_esc(r["last"])}</code>')
            r['alerted'] = now.isoformat(timespec='minutes')
        h[name] = r
    if msgs:
        text = '🛠️ <b>부자알람 운영 알림</b>\n\n' + '\n\n'.join(msgs)
        sent = (notify or _send_owner)(text)
        if not sent:            # 못 보냈으면 다음 실행에 다시 시도하도록 알림 시각을 지운다
            for name in results:
                if name in h and h[name].get('alerted') == now.isoformat(timespec='minutes'):
                    h[name].pop('alerted')
    s['health'] = h
    STATE.write_text(json.dumps(s), encoding='utf-8')
    return msgs


def _esc(t: str) -> str:
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _send_owner(text: str) -> bool:
    try:
        import brief
        import tg
        chat = brief._owner_chat()
        return bool(chat) and tg.send_message(chat, text)
    except Exception as e:
        print(f'[운영 알림 실패] {e}')
        return False
