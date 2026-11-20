# -*- coding: utf-8 -*-
"""품질 채점 — 유튜브 요약(즉석·채널)과 13장 리포트를 같은 틀로 잰다.

    python quality.py yt              # 유튜브 요약 전체 채점 + 분포
    python quality.py yt --packet 8   # 정성 심사용 발췌 파일 생성(8건)
    python quality.py report          # 13장 리포트 전종목 채점
    python quality.py packet PLTR     # 한 종목 심사 패킷(사람이 O/X 찍을 것)
    python quality.py judge <패킷.md>  # 찍어서 돌려준 걸 읽어 **채점기를 채점**

## 설계 원칙

**기계가 잴 수 있는 것만 기계가 잰다.** 숫자가 들어갔는지, 제목을 그대로
베꼈는지, 타임스탬프가 영상 길이 안에 있는지 — 이런 건 코드로 셀 수 있고
매번 같은 값이 나와서 **추세 비교가 된다**. 반면 "이 요약이 핵심을 짚었는가"는
코드가 못 잰다. 그건 --packet 으로 원문을 뽑아 사람과 LLM 심사위원이 본다.

**LLM 에게 자기 점수를 묻지 않는다.** 자기가 만든 요약을 자기가 채점하면
후하게 준다. 정성 평가는 요약을 만든 모델(Gemini)이 아니라 **다른 쪽**이 한다.
그래서 이 파일은 채점에 Gemini 를 **한 번도 호출하지 않는다** — 하루 쿼터는
사용자 요청에 쓴다.

**점수는 사용자에게 안 나간다.** 내부 검증용이다(config.SHOW_QUALITY 참고).

## 깨지는 지점 (미리 적어둔다)

· 숫자 밀도는 숫자가 적은 게 정상인 영상(정성적 시황 토크)을 부당하게 깎는다.
  그래서 개별 점수로 합격/불합격을 가르지 말고 **같은 채널의 추세**로 볼 것.
· 제목 재탕 점수는 제목이 이미 핵심인 영상(“TSLA 3분기 실적 발표”)에서
  낮게 나올 수밖에 없다.
· 커버리지는 '요약이 언급한 마지막 t / 영상 길이'라 뒤가 잡담이면 낮게 나온다.
· 리포트 채점은 pagecheck 와 같은 한계를 물려받는다 — live 데이터 페이지는
  --live 없이는 확인 못 한다.
"""
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

QUALITY_LOG = ROOT / 'quality_log.json'
PACKET_DIR = ROOT / 'quality_packets'

_NUM = re.compile(r'\d')
_MEANINGFUL_NUM = re.compile(r'(\$\s?[\d,.]+|[\d,.]+\s?(?:%|원|달러|억|조|만|배|bp)|'
                             r'\b\d{1,3}(?:,\d{3})+\b|\b\d+\.\d+\b|\b\d{4}년|\bQ[1-4]\b)')
_STOP = frozenset('''그 이 저 것 수 등 및 더 좀 왜 어떻게 관련 대한 위한 통해 있다 없다 한다 된다
the a an of for to in on and or is are was were this that with from as by at'''.split())


def _tok(s: str) -> set:
    s = re.sub(r'[^0-9a-z가-힣 ]+', ' ', (s or '').lower())
    return {w for w in s.split() if len(w) > 1 and w not in _STOP}


def _pct(n, d):
    return 0.0 if not d else round(n / d, 3)


_US_MAP = None

# SEC 회사 목록에 없는 게 **정상**인 식별자들 — 지수·통화·원자재·암호화폐.
# 2026-09-17 실측에서 32종이 '없는 심볼'로 잡혔는데 절반이 이 부류였다.
# 이걸 안 빼면 정상 태그를 오류로 세어 지표가 거짓말을 한다.
_NOT_A_COMPANY = frozenset('''KOSPI KOSDAQ SPX IXIC DJI SOX VIX
USDJPY JPY USD EUR KRW XAU XAG WTI BRENT
BTC ETH SOL ARB ONDO'''.split())
# 국가·일반명사를 티커 자리에 넣은 것 — 눌러도 아무 데도 안 가는 **진짜 오류**.
_NOT_A_TICKER = frozenset('''US CN KR JP EU LP ETF REIT'''.split())


def _us_ticker_known(sym: str):
    """미국 심볼이 SEC 등록 목록에 있는지. 목록을 못 읽으면 None(모름)."""
    global _US_MAP
    if _US_MAP is None:
        try:
            import ir
            _US_MAP = set(ir._cik_map())
        except Exception as e:
            print(f'[티커 목록 없음 — 검사 생략] {e}')
            _US_MAP = set()
    if not _US_MAP:
        return None
    return sym in _US_MAP


# 단일 기업 거래로는 비현실적인 선. 국가예산·전체 시장규모 얘기엔 오탐이 나므로
# 감점이 아니라 사람이 볼 플래그로만 쓴다.
_AMT_USD = re.compile(r'([\d,]+(?:\.\d+)?)\s*(억|조)\s*달러')
_AMT_KRW = re.compile(r'([\d,]+(?:\.\d+)?)\s*조\s*원')
_USD_LIMIT_BN = 300      # $300B 초과
_KRW_LIMIT_TRN = 400     # 400조원 초과


def _implausible_amount(s: str) -> bool:
    for mm in _AMT_USD.finditer(s or ''):
        try:
            v = float(mm.group(1).replace(',', ''))
        except ValueError:
            continue
        bn = v * (1000 if mm.group(2) == '조' else 0.1)   # 1억달러=$0.1B, 1조달러=$1,000B
        if bn > _USD_LIMIT_BN:
            return True
    for mm in _AMT_KRW.finditer(s or ''):
        try:
            if float(mm.group(1).replace(',', '')) > _KRW_LIMIT_TRN:
                return True
        except ValueError:
            continue
    return False


# ── 유튜브 요약 채점 ──────────────────────────────────────────────────
def score_yt(row: dict) -> dict:
    """한 건의 유튜브 요약 → 지표 dict. 네트워크·LLM 0회."""
    a = row.get('analysis') or {}
    title = row.get('title') or ''
    summary = [s for s in (a.get('summary') or []) if isinstance(s, str)]
    kps = [k.get('point', '') for k in (a.get('key_points') or []) if isinstance(k, dict)]
    body = summary + kps
    m = {'video_id': row.get('video_id'), 'title': title[:60],
         'source': row.get('source') or '', 'n_summary': len(summary), 'n_key': len(kps)}

    # ① 숫자 밀도 — "긍정적으로 전망"이 아니라 "목표가 $45(+30%)"인가.
    with_num = sum(1 for b in body if _MEANINGFUL_NUM.search(b))
    m['num_density'] = _pct(with_num, len(body))

    # ② 제목 재탕 — 사용자는 제목을 이미 봤다. 겹칠수록 정보량이 없다.
    tt = _tok(title)
    if tt and summary:
        ov = [len(_tok(s) & tt) / max(len(_tok(s)), 1) for s in summary]
        m['title_echo'] = round(statistics.mean(ov), 3)
    else:
        m['title_echo'] = 0.0

    # ③ 커버리지 — 영상의 어디까지 다뤘나(analyze()가 이미 계산해 둔 값).
    cov = a.get('_coverage')
    m['coverage'] = cov if isinstance(cov, (int, float)) else None

    # ④ 타임스탬프 유효성 — t 가 있고 0 이상이며 전 구간에 퍼졌는가.
    ts = [k.get('t') for k in (a.get('key_points') or []) if isinstance(k, dict)]
    ts = [t for t in ts if isinstance(t, (int, float)) and t >= 0]
    m['ts_ratio'] = _pct(len(ts), len(kps))
    m['ts_spread'] = round((max(ts) - min(ts)) / max(max(ts), 1), 3) if len(ts) >= 2 else None

    # ⑤ 발언/사실 구분 — 2026-09-17 프롬프트 규칙의 준수율.
    #    출연자 주장을 사실처럼 적으면 사용자가 그걸 근거로 매매한다.
    # 2026-10-03: 접두사('발언: ')에서 구조 필드(kind)로 바꿨다. 접두사 방식은
    # 규칙 문장을 아무리 더해도 20%에서 안 움직였다 — 모델이 내용이 아니라
    # 원문 말투에 반응했기 때문이다. 옛 레코드는 접두사로 폴백해 집계가 끊기지 않게 한다.
    kinds = [k.get('kind') for k in (a.get('key_points') or []) if isinstance(k, dict)]
    labeled = sum(1 for k in kinds if k in ('fact', 'claim'))
    if labeled:
        m['claim_tagged'] = _pct(labeled, len(kinds))
        m['claim_ratio'] = _pct(sum(1 for k in kinds if k == 'claim'), max(labeled, 1))
    else:
        m['claim_tagged'] = _pct(sum(1 for b in body if b.strip().startswith('발언')), len(body))
        m['claim_ratio'] = None

    # ⑥ 종목 근거 — view 를 긍정/부정으로 단정했으면 context 근거가 있어야 한다.
    tk = [t for t in (a.get('tickers') or []) if isinstance(t, dict)]
    opin = [t for t in tk if t.get('view') in ('긍정', '부정')]
    m['n_tickers'] = len(tk)
    m['view_grounded'] = _pct(sum(1 for t in opin if len(str(t.get('context') or '')) >= 8), len(opin))

    # ⑦ 종목 코드 유효성 — 태그를 누르면 엉뚱한 회사로 가는 걸 막는다.
    #    2026-09-17 심사에서 CXMT(중국 비상장 추정)에 '688072' 가 붙어 있었다.
    #    미국 심볼은 SEC 목록으로 실제 확인하고, 한국은 6자리 형식만 본다.
    #    ⚠️ 중국·일본 등은 확인할 목록이 없어 '모름'으로 둔다 — 없는 걸 틀렸다고
    #       하면 정상 태그가 감점된다.
    coded = [t for t in tk if str(t.get('ticker') or '').strip()]
    bad_code, unknown_code = 0, 0
    for t in coded:
        c = str(t['ticker']).strip().upper()
        if re.fullmatch(r'\d{6}', c):
            continue                      # 한국 — 형식만 확인
        elif c in _NOT_A_TICKER:
            bad_code += 1                 # 'US'(미국), 'CN'(중국) 같은 국가명
        elif c in _NOT_A_COMPANY:
            continue                      # 지수·통화·암호화폐 — 회사 목록에 없는 게 정상
        elif re.fullmatch(r'[A-Z][A-Z.\-]{0,9}', c):
            if _us_ticker_known(c) is False:
                # ETF 는 SEC 회사목록에 없어 여기 걸린다(SOXX·SMH 등). 회사명으로
                # 태그된 건 진짜 오류(TSMC→실제 ADR 은 TSM)라 사람이 봐야 한다.
                bad_code += 1
        else:
            unknown_code += 1
    m['n_coded'] = len(coded)
    m['bad_ticker'] = bad_code
    m['unknown_ticker'] = unknown_code

    # ⑧ 금액 이상치 — 숫자가 있다고 좋은 게 아니다. **틀린 숫자가 더 나쁘다.**
    #    실제 사례: "엔비디아와 5년간 7,000억 달러(약 1024조원) 규모 HBM 공급"
    #    — 엔비디아 연매출의 몇 배다. 영상 발언의 과장이든 받아쓰기 오류든
    #    그대로 통과시키면 사용자가 그걸 근거로 매매한다.
    #    ⚠️ 임계값은 '단일 기업 거래로는 비현실적'인 선이고 국가예산·시장규모
    #       얘기엔 오탐이 난다. 그래서 감점이 아니라 **플래그**로만 쓴다.
    ctx = [str(t.get('context') or '') for t in tk]
    m['magnitude_flags'] = sum(1 for s in body + ctx if _implausible_amount(s))

    # ⑨ 서식 — 렌더 전에 깨질 요소.
    joined = '\n'.join(body)
    m['fmt_issues'] = sum([
        bool(re.search(r'\\n|\\t', joined)),          # 이스케이프가 문자로 남음
        bool(re.search(r'<(?!/?(b|i|a|code)\b)[a-z]', joined)),  # 허용 밖 HTML 태그
        any(len(b) > 200 for b in body),              # 한 줄이 너무 긺
        bool(a.get('_parse_error')),
    ])
    m['empty'] = not body
    return m


YT_WEIGHTS = {'num_density': .25, 'coverage': .25, 'ts_ratio': .15,
              'view_grounded': .15, 'claim_tagged': .10, 'title_echo': -.10}


def yt_total(m: dict):
    """0~100. 재는 항목이 하나도 없으면 None — 0점과 구분한다."""
    if m.get('empty'):
        return 0.0
    got, tot = 0.0, 0.0
    for k, w in YT_WEIGHTS.items():
        v = m.get(k)
        if v is None:
            continue
        tot += abs(w)
        got += (1 - v) * abs(w) if w < 0 else v * w
    if not tot:
        return None
    base = 100 * got / tot
    return round(max(0.0, base - 5 * m.get('fmt_issues', 0)), 1)


# ── 13장 리포트 채점 ─────────────────────────────────────────────────
def score_report(ticker: str, live: bool = False) -> dict:
    sys.path.insert(0, str(ROOT / 'decks'))
    import pagecheck
    res = pagecheck.check_ticker(ticker, live=live)
    m = {'ticker': ticker}
    if '_error' in res:
        return {**m, 'error': res['_error'], 'pages_clean': 0, 'blocks': 0, 'warns': 0}
    blocks = warns = infos = unverified = 0
    for code, _label, kind in pagecheck.PAGES:
        rows = res.get(code) or []
        blocks += sum(1 for lv, _ in rows if lv == pagecheck.BLOCK)
        warns += sum(1 for lv, _ in rows if lv == pagecheck.WARN)
        infos += sum(1 for lv, _ in rows if lv == pagecheck.INFO)
        if not rows and kind == 'live' and not live:
            unverified += 1
    n = len(pagecheck.PAGES)
    m.update({'blocks': blocks, 'warns': warns, 'infos': infos,
              'pages': n, 'unverified': unverified,
              'pages_clean': sum(1 for c, _l, _k in pagecheck.PAGES if not res.get(c))})
    return m


def report_total(m: dict):
    if m.get('error'):
        return 0.0
    # 차단은 그 장을 못 쓰게 만들고, 경고는 장을 헐겁게 만든다 — 가중치를 다르게.
    #
    # 안 본 장도 깎는다. 예전에는 unverified 를 세어만 놓고 점수에 안 썼다.
    # 그래서 --live 없이 돌려 6장을 아예 안 본 덱이 13장 다 본 덱과 **똑같이
    # 93.0점**이 나왔다. 안 본 것은 깨끗한 게 아니라 모르는 것이고, 모르는 채로
    # 93점이 찍히면 그 점수를 믿고 발행하게 된다. 경고와 같은 무게로 깎는다.
    penalty = (12 * m.get('blocks', 0) + 4 * m.get('warns', 0)
               + 1 * m.get('infos', 0) + 4 * m.get('unverified', 0))
    return round(max(0.0, 100 - penalty), 1)


# ── 기록 ─────────────────────────────────────────────────────────────
def record(kind: str, rows: list, note: str = ''):
    """채점 결과를 누적 저장한다. 한 번의 점수보다 **추세**가 중요하다."""
    log = []
    if QUALITY_LOG.exists():
        try:
            log = json.loads(QUALITY_LOG.read_text(encoding='utf-8')) or []
        except Exception:
            pass
    scores = [r['score'] for r in rows if r.get('score') is not None]
    log.append({'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'kind': kind, 'n': len(rows), 'note': note,
                'mean': round(statistics.mean(scores), 1) if scores else None,
                'median': round(statistics.median(scores), 1) if scores else None,
                'p10': round(sorted(scores)[len(scores) // 10], 1) if len(scores) >= 10 else None,
                'rows': rows})
    QUALITY_LOG.write_text(json.dumps(log[-60:], ensure_ascii=False, indent=1), encoding='utf-8')
    return log


def trend(kind: str, n: int = 5):
    if not QUALITY_LOG.exists():
        return []
    try:
        log = json.loads(QUALITY_LOG.read_text(encoding='utf-8')) or []
    except Exception:
        return []
    return [e for e in log if e.get('kind') == kind][-n:]


# ── 채점기를 채점한다 ────────────────────────────────────────────────
#
# 여기까지의 점수는 전부 **내가 정한 31개 규칙**으로 내가 매긴 것이다. 규칙도
# 내가 고르고, 깎는 폭(12/4/1/4)도 내가 정했고, 2026-10-10 에는 그 폭 하나를
# 내가 바꿨다. 시험도 내가 내고 채점도 내가 하는 구조다.
#
# 그래서 93점이 뜻하는 건 딱 이것뿐이다 — "내가 생각해낸 항목 중엔 걸린 게
# 없다". 내가 생각 못 한 오류는 점수에 나타나지 않는다. 실제로 '안 본 장을
# 깨끗한 것으로 세는' 구멍이 두 달 있었는데 그동안 점수는 계속 93 이었다.
#
# 이 구간은 그 고리를 끊는다. 정답지를 **내가 아닌 두 곳**에서 가져온다.
#   ① 공시 원문 — 숫자가 원문에 실제로 있는지. 내 판단이 아니라 원문이 정답.
#   ② 사람 — 원문 구절을 나란히 놓고 O/X 만 찍게 한다.
# 그 O/X 가 쌓이면 **내 자동 판정이 사람 판정과 몇 % 일치하는지**가 나오고,
# 그게 채점기의 점수다. 불일치가 난 항목이 곧 규칙을 고칠 자리다.

VERDICT_LOG = ROOT / 'judge_log.json'
_CTX = 130               # 원문에서 앞뒤로 보여줄 글자 수


def _norm_num(s: str) -> str:
    return re.sub(r'[,\s$]', '', str(s))


_SCALE = {'B': 1e9, 'M': 1e6, 'K': 1e3, '': 1.0}
_TOKEN = re.compile(r'\d[\d,]*(?:\.\d+)?')
_TOL = 0.005             # 0.5% 안이면 같은 숫자로 본다(공시 원값 vs 리포트 반올림)


def _abs_value(value):
    """'$1.94B' → 1.94e9. 못 읽으면 None."""
    raw = _norm_num(value)
    m = re.search(r'-?\d+(?:\.\d+)?', raw)
    if not m:
        return None
    unit = raw[m.end():][:1].upper()
    try:
        return float(m.group()) * _SCALE.get(unit if unit in _SCALE else '', 1.0)
    except ValueError:
        return None


# 재무제표는 비슷한 크기의 숫자가 줄줄이 붙어 있어서 값만으로는 못 가린다.
# 실측: 순이익 $1.06B 로 찾으면 바로 윗줄 'Comprehensive income 1,058,258' 이
# 더 가까워서 그걸 집었고, 매출 $1.94B 는 6개월 누적 순이익 1,942,364 를
# 집었다. 둘 다 그럴듯해 보이는 오답이라 사람이 그냥 O 를 찍게 된다.
# 그래서 숫자 앞의 **항목 이름**을 같이 본다.
_LABEL_EN = {
    '매출': ('revenue', 'net sales'),
    '영업이익': ('income from operations', 'operating income', 'loss from operations'),
    '영업손실': ('loss from operations',),
    '순이익': ('net income', 'net loss'),
    '순손실': ('net loss',),
    '영업현금': ('operating activities',),
    '현금': ('cash and cash equivalents',),
    '임직원': ('employees',),
    '수주': ('remaining performance obligations', 'backlog'),
    '총매출': ('revenue',),
}


def _label_words(label: str) -> tuple:
    out = []
    for ko, ens in _LABEL_EN.items():
        if ko in str(label):
            out.extend(ens)
    return tuple(out)


def _ground(text: str, value, label: str = '') -> str:
    """원문에서 **그 값과 같은 숫자**가 나오는 구절을 떠온다. 없으면 빈 문자열.

    문자열로 찾으면 안 된다. 리포트는 반올림해서 '$1.94B' 로 적고 공시 원값은
    '1,935,886'(천 단위) 이라 자릿수가 아예 안 맞는다. 짧은 조각('194')으로
    찾으면 대차대조표 아무 데나 걸리는데, **틀린 인용은 없는 것보다 나쁘다** —
    근거처럼 보이는데 근거가 아니라서 사람이 O 를 찍게 만든다.

    그래서 숫자를 값으로 비교한다. 공시 표는 단위가 천·백만으로 섞여 있어
    세 배율을 다 시도하고, 0.5% 안에 드는 것만 같은 숫자로 본다. 여러 개가
    맞으면 **자릿수가 가장 많은 것**을 고른다(구체적일수록 그 숫자가 맞다).
    """
    want = _abs_value(value)
    if not text or want is None or want == 0:
        return ''
    flat = re.sub(r'\s+', ' ', text)
    words = _label_words(label)
    best = None
    for m in _TOKEN.finditer(flat):
        tok = m.group()
        digits = re.sub(r'[^\d]', '', tok)
        if len(digits) < 3:          # 두 자리 이하는 우연히 맞는다
            continue
        try:
            n = float(tok.replace(',', ''))
        except ValueError:
            continue
        for mult in (1e3, 1.0, 1e6):     # 공시 표 단위: 천 → 원 → 백만 순
            v = n * mult
            if v == 0:
                continue
            # 배율이 클수록 짧은 숫자가 우연히 맞는다. 실측: 영업현금흐름
            # $899.2M 을 찾는데 환산조정 '( 895 )' 가 895×1e6 으로 0.47% 안에
            # 들어와 그걸 집었다. 큰 배율엔 자릿수를 더 요구한다.
            if mult >= 1e6 and len(digits) < 4:
                continue
            if abs(v - want) / abs(want) <= _TOL:
                # 숫자 바로 앞 80자에 그 항목의 영문 이름이 있으면 우선한다.
                near = flat[max(0, m.start() - 80):m.start()].lower()
                hit = 1 if any(w in near for w in words) else 0
                rank = (hit, len(digits), -abs(v - want))
                if best is None or rank > best[0]:
                    best = (rank, m.start(), m.end())
                break
    if best is None:
        return ''
    # 그 항목의 영문 이름을 **알고 있는데** 숫자 옆에서 못 찾았으면 증거로
    # 내놓지 않는다. 숫자만 맞은 구절은 그럴듯해 보이는 오답이고, 사람은
    # 그걸 보고 O 를 찍는다. 근거가 약할 땐 '못 찾음'이 정직하다.
    if words and not best[0][0]:
        return ''
    _, s, e = best
    a, b = max(0, s - _CTX), min(len(flat), e + _CTX)
    return ('…' if a else '') + flat[a:b].strip() + ('…' if b < len(flat) else '')


def _claims(mod) -> list:
    """리포트에서 **원문과 대조 가능한 주장**만 뽑는다.

    서술형 해석(INCOME_NOTE 등)은 넣지 않는다 — 맞다/틀리다로 못 자르는 걸
    O/X 로 받으면 판정이 사람마다 달라져 일치율이 의미를 잃는다. 여기서
    재려는 건 '내 채점기가 틀린 숫자를 잡아내는가' 하나다.
    """
    g = lambda p, d=None: _dig(mod, p, d)
    out = []
    for kp in (g('RESULTS.kpis', []) or []):
        if len(kp) >= 3:
            out.append({'kind': 'KPI', 'label': str(kp[0]),
                        'claim': f'{kp[1]} ({kp[2]})', 'value': kp[1]})
    for f in (g('RESULTS.facts', []) or []):
        if len(f) >= 3:
            out.append({'kind': '실적', 'label': str(f[0]),
                        'claim': f'{f[2]} — {f[1]}', 'value': f[2]})
    for s in (g('SEGMENTS.by_line', []) or []):
        if len(s) >= 3:
            out.append({'kind': '부문', 'label': str(s[0]),
                        'claim': f'${s[1]}M · 비중 {s[2]}%', 'value': s[1]})
    for d, n in (g('HISTORY.employees', []) or []):
        out.append({'kind': '임직원', 'label': str(d),
                    'claim': f'{n:,}명', 'value': n})
    ceo = g('LEADERSHIP.ceo', {}) or {}
    if ceo.get('bio'):
        out.append({'kind': 'CEO약력', 'label': str(ceo.get('name', '')),
                    'claim': str(ceo['bio']), 'value': None})
    return out


def _dig(mod, path, default=None):
    cur = mod
    for part in path.split('.'):
        cur = getattr(cur, part, None) if not isinstance(cur, dict) else cur.get(part)
        if cur is None:
            return default
    return cur


def packet_report(ticker: str, live: bool = False) -> Path:
    """한 종목의 심사 패킷을 만든다. Gemini 0콜, EDGAR 만 읽는다."""
    import importlib
    sys.path.insert(0, str(ROOT / 'decks'))
    import check, ir
    mod = check.module_for(ticker)
    if mod is None:
        raise SystemExit(f'{ticker}: 데이터 파일 없음')
    importlib.reload(mod)

    m = score_report(ticker, live=live)
    auto = report_total(m)

    src_text, src_label, src_url = '', '', ''
    try:
        cik, company = ir.resolve_ticker(ticker)
        hist = ir.filing_history(cik, limit=24)
        filing = next((f for f in hist if ir._is_earnings_form(f)), None) or (hist[0] if hist else None)
        if filing:
            src_text = ir.filing_text(cik, filing) or ''
            src_label = f"{filing.get('form', '')} ({filing.get('filingDate', '')})"
            src_url = ir.filing_url(ticker, filing)
    except Exception as e:
        src_label = f'(공시 본문 조회 실패: {type(e).__name__})'

    rows = _claims(mod)
    PACKET_DIR.mkdir(exist_ok=True)
    out = PACKET_DIR / f'report_{ticker.lower()}_{datetime.now().strftime("%Y%m%d_%H%M")}.md'
    L = [f'# {ticker} 리포트 심사 — {datetime.now():%Y-%m-%d}', '',
         f'제 자동 점수는 **{auto}점**입니다(차단 {m.get("blocks", 0)} · '
         f'경고 {m.get("warns", 0)} · 참고 {m.get("infos", 0)}).',
         '그 점수가 맞는지 **당신이 채점해 주세요.**', '',
         '각 항목 맨 아래 `판정:` 뒤에 **O**(맞음) / **X**(틀림) / **?**(모르겠음) 중 하나만 적으면 됩니다.',
         '', f'원문은 제가 공시에서 그대로 떠온 것입니다 — {src_label}',
         (f'<{src_url}>' if src_url else ''),
         '**제 주장과 원문이 다르면 X 입니다.** 원문이 안 붙은 항목은 제가 공시에서',
         '못 찾았다는 뜻이고, 그 자체로 의심스러운 항목입니다.', '', '---', '']
    for i, c in enumerate(rows, 1):
        numeric = c['value'] is not None
        quote = _ground(src_text, c['value'], c['label']) if numeric else ''
        if quote:
            found = f"- **공시 원문**: …{quote}"
        elif numeric:
            found = ('- **공시 원문**: ⚠️ 이 숫자를 공시 본문에서 못 찾았습니다 '
                     '— 다른 공시(10-K·8-K)나 보도자료에 있을 수도, 틀린 숫자일 수도 있습니다')
        else:
            found = ('- **공시 원문**: (숫자가 아니라 서술이라 자동 대조를 못 합니다 '
                     '— 위임장/10-K 원문과 직접 비교해 주세요)')
        L += [f"## {i}. [{c['kind']}] {c['label']}",
              f"- **리포트 주장**: {c['claim']}",
              found,
              f"- 제 자동판정: {'통과' if m.get('blocks', 0) == 0 else '차단 있음'}"
              f" (규칙 31개 중 이 항목을 직접 보는 규칙 없음)",
              '', '판정: ', '', '---', '']
    L += ['## 다 찍으셨으면', '', '```bash',
          f'python quality.py judge {out.as_posix()}', '```', '',
          '그러면 제 자동판정이 당신 판정과 몇 % 일치하는지 계산해서',
          '`judge_log.json` 에 쌓습니다. 불일치가 난 항목이 제 채점 규칙을',
          '고쳐야 할 자리입니다.', '']
    out.write_text('\n'.join(L), encoding='utf-8')
    return out


def read_verdicts(path) -> dict:
    """사람이 찍어 돌려준 패킷을 읽는다."""
    p = Path(path)
    txt = p.read_text(encoding='utf-8')
    tk = re.search(r'^# (\S+) 리포트 심사', txt, re.M)
    items, cur = [], None
    for ln in txt.splitlines():
        h = re.match(r'^## (\d+)\. \[([^\]]+)\] (.*)$', ln)
        if h:
            cur = {'no': int(h.group(1)), 'kind': h.group(2), 'label': h.group(3).strip(),
                   'grounded': None, 'verdict': ''}
            items.append(cur)
        elif cur is not None and ln.startswith('- **공시 원문**'):
            cur['grounded'] = ('못 찾았습니다' not in ln) and ('자동 대조를 못' not in ln)
        elif cur is not None and ln.startswith('판정:'):
            v = ln.split(':', 1)[1].strip().upper()
            cur['verdict'] = v[:1] if v[:1] in ('O', 'X', '?') else ''
    marked = [i for i in items if i['verdict'] in ('O', 'X')]
    bad = [i for i in marked if i['verdict'] == 'X']
    # 내 자동판정은 '차단 0 = 전부 통과'였다. 사람이 X 를 찍은 항목은
    # 전부 내가 놓친 것이다 — 그게 채점기의 실제 구멍 크기다.
    return {'ticker': tk.group(1) if tk else p.stem, 'file': p.name,
            'items': len(items), 'marked': len(marked), 'wrong': len(bad),
            'missed': [f"{i['kind']}/{i['label']}" for i in bad],
            'agreement': round(_pct(len(marked) - len(bad), len(marked)), 3)
            if marked else None,
            'ungrounded_and_wrong': sum(1 for i in bad if i['grounded'] is False)}


def judge(path):
    r = read_verdicts(path)
    print(f"\n── {r['ticker']} 채점기 채점 ────────────────────────────")
    if not r['marked']:
        print('  판정이 하나도 안 찍혀 있습니다 — `판정:` 뒤에 O/X 를 적어 주세요.')
        return r
    print(f"  항목 {r['items']}개 중 {r['marked']}개 채점 · 당신이 X 준 것 {r['wrong']}개")
    print(f"  → 내 자동판정과 일치 {r['agreement']}")
    if r['wrong']:
        print(f"  내가 놓친 것: {', '.join(r['missed'][:6])}")
        print(f"  그중 공시 원문에서도 못 찾았던 것: {r['ungrounded_and_wrong']}개"
              f"  ← 여기부터 규칙을 만들면 된다")
    log = []
    if VERDICT_LOG.exists():
        try:
            log = json.loads(VERDICT_LOG.read_text(encoding='utf-8')) or []
        except Exception:
            log = []
    log.append({'at': datetime.now(timezone.utc).isoformat(), **r})
    VERDICT_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f"  기록: {VERDICT_LOG.name} ({len(log)}건)")
    return r


# ── 정성 심사용 발췌 ─────────────────────────────────────────────────
def packet_yt(rows: list, k: int = 8) -> Path:
    """점수 분포에서 **골고루** 뽑는다 — 최악만 보면 평균이 안 보이고,
    무작위로 뽑으면 드문 실패를 놓친다. 하위/중위/상위를 섞는다."""
    got = [r for r in rows if r.get('score') is not None]
    got.sort(key=lambda r: r['score'])
    if not got:
        pick = rows[:k]
    else:
        idx = sorted({round(i * (len(got) - 1) / max(k - 1, 1)) for i in range(k)})
        pick = [got[i] for i in idx]
    PACKET_DIR.mkdir(exist_ok=True)
    out = PACKET_DIR / f'yt_{datetime.now().strftime("%Y%m%d_%H%M")}.md'
    L = ['# 유튜브 요약 정성 심사 패킷', '',
         '기계 점수는 참고만 하고, **아래 질문에만** 답해 주세요.', '',
         '1. 이 요약만 읽고 영상의 핵심을 알 수 있나? (아니면 뭐가 빠졌나)',
         '2. 사실이 아닌 주장이 사실처럼 적힌 곳이 있나?',
         '3. 제목만 봐도 아는 내용을 되풀이한 항목이 있나?',
         '4. 투자 판단에 쓸 수 있는 구체성이 있나? (숫자·기한·조건)',
         '', '---', '']
    for r in pick:
        m = r['metrics']
        L += [f"## {m.get('title')}  ({m.get('video_id')})",
              f"- 기계점수 **{r['score']}** · 근거={m.get('source')} · "
              f"커버리지={m.get('coverage')} · 숫자밀도={m.get('num_density')} · "
              f"제목재탕={m.get('title_echo')}",
              f"- 링크: https://www.youtube.com/watch?v={m.get('video_id')}", '']
        a = r.get('analysis') or {}
        if a.get('one_liner'):
            L.append(f"**한 줄**: {a['one_liner']}")
        for s in (a.get('summary') or []):
            L.append(f"- {s}")
        for kp in (a.get('key_points') or []):
            if isinstance(kp, dict):
                L.append(f"- [{kp.get('t')}s] {kp.get('point')}")
        for t in (a.get('tickers') or []):
            if isinstance(t, dict):
                L.append(f"- 종목 {t.get('name')}({t.get('ticker')}) {t.get('view')} — {t.get('context')}")
        L += ['', '**심사 의견:** _(여기에)_', '', '---', '']
    out.write_text('\n'.join(L), encoding='utf-8')
    return out


# ── CLI ──────────────────────────────────────────────────────────────
def run_yt(packet: int = 0):
    import db
    rows_raw = db.unfinished_analyses()
    rows = []
    for r in rows_raw:
        a = r.get('analysis') or {}
        if not (a.get('summary') or a.get('key_points')):
            continue
        m = score_yt(r)
        rows.append({'video_id': m['video_id'], 'score': yt_total(m),
                     'metrics': m, 'analysis': a})
    scores = [r['score'] for r in rows if r['score'] is not None]
    print(f'유튜브 요약 채점 — {len(rows)}건 (LLM 호출 0회)')
    if scores:
        scores.sort()
        print(f'  평균 {statistics.mean(scores):.1f} · 중앙 {statistics.median(scores):.1f} · '
              f'하위10% {scores[len(scores)//10]:.1f} · 최저 {scores[0]:.1f} · 최고 {scores[-1]:.1f}')
    for key in ('num_density', 'coverage', 'ts_ratio', 'view_grounded', 'claim_tagged', 'title_echo'):
        vals = [r['metrics'][key] for r in rows if r['metrics'].get(key) is not None]
        if vals:
            print(f'  {key:<14} 평균 {statistics.mean(vals):.3f}  (측정 {len(vals)}건)')
    from collections import Counter
    print('  경로 분포:', dict(Counter(r['metrics']['source'] for r in rows)))
    bad = sum(1 for r in rows if r['metrics'].get('fmt_issues'))
    print(f'  서식 문제: {bad}건')
    # 아래 둘은 점수에 안 넣는다 — 오탐이 나는 성격이라 **사람이 볼 목록**으로만 낸다.
    mag = [r for r in rows if r['metrics'].get('magnitude_flags')]
    badt = [r for r in rows if r['metrics'].get('bad_ticker')]
    print(f'\n  ⚠️ 금액 이상치 {len(mag)}건 · 없는 미국 심볼 {len(badt)}건 (점수 미반영, 확인 필요)')
    for r in mag[:6]:
        print(f"     · {r['metrics']['title'][:44]}  ({r['video_id']})")
    for r in badt[:6]:
        print(f"     · [심볼] {r['metrics']['title'][:38]}  ({r['video_id']})")
    record('yt', [{'video_id': r['video_id'], 'score': r['score'], 'metrics': r['metrics']}
                  for r in rows])
    if packet:
        print(f'\n정성 심사 패킷: {packet_yt(rows, packet)}')
    return rows


def run_report(live: bool = False, packet: int = 0):
    sys.path.insert(0, str(ROOT / 'decks'))
    import check
    tickers = check._all_tickers()
    rows = []
    for t in tickers:
        m = score_report(t, live=live)
        rows.append({'ticker': t, 'score': report_total(m), 'metrics': m})
    scores = sorted(r['score'] for r in rows)
    print(f'13장 리포트 채점 — {len(rows)}종목' + ('' if live else ' (live 페이지 미검증)'))
    print(f'  평균 {statistics.mean(scores):.1f} · 중앙 {statistics.median(scores):.1f} · 최저 {scores[0]:.1f}')
    for r in sorted(rows, key=lambda x: x['score'])[:8]:
        m = r['metrics']
        print(f"  {r['ticker']:<10} {r['score']:>5}  차단{m.get('blocks',0)} 경고{m.get('warns',0)} "
              f"참고{m.get('infos',0)}" + (f"  미검증 {m['unverified']}장" if m.get('unverified') else ''))
    record('report', rows, note='live' if live else 'module-only')
    if packet:
        # 예전엔 이 인자를 받기만 하고 **함수 안에서 아무것도 안 했다**.
        # `--packet 3` 을 쳐도 조용히 아무 일도 안 일어났고, 그래서 내 점수를
        # 바깥에서 검증할 유일한 통로가 막혀 있었다. 점수가 낮은 종목부터 뽑는다.
        for r in sorted(rows, key=lambda x: x['score'])[:packet]:
            print(f"  심사 패킷: {packet_report(r['ticker'], live=live)}")
    return rows


if __name__ == '__main__':
    args = sys.argv[1:]
    kind = args[0] if args else 'yt'
    n = 0
    if '--packet' in args:
        i = args.index('--packet')
        n = int(args[i + 1]) if len(args) > i + 1 and args[i + 1].isdigit() else 8
    if kind == 'judge':
        if len(args) < 2:
            sys.exit('사용법: python quality.py judge <채점한_패킷.md>')
        judge(args[1])
    elif kind == 'packet':
        if len(args) < 2:
            sys.exit('사용법: python quality.py packet TICKER [--live]')
        print(f'심사 패킷: {packet_report(args[1].upper(), live="--live" in args)}')
    elif kind == 'report':
        run_report(live='--live' in args, packet=n)
    else:
        run_yt(packet=n)
