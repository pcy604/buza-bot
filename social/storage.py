"""이미지 공개 URL — Threads·Instagram API는 로컬 파일을 못 받고 **공개 URL**만 받는다.
Supabase Storage 공개 버킷 `social`에 올리고 URL을 돌려준다. (sql/social_posts.sql 이 버킷을 만든다)"""
import hashlib
from pathlib import Path
from db import _sb

BUCKET = 'social'

def public_url(local_path: str) -> str:
    p = Path(local_path)
    key = f"{hashlib.md5(p.read_bytes()).hexdigest()[:12]}_{p.name}"
    st = _sb.storage.from_(BUCKET)
    try:
        st.upload(key, p.read_bytes(), {'content-type': 'image/png', 'upsert': 'true'})
    except Exception as e:                     # 이미 있으면 통과
        if 'exists' not in str(e).lower() and 'duplicate' not in str(e).lower():
            raise
    return st.get_public_url(key)
