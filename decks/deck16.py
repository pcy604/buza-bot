# -*- coding: utf-8 -*-
"""16페이지 딥리포트 렌더러 — 1080x1080 PNG, Pillow 직접 그리기.

report.py(8슬라이드 인스타 캐러셀)의 라이트테마·폰트를 그대로 재사용하되,
표/그래프 밀도가 훨씬 높은 16개 주제 페이지를 그린다. 데이터는 satl16_data.py처럼
"숫자 + 출처 + 기준일"을 함께 들고 있는 모듈에서만 읽는다(렌더러는 계산하지 않음).
"""
import sys
import functools
from pathlib import Path
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import (  # noqa: E402  라이트테마 색·폰트·텍스트유틸 재사용
    S, PAD, BG, SURFACE, LINE, INK, INK_DIM, INK_FAINT, ACCENT, UP, DN, FLAT,
    SEGMENT_COLORS, _font, _s, _wrap_draw, _logo_or_monogram,
)
from card import _wrap  # noqa: E402  줄수 미리 재기용
import report as _report  # noqa: E402

# ── 슈퍼샘플링 ─────────────────────────────────────────────────────────
# 1080에 직접 그리면 12~15px 한글 텍스트와 곡선에 계단현상이 남는다.
# 페이지 코드는 1x 논리좌표 그대로 두고, 실제 캔버스만 SS배로 키워 그린 뒤
# 저장 직전에 LANCZOS로 downsample한다(= 슈퍼샘플 안티에일리어싱).
SS = 3


class _F:
    """1x 기준으로 치수를 보고하는 폰트 래퍼. 내부 폰트는 SS배 크기.
    bold: PNG 렌더 자체엔 안 쓰이지만(굵기는 이미 real 폰트 파일 선택에 반영됨),
    pptx_export.py가 네이티브 텍스트박스의 font.bold를 정하는 데 읽어간다."""
    __slots__ = ('real', 'k', 'size', 'bold')

    def __init__(self, real, k, logical_size, bold=False):
        self.real, self.k, self.size, self.bold = real, k, logical_size, bold

    def getlength(self, t):
        return self.real.getlength(t) / self.k

    def getbbox(self, t, *a, **kw):
        b = self.real.getbbox(t, *a, **kw)
        return tuple(v / self.k for v in b)


@functools.lru_cache(maxsize=None)
def _font(bold: bool, size: int):          # report._font를 덮어씀(1x 인터페이스 유지)
    return _F(_report._font(bold, int(round(size * SS))), SS, size, bold=bold)


def _unwrap(f):
    return f.real if isinstance(f, _F) else f


def _scale(v, k):
    """(x,y) / [x0,y0,x1,y1] / [(x,y),...] 어떤 형태든 좌표를 k배."""
    if v is None or isinstance(v, (int, float)):
        return v * k if isinstance(v, (int, float)) else v
    if isinstance(v[0], (list, tuple)):
        return [tuple(c * k for c in p) for p in v]
    return [c * k for c in v]


class SDraw:
    """1x 논리좌표로 호출하면 SS배 캔버스에 그려주는 ImageDraw 프록시."""
    _XY = ('line', 'rectangle', 'rounded_rectangle', 'ellipse', 'polygon',
           'pieslice', 'arc', 'chord', 'point')
    _SCALE_KW = ('width', 'radius')

    def __init__(self, dr):
        self._dr = dr

    def text(self, xy, txt, font=None, **kw):
        self._dr.text(tuple(_scale(xy, SS)), txt, font=_unwrap(font), **kw)

    def __getattr__(self, name):
        fn = getattr(self._dr, name)
        if name not in self._XY:
            return fn

        def wrapped(xy, *a, **kw):
            for k in self._SCALE_KW:
                if isinstance(kw.get(k), (int, float)):
                    kw[k] = max(1, int(round(kw[k] * SS)))
            return fn(_scale(xy, SS), *a, **kw)
        return wrapped


def new_canvas(w=None, h=None, bg=None):
    """SS배 캔버스 + 프록시 반환."""
    from PIL import Image as _I, ImageDraw as _D
    w = w or S
    h = h or S
    im = _I.new('RGB', (int(w * SS), int(h * SS)), bg or BG)
    return im, SDraw(_D.Draw(im))


def paste_scaled(im, img, xy, box=None, pad_ratio=0.0):
    """1x 논리좌표/크기로 이미지를 SS 캔버스에 붙인다. box=(w,h) 주면 그 안에 맞춤.
    pad_ratio: 로고처럼 여백 없이 가장자리까지 꽉 찬 이미지가 잘려 보이는 걸 막는 투명 여백."""
    from PIL import Image as _I
    img = img.convert('RGBA')
    if pad_ratio:
        pw, ph = int(img.width * pad_ratio), int(img.height * pad_ratio)
        canv = _I.new('RGBA', (img.width + pw * 2, img.height + ph * 2), (0, 0, 0, 0))
        canv.paste(img, (pw, ph), img)
        img = canv
    if box:
        tw, th = int(box[0] * SS), int(box[1] * SS)
        sc = min(tw / img.width, th / img.height)
        img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), _I.LANCZOS)
    im.paste(img, (int(xy[0] * SS), int(xy[1] * SS)), img)
    return img.width / SS, img.height / SS


def finish(im, size=None):
    """저장 직전 1x로 downsample."""
    from PIL import Image as _I
    size = size or S
    return im.resize((int(size), int(size)), _I.LANCZOS)

TOP = 172          # 콘텐츠 시작 y
BOT = S - 96       # 콘텐츠 끝 y (푸터 위)
CW = S - 2 * PAD   # 콘텐츠 폭

POS, NEG = UP, DN


# ── 공통 프레임 ────────────────────────────────────────────────────────
def _page(meta, idx, label, sub=''):
    im = Image.new('RGB', (S, S), BG)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, S, 6], fill=ACCENT)
    dr.text((PAD, 46), _s(meta['ticker']), font=_font(True, 30), fill=ACCENT)
    tw = _font(True, 30).getlength(_s(meta['ticker']))
    dr.text((PAD + tw + 14, 55), _s(meta['name']), font=_font(False, 18), fill=INK_DIM)
    it = f'{idx}/16'
    dr.text((S - PAD - _font(False, 16).getlength(it), 52), it, font=_font(False, 16), fill=INK_FAINT)
    dr.text((PAD, 96), label, font=_font(True, 38), fill=INK)
    if sub:
        dr.text((PAD, 142), sub, font=_font(False, 17), fill=INK_FAINT)
    dr.line([(PAD, 164), (S - PAD, 164)], fill=LINE, width=1)
    return im, dr


def _footer(dr, src):
    dr.line([(PAD, S - 72), (S - PAD, S - 72)], fill=LINE, width=1)
    _wrap_draw(dr, PAD, S - 60, f'출처: {src}', _font(False, 13), INK_FAINT, CW, line_h=17)


def _note(dr, y, text, max_w=CW, interp=True):
    """해석 박스는 좌측에 액센트 바 + 크림색 배경으로 사실과 판단을 시각적으로 분리.
    예전엔 텍스트가 '해석:'으로 시작하는지로 이걸 판별했는데, 그러면 화면에 "해석:"이란
    말이 그대로 찍힌다(사용자 지적: 매 페이지에 반복되는 게 거슬림) — 이제 스타일은
    interp 파라미터로 명시적으로 정하고, 텍스트에는 그 말을 아예 넣지 않는다."""
    if not text:
        return y
    f = _font(False, 17)
    h = len(_wrap(text, f, max_w - 30)) * 25 + 16
    dr.rounded_rectangle([PAD, y, PAD + max_w, y + h], radius=8,
                         fill=(0xfb, 0xf6, 0xec) if interp else SURFACE)
    if interp:
        dr.rectangle([PAD, y, PAD + 4, y + h], fill=ACCENT)
    _wrap_draw(dr, PAD + 18, y + 8, text, f, INK_DIM, max_w - 30, line_h=25)
    return y + h + 14


# ── 차트 프리미티브 ────────────────────────────────────────────────────
def _kpi_tiles(dr, y, items, cols=3, h=112):
    """(라벨, 값, 보조문구, 방향) 타일 그리드.

    sub(보조문구)가 타일 폭보다 길면 옆 타일을 침범하며 잘려 보이던 문제(자동생성
    긴 문구·4칸 이상으로 좁아진 타일에서 실제 발생) — 최대 2줄로 줄바꿈한다."""
    gap = 16
    w = (CW - gap * (cols - 1)) / cols
    sf0 = _font(False, 14)
    max_sub_lines = max((len(_wrap_lines(it[2], sf0, w - 32)) for it in items if len(it) > 2 and it[2]), default=1)
    h = max(h, 80 + max_sub_lines * 17 + 10)
    for i, it in enumerate(items):
        label, val, sub, dirn = (list(it) + ['', 'flat'])[:4]
        cx = PAD + (i % cols) * (w + gap)
        cy = y + (i // cols) * (h + gap)
        dr.rounded_rectangle([cx, cy, cx + w, cy + h], radius=12, fill=SURFACE)
        lf = _font(False, 15)
        dr.text((cx + 18, cy + 14), _s(_wrap_lines(label, lf, w - 32)[0]) if lf.getlength(label) > w - 32 else label,
                font=lf, fill=INK_FAINT)
        col = {'up': POS, 'dn': NEG}.get(dirn, INK)
        vf = _font(True, 30)
        val_s = val
        # 값 자체가 타일 폭을 넘으면(예: 좁은 4칸 타일에 긴 숫자) 폰트를 살짝 줄인다 —
        # 값은 핵심 정보라 줄바꿈보다 축소가 낫다.
        if vf.getlength(val_s) > w - 32:
            vf = _font(True, 24)
        dr.text((cx + 18, cy + 40), val_s, font=vf, fill=col)
        if sub:
            sf = _font(False, 14)
            for j, ln in enumerate(_wrap_lines(sub, sf, w - 32)):
                dr.text((cx + 18, cy + 80 + j * 17), ln, font=sf, fill=INK_FAINT)
    rows = (len(items) + cols - 1) // cols
    return y + rows * (h + gap)


# 보고통화. deck_pages.configure()가 종목마다 set_currency()로 맞춘다 —
# deck_pages를 여기서 import하면 순환이라(deck_pages → deck16) 값만 넘겨받는다.
CURRENCY = 'USD'


def set_currency(code):
    global CURRENCY
    CURRENCY = code if code in ('USD', 'KRW') else 'USD'


def _mfmt(m, dp=1):
    """이미 M(백만) 단위인 값을 $M/$B/$T로 자동 전환. $1000M(=$1B) 이상인 대형주(예:
    PLTR 분기매출)에서 "$1632.6M" 같은 안 읽히는 표기가 나오는 걸 막고, $1,000,000M(=$1T)
    이상(TSLA 시총 등)도 B에서 안 멈추고 T까지 이어간다.
    음수는 "-$X" 형태로(달러기호 뒤에 마이너스가 붙는 "$-X" 오표기 방지).

    ⚠️ 이 함수는 deck_pages._mB와 같은 알고리즘의 **두 번째 구현**이다. 한쪽만
    원화를 알면 같은 카드 안에서 표는 '5,767억원'인데 도넛 중앙은 '$576.7B'로
    갈린다(에코프로비엠 사업부문 페이지에서 실제로 그렇게 나왔다) — 통화 분기를
    양쪽에 똑같이 둔다."""
    if m is None:
        return '—'
    neg = m < 0
    am = abs(m)
    sign = '-' if neg else ''
    if CURRENCY == 'KRW':
        if am >= 1_000_000:
            val, unit = am / 1_000_000, '조'
        elif am >= 100:
            val, unit = am / 100, '억'
        else:
            val, unit = am, '백만'
        return f'{sign}{val:,.{0 if val >= 1000 else dp}f}{unit}원'
    if am >= 1_000_000:
        body = f'{am/1_000_000:.{dp}f}T'
    elif am >= 1000:
        body = f'{am/1000:.{dp}f}B'
    else:
        body = f'{am:.{dp}f}M'
    return f'{sign}${body}'


def _donut(dr, cx, cy, r, segs, inner=0.58, total_override=None):
    """segs: [(label, value, pct)] — 가운데 총합, 각 조각 위에 비중 표시.

    total이 진짜 0(부문별 매출 데이터가 아예 없는 종목 — 자동생성 초안에서 실제로
    발생)일 때 "0 or 1" 식으로 1을 대입하면 나눗셈은 안 죽지만 가운데 총합 라벨이
    "$1.0M"이라는 가짜 숫자로 찍힌다(실제 발견) — 링 대신 빈 원 + "데이터 없음"으로
    정직하게 표시. total_override: 부문별 분해는 없어도 회사 전체 매출은 다른 데서
    이미 아는 경우(자동생성 종목 흔함) — 링은 못 그려도 가운데 숫자는 진짜 값을
    보여준다("부문 비중 모른다"≠"매출 자체를 모른다", 이 둘을 구분 안 하면 실제로
    아는 숫자를 "데이터 없음"으로 숨기는 꼴이 된다고 지적받았다)."""
    import math
    # 값이 None인 조각이 있을 수 있다 — '모른다'와 '0이다'는 다른 사실이고,
    # 모르는 건 링에서 빼되 아는 조각은 그대로 그린다.
    segs = [s for s in segs if isinstance(s[1], (int, float))]
    total = sum(s[1] for s in segs)
    if not total:
        ir_ = int(r * inner)
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LINE, width=2)
        dr.ellipse([cx - ir_, cy - ir_, cx + ir_, cy + ir_], fill=BG)
        if total_override:
            tot = _mfmt(total_override)
            dr.text((cx - _font(True, 26).getlength(tot) / 2, cy - 20), tot, font=_font(True, 26), fill=INK)
            f = _font(False, 12)
            t = '총 매출\n(부문비중 미상)'
            for i, ln in enumerate(t.split('\n')):
                dr.text((cx - f.getlength(ln) / 2, cy + 10 + i * 15), ln, font=f, fill=INK_FAINT)
        else:
            f = _font(False, 13)
            t = '부문별 매출\n데이터 없음'
            for i, ln in enumerate(t.split('\n')):
                dr.text((cx - f.getlength(ln) / 2, cy - 12 + i * 16), ln, font=f, fill=INK_FAINT)
        return
    start = -90
    labels = []
    for i, s in enumerate(segs):
        ext = 360 * s[1] / total
        dr.pieslice([cx - r, cy - r, cx + r, cy + r], start, start + ext,
                    fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
        mid = math.radians(start + ext / 2)
        rr = r * (1 + inner) / 2                      # 도넛 띠 한가운데
        labels.append((cx + rr * math.cos(mid), cy + rr * math.sin(mid),
                       f'{s[2]}%' if len(s) > 2 else f'{s[1]/total*100:.0f}%', ext))
        start += ext
    ir_ = int(r * inner)
    dr.ellipse([cx - ir_, cy - ir_, cx + ir_, cy + ir_], fill=BG)
    # 조각별 비중 — 고정 각도(22°) 문턱값은 반지름이 작은 도넛(r=78 등)에서 여전히
    # 라벨이 자기 조각 폭보다 넓어 옆 조각·중앙 총합 숫자와 겹쳤다(실제 발견: AAPL
    # 5부문에서 "6.89%"·"8.09%" 라벨이 옆 라벨/중앙 "$109.4B"와 겹침). 각도 대신
    # 그 조각의 실제 호(弧) 폭과 라벨 텍스트 폭을 직접 비교해 생략 여부를 정한다.
    rr_lbl = r * (1 + inner) / 2
    fl = _font(True, 17)
    tot = _mfmt(total)
    tot_f = _font(True, 30)
    tot_half_w = tot_f.getlength(tot) / 2
    for lx, ly, txt, ext in labels:
        arc_w = 2 * math.pi * rr_lbl * (ext / 360)
        if fl.getlength(txt) > arc_w * 1.15:
            continue
        # 위 호폭 검사만으로는 못 잡는 경우가 있다 — 조각이 수평(3시/9시) 방향에
        # 가까우면 라벨 자체는 자기 조각 폭엔 들어가도 중앙의 굵고 넓은 총합 숫자
        # ("$109.4B" 등) 영역과 수평으로 겹친다(실제 발견: AAPL Americas 42.85%
        # 라벨이 "$109.4B"와 겹침). 라벨이 중앙 숫자와 같은 수평 밴드에 있고 반경
        # 방향으로도 아직 그 폭 안이면 생략.
        half_w = fl.getlength(txt) / 2
        # 여유폭을 너무 넉넉히 주면(+6) PLTR처럼 2부문 50:50에 가까운 흔한 경우까지
        # 여유 1~2px 차이로 라벨이 통째로 사라졌다(실제 발견 — 과잉 억제 회귀) —
        # 최소한의 여백(+2)만 남긴다.
        if abs(ly - cy) < 24 and (rr_lbl - half_w) < tot_half_w + 2:
            continue
        dr.text((lx - half_w, ly - 10), txt, font=fl, fill=(255, 255, 255))
    dr.text((cx - tot_half_w, cy - 24), tot, font=tot_f, fill=INK)
    dr.text((cx - _font(False, 14).getlength('총 매출') / 2, cy + 12), '총 매출',
            font=_font(False, 14), fill=INK_FAINT)


def _legend(dr, x, y, segs, w=None, val_fmt=_mfmt):
    for i, s in enumerate(segs):
        c = SEGMENT_COLORS[i % len(SEGMENT_COLORS)]
        dr.rounded_rectangle([x, y + 5, x + 14, y + 19], radius=3, fill=c)
        dr.text((x + 24, y), _s(s[0]), font=_font(True, 17), fill=INK)
        line2 = val_fmt(s[1]) + (f'  ·  {s[2]}%' if len(s) > 2 else '')
        dr.text((x + 24, y + 24), line2, font=_font(False, 15), fill=INK_FAINT)
        y += 56
    return y


def _hbar(dr, x, y, w, items, fmt=lambda v: f'{v:,.0f}', label_w=200, bar_h=26, gap=14,
          color=None, signed=False):
    """수평 막대 — items: [(label, value)]."""
    if not items:
        return y
    vals = [v for _, v in items]
    lo = min(min(vals), 0) if signed else 0
    hi = max(max(vals), 0)
    span = (hi - lo) or 1
    zero_x = x + label_w + (0 - lo) / span * (w - label_w - 90)
    plot_w = w - label_w - 90
    lf = _font(False, 16)
    for label, v in items:
        # label_w는 막대 시작 위치 계산에만 쓰이고 텍스트 자체엔 폭 제한이 없어서,
        # 긴 라벨(예: 기관명+괄호 설명)이 label_w를 넘으면 그대로 막대·값 위로
        # 흘러넘쳤다(실제 발생: TAM 페이지에서 작은 막대 옆 긴 기관명이 "$30.0B"
        # 값 텍스트와 겹침) — label_w 안에 들어가게 말줄임표로 자른다.
        lbl = _s(label)
        if lf.getlength(lbl) > label_w - 10:
            while lbl and lf.getlength(lbl + '…') > label_w - 10:
                lbl = lbl[:-1]
            lbl += '…'
        dr.text((x, y + 4), lbl, font=lf, fill=INK_DIM)
        bw = abs(v) / span * plot_w
        bx = zero_x if v >= 0 else zero_x - bw
        c = color or (POS if v >= 0 else NEG)
        dr.rounded_rectangle([bx, y, bx + max(bw, 2), y + bar_h], radius=4, fill=c)
        vt = fmt(v)
        vx = bx + bw + 10 if v >= 0 else bx - 10 - _font(True, 15).getlength(vt)
        dr.text((vx, y + 4), vt, font=_font(True, 15), fill=INK)
        y += bar_h + gap
    if signed and lo < 0:
        dr.line([(zero_x, y - gap - bar_h - 4), (zero_x, y - gap + 2)], fill=LINE, width=1)
    return y


def _vbar(dr, x, y, w, h, items, fmt=lambda v: f'{v:+.0f}%', hi_idx=None):
    """세로 막대(부호 있음) — items: [(label, value)]."""
    vals = [v for _, v in items]
    lo, hi = min(min(vals), 0), max(max(vals), 0)
    # 최고 막대의 값 라벨이 차트 위로 삐져나가 잘리던 문제 — 위쪽 여유를 준다
    hi = hi * 1.14 if hi > 0 else hi
    lo = lo * 1.10 if lo < 0 else lo
    span = (hi - lo) or 1
    base = y + h * hi / span
    bw = w / len(items) * 0.62
    gap = w / len(items)
    for i, (lb, v) in enumerate(items):
        bx = x + i * gap + (gap - bw) / 2
        bh = abs(v) / span * h
        by = base - bh if v >= 0 else base
        c = POS if v >= 0 else NEG
        if hi_idx is not None and i != hi_idx:
            c = tuple(min(255, int(ch + (255 - ch) * 0.45)) for ch in c)
        dr.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=c)
        f = _font(True, 11)
        t = fmt(v)
        dr.text((bx + bw / 2 - f.getlength(t) / 2, by - 16 if v >= 0 else by + bh + 4), t, font=f, fill=INK_DIM)
        fl = _font(False, 11)
        # 축 라벨은 막대·값라벨보다 확실히 아래에 — 음수 막대의 값라벨과 겹치던 버그 수정
        dr.text((x + i * gap + gap / 2 - fl.getlength(lb) / 2, y + h + 22), lb, font=fl, fill=INK_FAINT)
    dr.line([(x, base), (x + w, base)], fill=LINE, width=1)
    return y + h + 44


def _table(dr, x, y, w, header, rows, widths, aligns=None, row_h=36, emph=None):
    """header: [str], rows: [[str]], widths: 비율 리스트.

    칸 폭을 넘는 텍스트는 말줄임표로 자르던 걸(내용이 잘려 안 보임 — 지적받음)
    실제 줄바꿈(최대 2줄)으로 바꿨다. 행 높이가 고정이면 2줄짜리 셀이 다음 행과
    겹치므로, 행마다 실제 필요한 줄 수를 먼저 계산해 그 행만 높인다."""
    tot = sum(widths)
    xs, acc = [], 0
    for wd in widths:
        xs.append(x + acc / tot * w)
        acc += wd
    aligns = aligns or ['l'] + ['r'] * (len(header) - 1)

    def _lines(txt, cw, font):
        return _wrap_lines(_s(txt), font, cw - 12) or ['']

    def put(cells, fy, color, font, fill_row=None, row_hh=row_h):
        if fill_row:
            dr.rectangle([x, fy - 6, x + w, fy + row_hh - 10], fill=fill_row)
        for i, c in enumerate(cells):
            cw = (xs[i + 1] - xs[i]) if i + 1 < len(xs) else (x + w - xs[i])
            lines = _lines(c, cw, font)
            for j, ln in enumerate(lines):
                tw = font.getlength(ln)
                cx = xs[i] if aligns[i] == 'l' else xs[i] + cw - tw - 8
                dr.text((cx, fy + j * 19), ln, font=font, fill=color)

    fy_f = _font(True, 15)
    put(header, y, INK_FAINT, fy_f, row_hh=row_h)
    y += 26
    dr.line([(x, y), (x + w, y)], fill=INK_DIM, width=1)
    y += 10
    for i, r in enumerate(rows):
        strong = emph and i in emph
        f = _font(True, 16) if strong else _font(False, 16)
        # 이 행에서 가장 많이 줄바꿈되는 칸 기준으로 행 높이를 늘린다.
        n_lines = 1
        for ci, c in enumerate(r):
            cw = (xs[ci + 1] - xs[ci]) if ci + 1 < len(xs) else (x + w - xs[ci])
            n_lines = max(n_lines, len(_lines(c, cw, f)))
        this_h = row_h + (n_lines - 1) * 19
        put(r, y, INK if strong else INK_DIM, f, SURFACE if strong else None, row_hh=this_h)
        y += this_h
        dr.line([(x, y - 10), (x + w, y - 10)], fill=LINE, width=1)
    return y


def _waterfall(dr, x, y, w, h, items, unit=1000.0, start=0.0):
    """items: [(label, delta)] — 마지막 항목은 최종 합계 막대로 그림."""
    vals = [v / unit for _, v in items]
    run, tops, bots = start, [], []
    for i, v in enumerate(vals):
        if i == len(vals) - 1:
            tops.append(max(v, 0)); bots.append(min(v, 0))
        else:
            nxt = run + v
            tops.append(max(run, nxt)); bots.append(min(run, nxt))
            run = nxt
    lo, hi = min(bots + [0]), max(tops + [0])
    pad = (hi - lo) * 0.12 or 1          # 값 라벨이 상단에 붙어 잘리던 문제 방지
    lo, hi = lo - pad * 0.3, hi + pad
    span = (hi - lo) or 1
    def ypx(v):
        return y + h - (v - lo) / span * h
    bw = w / len(items) * 0.6
    gap = w / len(items)
    run = start
    for i, ((lb, raw), v) in enumerate(zip(items, vals)):
        bx = x + i * gap + (gap - bw) / 2
        last = i == len(vals) - 1
        if last:
            top, bot = max(v, 0), min(v, 0)
            c = POS if v >= 0 else NEG
        else:
            nxt = run + v
            top, bot = max(run, nxt), min(run, nxt)
            c = POS if v >= 0 else NEG
            run = nxt
        y0, y1 = ypx(top), ypx(bot)
        dr.rounded_rectangle([bx, y0, bx + bw, max(y1, y0 + 2)], radius=3,
                             fill=INK_DIM if last else c)
        f = _font(True, 12)
        t = f'{v:+,.1f}' if not last else f'{v:,.1f}'
        dr.text((bx + bw / 2 - f.getlength(t) / 2, y0 - 17), t, font=f, fill=INK)
        fl = _font(False, 11)
        for j, ln in enumerate(_wrap_lines(lb, fl, gap - 4)):
            dr.text((x + i * gap + gap / 2 - fl.getlength(ln) / 2, y + h + 8 + j * 14),
                    ln, font=fl, fill=INK_FAINT)
    dr.line([(x, ypx(0)), (x + w, ypx(0))], fill=LINE, width=1)
    return y + h + 44


def _wrap_lines(text, font, max_w):
    words, out, cur = _s(text).split(), [], ''
    for wd in words:
        t = (cur + ' ' + wd).strip()
        if font.getlength(t) <= max_w or not cur:
            cur = t
        else:
            out.append(cur); cur = wd
    if cur:
        out.append(cur)
    return out[:2]


def _timeline(dr, x, y, w, events, dot=9, gap=None, label_w=136, reserve=0):
    """events: [(when, title, desc, weight)] — 좌측 세로선 + 마커.
    when 라벨은 세로선 왼쪽에 우측정렬 — 좌측정렬이면 긴 라벨이 선/점을 침범했음.
    reserve: 타임라인 다음에 해석 노트 박스 등이 더 그려질 때, 그 공간을 미리 비워두는
    여백(px) — 이게 없으면 항목 수가 많은 종목(예: TSLA 9개)에서 자동간격 계산이 노트
    박스 자리까지 다 채워버려 노트가 푸터와 겹친다(실제 발생).

    title은 원래 줄바꿈 없이 한 줄로 그렸는데, 자동생성 데이터(autogen.py)의 긴 사건
    설명(예: 5개사 인수 나열)이 캔버스 밖으로 잘려 나가는 문제가 실제로 있었다 —
    _wrap_lines로 최대 2줄까지 감싸고, 2줄짜리 항목이 있으면 그 항목들만 행 높이를
    늘려 다음 항목과 안 겹치게 한다(전부 균일하게 늘리면 짧은 제목뿐인 종목에서
    타임라인이 불필요하게 늘어짐)."""
    line_x = x + label_w
    n = len(events)
    title_w = w - label_w - 30
    tf = _font(True, 19)
    wrapped = [_wrap_lines(title, tf, title_w) for _, title, _, _ in events]
    # 항목 수가 많으면(자동생성 연혁이 길어질 때) 위 min(96, ...) 계산만으로는 하한이
    # 없어 간격이 한 줄 글자 높이(~24px)보다도 작아질 수 있다 — 그러면 다음 항목
    # 제목이 앞 항목과 그대로 겹쳐 읽을 수 없는 글자 뭉텅이가 된다(실제 발견: AAPL
    # 11개 항목). 최소 34px은 항상 보장 — 그래도 안 맞으면 reserve 영역을 침범해서라도
    # 겹치는 것보다는 낫다(호출부가 항목 수를 줄이는 게 근본 해법).
    base_gap = gap or max(28, min(96, (BOT - 40 - reserve - y) // max(n, 1)))
    # 2줄 제목은 한 줄(~24px)만큼 아래 항목과 겹칠 여지가 있어 그 항목의 다음 간격만 보정.
    row_gaps = [base_gap + (24 if len(lines) > 1 else 0) for lines in wrapped]
    total_h = sum(row_gaps[:-1]) + 12 if n > 1 else 12
    dr.line([(line_x, y + 6), (line_x, y + total_h)], fill=LINE, width=2)
    for i, (when, title, desc, weight) in enumerate(events):
        c = ACCENT if weight == 'high' else INK_FAINT
        f = _font(True, 14)
        # when 라벨을 세로선 왼쪽에 우측정렬만 하고 폭 제한이 없어서, 긴 라벨(예:
        # "미국 대법원 판결 (Epic Games)")이 label_w를 넘으면 캔버스 왼쪽 바깥으로
        # 밀려나가 글자 앞부분이 잘렸다(실제 발견: AAPL) — label_w 안에 들어가게
        # 말줄임표로 자른다(_hbar의 라벨 처리와 같은 패턴).
        wl = _s(when)
        avail = label_w - 24
        if f.getlength(wl) > avail:
            while wl and f.getlength(wl + '…') > avail:
                wl = wl[:-1]
            wl += '…'
        dr.text((line_x - 20 - f.getlength(wl), y + 1), wl, font=f, fill=INK_FAINT)
        dr.ellipse([line_x - dot, y + 6 - dot, line_x + dot, y + 6 + dot], fill=c)
        ty = y - 3
        for ln in wrapped[i]:
            dr.text((line_x + 24, ty), ln, font=tf, fill=INK)
            ty += 24
        if desc:
            _wrap_draw(dr, line_x + 24, ty + 3, desc, _font(False, 15), INK_FAINT,
                       title_w, line_h=21)
        y += row_gaps[i]
    return y


def _line_chart(dr, x, y, w, h, series, colors, labels, bands=None):
    """series: [[float,...]] 동일 길이. bands: [(y값, 색, 라벨)] 수평 기준선."""
    flat = [v for s in series for v in s] + [b[0] for b in (bands or [])]
    lo, hi = min(flat), max(flat)
    span = (hi - lo) or 1
    pad = span * 0.08
    lo, hi = lo - pad, hi + pad
    span = hi - lo

    def ypx(v):
        return y + h - (v - lo) / span * h

    for b in (bands or []):
        by = ypx(b[0])
        for xx in range(int(x), int(x + w), 12):
            dr.line([(xx, by), (xx + 6, by)], fill=b[1], width=2)
        dr.text((x + w + 8, by - 9), b[2], font=_font(True, 13), fill=b[1])
    for s, c in zip(series, colors):
        pts = [(x + w * i / (len(s) - 1), ypx(v)) for i, v in enumerate(s)]
        dr.line(pts, fill=c, width=3, joint='curve')
    dr.line([(x, y + h), (x + w, y + h)], fill=LINE, width=1)
    for i, lb in enumerate(labels):
        f = _font(False, 12)
        px = x + w * i / max(len(labels) - 1, 1)
        dr.text((min(px, x + w - f.getlength(lb)), y + h + 10), lb, font=f, fill=INK_FAINT)
    return y + h + 32


def _score_rows(dr, x, y, w, rows, maxv=2):
    """CANSLIM류 스코어카드 — (코드, 항목, 점수, 코멘트)."""
    for code, name, sc, cmt in rows:
        col = [NEG, ACCENT, POS][sc]
        dr.ellipse([x, y + 2, x + 34, y + 36], fill=col)
        f = _font(True, 18)
        dr.text((x + 17 - f.getlength(code) / 2, y + 10), code, font=f, fill=(255, 255, 255))
        dr.text((x + 48, y + 2), _s(name), font=_font(True, 17), fill=INK)
        for k in range(maxv + 1):
            bx = x + w - 78 + k * 22
            on = k < sc if sc else False
            dr.rounded_rectangle([bx, y + 10, bx + 15, y + 25], radius=3,
                                 fill=col if on else LINE)
        _wrap_draw(dr, x + 48, y + 24, cmt, _font(False, 14), INK_FAINT, w - 150, line_h=19)
        y += 60
        dr.line([(x, y - 8), (x + w, y - 8)], fill=LINE, width=1)
    return y
