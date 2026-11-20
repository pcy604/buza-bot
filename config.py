"""설정 — .env 로드 (로컬) / 환경변수 (배포)."""
import os
from pathlib import Path


def _load_env():
    p = Path(__file__).parent / '.env'
    if not p.exists():
        return
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
GEMINI_KEY     = os.environ.get('GEMINI_KEY', '')
SUPABASE_URL   = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY   = os.environ.get('SUPABASE_KEY', '')
YT_PROXY       = os.environ.get('YT_PROXY', '')
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')
# DART(전자공시) — 한국주식 재무. decks/dart_client.py 가 os.environ에서 직접 읽으므로
# 여기서는 존재 확인용으로만 노출한다(없으면 KR 포토카드만 못 만들고 나머지는 정상).
DART_KEY       = os.environ.get('DART_KEY', '')
# 종목 분석 화면(stock-dashboard, Streamlit) — 요약·리포트에서 '대시보드에서 보기' 딥링크(2026-10-20).
#   ?sym=TICKER → 그 종목 분석 탭으로 바로, ?watch=A,B → 감시 목록을 칩으로. 비우면 링크를 안 붙인다.
# 소유자 텔레그램 chat_id — 운영 알림·주간 브리핑·VOC 수신·시황 기본 구독(2026-10-23, 첫 가입자 추측 폴백 폐기)
OWNER_CHAT     = os.environ.get('OWNER_CHAT', '').strip() or '5064831796'
DASHBOARD_URL  = os.environ.get('DASHBOARD_URL',
                                'https://stock-dashboard-dmfvhcig7brge7utl7et5r.streamlit.app').rstrip('/')

# 텔레그램 웹훅 모드. 켜면 크론 실행에서 getUpdates 폴링을 하지 않는다
# (웹훅이 걸린 상태에서 getUpdates를 부르면 텔레그램이 409를 냄).
# 명령 처리는 Cloudflare Worker → repository_dispatch → run.py 즉시 경로가 담당.
USE_WEBHOOK    = os.environ.get('USE_WEBHOOK', '').lower() in ('1', 'true', 'yes')

GEMINI_MODEL     = 'gemini-3.8-flash'
# 무료 쿼터는 **모델별로 분리**된다 — 앞 모델이 소진되면 순서대로 폴백한다.
# 그래서 이 목록의 길이가 곧 하루 처리량이다(모델당 20회).
#
# ⚠️ 2026-09-15 실측으로 두 가지를 발견해 갱신했다.
#   ① 폴백 마지막이던 gemini-2.0-flash 는 **없어진 모델**이었다:
#      "models/gemini-2.0-flash is no longer available. Please update your code
#       to use models/gemini-3.6-flash"
#      즉 앞의 둘이 소진되면 아무것도 못 하는 상태였다. '하루 20회 천장'으로 보이던 게
#      사실은 살아 있는 모델이 2개뿐이라 스스로 만든 천장이었다.
#   ② 3.x 계열은 **영상 토큰이 훨씬 싸다.** 같은 74분 영상을 count_tokens 로 재니
#      2.5-flash 1,137,217 → 3.x 397,057 (65% 감소). 2.5 에서는 1시간만 넘어도
#      컨텍스트 한도(1,048,576)를 넘겨 400 으로 죽던 것이 3.x 에서는 3시간까지 들어간다.
#      (analyzer._video_part 의 fps 적응은 그보다 긴 영상용으로 남겨둔다.)
#
# 네 모델 모두 이 키로 응답·영상입력 정상 확인함. 앞쪽이 최신·고품질, 뒤로 갈수록 가볍다.
GEMINI_MODELS    = ('gemini-3.8-flash', 'gemini-3.6-flash',
                    'gemini-3.5-flash', 'gemini-3.5-flash-lite')
SEC_UA           = 'buza-bot pcy604604@gmail.com'   # SEC EDGAR 필수 UA
IR_FORMS         = ('8-K', '10-Q', '10-K', '6-K', '20-F')
JOB_INTERVAL_H   = 6      # 데몬: 영상갱신·IR감시 주기(시간)
BRIEF_INTERVAL_D = 7      # 주간 소집 브리핑 주기(일) — brief.py
# 요약 메시지에 '근거: 자막 전문 · 영상의 91% 지점까지 다룸' 줄을 붙일지.
# 기본 끔 — 품질 지표는 **우리가 검증용으로** 보는 것이지 사용자에게 내보일
# 것이 아니라는 결정(2026-09-18). 켜려면 환경변수 SHOW_QUALITY=1.
# 끈 상태에서도 source·_coverage 는 그대로 저장된다(quality.py 가 읽는다).
SHOW_QUALITY   = os.environ.get('SHOW_QUALITY', '').lower() in ('1', 'true', 'yes')
TRANSCRIPT_LANGS = ['ko', 'en']
LOOKBACK_HOURS   = 12
MAX_PER_CHANNEL  = 2      # 프록시 전까진 영상분석(느림) 부담 줄이려 축소
RETRY_MAX        = 4
RETRY_WINDOW_H   = 48     # 실패한 영상을 이 시간 안에서만 다시 붙든다(오래된 건 포기)
RETRY_PER_RUN    = 2      # 한 실행에서 재시도할 최대 건수 — 쿼터·시간 상한

# ── 소셜 발행(social/) — 2026-11-12. 본인 계정 전용 토큰. 비우면 해당 플랫폼 publish 만 실패하고 나머지는 정상.
THREADS_USER_ID = os.environ.get('THREADS_USER_ID', '')
THREADS_TOKEN   = os.environ.get('THREADS_TOKEN', '')
IG_USER_ID      = os.environ.get('IG_USER_ID', '')
IG_TOKEN        = os.environ.get('IG_TOKEN', '')
X_API_KEY       = os.environ.get('X_API_KEY', '')
X_API_SECRET    = os.environ.get('X_API_SECRET', '')
X_ACCESS_TOKEN  = os.environ.get('X_ACCESS_TOKEN', '')
X_ACCESS_SECRET = os.environ.get('X_ACCESS_SECRET', '')
