"""토큰 점검·갱신 — 발행 직전에 돌려서 '키가 살아 있는가'를 게시 없이 확인한다.
Threads·Instagram 장기 토큰은 60일 만료, 만료 24시간 전부터 refresh 가능(갱신하면 다시 60일)."""
import requests
import config

def check_threads() -> dict:
    if not config.THREADS_TOKEN:
        return {'ok': False, 'why': 'THREADS_TOKEN 비어 있음'}
    r = requests.get(f'https://graph.threads.net/v1.0/me', params={'fields': 'id,username', 'access_token': config.THREADS_TOKEN}, timeout=30)
    j = r.json()
    if r.status_code == 200 and not config.THREADS_USER_ID:          # ID 는 토큰으로 알아낼 수 있다 — .env 에 적을 값을 알려준다
        return {'ok': False, 'why': f"THREADS_USER_ID 비어 있음 → .env 에 THREADS_USER_ID={j.get('id')} 추가 (username={j.get('username')})"}
    return {'ok': r.status_code == 200 and j.get('id') == str(config.THREADS_USER_ID), 'resp': j}

def check_instagram() -> dict:
    if not config.IG_TOKEN:
        return {'ok': False, 'why': 'IG_TOKEN 비어 있음'}
    r = requests.get(f'https://graph.instagram.com/v21.0/me', params={'fields': 'id,username,account_type', 'access_token': config.IG_TOKEN}, timeout=30)
    j = r.json()
    if r.status_code == 200 and not config.IG_USER_ID:
        return {'ok': False, 'why': f"IG_USER_ID 비어 있음 → .env 에 IG_USER_ID={j.get('id')} 추가 (username={j.get('username')})"}
    return {'ok': r.status_code == 200 and j.get('id') == str(config.IG_USER_ID), 'resp': j}

def refresh_threads() -> dict:
    r = requests.get('https://graph.threads.net/refresh_access_token',
                     params={'grant_type': 'th_refresh_token', 'access_token': config.THREADS_TOKEN}, timeout=30)
    return r.json()          # {'access_token':..., 'token_type':'bearer', 'expires_in': 5183944}

def refresh_instagram() -> dict:
    r = requests.get('https://graph.instagram.com/refresh_access_token',
                     params={'grant_type': 'ig_refresh_token', 'access_token': config.IG_TOKEN}, timeout=30)
    return r.json()

def check_all() -> dict:
    return {'threads': check_threads(), 'instagram': check_instagram()}
