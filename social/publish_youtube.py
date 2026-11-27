"""유튜브 쇼츠 — 2026-11-28. 세로 영상(≤60초)은 업로드만 하면 쇼츠로 분류된다. 제목에 #Shorts.
env(GitHub Secrets): YT_CLIENT_ID · YT_CLIENT_SECRET · YT_REFRESH_TOKEN (scope youtube.upload)
  발급: docs/youtube_setup.md. 할당량 = 하루 약 6건(업로드 1건 1,600 단위 / 기본 10,000).
texts = [제목, 설명], images[0] = 공개 mp4 URL."""
import os
import requests

from .storage import public_url


def _token() -> str:
    cid, sec, rt = (os.environ.get(k, '') for k in ('YT_CLIENT_ID', 'YT_CLIENT_SECRET', 'YT_REFRESH_TOKEN'))
    if not (cid and sec and rt):
        raise RuntimeError('유튜브 OAuth 미설정 — YT_CLIENT_ID/YT_CLIENT_SECRET/YT_REFRESH_TOKEN (docs/youtube_setup.md)')
    j = requests.post('https://oauth2.googleapis.com/token', data=dict(client_id=cid, client_secret=sec, refresh_token=rt,
                                                                      grant_type='refresh_token'), timeout=30).json()
    if 'access_token' not in j:
        raise RuntimeError(f'유튜브 토큰 갱신 실패: {j}')
    return j['access_token']


def publish(texts: list, images: list) -> str:
    if not images:
        raise RuntimeError('youtube: 영상 없음')
    tok = _token()
    video = requests.get(public_url(images[0]), timeout=120).content
    title = (texts[0] if texts else '시황')[:95]
    if '#Shorts' not in title:
        title = (title[:86] + ' #Shorts')
    meta = {'snippet': {'title': title, 'description': (texts[1] if len(texts) > 1 else '')[:4800],
                        'categoryId': '25', 'defaultLanguage': 'ko'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}}
    init = requests.post('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                         headers={'Authorization': f'Bearer {tok}', 'X-Upload-Content-Type': 'video/mp4',
                                  'X-Upload-Content-Length': str(len(video))}, json=meta, timeout=60)
    if init.status_code >= 400 or 'Location' not in init.headers:
        raise RuntimeError(f'youtube 업로드 시작 실패 {init.status_code}: {init.text[:300]}')
    up = requests.put(init.headers['Location'], data=video, headers={'Content-Type': 'video/mp4'}, timeout=600)
    j = up.json()
    if 'id' not in j:
        raise RuntimeError(f'youtube 업로드 실패: {str(j)[:300]}')
    return j['id']
