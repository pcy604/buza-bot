"""미디어 공개 URL — Threads·Instagram API는 로컬 파일을 못 받고 **공개 URL**만 받는다.
Supabase Storage 공개 버킷 `social`에 올리고 URL을 돌려준다. (sql/social_posts.sql 이 버킷을 만든다)

2026-11-22: content-type 이 'image/png' 로 박혀 있었다. 숏츠·릴스로 mp4 를 올리면
그대로 image/png 로 올라가 플랫폼이 거부한다. 확장자에서 정하도록 바꿨다."""
import hashlib
from pathlib import Path
from db import _sb

BUCKET = 'social'

# 플랫폼이 받는 형식만 둔다. 모르는 확장자는 올리지 않는다(잘못된 타입으로 올려 조용히 거부당하는 것보다 낫다).
_CT = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
       '.webp': 'image/webp', '.mp4': 'video/mp4', '.mov': 'video/quicktime'}


def content_type(path) -> str:
    ext = Path(path).suffix.lower()
    if ext not in _CT:
        raise RuntimeError(f'지원하지 않는 형식: {ext} ({path}) — social/storage._CT 에 추가할 것')
    return _CT[ext]


def public_url(local_path: str) -> str:
    p = Path(local_path)
    key = f"{hashlib.md5(p.read_bytes()).hexdigest()[:12]}_{p.name}"
    st = _sb.storage.from_(BUCKET)
    try:
        st.upload(key, p.read_bytes(), {'content-type': content_type(p), 'upsert': 'true'})
    except Exception as e:                     # 이미 있으면 통과
        if 'exists' not in str(e).lower() and 'duplicate' not in str(e).lower():
            raise
    return st.get_public_url(key)
