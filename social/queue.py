"""발행 큐 — Supabase social_posts. 상태: draft → approved → published | failed"""
from datetime import datetime, timezone
from db import _sb

T = 'social_posts'

def enqueue(slug: str, post) -> int:
    r = _sb.table(T).insert({'content_slug': slug, 'platform': post.platform,
                             'payload': post.dump(), 'status': 'draft'}).execute()
    return r.data[0]['id']

def get(pid: int):
    r = _sb.table(T).select('*').eq('id', pid).execute()
    return r.data[0] if r.data else None

def list_by(status: str = None, slug: str = None):
    q = _sb.table(T).select('*')
    if status: q = q.eq('status', status)
    if slug:   q = q.eq('content_slug', slug)
    return q.order('id').execute().data or []

def set_status(pid: int, status: str, external_id: str = None, error: str = None):
    row = {'status': status}
    if external_id: row['external_id'] = external_id
    if error: row['error'] = error[:2000]
    if status == 'published': row['published_at'] = datetime.now(timezone.utc).isoformat()
    _sb.table(T).update(row).eq('id', pid).execute()
