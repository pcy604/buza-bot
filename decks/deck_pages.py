# -*- coding: utf-8 -*-
"""16페이지 딥리포트 — 종목 무관 범용 렌더러.

페이지 함수(p00_cover~p16_checkpoints)는 전부 모듈 전역 D(정적 사실)·M(회사 메타)·
CIK·PEERS·L(라이브 수치, live.bundle 결과)만 보고 그린다. 다른 종목으로 바꾸려면
`configure()`로 이 전역들을 교체하면 된다 — 페이지 함수는 한 글자도 안 건드림.

    import deck_pages as P
    P.configure(data_module=pltr_data, ticker='PLTR', name='Palantir Technologies Inc.',
                exchange='NYSE', sector='빅데이터 분석·AI 플랫폼', cik=1321655,
                peers={'SNOW': 1640147}, site='https://www.palantir.com',
                ceo='Alexander Karp')
    P.render_all('out/pltr')

satl16_data.py가 이 스키마(HISTORY·LEADERSHIP·SHARES·SEGMENTS·TECH·RESULTS·
VALUATION·CANSLIM_N·INCOME_NOTE·BALANCE_NOTE·CASHFLOW·TAM·PEERS·ETFS·CHECKPOINTS·
SRC·AS_OF·PRICE_ASOF)의 실제 예시 — 새 종목 데이터 파일은 이 필드를 그대로 채우면 됨.
"""
import datetime as _dt
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import satl16_data as _default_data  # noqa: E402  기본값(단독 실행 시 SATL)
import live  # noqa: E402
import brandmark as BM  # noqa: E402
import charts2 as C2  # noqa: E402
from deck16 import (  # noqa: E402
    S, PAD, CW, TOP, BOT, BG, SURFACE, LINE, INK, INK_DIM, INK_FAINT, ACCENT,
    POS, NEG, FLAT, SEGMENT_COLORS, _font, _s, _wrap_draw, _wrap,
    _footer, _note, _kpi_tiles, _donut, _legend, _hbar, _vbar, _table,
    _waterfall, _timeline, new_canvas, paste_scaled, finish, SS, SDraw,
)
import deck16 as _D16  # noqa: E402  통화 전파용(set_currency)
import canslim as CL  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

D = _default_data
M = D.COMPANY
CIK = 1874315
PEERS = {'PL': 1836833, 'BKSY': 1753539}
BRAND_MARK = BM.mark_b          # 사용자 선택 시안(B. 링 다이얼 + 돌파) — 구 브랜드, stock_studian로 교체 후 미사용
BRAND_NAME = 'stock_studian'
BRAND_HANDLE = '@stock_studian'
# 브랜드 로고는 산출물이 아니라 자산이다. 예전엔 `out/`에 뒀는데 그 폴더는
# .gitignore라 러너엔 존재하지 않았고, 임포트 시점에 파일을 여느라
# `import deck_pages`가 FileNotFoundError로 죽어 12장 렌더가 통째로 실패했다
# (폰에서 /report QLYS — autogen은 다 성공했는데 렌더에서 날아갔다).
# assets/로 옮겨 커밋하고, 없더라도 벡터 마크로 물러나 렌더는 계속되게 한다.
_LOGO_PATH = Path(__file__).resolve().parent / 'assets' / 'stock_studian_pfp.png'
try:
    _STOCK_STUDIAN_LOGO = Image.open(_LOGO_PATH).convert('RGBA')
except Exception as _e:                      # noqa: BLE001 — 로고 하나로 전체를 죽이지 않는다
    print(f'[경고] 브랜드 로고 없음({_LOGO_PATH}) — 벡터 마크로 대체: {_e}')
    _STOCK_STUDIAN_LOGO = None


def _brand_mark(im, x, y, size):
    """stock_studian PNG 로고를 정사각형 박스에 맞춰 붙인다(부자알람 벡터 마크 대체)."""
    if _STOCK_STUDIAN_LOGO is None:
        BRAND_MARK(im, x, y, size)           # 구 벡터 마크로 폴백
        return
    paste_scaled(im, _STOCK_STUDIAN_LOGO, (x, y), (size, size), pad_ratio=0.0)


L = None                        # live 번들 (render_all/configure에서 주입)

# 보고통화. 'USD'(SEC·XBRL) | 'KRW'(DART). 금액 표기 전부가 이 값 하나만 본다 —
# 페이지 함수는 시장을 몰라도 되고, 새 시장을 붙일 때 손댈 곳이 _mB/_px 둘뿐이다.
CURRENCY = 'USD'

# 한국거래소 접미사. Yahoo는 KOSPI=.KS · KOSDAQ=.KQ 로 한국 종목을 그대로 준다
# (실측: 005930.KS 주가·시총·발행주식수·애널리스트 컨센서스 35명·목표주가까지 전부 응답).
KR_SUFFIXES = ('.KS', '.KQ')


def is_kr(ticker: str) -> bool:
    return str(ticker or '').upper().endswith(KR_SUFFIXES)


def configure(data_module, ticker, name, exchange, sector, cik, peers,
              site, ceo, wiki_file='', listing_date=None, currency=None):
    """다른 종목으로 전환 — 페이지 함수가 참조하는 모듈 전역을 전부 교체한다."""
    global D, M, CIK, PEERS, CURRENCY
    D = data_module
    M = {'ticker': ticker, 'name': name, 'exchange': exchange, 'sector': sector}
    CIK = cik
    PEERS = peers
    # 명시값 > 티커 접미사 추론. 종목을 갈아끼울 때마다 반드시 다시 정한다 —
    # 전역이라 앞 종목의 통화가 남으면 원화 종목이 달러로 찍힌다.
    CURRENCY = currency or ('KRW' if is_kr(ticker) else 'USD')
    # 금액을 찍는 **다른 모듈**도 같은 통화를 봐야 한다. 한쪽만 알면 같은 카드 안에서
    # 표는 '5,767억원'인데 도넛은 '$576.7B'로 갈린다(실측).
    C2.set_currency(CURRENCY)   # 가격축 라벨
    _D16.set_currency(CURRENCY)  # 도넛·범례 금액(_mfmt)
    return dict(site=site, ceo=ceo, wiki_file=wiki_file, listing_date=listing_date)


def _mB(m, dp=1, sign=False):
    """이미 M(백만) 단위인 값을 부호가 달러기호 밖으로 나오게 $M/$B/$T로 표기
    (예: -411.0 → "-$411.0M", 아니라 "$-411.0M"). $1000M(=$1B) 이상은 B, $1,000,000M(=$1T)
    이상은 T로 자동 전환 — TSLA 시총 $1.2조가 B 단계에서 멈춰 "$1236.3B"로 안 읽히던 걸
    포함해 대형주 스케일마다 반복되던 문제를 한 번에 막는다."""
    if m is None:
        return '—'
    neg = m < 0
    am = abs(m)
    prefix = '-' if neg else ('+' if sign else '')
    if CURRENCY == 'KRW':
        # 입력 계약은 달러판과 같다(보고통화의 백만 단위 = 백만원). DART는 원 단위로
        # 신고하므로 호출부에서 /1e6 한 값이 그대로 들어온다.
        # 단위는 한국 재무 관행대로 억(1e8원=100백만원)·조(1e12원=1e6백만원).
        # M/B/T를 그대로 쓰면 "$576.7M"에 해당하는 값이 한국 독자에겐 안 읽힌다.
        if am >= 1_000_000:
            val, unit_s = am / 1_000_000, '조'
        elif am >= 100:
            val, unit_s = am / 100, '억'
        else:
            val, unit_s = am, '백만'
        # 억 단위는 네 자리를 예사로 넘는다(삼성 분기매출 1,714,995억) — 천단위 구분이
        # 없으면 못 읽는다. 그리고 그 자릿수에서 소수 첫째자리는 노이즈라 떨군다.
        _dp = 0 if val >= 1000 else dp
        return f'{prefix}{val:,.{_dp}f}{unit_s}원'
    if am >= 1_000_000:
        body, unit_s = f'{am/1_000_000:.{dp}f}', 'T'
    elif am >= 1000:
        body, unit_s = f'{am/1000:.{dp}f}', 'B'
    else:
        body, unit_s = f'{am:.{dp}f}', 'M'
    return f'{prefix}${body}{unit_s}'


def _px(v, dp=2, sign=False):
    """**주당** 금액(주가·EPS·목표주가). _mB와 달리 단위 환산을 하지 않는다.

    원화는 소수점이 의미 없다(281,500원을 '281500.00원'으로 찍으면 안 됨) —
    천단위 구분 정수. 달러는 기존대로 소수 2자리."""
    if v is None:
        return '—'
    prefix = '+' if (sign and v >= 0) else ''
    if CURRENCY == 'KRW':
        return f'{prefix}{v:,.0f}원'
    return f'{prefix}${v:,.{dp}f}'


def _m(v, unit=1e6, dp=1, sign=False):
    """$ 단위 표기(raw 달러 입력). PLTR 검증에서 시총 $294.7B가 unit=1e6 그대로 찍혀
    "$294677.6M"으로 나오는 걸 확인 — $1000M(=$1B) 이상이면 B로 자동 전환."""
    if v is None:
        return '—'
    if unit == 1e6:
        return _mB(v / 1e6, dp, sign)
    s = f'{v/unit:+.{dp}f}' if sign else f'{v/unit:.{dp}f}'
    return s


def _pct(a, b):
    if a is None or not b:
        return None
    return (a - b) / abs(b) * 100


# ── 회계연도 축 (하드코딩 금지) ────────────────────────────────────────
# 예전엔 p07/p09/p10/p11이 `yrs = [2021, 2022, 2023, 2024, 2025]`처럼 연도를 리터럴로
# 박아뒀다. 그러면 (a) 2024년 상장 종목은 앞 세 칸이 영구히 비고, (b) 아직 FY2025를
# 신고 안 한 종목은 마지막 칸이 비고, (c) 해가 바뀌면 전 종목이 한 칸씩 어긋난다.
# "티커만 치면 된다"를 깨는 대표적인 원인이라 실제 데이터에서 축을 만든다.
def _fy_years(n=5, keys=('revenue',)):
    """XBRL에 실제 값이 있는 회계연도 중 최근 n개(오름차순).

    keys는 그 페이지의 '대표 항목' — 손익은 revenue, 대차대조표는 assets/equity,
    현금흐름표는 cfo. 대표 항목조차 없는 해는 축에서 빼야 유령 빈칸이 안 생긴다.
    데이터가 아예 없으면 초안 기준(BUILT_AT) 최근 n년으로 폴백(빈 표라도 축은 그려야 함)."""
    ann = (L or {}).get('annual', {})
    yrs = set()
    for k in keys:
        yrs |= {y for y, v in (ann.get(k) or {}).items() if v is not None}
    if yrs:
        return sorted(yrs)[-n:]
    base = str(_ref_year() or '')
    cur = (int(base) if base.isdigit() else 2026) - 1
    return list(range(cur - n + 1, cur + 1))


def _profit_series():
    """이익 계열 — 영업이익이 원칙, 없으면 순이익으로 대체.

    (연간 dict, 분기 dict, 한국어 라벨, 대체여부) 반환.

    은행(JPM)·리츠(O) 등 상당수 업종은 `OperatingIncomeLoss` 태그를 아예 공시하지
    않는다(실측 확인 — 두 종목 모두 opinc 전 연도 없음, netinc는 정상). 예전엔 그걸
    "영업이익 0/없음"으로 받아서 (a) CANSLIM C·A가 둘 다 0점, (b) 밸류에이션 ②가
    "최근 분기 적자라 PER이 정의되지 않음"이라는 **사실과 반대되는 문장**을 붙였다.
    JPM은 적자가 아니라 태그가 없을 뿐이다."""
    ann = (L or {}).get('annual', {})
    if any((ann.get('opinc') or {}).values()):
        return ann.get('opinc') or {}, (L or {}).get('q_opinc') or {}, '영업이익', False
    if any((ann.get('netinc') or {}).values()):
        return ann.get('netinc') or {}, (L or {}).get('q_netinc') or {}, '순이익', True
    return {}, {}, '영업이익', False


def _est_years(yrs):
    """컨센서스 2개 구간의 실제 연도 라벨(예: ['2026E', '2027E']).

    Yahoo earningsTrend가 endDate를 주므로 그걸 우선 쓰고(회계연도가 역년과 다른
    회사도 정확), 없으면 마지막 실적연도 +1/+2로 만든다. '2026E'를 문자열로 박아두면
    내년에 전 종목이 한꺼번에 틀린다."""
    p = ((L or {}).get('consensus', {}) or {}).get('periods', {}) or {}
    last = yrs[-1] if yrs else 2025
    out = []
    for i, k in enumerate(('0y', '+1y')):
        end = (p.get(k) or {}).get('end') or ''
        out.append(f'{end}E' if str(end).isdigit() else f'{last + i + 1}E')
    return out


# ── 공통 프레임 (브랜드 적용) ──────────────────────────────────────────
def _ref_year(default=0):
    """차트가 '올해'로 삼을 연도.

    표지의 AS_OF는 **최신 실적 공시일**(독자에게 보여줄 라벨)이라 차트 기준으로 쓰면 안 된다 —
    커버리지가 밀린 종목은 공시일이 작년일 수 있고, 그러면 축이 통째로 한 해 밀린다.
    차트·서술의 '지금'은 초안을 만든 시점(BUILT_AT)이다. 옛 데이터 파일엔 BUILT_AT이
    없으므로 AS_OF로 물러난다(그 파일들에선 AS_OF가 곧 초안 날짜였다).
    """
    for k in ('BUILT_AT', 'AS_OF'):
        v = str(getattr(D, k, '') or '')[:4]
        if v.isdigit():
            return int(v)
    return default


def _px_asof():
    """카드에 찍는 가격이 **실제로 언제 종가인지**.

    가격은 렌더할 때마다 live.bundle()로 새로 받아오는데(deck_pages.py 하단),
    날짜만 데이터 파일에 박힌 초안 날짜(PRICE_ASOF)를 쓰고 있었다. 그래서 초안을
    만든 날 바로 발행하지 않으면 최신 가격에 옛 날짜가 붙었다 — 2026-08-19 실측으로
    TSLA는 25일, 발행까지 나간 IONQ는 11일 어긋나 있었다.

    라이브 값이 있으면 그걸 쓰고, 없으면 **거짓말 대신 빈 문자열**을 돌려준다.
    (틀린 날짜를 찍느니 날짜를 안 찍는 게 낫다.)
    """
    a = ((L or {}).get('technical') or {}).get('asof')
    return a or ''


_CUR = None   # render_all 이 지금 그리는 페이지 순번 — 페이지가 늘어도 머리 번호가 안 어긋나게


def _page(idx, label, sub=''):
    # 페이지마다 번호를 숫자로 박아 두었다가 장을 끼워 넣으면 전부 어긋난다(2026-10-20,
    # 대가 관점 3장 추가). 실제 순번을 쓴다.
    if _CUR is not None:
        idx = _CUR
    im, dr = new_canvas()
    dr.rectangle([0, 0, S, 6], fill=ACCENT)
    _brand_mark(im, PAD, 34, 34)
    dr.text((PAD + 46, 40), BRAND_NAME, font=_font(True, 18), fill=INK)
    t = f'{M["ticker"]} · {idx}/{len(PAGES) - 1}'
    dr.text((S - PAD - _font(True, 16).getlength(t), 44), t, font=_font(True, 16), fill=INK_FAINT)
    dr.text((PAD, 88), label, font=_font(True, 36), fill=INK)
    if sub:
        dr.text((PAD, 134), sub, font=_font(False, 17), fill=INK_FAINT)
    dr.line([(PAD, 158), (S - PAD, 158)], fill=LINE, width=1)
    return im, dr


TOP2 = 182


# ── 표지 ───────────────────────────────────────────────────────────────
_GENERIC_BIZ = re.compile(r'(주문에 따른|주문에 따라|제조\s*[·및,]?\s*납품|판매로\s*(매출|수익)|매출을 올림|수익을 창출|수익 창출|'
                          r'다양한 고객|고객에게 (제품|서비스)를 (공급|판매)|제품을 판매)')


def _generic_biz(t) -> bool:
    """어느 회사에나 붙는 뻔한 사업 설명인가(2026-10-23 사용자 지적)."""
    return bool(_GENERIC_BIZ.search(str(t)))


def p00_cover():
    im, dr = new_canvas()
    dr.rectangle([0, 0, S, 8], fill=ACCENT)
    # ① 좌상단: 우리 브랜드
    _brand_mark(im, PAD, 40, 46)
    dr.text((PAD + 60, 44), BRAND_NAME, font=_font(True, 26), fill=INK)
    dr.text((PAD + 62, 80), BRAND_HANDLE, font=_font(False, 14), fill=INK_FAINT)
    # ② 우상단: 사명 — 상단 줄 바로 밑
    nm = M['name']
    dr.text((S - PAD - _font(True, 22).getlength(nm), 40), nm, font=_font(True, 22), fill=INK_DIM)

    # ③ 회사 로고 정중앙 크게
    logo = L.get('logo_hi') if L else None
    cy = 470
    if logo and Path(logo).exists():
        try:
            lg = Image.open(logo)
            box = (640, 300)
            # 위키미디어 로고는 내용이 이미지 가장자리에 딱 붙어 있어(bbox가 캔버스와 동일)
            # 그대로 붙이면 ® 같은 끝 글리프가 잘려 보인다 → 4% 투명 여백 추가
            pr = 0.04
            aw, ah = lg.width * (1 + pr * 2), lg.height * (1 + pr * 2)
            sc = min(box[0] / aw, box[1] / ah)
            nw, nh = aw * sc, ah * sc
            paste_scaled(im, lg, (S / 2 - nw / 2, cy - nh / 2), box, pad_ratio=pr)
        except Exception as e:
            print(f'[표지 로고 실패] {e}')
            logo = None
    if not logo:
        # 모노그램 글자는 티커 첫 글자다. 한국 티커는 숫자라(247540.KQ) 표지에 '2'가
        # 덩그러니 뜬다 — 첫 글자가 글자가 아니면 회사명에서 가져온다.
        head = (M['ticker'] or '')[:1]
        if not head.isalpha():
            head = next((ch for ch in (M['name'] or '') if ch.isalnum() and not ch.isdigit()),
                        head or '?')
        dr.ellipse([S // 2 - 130, cy - 130, S // 2 + 130, cy + 130], fill=ACCENT)
        f = _font(True, 110)
        dr.text((S // 2 - f.getlength(head) / 2, cy - 76), head,
                font=f, fill=(255, 255, 255))

    # 중앙 텍스트 블록
    cons = (L or {}).get('consensus', {})
    mc = cons.get('market_cap')
    lines = [(f'{M["ticker"]} ({M["name"]})', _font(True, 44), INK),
             ('' if '확인 필요' in str(M['sector'] or '') else M['sector'], _font(False, 28), INK_DIM),   # 자리표시자는 표지에 안 보임
             (f'시가총액 {_m(mc)}' if mc else '', _font(True, 30), ACCENT)]
    y = 690
    for t, f, col in lines:
        if not t:
            continue
        dr.text((S // 2 - f.getlength(t) / 2, y), t, font=f, fill=col)
        y += f.size + 18

    # ④ 이 회사 한눈에 — '- ' 짧은 줄 2~3개(2026-10-23 개정: '무엇을/누가 사나/어떻게 버나' 라벨 제거).
    # 표지는 캐러셀에서 가장 먼저(종종 유일하게) 보는 장이라 여기 둔다. 어느 회사에나 붙는 뻔한 줄
    # ("고객사 주문에 따른 장비 제조·납품…으로 매출을 올림")은 정보가 없으니 빼고 보여준다.
    biz = [b for b in (getattr(D, 'BUSINESS', None) or []) if b and not _generic_biz(b)][:3]
    if biz:
        bf = _font(False, 20)
        row_h = 32
        by0 = 858
        bh = 22 + row_h * len(biz)
        dr.rounded_rectangle([PAD, by0, S - PAD, by0 + bh], radius=14, fill=SURFACE)
        ty = by0 + 12
        for txt in biz:
            t = '- ' + str(txt).strip().rstrip('.')
            avail = CW - 44
            full = t
            while t and bf.getlength(t) > avail:
                t = t[:-1]
            if t != full:   # 넘치면 말줄임(원문은 5p 사업부문에 그대로 다시 나온다)
                t = t[:-1] + '…'
            dr.text((PAD + 22, ty), t, font=bf, fill=INK_DIM)
            ty += row_h

    # ⑤ 업로드 날짜만
    f = _font(False, 18)
    _cv = f'{D.AS_OF} 공시 기준' if getattr(D, 'AS_OF', '') else ''
    dr.text((S // 2 - f.getlength(_cv) / 2, S - 84), _cv, font=f, fill=INK_FAINT)
    return im


# ── 1. 업력 ────────────────────────────────────────────────────────────
def _listing_cagr(rows):
    """상장 후 가격 CAGR — ohlcv(월봉) 첫 종가 vs 최근 종가, 실제 개월수로 연환산.
    라이브 계산(밸류에이션·기술적 노트와 같은 패턴) — 데이터파일에 안 넣는 이유는
    가격이 매일 바뀌는데 파일에 박아두면 렌더할 때마다 stale해지기 때문.

    상장 2년 미만인데 그 사이 폭등한 종목(SNDK 실제 사례: 18개월 만에 27배 상승)은
    "연환산"하면 +895%/년처럼 통계적으로는 맞지만 실감이 안 나는 숫자가 나온다
    (실제 지적: "호러물"). 2년 미만이면 연환산 대신 그 기간 그대로의 누적 수익률을
    반환 — (값, 연환산여부) 튜플로 호출부가 라벨을 다르게 달 수 있게 한다."""
    if not rows or len(rows) < 2:
        return None
    first_close, last_close = rows[0][4], rows[-1][4]
    months = len(rows) - 1
    if not first_close or first_close <= 0 or months < 1:
        return None
    total_return = (last_close / first_close - 1) * 100
    if months < 24:
        return total_return, False
    years = months / 12
    return ((last_close / first_close) ** (1 / years) - 1) * 100, True


def _major_moves(rows, reversal=0.30, min_pct=45.0, top_n=4):
    """가격에서 '대시세·폭락' 구간을 직접 찾는다 — 지그재그(반전 임계) 방식.

    왜 이렇게 바꿨나: 이전엔 연혁 사건마다 '이후 6개월 등락률'을 붙였는데
    -5%·-10%·+26% 같은 **일반적인 변동성**만 나왔다. 그건 신호가 아니라 노이즈다.
    사건에 수익률을 붙일 게 아니라, **가격에서 큰 구간을 먼저 찾고 그 안에 사건을
    넣어야** "언제 대시세가 났고 그때 무슨 일이 있었나"가 읽힌다.

    지그재그: 직전 극값에서 reversal(기본 30%) 이상 되돌리면 한 다리가 끝난 것으로
    보고 피벗을 확정한다. 기간을 미리 정하지 않으므로 3개월짜리 급등도, 3년짜리
    하락도 그 실제 길이대로 잡힌다.
    """
    if len(rows) < 4:
        return []
    # 방향이 정해지기 전(direction=0)에는 고점·저점을 **둘 다** 들고 있어야 한다.
    # 하나만 추적하면 그 기준이 반대쪽 갱신에 덮여 반전 조건이 영영 안 걸린다
    # (실제로 그래서 ABCL 전 구간이 -75% 한 다리로 잡혔다).
    piv = []
    hi_i = lo_i = 0
    hi_v = lo_v = rows[0][4]
    direction = 0
    for i, r in enumerate(rows):
        v = r[4]
        if not v:
            continue
        if v > hi_v:
            hi_i, hi_v = i, v
        if v < lo_v:
            lo_i, lo_v = i, v
        if direction >= 0 and hi_v and v <= hi_v * (1 - reversal):
            piv.append((hi_i, hi_v))            # 고점 확정 → 하락 다리 시작
            direction = -1
            lo_i, lo_v = i, v
        elif direction <= 0 and lo_v and v >= lo_v * (1 + reversal):
            piv.append((lo_i, lo_v))            # 저점 확정 → 상승 다리 시작
            direction = 1
            hi_i, hi_v = i, v
    piv.append((hi_i, hi_v) if direction > 0 else (lo_i, lo_v))
    # 시간순 정리 + 중복 제거
    seen, ordered = set(), []
    for it in sorted(piv, key=lambda t: t[0]):
        if it[0] not in seen:
            seen.add(it[0]); ordered.append(it)
    piv = ordered

    legs = []
    for (i0, v0), (i1, v1) in zip(piv, piv[1:]):
        if i1 <= i0 or not v0:
            continue
        pct = (v1 / v0 - 1) * 100
        if abs(pct) < min_pct:
            continue
        d0 = _dt.datetime.fromtimestamp(rows[i0][0])
        d1 = _dt.datetime.fromtimestamp(rows[i1][0])
        months = max(1, (d1.year - d0.year) * 12 + (d1.month - d0.month))
        legs.append({'i0': i0, 'i1': i1, 'y0': d0.year, 'm0': d0.month,
                     'y1': d1.year, 'm1': d1.month, 'months': months,
                     'p0': v0, 'p1': v1, 'pct': pct})
    legs.sort(key=lambda l: -abs(l['pct']))
    legs = legs[:top_n]
    legs.sort(key=lambda l: (l['y0'], l['m0']))
    return legs


def _history_src(h, ohlcv) -> str:
    """연혁 페이지 출처. 두 곳(차트형·목록형)에서 같은 문자열을 만들되,
    **실제로 쓴 것만** 적는다.

    · 'Wikipedia'는 미국 종목의 연혁 출처였다. 한국 종목의 연혁은 DART 사업보고서에서
      왔는데 카드엔 위키피디아라고 찍혔다(실측) — 출처 오기다.
    · 임직원 집계가 없는 초안에서 '임직원= ·'가 값 없이 남았다. 없는 항목은 뺀다.
    """
    parts = [f'연혁={_fin_src("연차") if CURRENCY == "KRW" else "Wikipedia/공시"}']
    if h.get('employee_src'):
        parts.append(f'임직원={h["employee_src"]}')
    parts.append(f'주가=Yahoo Finance chart API{_scale_note(h, ohlcv)}')
    return ' · '.join(parts)


def _scale_note(h, ohlcv) -> str:
    """y축을 로그로 썼는지 선형으로 썼는지, 그 판단 근거(고저 배율)를 각주 문자열로.

    지금까지 조용히 자동 결정돼 "이번엔 로그가 맞았나"를 확인할 방법이 없었다.
    카드에 배율과 결과를 남기면 매번 눈으로 검증된다."""
    closes = [r[4] for r in (ohlcv.get('rows') or []) if r[4]]
    if not closes or not min(closes):
        return ''
    ratio = max(closes) / min(closes)
    used = h.get('log_scale')
    used = (ratio >= 10) if used is None else used
    return f' · y축={"로그" if used else "선형"}(고저 배율 {ratio:.1f}배)'


def _annual_src(long=False):
    """연차 원문 이름 — 한국 종목에 '10-K' 가 찍히던 것(2026-10-23 피에스케이·삼성전자 실측) 방지."""
    if CURRENCY == 'KRW':
        return '사업보고서(DART)' if long else '사업보고서'
    return '연차보고서(10-K)' if long else '10-K'


def p01_history():
    h = D.HISTORY
    # founded=0(자동추출 실패 — 10-K가 창업연도를 재서술 안 함, 스핀오프 등 원문에
    # 아예 없는 개념일 때 실제로 발생함, SNDK 사례)이면 "0년 창업"·"2027년차" 같은
    # 말이 안 되는 숫자가 그대로 찍혔다(실제 발견) — 서브타이틀·타일 둘 다 방어.
    founded = h.get('founded') or 0
    sub = (f'{founded}년 창업' if founded else '창업연도 확인 필요') + (f' · 공동창업자 {h["founders"]}' if h.get('founders') else '')
    im, dr = _page(3, '연혁 · 개요', sub)
    # 임직원 집계가 없는 초안(자동생성 직후·한국 종목)에서 [-1]이 IndexError로 죽어
    # **연혁 페이지가 통째로 사라졌다**(실측). 없으면 타일만 빠지게 한다.
    emp = (h.get('employees') or [None])[-1]
    yr_now = _ref_year()
    ohlcv = (L or {}).get('ohlcv', {})
    cagr_result = _listing_cagr(ohlcv.get('rows'))
    # 창업한 해가 1년차 — 2010년 창업이면 2026년은 17년차
    tiles = []
    if founded:
        tiles.append(('창업', f'{founded}년', f'{yr_now - founded + 1}년차', 'flat'))
    else:
        tiles.append(('창업', '확인 필요', f'{_annual_src()} 원문에 창업연도 서술 없음', 'flat'))
    # "창업" 타일만 방어해두고 "상장" 타일은 안 고쳐뒀다가 PLTR 재생성분에서 똑같은
    # 클래스의 버그가 재발했다(listed=0 → "상장 0년"·"2027년차", listing_type=''
    # 빈 문자열이면 .get(key,'상장') 기본값도 안 먹음 — dict.get은 키가 "없을 때"만
    # 기본값을 쓰지 값이 빈 문자열이면 그 빈 값을 그대로 반환하는 게 원인) — 같은
    # 패턴으로 방어.
    listed = h.get('listed') or 0
    listing_type = h.get('listing_type') or '상장'
    if listed:
        tiles.append(('상장', f'{listed}년',
                      f'{listing_type} · {M["exchange"]} {yr_now - listed + 1}년차', 'flat'))
    else:
        tiles.append(('상장', '확인 필요', f'{_annual_src()} 원문에 상장연도 서술 없음', 'flat'))
    if emp:
        tiles.append(('임직원', f'{emp[1]:,}명', f'{emp[0]} 기준 최신', 'flat'))
    if cagr_result is not None and listed:
        cagr, annualized = cagr_result
        if annualized:
            tiles.append(('상장 후 주가 CAGR', f'{cagr:+.0f}%/년',
                          f'{listed}년 상장 종가 대비 연환산', 'up' if cagr > 0 else 'dn'))
        else:
            # 상장 2년 미만이면 연환산 대신 그 기간 누적수익률 그대로(왜곡 방지)
            tiles.append(('상장 후 누적 수익률', f'{cagr:+.0f}%',
                          f'{listed}년 상장 종가 대비(연환산 아님, 2년 미만)', 'up' if cagr > 0 else 'dn'))
    y = _kpi_tiles(dr, TOP2, tiles, cols=len(tiles), h=68)
    y += 8
    # 장기 캔들+거래량 — 타일 줄이고 차트를 키운 자리(피드백: 위 4칸 줄이고 차트 늘리기).
    # log_scale: HISTORY에서 명시 지정 없으면 자동판단(charts2.price_stack) — IONQ처럼
    # 상장 얼마 안 된 종목은 자동판단도 로그로 잘못 켜질 수 있어 오버라이드 통로를 열어둠.
    # candle_h/vol_h를 150/40→130/32로 살짝 줄임 — 타임라인을 11개 항목으로(피드백:
    # 회사 역사 퀄리티 향상) 늘리면서 이 페이지가 전체적으로 빡빡해져 노트가 푸터와
    # 겹쳤다(실제 발견) — 차트·타일 여백을 조금씩 덜어 그 공간을 만든다.
    # ── 연혁 표시 방식 (2026-08-13 피드백) ──
    # "차트를 더 키우고 주요 연혁은 해당 구간 옆에 조그맣게" — 지금은 그 반대로
    # 되어 있다. 타임라인 11개를 아래에 세로로 쌓느라 차트를 150→130으로 줄였다.
    # 아래 세 값으로 배치를 바꿀 수 있게 열어둔다(기본값은 기존 동작 그대로라
    # 다른 종목 카드가 갑자기 달라지지 않는다). 시안 비교 후 기본값을 정한다.
    #   HIST_TIMELINE_MODE  'list'=아래 세로 목록(기존) · 'chart'=차트 위 라벨만
    #                       · 'both'=차트 라벨 + 아래 목록 축약
    EVENTS = []          # 연혁 + 등락구간을 합친 단일 사건 목록
    # 2026-08-14 시안 확정: 차트를 키우고 연혁을 '대시세·폭락 구간' 카드로
    # 합친 배치를 기본으로 한다(피드백: 차트 키우고 연혁은 구간 옆에 작게).
    mode = globals().get('HIST_TIMELINE_MODE', 'chart')
    candle_h = globals().get('HIST_CANDLE_H', 260)
    vol_h = globals().get('HIST_VOL_H', 48)

    anns = list(h.get('chart_annotations') or [])
    if mode in ('chart', 'both'):
        # 연혁을 차트 주석으로 접어 넣는다 — 사건이 일어난 그 구간 위에 붙어야
        # "언제 무슨 일이 있었고 주가가 어떻게 반응했나"가 한눈에 읽힌다.
        #
        # 피드백 3건을 여기서 한꺼번에 해결한다:
        #  ① 번호가 왼→오른쪽 순서가 아니었다 — 목록 순서대로 매겨서 시간과 무관했다.
        #     좌표를 정하는 건 (연,월)이므로 **먼저 정렬한 뒤** 번호를 받게 한다.
        #  ② 각 구간이 얼마나 오르내렸는지 말이 없었다 — 사건 이후 주가 변화를
        #     직접 계산해 라벨에 붙인다(결정론, LLM 0콜).
        #  ③ 9개는 너무 많다 — 장기 추세에서 진짜 중요한 것만 남긴다. 데이터에 이미
        #     있는 강조 플래그를 1순위로, 그다음은 **주가가 실제로 크게 반응한 순**으로
        #     고른다. "중요하다"를 사람이 매번 고르지 않아도 되게.
        rows_px = ohlcv.get('rows') or []

        # 구간이 단위다. 사건마다 고정 창(6개월) 수익률을 붙이면 -5%·-10% 같은
        # 일반 변동성만 나온다 — 그건 신호가 아니다. 가격에서 대시세·폭락 구간을
        # 먼저 찾고, 그 구간 안에 일어난 연혁을 설명으로 붙인다.
        legs = _major_moves(rows_px, top_n=globals().get('HIST_MAX_EVENTS', 4))

        def _events_in(leg):
            """그 구간 안에 일어난 연혁 사건 이름들."""
            out = []
            for row in (h.get('timeline') or []):
                try:
                    yr = int(str(row[0])[:4])
                except (ValueError, TypeError, IndexError):
                    continue
                if (leg['y0'], leg['m0']) <= (yr, 6) <= (leg['y1'], leg['m1']):
                    out.append(str(row[1]))
            return out

        for lg in legs:
            evs = _events_in(lg)
            dur = (f"{lg['months'] // 12}년 {lg['months'] % 12}개월"
                   if lg['months'] >= 12 else f"{lg['months']}개월")
            EVENTS.append({
                'yr': lg['y0'], 'mo': lg['m0'],
                'label': f"{lg['y0']}.{lg['m0']:02d} → {lg['y1']}.{lg['m1']:02d}  ({dur})",
                'move': f"{lg['pct']:+.0f}%",
                # 이정표가 없으면 **아무 말도 안 한다**. '기록된 이정표 없음' 은 정보가 0인데
                # 자리를 차지하고, 카드 4장이 전부 같은 문장을 반복하면 읽는 사람이
                # 나머지 문구까지 안 읽게 된다.
                'desc': (' · '.join(evs[:2]) if evs else ''),
                'kind': ('대시세' if lg['pct'] > 0 else '폭락'),
                'sub': f"{_px(lg['p0'])} → {_px(lg['p1'])}",
            })
        EVENTS.sort(key=lambda e: (e['yr'], e['mo']))
        anns = [(e['yr'], e['mo'], e['kind']) for e in EVENTS]

    chart_legend = []
    if ohlcv.get('rows'):
        y, chart_legend = C2.price_stack(dr, PAD, y, CW - 56, ohlcv['rows'],
                                         candle_h=candle_h, vol_h=vol_h,
                                         annotations=anns or None,
                                         log_scale=h.get('log_scale'))
        y += 12

    # 사건 카드 — 연혁이든 자동탐지 등락구간이든 같은 형식으로 한 번에.
    # 번호는 차트 배지와 그대로 짝이 맞는다(좌→우 시간순).
    if mode in ('chart', 'both') and EVENTS:
        cols = 2
        cw2 = (CW - 16) / cols
        lf = _font(False, 12.5)
        rows_n = (len(EVENTS) + cols - 1) // cols
        desc_lines = {}
        for i, e in enumerate(EVENTS):
            _d = '  ·  '.join([x for x in (e.get('sub'), e.get('desc')) if x])
            desc_lines[i] = _wrap(_d, lf, cw2 - 34)[:2] if _d else []
        card_h = 34 + max((len(v) for v in desc_lines.values()), default=0) * 16
        for i, e in enumerate(EVENTS):
            cx = PAD + (i // rows_n) * (cw2 + 16)
            cy = y + (i % rows_n) * (card_h + 6)
            up = e['move'].startswith('+')
            col = POS if up else (NEG if e['move'].startswith('-') else INK_DIM)
            dr.rounded_rectangle([cx, cy, cx + cw2, cy + card_h], radius=8, fill=SURFACE)
            dr.rectangle([cx, cy, cx + 3, cy + card_h], fill=col)
            dr.ellipse([cx + 11, cy + 8, cx + 27, cy + 24], fill=ACCENT)
            n = str(i + 1)
            dr.text((cx + (16 if len(n) == 1 else 13), cy + 10), n,
                    font=_font(True, 11), fill=(255, 255, 255))
            dr.text((cx + 34, cy + 9), f"{e['yr']}.{e['mo']:02d}", font=_font(True, 13), fill=INK)
            dr.text((cx + 84, cy + 10), e['kind'], font=_font(False, 11), fill=INK_FAINT)
            # 등락률 자리를 먼저 확보한 뒤 그만큼 뺀 폭으로 라벨을 자른다.
            # 고정폭으로 자르니 '…임상 제조 시'와 '-10%'가 겹쳐 찍혔다(실제 발생).
            mwid = _font(True, 13).getlength(e['move']) if e['move'] else 0
            if e['move']:
                dr.text((cx + cw2 - 12 - mwid, cy + 9), e['move'], font=_font(True, 13), fill=col)
            lbl_x = cx + 132
            lbl_max = (cx + cw2 - 20 - mwid) - lbl_x
            lbl = e['label']
            if lf.getlength(lbl) > lbl_max:
                while lbl and lf.getlength(lbl + '…') > lbl_max:
                    lbl = lbl[:-1]
                lbl += '…'
            dr.text((lbl_x, cy + 10), lbl, font=lf, fill=INK_DIM)
            for k, ln in enumerate(desc_lines[i]):
                dr.text((cx + 34, cy + 28 + k * 16), ln, font=lf, fill=INK_FAINT)
        y += rows_n * (card_h + 6) + 8

    if mode == 'chart':
        # 연혁이 차트 위로 올라갔으니 아래 목록은 생략하고 그 공간을 노트에 준다.
        note_lines = len(_wrap(h['note'], _font(False, 17), CW - 30)) if h.get('note') else 0
        _note(dr, min(y + 10, BOT - (note_lines * 25 + 26)), h['note'])
        _footer(dr, _history_src(h, ohlcv))
        return im

    dr.text((PAD, y), '주요 연혁', font=_font(True, 17), fill=INK)
    y += 28
    # reserve(노트박스용 예약공간)를 120 고정값으로 뒀더니, 노트가 긴 종목(TSLA —
    # 4줄)에서 실제 필요한 높이(줄수*25+16)가 120을 넘어 노트 하단이 푸터와
    # 겹쳤다(실제 발견 — _timeline의 최소 행간격 보정(겹침 버그 수정) 이후 여유가
    # 줄어들며 드러남). 노트 줄수를 미리 계산해 필요한 만큼만 예약한다.
    note_lines = len(_wrap(h['note'], _font(False, 17), CW - 30)) if h.get('note') else 0
    reserve = max(90, note_lines * 25 + 16 + 34)
    y = _timeline(dr, PAD, y, CW,
                  [(str(yr_t[0]), yr_t[1], '', 'high' if (len(yr_t) > 2 and yr_t[2]) else 'mid')
                   for yr_t in h['timeline']], reserve=reserve)
    _note(dr, y + 6, h['note'])
    _footer(dr, _history_src(h, ohlcv))
    return im


# ── 2. CEO · 리더십 ────────────────────────────────────────────────────
def p02_ceo():
    """CEO·리더십 + 주주구성·희석 + RSU 통합(13p 개편) — 원래 2장을 한 장에.
    CEO 쪽은 경영진 전체 표를 빼고 사진+bio만(전체 명단은 부수정보라 다른 페이지에
    자리를 뺏길 가치가 없다고 판단), 주주구성 쪽은 기관·내부자 항목 수를 줄여
    압축한다. RSU는 원래 없던 섹션 — LEADERSHIP.rsu_note가 있을 때만 표시."""
    LD = D.LEADERSHIP
    c = LD['ceo']
    s = D.SHARES
    own = (L or {}).get('ownership', {})
    yr_now = _ref_year()
    # "창업자가 직접 경영"은 SATL(Kargieman)엔 맞는 말이지만 CEO가 창업자가 아닌
    # 종목(전문경영인 영입 등)에 그대로 쓰면 틀린 말이 된다 — HISTORY.founders에
    # CEO 성이 실제로 있을 때만 "창업자" 문구를 쓴다.
    # 이름이 자동생성 플레이스홀더("(CEO 성명 확인 필요)")면 .split()[-1]이 "필요)"
    # 같은 걸 성(姓)인 척 뽑아내는 버그가 실제로 있었다 — 괄호 들어간 문구는
    # 이름이 아닌 걸로 취급해 빈 값 처리.
    _raw_name = c.get('name') or ''
    ceo_last0 = _raw_name.split()[-1] if _raw_name and '(' not in _raw_name else ''
    is_founder_ceo = bool(ceo_last0) and ceo_last0 in (D.HISTORY.get('founders') or '')
    ceo_since = c.get('since') or 0
    # is_founder_ceo 분기가 since 값 체크 없이 바로 계산해서, since=0(자동추출 실패
    # — PLTR 재생성분 실측 사례)일 때도 "2027년째"처럼 말 안 되는 숫자가 나왔다
    # (else 분기는 c.get('since')로 이미 방어돼 있었는데 if 분기만 빠져있었음).
    sub = (f'창업자가 {yr_now - ceo_since + 1}년째 직접 경영 중' if (is_founder_ceo and ceo_since)
           else f'{ceo_since}년부터 {yr_now - ceo_since + 1}년째 재임 중' if ceo_since
           else '')
    # RSU가 성과조건 없는 표준 베스팅뿐이면(정보가치 없어 rsu_note를 비워둔 경우,
    # AAPL 등) 제목에서도 "RSU"를 빼서 제목이 없는 내용을 예고하지 않게 한다.
    title = 'CEO · 주주구성 · RSU' if LD.get('rsu_note') else 'CEO · 주주구성'
    im, dr = _page(4, title, sub)

    initials = ''.join(w[0] for w in c['name'].split()[:2]).upper()
    # bio 줄수를 먼저 재서 박스 높이를 정한다 — 고정 128px이라 bio가 길면(실제로 넘침,
    # 지적받음) 박스 밖으로 글자가 튀어나갔다.
    bio_font = _font(False, 14)
    bio_lines = _wrap(c['bio'], bio_font, CW - 156) if c.get('bio') else []
    box_h = max(128, 80 + len(bio_lines) * 19 + 14)
    dr.rounded_rectangle([PAD, TOP2, S - PAD, TOP2 + box_h], radius=12, fill=SURFACE)
    C2.photo_circle(im, dr, PAD + 20, TOP2 + 16, 96, (L or {}).get('ceo_photo'), initials)
    dr.text((PAD + 136, TOP2 + 20), c['name'], font=_font(True, 26), fill=INK)
    role_txt = f'{c["role"]} · {ceo_since}년~' if ceo_since else f'{c["role"]}'
    dr.text((PAD + 136, TOP2 + 54), role_txt, font=_font(False, 16), fill=ACCENT)
    for i, ln in enumerate(bio_lines):
        dr.text((PAD + 136, TOP2 + 80 + i * 19), ln, font=bio_font, fill=INK_FAINT)
    y = TOP2 + box_h + 16
    if LD.get('note'):
        y = _wrap_draw(dr, PAD, y, LD['note'], _font(False, 13), INK_DIM, CW, line_h=18) + 6
    if LD.get('rsu_note'):
        dr.text((PAD, y), 'RSU · 보상구조', font=_font(True, 15), fill=INK)
        y = _wrap_draw(dr, PAD, y + 22, LD['rsu_note'], _font(False, 13), INK_DIM, CW, line_h=18) + 10
    people = LD.get('people') or []
    if people:
        # 이 페이지는 아래로 KPI 타일·기관투자자 막대·내부자 표·희석 노트가 줄줄이
        # 이어지는 고정 순서 레이아웃이라, 경영진 표가 길어지면 맨 아래 노트가 푸터를
        # 침범한다(실제 발생: PLTR 경영진 4명이 처음 채워지자마자 겹침). 아래 섹션들이
        # 실제로 쓰는 높이를 빼고 남는 만큼만 이 표에 할당한다.
        n_inst = len(own.get('institutions', [])[:3])
        below = (20                       # 구분선
                 + 82 + 6                 # KPI 타일
                 + (22 + n_inst * 26 + 8 if n_inst else 0)   # 기관투자자 막대
                 + 22 + 4 * 28 + 6        # 내부자 실질보유 표(헤더+최대 3행+그룹행)
                 + 70                     # 내부자 매매 흐름 섹션(신설)
                 + 22 + 3 * 26 + 12       # 잠재 희석요인 제목 + 막대 3개
                 + 120)                   # 희석 노트 박스 + 푸터 여유
        room = BOT - y - 22 - below
        row_h = 30
        max_rows = max(1, int(room // row_h))
        shown = people[:max_rows]
        dr.text((PAD, y), '주요 경영진', font=_font(True, 15), fill=INK)
        if len(shown) < len(people):
            f = _font(False, 12)
            dr.text((PAD + _font(True, 15).getlength('주요 경영진') + 10, y + 3),
                    f'(공시 {len(people)}명 중 상위 {len(shown)}명)', font=f, fill=INK_FAINT)
        # '비고' 칸은 자동생성에서 거의 항상 비어 있었다(LLM이 한 줄 이력을 못 채움).
        # 빈 칸을 두느니 **Form 4의 실제 보유 주식수**를 넣는다 — 투자자가 이 표에서
        # 알고 싶은 건 "이 사람이 자기 회사 주식을 얼마나 들고 있나"이고, 그건 공시에
        # 구조화돼 있어 LLM 0콜로 정확히 나온다.
        held = {}
        try:
            import officers as _off
            for hrow in _off.holdings(CIK):
                held[hrow['name']] = hrow['shares']
        except Exception as e:
            print(f'[경영진 보유주식 조회 실패] {e}')

        def _shares_cell(nm, fallback):
            v = held.get(nm)
            if v is None:                     # 이름 표기가 조금 달라도 성으로 한 번 더
                last = (nm or '').split()[-1] if nm else ''
                for k, s in held.items():
                    if last and last in k:
                        v = s
                        break
            return f'{v:,.0f}주' if v else (fallback or '—')

        y = _table(dr, PAD, y + 22, CW, ['이름', '역할', '보유주식'],
                   [[n, r, _shares_cell(n, b)] for n, r, b in shown], widths=[36, 32, 32],
                   aligns=['l', 'l', 'r'], row_h=row_h)
        y += 6
    y += 6
    dr.line([(PAD, y), (S - PAD, y)], fill=LINE, width=1)
    y += 14

    # ── 한국 (2026-11-04): 13F·위임장(Class A) 자리를 DART 최대주주 현황 + 외국인·기관 수급으로 ──
    #   미국식 그대로 두면 'Class A 기준'·'None개 기관 0.00%' 가 찍혔다(PSK·삼성전자 실측).
    kr_src = ''
    if is_kr(M['ticker']):
        maj = own.get('major') or {}
        mrows = maj.get('rows') or []
        fl = own.get('flow') or {}
        tiles_kr = []
        if mrows:
            tiles_kr.append(('최대주주+특수관계인', f"{(maj.get('total_pct') or 0):.2f}%",
                             f"{len(mrows)}명 · 보통주", 'flat'))
            tiles_kr.append(('최대주주 1인', f"{mrows[0]['pct']:.2f}%", mrows[0]['name'][:16], 'flat'))
        if fl and fl.get('days'):
            net = (fl.get('foreign_amt') or 0) + (fl.get('inst_amt') or 0)
            tiles_kr.append((f"외국인+기관 {fl['days']}일", _m(net, sign=True),
                             f"외국인 {_m(fl.get('foreign_amt') or 0, sign=True)} · 기관 {_m(fl.get('inst_amt') or 0, sign=True)}",
                             'up' if net > 0 else 'dn' if net < 0 else 'flat'))
        if not tiles_kr:
            tiles_kr = [('주주구성', '확인 불가', 'DART 최대주주 현황·수급 응답 없음', 'flat')]
        y = _kpi_tiles(dr, y, tiles_kr, cols=len(tiles_kr), h=82)
        y += 6
        if mrows:
            dr.text((PAD, y), f"최대주주 및 특수관계인 ({maj.get('as_of', 'DART')} 기준)", font=_font(True, 15), fill=INK)
            shown = mrows[:5]
            y = _hbar(dr, PAD, y + 22, CW,
                      [((f"{r['name']} ({r['relate']})" if r.get('relate') else r['name'])[:30], r['pct']) for r in shown],
                      fmt=lambda v: f'{v:.2f}%', label_w=300, bar_h=20, gap=6, color=SEGMENT_COLORS[0])
            if len(mrows) > len(shown):
                rest = sum(r['pct'] for r in mrows[len(shown):])
                dr.text((PAD, y + 2), f"외 {len(mrows) - len(shown)}명 합계 {rest:.2f}%", font=_font(False, 12), fill=INK_FAINT)
                y += 18
            y += 8
        kr_src = (f"지분=DART 최대주주 현황({maj.get('as_of', '없음')})"
                  + (f" · 수급=네이버 증권 {fl.get('from', '')}~{fl.get('to', '')}(순매수 주식수×종가 추정)" if fl else ''))

    inst = [] if kr_src else own.get('institutions', [])[:3]
    px0 = (L or {}).get('proxy', {})
    ceo_row = next((p for p in px0.get('people', []) if ceo_last0 in p['name']), {}) if ceo_last0 else {}
    ceo_tile_label = f'창업자 {ceo_last0}' if is_founder_ceo else (f'CEO {ceo_last0}' if ceo_last0 else 'CEO 지분')
    # "대주주 지분이 얼마인지 안 보인다"는 지적 — 위임장 개인별 실질보유가 안 잡히는
    # 종목(파싱 실패·단일클래스 등)에서도 13F 기관 1위는 항상 있으니 이걸로 대체 표시.
    top_holder = inst[0] if inst else None
    # "임원·이사 전체" 타일은 의미 없다는 지적으로 삭제.
    tiles4 = [
        (ceo_tile_label, f"{(ceo_row.get('a_pct') or 0):.2f}%" if ceo_row.get('a_pct') else '1% 미만',
         'Class A 기준', 'flat'),
        ('기관 지분', f"{(own.get('institutions_pct') or 0)*100:.2f}%",
         f'{own.get("inst_count","—")}개 기관', 'flat'),
    ]
    if top_holder:
        tiles4.append(('최대주주', f"{top_holder['pct']*100:.2f}%", top_holder['name'][:20], 'flat'))
    if not kr_src:
        y = _kpi_tiles(dr, y, tiles4, cols=len(tiles4), h=82)
        y += 6
    if inst:
        dr.text((PAD, y), '주요 기관투자자 (13F 기준)', font=_font(True, 15), fill=INK)
        y = _hbar(dr, PAD, y + 22, CW, [(h['name'][:34], h['pct'] * 100) for h in inst],
                  fmt=lambda v: f'{v:.2f}%', label_w=260, bar_h=20, gap=6, color=SEGMENT_COLORS[0])
        y += 8

    px = {} if kr_src else (L or {}).get('proxy', {})
    people = [p for p in px.get('people', []) if p.get('a_shares') or p.get('b_shares')]
    people = sorted(people, key=lambda p: -(p.get('a_shares') or 0))[:3]
    g = px.get('group')
    if people or g:
        dr.text((PAD, y), f'내부자 실질보유 (위임장 {px.get("as_of","")} 기준)', font=_font(True, 15), fill=INK)
        irows = []
        for p in people:
            ap = f"{p['a_pct']:.2f}%" if p.get('a_pct') else '1% 미만'
            bcol = f"{p['b_shares']:,.0f}주({p['b_pct']:.0f}%)" if p.get('b_shares') else '—'
            irows.append([p['name'][:24], ap, bcol])
        if g:
            irows.append(['임원·이사 전체', f"{g['a_pct']:.2f}%" if g.get('a_pct') else '—',
                          f"{g['b_shares']:,.0f}주(100%)" if g.get('b_shares') else '—'])
        y = _table(dr, PAD, y + 22, CW, ['이름', 'A 지분율', 'Class B'],
                   irows, widths=[46, 27, 27], aligns=['l', 'r', 'r'],
                   # 2026-10-25: row_h=28은 한글 받침이 있는 셀("1% 미만" 등)에서
                   # 행 다음 구분선이 글자 아랫부분을 가로질러 받침이 떨어져 보이는
                   # 버그를 실측으로 재현·확인함(라틴 텍스트는 받침이 없어 안 걸림).
                   # 34는 같은 _table을 쓰는 다른 호출부(1106행)에서 이미 안전하게
                   # 쓰이는 값 — 재현 스크립트로 34에서 깨끗함을 확인 후 적용.
                   row_h=34, emph={len(irows) - 1} if g else set())
        y += 6

    # ── 내부자 매매 흐름 (최근 12개월) — Form 4, LLM 0콜 ──
    # 지분율 스냅샷만으로는 "지금 사고 있나 팔고 있나"를 알 수 없다. 그게 이 페이지에서
    # 투자자가 가장 알고 싶은 것이고, 공시에 구조화돼 있다.
    # 부여(RSU)·세금 원천징수 매도는 신호가 아니므로 **공개시장 매수(P)/매도(S)만** 센다 —
    # 섞으면 "내부자 대량 매도" 같은 잘못된 그림이 나온다.
    try:
        import officers as _off
        _fl = _off.insider_flow(CIK, months=12)
        if _fl['buy_n'] or _fl['sell_n']:
            net = _fl['net_shares']
            col = POS if net > 0 else (NEG if net < 0 else INK_DIM)
            dr.text((PAD, y), '내부자 매매 · 최근 12개월', font=_font(True, 15), fill=INK)
            txt = (f"공개시장 매수 {_fl['buy_n']}건 {_fl['buy_shares']:,.0f}주  ·  "
                   f"매도 {_fl['sell_n']}건 {_fl['sell_shares']:,.0f}주")
            dr.text((PAD, y + 24), txt, font=_font(False, 14), fill=INK_DIM)
            nt = f"순 {net:+,.0f}주"
            dr.text((S - PAD - _font(True, 15).getlength(nt), y + 22), nt,
                    font=_font(True, 15), fill=col)
            if _fl['grant_shares']:
                dr.text((PAD, y + 44),
                        f"(부여·행사 {_fl['grant_shares']:,.0f}주는 보상이라 매수로 세지 않음)",
                        font=_font(False, 12), fill=INK_FAINT)
                y += 18
            y += 50
    except Exception as e:
        print(f'[내부자 매매 조회 실패] {e}')

    dil = s.get('dilution') or []
    dil_tail = ''
    if dil:
        # ⚠️ 막대는 '자리가 있으면' 그린다. 예전엔 무조건 그려서, 위 섹션이 긴 종목
        #    (SATL — 경영진·기관·내부자가 모두 채워짐)에서 막대가 페이지 밖으로
        #    밀려나 마지막 항목이 아예 안 보이고 푸터와 겹쳤다(실측 2026-09-09).
        #    잘린 막대는 틀린 그림이다 — 세 개 중 두 개만 보이면 비중을 오독한다.
        need = 22 + len(dil[:3]) * 26 + 12
        if y + need <= BOT - 16:
            dr.text((PAD, y), '잠재 희석요인', font=_font(True, 15), fill=INK)
            y = _hbar(dr, PAD, y + 22, CW, [(n, v / 1000) for n, v in dil[:3]],
                      fmt=_mB, label_w=260, bar_h=20, gap=6, color=NEG)
        else:
            dil_tail = ' · 잠재 희석: ' + ', '.join(f'{n} {_mB(v / 1000)}' for n, v in dil[:3])
    # 이 페이지는 위쪽 섹션 길이가 종목마다 크게 달라(경영진 명단 유무·기관 수·내부자
    # 행 수) 마지막 노트가 푸터를 침범하는 사고가 반복됐다 — 자리가 없으면 노트 박스
    # 대신 푸터 위 한 줄로 축약해 넣는다(내용을 버리지 않으면서 겹침도 없음).
    # ⚠️ 예전 폴백은 자리가 없으면 노트를 **푸터 한 줄에 통째로** 붙였다. 노트가 짧을
    #    때만 성립하는 처리였고, SATL 처럼 200자가 넘으면 푸터가 화면 밖으로 흘러
    #    위 막대와 겹쳤다(실측 2026-09-09, 4p). 겹침을 없애려던 코드가 더 나쁜 겹침을
    #    만든 것이다. 이제는 자리에 그대로 그리되 **들어가는 줄까지만** 그리고 말줄임을
    #    붙인다 — 잘렸다는 사실이 보이는 게, 푸터에 숨겨져 안 읽히는 것보다 낫다.
    note_txt = s.get('note') or ''
    tail = ''
    if note_txt:
        _lines = _wrap(note_txt, _font(False, 17), CW - 30)
        avail = BOT - (y + 10) - 16
        fit = max(0, int(avail // 25))
        if fit >= len(_lines):
            _note(dr, y + 10, note_txt)
        elif fit >= 1:
            cut = _lines[:fit]
            cut[-1] = cut[-1].rstrip()[:-1] + '…'
            _note(dr, y + 10, ' '.join(cut))
        else:
            tail = ' · 희석요인 상세는 공시 참조'
    photo_src = (L or {}).get('ceo_photo_source') or f'{M["name"]} 공식 홈페이지 경영진 페이지'
    if kr_src:
        _footer(dr, f'CEO 사진={photo_src} · {kr_src}{dil_tail}{tail}')
        return im
    proxy_src = f'DEF 14A({px["as_of"]})' if px.get('as_of') else 'DEF 14A(파싱 불가)'
    _footer(dr, f'CEO 사진={photo_src} · 지분={proxy_src} · 기관=Yahoo Finance 13F{dil_tail}{tail}')
    return im


# ── 4. 사업부문 ────────────────────────────────────────────────────────
def p04_segments():
    """사업부문 + 경쟁사 + TAM 통합(13p 개편) — 원래 3장이던 걸 한 장에 압축.
    셋 다 다 넣으면 안 들어가서 각각 가장 핵심 시각화 하나씩만 남긴다: 부문은
    도넛+미니설명(추이차트 삭제 — 손익계산서 페이지와 중복), 경쟁사는 표 하나만
    (막대차트 2개 삭제), TAM은 기관 추정 막대 하나만(점유율·RPO 삭제). PEERS(CIK맵)나
    TAM.estimates가 비어있으면(자동생성 종목 등) 그 섹션만 조용히 생략한다."""
    g = D.SEGMENTS
    # 부문 매출은 모를 수 있다(None) — 아는 것만 더한다. 예전엔 모르는 값이
    # 0.0으로 채워져 있어 이 합이 항상 성립했지만, 그 0이 곧 거짓 주장이었다.
    seg_rev = sum(v for _, v, _ in g['by_line'] if isinstance(v, (int, float)))
    # 부문별 '비중'은 없어도 회사 전체 매출(다른 페이지와 같은 소스, q_revenue)은
    # 항상 실제 값이 있다 — 부문분해가 안 된다고 총매출까지 "데이터 없음"으로 보이면
    # 실제로 아는 숫자를 숨기는 꼴이라 지적받았다("이제 거짓말까지 하는거니").
    q_rev = (L or {}).get('q_revenue', {})
    real_tot = q_rev[max(q_rev)] if q_rev else None
    if seg_rev:
        sub = f'최근 분기 매출 {_mB(seg_rev)} — {len(g["by_line"])}개 부문'
    elif real_tot:
        sub = f'최근 분기 매출 {_m(real_tot)} — 부문별 비중 데이터 없음'
    else:
        sub = f'{len(g["by_line"])}개 부문 — 매출 데이터 없음'
    im, dr = _page(5, '사업부문 · 경쟁사 · TAM', sub)
    # _donut/_mfmt은 $M 단위 입력을 기대하는데 real_tot는 raw 달러값이라(q_revenue가
    # 원단위) 그대로 넘기면 $64.7M이 "$64.7T"로 찍히는 버그가 실제로 있었다 — /1e6 필요.
    # 부문이 2~3개뿐인 종목은 이 블록이 짧아 페이지 하단이 크게 빈다(실제 지적:
    # "공백 지우게 크기 키우자") — 부문 수가 적을수록 도넛·카드를 키워 여백을 줄인다.
    n_seg = max(1, len(g['detail'][:6]))
    # 카드가 PAD+200에서 시작하므로 도넛 오른쪽 끝(PAD+100+r)이 그 앞에서 멈춰야 한다.
    donut_r = 78 if n_seg >= 4 else 92
    card_min = 58 if n_seg >= 4 else (104 if n_seg <= 2 else 78)
    _donut(dr, PAD + 100, TOP2 + donut_r + 6, donut_r, g['by_line'],
          total_override=(real_tot / 1e6) if (real_tot and not seg_rev) else None)
    y0 = TOP2
    by = y0
    desc_font = _font(False, 13)
    # [:4]로 자르면 5부문 이상인 종목(AAPL 등)에서 부제("N개 부문")와 실제 카드 수가
    # 안 맞는다(실제 발견: "5개 부문"인데 카드는 4개만 보임) — 부제와 항상 일치하게
    # 상한을 6으로 올린다(그 이상은 카드 자체가 극히 드물고, 있어도 아래 섹션 자리가
    # 부족해지므로 여전히 안전판은 둠).
    for i, (name, desc, cur, prior) in enumerate(g['detail'][:6]):
        n_lines = min(len(_wrap(desc, desc_font, CW - 232)), 2)
        box_h = max(card_min, 26 + n_lines * 18 + 10)
        dr.rounded_rectangle([PAD + 200, by, S - PAD, by + box_h], radius=8, fill=SURFACE)
        dr.rectangle([PAD + 200, by, PAD + 203, by + box_h], fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
        dr.text((PAD + 216, by + 8), name, font=_font(True, 15), fill=INK)
        if cur and prior:
            yoy = (cur - prior) / prior * 100
            t = f'{_mB(cur)} ({yoy:+.0f}%)'
            f = _font(True, 13)
            dr.text((S - PAD - 14 - f.getlength(t), by + 9), t, font=f, fill=POS if yoy > 0 else NEG)
        _wrap_draw(dr, PAD + 216, by + 28, desc, desc_font, INK_DIM, CW - 232, line_h=17)
        by += box_h + 8
    y = max(by, TOP2 + 180) + 10
    # "경쟁사" — TAM과 같은 이유로 헤더는 항상 표시(제목("사업부문·경쟁사·TAM")이
    # 이 섹션을 명시하는데 후보가 하나도 안 잡히면(예: AAPL — 10-K가 경쟁사를
    # 구체적으로 안 나열함) 이전엔 아무것도 안 그려 페이지 반이 통째로 빈 채
    # 방치됐다(실제 발견) — 없으면 없다고 명시.
    comp = g.get('competitors') or []
    dr.text((PAD, y), '경쟁사', font=_font(True, 16), fill=INK)
    y += 24
    if comp:
        dr.text((PAD, y), ', '.join(comp[:8]) + ('  외' if len(comp) > 8 else ''),
                font=_font(False, 14), fill=INK_DIM)
    else:
        # 헤더만 덩그러니 남으면 "왜 비었지"가 된다 — 없는 이유를 한 줄로 밝힌다
        # (TAM 섹션에서 이미 쓰던 것과 같은 패턴).
        dr.text((PAD, y), f'{_annual_src(long=True)}가 경쟁사를 실명으로 나열하지 않음 — 추측으로 채우지 않음',
                font=_font(False, 14), fill=INK_FAINT)
    y += 26
    dr.line([(PAD, y), (S - PAD, y)], fill=LINE, width=1)
    y += 16

    # ── 경쟁사 재무비교 — CIK 등록된 PEERS 있을 때만, 없으면 그 이유를 명시 ──
    if PEERS:
        pf = (L or {}).get('peers', {})
        ann = (L or {}).get('annual', {})
        cons = (L or {}).get('consensus', {})
        names_map = getattr(D, 'PEERS', {}).get('names', {})
        tks = [M['ticker']] + list(PEERS.keys())
        disp = [M['name'].split(',')[0].split(' Inc')[0]] + [names_map.get(t, t) for t in PEERS]
        rows = []
        for i, t in enumerate(tks):
            a = ann if t == M['ticker'] else pf.get(t, {}).get('ann', {})
            mc = cons.get('market_cap') if t == M['ticker'] else pf.get(t, {}).get('mktcap')
            ys = sorted(a.get('revenue', {}))
            r_last = a.get('revenue', {}).get(ys[-1]) if ys else None
            rows.append([disp[i], _m(mc, dp=2) if mc else '—', _m(r_last),
                        f'{mc/r_last:.1f}배' if mc and r_last else '—'])
        dr.text((PAD, y), '경쟁사 비교 (최근 회계연도)', font=_font(True, 16), fill=INK)
        y = _table(dr, PAD, y + 24, CW, ['회사', '시가총액', '매출', 'PSR'],
                   rows, widths=[34, 22, 22, 22], row_h=32, emph={0})
        y += 6
    elif comp:
        # 경쟁사 이름은 있는데(사람이 보충) 재무비교 표가 없는 경우 — 이유가
        # "10-K에 이름이 없어서"가 아니라 "그 경쟁사가 SEC 등록 기업이 아니라서"로
        # 완전히 다르므로 별도 문구(예: AAPL — 삼성전자·샤오미는 각각 한국·홍콩
        # 상장이라 SEC XBRL 재무제표 자체가 없음).
        y = _note(dr, y,
                  ('재무비교 표 없음 — 위 경쟁사가 전부 국내 미상장(해외 거래소 상장 또는 비상장)이라 '
                   'DART 재무제표를 못 씀. 숫자를 지어내는 대신 비워둠'
                   if CURRENCY == 'KRW' else
                   '재무비교 표 없음 — 위 경쟁사가 전부 비SEC 등록 기업(해외 거래소 상장 또는'
                   ' 비상장)이라 SEC XBRL 재무제표를 못 씀. 숫자를 지어내는 대신 비워둠'),
                  interp=False)
    else:
        y = _note(dr, y,
                  f'경쟁사 비교 데이터 없음 — {_fin_src("연차")} 원문에 구체적 경쟁사명이 안 나옴'
                  '(다수 시장에서 "경쟁이 치열함"으로만 서술) 또는 후보 시총이 비교 의미 없는 체급 차이',
                  interp=False)

    # ── TAM — 헤더는 항상 표시(그래야 이 블록이 TAM 섹션인 게 명확함, 이전엔 헤더
    # 없이 노트만 떠서 "TAM은 왜 없냐"는 지적을 받았다). 기관별 막대는 estimates가
    # 있을 때만, 없으면(자동생성 종목 대부분) 노트 텍스트만.
    t = D.TAM
    ests = t.get('estimates') or []
    dr.text((PAD, y), f'TAM — {t.get("label") or "시장규모"}', font=_font(True, 16), fill=INK)
    y += 24
    if ests:
        # TAM만은 원화 종목에서도 **$ 그대로** 둔다. 시장규모는 Grand View Research 같은
        # 글로벌 리서치가 USD로 발표한 수치라, 원으로 바꾸려면 우리가 환율을 갖다 붙여야
        # 하고 그건 출처가 말하지 않은 숫자를 만드는 것이다. 통화를 명시해 혼동을 막는다.
        y = _hbar(dr, PAD, y, CW, [(n, v) for n, v, _ in ests],
                  fmt=lambda v: f'${v:.1f}B', label_w=240, bar_h=20, gap=7, color=SEGMENT_COLORS[1])
        y += 4
    _note(dr, y, t.get('share_note') or t.get('note', '') or '리서치 데이터 없음 — 사용자 보충 필요')
    _footer(dr, f'{g["src"]} · 경쟁사={t.get("src", g["src"])}')
    return im


# ── 5. 기술적 분석 ─────────────────────────────────────────────────────
def _technical_note(t):
    """52주 위치·이평선 관계에서 해석 문장을 그 자리에서 만든다(하드코딩하면 다른
    종목엔 틀린 말이 됨 — PLTR 검증에서 실제로 드러난 문제와 동일 패턴)."""
    hi_gap, lo_gap = t['from_high_pct'], t['from_low_pct']
    parts = [f"주가는 52주 고점 대비 {hi_gap:+.0f}%, 저점 대비로는 {lo_gap:+.0f}%. "]
    if t['trend'] == '하락':
        parts.append('50일선·200일선 모두 아래로 이탈해 단기 추세는 하락 쪽.')
    elif t['trend'] == '상승':
        parts.append('50일선·200일선 모두 위에 있어 단기 추세는 상승 쪽.')
    else:
        parts.append('50일선·200일선이 엇갈려 있어 추세는 혼조.')
    return ''.join(parts)


def p05_outlook():
    """종합평가(13p 개편, 신설) — 기존 '기술적분석'·'체크포인트' 단독페이지를 합치고
    애널리스트 목표주가·정성적 종합평가를 새로 추가. 캔들차트는 연혁 페이지로 이미
    옮겼으니 여기선 반복 안 함."""
    t = (L or {}).get('technical', {})
    cons = (L or {}).get('consensus', {})
    _pa = _px_asof()
    im, dr = _page(1, '종합평가', f'{_pa} 종가 기준' if _pa else '종가 기준(가격 기준일 확인 불가)')
    tiles = []
    if t:
        tiles.append(('현재가', _px(t["price"]), f'52주 {_px(t["lo52"])}~{_px(t["hi52"])}', 'flat'))
    tm = cons.get('target_mean')
    rec = cons.get('recommendation')
    if tm and t:
        upside = (tm / t['price'] - 1) * 100
        rec_kr = {'strong_buy': '적극매수', 'buy': '매수', 'hold': '중립', 'underperform': '비중축소',
                  'sell': '매도'}.get(rec, rec) if rec else ''
        sub = f'{upside:+.0f}% ({_px(cons.get("target_low", 0), dp=0)}~{_px(cons.get("target_high", 0), dp=0)})'
        if rec_kr:
            sub += f' · {rec_kr} {cons.get("n_analysts_price","—")}명'
        tiles.append(('애널리스트 목표주가', _px(tm), sub, 'up' if upside > 0 else 'dn'))
    if tiles:
        y = _kpi_tiles(dr, TOP2, tiles, cols=len(tiles), h=100)
    else:
        y = TOP2
    y += 10
    summary = getattr(D, 'SUMMARY', '')
    if summary:
        # 회색 문단이 그냥 줄글로 이어져 안 정돈돼 보인다는 지적 — 줄마다 불릿을 달아
        # 목록처럼 정리한다. ▸ 같은 특수기호는 이 폰트에 글리프가 없어 빈 네모(□)로
        # 깨졌다(⚠️ 이모지 때와 같은 클래스의 문제) — 폰트가 확실히 지원하는 "-"만 사용.
        bulleted = '\n'.join(f'- {ln}' for ln in summary.split('\n') if ln)
        y = _wrap_draw(dr, PAD, y, bulleted, _font(False, 15), INK_DIM, CW, line_h=21) + 8
    if t:
        dr.text((PAD, y), _technical_note(t), font=_font(False, 13), fill=INK_FAINT)
        y += 26
    dr.line([(PAD, y), (S - PAD, y)], fill=LINE, width=1)
    y += 14
    dr.text((PAD, y), '향후 체크포인트', font=_font(True, 17), fill=INK)
    # 타임라인 점 색(주황=high/회색=mid)이 무슨 뜻인지 범례 없이 나가서 "이거 뭐임"
    # 소리를 들었다 — 제목 옆에 작은 범례를 단다.
    lx = PAD + _font(True, 17).getlength('향후 체크포인트') + 24
    for lbl, col in (('핵심', ACCENT), ('참고', INK_FAINT)):
        dr.ellipse([lx, y + 3, lx + 12, y + 15], fill=col)
        dr.text((lx + 18, y), lbl, font=_font(False, 13), fill=INK_FAINT)
        lx += 18 + _font(False, 13).getlength(lbl) + 16
    y += 30
    # 체크포인트가 데이터 파일에 적힌 순서 그대로 그려져서 "2027년이 2026년보다 위"처럼
    # 날짜 역순으로 보이는 문제가 있었다(실제 지적받음) — 항상 연도순으로 정렬해서 그린다.
    y = _timeline(dr, PAD, y, CW, sorted(D.CHECKPOINTS, key=lambda c: _s(c[0])), reserve=90)
    _note(dr, y + 4, D.CHECKPOINT_NOTE)
    # 체크포인트 출처는 데이터 파일이 직접 밝히게 한다. SRC['PR']로 고정해두면,
    # 컨센서스에서 유도한 항목(autogen_kr이 만드는 '연간 컨센서스 달성 여부' 등)에까지
    # 실적공시가 출처인 것처럼 찍힌다 — 숫자마다 출처가 이 카드의 1번 규칙이다.
    cp_src = getattr(D, 'CHECKPOINT_SRC', '') or D.SRC['PR'] + ' 로드맵 항목'
    _footer(dr, f'목표주가=Yahoo Finance 애널리스트 컨센서스 · 체크포인트={cp_src}')
    return im


# ── 6. 실적 · 어닝콜 ───────────────────────────────────────────────────
def p06_results():
    r = D.RESULTS
    quotes = r.get('quotes') or []
    # 한국은 어닝콜 전문이 무료로 공개되지 않는다 — 실적 원천이 영업(잠정)실적 공정공시다.
    # 제목에 '어닝콜'을 박아두면 인용이 한 줄도 없는 카드에 어닝콜이라 써 있게 된다.
    kr_mkt = CURRENCY == 'KRW'
    title = '최근 실적' if kr_mkt else '최근 실적 · 어닝콜'
    facts_head = '실적 공시 핵심 숫자' if kr_mkt else '어닝콜 핵심 숫자 · 계약'
    im, dr = _page(2, title, f'{r.get("period","최근 분기")} — 숫자와 변화폭')
    rows = [(k, v, chg, d) for k, v, chg, d in r['kpis']]
    y = _kpi_tiles(dr, TOP2, rows, cols=3, h=104)
    y += 10
    dr.text((PAD, y), facts_head, font=_font(True, 19), fill=INK)
    y = _table(dr, PAD, y + 30, CW, ['항목', '내용', '금액·수치'],
               r['facts'], widths=[26, 50, 24], aligns=['l', 'l', 'r'], row_h=34)
    y += 8
    # 인용이 없으면 제목도 띄우지 않는다 — 빈 '경영진 발언' 머리글만 남아 페이지
    # 하단 절반이 통째로 비는 걸 실측으로 확인했다(에코프로비엠).
    if quotes:
        dr.text((PAD, y), '경영진 발언', font=_font(True, 19), fill=INK)
        y += 30
        # 영문 원문은 삭제 — 한글 번역만(사용자 피드백: 인스타 독자는 원문 안 읽고 넘어감).
        for q in quotes[:2]:
            who, kr = q[0], q[1]
            dr.rectangle([PAD, y, PAD + 3, y + 18], fill=ACCENT)
            dr.text((PAD + 13, y), who, font=_font(True, 13), fill=ACCENT)
            y = _wrap_draw(dr, PAD + 13, y + 20, f'“{kr}”', _font(False, 14), INK_DIM, CW - 20, line_h=19)
            y += 12
    elif kr_mkt:
        # 빈 자리를 그냥 두지 않고 **왜 없는지**를 쓴다. 원문 링크를 주면 독자가
        # 직접 확인할 수 있어, 인용이 없다는 게 정보 부족이 아니라 출처 명시가 된다.
        y = _note(dr, y + 4,
                  '한국 상장사는 어닝콜 전문을 무료로 공개하지 않아 경영진 발언 인용은 싣지 않음. '
                  '위 숫자는 회사가 제출한 영업(잠정)실적 공정공시 원문 그대로임'
                  + (f' — {r["url"]}' if r.get('url') else '.'))
    _footer(dr, r['src'])
    return im


def _valuation_note(psr, labels, profitable, has_book, per=None, pbr=None, latest_eq=None):
    """PLTR 검증에서 실제로 드러난 문제: 이 해석 문구가 satl16_data.py에 SATL 얘기로
    고정돼 있어서, 다른 종목(흑자·정상자본인 PLTR)에 그대로 쓰면 "PER·PBR 산출 불가"라는
    틀린 말이 나왔다. 밸류에이션 해석은 회사마다 다른 손이 아니라 방금 계산한 실제
    배수에서 뽑아야 다른 종목에서도 맞는 말을 한다(15p 퀀트 노트와 같은 패턴)."""
    psr_now = next((v for v in psr if v is not None), None)
    psr_last = psr[-1]
    trend = None
    if psr_now is not None and psr_last is not None and psr_now:
        trend = f'{psr_now:.0f}배({labels[0]}) → {psr_last:.0f}배({labels[-1]})'

    if profitable and per:
        per_now = next((v for v in per if v is not None), None)
        per_last = next((v for v in reversed(per) if v is not None), None)
        parts = []
        if per_now and per_last:
            parts.append(f'PER은 {per_now:.0f}배에서 컨센서스대로면 {per_last:.0f}배까지 하락. ')
        if trend:
            parts.append(f'매출 기준 PSR도 {trend}로 같은 방향. ')
        parts.append('다만 두 배수 모두 이미 상당한 미래 이익 성장을 선반영한 상태 — '
                     '컨센서스가 못 미치면 배수가 아니라 주가가 조정되는 쪽.')
        return ''.join(parts)

    if has_book and pbr:
        pbr_now = next((v for v in pbr if v is not None), None)
        pbr_last = next((v for v in reversed(pbr) if v is not None), None)
        parts = ['아직 이익 기준 배수(PER)는 못 쓰지만 자본 기준(PBR)은 계산됨. ']
        if pbr_now and pbr_last:
            parts.append(f'PBR {pbr_now:.1f}배({labels[0]}) → {pbr_last:.1f}배(최근)로 변화. ')
        if trend:
            parts.append(f'매출 기준 PSR은 {trend}.')
        return ''.join(parts)

    parts = ['PER·PBR은 산출 자체가 불가(적자']
    if latest_eq is not None and latest_eq < 0:
        parts.append(f' + 자본잠식 {_mB(latest_eq/1e6, sign=True)})')
    else:
        parts.append(')')
    parts.append('. 남는 잣대는 PSR 하나뿐인데, ')
    if trend:
        parts.append(f'컨센서스대로면 {trend}로 하락. ')
    parts.append('즉 지금 주가는 컨센서스 매출을 상당 부분 반영한 값 — 컨센서스가 깨지면 '
                 '배수가 아니라 주가가 조정되는 쪽.')
    return ''.join(parts)


# ── 7. 밸류에이션 ──────────────────────────────────────────────────────
def p07_valuation():
    cons = (L or {}).get('consensus', {})
    ann = (L or {}).get('annual', {})
    mc = cons.get('market_cap') or 0
    ev = cons.get('ev') or 0
    im, dr = _page(8, '밸류에이션', '실적 3년 + 컨센서스 2년 (빗금=애널리스트 추정)')

    yrs = _fy_years(3, ('revenue',))
    est = _est_years(yrs)
    rev = [ann.get('revenue', {}).get(y) for y in yrs]
    p = cons.get('periods', {})
    rev += [p.get('0y', {}).get('rev'), p.get('+1y', {}).get('rev')]
    labels = [str(v) for v in yrs] + est
    psr = [(mc / v if v else None) for v in rev]
    evs = [(ev / v if v else None) for v in rev]

    # 차트 높이 176은 페이지 하단에 200px 넘는 빈 공백을 남겼다(9~11p에서 이미 한 번
    # 지적받아 고친 것과 같은 문제가 8p에만 남아 있었음) — 두 차트를 키워 공백을 메운다.
    # 다만 ②는 분기마다 위에 붙는 설명 분량이 달라(PBR 분기는 노트 한 칸이 더 들어감)
    # 고정값을 쓰면 어떤 종목에선 공백, 어떤 종목에선 푸터 침범이 된다(SATL 실측:
    # 해석 노트가 캔버스 밖으로 넘어감) — 남은 세로 공간에서 역산한다.
    CH = 262

    def _fit_h(top, reserve=130):
        """top에서 시작하는 차트에 줄 수 있는 최대 높이(아래 해석 노트·푸터 자리 확보)."""
        return int(max(120, min(CH, BOT - reserve - top)))

    def _na(dr, cx, cy, txt='데이터없음'):
        """컨센서스가 없는 미래 칸에 찍는 라벨. 예전엔 그냥 텍스트만 찍어서 PER/EPS
        라인·값라벨과 정통으로 겹쳐 뭉개졌다(PLTR 실측: 2026E·2027E 칸에서 '데이터없음'과
        '$1.58'이 한 덩어리로 보임) — 막대 라벨에 이미 쓰던 배경 패치(halo) 기법을
        똑같이 적용해 뭐가 지나가든 항상 또렷하게 만든다."""
        f = _font(False, 13)
        w = f.getlength(txt)
        dr.rectangle([cx - w / 2 - 5, cy - 3, cx + w / 2 + 5, cy + 19], fill=BG)
        dr.text((cx - w / 2, cy), txt, font=f, fill=INK_FAINT)

    dr.text((PAD, TOP2), '① 매출 & PSR', font=_font(True, 17), fill=INK)
    y = C2.dual_axis(dr, PAD, TOP2 + 46, CW, CH, labels, [v / 1e6 if v else None for v in rev], psr,
                     _mB, lambda v: f'{v:.0f}배', est_from=len(yrs),
                     bar_name='매출', line_name='PSR(현재 시총 기준)')
    y += 16

    # ② 종목 상태에 따라 자동 분기 — 흑자면 이익·PER, 자본 있으면 자기자본·PBR,
    #    둘 다 아니면(SATL) 적자 축소 궤적. 모든 종목에 같은 템플릿을 쓰기 위한 조건부 구성.
    # oy는 반드시 ①(yrs)과 같은 연도 구간을 써야 두 차트 x축이 맞는다 — 예전엔 oy가
    # 2022년부터라 ①(2023년부터)과 시작연도·칸수가 어긋났다(실제 지적받은 버그).
    oy = list(yrs)
    p_ann, p_qtr, p_label, p_alt = _profit_series()
    op = [p_ann.get(v) for v in oy]
    eq = [ann.get('equity', {}).get(v) for v in oy]
    # 판정은 반드시 '최신 분기' 기준. 연말값만 보면 SATL처럼 FY2025 자본 +$60.5M인데
    # Q1 2026에 자본잠식(-$25.5M)이 난 경우 PBR을 그려버려 같은 페이지 안에서 해설과 모순된다.
    q_eq = (L or {}).get('quarterly', {}).get('equity', {})
    q_op = p_qtr
    latest_eq = q_eq[max(q_eq)] if q_eq else eq[-1]
    latest_op = q_op[max(q_op)] if q_op else op[-1]
    # "최근 분기 흑자"만 보고 이익·PER 차트를 그리면, 표시 구간(연간 3년)이 전부 적자인
    # 종목에서 막대가 하나도 안 그려지고(음수는 높이 0) PER도 산출 불가라 차트가 통째로
    # 빈 채 라벨만 베이스라인에 눕는다(SATL 실측: -$69M·-$52M·-$31M만 덩그러니).
    # 차트에 실제로 그릴 게 있을 때만 이 분기를 쓴다.
    profitable = (latest_op is not None and latest_op > 0
                  and any((v or 0) > 0 for v in op))
    has_book = latest_eq is not None and latest_eq > 0

    per = pbr = None
    if profitable:
        netinc = [ann.get('netinc', {}).get(v) for v in oy]
        # 과거분은 '현재 시총 ÷ 그 해 순이익'(=PSR과 같은 방식으로 시총 고정, 실적만 변화).
        # price/EPS와 사실상 동일한 배수라 컨센서스(price/EPS 기반) 구간과 이어붙여도 왜곡 없음.
        hist_per = [(mc / v if v and v > 0 else None) for v in netinc]
        eps_series = [p.get('0y', {}).get('eps'), p.get('+1y', {}).get('eps')]
        fwd_per = [(cons.get('price') / e if e and e > 0 else None) for e in eps_series]
        per = hist_per + fwd_per
        # EPS 라인 추가(요청) — 과거분은 XBRL 실측(annual_series에 'eps' 태그 신규
        # 등록), 미래분은 위에서 이미 구해둔 컨센서스 eps_series 재사용.
        hist_eps = [ann.get('eps', {}).get(v) for v in oy]
        eps_line = hist_eps + eps_series
        dr.text((PAD, y), f'② {p_label} & PER · EPS — 이익 대비 몇 배에 거래되는가',
                font=_font(True, 17), fill=INK)
        chart_top = y + 46
        ch2 = _fit_h(chart_top)
        y = C2.dual_axis(dr, PAD, chart_top, CW, ch2,
                         [str(v) for v in oy] + est,
                         [v / 1e6 if v else None for v in op] + [None, None], per,
                         lambda v: _mB(v, 0), lambda v: f'{v:.0f}배', est_from=len(oy),
                         bar_name=p_label, line_name='PER',
                         line2=eps_line, line2_fmt=_px, line2_name='EPS(희석)',
                         # PER(수십~수천 배)과 EPS($ 단위)는 자릿수가 달라 한 축에 얹으면
                         # EPS가 베이스라인에 눌려 궤적이 안 보이고 라벨만 쌓인다 —
                         # 별도 축으로 그려야 "EPS가 실제로 늘고 있다"가 보인다.
                         line2_own_scale=True)
        # 2026E·2027E 영업이익 막대가 빈 이유(무료 데이터엔 영업이익 컨센서스가 없어
        # EPS 기반 PER만 이어짐) — PBR 분기 쪽엔 이미 "데이터없음" 명시가 있었는데
        # 이 흑자(profitable) 분기엔 빠져있어 그냥 렌더 버그처럼 보였다(실제 지적
        # 대상: AAPL — 미래 두 칸이 아무 설명 없이 통째로 비어 보임). PER이 우하향
        # 추세라 chart_top 기준 고정 y(과거엔 +80)는 PER 라인·라벨과 겹칠 수 있다
        # (실제 발견) — 라인 라벨은 base-16 아래로는 안 내려가니, 베이스라인
        # 바로 위(막대가 있었다면 밑동이 있었을 자리)에 둬 겹칠 여지를 없앤다.
        # 예전엔 베이스라인 바로 위(chart_top+176-20)에 찍었는데, 거기가 바로 EPS
        # 값라벨 자리라 정통으로 겹쳤다(PLTR 실측). PER은 좌상단→우하단으로 내려오므로
        # 미래 두 칸의 상단부는 항상 비어 있다 — 거기에 halo와 함께 찍는다.
        gap_x = CW / (len(oy) + 2)
        for i in range(len(oy), len(oy) + 2):
            _na(dr, PAD + i * gap_x + gap_x / 2, chart_top + 34)
    elif has_book:
        pbr = [(mc / v if v and v > 0 else None) for v in eq]
        # EPS 컨센서스를 실제로 확인해보니 2026E는 흑자(+$0.28), 2027E는 다시 적자(-$2.37)
        # — "27~28년도 적자라 PER이 없냐"는 질문에 대한 정확한 답은 "아니다, 2026E는
        # 흑자 추정인데 1년짜리라 지속가능한 지표로 보기엔 무리가 있어 PBR을 기본으로
        # 유지"임. 이 사실을 노트에 명시.
        p = cons.get('periods', {})
        eps0, eps1 = (p.get('0y') or {}).get('eps'), (p.get('+1y') or {}).get('eps')
        # 예전엔 "2026E 흑자, 2027E 다시 적자"라는 SATL 한 종목의 실제 상황이 문장에
        # 통째로 박혀 있었다 — 다른 종목에 그대로 붙으면 명백한 거짓말이 된다.
        # 연도도 흑/적자 판정도 실제 값에서 만든다(같은 클래스 버그를 7p에서 한 번
        # 고쳤는데 이 분기만 남아 있었음).
        def _sign_kr(v):
            return '흑자' if (v or 0) > 0 else '적자'
        eps_line = (f'참고로 EPS 컨센서스는 {est[0]} {eps0:+.2f}({_sign_kr(eps0)}), '
                    f'{est[1]} {eps1:+.2f}({_sign_kr(eps1)}).'
                    + (' 흑자 구간이 1년뿐이라 지속 흑자전환으로 보기엔 이름'
                       if (eps0 or 0) > 0 >= (eps1 or 0) else '')
                    if (eps0 is not None and eps1 is not None) else '')
        dr.text((PAD, y), '② 자기자본 & PBR (PER 대체 지표)', font=_font(True, 17), fill=INK)
        y += 30
        # "적자라서"와 "이익 태그 자체가 없어서"는 전혀 다른 상황인데 한 문장으로
        # 뭉뚱그리면 흑자 기업(은행·리츠)에 "적자"라고 쓰는 거짓말이 된다.
        why = ('영업이익·순이익 태그를 공시에서 못 찾아'
               if not p_ann else '최근 분기 적자라')
        y = _note(dr, y, f'{why} PER(이익 배수)이 정의되지 않아 장부가 기준 PBR로 대체. '
                         f'{est[0]}·{est[1]} 자기자본 막대가 빈 것은 장부가 컨센서스가 무료 데이터에 '
                         '없기 때문(Yahoo는 매출·EPS만 제공).\n'
                         f'{eps_line}')
        y += 14
        chart_top = y
        y = C2.dual_axis(dr, PAD, y, CW, _fit_h(chart_top), [str(v) for v in oy] + est,
                         [v / 1e6 if v else None for v in eq] + [None, None], pbr + [None, None],
                         lambda v: _mB(v, 0), lambda v: f'{v:.1f}배', est_from=len(oy),
                         bar_name='자기자본', line_name='PBR')
        # 빈 칸에 "데이터없음"을 직접 표시(피드백: 그냥 비워두지 말고 없다고 명시) —
        # 막대 영역 세로 중앙(chart_top 기준, 리턴된 y는 범례 등 포함해 위치 계산이
        # 부정확해지므로 호출 전 y를 따로 저장해 기준으로 삼는다.
        gap_x = CW / (len(oy) + 2)
        for i in range(len(oy), len(oy) + 2):
            _na(dr, PAD + i * gap_x + gap_x / 2, chart_top + 80)
        y += 20
    else:
        # 영업이익 컨센서스는 무료 소스에 없다(Yahoo는 매출·EPS만 제공).
        # EPS × 주식수로 순손익 규모를 환산해 같은 $M 축에 올리되, 순손익임을 명시한다.
        sh = cons.get('shares_out') or 0
        est_loss = [abs(p.get(k, {}).get('eps') or 0) * sh / 1e6 or None for k in ('0y', '+1y')]
        dr.text((PAD, y), f'② 손실 축소 궤적 — 실적은 {p_label} 손실, 컨센서스는 순손실(환산)',
                font=_font(True, 17), fill=INK)
        y = C2.dual_axis(dr, PAD, y + 46, CW, _fit_h(y + 46, reserve=190),
                         [str(v) for v in oy] + est,
                         [abs(v) / 1e6 if v else None for v in op] + est_loss,
                         [None] * (len(oy) + 2),
                         lambda v: f'-{_mB(v, 0)}', lambda v: '', est_from=len(oy),
                         bar_name='손실 규모(절대값)', bar_color=NEG)
        y += 4
        # EPS 컨센서스가 한쪽만 있거나 아예 없는 종목에서 :+.2f 포맷이 None을 만나
        # TypeError로 페이지가 통째로 죽던 자리 — 값이 있을 때만 문구를 만든다.
        e0, e1 = (p.get('0y') or {}).get('eps'), (p.get('+1y') or {}).get('eps')
        eps_txt = ' / '.join(f'{lb} {ev:+.2f}' for lb, ev in zip(est, (e0, e1)) if ev is not None)
        dr.text((PAD, y), '※ 영업이익 컨센서스는 무료 데이터에 없어 EPS 컨센서스'
                          f'({eps_txt}) × 주식수 {sh/1e6:.0f}M로 순손실 환산 — 영업손실과 직접 비교는 불가'
                if eps_txt else '※ 영업이익·EPS 컨센서스 모두 무료 데이터에 없음 — 미래 구간은 빈 칸',
                font=_font(False, 13), fill=INK_FAINT)
        y += 22
        y += 8
        dr.text((PAD, y), f'PER — 적자로 산출 불가   ·   PBR — 최신 분기 자기자본 {_m(latest_eq)}'
                          f'(자본잠식)으로 산출 불가',
                font=_font(True, 15), fill=INK_FAINT)
        y += 26
    note = _valuation_note(psr, labels, profitable, has_book, per=per, pbr=pbr, latest_eq=latest_eq)
    _note(dr, y + 6, note)
    _footer(dr, f'실적={_fin_src("짧게")} · 컨센서스=Yahoo Finance 애널리스트 {cons.get("analysts","—")}인(당해·차년 2개년까지만 무료 제공) · 시총={_px_asof() or "기준일 확인 불가"}')
    return im


# ── 8. CANSLIM (자료 대기) ─────────────────────────────────────────────
def p08_canslim():
    ann = (L or {}).get('annual', {})
    c_ann, qop, c_label, c_alt = _profit_series()
    im, dr = _page(7, 'CANSLIM', '체슬리투자자문 방식 · C+A+N 합산')

    def _fy_q(datestr):
        # 분기말 날짜(YYYY-MM-DD)에서 실제 분기 번호를 뽑는다 — "Q1"을 하드코딩하면
        # 최근분기가 Q1이 아닌 종목(TSLA는 Q2)에서 라벨이 실적과 안 맞게 된다.
        y, m = int(datestr[:4]), int(datestr[5:7])
        q = {3: 1, 6: 2, 9: 3, 12: 4}.get(m, (m - 1) // 3 + 1)
        return f'FY{y % 100} Q{q}'

    ends = sorted(qop)
    q_cur = qop.get(ends[-1]) if ends else None
    ly = f'{int(ends[-1][:4]) - 1}{ends[-1][4:]}' if ends else None
    q_prior = qop.get(ly)
    if q_prior is None and ends:
        # 정확히 1년 전 같은 날짜 문자열이 없으면(AAPL처럼 분기말이 "매월 마지막
        # 토요일" 등 날짜가 매년 며칠씩 밀리는 회사) 전년동기 자체가 없는 걸로
        # 처리돼 YoY가 통째로 "—"·0점 처리됐다 — RESULTS.kpis(autogen._kpi_rows)는
        # 같은 문제를 연+월만 맞춰 찾는 걸로 이미 우회하고 있었는데 CANSLIM만 이
        # 완화 로직이 없었다(실제 발견: AAPL — 페이지 2는 영업이익 +27% YoY인데
        # CANSLIM C점수는 데이터없음으로 모순). 같은 연+월(±1일 오차 흡수) 후보로 대체.
        ly_ym = ly[:7]
        cands = [e for e in ends if e[:7] == ly_ym]
        if cands:
            ly = cands[0]
            q_prior = qop.get(ly)
    cur_lbl = _fy_q(ends[-1]) if ends else 'FY? Q?'
    prior_lbl = _fy_q(ly) if ly else 'FY? Q?'
    # A(연간 영업이익 CAGR) 구간도 연도를 박아두면 안 된다 — 예전엔 2023·2025 고정이라
    # (a) FY2025를 아직 신고 안 한 종목은 a_last=None으로 A가 통째로 0점, (b) 2024년
    # 상장 종목은 a_first=None으로 같은 결과, (c) 해가 바뀌면 전 종목이 한 해씩 밀렸다.
    ay = _fy_years(3, ('opinc', 'netinc'))
    a_first = c_ann.get(ay[0])
    a_last = c_ann.get(ay[-1])
    r = CL.evaluate(q_cur, q_prior, a_first, a_last, D.CANSLIM_N, a_years=max(1, len(ay) - 1))

    # 총점 배지 — "총점 9"만 간단히, 티커·페이지수 바로 밑(우측 상단)에 작게.
    # C/A/N 각 점수는 아래 C·A 카드와 N표에 이미 나오니 배지엔 총점만.
    # "가위로 오려붙인 듯한" 지적의 원인: rounded_rectangle(둥근 모서리) 위에 sharp
    # rectangle(각진 모서리) 액센트바를 겹쳐 그리면 작은 박스에서 모서리가 어긋나 보인다
    # — 라운딩을 아예 없애고 각진 사각형으로만 통일해 어긋날 여지 자체를 없앤다.
    # 배지 총점을 r['total'](반올림 전 합, 예: 21.6+2.9+0=24.5→24)로 찍으면 카드에
    # 표시되는 개별 점수(반올림된 22+3+0=25)와 안 맞는 모순이 생겼다(실제 지적:
    # "C+A 더하면 25인데 왜 총점은 24"). 카드에 실제로 보이는(반올림된) 숫자끼리
    # 더한 값을 배지에 쓴다 — 화면에 보이는 숫자들끼리는 항상 앞뒤가 맞아야 함.
    lbl = '총점'
    tt = f'{round(r["C"]) + round(r["A"]) + round(r["N"]):.0f}'
    lf, tf = _font(True, 13), _font(True, 22)
    bw = 18 + lf.getlength(lbl) + 10 + tf.getlength(tt) + 16
    bh = 34
    bx0, by0 = S - PAD - bw, 68
    dr.rectangle([bx0, by0, bx0 + bw, by0 + bh], fill=(0xfb, 0xf6, 0xec))
    dr.rectangle([bx0, by0, bx0 + 3, by0 + bh], fill=ACCENT)
    dr.text((bx0 + 14, by0 + 10), lbl, font=lf, fill=INK_DIM)
    dr.text((bx0 + 18 + lf.getlength(lbl), by0 + 5), tt, font=tf, fill=ACCENT)

    cw = (CW - 24) / 2
    # C 카드
    for i, (code, title, formula, lines, calc, score) in enumerate([
        ('C', '분기 영업이익 증가율', '(전년동기 대비 분기 영업이익 증가율 - 5%)',
         [f'{cur_lbl} 영업이익  {_m(q_cur)}', f'{prior_lbl} 영업이익  {_m(q_prior)}',
          f'YoY 증가율  {r["C_growth"]:+.1f}%' if r['C_growth'] is not None else 'YoY —'],
         f'{r["C_growth"]:.1f}% - 5% → {r["C"]:.1f}점 (상한 25)' if r['C_growth'] is not None else '—',
         r['C']),
        ('A', '연간 영업이익 CAGR', f'(최근 {len(ay)}년 연간 영업이익 CAGR - 5%)',
         [f'FY{v} 영업이익  {_m(ann.get("opinc", {}).get(v))}' for v in ay] +
         [f'CAGR  {r["A_cagr"]:.1f}%' if r['A_cagr'] is not None else 'CAGR —'],
         f'{r["A_cagr"]:.1f}% - 5% → {r["A"]:.1f}점 (적자구간 CAGR은 0% 처리)'
         if r['A_cagr'] is not None else '—', r['A']),
    ]):
        cx = PAD + i * (cw + 24)
        dr.rounded_rectangle([cx, TOP2, cx + cw, TOP2 + 386], radius=12, outline=LINE, width=1)
        dr.rounded_rectangle([cx, TOP2, cx + cw, TOP2 + 52], radius=12, fill=(0x1f, 0x5b, 0x3f))
        dr.rectangle([cx, TOP2 + 40, cx + cw, TOP2 + 52], fill=(0x1f, 0x5b, 0x3f))
        dr.text((cx + 18, TOP2 + 11), code, font=_font(True, 26), fill=(255, 255, 255))
        dr.text((cx + 56, TOP2 + 18), title, font=_font(True, 18), fill=(255, 255, 255))
        yy = TOP2 + 70
        yy = _wrap_draw(dr, cx + 18, yy, '공식: ' + formula, _font(False, 14), INK_FAINT, cw - 36, line_h=19) + 10
        for ln in lines:
            dr.text((cx + 18, yy), '· ' + ln, font=_font(False, 16), fill=INK_DIM)
            yy += 26
        dr.rounded_rectangle([cx + 14, TOP2 + 268, cx + cw - 14, TOP2 + 322], radius=8, fill=SURFACE)
        _wrap_draw(dr, cx + 26, TOP2 + 280, calc, _font(True, 15), INK, cw - 52, line_h=20)
        dr.text((cx + 18, TOP2 + 338), '점수', font=_font(False, 15), fill=INK_FAINT)
        sv = f'{score:.0f}'
        dr.text((cx + cw - 22 - _font(True, 32).getlength(sv), TOP2 + 332), sv,
                font=_font(True, 32), fill=ACCENT)

    y = TOP2 + 404
    dr.text((PAD, y), 'N — New Product · New Market · New High', font=_font(True, 19), fill=INK)
    rows = [[nm, D.CANSLIM_N_DETAIL.get(nm, ''), f'{pt:+.0f}점' if pt else '0점']
            for nm, pt in r['N_rows']]
    y = _table(dr, PAD, y + 30, CW, ['항목', '세부 내용', '점수'],
               rows, widths=[24, 60, 16], aligns=['l', 'l', 'r'], row_h=44)
    dr.text((PAD, y + 2), f'N 합계 {r["N"]:.0f}점', font=_font(True, 17), fill=ACCENT)
    _note(dr, y + 32, D.CANSLIM_NOTE)
    _footer(dr, '채점식=체슬리투자자문 공개 리포트에서 역산(4건 전부 총점 일치 확인) · '
                f'실적={_fin_src("짧게")} · N 항목은 자체 판정')
    return im


# ── 9~11. 재무 3표 (다년 추세) ─────────────────────────────────────────
def _growth_col(rows):
    """마지막 열의 (헤더, {키: 문자열}) 계산.

    기본은 첫 해→마지막 해 CAGR. 분기 표에서는 CAGR이 의미가 없다 — 분기는 계절성이
    있어 연환산하면 4분기 성수기 하나가 '연 300% 성장'으로 둔갑한다. 그래서 분기
    표는 `rows['growth']`로 **전년동기(YoY)** 열을 미리 계산해 넘긴다."""
    if rows.get('growth'):
        return rows['growth']            # (헤더라벨, {key: '표시문자열'})
    n_span = len(rows['years']) - 1
    return f'CAGR({n_span}y)', None


def _fin_page(idx, title, sub, rows, note, src, chart=None, extra=None):
    """extra(dr, y): 표+해석 노트 다음에 붙는 페이지별 추가 섹션(콜백).
    이전엔 호출부(p09/p11)가 _fin_page 반환 후 별도 SDraw로 감싸 고정 y좌표에
    직접 그렸는데, GPM/OPM 행을 추가하면서 표 높이가 늘자 그 고정값이 표·노트와
    겹쳐버렸다(실제 발생) — 여기서 실제 종료 y를 넘겨줘 좌표가 항상 맞게 한다."""
    im, dr = _page(idx, title, sub)
    y = TOP2
    if chart:
        # 차트 높이를 상수로 두면 표 줄 수·해석 노트 길이가 종목마다 달라서 어떤
        # 종목은 하단이 200px 넘게 비고(실제 지적: "공백 지우게 차트 크기 키우자"),
        # 어떤 종목은 노트가 푸터를 침범한다. 표·노트가 실제로 쓸 높이를 먼저 재고
        # 남는 만큼을 차트에 준다 — 종목이 바뀌어도 여백이 일정해진다.
        n_rows = len(rows['lines'])
        row_h = rows.get('row_h', 34)
        est_table = 46 + n_rows * row_h + 14
        est_note = (len(_wrap(note, _font(False, 17), CW - 30)) * 25 + 30) if note else 0
        est_extra = 170 if extra else 0
        avail = BOT - TOP2 - 46 - est_table - est_note - est_extra
        # 상한 300은 표가 9줄쯤 되는 연간 페이지 기준이다. 행이 적은 페이지(분기 표는
        # 빈 행을 걸러내 4줄까지 줄어든다)에서는 그 상한 때문에 하단이 300px 넘게
        # 비어 미완성처럼 보인다 — 페이지가 직접 상한을 올릴 수 있게 한다.
        y = chart(dr, y, int(max(150, min(rows.get('chart_max', 300), avail))))
        y += 10
    span_label, span_map = _growth_col(rows)
    header = ['항목'] + [str(v) for v in rows['years']] + [span_label]
    body = []
    emph = set()
    for i, row in enumerate(rows['lines']):
        label, key, good, strong = row[:4]
        pct = row[4] if len(row) > 4 else False   # %행(마진)은 CAGR·달러표기 대상이 아님
        # EPS처럼 이미 "주당 X.XX달러"인 항목을 _m()(백만 단위 가정, $M/$B 자동전환)에
        # 넣으면 "$0.0M" 같은 헛소리가 나온다 — raw 플래그로 단위변환 없이 그대로 표기.
        raw = row[5] if len(row) > 5 else False
        vals = [rows['data'].get(key, {}).get(v) for v in rows['years']]
        if span_map is not None:
            # 분기 표 등 — 마지막 열을 호출부가 미리 계산해 넘긴 경우.
            fmt = (lambda v: f'{v:.1f}%') if pct else (_px if raw else (lambda v: _m(v)))
            body.append([label] + [(fmt(v) if v is not None else '—') for v in vals]
                        + [span_map.get(key, '—')])
            if strong:
                emph.add(i)
            continue
        if pct:
            cells = [label] + [(f'{v:.1f}%' if v is not None else '—') for v in vals]
            cells.append('—')
        elif raw:
            cells = [label] + [_px(v) for v in vals]
            pair = [v for v in vals if v is not None]
            if len(pair) >= 2 and pair[0] > 0 and pair[-1] > 0:
                cagr = ((pair[-1] / pair[0]) ** (1 / (len(pair) - 1)) - 1) * 100
                cells.append(f'{cagr:+.0f}%')
            else:
                cells.append('—')
        else:
            cells = [label] + [(_m(v) if v is not None else '—') for v in vals]
            pair = [v for v in vals if v is not None]
            # CAGR은 양수 구간에서만 정의됨 — 적자(음수)나 부호가 바뀌는 항목은 '—'
            if len(pair) >= 2 and pair[0] > 0 and pair[-1] > 0:
                cagr = ((pair[-1] / pair[0]) ** (1 / (len(pair) - 1)) - 1) * 100
                cells.append(f'{cagr:+.0f}%')
            else:
                cells.append('—')
        body.append(cells)
        if strong:
            emph.add(i)
    n = len(rows['years'])
    widths = [26] + [74 / (n + 1)] * n + [74 / (n + 1)]
    y = _table(dr, PAD, y, CW, header, body, widths=widths, row_h=rows.get('row_h', 34), emph=emph)
    y = _note(dr, y + 8, note)
    if extra:
        y = extra(dr, y)
    _footer(dr, src)
    return im


def p09_income():
    ann = (L or {}).get('annual', {})
    yrs = _fy_years(5, ('revenue',))

    def chart(dr, y, ch):
        dr.text((PAD, y), '매출 vs 매출원가 — 규모의 경제가 실제로 먹히는지', font=_font(True, 17), fill=INK)
        # .get(v, 0) 기본값은 "데이터 없음"과 "매출 0"을 구분 못 해서, 상장 전이라
        # 아예 신고 이력이 없는 해(스핀오프 종목 — SNDK가 실제 사례, 2021·2022엔
        # 독립법인이 아니었음)에 유령 막대+"$0.0M" 라벨이 찍혔다(실제 발견, 표는
        # 이미 "—"로 정직하게 비어있는데 차트만 거짓 0으로 보임) — None 유지.
        rev = [(v0 / 1e6 if (v0 := ann.get('revenue', {}).get(v)) is not None else None) for v in yrs]
        cogs = [(v0 / 1e6 if (v0 := ann.get('cogs', {}).get(v)) is not None else None) for v in yrs]
        gm = [(1 - c / r) * 100 if (r and c is not None) else None for r, c in zip(rev, cogs)]
        opm = [data['opm'].get(v) for v in yrs]
        # 한 번도 흑자였던 적 없으면(전 구간 대폭 마이너스) OPM 라인이 GPM과 스케일이
        # 안 맞아 차트를 짜부라뜨리기만 하고 정보값이 없다 — 지적대로 그럴 땐 아예 뺀다.
        # 표(아래 '영업이익률(OPM)' 행)엔 실제 숫자가 그대로 남아있어 정보 손실은 없음.
        ever_profitable = any((v or 0) > 0 for v in opm)
        kw = dict(line2=opm, line2_fmt=lambda v: f'{v:.0f}%', line2_name='OPM') if ever_profitable else {}
        # 매출원가 태그를 안 내는 회사(ABCL 실측)는 GPM이 통째로 비는데, 범례에는
        # 'GPM'이 그대로 떠서 "선이 어디 갔지"가 된다 — 그릴 값이 없으면 이름도 뗀다.
        gpm_name = 'GPM' if any(v is not None for v in gm) else ''
        return C2.dual_axis(dr, PAD, y + 40, CW, ch, [str(v) for v in yrs], rev, gm,
                            _mB, lambda v: f'{v:.0f}%', bar_name='매출', line_name=gpm_name, **kw)
    data = dict(ann)
    # PLTR 등 일부 회사는 SG&A를 통합 태그로 안 내고 판매비(S&M)·관리비(G&A)를 따로
    # 공시한다 — 'sga' 후보 태그만 쓰면 판매비가 통째로 빠져서, "규모의 경제" 비용
    # 진단(cogs+rnd+sga+dep)이 실제 보고된 영업이익과 수백M~1B+ 단위로 안 맞았다
    # (실제 검증: PLTR 계산상 영업이익이 보고치보다 매년 $0.6~1.0B씩 높게 나옴 —
    # 판매비가 몽땅 빠진 게 원인). 여기서 둘을 합쳐 'sga'를 "판매관리비 전체"로 만든다.
    data['sga'] = {}
    for v in yrs:
        s1, s2 = ann.get('sga', {}).get(v), ann.get('salesmkt', {}).get(v)
        if s1 is not None or s2 is not None:
            data['sga'][v] = (s1 or 0) + (s2 or 0)
    data['gp'], data['gpm'], data['opm'] = {}, {}, {}
    for v in yrs:
        rev = ann.get('revenue', {}).get(v)
        cogs = ann.get('cogs', {}).get(v)
        op = ann.get('opinc', {}).get(v)
        if rev:
            if cogs is not None:
                data['gp'][v] = rev - cogs
                data['gpm'][v] = (rev - cogs) / rev * 100
            if op is not None:
                data['opm'][v] = op / rev * 100
    # "영업손익"이 아니라 항상 "영업이익"으로 표기 — 적자分은 _m()이 음수 그대로
    # "-108.0" 식으로 찍어주므로 라벨과 부호 둘 다 별도 분기 없이 항상 정확하다.
    # row_h는 29 — GPM/OPM 두 줄이 늘어난 만큼 줄여서, SATL처럼 해석 노트가 길고
    # 여전히 적자라 손익분기 박스까지 나오는 경우에도 페이지 하단 출처줄과 안 겹치게
    # 한다(실제로 겹쳤던 버그: 9줄짜리 표 + 긴 노트 + 손익분기 박스가 캔버스를 넘어감).
    # EPS(희석) 추가 — sources.TAGS에 'eps'(EarningsPerShareDiluted) 태그를 새로 등록해
    # annual_series가 자동으로 같이 가져옴. row 튜플 6번째 True가 "raw"(단위변환 없이
    # $X.XX 그대로) 플래그.
    rows = {'years': yrs, 'data': data, 'row_h': 29, 'lines': [
        ('매출', 'revenue', True, True), ('매출원가', 'cogs', False, False),
        ('매출총이익', 'gp', True, False), ('매출총이익률(GPM)', 'gpm', False, False, True),
        ('연구개발비', 'rnd', False, False), ('판매관리비', 'sga', False, False),
        ('감가상각', 'dep', False, False), ('영업이익', 'opinc', True, True),
        ('영업이익률(OPM)', 'opm', False, False, True),
        # 순이익 행은 원래 없었다 — 영업이익만 있으면 은행(JPM)·리츠(O)처럼
        # OperatingIncomeLoss를 아예 공시하지 않는 업종에서 손익계산서에 이익 숫자가
        # 한 줄도 안 남는다(실측 확인). 전 종목에 유용하기도 하고.
        ('순이익', 'netinc', True, True),
        ('희석 EPS', 'eps', True, False, False, True),
    ]}
    return _fin_page(9, '손익계산서', f'FY{yrs[0]}~{yrs[-1]} 다년 추세 ({_fin_src("표준")})', rows,
                     D.INCOME_NOTE,
                     getattr(D, 'INCOME_SRC', f'{_fin_src("표준")} · 손익분기는 자체 계산'), chart)


def _fin_src(kind='표준'):
    """재무 출처 문구. 시장마다 원천이 다르므로 한 곳에서만 정한다 — 문자열을 페이지마다
    박아두면 한국 종목 카드에 'SEC XBRL companyfacts'가 그대로 찍힌다(실측으로 발생)."""
    if CURRENCY == 'KRW':
        return {'표준': 'DART 재무제표 API(fnlttSinglAcntAll)',
                '짧게': 'DART 재무제표', '분기': 'DART 분기·반기보고서',
                '연차': 'DART 사업보고서'}[kind]
    return {'표준': 'SEC XBRL companyfacts', '짧게': 'SEC XBRL',
            '분기': 'SEC XBRL (10-Q)', '연차': '연차보고서(10-K/20-F)'}[kind]


def _q_label(end: str) -> str:
    """분기말 날짜 → 표 열 머리. 달력분기(3·6·9·12월)면 '26.2Q', 아니면 '26.05'.

    회계분기 번호는 회사의 결산월을 알아야 정해진다 — 모르면서 붙이면 3월 결산
    회사에서 번호가 한 분기씩 어긋난다. 달력분기가 아닌 종목은 번호를 **안 붙인다**
    (틀린 라벨보다 덜 예쁜 라벨)."""
    y, m = end[2:4], int(end[5:7])
    return f'{y}.{m // 3}Q' if m in (3, 6, 9, 12) else f'{y}.{m:02d}'


def p12_income_q():
    """최근 4개 분기 손익계산서.

    분기 데이터는 live.bundle()이 이미 14분기를 받아오고 있었는데(US=XBRL 10-Q,
    KR=DART 분기보고서) 렌더러는 연간 5년만 쓰고 있었다 — 새로 수집할 게 없다.
    연간 표만으로는 "지금 무슨 일이 벌어지는 중인가"가 안 보인다: 흑자전환·마진
    붕괴는 분기에서 먼저 나타나고 연간에 묻힌다."""
    qtr = dict((L or {}).get('quarterly', {}))
    # 미국은 10-K가 4분기를 따로 안 실어 quarterly_series에 Q4가 빠진다 — 그대로 쓰면
    # 열이 25.2Q·25.3Q·26.1Q처럼 **한 분기씩 건너뛴 채** 나란히 서서, 붙어 있는 두 열이
    # 실제로는 두 분기 떨어진 비교가 된다. live.bundle이 이미 역산해 채운 계열
    # (q_revenue·q_opinc·q_netinc)이 있으니 그쪽을 우선 쓴다.
    # **합집합**으로 병합한다. 길이만 비교해 통째로 갈아치우면, 역산 계열이 더 짧을 때
    # (q_* 는 9분기, quarterly_series 는 14분기) 채워진 Q4가 통째로 버려진다 — 실측으로
    # ABCL 25.4Q가 그렇게 사라져 표가 25.3Q 다음에 26.1Q를 붙여놨다.
    for key, src in (('revenue', 'q_revenue'), ('opinc', 'q_opinc'), ('netinc', 'q_netinc')):
        filled = (L or {}).get(src) or {}
        if filled:
            qtr[key] = {**qtr.get(key, {}), **filled}
    ends = sorted(qtr.get('revenue', {}))
    if len(ends) < 2:
        return None                      # 분기 데이터가 없으면 페이지를 통째로 건너뛴다
    show = ends[-4:]

    data = {k: dict(v) for k, v in qtr.items()}
    data['gp'], data['gpm'], data['opm'] = {}, {}, {}
    for e in ends:
        rev = qtr.get('revenue', {}).get(e)
        cogs = qtr.get('cogs', {}).get(e)
        op = qtr.get('opinc', {}).get(e)
        if rev:
            if cogs is not None:
                data['gp'][e] = rev - cogs
                data['gpm'][e] = (rev - cogs) / rev * 100
            if op is not None:
                data['opm'][e] = op / rev * 100

    # 마지막 열은 **전년동기(YoY)**. 분기에 CAGR을 쓰면 계절성 탓에 성수기 한 분기가
    # '연 300% 성장'으로 둔갑한다. 네 분기 앞(=같은 분기 전년)과 비교한다.
    # 전년동기는 **날짜로** 찾는다. "4칸 앞"으로 세면 계열에 구멍이 하나만 있어도
    # 엉뚱한 분기와 비교한다 — 실측으로 ABCL이 26.2Q($4.0M)를 25.2Q($17.1M)가 아니라
    # 25.1Q($4.2M)와 비교해 YoY가 -77%가 아닌 -4%로 찍혔다.
    latest = show[-1]
    ly = f'{int(latest[:4]) - 1}{latest[4:]}'
    prior = ly if ly in qtr.get('revenue', {}) else next(
        (e for e in ends if e[:4] == ly[:4] and e[5:7] == ly[5:7]), None)
    growth = {}
    for key in list(data):
        a = data.get(key, {}).get(latest)
        b = data.get(key, {}).get(prior) if prior else None
        if a is None or b is None:
            growth[key] = '—'
        elif key in ('gpm', 'opm'):
            growth[key] = f'{a - b:+.1f}%p'      # 마진은 %p 차이가 맞다(비율의 비율 아님)
        elif b == 0 or (b < 0 <= a):
            growth[key] = '흑자전환' if b < 0 <= a else '—'
        elif b < 0 and a < 0:
            growth[key] = '적자지속'
        else:
            growth[key] = f'{(a - b) / abs(b) * 100:+.0f}%'

    def chart(dr, y, ch):
        dr.text((PAD, y), '분기 매출과 마진 — 연간에 묻히는 변곡을 본다',
                font=_font(True, 17), fill=INK)
        span = ends[-8:]
        rev = [(v / 1e6 if (v := qtr.get('revenue', {}).get(e)) is not None else None) for e in span]
        gm = [data['gpm'].get(e) for e in span]
        opm = [data['opm'].get(e) for e in span]
        # 마진선은 **그릴 값이 있고, 그려서 정보가 될 때만** 얹는다.
        #  · 매출원가 태그가 없는 회사(ABCL 실측)는 GPM이 통째로 비어 범례만 뜬다.
        #  · 한 번도 흑자였던 적 없으면 OPM이 -1550% 같은 값이라 매출 막대를 짜부라뜨린다
        #    (p09_income이 연간 차트에서 쓰는 것과 같은 판단).
        kw = {}
        if any(v is not None for v in opm) and any((v or 0) > 0 for v in opm):
            kw = dict(line2=opm, line2_fmt=lambda v: f'{v:.0f}%', line2_name='OPM')
        if not any(v is not None for v in gm):
            gm, kw = (kw.get('line2'), {}) if kw else (None, {})
            if gm is None:               # GPM·OPM 둘 다 못 그리면 매출 막대만
                return C2.dual_axis(dr, PAD, y + 40, CW, ch, [_q_label(e) for e in span],
                                    rev, [None] * len(span), _mB, lambda v: f'{v:.0f}%',
                                    bar_name='매출', line_name='')
            return C2.dual_axis(dr, PAD, y + 40, CW, ch, [_q_label(e) for e in span], rev, gm,
                                _mB, lambda v: f'{v:.0f}%', bar_name='매출', line_name='OPM')
        return C2.dual_axis(dr, PAD, y + 40, CW, ch, [_q_label(e) for e in span], rev, gm,
                            _mB, lambda v: f'{v:.0f}%', bar_name='매출', line_name='GPM', **kw)

    lines = [
        ('매출', 'revenue', True, True), ('매출원가', 'cogs', False, False),
        ('매출총이익', 'gp', True, False),
        ('매출총이익률(GPM)', 'gpm', False, False, True),
        ('영업이익', 'opinc', True, True),
        ('영업이익률(OPM)', 'opm', False, False, True),
        ('순이익', 'netinc', True, True),
        ('영업활동 현금흐름', 'cfo', True, False),
    ]
    # 표시 구간에 값이 하나도 없는 행은 뺀다 — '—'만 네 칸 늘어선 줄은 정보가 아니라
    # 잡음이고, 읽는 사람은 "왜 비었지"를 페이지에서 알 수 없다(ABCL 실측: 매출원가·
    # 매출총이익·GPM 세 줄이 통째로 빈 채 자리만 차지했다).
    # 값이 한 칸뿐인 행도 뺀다 — 네 칸 중 하나만 찬 줄은 추세를 못 보여주면서 자리만
    # 차지한다(ABCL 실측: 영업활동 현금흐름이 26.1Q 한 칸만 차 있었다).
    lines = [ln for ln in lines
             if sum(data.get(ln[1], {}).get(e) is not None for e in show) >= 2]

    rows = {'years': [_q_label(e) for e in show], 'row_h': 31, 'chart_max': 470,
            'data': {k: {_q_label(e): v.get(e) for e in show} for k, v in data.items()},
            'growth': ('YoY' if prior else '—', {k: growth.get(k, '—') for k in data}),
            'lines': lines}
    q_src = _fin_src('분기')
    note = getattr(D, 'INCOME_Q_NOTE', '') or (
        f'{rows["years"][0]}~{rows["years"][-1]} 각 분기의 3개월 실적. '
        f'마지막 열은 전년 동기 대비 — 분기는 계절성이 있어 직전 분기와 비교하면 오독된다.')
    return _fin_page(12, '분기 손익계산서', f'최근 {len(show)}개 분기 ({q_src})',
                     rows, note, f'{q_src} · 마진·YoY는 자체 계산', chart)


def p10_balance():
    ann = (L or {}).get('annual', {})
    yrs = _fy_years(5, ('assets', 'equity'))

    def chart(dr, y, ch):
        # 제목에 "유동성은 늘고 자본은 요동친다"는 해석이 통째로 박혀 있었다 —
        # SATL 한 종목의 실제 모습을 전 종목 공용 제목으로 쓴 셈이라 현금이 줄고
        # 자본이 안정적인 회사에선 그냥 거짓말이 된다(7p에서 한 번 고쳤던 것과
        # 같은 클래스). 실제 첫해→마지막해 변화에서 문구를 만든다.
        cash = [(v0 / 1e6 if (v0 := ann.get('cash', {}).get(v)) is not None else None) for v in yrs]
        eq = [ann.get('equity', {}).get(v) for v in yrs]

        def _dir(series):
            kn = [v for v in series if v is not None]
            if len(kn) < 2 or not kn[0]:
                return None
            ch = (kn[-1] - kn[0]) / abs(kn[0]) * 100
            return '늘고' if ch > 15 else ('줄고' if ch < -15 else '큰 변화 없고')
        cd, ed = _dir(cash), _dir(eq)
        ed_txt = {'늘고': '자본은 쌓인다', '줄고': '자본은 깎인다',
                  '큰 변화 없고': '자본은 제자리다'}.get(ed, '자본은 어떻게 움직였나')
        title = (f'현금 vs 자기자본 — 유동성은 {cd} {ed_txt}' if cd
                 else '현금 vs 자기자본 — 유동성과 장부가의 추이')
        dr.text((PAD, y), title, font=_font(True, 17), fill=INK)
        return C2.dual_axis(dr, PAD, y + 44, CW, ch, [str(v) for v in yrs], cash,
                            [v / 1e6 if v is not None else None for v in eq],
                            # dp=0이면 표엔 "$2.3B"인데 차트 라벨은 "$2B"로 찍혀 같은
                            # 페이지 안에서 숫자가 달라 보인다 — 표와 같은 소수1자리로 통일.
                            _mB, lambda v: _mB(v, 1, sign=True),
                            bar_name='현금', line_name='자기자본')
    rows = {'years': yrs, 'data': ann, 'row_h': 33, 'lines': [
        ('현금성자산', 'cash', True, True), ('매출채권', 'ar', True, False),
        ('유형자산', 'ppe', True, False), ('자산 총계', 'assets', True, True),
        ('부채 총계', 'liab', False, True), ('계약부채(선수금)', 'contract_liab', True, False),
        ('자본 총계', 'equity', True, True),
    ]}
    return _fin_page(10, '대차대조표', f'FY{yrs[0]}~{yrs[-1]} 다년 추세', rows,
                     D.BALANCE_NOTE, _fin_src('표준'), chart)


def p11_cashflow():
    ann = (L or {}).get('annual', {})
    yrs = _fy_years(5, ('cfo',))
    cfo_vals = [ann.get('cfo', {}).get(v) for v in yrs]
    known_cfo = [v for v in cfo_vals if v is not None]
    latest_cfo = known_cfo[-1] if known_cfo else None
    prior_cfo = known_cfo[-2] if len(known_cfo) >= 2 else None
    positive = latest_cfo is not None and latest_cfo > 0
    # 이진 판정(흑자/적자) 두 문구뿐이면 "직전엔 적자였다가 최근에야 막 흑자로
    # 돌아선" 경우까지 "흑자 기조 *유지* 중"이라고 잘못 말한다(실제 발견: SNDK —
    # 2023·2024 적자, 2025 딱 1개년만 흑자인데 "유지 중"이라는 건 거짓말에 가까움,
    # 노트박스는 이미 "전환"이라고 정확히 말하고 있어 제목과 모순됐음). 전환 케이스를
    # 별도로 구분.
    turnaround = positive and prior_cfo is not None and prior_cfo <= 0

    def chart(dr, y, ch):
        if turnaround:
            title = '영업현금흐름 — 적자에서 흑자로 전환'
        elif positive:
            title = '영업현금흐름 — 흑자 기조 유지 중'
        else:
            title = '영업현금흐름 — 적자 축소 궤적'
        dr.text((PAD, y), title, font=_font(True, 17), fill=INK)
        # .get(v, 0) 기본값이 "데이터 없음"인 해(상장/스핀오프 전이라 신고 이력
        # 자체가 없음 — SNDK 2021·2022 실제 사례)에도 유령 0-막대+"$0.0M" 라벨을
        # 찍었다(표는 이미 "—"로 정직한데 차트만 거짓 0으로 보이는 불일치) — None 유지.
        cfo = [(v0 / 1e6 if (v0 := ann.get('cfo', {}).get(v)) is not None else None) for v in yrs]
        capex = [(v0 / 1e6 if (v0 := ann.get('capex', {}).get(v)) is not None else None) for v in yrs]
        fcf = [(c - x) if (c is not None and x is not None) else None for c, x in zip(cfo, capex)]
        # 표와 같은 소수1자리로 통일(대차대조표와 동일한 이유 — "$2B" vs "$2.3B" 불일치).
        bar_fmt = _mB if positive else (lambda v: f'-{_mB(v)}')
        # 막대색을 흑자/적자에 따라 POS/NEG로 바꿔왔는데, 손익계산서·대차대조표는
        # 부호와 무관하게 항상 같은 기본색(SEGMENT_COLORS[0])을 쓴다 — 세 재무제표
        # 페이지 색을 통일해달라는 피드백으로 여기도 bar_color 지정을 없애 기본색을 쓴다.
        return C2.dual_axis(dr, PAD, y + 44, CW, ch, [str(v) for v in yrs],
                            [(v if positive else abs(v)) if v is not None else None for v in cfo], fcf,
                            bar_fmt, lambda v: _mB(v, 1, sign=True),
                            bar_name='영업현금흐름' + ('' if positive else '(절대값)'),
                            line_name='잉여현금흐름')
    rows = {'years': yrs, 'data': ann, 'row_h': 36, 'lines': [
        ('영업활동 현금흐름', 'cfo', True, True), ('설비투자(CapEx)', 'capex', False, False),
    ]}
    # 순손실↔영업현금 괴리가 큰 종목(SATL처럼 비현금 손실이 압도)만 확대 패널이 의미 있음.
    # 데이터 파일이 zoom을 안 주면(=괴리가 작아 주 차트만으로 충분) 이 블록 자체를 생략한다.
    zoom = D.CASHFLOW.get('zoom')

    def extra(dr, y):
        if not zoom:
            return y
        period = D.RESULTS.get('period', '최근 분기')
        dr.text((PAD, y), f'{period} 브리지: 순손익 → 영업현금 (확대 구간)', font=_font(True, 17), fill=INK)
        _waterfall(dr, PAD, y + 34, CW, 120, zoom, start=D.CASHFLOW.get('zoom_start', 0))
        return y + 34 + 120 + 10

    # zoom 없는 종목(TSLA 등)에서 부제가 "+ 최근 분기 브리지"라고 예고해놓고 실제로는
    # 아무 브리지도 안 나와 혼란스러웠다 — zoom 유무에 맞춰 부제 자체를 바꾼다.
    span = f'FY{yrs[0]}~{yrs[-1]}'
    sub = f'{span} + 최근 분기 브리지' if zoom else f'{span} 다년 추세'
    return _fin_page(11, '현금흐름표', sub, rows,
                     D.CASHFLOW['note'], D.CASHFLOW['src'], chart, extra)



def _quant_note(mm, dd, listing_date=None):
    """월간 통계·낙폭에서 해설을 자동 생성 — 하드코딩하면 다른 종목·다른 기간에서 바로 거짓말이 됨."""
    win = {m: v for m, v in (mm.get('win') or {}).items() if v is not None}
    avg = {m: v for m, v in (mm.get('avg') or {}).items() if v is not None}
    strong = [m for m, v in sorted(win.items()) if v >= 60]
    vals = [v for row in (mm.get('matrix') or {}).values() for v in row.values() if v is not None]
    n_yr = len(mm.get('years') or [])
    best_m = max(avg, key=avg.get) if avg else None
    worst_m = min(avg, key=avg.get) if avg else None
    # 문장을 전부 이어붙이면(em-dash로 계속 연결) "우다다 나열"처럼 읽힌다는 지적 —
    # 관찰 하나당 한 줄(\n)로 끊는다. 의미 없는 강조용 em-dash도 최대한 뺀다.
    parts = []
    if strong:
        parts.append(f'승률 60% 이상인 달: {"·".join(f"{m}월" for m in strong)}')
    if best_m and worst_m:
        parts.append(f'평균 수익률 최고 {best_m}월(+{avg[best_m]:.0f}%), 최저 {worst_m}월({avg[worst_m]:+.0f}%)'
                     f' (표본 {n_yr}년뿐이라 계절성 단정은 금물)')
    if vals:
        parts.append(f'월간 진폭 최대 {max(vals):+.0f}%, 최소 {min(vals):+.0f}% — 변동성 매우 큼')
    cur, mx = dd.get('current'), dd.get('max_all')
    if cur is not None and mx is not None:
        parts.append(f'낙폭은 조회기간 최대 {mx:.0f}%, 현재 {cur:.0f}%. 이 종목에선 {cur:.0f}%가 평상시 '
                     f'범위라 낙폭만 보고 싸다고 판단하면 안 됨')
    # 상장월 계산기준 설명 줄은 삭제(피드백: 불필요한 코멘트) — 계산 로직 자체는
    # monthly_matrix에 그대로 유지(정상적으로 값이 채워짐), 화면에 문구만 안 띄움.
    return '\n'.join(parts)


# ── 15. 월간 퀀트 · MDD ────────────────────────────────────────────────
def p15_quant():
    mm = (L or {}).get('monthly', {})
    dd = (L or {}).get('drawdown', {})
    im, dr = _page(6, '월간 퀀트 · MDD', '연도×월 상승률 / 전고점 대비 낙폭')
    # 10년(요청: 최소 2017년 이후)까지 늘리면서 히트맵 기본 행높이(34px)로는 페이지가
    # 넘쳤다 — 행높이를 줄여서 맞춘다(그래도 15px 폰트라 읽는 덴 문제없음).
    n_hm_years = len(mm.get('years') or [])
    hm_row_h = 34 if n_hm_years <= 7 else max(24, 34 - (n_hm_years - 7) * 2)
    y = C2.heatmap(dr, PAD, TOP2, CW, mm, row_h=hm_row_h)
    y += 20
    # "6년" 고정 문구 — 히트맵·MDD 조회기간을 종목마다/구간마다 다르게 늘리면서
    # (예: AAPL 30년) 문구가 실제 기간과 안 맞게 될 뻔했다 — 실제 데이터에서 계산.
    # dd['years']는 "몇 년치 요청했나"(예: 30)일 뿐 실제 받은 데이터 기간이 아니다
    # — 어린 종목(IONQ 등)은 since=listing_date로 실제론 5~6년치만 오는데도
    # "MDD 30년"이라고 찍히는 버그가 실제로 있었다. series 타임스탬프에서 실제
    # 기간을 직접 잰다.
    dd_series = dd.get('series') or []
    if dd_series:
        span_yrs = (dd_series[-1][0] - dd_series[0][0]) / 31557600
        dd_label = f'{max(1, round(span_yrs))}년'
    else:
        dd_label = f'{len(mm.get("years") or [])}년'
    mm_years = mm.get('years') or []
    dr.text((PAD, y), f'MDD 낙폭 (전고점 대비 %, 조회기간 {dd_label})', font=_font(True, 18), fill=INK)
    y = C2.drawdown_chart(dr, PAD + 50, y + 40, CW - 60, 190, dd, ref_line=dd.get('max_all'))
    y += 6
    dr.text((PAD, y), f'현재 낙폭 {dd.get("current",0):.1f}%   ·   1년 내 최대 {dd.get("max_1y",0):.1f}%'
                      f'   ·   조회기간 최대 {dd.get("max_all",0):.1f}%',
            font=_font(True, 16), fill=INK_DIM)
    _note(dr, y + 26, _quant_note(mm, dd, (L or {}).get('listing_date')))
    heat_label = f'{min(mm_years)}~{max(mm_years)}' if mm_years else dd_label
    _footer(dr, f'{D.SRC.get("YF", "Yahoo Finance chart API")}{" · " + _px_asof() + " 종가" if _px_asof() else ""} · 히트맵 {heat_label} · MDD {dd_label} '
                f'월봉·일봉 기준 자체 계산')
    return im


# 13p 개편(사용자 확정 레이아웃) — 종합평가·최근실적을 앞으로 빼고, CEO+주주구성+RSU·
# 사업부문+경쟁사+TAM을 각각 한 장으로 합쳐 17장→11장(+표지)으로 줄임. 기존 기술적분석·
# ETF·체크포인트 단독페이지는 없어지고 각각 종합평가/주주구성/종합평가 페이지에 흡수됨.
# 2026-10-20: 대가 관점 3장 추가(deck_guru.py) — 린치 2분 점검은 종합평가 다음(이야기부터),
# 차트 읽기는 연혁(가격 차트) 다음, 오닐 원전 7관문은 체슬리 CANSLIM 바로 다음(나란히 비교).
import deck_guru as _G  # noqa: E402


def p16_lynch():
    return _G.lynch_page(sys.modules[__name__], PAGES.index(p16_lynch))


def p17_chart():
    return _G.chart_page(sys.modules[__name__], PAGES.index(p17_chart))


def p18_oneil():
    return _G.oneil_page(sys.modules[__name__], PAGES.index(p18_oneil))


def p19_industry():
    return _G.industry_page(sys.modules[__name__], PAGES.index(p19_industry))


PAGES = [p00_cover, p05_outlook, p16_lynch, p06_results, p01_history, p17_chart, p02_ceo, p04_segments, p19_industry,
         p15_quant, p08_canslim, p18_oneil, p07_valuation, p09_income, p12_income_q,
         p10_balance, p11_cashflow]


def render_all(out_dir='out', site=None, ceo=None, wiki_file='', listing_date=None, prefix=None):
    """configure()로 D/M/CIK/PEERS를 맞춘 뒤 호출. site·ceo 등은 configure()가 돌려준
    dict를 그대로 넘기면 된다(예: kw = P.configure(...); P.render_all(**kw))."""
    global L, _CUR
    listing_date = listing_date or getattr(D, 'HISTORY', {}).get('listing_date')
    L = live.bundle(M['ticker'], CIK, PEERS, site, ceo, wiki_file=wiki_file,
                    listing_date=listing_date, company=M['name'])
    p = Path(__file__).resolve().parent / out_dir
    p.mkdir(parents=True, exist_ok=True)
    # 한국 티커의 '.KQ'가 파일명에 들어가면 '247540.kq_00.png'처럼 확장자가 둘인 꼴이
    # 돼 도구마다 다르게 해석한다 — 점을 뺀다.
    prefix = prefix or M['ticker'].lower().replace('.ks', '').replace('.kq', '')
    paths = []
    for i, fn in enumerate(PAGES):
        _CUR = i
        try:
            im = fn()
        except Exception as e:
            import traceback
            print(f'[페이지 {i} 실패] {type(e).__name__}: {e}')
            traceback.print_exc()
            continue
        if im is None:
            # 페이지 함수가 "그릴 근거가 없다"고 스스로 판단한 경우(예: 분기 데이터가
            # 없는 종목의 분기 손익표). 빈 페이지를 내보내느니 장을 뺀다.
            print(f'[페이지 {i} 생략] {fn.__name__} — 데이터 없음')
            continue
        path = p / f'{prefix}_{i:02d}.png'
        finish(im).save(path)          # SS배 캔버스 → 1080으로 downsample
        paths.append(str(path))
    return paths


if __name__ == '__main__':
    # 단독 실행 시 기본값(SATL) 그대로 렌더 — 하위호환
    for path in render_all(site='https://satellogic.com', ceo='Emiliano Kargieman',
                           wiki_file='5/5f/Satellogic.png'):
        print(path)
