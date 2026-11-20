"""Threads API — 단일/캐러셀 글 + 답글 체인.  https://developers.facebook.com/docs/threads
env: THREADS_USER_ID, THREADS_TOKEN (장기 토큰 60일, refresh 필요)"""
import time, requests
import config
from .storage import public_url

API = 'https://graph.threads.net/v1.0'

def _post(path, **data):
    data['access_token'] = config.THREADS_TOKEN
    r = requests.post(f'{API}/{path}', data=data, timeout=60)
    j = r.json()
    if r.status_code >= 400 or 'error' in j:
        raise RuntimeError(f'threads {path}: {j}')
    return j

def _container(text, image_urls, reply_to=None):
    uid = config.THREADS_USER_ID
    base = {'text': text}
    if reply_to:
        base['reply_to_id'] = reply_to
    if not image_urls:
        return _post(f'{uid}/threads', media_type='TEXT', **base)['id']
    if len(image_urls) == 1:
        return _post(f'{uid}/threads', media_type='IMAGE', image_url=image_urls[0], **base)['id']
    kids = [_post(f'{uid}/threads', media_type='IMAGE', image_url=u, is_carousel_item='true')['id'] for u in image_urls]
    return _post(f'{uid}/threads', media_type='CAROUSEL', children=','.join(kids), **base)['id']

def publish(texts: list, images: list) -> str:
    urls = [public_url(p) for p in images]
    root = prev = None
    for i, t in enumerate(texts):
        cid = _container(t, urls if i == 0 else [], reply_to=prev)
        time.sleep(3)                                  # 컨테이너 처리 대기(문서 권장)
        mid = _post(f'{config.THREADS_USER_ID}/threads_publish', creation_id=cid)['id']
        root = root or mid
        prev = mid
    return root
