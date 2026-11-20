"""텔레그램 ↔ 대시보드 계정 연결 (2026-11-12, 백로그 9).

흐름: 대시보드(로그인) '봇 연결' → 1회용 코드 + t.me/<봇>?start=link_CODE 링크
      → 사용자가 누르면 봇이 '/start link_CODE' 를 받아 account_links.chat_id 를 채운다.
      대시보드 '보유 종목을 봇 감시에 추가' → account_links.watch_sync 에 종목 목록 → 크론이 감시 등록 후 비움.
표: account_links(uid=sha256(email), code, code_expires, chat_id, linked_at, watch_sync) — sql/account_links.sql.
이메일 원문은 이 저장소·표 어디에도 남지 않는다(uid 는 대시보드 user_store 와 같은 해시).
"""
import re
from datetime import datetime, timezone

CODE_RE = re.compile(r'^[A-Z0-9]{6,10}$')


def _tbl():
    import db
    return db._sb.table('account_links')


def link(chat, code: str) -> str:
    """'ok' | 'bad' | 'expired' | 'error'"""
    code = (code or '').strip().upper()
    if not CODE_RE.match(code):
        return 'bad'
    try:
        rows = _tbl().select('uid,code_expires').eq('code', code).execute().data or []
        if not rows:
            return 'bad'
        exp = rows[0].get('code_expires')
        if exp and datetime.fromisoformat(str(exp).replace('Z', '+00:00')) < datetime.now(timezone.utc):
            return 'expired'
        now = datetime.now(timezone.utc).isoformat()
        _tbl().update({'chat_id': int(chat), 'linked_at': now, 'code': None, 'code_expires': None,
                       'updated_at': now}).eq('uid', rows[0]['uid']).execute()
        return 'ok'
    except Exception as e:
        print(f'[계정 연결 실패] {type(e).__name__}: {str(e)[:120]}')
        return 'error'


def pending_syncs() -> list:
    try:
        return [r for r in (_tbl().select('uid,chat_id,watch_sync').not_.is_('watch_sync', 'null')
                            .execute().data or []) if r.get('chat_id')]
    except Exception as e:
        print(f'[감시 동기화 조회 실패] {type(e).__name__}: {str(e)[:120]}')
        return []


def clear_sync(uid: str):
    _tbl().update({'watch_sync': None, 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('uid', uid).execute()


def run_sync(add_one, send) -> int:
    """크론: 대시보드가 보낸 종목을 감시 등록. add_one(chat, sym) → 등록된 심볼 또는 None."""
    n = 0
    for r in pending_syncs():
        chat, syms = r['chat_id'], [str(s) for s in (r.get('watch_sync') or [])][:30]
        ok = [x for x in (add_one(chat, s) for s in syms) if x]
        try:
            clear_sync(r['uid'])
        except Exception:
            continue
        if ok:
            send(chat, f"🔗 대시보드 보유 종목 {len(ok)}개를 감시에 추가했어요: {', '.join(ok)}\n목록: /watchlist")
            n += 1
    return n
