# -*- coding: utf-8 -*-
"""인물 추적 — 특정 인물이 **여러 채널에 출연한 영상**을 찾아 요약 대상에 올린다.

박세익 대표처럼 한 사람이 체슬리TV(본진) 말고도 김작가TV·머니인사이드·한국경제TV 등
여러 곳에 나오는데, 채널 구독만으로는 본진 것만 받는다. 사람을 기준으로 훑는다.

## 어떻게 찾나 — 유튜브 검색 결과 파싱 (API 키 불필요)

유튜브는 **검색 RSS 를 제공하지 않는다.** 채널 RSS(feeds/videos.xml)는 channel_id
단위뿐이다. 그래서 검색 결과 페이지의 `ytInitialData` 를 읽는다.
Data API(search.list)는 키가 있어야 하고 호출당 100유닛(하루 100회)이라
키가 없는 지금 상태에서는 선택지가 아니다.

⚠️ 이 방식은 **유튜브가 페이지 구조를 바꾸면 조용히 0건이 된다.** 그래서
   "결과 0건"을 정상으로 넘기지 않고 호출부가 로그를 남긴다(find 가 빈 리스트와
   파싱 실패를 구분해 돌려준다).

## 본진 제외

이미 구독 중인 채널의 영상은 **채널 경로가 이미 처리**한다(코너 선택까지 적용된다).
여기서 또 집으면 코너 선택을 우회해 들어오고 쿼터를 두 번 쓴다.
그래서 구독 채널은 건너뛴다(2026-10-03 결정).

## 동명이인

검색이 느슨해서 '박세익'으로 찾으면 **'박세환'** 이 섞여 들어온다(실측).
제목·채널명에 이름이 **그대로** 있는지 다시 확인한다.
"""
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PEOPLE_PATH = ROOT / 'people_state.json'
SEARCH_URL = 'https://www.youtube.com/results?search_query={q}&sp=CAI%253D'   # CAI=업로드순


# ── 상태 ─────────────────────────────────────────────────────────────
def load() -> dict:
    if PEOPLE_PATH.exists():
        try:
            return json.loads(PEOPLE_PATH.read_text(encoding='utf-8')) or {}
        except Exception:
            pass
    return {}


def save(st: dict):
    PEOPLE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding='utf-8')


def _entries(chat_id) -> list:
    """[{'name':…, 'queries':[…]}]. 옛 형식({'names': [...]})도 읽는다."""
    e = load().get(str(chat_id)) or {}
    out = list(e.get('people') or [])
    for n in (e.get('names') or []):          # 옛 형식 호환
        if not any(x.get('name') == n for x in out):
            out.append({'name': n, 'queries': [n]})
    return out


def watches_of(chat_id) -> list:
    return [e['name'] for e in _entries(chat_id)]


def queries_of(chat_id, name: str) -> list:
    for e in _entries(chat_id):
        if e['name'] == name:
            return list(e.get('queries') or [name])
    return [name]


def add(chat_id, name: str, extra: str = '') -> bool:
    """인물 등록. extra(소속 등)를 주면 **검색어를 하나 더** 만든다.

    ⚠️ extra 는 **판정 조건이 아니다.** 실측(2026-10-03): 타채널은 소속을 생략하고
       '(박세익 대표)' 로만 적어서, 회사명을 AND 로 요구하면 19건 중 8건이 잘렸고
       **잘린 게 전부 진짜 본인**이었다 — 타채널 출연이 이 기능의 존재 이유인데
       정작 그걸 잘라내는 꼴이다.
       반대로 **검색어로 쓰면 이득**이다: '박세익' 19건 vs '체슬리 박세익' 18건인데
       겹치는 건 10건뿐이고 **새로 8건**이 나왔다. 유튜브 검색은 조합을 바꾸면
       좁혀지는 게 아니라 **다른 그물**이 된다. 그래서 합집합으로 모은다.
       검색은 HTML 1회라 공짜고, 요약은 PERSON_PER_RUN 이 따로 막는다.
    """
    st = load()
    e = st.setdefault(str(chat_id), {})
    ppl = e.setdefault('people', [])
    for n in (e.pop('names', None) or []):     # 옛 형식 흡수
        if not any(x.get('name') == n for x in ppl):
            ppl.append({'name': n, 'queries': [n]})
    cur = next((x for x in ppl if x.get('name') == name), None)
    qs = [name] + ([f'{extra} {name}'] if extra else [])
    if cur:
        added = [q for q in qs if q not in cur['queries']]
        if not added:
            return False
        cur['queries'] += added               # 같은 인물에 검색어만 추가
    else:
        ppl.append({'name': name, 'queries': qs})
    save(st)
    return True


def remove(chat_id, name: str) -> bool:
    """추적 해제. 없는 이름이면 False — 호출부가 '없다'고 말할 수 있어야 한다."""
    st = load()
    e = st.get(str(chat_id)) or {}
    ppl = e.get('people') or []
    old_names = e.get('names') or []
    hit = any(x.get('name') == name for x in ppl) or name in old_names
    if not hit:
        return False
    e['people'] = [x for x in ppl if x.get('name') != name]
    e['names'] = [n for n in old_names if n != name]
    st[str(chat_id)] = e
    save(st)
    return True


def find_many(queries, ua: str):
    """여러 검색어 결과를 **합집합**으로 모은다. (영상목록, 하나라도 파싱 성공했나)"""
    seen, out, any_ok = set(), [], False
    for q in queries:
        found, ok = find(q, ua)
        any_ok = any_ok or ok
        for v in found:
            if v['video_id'] not in seen:
                seen.add(v['video_id'])
                out.append(v)
    return out, any_ok


# ── 검색 ─────────────────────────────────────────────────────────────
def _walk(o, key):
    if isinstance(o, dict):
        if key in o:
            yield o[key]
        for v in o.values():
            yield from _walk(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, key)


_DUR = re.compile(r'^(?:(\d+):)?(\d+):(\d+)$')


def _seconds(txt: str):
    m = _DUR.match((txt or '').strip())
    if not m:
        return None
    h, mi, s = m.group(1), m.group(2), m.group(3)
    return int(h or 0) * 3600 + int(mi) * 60 + int(s)


def find(name: str, ua: str):
    """(영상목록, 파싱성공여부). 파싱 실패와 '결과 0건'을 구분해 돌려준다.

    구분하는 이유: 유튜브가 페이지 구조를 바꾸면 둘 다 0건으로 보이는데,
    전자는 고쳐야 하는 고장이고 후자는 정상이다. 같이 묶으면 고장이 조용히 묻힌다.
    """
    import requests
    url = SEARCH_URL.format(q=urllib.parse.quote(name))
    try:
        r = requests.get(url, headers={'User-Agent': ua, 'Accept-Language': 'ko-KR,ko'},
                         cookies={'SOCS': 'CAI'}, timeout=20)
    except Exception as e:
        print(f'[인물검색 실패] {name}: {type(e).__name__}')
        return [], False
    m = (re.search(r'var ytInitialData\s*=\s*(\{.*?\});\s*</script>', r.text, re.S)
         or re.search(r'ytInitialData"?\]?\s*=\s*(\{.*?\});', r.text, re.S))
    if not m:
        print(f'[인물검색] {name}: ytInitialData 없음 — 유튜브 페이지 구조가 바뀌었을 수 있음')
        return [], False
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        print(f'[인물검색] {name}: JSON 파싱 실패 {type(e).__name__}')
        return [], False
    out, seen = [], set()
    for vr in _walk(data, 'videoRenderer'):
        try:
            vid = vr['videoId']
            if vid in seen:
                continue
            seen.add(vid)
            title = ''.join(x.get('text', '') for x in vr['title']['runs'])
            ch = vr.get('ownerText') or vr.get('longBylineText') or {}
            chan = ''.join(x.get('text', '') for x in ch.get('runs', []))
            out.append({'video_id': vid, 'title': title, 'channel': chan,
                        'url': f'https://www.youtube.com/watch?v={vid}',
                        'published': '',          # 검색은 '3일 전' 식이라 절대시각이 없다
                        'published_text': (vr.get('publishedTimeText') or {}).get('simpleText', ''),
                        'duration_sec': _seconds((vr.get('lengthText') or {}).get('simpleText', ''))})
        except Exception:
            continue
    return out, True


def is_really(name: str, v: dict) -> bool:
    """동명이인·오탐 거르기 — 제목이나 채널명에 이름이 **그대로** 있어야 한다.

    실측(2026-10-03): '박세익' 검색에 **'박세환' 박사** 영상이 2건 섞여 들어왔다.
    유튜브 검색이 느슨해서 비슷한 이름을 같이 준다. 이걸 안 거르면 남의 발언이
    그 사람 것으로 요약돼 나간다.
    """
    hay = f"{v.get('title', '')} {v.get('channel', '')}"
    return name in hay
