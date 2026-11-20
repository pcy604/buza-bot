"""X API v2 — 포스트 + 답글 체인, 이미지는 v1.1 media/upload. Free 티어(쓰기 전용, 월 1,500).
env: X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET  (앱 권한 Read and Write 필수)"""
import requests
from requests_oauthlib import OAuth1
import config

def _auth():
    return OAuth1(config.X_API_KEY, config.X_API_SECRET, config.X_ACCESS_TOKEN, config.X_ACCESS_SECRET)

def _media(path) -> str:
    with open(path, 'rb') as f:
        r = requests.post('https://upload.twitter.com/1.1/media/upload.json', auth=_auth(),
                          files={'media': f}, timeout=120)
    r.raise_for_status()
    return r.json()['media_id_string']

def publish(texts: list, images: list) -> str:
    media_ids = [_media(p) for p in images[:4]]
    root = prev = None
    for i, t in enumerate(texts):
        body = {'text': t}
        if i == 0 and media_ids:
            body['media'] = {'media_ids': media_ids}
        if prev:
            body['reply'] = {'in_reply_to_tweet_id': prev}
        r = requests.post('https://api.x.com/2/tweets', auth=_auth(), json=body, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f'x tweets: {r.status_code} {r.text}')
        prev = r.json()['data']['id']
        root = root or prev
    return root
