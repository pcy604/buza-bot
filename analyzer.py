"""영상 분석 — RSS 감지 · 자막(프록시) · Gemini 요약. (stock_screener/guru_youtube 이식)"""
import re
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import requests
import config
import factcheck

KST = timezone(timedelta(hours=9))
TRANSCRIPT_LIMIT = 120_000
STAMP_INTERVAL = 20
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'

_TRANSIENT = ('503', 'unavailable', 'overloaded', 'high demand', '429', 'resource_exhausted', 'deadline', 'timeout')


# ── 채널 ID 해석 ─────────────────────────────────────────────────────
def resolve_channel_id(ref: str):
    s = ref.strip()
    m = re.search(r'(UC[\w-]{20,})', s)
    if m and (s.startswith('UC') or '/channel/' in s):
        return m.group(1)
    url = s.split('?')[0] if s.startswith('http') else f'https://www.youtube.com/@{s.lstrip("@")}'
    # ⚠️ 2026-09-17: /add 가 @핸들 URL에서 전부 실패하고 있었다. 원인은 여기 박아둔
    #    SOCS 쿠키 값이 2024-08-06자로 **만료**돼, YouTube가 채널 페이지 대신 EU
    #    동의 화면을 돌려준 것이다(폴란드 IP 기준 "Zanim przejdziesz do YouTube",
    #    583KB짜리 동의 페이지에 channelId가 없다). 짧은 'CAI' 값이면 통과한다.
    #    쿠키 값을 길게 박아두면 이런 식으로 조용히 썩는다 — 최소값만 쓴다.
    #    /channel/UC... 형식은 위 정규식에서 이미 처리되므로 여기까지 안 온다.
    pat = re.compile(r'"(?:channelId|externalId)":"(UC[\w-]{20,})"')
    for u in (url, url.rstrip('/') + '/videos'):
        try:
            r = requests.get(u, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en'},
                             cookies={'SOCS': 'CAI'}, timeout=15)
            m = pat.search(r.text) or re.search(r'/channel/(UC[\w-]{20,})', r.text)
            if m:
                return m.group(1)
            print(f'[채널ID 실패] {u} — 응답 {len(r.text):,}자에 channelId 없음'
                  f'{" (동의 화면으로 보임)" if "consent" in r.url or len(r.text) < 700_000 else ""}')
        except Exception as e:
            print(f'[채널ID 예외] {u}: {type(e).__name__}')
    return None


def channel_title(cid: str) -> str:
    try:
        r = requests.get(f'https://www.youtube.com/feeds/videos.xml?channel_id={cid}', timeout=15)
        t = ET.fromstring(r.content).find('{http://www.w3.org/2005/Atom}title')
        return (t.text or cid) if t is not None else cid
    except Exception:
        return cid


# ── 합본(전체방송) 판별 ──────────────────────────────────────────────
# 삼프로TV·체슬리TV 같은 채널은 **같은 내용을 두 번 올린다**: 긴 전체방송 한 개와,
# 그걸 쪼갠 짧은 클립 여러 개. 전체방송은 클립들의 합이라 요약할 내용이 새롭지 않다.
#
# 2026-09-17 실측(분석 257건):
#   · 합본은 전체의 6%인데 **실패의 31%**를 차지
#   · 합본 실패율 31% vs 나머지 4% — 8배
#   · 실패 원인은 대부분 토큰 한도 초과(1,048,576) — 4시간짜리는 fps를 낮춰도 안 들어간다
# 즉 가장 비싸고, 가장 자주 실패하고, 내용은 중복인 것을 굳이 돌리고 있었다.
#
# ⚠️ 무조건 버리지 않는다. 전체방송만 올리는 채널을 구독하면 그 채널은 아무것도
#    못 받게 된다. **같은 수집분에 다른 영상이 있을 때만** 건너뛴다.
FULL_BROADCAST = re.compile(r'전체보기|전체방송|풀버전|다시보기|운용회의\s*라이브|생방송\s*전체', re.I)


def fetch_recent_videos(channel_id: str, channel_name: str) -> list:
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    ns = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
    out = []
    try:
        # RSS 는 동의 화면을 안 타지만, 같은 만료된 SOCS 값을 여기도 박아뒀었다
        # (resolve_channel_id 주석 참고 — 그쪽은 이것 때문에 통째로 죽어 있었다).
        # 같은 지뢰를 두 군데 두지 않는다.
        r = requests.get(url, headers={'User-Agent': UA},
                         cookies={'SOCS': 'CAI'}, timeout=15)
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f'[RSS 실패] {channel_name}: {e}')
        return out
    now = datetime.now(timezone.utc)
    for e in root.findall('a:entry', ns):
        try:
            vid = e.find('yt:videoId', ns).text
            title = e.find('a:title', ns).text or ''
            published = e.find('a:published', ns).text
            pub = datetime.fromisoformat(published)
        except Exception:
            continue
        if (now - pub).total_seconds() > config.LOOKBACK_HOURS * 3600:
            continue
        tl = title.lower()
        # '다시보기'는 여기서 뺐다 — 아래 FULL_BROADCAST 조건부 규칙으로 옮겼다.
        # 무조건 버리면 다시보기만 올리는 채널이 통째로 비기 때문이다.
        if any(k in tl for k in ('#shorts', 'shorts', '쇼츠', '예고')):
            continue
        out.append({'video_id': vid, 'title': title, 'channel': channel_name,
                    'published': published, 'url': f'https://www.youtube.com/watch?v={vid}'})

    clips = [v for v in out if not FULL_BROADCAST.search(v['title'])]
    if clips and len(clips) < len(out):
        skipped = [v['title'][:40] for v in out if FULL_BROADCAST.search(v['title'])]
        print(f'[{channel_name}] 합본 {len(skipped)}건 건너뜀(같은 내용의 짧은 클립이 있음): '
              + ' / '.join(skipped))
        return clips
    if not clips and out:
        # 전체방송만 올라온 날 — 건너뛰면 이 채널은 아무것도 못 준다. 그대로 간다.
        print(f'[{channel_name}] 합본뿐이라 그대로 처리({len(out)}건)')
    return out


# ── 자막 (프록시 지원) ───────────────────────────────────────────────
def _ytt():
    from youtube_transcript_api import YouTubeTranscriptApi
    if config.YT_PROXY:
        try:
            from youtube_transcript_api.proxies import GenericProxyConfig
            return YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=config.YT_PROXY, https_url=config.YT_PROXY))
        except Exception:
            pass
    return YouTubeTranscriptApi()


def _fetch_via(api, video_id):
    fetched = api.fetch(video_id, languages=config.TRANSCRIPT_LANGS)
    segs = [(float(getattr(s, 'start', 0)), getattr(s, 'text', '')) for s in fetched]
    return [(t, x) for t, x in segs if x] or None


def get_transcript_segments(video_id: str):
    """프록시 → (실패 시) 직접 순서로 시도한다.

    2026-08-17: 프록시 IP가 YouTube에 차단(RequestBlocked/IpBlocked)돼 자막이
    94% 실패하고 있었다(224건 중 transcript 13건). 그러면 영상을 통째로 Gemini에
    던지는 폴백으로 넘어가는데, 그 경로는 커버리지가 확연히 낮다
    (요약이 다룬 마지막 시점 p25: 자막 20.8분 vs 폴백 6.5분).
    가정용 IP에서는 직접 접속이 5/5로 멀쩡하므로, 프록시가 막히면 직접도 시도한다.
    (러너는 데이터센터 IP라 직접도 막힌다 — 거기선 프록시 교체가 유일한 답이다.)
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    attempts = []
    if config.YT_PROXY:
        attempts.append(('프록시', _ytt()))
    attempts.append(('직접', YouTubeTranscriptApi()))
    last = ''
    for label, api in attempts:
        try:
            segs = _fetch_via(api, video_id)
            if segs:
                if label != '프록시':
                    print(f'[자막] {video_id}: {label} 경로로 성공')
                return segs
        except Exception as e:
            last = type(e).__name__
            print(f'[자막 실패·{label}] {video_id}: {last}')
    return None


def fmt_ts(sec) -> str:
    sec = int(sec or 0)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def build_stamped(segs) -> str:
    """자막을 [mm:ss] 마커와 함께 한 덩어리로. 한도를 넘으면 '앞에서 자르기'가 아니라
    간격을 벌려 **전 구간에서 고르게** 솎아낸다.

    2026-08-17: 예전엔 `[:TRANSCRIPT_LIMIT]`로 앞부분만 남겨서, 4시간짜리 전체방송
    (실측 127,156자)은 뒤 절반이 통째로 사라진 채 요약됐다. 30분 영상은 1만자 남짓이라
    영향이 없지만, 긴 방송에서는 "뒤에 나온 결론"이 요약에 아예 못 들어간다.
    """
    out, nxt = [], 0
    for start, text in segs:
        if start >= nxt:
            out.append(f"[{fmt_ts(start)}]")
            nxt = start + STAMP_INTERVAL
        out.append(text)
    body = ' '.join(out)
    if len(body) <= TRANSCRIPT_LIMIT:
        return body

    # 문자 단위로 자르거나 솎으면 글자가 깨진다 — 문장(세그먼트) 단위로 균등하게 남긴다.
    total = sum(len(x) for _, x in segs)
    keep_ratio = TRANSCRIPT_LIMIT / total
    step = max(1, round(1 / keep_ratio))
    kept = segs[::step]
    out2, nxt2 = [], 0
    for start, text in kept:
        if start >= nxt2:
            out2.append(f"[{fmt_ts(start)}]")
            nxt2 = start + STAMP_INTERVAL
        out2.append(text)
    body2 = ' '.join(out2)[:TRANSCRIPT_LIMIT]
    print(f'[자막 축약] {len(body):,}자 → {len(body2):,}자 '
          f'(세그먼트 {len(segs):,}→{len(kept):,}, 전 구간 균등)')
    return body2


# ── Gemini ──────────────────────────────────────────────────────────
PROMPT = """당신은 주식·투자 전문 애널리스트입니다. '{channel}' 채널의 영상 「{title}」 내용입니다.
투자자가 빠르게 흡수할 핵심을 {lang}로 정리하세요. 모든 출력 텍스트는 {lang}로.
자막의 [mm:ss] 마커를 참고해 각 항목이 언급된 시점을 초(정수)로 함께 적으세요.

순수 JSON만 출력:
{{
  "relevant": true,
  "one_liner": "핵심 한 문장",
  "summary": ["요약 3~6개"],
  "tickers": [{{"name":"종목","ticker":"미국=심볼/한국=6자리코드/모르면 빈칸","context":"맥락 한 줄","view":"긍정|중립|부정","t":정수초}}],
  "key_points": [{{"point":"강조 포인트","kind":"fact|claim","t":정수초}}],
  "actionable": ["체크 액션 0~3개"]
}}
규칙:
- relevant=투자·시장 핵심이면 true, 잡담·인문교양이면 false. 종목 없으면 tickers=[]. 추측 금지.
  **출연자가 투자 전문가여도 영상 주제가 신앙·간증·인생 이야기·자기계발이면 false**(2026-10-24 실측:
  기독교 방송 간증 영상이 투자 요약으로 나갔다). 시장·종목·경제 이야기가 영상의 중심일 때만 true.
- **영상에서 말한 숫자를 빼먹지 말 것.** 목표가·수익률·실적 수치·비중·기간이 나오면
  그 숫자를 요약에 그대로 넣는다. "긍정적으로 전망했다"는 요약이 아니다 —
  "목표가 $45 제시(현재가 대비 +30%)"가 요약이다.
- **제목을 바꿔 쓰지 말 것.** 제목만 봐도 아는 내용은 summary 에 넣지 않는다.
  사용자는 제목을 이미 봤다. 제목에 없는 것만 적는다.
- **먼저 "이 영상이 결국 하고 싶은 말"을 한 문장으로 정하고, 그 문장에 기여하지
  않는 항목은 빼거나 맨 뒤로 보낼 것.** 패널 토크·마감시황처럼 여러 코너가 붙은
  영상은 시간순으로 나열하면 요약이 아니라 목차가 된다. 실제로 그렇게 나왔다:
  한 요약이 투자원칙·파생상품 경고·1994년 멕시코 위기·스웨덴 산업구조·배당주 6선을
  접속사로 이어붙였고, 그중 절반은 제목과 아무 상관이 없었다.
  one_liner 가 그 한 문장이고, summary·key_points 는 그 문장을 떠받쳐야 한다.
- **key_points 의 모든 항목에 "kind" 를 반드시 붙일 것.** 빠뜨리면 안 된다.
    kind="fact"  — 영상 밖에서 확인 가능한 것. 공시 수치, 발표된 계약, 지수 종가,
                   이미 일어난 사건.
    kind="claim" — 출연자의 판단. 전망·평가·제언·추정·인과 해석.
  ⚠️ 판단은 **문장의 말투가 아니라 내용**으로 한다. 2026-09 실측에서 "~라고 봅니다"에만
     표시가 붙고 같은 의견을 "~하다"로 바꿔 쓰면 안 붙었다. 주어가 없어도
     "한국도 투트랙이 시급하다", "Capex 지연은 성장률 둔화로 이어질 수 있다" 는 claim 이다.
  ⚠️ 한 항목에 사실과 판단을 같이 담지 말 것. 섞이면 kind 를 정할 수 없다 —
     그럴 땐 **두 항목으로 쪼개라.**
  (텍스트에 "발언: " 을 덧붙이지 않아도 된다. kind 가 그 역할을 한다.)
- **제목이 던진 질문에 먼저 답할 것.** 제목에 나온 용어("AI 속도조절론" 등)를
  요약에서 설명 없이 결론만 말하면, 전제를 모르는 사람은 무슨 얘긴지 알 수 없다.
- **숫자를 옮기기 전에 말이 되는지 한 번 따져볼 것.** 실제로 이런 게 나갔다:
  "SK하이닉스, 엔비디아와 5년간 7,000억 달러 HBM 공급" — 엔비디아 연매출의 5배다.
  잘못 들었거나 출연자가 과장한 것이다. 규모가 회사 매출·시총에 비해 터무니없으면
  그 숫자는 빼거나 "발언: "을 붙여 출연자 주장임을 명시한다. 틀린 숫자는 없는 숫자보다 나쁘다.
- **티커 코드를 모르면 빈칸으로 둘 것.** 지어내지 말고, 확신이 없으면 이름만 적는다.
  나라 이름('US'·'CN')이나 지수·통화(KOSPI·VIX·USD/JPY)는 종목이 아니므로 코드를 비운다.
  회사 이름만 맞으면 쓸모가 있지만, 코드가 틀리면 사용자가 엉뚱한 종목으로 간다.
- view 는 **영상에서 그 근거가 실제로 언급된 경우에만** 긍정/부정을 쓴다.
  종목이 그냥 언급만 됐으면 중립이다. context 에 그 판단의 근거를 한 줄로 적는다.
- actionable 은 "관심 갖기" 같은 말 대신 **확인 가능한 행동**만("10/28 실적발표에서
  가이던스 상향 여부 확인"). 없으면 빈 배열.

[영상 내용]
{body}
"""

_EMPTY = {'relevant': True, 'one_liner': '', 'summary': [], 'tickers': [], 'key_points': [], 'actionable': []}


def _client(timeout_ms: int = 150_000):
    from google import genai
    from google.genai import types
    # 호출당 타임아웃(ms) — 무한 hang 방지.
    # ⚠️ 2026-10-03 실측: 9/24~ 실패 7건 중 **4건이 타임아웃**으로 최대 원인이었다.
    #    자막 경로(텍스트)는 150초로 충분하지만 영상 직접 분석은 모델이 영상을
    #    훑는 시간이 더 든다. 경로별로 다르게 준다(VIDEO_TIMEOUT_MS).
    #    너무 키우면 러너 작업시간을 먹으므로 상한을 둔다.
    return genai.Client(api_key=config.GEMINI_KEY,
                        http_options=types.HttpOptions(timeout=timeout_ms))


VIDEO_TIMEOUT_MS = 330_000   # 영상 직접 분석 전용(5.5분). 자막 경로는 기본값을 쓴다.


def _parse(text: str) -> dict:
    t = re.sub(r'^```(?:json)?\s*|\s*```$', '', (text or '').strip(), flags=re.I).strip()
    cands = [t]
    m = re.search(r'\{.*\}', t, flags=re.DOTALL)
    if m:
        cands.append(m.group(0))
    for c in cands:
        try:
            # ⚠️ 검사는 여기 **한 곳**에만 건다. analyze()의 자막 경로와 영상 폴백,
            #    그리고 ir.py 의 공시 요약까지 전부 _parse 를 거치므로, 경로마다
            #    따로 부르면 새 경로가 생겼을 때 조용히 빠져나간다.
            return factcheck.sanitize({**_EMPTY, **json.loads(c)})
        except Exception:
            continue
    return {**_EMPTY, '_parse_error': True}


class VideoTooLong(RuntimeError):
    """fps 를 최저로 낮춰도 입력 토큰 한도를 넘는 영상 — 보내봐야 400 이다."""


class QuotaExhausted(RuntimeError):
    """모든 모델의 '일일' 무료 쿼터가 소진된 상태 — 오늘은 기다려도 안 풀린다."""


def _quota_kind(err_text: str):
    """429의 종류를 'none'(무료티어 없음)·'minute'(잠깐)·'day'(오늘 끝)로 구분.

    실측으로 확인한 함정 두 가지:

    ① 한 번의 429 응답에 **여러 quotaId가 동시에 나열된다**. 실제 응답에
       PerDay·PerMinute·InputTokensPerMinute가 한꺼번에 들어 있어서, "perday라는
       글자가 있으면 일일소진"으로 판단하면 13초만 기다리면 될 상황도 "오늘 끝"으로
       오진해 모델을 통째로 건너뛴다. Google이 직접 알려주는 `retryDelay`가 가장
       믿을 만한 신호다 — 60초 이내면 기다리면 풀리는 것.

    ② `limit: 0`이면 "다 썼다"가 아니라 **애초에 그 모델엔 무료 한도가 없다**는 뜻이다
       (실측: gemini-2.0-flash는 분당 한도까지 limit=0 — 사용량과 무관하게 항상 차단).
       기다려도 영영 안 풀리니 재시도도, 다음 실행에서의 재시도도 낭비다.
    """
    low = err_text.lower()
    if not ('429' in low or 'resource_exhausted' in low or 'quota' in low):
        return None, 0
    m = re.search(r"'retrydelay'\s*:\s*'(\d+)s'", low)
    delay = int(m.group(1)) if m else 0
    limits = set(re.findall(r'limit:\s*(\d+)', low))
    if limits == {'0'} and 'perminute' in low.replace('_', ''):
        return 'none', 0        # 무료 티어 자체가 없는 모델
    # ⚠️ 위반한 quotaId 를 먼저 본다. 예전엔 retryDelay 를 우선했는데, 일일 한도에
    #    걸려도 Google 이 짧은 retryDelay(21초)를 같이 주기 때문에 **하루치가 끝난 걸
    #    '분당 한도'로 오진하고 4분을 기다린 뒤 실패**했다.
    #    실측(2026-09-14 /dd SATL):
    #      quotaId=['generaterequestsperdayperprojectpermodel'] limit=['20'] retryDelay=21s
    #      → '분당 한도 23초 대기 후 재시도 1/4' 로 분류돼 109초를 날렸다.
    #    원 주석이 걱정한 건 한 응답에 PerDay·PerMinute 가 **동시에** 나열되는 경우다.
    #    그때만 retryDelay 로 가르고, perday 단독이면 그대로 '오늘 끝'으로 본다.
    ids = ''.join(re.findall(r"quotaid['\"]?\s*:\s*['\"]?([a-z0-9]+)", low))
    if 'perday' in ids and 'perminute' not in ids:
        return 'day', 0
    if 0 < delay <= 60:
        return 'minute', delay  # 잠깐 기다리면 풀림
    if 'perday' in low.replace('_', ''):
        return 'day', 0
    return 'minute', delay or 15


# 이 프로세스에서 "무료 티어 없음"으로 확인된 모델 — 매 호출마다 다시 찔러봐야
# 똑같이 차단당하므로(티커당 8콜 × 왕복 낭비) 한 번 확인하면 건너뛴다.
_NO_FREE_TIER = set()


def _generate(client, contents, retries=4):
    last = None
    exhausted = []
    usable = [m for m in config.GEMINI_MODELS if m not in _NO_FREE_TIER]
    for model in usable:
        i = 0
        while i < retries:
            try:
                return client.models.generate_content(model=model, contents=contents)
            except Exception as e:
                last, s = e, str(e)
                kind, delay = _quota_kind(s)
                if kind == 'none':
                    print(f'[{model} 무료 티어 없음(limit 0) → 이후 건너뜀]')
                    _NO_FREE_TIER.add(model)
                    break
                if kind == 'day':
                    print(f'[{model} 일일 쿼터 소진 → 다음 모델]')
                    exhausted.append(model)
                    break
                if kind == 'minute':
                    wait = min(max(delay + 2, 5), 65)
                    if i == 0:
                        # 첫 번째만 원문 근거를 남긴다. 예전엔 분류 결과('분당 한도')만
                        # 찍어서, 나중에 "정말 분당이었나 일일이었나"를 확인할 방법이
                        # 없었다 — 2026-09-06 에 4분씩 기다리다 실패한 원인을 사후에
                        # 못 가렸다. 값이 아니라 한도 종류만 찍으므로 키는 안 샌다.
                        _q = set(re.findall(r"quotaid['\"]?\s*:\s*['\"]?([a-z0-9]+)", s.lower()))
                        _l = set(re.findall(r'limit:\s*(\d+)', s.lower()))
                        print(f'[{model} 429 근거 — quotaId={sorted(_q) or "?"} '
                              f'limit={sorted(_l) or "?"} retryDelay={delay}s]')
                    print(f'[{model} 분당 한도 — {wait}초 대기 후 재시도 {i+1}/{retries}]')
                    time.sleep(wait)
                    i += 1
                    continue
                if not any(k in s.lower() for k in _TRANSIENT) or i == retries - 1:
                    raise
                time.sleep(5 * (i + 1))
                i += 1
    if usable and len(exhausted) == len(usable):
        raise QuotaExhausted(
            'Gemini 무료 티어 일일 쿼터가 전 모델에서 소진됨 — 오늘은 더 못 돌린다. '
            '무료 일일 한도는 태평양시 자정(한국시간 오후 4~5시경)에 초기화됨.') from last
    raise last


def coverage(a: dict, segs=None) -> float | None:
    """요약이 영상의 몇 %까지 다뤘나 (0~1). 품질이 조용히 나빠지는 걸 잡는 지표.

    2026-08-17 신설. 덱 파이프라인에서 겪은 것과 같은 문제 — 계속 돌긴 도는데
    품질이 내려간 걸 아무도 모르는 상태를 만들지 않으려고 숫자로 남긴다.
    """
    ts = [p.get('t') for p in (a.get('key_points') or []) + (a.get('tickers') or [])
          if isinstance(p, dict) and isinstance(p.get('t'), (int, float))]
    ts = [t for t in ts if 0 < t < 6 * 3600]          # 6시간 초과는 환각으로 버림
    if not ts:
        return None
    dur = segs[-1][0] if segs else a.get('duration_sec')
    if not dur or dur <= 0:
        return None
    return min(1.0, max(ts) / float(dur))


def sanitize_times(a: dict, dur=None) -> dict:
    """영상 길이를 넘는 시점(t)은 지운다 — 영상 경로에서 [7:33:30]·[17:15:40] 같은 환각 시점이
    링크로 나갔다(2026-10-24, 20분대 영상). 길이를 모르면 6시간을 상한으로 본다."""
    cap = float(dur) * 1.05 if dur and dur > 0 else 6 * 3600
    for k in ('key_points', 'tickers'):
        for it in a.get(k) or []:
            if isinstance(it, dict) and isinstance(it.get('t'), (int, float)) and not (0 <= it['t'] <= cap):
                it['t'] = None
    return a


def has_content(a: dict) -> bool:
    return bool(a.get('one_liner') or a.get('summary') or a.get('tickers') or a.get('key_points'))


# 긴 영상용 프레임 샘플링 후보 — 높은 순으로 시도해 한도에 드는 첫 값을 쓴다.
# 낮출수록 화면 정보(차트·자막 글씨)를 놓치지만 **음성은 fps와 무관하게 전량 유지**되고,
# 이 경로의 프롬프트가 음성 기반이라 손실이 작다. 무엇보다 지금은 아예 실패하고 있다.
_FPS_STEPS = (None, 0.5, 0.2, 0.1)
_TOKEN_LIMIT = 1_048_576
# ⚠️ 한도에 **붙여서** 통과시키면 안 된다. 2026-10-10 실측에서 fps=0.2 가
#    1,042,124 토큰으로 "한도 아래"라 선택됐는데, 여유가 6,452(0.6%)뿐이라
#    실제 요청에서 400(토큰 초과)이 났다. 그 영상은 3·4회 재시도까지 하며
#    쿼터를 태웠다(VideoTooLong 가드는 '한도 아래'로 판정해 안 걸렸다).
#    한 단계 더 낮추면 881,948 로 16만 토큰이 남는다 — 품질 손해보다 실패가 비싸다.
#    count_tokens 는 프롬프트·오버헤드를 빼고 영상만 세므로 측정값=실제값이 아니다.
_SAFE_MARGIN = 0.90          # 한도의 90%까지만 쓴다(약 10만 토큰 여유)
_SAFE_LIMIT = int(_TOKEN_LIMIT * _SAFE_MARGIN)


def _video_part(client, url: str, vid: str):
    """영상을 한도 안에 들어가는 가장 높은 fps 로 담아 돌려준다.

    ## 왜 필요한가 (2026-09-06 실측)

    자막을 못 구하면 영상을 통째로 Gemini 에 넘기는데, 영상은 초당 토큰이라
    **1시간을 넘으면 컨텍스트 한도(1,048,576)를 넘어 400 으로 죽는다.** 실측한
    74분짜리가 1,137,217 토큰이었다. 실패 54건 중 20건이 이 한 가지 이유였고,
    삼프로TV '전체보기' 처럼 2~3시간짜리는 구조적으로 100% 실패하고 있었다.

    고정 fps 로는 못 막는다 — 같은 영상 기준 외삽으로 fps=0.5 는 2시간에서,
    fps=0.2 는 4시간 근처에서 다시 넘는다. 그래서 `count_tokens` 로 먼저 재고
    맞는 값을 고른다. count_tokens 는 **생성 쿼터를 쓰지 않으므로** 공짜다.
    (media_resolution 으로 줄이는 길도 있으나 이 API 티어에서 거부당한다 —
     'only supported in Gemini Enterprise Agent Platform'. fps 가 유일한 레버다.)

    측정이 실패하면 원래대로 기본 fps 로 보낸다 — 짧은 영상이 대부분이라
    측정 불가를 이유로 화질을 미리 깎을 이유가 없다.
    """
    from google.genai import types
    fd = types.FileData(file_uri=url)
    model = config.GEMINI_MODELS[0]
    for fps in _FPS_STEPS:
        part = types.Part(file_data=fd,
                          video_metadata=types.VideoMetadata(fps=fps) if fps else None)
        try:
            n = client.models.count_tokens(
                model=model, contents=types.Content(parts=[part])).total_tokens
        except Exception as e:
            # ⚠️ 예전엔 여기서 **기본 fps 로 맹목 전송**했다. 그래서 길이를 모르는
            #    긴 영상이 그대로 나가 400(토큰 초과)을 받았다 — VideoTooLong 이
            #    못 잡은 실패 1건의 정체가 이것이다(2026-10-03).
            #    측정을 못 했으면 '괜찮다'가 아니라 '모른다'다. 가장 안전한 쪽
            #    (최저 fps)으로 보낸다 — 짧은 영상이면 품질 손해가 거의 없고,
            #    긴 영상이면 유일하게 들어갈 수 있는 설정이다.
            print(f'[토큰 측정 실패 {vid}: {str(e)[:60]} → 최저 fps={_FPS_STEPS[-1]} 로 안전 전송]')
            return types.Part(file_data=fd,
                              video_metadata=types.VideoMetadata(fps=_FPS_STEPS[-1]))
        if n < _SAFE_LIMIT:
            if fps:
                print(f'[긴 영상 {vid}: fps={fps} 로 {n:,}토큰 (기본은 한도 초과)]')
            return part
        last = n
    # 마지막 단계로도 못 줄였다. 예전엔 "이유를 남기고 시도는 한다"며 그대로 보냈는데,
    # ⚠️ count_tokens 가 이미 초과라고 말한 뒤의 호출은 **반드시 400 이 난다.**
    #    그런데 analyze 가 재시도까지 해서, 실측으로 실패 2건이 각각 3·4회 시도했다 —
    #    성공할 수 없는 호출에 하루 쿼터를 7칸 태운 셈이다(모델당 20회 중).
    #    이유는 예외 메시지로 남기고, 호출은 하지 않는다.
    raise VideoTooLong(
        f'fps={_FPS_STEPS[-1]} 로도 {last:,}토큰 — 안전선({_SAFE_LIMIT:,}, 한도 {_TOKEN_LIMIT:,}의 '
        f'{int(_SAFE_MARGIN * 100)}%) 초과. '
        f'구간 분할 미구현이라 이 영상은 영상 경로로 요약할 수 없다(자막이 있으면 그쪽은 가능).')


def analyze(video: dict, lang: str = '한국어'):
    """(analysis, source) 반환."""
    client = _client()
    segs = get_transcript_segments(video['video_id'])
    if segs:
        prompt = PROMPT.format(channel=video['channel'], title=video['title'], body=build_stamped(segs), lang=lang)
        try:
            a = sanitize_times(_parse(_generate(client, prompt).text), segs[-1][0] if segs else None)
            cov = coverage(a, segs)
            if cov is not None:
                a['_coverage'] = round(cov, 3)
                if cov < 0.5:
                    print(f'[커버리지 낮음] {video["video_id"]}: 요약이 영상의 '
                          f'{cov*100:.0f}%까지만 다룸 (자막 경로)')
            return a, 'transcript'
        except Exception as e:
            print(f'[텍스트 실패→영상] {e}')
    try:
        from google.genai import types
        # 2026-08-17: 예전 폴백 프롬프트는 "영상 음성 직접 분석" 한 줄뿐이라 전 구간을
        # 훑으라는 지시가 없었다. 실측상 이 경로의 커버리지가 자막 경로의 1/3이었다
        # (요약이 다룬 마지막 시점 p25 6.5분 vs 20.8분, 10분 미만이 153건 중 52건).
        # 전체를 끝까지 보고 고르게 뽑으라고 명시하고, 관측한 길이도 같이 받아
        # 커버리지를 사후에 잴 수 있게 한다.
        prompt = PROMPT.format(channel=video['channel'], title=video['title'], lang=lang,
                               body='(자막 없음 — 영상 음성을 직접 분석하세요.)\n'
                                    '중요: 영상을 처음부터 끝까지 전부 듣고, summary와 key_points를 '
                                    '앞부분에 몰지 말고 전 구간에 고르게 배치하세요. '
                                    '후반부(특히 마지막 1/3)에서 나온 결론·전망을 반드시 포함하세요. '
                                    'JSON에 "duration_sec": 관측한 영상 총길이(정수 초) 를 추가하세요. '
                                    '각 항목의 t는 실제 언급 시점(초)입니다.')
        # 영상 경로는 전용 타임아웃 클라이언트로 — 자막 경로와 소요가 다르다.
        vclient = _client(VIDEO_TIMEOUT_MS)
        resp = _generate(vclient, types.Content(parts=[
            _video_part(vclient, video['url'], video['video_id']), types.Part(text=prompt)]))
        a = _parse(resp.text)
        try:
            _d = int(a.get('duration_sec') or 0)
        except (TypeError, ValueError):
            _d = 0
        a = sanitize_times(a, _d or None)
        cov = coverage(a)
        if cov is not None:
            a['_coverage'] = round(cov, 3)
            if cov < 0.5:
                print(f'[커버리지 낮음] {video["video_id"]}: 요약이 영상의 '
                      f'{cov*100:.0f}%까지만 다룸 (영상 폴백)')
        return a, 'video'
    except VideoTooLong as e:
        # 재시도해도 결과가 같다 — source 를 따로 둬서 재시도 큐가 붙들지 않게 한다.
        print(f'[영상 너무 김] {video["video_id"]}: {e}')
        return {**_EMPTY, '_error': str(e)[:200]}, 'too_long'
    except Exception as e:
        print(f'[영상 분석 실패] {e}')
        return {**_EMPTY, '_error': str(e)[:200]}, 'fail'
