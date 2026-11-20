"""Instagram API with Instagram Login — 페이스북 페이지 없이 동작(2024~). 단일 이미지·캐러셀.
env: IG_USER_ID, IG_TOKEN (장기 토큰 60일)   https://developers.facebook.com/docs/instagram-platform"""
import time, requests
import config
from .storage import public_url

API = 'https://graph.instagram.com/v21.0'

def _post(path, **data):
    data['access_token'] = config.IG_TOKEN
    r = requests.post(f'{API}/{path}', data=data, timeout=60)
    j = r.json()
    if r.status_code >= 400 or 'error' in j:
        raise RuntimeError(f'instagram {path}: {j}')
    return j

def publish(texts: list, images: list) -> str:
    if not images:
        raise RuntimeError('instagram: 이미지 없는 게시물은 불가')
    uid, cap = config.IG_USER_ID, texts[0]
    urls = [public_url(p) for p in images[:10]]
    if len(urls) == 1:
        cid = _post(f'{uid}/media', image_url=urls[0], caption=cap)['id']
    else:
        kids = [_post(f'{uid}/media', image_url=u, is_carousel_item='true')['id'] for u in urls]
        cid = _post(f'{uid}/media', media_type='CAROUSEL', children=','.join(kids), caption=cap)['id']
    for _ in range(10):                                # 컨테이너 FINISHED 대기
        s = requests.get(f'{API}/{cid}', params={'fields': 'status_code', 'access_token': config.IG_TOKEN}, timeout=30).json()
        if s.get('status_code') == 'FINISHED':
            break
        time.sleep(5)
    return _post(f'{uid}/media_publish', creation_id=cid)['id']
