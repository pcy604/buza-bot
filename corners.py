# -*- coding: utf-8 -*-
"""코너(영상 종류) 선택 — 채널의 어떤 코너만 요약할지 고른다.

채널 하나가 하루 14개를 올리는데 그중 내가 볼 건 두어 개다(삼프로TV 실측).
지금은 MAX_PER_CHANNEL=2 로 **최신 2개**를 가져가므로, 뭘 받을지는 사실상
업로드 순서가 정한다 — 보고 싶은 코너가 밀려도 알 수 없다.

여기서는 코너를 골라두고, 고른 것만 수집 대상으로 남긴다.

## 설계 메모

· 코너명은 제목의 대괄호 표지에서 뽑는다(channels.program 과 **같은 함수**를 쓴다).
  두 군데서 따로 뽑으면 성적표에 보이는 이름과 고를 때 보이는 이름이 달라진다.
· 선택은 **화이트리스트**다. 비어 있으면 '전부'로 본다 — 새로 구독한 채널이
  아무것도 안 오는 상태로 시작하면 안 된다.
· 저장한 뒤 채널이 제목 형식을 바꾸면 고른 코너가 사라지고 **새 코너가 생긴다**.
  그걸 detect_new() 가 잡아 주간 브리핑에 올린다 — 규칙을 넣고 끝내면 언제
  썩었는지 알 수 없다.

⚠️ 코너표시가 없는 영상: 대괄호를 안 쓰는 채널도 있다(오종태의투자병법 17건).
   그런 채널은 코너가 '(코너표시 없음)' 하나로 뭉치므로 선택의 의미가 없다 —
   그 경우 선택 UI를 띄우지 않고 전체로 둔다.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from channels import program  # noqa: E402  — 성적표와 같은 이름 규칙을 쓴다

NO_TAG = '(코너표시 없음)'
MIN_CHOICES = 2          # 코너가 1종뿐이면 고를 게 없다


def survey(titles) -> list:
    """제목 목록 → [(코너명, 건수)] 많은 순. 선택지로 쓴다."""
    c = Counter(program(t) for t in titles if t)
    return c.most_common()


def worth_choosing(choices) -> bool:
    """고를 만한 채널인가 — 코너가 2종 이상이어야 의미가 있다."""
    real = [c for c, _ in choices if c != NO_TAG]
    return len(real) >= MIN_CHOICES


def selected_of(sub: dict) -> set:
    """구독 레코드에서 고른 코너 집합. 없거나 비면 빈 집합(=전부)."""
    v = (sub or {}).get('corners')
    if isinstance(v, str):
        v = [x for x in v.split('\x1f') if x]
    return set(v or [])


def keep(title: str, chosen) -> bool:
    """이 영상을 수집할까.

    chosen 이 비면 전부 통과시킨다 — '아직 안 골랐다'와 '아무것도 원하지 않는다'는
    다르고, 후자를 기본값으로 두면 구독해도 아무것도 안 오는 채널이 생긴다.
    """
    if not chosen:
        return True
    return program(title) in chosen


def detect_new(seen, titles) -> list:
    """설정 당시 **보였던 코너 전체**(seen)에 없던 코너가 나타났는지.

    ⚠️ 여기에 '고른 코너(chosen)'를 넘기면 안 된다. 안 고른 코너가 전부 '새 코너'로
       잡혀서 매주 같은 알림이 온다(테스트에서 실제로 그렇게 나왔다).
       고른 것과 본 것은 다르다 — 그래서 저장할 때 둘 다 남긴다.

    반환: [(새 코너명, 건수)] — 비면 변화 없음.
    """
    if not seen:
        return []
    now = Counter(program(t) for t in titles if t)
    return [(k, v) for k, v in now.most_common() if k not in seen and k != NO_TAG]


def seen_of(sub: dict) -> set:
    """설정 당시 보였던 코너 전체. 없으면 고른 것으로 대신한다(옛 레코드 호환)."""
    v = (sub or {}).get('corners_seen')
    if isinstance(v, str):
        v = [x for x in v.split(chr(31)) if x]
    return set(v or []) or selected_of(sub)


def format_list(choices, chosen=None) -> str:
    """번호 매긴 코너 목록 — 텍스트 UI 와 체크박스 UI 양쪽에서 쓴다."""
    chosen = chosen or set()
    lines = []
    for i, (name, n) in enumerate(choices, 1):
        mark = '☑️' if (not chosen or name in chosen) else '☐'
        lines.append(f'{mark} <b>{i}</b>. {name} <i>({n}건)</i>')
    return '\n'.join(lines)


# ── 저장 (로컬 JSON) ─────────────────────────────────────────────────
# ⚠️ Supabase 가 아니라 파일에 둔다. subscriptions 테이블에 열을 추가하려면 사람이
#    대시보드에서 DDL 을 쳐야 하는데, 그 한 단계 때문에 기능 전체가 막힌다.
#    ir_state.json·deck_quota.json 과 같은 방식이고, run.yml 이 커밋해 보존한다.
#    ⚠️ 그래서 **run.yml 의 커밋 목록에 corner_prefs.json 을 넣어야 한다** —
#       안 넣으면 매 실행이 새 컨테이너라 설정이 그때그때 사라진다.
import json  # noqa: E402

PREFS_PATH = ROOT / 'corner_prefs.json'


def _key(chat_id, channel_id) -> str:
    return f'{chat_id}:{channel_id}'


def load_prefs() -> dict:
    if PREFS_PATH.exists():
        try:
            return json.loads(PREFS_PATH.read_text(encoding='utf-8')) or {}
        except Exception:
            pass
    return {}


def save_prefs(p: dict):
    PREFS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding='utf-8')


def get(chat_id, channel_id) -> dict:
    """{'chosen': set, 'seen': set}. 설정한 적 없으면 둘 다 빈 집합(=전부)."""
    e = load_prefs().get(_key(chat_id, channel_id)) or {}
    return {'chosen': set(e.get('chosen') or []), 'seen': set(e.get('seen') or [])}


def put(chat_id, channel_id, chosen, seen):
    """고른 것과 **그때 보였던 것 전체**를 같이 남긴다(detect_new 의 기준선)."""
    p = load_prefs()
    p[_key(chat_id, channel_id)] = {'chosen': sorted(chosen), 'seen': sorted(seen),
                                    'at': __import__('datetime').datetime.now(
                                        __import__('datetime').timezone.utc).strftime('%Y-%m-%d')}
    save_prefs(p)


def union_for_channel(channel_id: str, subscriber_chat_ids) -> set:
    """이 채널을 구독한 사람들이 원하는 코너의 **합집합**.

    분석은 채널당 1회만 하고 여러 사용자에게 뿌린다(engine.refresh/fanout).
    그래서 수집 단계에서 한 사람 기준으로 거르면 다른 사람이 원한 코너가 사라진다.
    한 명이라도 '전부'(미설정)면 합집합도 '전부'다.
    """
    out = set()
    for chat in subscriber_chat_ids:
        c = get(chat, channel_id)['chosen']
        if not c:
            return set()          # 미설정 = 전부 — 합집합은 더 좁아질 수 없다
        out |= c
    return out
