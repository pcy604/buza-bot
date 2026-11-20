"""먼저 묻고, 먼저 챙긴다 — 신규 사용자 리마인드 + 첫 경험 1문항 설문 (2026-11-12).

왜
- 11-12 진단: 외부 사용자 4명·3주간 외부 VOC 0건. /voc 는 '사용자가 스스로 찾아와 쓰는' 통로라
  불편을 느낀 사람은 말없이 떠난다(실측: 1명은 /start 만 3회 누르고 이탈).
- 그래서 봇이 먼저 두 번 묻는다. 둘 다 사람당 평생 1회(스팸 금지).
  ① 리마인드: /start 후 24시간 동안 종목 등록·기능 사용이 하나도 없으면 → 버튼 3개(종목 예시)로 다시 권한다.
  ② 설문: 처음 기능을 쓴 지 24시간 뒤 → '쓸만했나요?' 버튼 3개. 👎·😐 이면 '무엇이 아쉬웠나' 답장을 받는다(VOC 로 접수).
- 버튼은 ReplyKeyboard(누르면 그 글자가 일반 메시지로 온다)라 Worker·콜백 처리 추가 없이 기존 경로로 들어온다.

상태: nudge_state.json {chat: {'remind': ts, 'survey': ts, 'rating': '👍'}} — run.yml 이 커밋한다.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATE_PATH = Path(__file__).parent / 'nudge_state.json'
WAIT = timedelta(hours=24)
STALE = timedelta(days=30)          # 30일 넘게 조용한 사람에겐 보내지 않는다
# '가치를 받은' 명령 — 이걸 한 번이라도 썼으면 리마인드 대상이 아니라 설문 대상
VALUE_CMDS = {'/report', '/dashboard', '/market', '/watch', '/ir', '/yt', '/add', '/person',
              '(유튜브 링크)', '/watchlist', '/recap'}
RATINGS = {'👍 쓸만해요': 'good', '😐 그저 그래요': 'meh', '👎 별로예요': 'bad'}
ONBOARD_KB = {'keyboard': [[{'text': 'TSLA'}, {'text': '삼성전자'}, {'text': 'NVDA'}]],
              'resize_keyboard': True, 'one_time_keyboard': True,
              'input_field_placeholder': '종목 이름이나 티커'}
SURVEY_KB = {'keyboard': [[{'text': k} for k in RATINGS]],
             'resize_keyboard': True, 'one_time_keyboard': True}


def _load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def _save(d: dict):
    STATE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding='utf-8')


def _now():
    return datetime.now(timezone.utc)


def _iso(t):
    return t.isoformat(timespec='seconds')


def plan(rows: list, owner: str, watched: set, state: dict, now=None) -> list:
    """보낼 것 목록 [(chat, 'remind'|'survey')]. 순수 함수 — 테스트 대상.

    rows: activity_log [{ts, chat, cmd}] · watched: 감시 종목이 있는 chat 문자열 집합."""
    now = now or _now()
    first_start, first_value, last_seen = {}, {}, {}
    for r in rows:
        try:
            t = datetime.fromisoformat(r['ts'])
        except Exception:
            continue
        c = str(r.get('chat'))
        if c == owner:
            continue
        last_seen[c] = max(last_seen.get(c, t), t)
        if r.get('cmd') == '/start':
            first_start.setdefault(c, t)
        if r.get('cmd') in VALUE_CMDS:
            first_value.setdefault(c, t)
    out = []
    for c, seen in last_seen.items():
        st = state.get(c, {})
        if now - seen > STALE:
            continue
        if c in first_value or c in watched:
            t0 = first_value.get(c)
            if t0 and now - t0 >= WAIT and not st.get('survey'):
                out.append((c, 'survey'))
        elif c in first_start and now - first_start[c] >= WAIT and not st.get('remind'):
            out.append((c, 'remind'))
    return out


def run(send, owner: str, watched: set, rows: list = None, now=None) -> int:
    """크론에서 호출. send(chat, text, reply_markup) → bool."""
    if rows is None:
        import stats
        rows = stats._load()
    state = _load()
    n = 0
    for c, kind in plan(rows, str(owner or ''), {str(x) for x in watched}, state, now):
        if kind == 'remind':
            txt = ('👋 아직 지켜볼 종목을 안 정하셨네요.\n'
                   '아래 버튼을 누르거나 종목 이름을 보내 주시면, 그 종목의 <b>공시·중요 뉴스만</b> '
                   '하루 두 번 요약해 드려요. 별일 없는 날은 조용해요.\n\n'
                   '그냥 둘러보려면: /market (오늘 장 마감 시황) · /help')
            kb = ONBOARD_KB
        else:
            txt = ('🙏 부자알람 써 보신 지 하루가 지났어요. <b>쓸만했나요?</b>\n'
                   '아래 버튼 하나만 눌러 주세요. 아쉬운 점은 /voc 로 바로 고칠게요.')
            kb = SURVEY_KB
        if send(c, txt, kb):
            state.setdefault(c, {})[kind] = _iso(now or _now())
            if kind == 'remind':
                try:
                    import prefs
                    prefs.set_onboarding(int(c), True)   # 버튼 누른 티커가 곧장 감시 등록되게
                except Exception:
                    pass
            n += 1
    if n:
        _save(state)
    return n


def record_rating(chat, label: str) -> str:
    """설문 버튼 응답 기록 → 'good'|'meh'|'bad'."""
    r = RATINGS[label]
    state = _load()
    st = state.setdefault(str(chat), {})
    st['rating'] = r
    st['rated'] = _iso(_now())
    _save(state)
    return r


def summary(state: dict = None) -> dict:
    state = _load() if state is None else state
    vals = [v.get('rating') for v in state.values() if v.get('rating')]
    return {'asked': sum(1 for v in state.values() if v.get('survey')),
            'answered': len(vals), 'good': vals.count('good'),
            'meh': vals.count('meh'), 'bad': vals.count('bad'),
            'reminded': sum(1 for v in state.values() if v.get('remind'))}
