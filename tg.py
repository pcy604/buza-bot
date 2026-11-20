"""텔레그램 Bot API 래퍼."""
import json
import requests
import config

API = f'https://api.telegram.org/bot{config.TELEGRAM_TOKEN}'


def get_updates(offset: int, timeout: int = 0):
    try:
        r = requests.get(f'{API}/getUpdates',
                         params={'offset': offset + 1, 'timeout': timeout,
                                 'allowed_updates': json.dumps(['message'])}, timeout=timeout + 30)
        return r.json().get('result', [])
    except Exception as e:
        print(f'[getUpdates 오류] {e}')
        return []


# 마지막 발송 실패(2026-10-21). 봇을 차단한 사용자(403)·없는 대화(400 chat not found)는
# 몇 번을 다시 보내도 실패한다 — 그걸 '일시 실패'로 다루면 공시 기준선이 영영 안 넘어가
# 다른 감시자들이 같은 공시를 매 실행마다 다시 받는다. 호출부는 permanent_fail() 로 구분한다.
LAST_ERR = {}


def _note(j: dict):
    LAST_ERR.clear()
    if not j.get('ok'):
        LAST_ERR.update(code=j.get('error_code'), desc=str(j.get('description') or ''))


def permanent_fail() -> bool:
    """직전 발송 실패가 다시 보내도 소용없는 종류인가(차단·탈퇴·없는 대화)."""
    d = LAST_ERR.get('desc', '').lower()
    return LAST_ERR.get('code') == 403 or (LAST_ERR.get('code') == 400 and
                                           ('chat not found' in d or 'deactivated' in d))


def send_message(chat_id, text: str, reply_markup: dict = None) -> bool:
    try:
        body = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
        if reply_markup:
            body['reply_markup'] = reply_markup
        r = requests.post(f'{API}/sendMessage', json=body, timeout=15)
        _note(r.json())
        if not r.json().get('ok'):
            print(f'[send 실패] {chat_id}: {r.json().get("description")}')
        return r.json().get('ok', False)
    except Exception as e:
        LAST_ERR.clear()
        print(f'[send 오류] {e}')
        return False


def send_photo(chat_id, png_path: str, caption: str = '', reply_markup: dict = None) -> bool:
    try:
        data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'}
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup, ensure_ascii=False)
        with open(png_path, 'rb') as f:
            r = requests.post(f'{API}/sendPhoto', data=data, files={'photo': f}, timeout=60)
        _note(r.json())
        if not r.json().get('ok'):
            print(f'[photo 실패] {chat_id}: {r.json().get("description")}')
        return r.json().get('ok', False)
    except Exception as e:
        LAST_ERR.clear()
        print(f'[photo 오류] {e}')
        return False


def send_media_group_ids(chat_id, file_ids: list, caption: str = '') -> bool:
    """이미 텔레그램에 올라간 사진들을 file_id로 다시 보낸다.

    파일 업로드가 없어서 즉시 끝나고, 봇이 도는 GitHub Actions 러너에 PNG가
    없어도 된다(`decks/out`은 .gitignore라 러너엔 애초에 없다). 12장 포토카드를
    로컬에서 한 번 발행해 두면 그 뒤로는 이 경로로 몇 번이든 다시 보낼 수 있다."""
    if not file_ids:
        return False
    try:
        media = []
        for i, fid in enumerate(file_ids):
            item = {'type': 'photo', 'media': fid}
            if i == 0 and caption:
                item['caption'] = caption
                item['parse_mode'] = 'HTML'
            media.append(item)
        r = requests.post(f'{API}/sendMediaGroup',
                          json={'chat_id': chat_id, 'media': media}, timeout=60)
        ok = r.json().get('ok', False)
        if not ok:
            print(f'[미디어그룹(id) 실패] {chat_id}: {r.json().get("description")}')
        return ok
    except Exception as e:
        print(f'[미디어그룹(id) 오류] {e}')
        return False


def send_media_group(chat_id, png_paths: list, caption: str = '') -> bool:
    """여러 장을 한 앨범(인스타 캐러셀 그대로 옮기기 좋은 형태)으로 발송.
    캡션은 텔레그램 사양상 첫 장에만 붙음. 2~10장 지원."""
    if not png_paths:
        return False
    media, files = [], {}
    try:
        for i, path in enumerate(png_paths):
            key = f'photo{i}'
            item = {'type': 'photo', 'media': f'attach://{key}'}
            if i == 0 and caption:
                item['caption'] = caption
                item['parse_mode'] = 'HTML'
            media.append(item)
            files[key] = open(path, 'rb')
        r = requests.post(f'{API}/sendMediaGroup',
                          data={'chat_id': chat_id, 'media': json.dumps(media)},
                          files=files, timeout=120)
        res = r.json()
        ok = res.get('ok', False)
        if not ok:
            print(f'[미디어그룹 실패] {chat_id}: {res.get("description")}')
            return False
        # 성공하면 업로드된 사진들의 file_id를 돌려준다. 같은 사진을 다시 보낼 때
        # 파일 없이 이 id만으로 보낼 수 있어서(send_media_group_ids), 봇이 러너에서
        # PNG를 갖고 있지 않아도 재전송이 된다. 리스트는 비어있지 않으면 참이라
        # 기존 호출부의 불리언 검사와도 호환된다.
        ids = []
        for m in res.get('result', []):
            photos = m.get('photo') or []
            if photos:
                ids.append(photos[-1]['file_id'])      # 마지막이 최대 해상도
        return ids or True
    except Exception as e:
        print(f'[미디어그룹 오류] {e}')
        return False
    finally:
        for f in files.values():
            f.close()


# ── 봇 프로필: 메뉴(☰) 명령 목록 · 빈 대화창 소개 · 공유 카드 소개 (2026-10-21) ──
# 사용자가 /help 를 몰라도 입력창 왼쪽 메뉴 버튼과 첫 화면에서 쓰는 법이 보이게 한다.
# 언어별로 따로 건다 — 텔레그램 앱 언어가 ko 면 한국어, 그 밖은 기본(영어).
PROFILE = {
    'commands': {
        'ko': [('dashboard', '1-1 홈페이지 분석 — /dashboard TSLA'),
               ('market', '1-2 장 마감 시황 — /market kr · us'),
               ('report', '2-1 심층 리포트(16장) — /report TSLA'),
               ('ir', '2-2 최근 공시·분기 재무 한 장(미국) — /ir TSLA'),
               ('add', '3-1 유튜브 채널 구독 — 새 영상 자동 요약'),
               ('person', '3-2 인물 추적 — /person 박세익'),
               ('yt', '3-3 유튜브 영상 요약'),
               ('list', '3-4 내 구독 채널'),
               ('corners', '3-5 채널별 받을 영상 고르기'),
               ('remove', '3-6 구독 해제 — /remove 1'),
               ('watch', '4-1 뉴스·공시·자동 요약 등록 — /watch TSLA'),
               ('watchlist', '4-2 내 감시 종목'),
               ('unwatch', '4-3 감시 해제 — /unwatch TSLA'),
               ('voc', '5-1 불편·건의 보내기 — /voc'),
               ('recap', '5-2 최근 내 요청 정리'),
               ('terms', '5-3 이용 안내·면책'),
               ('help', '전체 사용법')],
        'en': [('dashboard', '1-1 Web stock analysis — /dashboard TSLA'),
               ('market', '1-2 Market close recap — /market kr · us'),
               ('report', '2-1 Deep-dive report (16 cards) — /report TSLA'),
               ('ir', '2-2 Latest filings & quarterly trend — /ir TSLA'),
               ('add', '3-1 Subscribe to a YouTube channel'),
               ('person', '3-2 Track a person — /person NAME'),
               ('yt', '3-3 YouTube video summary'),
               ('list', '3-4 My channels'),
               ('corners', '3-5 Pick video types per channel'),
               ('remove', '3-6 Unsubscribe — /remove 1'),
               ('watch', '4-1 News & filings digest — /watch TSLA'),
               ('watchlist', '4-2 My watchlist'),
               ('unwatch', '4-3 Stop watching — /unwatch TSLA'),
               ('voc', '5-1 Send feedback — /voc'),
               ('recap', '5-2 My recent requests'),
               ('terms', '5-3 Terms & disclaimer'),
               ('help', 'How to use')],
    },
    # 소유자 메뉴에만 더 보이는 명령(2026-10-23) — 텔레그램 chat 범위 명령 목록(일반 사용자 메뉴엔 안 보임)
    'owner_extra': [('stats', '6-1 사용 현황 — 가입자·DAU·기능 순위 (나만 보임)')],
    # 빈 대화창(시작 전)에 '이 봇은 무엇을 하나요?'로 뜨는 글. 최대 512자.
    # 핵심 기능 4개(대시보드 분석·리포트·뉴스 요약·유튜브 요약)가 모두 보여야 한다(2026-10-21 차니 지적).
    'description': {
        'ko': ('📈 부자알람 — 주식 공부를 대신 해 주는 봇\n\n'
               '1️⃣ 홈페이지 분석 — /dashboard TSLA\n'
               '   밸류 밴드·실적·동종업계·리스크를 한 화면에\n'
               '2️⃣ 심층 리포트 — /report 삼성전자\n'
               '   16장 카드: 재무·CANSLIM·린치 유형·차트\n'
               '3️⃣ 유튜브 요약 — 채널 구독 · 인물 · 영상 링크\n'
               '   /add 채널 · /person 박세익 · 링크 붙여넣기\n'
               '4️⃣ 뉴스·공시 자동 요약 — /watch 삼성전자\n'
               '   공시는 바로, 뉴스는 아침·저녁 하루 2번\n\n'
               '🇺🇸 미국 · 🇰🇷 한국 종목. [시작]을 눌러 주세요.\n'
               '투자 권유가 아닌 정보 요약입니다.'),
        'en': ('📈 Buza Alarm — does your stock homework for you\n\n'
               '1️⃣ Web analysis — /dashboard TSLA\n'
               '   Valuation bands, earnings, peers, risks\n'
               '2️⃣ Deep-dive report — /report TSLA\n'
               '   16 cards: financials, CANSLIM, Lynch, chart\n'
               '3️⃣ YouTube summaries — channels, people, links\n'
               '   /add a channel · /person a guest · paste a link\n'
               '4️⃣ News & filings digest — /watch TSLA\n'
               '   Filings instantly, news twice a day\n\n'
               'US 🇺🇸 and Korea 🇰🇷 stocks. Tap Start.\n'
               'Information only, not investment advice.'),
    },
    # 프로필·공유 링크 미리보기에 뜨는 한 줄. 최대 120자.
    'short': {'ko': '주식 공부를 대신 해 주는 봇 · ①홈페이지 분석 ②심층 리포트 ③유튜브 요약 ④뉴스·공시 요약 🇺🇸🇰🇷',
              'en': 'Your stock homework, done: 1 web analysis 2 deep reports 3 YouTube summaries 4 news digest'},
}


def profile_hash() -> str:
    import hashlib
    return hashlib.sha1(json.dumps(PROFILE, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def setup_profile() -> bool:
    """PROFILE 을 텔레그램에 건다. 기본(언어 미지정)은 영어, ko 는 한국어."""
    ok = True
    for lang in ('en', 'ko'):
        lc = {} if lang == 'en' else {'language_code': lang}
        calls = [('setMyCommands', {'commands': [{'command': c, 'description': d}
                                                 for c, d in PROFILE['commands'][lang]], **lc}),
                 ('setMyDescription', {'description': PROFILE['description'][lang], **lc}),
                 ('setMyShortDescription', {'short_description': PROFILE['short'][lang], **lc})]
        for m, body in calls:
            try:
                j = requests.post(f'{API}/{m}', json=body, timeout=15).json()
                if not j.get('ok'):
                    print(f'[프로필 {m} {lang} 실패] {j.get("description")}')
                    ok = False
            except Exception as e:
                print(f'[프로필 {m} {lang} 오류] {e}')
                ok = False
    try:   # 소유자 대화방만: 공개 메뉴 + 소유자 전용 명령
        import config
        oc = getattr(config, 'OWNER_CHAT', '')
        if oc:
            cmds = PROFILE['commands']['ko'] + PROFILE['owner_extra']
            j = requests.post(f'{API}/setMyCommands', json={
                'commands': [{'command': c, 'description': d} for c, d in cmds],
                'scope': {'type': 'chat', 'chat_id': int(oc)}}, timeout=15).json()
            if not j.get('ok'):
                print(f'[소유자 메뉴 실패] {j.get("description")}')
                ok = False
    except Exception as e:
        print(f'[소유자 메뉴 오류] {e}')
        ok = False
    try:   # 입력창 왼쪽 버튼을 '명령 메뉴'로 (기본값이지만 명시)
        requests.post(f'{API}/setChatMenuButton', json={'menu_button': {'type': 'commands'}}, timeout=15)
    except Exception:
        pass
    return ok
