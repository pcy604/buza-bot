# -*- coding: utf-8 -*-
"""발행 전 품질 게이트 — 렌더된 덱을 사람이 12장 훑는 일을 대신한다.

    python check.py PLTR          # 데이터 파일만 검사
    python build.py PLTR          # 렌더 후 자동 실행(build.py가 호출)

왜 필요한가: 지금까지의 반복 패턴은 항상 같았다 — 새 종목을 뽑고, 12장을 눈으로 훑고,
"0년 창업", "경영진 명단 없음", "TAM 없음", "N 항목 전부 0점" 같은 걸 발견해서 지적하고,
고치고, 다음 종목에서 똑같은 걸 또 발견한다. 사람이 발견해야만 알 수 있는 구조가
문제라서, 발행 전에 기계가 먼저 훑고 목록을 내놓게 한다.

판정
  BLOCK  이대로 SNS에 올리면 안 되는 것(빈 페이지·자리표시자 문구가 그대로 노출·거짓 숫자)
  WARN   올려도 되지만 품질이 떨어지는 것(있으면 좋은데 비어 있음)
  INFO   정직하게 비운 것(추측 금지 원칙상 정상 — 확인만)
"""
import importlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 발행 전 게이트가 정작 로컬(Windows 콘솔=cp949)에서 '—' 하나 때문에
# UnicodeEncodeError 로 죽어 있었다. 러너는 UTF-8 이라 통과해서 안 보였다.
# pagecheck 는 이미 같은 방어를 하고 있었고, check 를 임포트하는
# crosscheck·pagecheck 도 이 한 줄로 같이 산다.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

BLOCK, WARN, INFO = 'BLOCK', 'WARN', 'INFO'

# 검수 전 자리표시자가 그대로 카드에 찍히면 즉시 티가 난다 — 이 문구들이 렌더되는
# 필드에 남아 있으면 발행 차단.
_PLACEHOLDER = ('[자동생성]', '확인 필요', '확인필요', '채워넣기 필요', '(CEO 성명',
                '리서치 필요', 'TODO', 'FIXME')

# 실제로 카드에 글자로 찍히는 필드만 검사한다(주석·src 등은 제외).
_RENDERED_TEXT = [
    'HISTORY.note', 'HISTORY.employee_src', 'LEADERSHIP.note', 'LEADERSHIP.rsu_note',
    'LEADERSHIP.ceo.bio', 'SEGMENTS.note', 'SHARES.note', 'TAM.note', 'TAM.label',
    'CANSLIM_NOTE', 'INCOME_NOTE', 'BALANCE_NOTE', 'CASHFLOW.note', 'CHECKPOINT_NOTE',
    'SUMMARY',
]


def _get(mod, path, default=None):
    cur = getattr(mod, path.split('.')[0], None)
    for k in path.split('.')[1:]:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


def audit(mod, ticker=''):
    """데이터 모듈 하나를 검사해 [(등급, 항목, 설명), ...] 반환."""
    out = []

    def add(level, item, msg):
        out.append((level, item, msg))

    # ── 비전문가 기준: 이 회사가 뭐 하는 회사인지 ──────────────────────
    biz = [b for b in (_get(mod, 'BUSINESS', []) or []) if b]
    if len(biz) < 3:
        add(BLOCK, 'BUSINESS', f'표지 3줄(무엇을/누가/어떻게) 중 {len(biz)}줄만 있음 — '
                               '이 산업을 모르는 독자가 무슨 회사인지 알 방법이 없음')

    # ── 빈 페이지를 만드는 것들 ────────────────────────────────────────
    if not _get(mod, 'SUMMARY', ''):
        add(BLOCK, 'SUMMARY', '1p 종합평가가 통째로 빔')
    if not (_get(mod, 'RESULTS.kpis', []) or []):
        add(BLOCK, 'RESULTS.kpis', '2p 실적 KPI 타일이 통째로 빔')
    if not (_get(mod, 'RESULTS.facts', []) or []):
        add(WARN, 'RESULTS.facts', '2p 어닝콜 핵심 숫자 표가 빔')
    if not (_get(mod, 'CHECKPOINTS', []) or []):
        add(BLOCK, 'CHECKPOINTS', '1p 향후 체크포인트 타임라인이 빔')
    if not (_get(mod, 'HISTORY.timeline', []) or []):
        add(WARN, 'HISTORY.timeline', '3p 주요 연혁이 빔')
    if not (_get(mod, 'SEGMENTS.by_line', []) or []):
        add(WARN, 'SEGMENTS.by_line', '5p 부문별 매출 도넛이 빔(전사 총매출로만 표시됨)')

    # ── "0년" 계열: 렌더러가 방어는 하지만 정보가 비는 건 그대로 ────────
    ceo = _get(mod, 'LEADERSHIP.ceo', {}) or {}
    if str(ceo.get('name', '')).startswith('('):
        add(BLOCK, 'LEADERSHIP.ceo.name', 'CEO 실명을 못 뽑아 자리표시자가 그대로 남음')
    if not ceo.get('since'):
        add(WARN, 'LEADERSHIP.ceo.since', 'CEO 취임연도 미확인 — 4p에 재임기간이 안 나옴')
    if not ceo.get('bio'):
        add(WARN, 'LEADERSHIP.ceo.bio', 'CEO 약력이 빔 — 4p 프로필 박스가 헐거워짐')
    if not (_get(mod, 'LEADERSHIP.people', []) or []):
        add(WARN, 'LEADERSHIP.people', '주요 경영진 명단이 빔 — 4p 표가 통째로 생략됨')
    if not _get(mod, 'HISTORY.founded'):
        add(WARN, 'HISTORY.founded', '창업연도 미확인 — 3p "창업" 타일이 안 나옴')
    if not _get(mod, 'HISTORY.listed'):
        add(WARN, 'HISTORY.listed', '상장연도 미확인 — 3p "상장" 타일·상장후 CAGR이 안 나옴')
    if not _get(mod, 'COMPANY.exchange'):
        add(WARN, 'COMPANY.exchange', '거래소 미확인 — 3p 상장 타일에 빈칸으로 노출')

    # ── CANSLIM N: 전부 0이면 총점이 사실상 C+A뿐 ──────────────────────
    n = _get(mod, 'CANSLIM_N', {}) or {}
    scored = [k for k in ('top_tier', 'growth_years', 'governance') if n.get(k)]
    if not scored and not n.get('market_cagr'):
        add(WARN, 'CANSLIM_N', 'N 5개 항목이 전부 0/None — 7p 총점이 사실상 C+A뿐')
    detail = _get(mod, 'CANSLIM_N_DETAIL', {}) or {}
    missing_detail = [k for k, v in n.items()
                      if v and k != 'competitors' and not any(v2 for v2 in detail.values())]
    if n and detail == {}:
        add(WARN, 'CANSLIM_N_DETAIL', 'N 점수는 있는데 근거 문장이 없음 — 지어낸 점수와 구분 불가')

    # ── 정직하게 비운 것(정상) ─────────────────────────────────────────
    if not (_get(mod, 'TAM.estimates', []) or []):
        add(INFO, 'TAM.estimates', '시장규모 추정치 없음 — 뉴스 검색에서 숫자를 못 찾음(추측 금지 원칙)')
    if not (_get(mod, 'SEGMENTS.competitors', []) or []):
        add(INFO, 'SEGMENTS.competitors', '10-K가 경쟁사 이름을 구체적으로 안 듦 — 비교표 생략됨')
    for mv in (_get(mod, 'PRICE_MOVES', []) or []):
        if '미확인' in str(mv.get('reason', '')):
            add(INFO, 'PRICE_MOVES', f'{mv.get("period")} 구간 등락 이유를 뉴스에서 못 찾음')

    # ── 자리표시자 문구가 카드에 그대로 찍히는가 ───────────────────────
    for path in _RENDERED_TEXT:
        v = str(_get(mod, path, '') or '')
        hit = next((p for p in _PLACEHOLDER if p in v), None)
        if hit:
            add(BLOCK, path, f'검수용 문구 "{hit}"가 카드에 그대로 노출됨')

    # ── 금액 표기 규칙 위반 ────────────────────────────────────────────
    # 프로젝트 규칙은 "$X.XB / $X.XM" 고정인데 LLM이 종종 한국식 억/조 단위로 쓴다.
    # 단순한 표기 문제가 아니라 실제로 틀린 숫자가 된다 — PLTR 실측: 매출 $1.5B를
    # "1.5억 달러"로 씀($1.5B = 15억 달러). 같은 페이지의 표와 대놓고 안 맞음.
    for path in _RENDERED_TEXT:
        v = str(_get(mod, path, '') or '')
        # 2026-08-16: 예전 패턴은 단위가 하나만 붙은 경우(`1.5억 달러`)만 잡아서
        # SNDK의 `73억 5,500만 달러`($7.36B)가 그대로 빠져나갔다. 단위가 연달아
        # 붙는 한국식 표기 전체를 잡도록 넓힌다.
        m = re.search(r'\d[\d,.]*\s*(억|조|천만|백만)[\s\d,.억조만천백]*달러', v)
        if m:
            add(BLOCK, path, f'금액을 "{m.group(0)}"로 씀 — $X.XB/$X.XM 표기 규칙 위반이자 '
                             f'표의 숫자와 어긋남')

    # ── 신선도: 실적 발표 직후 캐시가 낡으면 같은 페이지 안에서 숫자가 어긋난다 ──
    # 신선도는 **초안을 언제 만들었나**로 재야 한다. 표지의 AS_OF는 2026-08-19부터
    # '반영한 최신 실적 공시일'이라 의미가 다르다 — 공시일로 재면 분기 중반엔 항상
    # 늙어 보이고, 초안이 오늘 것이어도 BLOCK이 난다. 옛 파일엔 BUILT_AT이 없으므로
    # AS_OF로 물러난다(그 파일들에선 AS_OF가 곧 초안 날짜였다).
    as_of = str(_get(mod, 'BUILT_AT', '') or _get(mod, 'AS_OF', '') or '')
    try:
        age = (datetime.now(timezone.utc).date() - datetime.strptime(as_of, '%Y-%m-%d').date()).days
        if age > 30:
            add(BLOCK, 'AS_OF', f'데이터가 {age}일 지남 — 실적이 한 번 이상 바뀌었을 수 있음. '
                                f'`python autogen.py {ticker}` 재생성 필요')
        elif age > 7:
            add(WARN, 'AS_OF', f'데이터가 {age}일 지남 — 재생성 권장')
    except ValueError:
        add(WARN, 'AS_OF', f'날짜 형식이 이상함: {as_of!r}')

    # 초안을 만든 뒤에 새 실적 공시가 났는가. 이관(2026-08-19) 전에는 두 날짜가 같은
    # 값이라 이 질문 자체를 할 수 없었다. 실측: 초안 뒤에 10-Q가 들어온 종목이 14종 중
    # 4종(AXTI·IONQ·SNDK·SATL)이었고 그중 IONQ는 이미 발행까지 나갔다.
    _lab = str(_get(mod, 'AS_OF', '') or '')
    _blt = str(_get(mod, 'BUILT_AT', '') or '')
    if _lab and _blt and _lab > _blt:
        try:
            _gap = (datetime.strptime(_lab, '%Y-%m-%d').date()
                    - datetime.strptime(_blt, '%Y-%m-%d').date()).days
            add(BLOCK, 'AS_OF', f'초안({_blt}) 이후 {_gap}일 만에 새 실적 공시({_lab})가 났다 — '
                                f'리포트가 그 공시를 못 봤다. `python autogen.py {ticker}` 재생성 필요')
        except ValueError:
            pass

    # ══════════════════════════════════════════════════════════════════
    # 아래 규칙들은 2026-08-13 ABCL 리뷰에서 나왔다. 그때 check는 "이상 없음
    # (차단 0 · 경고 0)"으로 통과시켰는데 사람이 보자마자 고칠 것을 여러 개 찾았다.
    # 기존 규칙이 전부 "빈 칸이 있나"만 보고 있었고, 정작 문제는
    # **"채워졌는데 서로 안 맞나"**였다. 그 축을 여기서 연다.
    #
    # 원칙: 사람이 한 번 지적한 것은 규칙이 된다. 두 번 말하게 하지 않는다.
    # ══════════════════════════════════════════════════════════════════

    # ── 라이브 시세를 데이터 파일에 굳혔나 ──
    # 시세는 render 시점에 live.bundle()이 새로 가져온다. 생성 시점 값을 문장에
    # 박아두면 두 값이 반드시 어긋난다 — ABCL에서 같은 페이지에 '현재가 $10.22'와
    # '$10.16'이 나란히 찍혔고 PSR도 41.5/41.7/42 세 값이 됐다.
    _LIVE_WORDS = re.compile(r'(현재가|시가총액|목표주가|PSR)\s*\$?[\d,\.]+|PSR\s*[\d,\.]+\s*배')
    for fld in ('SUMMARY', 'INCOME_NOTE', 'BALANCE_NOTE', 'CASHFLOW_NOTE', 'CHECKPOINT_NOTE'):
        txt = _get(mod, fld, '') or ''
        if isinstance(txt, str):
            m = _LIVE_WORDS.search(txt)
            if m:
                add(BLOCK, fld, f'시세성 수치가 문장에 굳어 있음({m.group(0)!r}) — '
                                f'렌더 시점 값과 어긋난다. 밸류에이션은 카드 박스에서만 표시할 것')

    # ── 손익 전환 문장이 최신 부호와 모순되나 ──
    # ABCL은 FY2020 흑자전환 후 FY2023부터 다시 적자인데 "FY2020에 흑자로 전환됨"이
    # 찍혀 같은 페이지의 '순이익 -$146.4M'과 정면으로 모순됐다. 첫 전환만 보고
    # 그 뒤 역전을 무시한 결과다.
    # 손익 시계열은 데이터 파일에 없고 렌더 시점에 XBRL에서 온다. 그래서 외부와
    # 대조할 수 없고, **문장 자신과의 모순**으로 판정한다 — 같은 문단이 최신 실적을
    # 이미 말하고 있으므로 그것만으로 충분하다.
    summ = _get(mod, 'SUMMARY', '') or ''
    if isinstance(summ, str) and '흑자로 전환' in summ:
        # ⚠️ 어떤 항목이 흑자 전환했는지를 먼저 본다. 예전엔 그걸 안 보고 문단 안에
        #    '영업이익 $-' 이든 '순이익 $-' 이든 하나만 있으면 막았다. 그래서 BE 처럼
        #    "**영업이익**은 FY2024에 흑자로 전환됨 / 순이익 $-87.1M" 이라는 **정상**
        #    문장이 차단됐다(2026-09-11 실측). 둘은 다른 항목이라 모순이 아니다.
        #    주어를 못 찾는 문장(ABCL: "FY2020에 흑자로 전환됨")은 예전처럼 보수적으로
        #    판정한다 — 원래 이 규칙이 잡으려던 게 그 형태다.
        neg = {m.group(1) for m in re.finditer(r'(영업이익|순이익)\s*\$-', summ)}
        subj = set()
        for _sent in re.split(r'[.\n]', summ):
            if '흑자로 전환' in _sent:
                subj |= {w for w in ('영업이익', '순이익') if w in _sent}
        bad = (subj & neg) if subj else neg
        if bad:
            add(BLOCK, 'SUMMARY', f'"흑자로 전환" 문장이 있는데 같은 문단의 {sorted(bad)[0]}가 적자 — '
                                  '마지막 부호 변화를 봐야 한다(첫 전환만 보면 그 뒤 역전을 놓친다)')

    # ── 내부 채점 공식이 카드에 그대로 노출되나 ──
    # 근거 문장("경쟁사 9곳 → -2점")은 의도된 표시다. 문제는 산식 자체가 새는 것:
    # "공식: (전년동기 대비 분기 영업이익 증가율 - 5%) → 0.0점 (상한 25)".
    _FORMULA = re.compile(r'공식\s*:|상한\s*\d|가중치\s*\d|\bround\(|\bmin\(|\bmax\(')
    for fld in ('CANSLIM_NOTE', 'CANSLIM_N_DETAIL', 'CHECKPOINT_NOTE', 'SUMMARY'):
        v = _get(mod, fld, None)
        texts = list(v.values()) if isinstance(v, dict) else ([v] if isinstance(v, str) else [])
        for t in texts:
            if isinstance(t, str) and _FORMULA.search(t):
                add(BLOCK, fld, f'내부 채점 산식이 카드에 노출됨: {t[:60]!r} — '
                                f'근거 문장은 남기되 공식·상한·가중치 표현은 빼야 함')
                break

    # ── 같은 출처가 서로 다른 값을 대고 있나 (TAM) ──
    # ABCL: ('BioSpace', 89.82) 와 ('BioSpace', 2168.91) — 같은 이름인데 24배 차이.
    # 독자가 "같은 출처인데 왜 이렇게 다른지 알 길이 없다"고 멈춘 지점이다.
    tam = _get(mod, 'TAM', {}) or {}
    ests = tam.get('estimates') if isinstance(tam, dict) else None
    if ests:
        by_src = {}
        for e in ests:
            if isinstance(e, (list, tuple)) and len(e) >= 2 and isinstance(e[1], (int, float)):
                by_src.setdefault(str(e[0]), []).append(float(e[1]))
        for src, vals in by_src.items():
            if len(vals) > 1 and min(vals) > 0 and max(vals) / min(vals) >= 5:
                add(WARN, 'TAM.estimates',
                    f'같은 출처 {src!r}가 {min(vals):,.0f} 와 {max(vals):,.0f} 로 '
                    f'{max(vals)/min(vals):.0f}배 차이 — 시장 정의가 다르면 라벨을 구분할 것')

    # ── 세그먼트 유령 0: 아는 숫자를 0으로 감췄나 ──
    # ABCL: AbCellera-led 0.0 / Partner-led 0.0 으로 둘 다 0이라 렌더러가 "부문별
    # 비중 데이터 없음"으로 숨겼는데, 실제로는 Partner-led가 전사 매출의 100%였다.
    # 0과 None은 완전히 다른 사실이고, 이 프로젝트에서 반복해 나온 버그 클래스다.
    seg = _get(mod, 'SEGMENTS', {}) or {}
    by_line = seg.get('by_line') if isinstance(seg, dict) else None
    if by_line:
        vals = [v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else None for v in by_line]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if nums and all(v == 0 for v in nums):
            add(BLOCK, 'SEGMENTS.by_line',
                f'부문 {len(nums)}개가 전부 0 — 진짜 0인지, 아는 값을 0으로 채운 건지 구분 안 됨. '
                f'모르는 값은 None으로 두어야 렌더러가 정직하게 생략한다')

    # ── TAM 노트가 자기 estimates와 다른 숫자를 말하나 ──
    # ABCL 노트는 "$3천억(2025)/$5천억(2030)"인데 estimates 4건 어디에도 그 값이 없다.
    tam = _get(mod, 'TAM', {}) or {}
    note = tam.get('note') if isinstance(tam, dict) else ''
    ests = tam.get('estimates') if isinstance(tam, dict) else None
    if isinstance(note, str) and note and ests:
        have = {round(float(e[1])) for e in ests
                if isinstance(e, (list, tuple)) and len(e) > 1 and isinstance(e[1], (int, float))}
        said = {round(float(x)) for x in re.findall(r'(\d{2,5})\s*(?:억|십억|B\b)', note)}
        if said and have and not (said & have):
            add(WARN, 'TAM.note',
                f'노트가 말하는 시장규모 {sorted(said)} 가 estimates {sorted(have)} 에 없음 — '
                f'출처가 다르면 노트에도 출처를 밝힐 것')

    order = {BLOCK: 0, WARN: 1, INFO: 2}
    return sorted(out, key=lambda r: order[r[0]])


def module_for(ticker: str):
    """종목의 데이터 모듈을 임포트해서 돌려준다.

    report() 안에 박혀 있던 것을 꺼냈다 — refresh.py 가 "발행 차단인 종목"을 고르려면
    렌더 없이 audit() 만 돌려야 하는데, 그러려면 모듈 해석이 먼저 필요하다.
    규칙이 두 벌이 되면 한국 종목에서 조용히 갈라지므로 여기 하나만 둔다.

    한국 티커는 숫자로 시작하고 점이 있어(005930.KS) 그대로 모듈명을 만들면
    '005930.ks_data' → 파이썬이 '005930' 패키지를 찾다가 죽는다.
    autogen_kr.module_name() 과 **같은 규칙**을 써야 한다.
    """
    if ticker.upper().endswith(('.KS', '.KQ')):
        import sources_kr
        name = sources_kr.module_name(ticker)
    else:
        try:
            import autogen
            name = autogen._module_name(ticker)
        except Exception:
            name = f'{ticker.lower()}_data'
    # ⚠️ 반드시 reload 한다. import_module 만 쓰면 한 프로세스가 재생성 **전에**
    #    임포트해둔 옛 모듈을 돌려준다 — 그러면 방금 고친 종목이 여전히 차단으로
    #    보이고(실측 2026-09-08 AXTI), 신선도를 재면 옛 BUILT_AT 이 나온다
    #    (실측 2026-10-03: AAPL 이 9/25 재생성됐는데 8/02 로 읽혀 "53일 낡음"이라고
    #     보고했다 — 틀린 수치로 할 일 목록을 만들 뻔했다).
    #    운영 경로는 deck_live._forget_module 이 따로 막고 있지만, 그걸 안 거치는
    #    분석·채점 도구가 같은 함정에 빠진다. 해석 규칙은 여기 한 곳에만 둔다.
    mod = importlib.import_module(name)
    try:
        return importlib.reload(mod)
    except Exception:
        return mod        # 리로드가 깨지면 있는 걸로라도 판정한다(조용히 빠지지 않게)


def blockers(ticker: str, mod=None):
    """이 종목이 발행 차단인 이유들 — [(항목, 설명), ...]. LLM 0콜·렌더 0회.

    렌더(24초)를 돌려봐야 차단 여부를 알던 것을 즉시 판정으로 바꾼다. 봇이 요청을
    받았을 때 "그릴지 / 먼저 재생성할지"를 그리기 전에 정해야 하기 때문이다.
    """
    if mod is None:
        try:
            mod = module_for(ticker)
        except Exception as e:
            return [('IMPORT', f'데이터 모듈을 못 읽음: {e}')]
    return [(item, msg) for lvl, item, msg in audit(mod, ticker) if lvl == BLOCK]


def report(ticker: str, mod=None) -> int:
    """검사 결과를 콘솔에 찍고 BLOCK 개수를 반환."""
    if mod is None:
        mod = module_for(ticker)
    rows = audit(mod, ticker)
    n_block = sum(1 for r in rows if r[0] == BLOCK)
    n_warn = sum(1 for r in rows if r[0] == WARN)
    icon = {BLOCK: 'X', WARN: '!', INFO: '·'}
    print(f'\n── {ticker} 발행 전 점검 ' + '─' * 40)
    if not rows:
        print('  이상 없음 — 바로 발행 가능')
    for level, item, msg in rows:
        print(f'  [{icon[level]}] {item:<26} {msg}')
    verdict = ('발행 불가' if n_block else ('발행 가능(품질 개선 여지 있음)' if n_warn else '발행 가능'))
    print(f'  → {verdict}   (차단 {n_block} · 경고 {n_warn})')
    if n_block:
        # TICKERS에 수동 등록된 종목은 파일명이 {ticker}_data.py가 아닐 수 있다
        # (SATL → satl16_data.py) — 실제 모듈명을 쓴다.
        fname = getattr(mod, '__name__', f'{ticker.lower()}_data')
        print(f'     고칠 곳: decks/{fname}.py — 고친 뒤 그 필드 경로를 '
              f'같은 파일 LOCKED에 추가하면 재생성해도 안 덮어씀')
    return n_block


def _all_tickers():
    """decks/*_data.py 에서 종목 코드를 뽑는다. satl16_data.py → SATL 같은 예외도 흡수.

    ⚠️ 한국 종목은 파일명에서 되돌릴 수 없다. kr005930_data.py 는 뒤 숫자를 떼면
    'KR' 이 되고, 코스피(.KS)냐 코스닥(.KQ)이냐도 파일명에 남아 있지 않다. 그래서
    한국 종목 둘이 똑같이 'KR' 로 뭉개져 임포트가 깨졌고, 이 함수를 쓰는
    report_all()·pending_line() 이 **한국 종목을 아예 못 보고 있었다**(2026-09-06
    발견 — 화면엔 아무 표시도 없이 그냥 목록에서 빠져 있었다).
    파일 안의 'ticker' 필드가 유일한 출처다.
    """
    import re as _re
    out = []
    for p in sorted(Path(__file__).resolve().parent.glob('*_data.py')):
        if p.stem.startswith('kr'):
            m = _re.search(r"""['"]ticker['"]\s*:\s*['"]([^'"]+)['"]""",
                           p.read_text(encoding='utf-8', errors='replace'))
            if m:
                out.append(m.group(1).upper())
                continue
        out.append(_re.sub(r'\d+$', '', p.stem[:-5]).upper())
    return out


def _published():
    """텔레그램으로 실제 발행된 종목 집합 (deck_files.json)."""
    try:
        f = Path(__file__).resolve().parent.parent / 'deck_files.json'
        return set(json.loads(f.read_text(encoding='utf-8')).keys())
    except Exception:
        return set()


def _rendered_at(ticker):
    """out/{ticker}/ 안 PNG의 최종 수정시각 → 렌더 후 며칠 지났나."""
    d = Path(__file__).resolve().parent / 'out' / ticker.lower()
    pngs = list(d.glob('*.png')) if d.exists() else []
    if not pngs:
        return None
    newest = max(p.stat().st_mtime for p in pngs)
    return (datetime.now() - datetime.fromtimestamp(newest)).days


def _stale_render(ticker, mod):
    """데이터 파일을 고친 뒤 재렌더를 안 했는가.

    2026-08-16 신설. 데이터만 고치고 렌더를 잊으면 카드에는 옛 숫자가 그대로
    남는데, 그동안은 이걸 잡는 장치가 없었다(실제로 AGL·IONQ가 그 상태였다).
    """
    d = Path(__file__).resolve().parent / 'out' / ticker.lower()
    pngs = list(d.glob('*.png')) if d.exists() else []
    src = getattr(mod, '__file__', None)
    if not pngs or not src or not Path(src).exists():
        return False
    return Path(src).stat().st_mtime > max(p.stat().st_mtime for p in pngs)


def report_all(stale_days=7):
    """전 종목 한 번에 — 차단·경고 + '만들어놓고 안 나간' 것까지 한 화면에.

    2026-08-16 신설. 그전까지는 종목을 하나씩 쳐야 상태를 알 수 있어서, 12종 중
    3종만 발행된 채 나머지가 몇 주간 서 있는 걸 아무도 못 봤다. 차단이 0인데
    발행이 안 된 종목을 '발행 대기'로 따로 뽑는 게 이 함수의 핵심 목적이다.
    """
    pub, rows = _published(), []
    for t in _all_tickers():
        try:
            import autogen
            mod = importlib.import_module(autogen._module_name(t))
        except Exception:
            try:
                mod = importlib.import_module(f'{t.lower()}_data')
            except Exception as e:
                rows.append((t, -1, -1, False, None, f'임포트 실패: {e}', False)); continue
        r = audit(mod, t)
        rows.append((t, sum(1 for x in r if x[0] == BLOCK), sum(1 for x in r if x[0] == WARN),
                     t in pub, _rendered_at(t), '', _stale_render(t, mod)))

    print('\n' + '=' * 78)
    print('12p 딥리포트 — 전 종목 발행 상태')
    print('=' * 78)
    print(f"  {'종목':<7}{'차단':>5}{'경고':>5}  {'렌더':<9}{'발행':<7}상태")
    waiting, restale = [], []
    for t, nb, nw, is_pub, age, err, stale in rows:
        if err:
            print(f'  {t:<7}{"?":>5}{"?":>5}  {"-":<9}{"-":<7}{err}'); continue
        rend = f'{age}일 전' if age is not None else '미렌더'
        if stale:
            rend += '*'
            restale.append(t)
        if nb:
            state = f'🔴 차단 {nb}건'
        elif stale:
            state = '🟣 재렌더 필요'
        elif is_pub:
            state = '✅ 발행됨'
        elif age is None:
            state = '🟡 렌더 필요'
        else:
            state = '🟠 발행 대기'
            waiting.append((t, age))
        print(f'  {t:<7}{nb:>5}{nw:>5}  {rend:<9}{"O" if is_pub else "-":<7}{state}')

    n_block = sum(1 for r in rows if r[1] > 0)
    print('-' * 78)
    print(f'  총 {len(rows)}종 · 발행됨 {sum(1 for r in rows if r[3])} · '
          f'발행 대기 {len(waiting)} · 차단 {n_block} · 미렌더 '
          f'{sum(1 for r in rows if r[4] is None and r[1] == 0)}')
    if restale:
        print(f'\n  🟣 데이터를 고친 뒤 재렌더 안 함(* 표시): {", ".join(restale)}')
        print('     이 상태로 발행하면 카드에 옛 숫자가 그대로 나간다.')
    if waiting:
        old = [f'{t}({a}일)' for t, a in waiting if a is not None and a >= stale_days]
        print(f'\n  🟠 발행 대기: {", ".join(t for t, _ in waiting)}')
        if old:
            print(f'  ⚠️  렌더 후 {stale_days}일 넘게 안 나간 것: {", ".join(old)}')
        print('     차단이 0이면 "품질 개선 여지 있음"은 발행을 미룰 사유가 아니다.')
    return n_block


def pending_line():
    """한 줄 요약 — build.py가 렌더 끝에 부른다. 밀린 게 있으면 그것만 짚는다."""
    pub = _published()
    block = stale = waiting = missing = 0
    names = []
    for t in _all_tickers():
        try:
            import autogen
            mod = importlib.import_module(autogen._module_name(t))
        except Exception:
            try:
                mod = importlib.import_module(f'{t.lower()}_data')
            except Exception:
                continue
        nb = sum(1 for x in audit(mod, t) if x[0] == BLOCK)
        age, st = _rendered_at(t), _stale_render(t, mod)
        if nb:
            block += 1
        elif st:
            stale += 1
        elif age is None:
            missing += 1
        elif t not in pub:
            waiting += 1; names.append(t)
    bits = []
    if block:
        bits.append(f'차단 {block}')
    if stale:
        bits.append(f'재렌더 {stale}')
    if missing:
        bits.append(f'미렌더 {missing}')
    if waiting:
        bits.append(f'발행 대기 {waiting}({", ".join(names)})')
    print('\n  📦 전체 덱 상태 — ' + (' · '.join(bits) if bits else '밀린 것 없음') +
          ('   (자세히: python check.py --all)' if bits else ''))
    return waiting + block + stale + missing


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용법: python check.py TICKER   |   python check.py --all')
        sys.exit(1)
    if sys.argv[1] in ('--all', '-a', 'all'):
        sys.exit(1 if report_all() else 0)
    sys.exit(1 if report(sys.argv[1].upper()) else 0)
