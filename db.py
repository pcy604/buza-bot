"""Supabase 데이터 계층."""
from supabase import create_client
import config

_sb = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


# ── 폴링 오프셋 ──────────────────────────────────────────────────────
def get_offset() -> int:
    r = _sb.table('bot_state').select('tg_offset').eq('id', 1).execute()
    return r.data[0]['tg_offset'] if r.data else 0


def set_offset(o: int):
    _sb.table('bot_state').update({'tg_offset': o}).eq('id', 1).execute()


# ── 유저 ────────────────────────────────────────────────────────────
def upsert_user(chat_id: int, username: str = None):
    row = {'chat_id': chat_id}
    if username:
        row['username'] = username
    _sb.table('users').upsert(row).execute()


def get_user(chat_id: int):
    r = _sb.table('users').select('*').eq('chat_id', chat_id).execute()
    return r.data[0] if r.data else None


def all_users():
    return _sb.table('users').select('*').execute().data


# ── 구독 ────────────────────────────────────────────────────────────
def add_subscription(chat_id: int, channel_id: str, channel_name: str):
    upsert_user(chat_id)
    _sb.table('subscriptions').upsert(
        {'chat_id': chat_id, 'channel_id': channel_id, 'channel_name': channel_name},
        on_conflict='chat_id,channel_id').execute()
    _sb.table('channels').upsert({'channel_id': channel_id, 'name': channel_name}).execute()


def list_subscriptions(chat_id: int):
    return _sb.table('subscriptions').select('*').eq('chat_id', chat_id).execute().data


def remove_subscription(chat_id: int, channel_id: str):
    _sb.table('subscriptions').delete().eq('chat_id', chat_id).eq('channel_id', channel_id).execute()


def subscribers_of(channel_id: str):
    r = _sb.table('subscriptions').select('chat_id').eq('channel_id', channel_id).execute()
    return [x['chat_id'] for x in r.data]


# ── 채널 마스터 ──────────────────────────────────────────────────────
def all_channels():
    return _sb.table('channels').select('*').execute().data


# ── 분석 캐시 ────────────────────────────────────────────────────────
def get_analysis(video_id: str):
    r = _sb.table('analyses').select('*').eq('video_id', video_id).execute()
    return r.data[0] if r.data else None


def save_analysis(rec: dict):
    _sb.table('analyses').upsert(rec).execute()


def unfinished_analyses():
    """내용이 안 채워진 분석들 — 재시도 대상. attempts 필터는 호출부에서 한다.

    refresh() 는 채널당 최근 MAX_PER_CHANNEL(=2)개만 보므로, 한 번 실패한 영상은
    6시간 뒤 다음 실행에서 이미 top-2 밖으로 밀려나 **재시도 대상에서 사라진다.**
    RETRY_MAX=4 인데 실패 67건 중 58건(87%)이 attempts=1 에 멈춰 있던 이유가 이것이다.
    최신 목록과 별개로 여기서 끌어와야 재시도가 실제로 일어난다.
    """
    return _sb.table('analyses').select('*').execute().data or []


def analyses_for_channel(channel_id: str):
    return _sb.table('analyses').select('*').eq('channel_id', channel_id).execute().data


# ── 발송 기록 ────────────────────────────────────────────────────────
def already_delivered(chat_id: int, video_id: str) -> bool:
    r = _sb.table('deliveries').select('video_id').eq('chat_id', chat_id).eq('video_id', video_id).execute()
    return bool(r.data)


def record_delivery(chat_id: int, video_id: str):
    _sb.table('deliveries').upsert({'chat_id': chat_id, 'video_id': video_id}).execute()
