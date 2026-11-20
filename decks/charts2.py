# -*- coding: utf-8 -*-
"""16p 개편에서 추가된 차트 프리미티브 — 히트맵·MDD·주봉·듀얼축·사진원형·누적막대.

deck16.py(1차 프리미티브)와 같은 라이트테마를 공유한다.
"""
import sys
import datetime as _dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deck16 import (  # noqa: E402
    S, PAD, CW, BG, SURFACE, LINE, INK, INK_DIM, INK_FAINT, ACCENT, POS, NEG, FLAT,
    SEGMENT_COLORS, _font, _s,
)


# 가격 축 라벨용 보고통화. deck_pages.configure()가 종목마다 set_currency()로 맞춘다.
# deck_pages를 여기서 import하면 순환이라(deck_pages → charts2), 값만 넘겨받는다.
CURRENCY = 'USD'


def set_currency(code):
    global CURRENCY
    CURRENCY = code if code in ('USD', 'KRW') else 'USD'


def _price_label(v, dp=None):
    """주가 축 라벨. 원화는 소수점이 무의미하고(1원 미만 호가 없음) 자릿수가 커서
    천단위 구분 정수로만 찍는다."""
    if CURRENCY == 'KRW':
        return f'{v:,.0f}원'
    if dp is not None:
        return f'${v:,.{dp}f}'
    return f'${v:,.2f}' if v < 10 else f'${v:,.0f}'


def _tint(color, amount):
    """흰색 쪽으로 amount(0~1)만큼 섞기."""
    return tuple(min(255, int(c + (255 - c) * amount)) for c in color)


# ── 연도×월 상승률 히트맵 ──────────────────────────────────────────────
def heatmap(dr, x, y, w, data, row_h=34, head_h=30):
    years = data['years']
    label_w = w * 0.085
    cw = (w - label_w) / 13
    f_h = _font(True, 15)

    heads = ['연도'] + [f'{m}월' for m in range(1, 13)] + ['연간']
    for i, h in enumerate(heads):
        cx = x + (0 if i == 0 else label_w + (i - 1) * cw)
        cwid = label_w if i == 0 else cw
        dr.text((cx + cwid / 2 - f_h.getlength(h) / 2, y + 7), h, font=f_h, fill=INK_DIM)
    y += head_h
    dr.line([(x, y), (x + w, y)], fill=INK_DIM, width=1)

    def cell(cx, cwid, cy, val, bold=False):
        if val is None:
            # 상장 첫 달처럼 원천적으로 수익률이 없는 칸은 파이썬 None의 repr이 아니라
            # 빈 칸(—)로 보여야 한다(실제로 "None"이라는 글자가 화면에 찍히는 버그였음).
            t, col, f = '—', _tint(INK_FAINT, 0.35), _font(False, 15)
            dr.text((cx + cwid / 2 - f.getlength(t) / 2, cy + 8), t, font=f, fill=col)
            return
        t = f'{val:+.0f}'
        col = POS if val > 0 else (NEG if val < 0 else FLAT)
        a = min(abs(val) / 60.0, 1.0)
        if a > 0.12:
            dr.rectangle([cx + 2, cy + 2, cx + cwid - 2, cy + row_h - 4], fill=_tint(col, 1 - a * 0.20))
        f = _font(True, 15) if bold else _font(False, 15)
        dr.text((cx + cwid / 2 - f.getlength(t) / 2, cy + 8), t, font=f, fill=col)

    for yr in years:
        f = _font(True, 15)
        dr.text((x + label_w / 2 - f.getlength(str(yr)) / 2, y + 8), str(yr), font=f, fill=INK)
        for m in range(1, 13):
            cell(x + label_w + (m - 1) * cw, cw, y, data['matrix'][yr][m])
        cell(x + label_w + 12 * cw, cw, y, data['annual'].get(yr), bold=True)
        y += row_h
        dr.line([(x, y), (x + w, y)], fill=LINE, width=1)

    # 연간 열의 평균·승률도 채운다(연도별 연간수익률 기준)
    ann_vals = [v for v in data['annual'].values() if v is not None]
    ann_avg = sum(ann_vals) / len(ann_vals) if ann_vals else None
    ann_win = (sum(1 for v in ann_vals if v > 0) / len(ann_vals) * 100) if ann_vals else None

    for name, src, ann in (('평균', data['avg'], ann_avg), ('승률', data['win'], ann_win)):
        dr.rectangle([x, y, x + w, y + row_h], fill=SURFACE)
        f = _font(True, 15)
        dr.text((x + label_w / 2 - f.getlength(name) / 2, y + 8), name, font=f, fill=INK)

        def put(cx, v, bold=False):
            if v is None:
                t, col = '—', INK_FAINT
            else:
                t = f'{v:+.0f}'
                col = (POS if v >= 50 else (NEG if v < 34 else FLAT)) if name == '승률' \
                    else (POS if v > 0 else (NEG if v < 0 else FLAT))
            ff = _font(True, 15)
            dr.text((cx + cw / 2 - ff.getlength(t) / 2, y + 8), t, font=ff, fill=col)

        for m in range(1, 13):
            put(x + label_w + (m - 1) * cw, src.get(m))
        put(x + label_w + 12 * cw, ann, bold=True)
        y += row_h
        dr.line([(x, y), (x + w, y)], fill=LINE, width=1)
    return y


# ── MDD(전고점 대비 낙폭) 영역 차트 ────────────────────────────────────
def drawdown_chart(dr, x, y, w, h, dd, ref_line=None):
    ser = dd['series']
    if not ser:
        return y + h
    lo = min(min(v for _, v in ser), (ref_line or 0)) * 1.06
    span = abs(lo) or 1

    def ypx(v):
        return y + (-v / span) * h

    for g in range(0, int(abs(lo)) + 1, 20):
        gy = ypx(-g)
        dr.line([(x, gy), (x + w, gy)], fill=LINE, width=1)
        dr.text((x - 46, gy - 9), ('0%' if g == 0 else f'-{g}%'), font=_font(False, 13), fill=INK_FAINT)

    n = len(ser)
    pts = [(x + w * i / (n - 1), ypx(v)) for i, (_, v) in enumerate(ser)]
    dr.polygon([(x, y)] + pts + [(x + w, y)], fill=_tint(NEG, 0.86))
    dr.line(pts, fill=NEG, width=2, joint='curve')

    if ref_line is not None:
        ry = ypx(ref_line)
        for xx in range(int(x), int(x + w), 11):
            dr.line([(xx, ry), (xx + 5, ry)], fill=ACCENT, width=2)
        lab = f'조회기간 최대 {ref_line:.0f}%'
        # ref_line은 보통 조회기간 최저점(=lo 산출 기준) 그 자체라 점선이 항상 차트
        # 바닥 바로 위(6% 여백)에 붙는다 — 라벨을 밑에 달면(ry+6) 그 여백 밖, 즉
        # 연도 라벨 행과 겹치는 자리로 새어나갔다(실제 발견: AAPL 30년 MDD에서
        # "조회기간 최대 -82%"가 "2023 2025" 연도와 겹침). 점선 위에 달면 항상
        # 플롯 안쪽이라 안전하다.
        dr.text((x + w - _font(True, 13).getlength(lab), ry - 18), lab, font=_font(True, 13), fill=ACCENT)

    yrs = {}
    for i, (t, _) in enumerate(ser):
        yrs.setdefault(_dt.datetime.utcfromtimestamp(t).year, i)
    f = _font(False, 13)
    items = sorted(yrs.items())[1:]
    # 조회기간이 길어지면(AAPL 30년 등) 매년 라벨을 다 찍으면 "1997 1998 1999..."가
    # 다닥다닥 붙어 서로 겹치고 그 아래 문장까지 침범했다(실제 발견) — 세로 구분선은
    # 매년 그대로 두되(가벼우니 촘촘해도 무방), 글자 라벨만 폭에 맞게 솎아낸다.
    max_labels = max(1, int(w / 55))
    step = max(1, -(-len(items) // max_labels))  # ceil
    for idx, (yr, i) in enumerate(items):
        px = x + w * i / (n - 1)
        dr.line([(px, y), (px, y + h)], fill=_tint(LINE, 0.35), width=1)
        if idx % step == 0:
            dr.text((px + 5, y + h + 8), str(yr), font=f, fill=INK_FAINT)
    return y + h + 30


# ── 주봉 가격 차트 ─────────────────────────────────────────────────────
def price_chart(dr, x, y, w, h, points, ma_windows=(13, 52)):
    if len(points) < 2:
        return y + h
    closes = [c for _, c in points]
    mas = {}
    for wnd in ma_windows:
        arr = []
        for i in range(len(closes)):
            arr.append(sum(closes[max(0, i - wnd + 1):i + 1]) / wnd if i >= wnd - 1 else None)
        mas[wnd] = arr
    allv = closes + [v for a in mas.values() for v in a if v]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.08
    lo, hi = max(lo - pad, 0), hi + pad   # 주가축이 음수로 내려가지 않게
    span = (hi - lo) or 1

    def ypx(v):
        return y + h - (v - lo) / span * h

    for g in range(5):
        v = lo + span * g / 4
        gy = ypx(v)
        dr.line([(x, gy), (x + w, gy)], fill=LINE, width=1)
        dr.text((x + w + 10, gy - 8), _price_label(v, dp=1), font=_font(False, 12), fill=INK_FAINT)

    n = len(points)

    def px(i):
        return x + w * i / (n - 1)

    dr.line([(px(i), ypx(c)) for i, c in enumerate(closes)], fill=INK, width=2, joint='curve')
    for wnd, col in zip(ma_windows, (ACCENT, SEGMENT_COLORS[0])):
        seg = [(px(i), ypx(v)) for i, v in enumerate(mas[wnd]) if v]
        if len(seg) > 1:
            dr.line(seg, fill=col, width=2, joint='curve')

    lx = x
    legend = [('주봉 종가', INK)] + [(f'{w_}주 이평', c) for w_, c in zip(ma_windows, (ACCENT, SEGMENT_COLORS[0]))]
    for name, col in legend:
        dr.line([(lx, y - 12), (lx + 22, y - 12)], fill=col, width=3)
        dr.text((lx + 28, y - 21), name, font=_font(False, 13), fill=INK_DIM)
        lx += 34 + _font(False, 13).getlength(name)

    seen, f = set(), _font(False, 12)
    for i, (t, _) in enumerate(points):
        yr = _dt.datetime.utcfromtimestamp(t).year
        if yr not in seen:
            seen.add(yr)
            if len(seen) > 1:
                dr.text((px(i) - 14, y + h + 8), str(yr), font=f, fill=INK_FAINT)
    return y + h + 30


# ── 막대(실적/컨센서스) + 보조축 라인 ──────────────────────────────────
def dual_axis(dr, x, y, w, h, labels, bars, line, bar_fmt, line_fmt,
              est_from=None, bar_name='', line_name='', bar_color=None,
              line2=None, line2_fmt=None, line2_name='', line2_color=None,
              line2_own_scale=False):
    """line2: 같은 보조축(%)을 공유하는 두 번째 라인(예: GPM 옆에 OPM) — 매 포인트마다
    라벨을 달면 충돌 회피 로직이 두 배로 복잡해지므로, line2는 궤적+점만 그리고 값-라벨은
    마지막(최신) 포인트 하나만 붙인다. 과거 대비 지금 수준이 가장 중요한 정보라는 판단."""
    """막대 + 보조축 라인.

    실제로 겪은 버그: 막대 안(흰 글자) 라벨과 라인의 값-라벨 사이 충돌만 신경 썼는데,
    PLTR 대차대조표(현금 막대 vs 자기자본 라인, 둘 다 $M 스케일이라 라인이 막대 높이
    근처를 지나감)에서는 라벨이 아니라 **라인의 궤적 자체**가 막대 안 흰 글자를 가로질러
    글자가 안 보이는 문제였다. 그려지는 순서를 라인 궤적 → 막대(+막대 라벨) → 라인의
    점과 값-라벨 순으로 바꿔, 막대가 자기 영역의 라인을 덮게 하고 점/라벨은 항상 맨 위에
    보이게 한다.
    """
    bar_color = bar_color or SEGMENT_COLORS[0]
    vals = [v for v in bars if v is not None]
    # 헤드룸 20%→30%: 막대·라인이 둘 다 마지막 구간에서 최댓값을 찍으면(예: 매출 최고점과
    # 매출총이익률 최고점이 같은 해에 겹침) 라벨 두 개가 플롯 맨 위 좁은 공간에 몰려
    # 아래 clash 로직으로도 못 피하는 경우가 생김 — 여유를 늘려 애초에 덜 몰리게 한다.
    hi = (max(vals + [0]) * 1.30) or 1
    bw = w / len(labels) * 0.5
    gap = w / len(labels)
    base = y + h

    lv = [v for v in line if v is not None]
    lv2 = [v for v in (line2 or []) if v is not None]
    pts, pts2, llo, lhi, lspan = [], [], 0, 1, 1
    # line2는 기본적으로 line1과 같은 축을 쓴다(GPM vs OPM처럼 둘 다 %일 때는 같은 축이라야
    # "몇 %p 차이"가 눈에 보인다). 하지만 단위가 다르면(PER 0~1724배 vs EPS $0.09~$2.26)
    # 보조선이 통째로 바닥에 눌려 궤적도 안 보이고 라벨만 베이스라인에 쌓인다 —
    # 실제로 8p에서 EPS 라벨 뭉치가 막대·PER 라벨을 덮었다. 그럴 땐 독립 축을 준다.
    lv_all = lv + ([] if line2_own_scale else lv2)
    if lv_all:
        # 값이 음수일 때 max(lv)*1.3 은 오히려 더 작아져 축이 뒤집힌다(EPS 컨센서스에서 실제 발생).
        # 배수처럼 항상 양수인 계열은 0 기준선을 살리고, 음수 계열은 양쪽에 여백을 준다.
        lo_, hi_ = min(lv_all), max(lv_all)
        if lo_ == hi_:
            lo_, hi_ = lo_ - abs(lo_ or 1) * 0.5, hi_ + abs(hi_ or 1) * 0.5
        # 마진(%)처럼 78~82%로 폭이 좁은 계열은 range*0.42만으로는 패딩이 몇 px에 그쳐
        # 최고점이 플롯 꼭대기에 거의 붙는다 — 절대값 기준 최소 패딩을 같이 걸어준다.
        pad = max((hi_ - lo_) * 0.5, abs(hi_) * 0.15, 1)
        llo, lhi = (0 if lo_ > 0 else lo_ - pad), hi_ + pad
        lspan = (lhi - llo) or 1
    if lv2:
        if line2_own_scale:
            lo2, hi2 = min(lv2), max(lv2)
            if lo2 == hi2:
                lo2, hi2 = lo2 - abs(lo2 or 1) * 0.5, hi2 + abs(hi2 or 1) * 0.5
            pad2 = max((hi2 - lo2) * 0.35, abs(hi2) * 0.15, 0.01)
            llo2, lhi2 = (0 if lo2 > 0 else lo2 - pad2), hi2 + pad2
        else:
            llo2, lhi2 = llo, lhi
        lspan2 = (lhi2 - llo2) or 1
        pts2 = [(x + i * gap + gap / 2, base - (v - llo2) / lspan2 * h)
                for i, v in enumerate(line2) if v is not None]
        if len(pts2) > 1:
            dr.line(pts2, fill=(line2_color or (0x6b, 0x4c, 0x9a)), width=3, joint='curve')
    if lv:
        pts = [(x + i * gap + gap / 2, base - (v - llo) / lspan * h)
               for i, v in enumerate(line) if v is not None]
        if len(pts) > 1:
            dr.line(pts, fill=ACCENT, width=3, joint='curve')   # 1) 궤적 먼저

    bar_label_y = {}
    pending_labels = []   # (x_center, ly, text, font) — 점보다 나중에 그려서 항상 위에 보이게
    for i, v in enumerate(bars):   # 2) 막대가 궤적을 덮는다
        if v is None:
            continue
        bx = x + i * gap + (gap - bw) / 2
        bh = max(v, 0) / hi * h
        est = est_from is not None and i >= est_from
        dr.rounded_rectangle([bx, base - bh, bx + bw, base], radius=4,
                             fill=_tint(bar_color, 0.55) if est else bar_color)
        if est:   # 컨센서스는 빗금으로 실적과 확실히 구분
            k = int(base - bh)
            while k < base:
                dr.line([(bx, k), (bx + bw, min(k + 7, base))], fill=(255, 255, 255), width=2)
                k += 9
        f = _font(True, 14)
        t = bar_fmt(v)
        # 막대 안(흰 글자)에 넣으면 위치가 막대 높이마다 달라져 라인과의 충돌 예측이
        # 어려워진다(실제로 겪음: 현금 vs 자기자본처럼 두 계열이 비슷한 스케일일 때).
        # 항상 막대 위 바깥에 두면 위치가 일정해져 라인 라벨과의 충돌 회피가 안정적이다.
        ly = base - bh - 21
        pending_labels.append((bx + bw / 2, ly, t, f))
        bar_label_y[i] = (ly - 4, ly + 22)

    if lv:   # 3) 점은 막대 위, 막대 라벨(글자)보다는 아래 — 점이 숫자를 가리면 안 된다.
        idxs = [i for i, v in enumerate(line) if v is not None]
        for (pxx, pyy), v, i in zip(pts, lv, idxs):
            dr.ellipse([pxx - 5, pyy - 5, pxx + 5, pyy + 5], fill=ACCENT)
    line2_color = line2_color or (0x6b, 0x4c, 0x9a)
    if lv2:
        for (pxx, pyy) in pts2:
            dr.ellipse([pxx - 5, pyy - 5, pxx + 5, pyy + 5], fill=line2_color)

    # 4) 막대 라벨(숫자)은 점을 그린 다음에 그린다 — 두 계열이 비슷한 스케일이면(예:
    # 현금 막대 vs 자기자본 라인) 점이 막대 라벨 자리에 놓일 수 있는데, 그 경우도 항상
    # 라벨 글자가 점 위로 올라오게 해서 숫자가 가려지는 걸 막는다(실제 발생: "$831M"의
    # 숫자 일부가 라인의 점에 가려짐). 이건 "점"만 상정한 회피인데, 막대가 라인의
    # 스케일과 비슷하게 커지면 막대 라벨 자리를 라인의 궤적 자체(점이 아니라 선)가
    # 지나가기도 한다 — 글자 뒤에 배경색 패치를 깔아 뭐가 지나가든 항상 또렷이
    # 보이게 한다(실제 발견: AAPL 매출 막대 라벨 "$394.3B"를 GPM 라인이 관통).
    # halo(배경 패치)는 "뭐가 지나가든 글자가 또렷하게" 보이게 해주지만, 그건 **선·점**을
    # 상대로만 참이다. halo 두 개가 같은 자리에 겹치면 나중에 그리는 쪽이 먼저 그린 글자를
    # 배경색으로 지워버린다 — 실제로 PLTR 밸류에이션에서 EPS 라벨($0.09)이 바로 옆
    # 영업이익 막대 라벨을 반쯤 지웠고, EPS($1.58)가 PER 라벨을 통째로 지웠다.
    # 그래서 이미 글자가 놓인 자리를 기록해두고, 뒤에 오는 라벨이 그 자리를 피하게 한다.
    occupied = []

    def _hits(box):
        return any(not (box[2] <= o[0] or box[0] >= o[2] or box[3] <= o[1] or box[1] >= o[3])
                   for o in occupied)

    def _box(cx, ty, tw, f):
        return (cx - tw / 2 - 3, ty - 2, cx + tw / 2 + 3, ty + f.size + 2)

    def _halo_text(cx, ty, t, f, color, claim=True):
        tw = f.getlength(t)
        box = _box(cx, ty, tw, f)
        dr.rectangle(list(box), fill=BG)
        dr.text((cx - tw / 2, ty), t, font=f, fill=color)
        if claim:
            occupied.append(box)

    def _overlap_area(box):
        tot = 0.0
        for o in occupied:
            ow = min(box[2], o[2]) - max(box[0], o[0])
            oh = min(box[3], o[3]) - max(box[1], o[1])
            if ow > 0 and oh > 0:
                tot += ow * oh
        return tot

    def _free_y(cx, t, f, cands):
        """후보 y 중 이미 놓인 라벨과 안 겹치는 첫 자리.

        전부 막히면 '가장 덜 겹치는' 자리로 간다 — 예전처럼 무조건 1번 후보로 돌아가면
        이미 실패가 확인된 자리에 다시 찍어 앞 라벨을 halo로 지운다(PLTR 2023칸에서
        EPS 라벨이 영업이익 막대 라벨을 반쯤 지운 게 정확히 이 경우)."""
        tw = f.getlength(t)
        inside = [ty for ty in cands if ty >= y - 2 and ty + f.size <= base - 2]
        pool = inside or cands
        for ty in pool:
            if not _hits(_box(cx, ty, tw, f)):
                return ty
        return min(pool, key=lambda ty: _overlap_area(_box(cx, ty, tw, f)))

    for cx, ly, t, f in pending_labels:
        _halo_text(cx, ly, t, f, INK)

    # 라인 값-라벨 — 예전엔 막대 라벨·점과 안 겹치는 자리를 후보 5~6개 중에서 찾다 보니
    # 컬럼마다 위/막대안쪽/아래로 제각각 튀어(실제 지적: "GPM 라벨이 왔다갔다 해서 안
    # 예쁨") 일관성이 없어 보였다. 막대 라벨엔 배경 패치가 있어(위 _halo_text) 웬만큼
    # 겹쳐도 안 지저분하지만, 배지(halo) 두 개가 완전히 같은 자리에 겹치면 나중에
    # 그려지는 쪽이 먼저 그려진 라벨을 지워버린다(실제 발견: 막대·PER이 둘 다 그 해
    # 최고점 부근이면 "47배"·"$114B"가 겹쳐 뭉개짐) — 그래서 "점 위" 고정은 유지하되
    # 막대 라벨 존과 실제로 겹칠 때만 "점 아래"로 피한다(딱 2가지 자리뿐이라 이전의
    # 왔다갔다 하던 5~6후보 방식과 달리 예측 가능함).
    f13 = _font(True, 13)
    if lv:
        idxs = [i for i, v in enumerate(line) if v is not None]
        for (pxx, pyy), v, i in zip(pts, lv, idxs):
            t = line_fmt(v)
            # 1순위 "점 위" 고정 — 자리가 막히면 아래, 그 다음 한 칸 더 위/아래.
            _halo_text(pxx, _free_y(pxx, t, f13, [pyy - 25, pyy + 14, pyy - 42, pyy + 31, pyy - 59, pyy + 48]),
                       t, f13, ACCENT)

    # line2(OPM·EPS 등 보조선) 값-라벨 — 원래 마지막 점만 범례 이름에 끼워 넣고 그래프
    # 안에는 아예 안 보였다("OPM 수치는 보이지도 않아" 지적) — 매 포인트 다 보여주되
    # line1과 반대편(점 아래)을 1순위로 둔다. 예전엔 자리 검사 없이 고정이라 앞서 그린
    # 막대·PER 라벨을 halo로 지워버렸다 — 이제 빈 자리를 찾아 간다.
    if lv2 and line2_fmt:
        idxs2 = [i for i, v in enumerate(line2 or []) if v is not None]
        for (pxx, pyy), v, i in zip(pts2, lv2, idxs2):
            t = line2_fmt(v)
            _halo_text(pxx, _free_y(pxx, t, f13, [pyy + 14, pyy - 25, pyy + 31, pyy - 42, pyy + 48, pyy - 59]),
                       t, f13, line2_color)

    dr.line([(x, base), (x + w, base)], fill=INK_DIM, width=1)
    f = _font(False, 13)
    for i, lb in enumerate(labels):
        est = est_from is not None and i >= est_from
        dr.text((x + i * gap + gap / 2 - f.getlength(lb) / 2, base + 10), lb,
                font=_font(True, 13) if est else f, fill=ACCENT if est else INK_FAINT)
    lx = x
    line2_legend = line2_name
    if lv2 and line2_fmt and line2_name:
        line2_legend = f'{line2_name} (최근 {line2_fmt(lv2[-1])})'
    for name, col in ((bar_name, bar_color), (line_name, ACCENT), (line2_legend, line2_color)):
        if not name:
            continue
        dr.rounded_rectangle([lx, y - 16, lx + 16, y - 4], radius=3, fill=col)
        dr.text((lx + 22, y - 20), name, font=_font(False, 13), fill=INK_DIM)
        lx += 32 + _font(False, 13).getlength(name)
    return base + 34


# ── 원형 인물 사진 (없으면 이니셜 배지) ────────────────────────────────
def photo_circle(im, dr, x, y, d, path, fallback_text='', fg=None):
    from PIL import Image as _Im
    from PIL.ImageDraw import Draw as _Draw   # ImageDraw는 모듈 — Draw가 호출 대상
    from deck16 import SS
    fg = fg or ACCENT
    if path and Path(path).exists():
        try:
            ph = _Im.open(path).convert('RGB')
            sq = min(ph.size)
            left = (ph.width - sq) // 2
            dp = int(d * SS)                       # 캔버스는 SS배 — 사진도 그만큼 크게
            ph = ph.crop((left, 0, left + sq, sq)).resize((dp, dp), _Im.LANCZOS)
            mask = _Im.new('L', (dp, dp), 0)
            _Draw(mask).ellipse([0, 0, dp - 1, dp - 1], fill=255)
            im.paste(ph, (int(x * SS), int(y * SS)), mask)
            dr.ellipse([x, y, x + d, y + d], outline=LINE, width=2)
            return True
        except Exception as e:
            print(f'[사진 렌더 실패] {path}: {type(e).__name__}: {e}')   # 조용히 삼키지 않기
    dr.ellipse([x, y, x + d, y + d], fill=fg)
    f = _font(True, int(d * 0.36))
    dr.text((x + d / 2 - f.getlength(fallback_text) / 2, y + d / 2 - d * 0.25),
            fallback_text, font=f, fill=(255, 255, 255))
    return False


# ── 누적 세로 막대 ─────────────────────────────────────────────────────
def stacked_bars(dr, x, y, w, h, labels, series, colors, names, fmt):
    totals = [sum(s[i] for s in series) for i in range(len(labels))]
    hi = (max(totals + [0]) * 1.18) or 1
    bw = w / len(labels) * 0.5
    gap = w / len(labels)
    base = y + h
    for i, lb in enumerate(labels):
        bx = x + i * gap + (gap - bw) / 2
        acc = 0
        for s, c in zip(series, colors):
            bh = s[i] / hi * h
            dr.rectangle([bx, base - acc - bh, bx + bw, base - acc], fill=c)
            acc += bh
        f = _font(True, 13)
        t = fmt(totals[i])
        dr.text((bx + bw / 2 - f.getlength(t) / 2, base - acc - 20), t, font=f, fill=INK)
        fl = _font(False, 13)
        dr.text((x + i * gap + gap / 2 - fl.getlength(lb) / 2, base + 9), lb, font=fl, fill=INK_FAINT)
    dr.line([(x, base), (x + w, base)], fill=INK_DIM, width=1)
    lx = x
    for nm, c in zip(names, colors):
        dr.rounded_rectangle([lx, y - 16, lx + 16, y - 4], radius=3, fill=c)
        dr.text((lx + 22, y - 20), nm, font=_font(False, 13), fill=INK_DIM)
        lx += 32 + _font(False, 13).getlength(nm)
    return base + 32


# ── 다년 추세 미니 라인(스파크) 배열 ───────────────────────────────────
def trend_rows(dr, x, y, w, rows, row_h=54, spark_w=180):
    """[(라벨, [값...], 표시문자열, 방향색)] — 재무 항목별 다년 추세를 표로 세움."""
    for label, series, disp, good in rows:
        dr.text((x, y + 12), _s(label), font=_font(True, 17), fill=INK)
        vals = [v for v in series if v is not None]
        if len(vals) > 1:
            lo, hi = min(vals), max(vals)
            span = (hi - lo) or 1
            sx = x + w - spark_w - 190
            pts = [(sx + spark_w * i / (len(vals) - 1), y + 40 - (v - lo) / span * 30)
                   for i, v in enumerate(vals)]
            col = POS if good else NEG
            dr.line(pts, fill=col, width=3, joint='curve')
            dr.ellipse([pts[-1][0] - 4, pts[-1][1] - 4, pts[-1][0] + 4, pts[-1][1] + 4], fill=col)
        f = _font(True, 17)
        dr.text((x + w - f.getlength(disp), y + 12), disp, font=f, fill=POS if good else NEG)
        y += row_h
        dr.line([(x, y - 10), (x + w, y - 10)], fill=LINE, width=1)
    return y


# ── 캔들스틱 + 거래량 + RSI + MACD 스택 ────────────────────────────────
import datetime as _dt2  # noqa: E402


def price_stack(dr, x, y, w, rows, rsi=None, macd=None, signal=None, hist=None,
                candle_h=168, vol_h=44, rsi_h=64, macd_h=70, annotations=None, log_scale=None):
    """rows: [(ts,open,high,low,close,volume), ...] 캔들(일/월봉 공용). 넷 다 같은 x축을
    공유해야 비교가 되므로 한 함수에서 이어 그린다. rsi/macd/signal/hist 중 없는 건
    그 패널만 생략. annotations: [(year, month, label), ...] — 역사적 전환점을 세로
    강조선+짧은 라벨로 전 패널에 걸쳐 표시(사용자가 쓰던 참고 장표의 "레벨업 박스" 재현).
    log_scale: None=자동판단(길고 배율 큰 이력만 로그), True/False=종목 데이터파일에서
    강제 지정 — 자동판단이 상장 얼마 안 된 종목(IONQ 등)에도 로그를 켜서 "이상하다"는
    지적을 받았는데, 사실 "로그가 맞는 종목/선형이 맞는 종목"은 배율·기간만으로 완전히
    기계적으로 갈리는 문제가 아니라(예: 짧아도 SPAC 급등주는 로그가 나을 수 있음)
    최종 판단은 종목별로 사람이 하는 게 맞다고 봐서 오버라이드 통로를 열어둔다."""
    n = len(rows)
    if n < 2:
        return y
    gap_x = w / n
    cwid = max(gap_x * 0.55, 1.5)
    top_y = y   # 주석 세로선이 전 패널을 관통하도록 시작 y를 기억해둔다

    opens = [r[1] for r in rows]
    highs = [r[2] for r in rows]
    lows = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    vols = [r[5] or 0 for r in rows]

    # ── 1) 캔들스틱 ──
    hi, lo = max(highs), max(min(lows), 0.0001)
    # 상장 후 전체 이력(월봉)처럼 고점/저점 비율이 큰 경우(TSLA: 2010년 $1대 → 2026년
    # $300~400대, 300배+) 선형축이면 초기 수십~백여 개월이 바닥에 짜부라져 안 보인다
    # (실제 발견: 2010~2019 캔들이 전부 한 줄로 뭉개짐) — 비율이 크면 로그축으로 자동 전환.
    # 단, 비율만 보면 상장 몇 년 안 된 종목(SPAC 급락후 반등 등으로 배율이 쉽게 4배
    # 넘음 — IONQ 5년치가 실제 사례)도 로그로 잡혀버려 "얼마 안 된 종목인데 로그로 보니
    # 이상하다"는 지적을 받았다 — 로그축은 비율뿐 아니라 이력이 충분히 길 때만(월봉
    # 8년=96개월 이상) 켠다. 짧은 이력은 어차피 몇 배 차이가 나도 선형이 더 직관적.
    if log_scale is not None:
        use_log = log_scale
    else:
        # 96개월 문턱값은 "배율이 크려면 이력이 길어야 한다"는 전제였는데, 이게 깨지는
        # 경우가 실제로 나왔다(SNDK — 상장 18개월 만에 84배: $27.89→$2354.39, AI/메모리
        # 슈퍼사이클급 폭등). 선형축으로 그리니 초기 11개월 캔들이 차트 하단에 실선처럼
        # 짜부라지고, 그 자리를 매물대 회색 막대만 크게 뒤덮어 "호러물" 소리를 들었다 —
        # 배율이 극단적으로 크면(15배+) 이력이 짧아도 로그축을 켠다. 완만한 배율
        # (4~15배)은 원래 의도대로 이력이 충분히 길 때만(IONQ류 오판 방지).
        ratio = (hi / lo) if lo > 0 else 0
        use_log = ratio > 15 or (ratio > 4 and len(rows) >= 96)
    import math as _math
    if use_log:
        hi_l, lo_l = _math.log(hi), _math.log(lo)
        pad = (hi_l - lo_l) * 0.08 or 0.05
        hi_lp, lo_lp = hi_l + pad, lo_l - pad
        span_l = (hi_lp - lo_lp) or 1

        def ypx(v):
            return y + candle_h - (_math.log(max(v, 0.0001)) - lo_lp) / span_l * candle_h
    else:
        pad = (hi - lo) * 0.08 or hi * 0.05
        hi_p, lo_p = hi + pad, lo - pad
        span = (hi_p - lo_p) or 1

        def ypx(v):
            return y + candle_h - (v - lo_p) / span * candle_h

    # ── 0) 매물대(볼륨 프로파일) — 캔들보다 먼저(배경으로) 그려서 캔들이 위에 겹치게.
    # 사용자가 쓰던 참고 차트(HTS)의 "매물대" 표시를 재현 — 가격을 몇 개 구간으로
    # 나눠 그 구간에서 거래된 물량(캔들의 종가가 속한 구간에 거래량을 더함, 단순화된
    # 근사치)을 왼쪽에서 뻗어나가는 가로 막대로 보여준다.
    # 구간(bin) 경계를 선형으로만 나누면, 로그축을 쓰는 종목(수십 년간 수백~수천배
    # 오른 종목 — AAPL이 실제 사례)에서 옛날의 낮은 가격대가 전부 첫 구간 하나에
    # 뭉개져 들어가고, 캔들은 로그축이라 화면에 넓게 퍼져 있는데 매물대만 그 캔들
    # 자리와 안 맞는 좁은 회색 덩어리로 보였다(실제 발견) — 로그축일 땐 구간도
    # 로그 간격으로 나눠 캔들 위치와 항상 일치시킨다.
    n_bins = 14
    span_p = (hi - lo) or 1
    if use_log:
        lo_lb, hi_lb = _math.log(max(lo, 0.0001)), _math.log(hi)
        span_lb = (hi_lb - lo_lb) or 1

        def _bidx(price):
            return min(int((_math.log(max(price, 0.0001)) - lo_lb) / span_lb * n_bins), n_bins - 1)

        def _bbounds(bi):
            return _math.exp(lo_lb + span_lb * bi / n_bins), _math.exp(lo_lb + span_lb * (bi + 1) / n_bins)
    else:
        def _bidx(price):
            return min(int((price - lo) / span_p * n_bins), n_bins - 1)

        def _bbounds(bi):
            return lo + span_p * bi / n_bins, lo + span_p * (bi + 1) / n_bins
    bin_vols = [0.0] * n_bins
    for i in range(n):
        typical = (highs[i] + lows[i] + closes[i]) / 3
        bin_vols[_bidx(typical)] += vols[i]
    tot_vol = sum(bin_vols) or 1
    max_bin = max(bin_vols) or 1
    profile_w = w * 0.3
    pf = _font(False, 11)
    last_label_y = None  # 2026-10-25: 칸 하나하나는 13px 기준을 통과해도, 그런 칸이
    # 연속으로 많으면(PLTR 실측: 상장 초기 구간) 바로 위 라벨과 2~3px 간격으로
    # 다닥다닥 붙어 읽기 힘들었다 — "자기 칸에 들어가는가"뿐 아니라 "바로 앞
    # 라벨과 떨어져 있는가"도 봐야 진짜로 안 붙는다.
    for bi in range(n_bins):
        bv = bin_vols[bi]
        if bv <= 0:
            continue
        p_lo, p_hi = _bbounds(bi)
        yA, yB = ypx(p_lo), ypx(p_hi)
        y0, y1 = min(yA, yB), max(yA, yB)
        bw_ = profile_w * bv / max_bin
        dr.rectangle([x, y0, x + bw_, max(y1, y0 + 2)], fill=_tint(INK_FAINT, 0.72))
        pct = bv / tot_vol * 100
        # 로그축 구간을 도입한 뒤(위 개선) 예전보다 훨씬 많은 구간이 실제로 채워져,
        # 구간 하나의 세로 폭(y1-y0)이 11px 글자 한 줄보다 좁으면 라벨끼리 겹쳤다
        # (실제 발견: AAPL — "3.2%"·"3.0%"·"9.0%"...가 세로로 다닥다닥 겹침).
        # 자기 칸 안에 실제로 들어갈 때만, 그리고 바로 앞 라벨과 최소 16px 떨어졌을 때만 그린다.
        label_y = (y0 + y1) / 2
        if pct >= 3 and (y1 - y0) >= 13 and (last_label_y is None or abs(label_y - last_label_y) >= 16):
            dr.text((x + 4, label_y - 7), f'{pct:.1f}%', font=pf, fill=INK_DIM)
            last_label_y = label_y

    # y축 눈금 — 예전엔 고점·저점(+로그축이면 중간값 하나)만 딱 3개 찍었는데, 배율이
    # 큰 로그축 종목(AAPL: $0.06~$345, 5700배+)에서는 "$5"·"$0.06"처럼 뜬금없는
    # 숫자 3개만 떠 있어 가격 감이 안 잡히고 안 예뻐 보인다는 지적 — 실제 눈금선과
    # 함께 1·2·5 배수의 "깔끔한" 가격 레벨을 로그 간격대로 여러 개 찍는다.
    f_axis = _font(False, 12)

    def _fmt_axis(v):
        return _price_label(v)

    if use_log:
        levels = []
        for k in range(-3, 6):
            for m in (1, 2, 5):
                v = m * (10 ** k)
                if lo * 0.98 <= v <= hi * 1.02:
                    levels.append(v)
        levels = sorted(set(levels))
        # 너무 촘촘하면(짧은 이력) 라벨이 겹치니 최대 6개로 솎아낸다.
        if len(levels) > 6:
            step = len(levels) / 6
            levels = [levels[int(i * step)] for i in range(6)]
    else:
        levels = [lo + (hi - lo) * f for f in (0, 0.25, 0.5, 0.75, 1.0)]
    for lv in levels:
        ly = ypx(lv)
        dr.line([(x, ly), (x + w, ly)], fill=LINE, width=1)
        dr.text((x + w + 6, ly - 6), _fmt_axis(lv), font=f_axis, fill=INK_FAINT)

    for i in range(n):
        cx = x + i * gap_x + gap_x / 2
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        col = POS if c >= o else NEG
        dr.line([(cx, ypx(h)), (cx, ypx(l))], fill=col, width=2)
        top, bot = ypx(max(o, c)), ypx(min(o, c))
        dr.rectangle([cx - cwid / 2, top, cx + cwid / 2, max(bot, top + 1.5)], fill=col)
    y = y + candle_h + 10

    # ── 2) 거래량 ──
    vmax = max(vols) or 1
    for i in range(n):
        cx = x + i * gap_x + gap_x / 2
        vh = (vols[i] / vmax) * vol_h
        col = POS if closes[i] >= opens[i] else NEG
        dr.rectangle([cx - cwid / 2, y + vol_h - vh, cx + cwid / 2, y + vol_h], fill=_tint(col, 0.4))
    dr.text((x + w + 6, y - 4), '거래량', font=f_axis, fill=INK_FAINT)
    y = y + vol_h + 14

    # ── 3) RSI(14) ──
    if rsi:
        def rpx(v):
            return y + rsi_h - (v / 100) * rsi_h
        dr.rectangle([x, rpx(70), x + w, rpx(30)], fill=_tint(SEGMENT_COLORS[0], 0.88))
        for lvl in (30, 70):
            dr.line([(x, rpx(lvl)), (x + w, rpx(lvl))], fill=INK_FAINT, width=1)
        pts = [(x + i * gap_x + gap_x / 2, rpx(v)) for i, v in enumerate(rsi) if v is not None]
        if len(pts) > 1:
            dr.line(pts, fill=ACCENT, width=2, joint='curve')
        last_rsi = next((v for v in reversed(rsi) if v is not None), None)
        f13 = _font(True, 13)
        dr.text((x, y - 18), 'RSI(14)', font=_font(True, 14), fill=INK)
        if last_rsi is not None:
            t = f'{last_rsi:.0f}'
            dr.text((x + w - f13.getlength(t), y - 18), t, font=f13, fill=ACCENT)
        dr.text((x + w + 6, rpx(70) - 6), '70', font=f_axis, fill=INK_FAINT)
        dr.text((x + w + 6, rpx(30) - 6), '30', font=f_axis, fill=INK_FAINT)
        y = y + rsi_h + 18

    # ── 4) MACD(12,26,9) ──
    if macd:
        mv = [v for v in (macd + (signal or [])) if v is not None]
        if mv:
            mhi, mlo = max(mv), min(mv)
            if mhi == mlo:
                mhi, mlo = mhi + 1, mlo - 1
            mmid, mspan = (mhi + mlo) / 2, (mhi - mlo) * 1.25
            mlo2, mhi2 = mmid - mspan / 2, mmid + mspan / 2

            def mpx(v):
                return y + macd_h - (v - mlo2) / (mhi2 - mlo2) * macd_h
            zero_y = mpx(0)
            dr.line([(x, zero_y), (x + w, zero_y)], fill=INK_FAINT, width=1)
            if hist:
                for i, hv in enumerate(hist):
                    if hv is None:
                        continue
                    cx = x + i * gap_x + gap_x / 2
                    col = POS if hv >= 0 else NEG
                    yv = mpx(hv)
                    dr.rectangle([cx - cwid / 2, min(zero_y, yv), cx + cwid / 2, max(zero_y, yv)],
                                 fill=_tint(col, 0.45))
            mpts = [(x + i * gap_x + gap_x / 2, mpx(v)) for i, v in enumerate(macd) if v is not None]
            spts = [(x + i * gap_x + gap_x / 2, mpx(v)) for i, v in enumerate(signal or []) if v is not None]
            if len(mpts) > 1:
                dr.line(mpts, fill=SEGMENT_COLORS[0], width=2, joint='curve')
            if len(spts) > 1:
                dr.line(spts, fill=(0xc8, 0x72, 0x0c), width=2, joint='curve')
            dr.text((x, y - 18), 'MACD(12,26,9)', font=_font(True, 14), fill=INK)
        y = y + macd_h + 14

    # ── 역사적 전환점 주석 — 세로 강조선(전 패널 관통) + 번호 배지 ──
    # 전체 설명을 차트 위에 바로 쓰면(예전 방식) 항목이 여러 개일 때 라벨끼리
    # 겹치거나 좁은 칸에 짤린다 — 배지엔 번호만 찍고, 실제 설명은 호출부가 차트
    # 아래에 범례로 그리도록 (번호, 라벨) 목록을 반환한다.
    legend = []
    if annotations:
        bottom_y = y
        for idx, ann in enumerate(annotations, 1):
            yr, mo, label = ann[0], ann[1], ann[2]
            # 가장 가까운 봉 인덱스를 (연,월) 기준으로 찾는다 — 월봉이면 정확히 맞고,
            # 일봉이면 그 달의 첫 거래일 근처로 근사된다.
            best_i, best_d = None, None
            for i, r in enumerate(rows):
                dtp = _dt2.datetime.fromtimestamp(r[0])
                d = abs((dtp.year - yr) * 12 + (dtp.month - mo))
                if best_d is None or d < best_d:
                    best_i, best_d = i, d
            if best_i is None:
                continue
            cx = x + best_i * gap_x + gap_x / 2
            badge_r = 10
            k = 0
            while k < int((bottom_y - (top_y + badge_r * 2)) // 8):
                yy = top_y + badge_r * 2 + k * 8
                dr.line([(cx, yy), (cx, yy + 4)], fill=ACCENT, width=2)
                k += 1
            dr.ellipse([cx - badge_r, top_y, cx + badge_r, top_y + badge_r * 2], fill=ACCENT)
            f_badge = _font(True, 13)
            num = str(idx)
            dr.text((cx - f_badge.getlength(num) / 2, top_y + badge_r - 9), num,
                    font=f_badge, fill=(255, 255, 255))
            legend.append((idx, _s(label)))

    # ── x축 날짜 라벨 ──
    f3 = _font(False, 11)
    step = max(1, n // 5)
    for i in range(0, n, step):
        lbl = _dt2.datetime.fromtimestamp(rows[i][0]).strftime('%y.%m.%d')
        dr.text((x + i * gap_x + gap_x / 2 - f3.getlength(lbl) / 2, y), lbl, font=f3, fill=INK_FAINT)
    y += 18
    return y, legend
