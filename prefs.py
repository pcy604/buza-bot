"""사용자별 설정 — 뉴스 요약 받는 시각·시간대·언어.

2026-10-20: 감시 뉴스가 6시간 게이트에 묶여 '아무 때나' 왔다. 전 세계 사용자를 전제로
사람마다 자기 시간대의 정해진 시각에 하루 1번, 자기 언어로 받게 한다.

저장은 user_prefs.json (실행 끝에 레포로 커밋 — ir_state.json 과 같은 방식).
  {"<chat_id>": {"tz": "Asia/Seoul", "hour": 8, "lang": "ko"}}

시간대 값은 두 형태만 허용한다.
  · IANA 이름 (Asia/Seoul, Europe/Warsaw) — 서머타임이 자동 반영된다
  · 'UTC+09:00' 같은 고정 오프셋 — IANA 이름을 모르는 사람용. 서머타임은 반영 안 됨
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PREFS_PATH = Path(__file__).parent / 'user_prefs.json'

DEFAULT_HOUR = 8
DEFAULT_LANG = 'en'
DEFAULT_TZ = 'UTC'

# 요약 본문은 LLM 이 이 언어로 쓴다. 이름은 프롬프트에 그대로 들어간다.
LANGS = {
    'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh': '简体中文',
    'es': 'Español', 'pt': 'Português', 'de': 'Deutsch', 'fr': 'Français',
    'pl': 'Polski', 'uk': 'Українська', 'vi': 'Tiếng Việt', 'id': 'Bahasa Indonesia',
}
# 텔레그램 language_code 로 첫 시간대를 추정한다. 틀리면 사용자가 /tz 로 고친다.
LANG_TZ = {
    'ko': 'Asia/Seoul', 'ja': 'Asia/Tokyo', 'zh': 'Asia/Shanghai', 'pl': 'Europe/Warsaw',
    'uk': 'Europe/Kyiv', 'de': 'Europe/Berlin', 'fr': 'Europe/Paris', 'vi': 'Asia/Ho_Chi_Minh',
    'id': 'Asia/Jakarta', 'pt': 'America/Sao_Paulo', 'es': 'America/Mexico_City',
    'en': 'UTC',
}


def _load() -> dict:
    try:
        return json.loads(PREFS_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def _save(d: dict):
    PREFS_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def get(chat) -> dict:
    p = {'tz': DEFAULT_TZ, 'hour': DEFAULT_HOUR, 'lang': DEFAULT_LANG}
    p.update(_load().get(str(chat), {}))
    return p


def _set(chat, **kw):
    d = _load()
    cur = d.setdefault(str(chat), {})
    cur.update(kw)
    _save(d)
    return get(chat)


def remember_client_language(chat, language_code):
    """첫 접촉 때만 텔레그램 앱 언어로 언어·시간대를 추정해 둔다.
    이미 설정이 있으면 건드리지 않는다 — 사용자가 고른 값을 덮어쓰면 안 된다."""
    if str(chat) in _load():
        return
    code = (language_code or '').split('-')[0].lower()
    lang = code if code in LANGS else DEFAULT_LANG
    _set(chat, lang=lang, tz=LANG_TZ.get(lang, DEFAULT_TZ), hour=DEFAULT_HOUR)


# ── 파싱 ─────────────────────────────────────────────────────────────
_HOUR_RE = re.compile(r'^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|시)?\s*$', re.I)
_OFF_RE = re.compile(r'^\s*(?:utc|gmt)?\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\s*$', re.I)


def parse_hour(s: str):
    """'7' · '07:00' · '7am' · '7pm' · '19시' → 0~23. 분은 버린다(시 단위 발송)."""
    m = _HOUR_RE.match(s or '')
    if not m:
        return None
    h = int(m.group(1))
    suf = (m.group(3) or '').lower()
    if suf == 'pm' and h < 12:
        h += 12
    elif suf == 'am' and h == 12:
        h = 0
    return h if 0 <= h <= 23 else None


def parse_tz(s: str):
    """IANA 이름이나 'UTC+9' · '+5:30' · 'GMT-3' → 저장할 문자열. 모르면 None."""
    s = (s or '').strip()
    if not s:
        return None
    if s.upper() in ('UTC', 'GMT', 'Z'):
        return 'UTC'
    m = _OFF_RE.match(s)
    if m:
        sign, hh, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if hh > 14 or mm >= 60:
            return None
        return f'UTC{sign}{hh:02d}:{mm:02d}'
    for cand in (s, s.replace(' ', '_'), '/'.join(w.capitalize() for w in s.replace(' ', '_').split('/'))):
        try:
            ZoneInfo(cand)
            return cand
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return None


def parse_lang(s: str):
    s = (s or '').strip().lower()
    if s in LANGS:
        return s
    for code, name in LANGS.items():
        if s == name.lower():
            return code
    return None


def zone(tz: str):
    m = re.match(r'^UTC([+-])(\d{2}):(\d{2})$', tz or '')
    if m:
        off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3)))
        return timezone(off if m.group(1) == '+' else -off)
    try:
        return ZoneInfo(tz)
    except Exception:
        return timezone.utc


def local_now(p: dict, now: datetime = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(zone(p.get('tz')))


def local_day(p: dict, now: datetime = None) -> str:
    return local_now(p, now).date().isoformat()


NEWS_EVERY_H = 12   # 2026-10-21: 하루 1번 → 12시간마다(예: 08시·20시). 미국 장 마감 뒤 + 한국 장 마감 뒤.


def slot_hours(p: dict) -> list:
    h = int(p.get('hour', DEFAULT_HOUR))
    return sorted({(h + k * NEWS_EVERY_H) % 24 for k in range(24 // NEWS_EVERY_H)})


def current_slot(p: dict, now: datetime = None) -> str:
    """지금 속한 발송 회차 'YYYY-MM-DD@HH' — 이미 지난 가장 최근 발송 시각.
    같은 회차엔 한 번만 보내고, 크론이 밀려도 '지났으면' 보낸다(hour_reached 와 같은 이유)."""
    lt = local_now(p, now)
    best = None
    for back in (0, 1):
        d = lt - timedelta(days=back)
        for h in slot_hours(p):
            t = d.replace(hour=h, minute=0, second=0, microsecond=0)
            if t <= lt and (best is None or t > best):
                best = t
    return best.strftime('%Y-%m-%d@%H')


def hour_reached(p: dict, now: datetime = None) -> bool:
    """오늘 받을 시각이 지났는가. '정각에만'이 아니라 '지났으면'인 이유:
    GitHub 크론은 1~2시간씩 밀리고 가끔 건너뛴다. 정각 일치로 판정하면
    밀린 날은 아예 안 온다. 하루 1번은 호출부가 날짜로 막는다."""
    return local_now(p, now).hour >= int(p.get('hour', DEFAULT_HOUR))


def set_onboarding(chat, on: bool):
    return _set(chat, onboarding=bool(on))


def set_hour(chat, hour: int):
    return _set(chat, hour=int(hour))


def set_tz(chat, tz: str):
    return _set(chat, tz=tz)


def set_lang(chat, lang: str):
    return _set(chat, lang=lang)


# ── 화면 문구 (ko·en 만 직접 쓰고, 나머지 언어는 en 으로) ─────────────
# 요약 본문은 LLM 이 선택 언어로 쓰므로 모든 언어가 된다. 여기 있는 건 틀 문구뿐이다.
TEXT = {
    'news_head': {'ko': '📰 <b>{t}</b> 새 뉴스 {n}건', 'en': '📰 <b>{t}</b> — {n} new stories'},
    'news_head2': {'ko': '📰 <b>{t}</b> 중요 {k}건 <i>· 새 사건 {n}건 중</i>', 'en': '📰 <b>{t}</b> — {k} key of {n} new stories'},
    'other_news': {'ko': '나머지 기사', 'en': 'other stories'},
    'followup': {'ko': '🔁 후속', 'en': '🔁 update'},
    'sources': {'ko': '원문', 'en': 'Sources'},
    'outlets': {'ko': '매체 {n}곳', 'en': '{n} outlets'},
    'more': {'ko': '외 {n}건', 'en': '+{n} more'},
    'no_digest': {'ko': '<i>(요약을 못 만들어 원문만 보냅니다)</i>',
                  'en': '<i>(Summary unavailable — sending the original links)</i>'},
    'links_cut': {'ko': '<i>원문 링크 {n}건은 길이 제한으로 생략</i>',
                  'en': '<i>{n} links omitted (message length limit)</i>'},
    'settings': {
        'ko': ('⚙️ <b>내 설정</b>\n'
               '• 뉴스 요약 받는 시각: 매일 <b>{hour:02d}:00</b>·<b>{hour2:02d}:00</b> (12시간마다)\n'
               '• 시간대: <b>{tz}</b> (지금 {now})\n'
               '• 언어: <b>{lang}</b>\n\n'
               '바꾸기\n'
               '<code>/time 7</code> — 받는 시각 (0~23시, 12시간 뒤에 한 번 더)\n'
               '<code>/tz Asia/Seoul</code> 또는 <code>/tz +9</code> — 시간대\n'
               '<code>/lang en</code> — 언어 ({langs})'),
        'en': ('⚙️ <b>Your settings</b>\n'
               '• News digest at: <b>{hour:02d}:00</b> & <b>{hour2:02d}:00</b> (every 12h)\n'
               '• Time zone: <b>{tz}</b> (now {now})\n'
               '• Language: <b>{lang}</b>\n\n'
               'Change\n'
               '<code>/time 7</code> — delivery hour (0–23, plus 12h later)\n'
               '<code>/tz America/New_York</code> or <code>/tz -5</code> — time zone\n'
               '<code>/lang ko</code> — language ({langs})'),
    },
    'time_ok': {'ko': '✅ 이제 매일 <b>{hour:02d}:00</b>·<b>{hour2:02d}:00</b> ({tz})에 감시 종목 뉴스를 요약해 드려요.',
                'en': '✅ Digest set to <b>{hour:02d}:00</b> & <b>{hour2:02d}:00</b> ({tz}).'},
    'time_bad': {'ko': '사용법: <code>/time 7</code> (0~23시, 예: /time 19 · /time 7am)',
                 'en': 'Usage: <code>/time 7</code> (0–23, e.g. /time 19 · /time 7am)'},
    'tz_ok': {'ko': '✅ 시간대를 <b>{tz}</b>로 바꿨어요. 지금 그쪽 시각은 {now} 입니다.',
              'en': '✅ Time zone set to <b>{tz}</b>. Local time there is {now}.'},
    'tz_bad': {'ko': '시간대를 못 알아들었어요. 예: <code>/tz Asia/Seoul</code> · <code>/tz Europe/Warsaw</code> · <code>/tz +9</code>',
               'en': "Couldn't read that time zone. e.g. <code>/tz America/New_York</code> · <code>/tz Europe/London</code> · <code>/tz -5</code>"},
    'lang_ok': {'ko': '✅ 언어를 <b>{lang}</b>로 바꿨어요. 다음 요약부터 적용돼요.',
                'en': '✅ Language set to <b>{lang}</b>. Applies from the next digest.'},
    'lang_bad': {'ko': '지원 언어: {langs}\n예: <code>/lang en</code>',
                 'en': 'Supported: {langs}\ne.g. <code>/lang ko</code>'},
    'watch_ok': {
        'ko': ('👁️ <b>{t}</b> ({name}) 감시 시작.\n'
               '새 <b>공시</b>는 카드로 (6시간마다 확인), 새 <b>뉴스</b>는 매일 <b>{hour:02d}:00</b>·<b>{hour2:02d}:00</b> ({tz})에 '
               '지난 12시간치를 요약해서 보내드려요. 중요한 사건이 없으면 보내지 않아요.\n'
               '· 지금 최신 자료: <code>/ir {t}</code>\n'
               '· 감시 목록: <code>/watchlist</code> · 해제: <code>/unwatch {t}</code>'),
        'en': ('👁️ Now watching <b>{t}</b> ({name}).\n'
               'New <b>SEC filings</b> arrive as cards (checked every 6h). <b>News</b> comes twice a day at '
               '<b>{hour:02d}:00</b> & <b>{hour2:02d}:00</b> ({tz}) as a digest of the past 12h — skipped if nothing material happened.\n'
               '· Latest now: <code>/ir {t}</code>\n'
               '· List: <code>/watchlist</code> · Stop: <code>/unwatch {t}</code>'),
    },
    'dash_one':  {'ko': '📊 대시보드에서 보기', 'en': '📊 Open in dashboard'},
    'dash_list': {'ko': '📊 대시보드에서 감시 목록 열기', 'en': '📊 Open watchlist in dashboard'},
    'feedback_ask': {'ko': '도움이 됐나요? 👍 /good_{tk} · 👎 /bad_{tk}',
                     'en': 'Useful? 👍 /good_{tk} · 👎 /bad_{tk}'},
    'feedback_thanks': {'ko': '고마워요. 요약 품질을 고르는 데 그대로 씁니다.',
                        'en': 'Thanks — this goes straight into tuning the digest.'},
    'onboard': {
        'ko': ('👋 <b>부자알람</b>에 오신 걸 환영해요.\n\n'
               '가지고 있거나 지켜보는 <b>종목</b>을 보내 주세요. 티커·6자리 코드·한글 이름 모두 돼요.\n'
               '(예: <code>TSLA 삼성전자 005930</code>)\n'
               '매일 <b>{hour:02d}:00</b>·<b>{hour2:02d}:00</b> ({tz})에 그 종목들의 <b>중요한 변화만</b> 요약해 드려요. '
               '별일 없는 날은 조용합니다.\n\n'
               '전체 기능: /help · 불편·건의: /voc\n\n'
               '<i>투자 권유가 아닌 정보 요약이에요 · 이용 안내·면책: /terms</i>'),
        'en': ('👋 Welcome to <b>Buza Alarm</b>.\n\n'
               'Send me the <b>US stock tickers</b> you hold or watch (e.g. <code>SATL AXTI</code>).\n'
               "Every day at <b>{hour:02d}:00</b> & <b>{hour2:02d}:00</b> ({tz}) you'll get <b>only what materially changed</b> — "
               'quiet days stay quiet.\n\n'
               'All features: /help · Feedback: /voc\n\n'
               '<i>Information, not investment advice · Terms: /terms</i>'),
    },
    # 이용 안내·면책 — 대시보드 하단 고지(dashboard.py DISCLAIMER_VER)와 같은 내용. 바꾸면 둘 다 바꾼다.
    'terms': {
        'ko': ('ⓘ <b>이용 안내</b>\n\n'
               '<b>정보 도구입니다</b> — 부자알람은 공개 데이터(SEC·DART·뉴스·유튜브)를 정해진 규칙과 AI로 요약해 보여줘요. '
               '<b>투자 권유가 아니며</b>, 모든 투자 판단과 책임은 이용자 본인에게 있어요.\n\n'
               '<b>데이터 지연·오류</b> — 가격은 무료 API 기준이라 최소 15분 이상 늦을 수 있고, '
               'AI 요약은 원문과 다르거나 틀릴 수 있어요. 중요한 결정 전에는 원문 링크를 꼭 확인해 주세요.\n\n'
               '<b>백테스트·목표가</b> — 상승 확률·평균 상승률은 표시된 기간의 과거 성과일 뿐 미래를 보장하지 않아요. '
               '목표가는 증권사 컨센서스를 옮긴 것이에요.\n\n'
               '<b>이해상충</b> — 운영자는 언급된 종목을 보유하고 있을 수 있어요. 알림·점수는 보유 여부와 무관하게 '
               '모든 종목에 같은 규칙으로 계산돼요.\n\n'
               '<b>개인정보</b> — 텔레그램 ID·감시 종목·설정만 저장해요. 지우고 싶으면 운영자에게 말해 주세요.'),
        'en': ('ⓘ <b>Terms</b>\n\n'
               '<b>An information tool</b> — Buza Alarm summarizes public data (SEC, DART, news, YouTube) with fixed rules and AI. '
               '<b>It is not investment advice</b>; every decision and its outcome are yours.\n\n'
               '<b>Delays & errors</b> — prices come from free APIs and may lag 15+ minutes; AI summaries can be wrong. '
               'Check the source links before acting.\n\n'
               '<b>Backtests & targets</b> — win rates and average gains are past results, not promises. '
               'Price targets are analyst consensus.\n\n'
               '<b>Conflicts</b> — the operator may hold mentioned stocks. Alerts and scores use the same rules for every stock.\n\n'
               '<b>Privacy</b> — only your Telegram ID, watchlist and settings are stored. Ask the operator to delete them.'),
    },
    'onboard_done': {
        'ko': '👁️ 감시 시작: <b>{ok}</b>{bad}\n첫 요약은 다음 <b>{hour:02d}:00</b>·<b>{hour2:02d}:00</b> ({tz}) 중 먼저 오는 시각에 와요. 지금 바로 보려면 <code>/ir {first}</code>',
        'en': "👁️ Now watching: <b>{ok}</b>{bad}\nFirst digest arrives at the next <b>{hour:02d}:00</b> or <b>{hour2:02d}:00</b> ({tz}). To see one now: <code>/ir {first}</code>",
    },
    'onboard_bad': {'ko': '\n(못 찾은 종목: {bad} — 미국·한국 상장사만 지원)', 'en': "\n(Not found: {bad} — US-listed only)"},
    'deck_head': {'ko': '📑 <b>{t}</b> 새 IR 발표자료', 'en': '📑 <b>{t}</b> — new investor presentation'},
    'deck_changes': {'ko': '지난 자료 대비 달라진 점', 'en': 'What changed vs the previous deck'},
    'deck_points': {'ko': '그 밖의 핵심', 'en': 'Other key points'},
    'deck_watch': {'ko': '확인해 볼 것', 'en': 'Worth checking'},
    'deck_nosum': {'ko': '<i>(본문을 읽지 못해 제목·링크만 보냅니다)</i>',
                   'en': '<i>(Could not read the file — sending title and link only)</i>'},
    'deck_link': {'ko': '원문 PDF', 'en': 'Original PDF'},
    'thesis_saved': {'ko': '📌 <b>{t}</b> 보유 근거를 저장했어요. 앞으로 이 종목 뉴스 요약에서 각 사건이 이 근거를 '
                           '<b>지지하는지(✅) / 반대하는지(⚠️)</b> 함께 표시해 드려요.\n\n<i>{text}</i>',
                     'en': '📌 Saved your thesis for <b>{t}</b>. News digests will now mark each event as '
                           '<b>supporting (✅) or contradicting (⚠️)</b> it.\n\n<i>{text}</i>'},
    'thesis_show': {'ko': '📌 <b>{t}</b> 보유 근거\n<i>{text}</i>\n\n지우기: <code>/thesis {t} -</code>',
                    'en': '📌 <b>{t}</b> thesis\n<i>{text}</i>\n\nDelete: <code>/thesis {t} -</code>'},
    'thesis_none': {'ko': '아직 적어 둔 보유 근거가 없어요.\n예: <code>/thesis SATL 정부 감시 계약이 반복 매출로 바뀌는 중. '
                          'Merlin 발사가 1년 넘게 밀리면 근거 깨짐</code>\n'
                          '<b>왜 샀는지</b>와 <b>무엇이 깨지면 팔지</b>를 같이 적으면 좋아요.',
                    'en': 'No thesis saved yet.\ne.g. <code>/thesis SATL Gov contracts turning recurring. '
                          'Broken if Merlin launch slips over a year</code>\nWrite <b>why you own it</b> and '
                          '<b>what would make you sell</b>.'},
    'thesis_list': {'ko': '📌 <b>내 보유 근거</b>', 'en': '📌 <b>Your theses</b>'},
    'thesis_deleted': {'ko': '🗑️ <b>{t}</b> 보유 근거를 지웠어요.', 'en': '🗑️ Deleted thesis for <b>{t}</b>.'},
    'thesis_fields': {'ko': '비중 {w} · 감내 손실 {l} · 재점검 {r} · 기록 당시 {p}',
                      'en': 'weight {w} · max loss {l} · review {r} · price then {p}'},
    'thesis_tip': {'ko': '\n\n<i>근거 안에 "비중 10%", "감내 -20%", "점검 30일"을 넣으면 손실선 이탈과 재점검 때 알려 드려요.</i>',
                   'en': '\n\n<i>Add "weight 10%", "stop 20%", "review 30d" to get loss-line and review alerts.</i>'},
    'thesis_loss': {'ko': '⚠️ <b>{t}</b> 감내 손실선 이탈\n기록 당시 {p0} → 지금 {p} ({chg:+.1f}%) · 정해 둔 선 -{l:.0f}%\n'
                          '<b>적어 둔 근거</b>\n<i>{text}</i>\n\n근거가 아직 유효한지 직접 판단해 보세요. 봇은 매매를 권하지 않습니다.',
                    'en': '⚠️ <b>{t}</b> crossed your max-loss line\n{p0} then → {p} now ({chg:+.1f}%) · your line -{l:.0f}%\n'
                          '<b>Your thesis</b>\n<i>{text}</i>\n\nCheck whether it still holds. This is not trading advice.'},
    'thesis_review': {'ko': '🗓️ <b>{t}</b> 보유 근거 재점검 ({days}일 경과)\n<i>{text}</i>\n{pline}\n'
                            '그대로면 그냥 두고, 바뀌었으면 <code>/thesis {t} 새 근거</code>로 고쳐 적어 주세요.',
                      'en': '🗓️ <b>{t}</b> thesis review ({days} days)\n<i>{text}</i>\n{pline}\n'
                            'If it still holds, do nothing; otherwise update with <code>/thesis {t} new thesis</code>.'},
    'thesis_pline': {'ko': '기록 당시 {p0} → 지금 {p} ({chg:+.1f}%)', 'en': '{p0} then → {p} now ({chg:+.1f}%)'},
    'thesis_for': {'ko': '✅ 근거 지지', 'en': '✅ supports thesis'},
    'thesis_against': {'ko': '⚠️ 근거와 반대', 'en': '⚠️ contradicts thesis'},
    'react': {'ko': '📊 주가: 지난 요약 이후 {chg:+.1f}% · 가장 큰 날 {date} {ret:+.1f}%{vol}{gap}{held}',
              'en': '📊 Price: {chg:+.1f}% since last digest · biggest day {date} {ret:+.1f}%{vol}{gap}{held}'},
    'react_vol': {'ko': ' (거래량 평소 {x:.1f}배)', 'en': ' (volume {x:.1f}× avg)'},
    'react_gap': {'ko': ' · 갭 {g:+.1f}%', 'en': ' · gap {g:+.1f}%'},
    'react_held': {'ko': ' · 마감까지 유지', 'en': ' · held into close'},
    'react_faded': {'ko': ' · 장중 움직임 반납', 'en': ' · faded by close'},
    'react_flow': {'ko': '🏦 수급({days}일): 외국인 {f} · 기관 {i}{streak}',
                   'en': '🏦 Flows ({days}d): foreigners {f} · institutions {i}{streak}'},
    'flow_streak': {'ko': ' · {who} {n}일 연속 {side}', 'en': ' · {who} {side} {n} days straight'},
    'move_only': {'ko': '<i>중요 사건으로 볼 뉴스는 없지만, 주가가 거래량을 동반해 크게 움직였어요.</i>',
                  'en': '<i>No material news, but the stock moved sharply on heavy volume.</i>'},
    'help_en': {
        'en': ('👋 <b>Buza Alarm</b> — does your stock homework for you\n\n'
               '📊 <b>1. Web analysis</b>\n'
               '1-1 /dashboard TICKER — valuation bands, earnings, peers, risks\n'
               '1-2 /market — market close recap (Korean) · kr · us · week · on\n\n'
               '📑 <b>2. Deep-dive report</b>\n'
               '2-1 /report TICKER — 16-card research deck (Korean)\n'
               '2-2 /ir TICKER — latest filing + quarterly trend in one card (US)\n\n'
               '🎬 <b>3. YouTube summaries</b>\n'
               '3-1 /add CHANNEL_URL — subscribe, new videos summarized\n'
               '3-2 /person NAME — track a person\n'
               '3-3 /yt LINK — YouTube video summary\n'
               '3-4 /list — my channels\n'
               '3-5 /corners — pick video types per channel\n'
               '3-6 /remove N — unsubscribe\n\n'
               '📰 <b>4. News & filings digest</b>\n'
               '4-1 /watch TICKER — filings instantly, news every 12h\n'
               '4-2 /watchlist — my watchlist\n'
               '4-3 /unwatch TICKER — stop watching\n\n'
               '💬 <b>5. Other</b>\n'
               '5-1 /voc MESSAGE — send feedback\n'
               '5-2 /recap [DAYS] — my recent requests\n'
               '5-3 /terms — terms & disclaimer\n\n'
               '<i>Information only, not investment advice. Sources are always linked.</i>'),
    },
}


def t(_lang: str, _key: str, **kw) -> str:
    """틀 문구. 인자명이 _lang 인 건 문구 안의 {lang}·{t} 자리와 이름이 겹치지 않게."""
    if 'hour' in kw and 'hour2' not in kw:        # 두 번째 발송 시각(12시간 뒤)을 문구에 같이 쓴다
        kw['hour2'] = (int(kw['hour']) + NEWS_EVERY_H) % 24
    row = TEXT[_key]
    s = row.get(_lang) or row['en']
    return s.format(**kw) if kw else s


def langs_line() -> str:
    return ' · '.join(f'{c}={n}' for c, n in LANGS.items())
