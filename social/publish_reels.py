"""인스타 릴스(세로 영상) — 2026-11-28 차니: 인스타는 피드(4:5 잘림) 대신 쇼츠만.
env: IG_USER_ID, IG_TOKEN. images[0] = 공개 mp4 URL(초안 때 Storage 에 올린 것)."""
import time, requests
import config
from .storage import public_url

API = 'https://graph.instagram.com/v21.0'


def publish(texts: list, images: list) -> str:
    if not images:
        raise RuntimeError('reels: 영상 없음')
    tok, uid = config.IG_TOKEN, config.IG_USER_ID
    r = requests.post(f'{API}/{uid}/media', data=dict(media_type='REELS', video_url=public_url(images[0]),
                                                      caption=texts[0][:2200], share_to_feed='true', access_token=tok), timeout=60).json()
    if 'id' not in r:
        raise RuntimeError(f'reels 컨테이너: {r}')
    cid = r['id']
    for _ in range(40):                                   # 영상 처리 — 최대 ~6분
        s = requests.get(f'{API}/{cid}', params={'fields': 'status_code', 'access_token': tok}, timeout=30).json()
        if s.get('status_code') == 'FINISHED':
            break
        if s.get('status_code') == 'ERROR':
            raise RuntimeError(f'reels 처리 실패: {s}')
        time.sleep(9)
    j = requests.post(f'{API}/{uid}/media_publish', data=dict(creation_id=cid, access_token=tok), timeout=60).json()
    if 'id' not in j:
        raise RuntimeError(f'reels 게시: {j}')
    return j['id']
