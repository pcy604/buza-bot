"""인스타그램 캐러셀 리포트 렌더 — 1080x1080 슬라이드 8장, Pillow 직접 그리기.

card.py(개인용 빠른카드)와는 별도 시각언어 — 퍼블리시 가능한 수준을 목표로 함:
숫자마다 출처·갱신일 명시, 스칼라 아닌 벡터(방향+가속도)로 트렌드 표시.
"""
import functools
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from card import _wrap, _draw_wrapped, _s, FONT_CANDIDATES  # 텍스트 유틸 재사용

S = 1080  # 인스타그램 정사각 슬라이드
PAD = 64

BG = (0xff, 0xff, 0xff)
SURFACE = (0xf3, 0xf4, 0xf6)
LINE = (0xe2, 0xe4, 0xe8)
INK = (0x1a, 0x1d, 0x22)
INK_DIM = (0x54, 0x5b, 0x64)
INK_FAINT = (0x96, 0x9d, 0xa6)
ACCENT = (0xb8, 0x6a, 0x00)
UP = (0x1a, 0x8a, 0x4c)
DN = (0xc4, 0x38, 0x2c)
FLAT = (0x7c, 0x83, 0x8c)
DIR_COLOR = {'up': UP, 'dn': DN, 'flat': FLAT}
SEGMENT_COLORS = [(0x2f, 0x6e, 0xa8), (0x86, 0x4f, 0xa8), (0x1f, 0x8a, 0x82),
                  (0xb8, 0x4a, 0x71), (0x8a, 0x84, 0x2c)]


@functools.lru_cache(maxsize=None)
def _resolve_fonts():
    for reg, bold in FONT_CANDIDATES:
        if Path(reg).exists() and Path(bold).exists():
            return reg, bold
    raise FileNotFoundError('한글 폰트를 찾을 수 없음')


@functools.lru_cache(maxsize=None)
def _font(bold: bool, size: int):
    reg, bold_path = _resolve_fonts()
    return ImageFont.truetype(bold_path if bold else reg, size)


def _new_slide():
    im = Image.new('RGB', (S, S), BG)
    return im, ImageDraw.Draw(im)


def _header(d, draw, idx, total, label):
    """모든 슬라이드 공통 상단 — 티커·회사명·슬라이드 번호."""
    draw.text((PAD, 56), _s(d['ticker']), font=_font(True, 34), fill=ACCENT)
    tw = _font(True, 34).getlength(_s(d['ticker']))
    draw.text((PAD + tw + 16, 66), _s(d['company']), font=_font(False, 20), fill=INK_DIM)
    idx_txt = f'{idx}/{total}'
    iw = _font(False, 16).getlength(idx_txt)
    draw.text((S - PAD - iw, 62), idx_txt, font=_font(False, 16), fill=INK_FAINT)
    draw.text((PAD, 104), label, font=_font(True, 15), fill=INK_FAINT)
    draw.line([(PAD, 132), (S - PAD, 132)], fill=LINE, width=1)


def _footer(draw, source: str):
    """출처·갱신일 캡션 — 요구사항: 숫자마다 출처가 명확해야 함."""
    draw.line([(PAD, S - 76), (S - PAD, S - 76)], fill=LINE, width=1)
    draw.text((PAD, S - 58), source, font=_font(False, 14), fill=INK_FAINT)


def _vector_arrow(draw, x, y, direction: str, size: int = 18):
    """스칼라가 아니라 방향을 그리는 화살표 — up/dn/flat."""
    col = DIR_COLOR.get(direction, FLAT)
    if direction == 'up':
        pts = [(x, y + size), (x + size / 2, y), (x + size, y + size)]
    elif direction == 'dn':
        pts = [(x, y), (x + size / 2, y + size), (x + size, y)]
    else:
        pts = [(x, y + size / 2 - 3), (x + size, y + size / 2 - 3),
               (x + size, y + size / 2 + 3), (x, y + size / 2 + 3)]
    draw.polygon(pts, fill=col)


def _sparkline(draw, x, y, w, h, series: list, color):
    """작은 추세선 — 값 자체보다 궤적(방향)이 중요하므로 축 없이 라인+끝점 강조만."""
    if len(series) < 2:
        draw.line([(x, y + h / 2), (x + w, y + h / 2)], fill=INK_FAINT, width=2)
        return
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(series):
        px = x + w * i / (len(series) - 1)
        py = y + h - (v - lo) / span * h
        pts.append((px, py))
    draw.line(pts, fill=color, width=4, joint='curve')
    draw.ellipse([pts[-1][0] - 5, pts[-1][1] - 5, pts[-1][0] + 5, pts[-1][1] + 5], fill=color)


def _bar_chart(draw, x, y, w, h, labels: list, values: list, fy_flags: list, unit_fmt):
    """분기 막대그래프 — 연간(FY) 항목은 옅은 색으로 구분(분기와 스케일이 달라 섞으면 오독 유발)."""
    if not values:
        draw.text((x, y + h / 2), '데이터 없음', font=_font(False, 15), fill=INK_FAINT)
        return
    lo, hi = min(min(values), 0), max(values)
    span = (hi - lo) or 1
    bw = w / len(values) * 0.6
    gap = w / len(values)
    base_y = y + h * hi / span if hi > 0 else y + h
    for i, (v, lbl, is_fy) in enumerate(zip(values, labels, fy_flags)):
        bx = x + i * gap + (gap - bw) / 2
        bar_h = abs(v) / span * h
        by = base_y - bar_h if v >= 0 else base_y
        color = INK_FAINT if is_fy else (UP if v >= 0 else DN)
        draw.rectangle([bx, by, bx + bw, by + bar_h if v >= 0 else by + bar_h], fill=color)
        vtxt = unit_fmt(v)
        f_v = _font(True, 13)
        vw = f_v.getlength(vtxt)
        vy = by - 20 if v >= 0 else by + bar_h + 4
        draw.text((bx + bw / 2 - vw / 2, vy), vtxt, font=f_v, fill=INK)
        f_l = _font(False, 12)
        lw = f_l.getlength(lbl)
        draw.text((bx + bw / 2 - lw / 2, y + h + 10), lbl, font=f_l, fill=INK_FAINT)
    draw.line([(x, base_y), (x + w, base_y)], fill=LINE, width=1)


def _wrap_draw(draw, x, y, text, font, color, max_w, line_h=None):
    return _draw_wrapped(draw, x, y, text, font, color, max_w, line_h)


def _logo_or_monogram(im, dr, d, box=120):
    """로고 있으면 붙이고, 없으면 티커 첫 글자 모노그램 배지로 대체 — 표지가 절대 비어 보이지 않게."""
    x0, y0 = S - PAD - box, 56
    path = d.get('logo_path')
    logo = None
    if path and Path(path).exists():
        try:
            logo = Image.open(path).convert('RGBA')
        except Exception:
            logo = None
    if logo:
        lw, lh = logo.size
        scale = min(box / lw, box / lh)
        nw, nh = max(1, round(lw * scale)), max(1, round(lh * scale))
        logo = logo.resize((nw, nh), Image.LANCZOS)
        im.paste(logo, (x0 + (box - nw) // 2, y0 + (box - nh) // 2), logo)
    else:
        dr.ellipse([x0, y0, x0 + box, y0 + box], fill=ACCENT)
        letter = _s(d.get('ticker', '?'))[:1].upper()
        f = _font(True, 56)
        lw = f.getlength(letter)
        dr.text((x0 + box / 2 - lw / 2, y0 + box / 2 - 32), letter, font=f, fill=(0xff, 0xff, 0xff))


# ── 슬라이드 1: 표지 ─────────────────────────────────────────────────
def slide_cover(d):
    im, dr = _new_slide()
    dr.rectangle([0, 0, S, 10], fill=ACCENT)
    dr.text((PAD, 52), '기업 분석 리포트 · buza_alarm_bot', font=_font(True, 16), fill=INK_FAINT)
    _logo_or_monogram(im, dr, d)
    dr.text((PAD, 140), _s(d['ticker']), font=_font(True, 96), fill=ACCENT)
    dr.text((PAD, 260), _s(d['company']), font=_font(False, 32), fill=INK_DIM)
    y = _wrap_draw(dr, PAD, 420, d.get('headline', ''), _font(True, 44), INK, S - 2 * PAD, line_h=58)
    dr.text((PAD, S - 140), f'기준일 {d.get("date","")}', font=_font(False, 18), fill=INK_FAINT)
    dr.text((PAD, S - 108), '데이터 출처는 각 슬라이드 하단 · 마지막 장에 전체 요약',
            font=_font(False, 16), fill=INK_FAINT)
    return im


# ── 슬라이드 2: 사업개요 ─────────────────────────────────────────────
def slide_profile(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '사업 개요')
    p = d.get('profile') or {}
    y = _wrap_draw(dr, PAD, 170, p.get('business', '정보 없음'), _font(False, 26), INK, S - 2 * PAD, line_h=38)
    segs = [s for s in (p.get('segments') or []) if isinstance(s.get('pct'), (int, float))]
    if segs:
        y += 40
        bar_y, bar_h = y, 40
        total_pct = sum(s['pct'] for s in segs) or 1
        x = PAD
        for i, s in enumerate(segs):
            w = (S - 2 * PAD) * (s['pct'] / total_pct)
            dr.rectangle([x, bar_y, x + w, bar_y + bar_h], fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
            x += w
        y = bar_y + bar_h + 24
        lx, ly = PAD, y
        for i, s in enumerate(segs):
            label = f'{s["name"]} {s["pct"]:.0f}%'
            lw = _font(False, 18).getlength(label) + 34
            if lx + lw > S - PAD and lx > PAD:
                lx, ly = PAD, ly + 34
            dr.ellipse([lx, ly + 4, lx + 14, ly + 18], fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
            dr.text((lx + 22, ly), label, font=_font(False, 18), fill=INK_DIM)
            lx += lw
    _footer(dr, f'출처: {d.get("profile_source","최근 연차보고서(10-K/20-F)")}')
    return im


# ── 슬라이드 3: 실적 스냅샷 (벡터) ────────────────────────────────────
def slide_vectors(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '실적 스냅샷 · 방향성')
    vectors = d.get('vectors') or {}
    rows = [k for k in ('revenue', 'gross_margin', 'operating_income', 'fcf') if k in vectors]
    row_h = (S - 260) // max(len(rows), 1)
    y = 160
    for key in rows:
        v = vectors[key]
        dr.text((PAD, y + 10), v['label'], font=_font(True, 22), fill=INK)
        _sparkline(dr, PAD + 160, y + 6, 260, 50, v['series'], DIR_COLOR.get(v['dir'], FLAT))
        _vector_arrow(dr, PAD + 450, y + 16, v['dir'])
        qoq = v.get('qoq_pct')
        qoq_txt = f'{qoq:+.0f}%' if qoq is not None else '—'
        dr.text((PAD + 490, y + 8), qoq_txt, font=_font(True, 26), fill=DIR_COLOR.get(v['dir'], FLAT))
        dr.text((PAD + 490, y + 40), v['trajectory'], font=_font(False, 15), fill=INK_FAINT)
        y += row_h
        dr.line([(PAD, y - 12), (S - PAD, y - 12)], fill=LINE, width=1)
    _footer(dr, f'출처: 최근 공시 분기별 수치 · 최종 갱신 {d.get("date","")}')
    return im


# ── 슬라이드 4: 재무제표 표+그래프 ───────────────────────────────────
def slide_financials(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '재무제표 · 분기 추이')
    v = (d.get('vectors') or {}).get('revenue', {})
    full_labels = v.get('full_labels', v.get('labels', []))
    full_series = v.get('full_series', v.get('series', []))
    labels = [lb.replace(' 20', "'") for lb in full_labels]
    is_fy = [lb.upper().startswith('FY') for lb in full_labels]
    _bar_chart(dr, PAD, 190, S - 2 * PAD, 260, labels, full_series, is_fy,
              lambda x: f'${x/1e6:.1f}M' if abs(x) >= 1e6 else f'${x:,.0f}')
    dr.text((PAD, 480), '매출 (진하면 분기, 옅으면 연간 — 스케일 다름 주의)',
            font=_font(False, 14), fill=INK_FAINT)
    ty = 540
    dr.line([(PAD, ty), (S - PAD, ty)], fill=LINE, width=1)
    ty += 20
    rows = d.get('trend_rows') or []
    periods = d.get('periods') or []
    show_periods = periods[-4:]
    f_h = _font(False, 14)
    col_w = (S - 2 * PAD - 140) / max(len(show_periods), 1)
    for i, p in enumerate(show_periods):
        px = PAD + 140 + i * col_w + col_w
        tw = f_h.getlength(p)
        dr.text((px - tw, ty), p, font=f_h, fill=INK_FAINT)
    ty += 26
    dr.line([(PAD, ty), (S - PAD, ty)], fill=LINE, width=1)
    for row in rows:
        ty += 8
        dr.text((PAD, ty), row['label'], font=_font(True, 16), fill=INK_DIM)
        vals = row['values'][-4:]
        for i, val in enumerate(vals):
            px = PAD + 140 + i * col_w + col_w
            f_v = _font(True, 15)
            vw = f_v.getlength(_s(val))
            dr.text((px - vw, ty), _s(val), font=f_v, fill=INK)
        ty += 34
        dr.line([(PAD, ty), (S - PAD, ty)], fill=LINE, width=1)
    _footer(dr, f'출처: SEC EDGAR 공시 원문 · 최종 갱신 {d.get("date","")}')
    return im


# ── 슬라이드 5: 밸류에이션·기술적 ─────────────────────────────────────
def slide_valuation(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '밸류에이션 · 기술적')
    price = d.get('price') or {}
    val = d.get('valuation') or {}
    tiles = []
    if price:
        tiles.append(('현재가', f'{price["price"]} {price.get("currency","USD")}', 'flat'))
        tiles.append(('52주 범위', f'{price["low52"]}~{price["high52"]}', 'flat'))
        tiles.append(('50일선 대비', f'{price["vs_ma50"]:+.1f}%', 'up' if price['vs_ma50'] >= 0 else 'dn'))
        tiles.append(('3개월', f'{price["chg_3m"]:+.1f}%', 'up' if price['chg_3m'] >= 0 else 'dn'))
    if val:
        tiles.insert(1, ('시가총액', _fmt_money(val.get('market_cap')), 'flat'))
        if val.get('ps_ratio'):
            tiles.insert(2, ('TTM P/S', f'{val["ps_ratio"]:.2f}배', 'flat'))
    cols, rows_n = 2, (len(tiles) + 1) // 2
    tw_, th_ = (S - 2 * PAD - 20) / cols, 140
    for i, (label, value, dirn) in enumerate(tiles):
        cx = PAD + (i % cols) * (tw_ + 20)
        cy = 170 + (i // cols) * (th_ + 20)
        dr.rounded_rectangle([cx, cy, cx + tw_, cy + th_], radius=14, fill=SURFACE)
        dr.text((cx + 24, cy + 22), label, font=_font(False, 16), fill=INK_FAINT)
        dr.text((cx + 24, cy + 54), value, font=_font(True, 32), fill=DIR_COLOR.get(dirn, INK))
    _footer(dr, f'시총=발행주식수×현재가(당일) · 출처: Yahoo Finance, EDGAR · {d.get("date","")}')
    return im


# ── 슬라이드 6: 어닝콜 하이라이트 ─────────────────────────────────────
def slide_transcript(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '어닝콜 하이라이트')
    t = d.get('transcript')
    y = 180
    if not t:
        dr.text((PAD, y), '이번 분기 어닝콜 전문을 찾지 못했어요', font=_font(False, 20), fill=INK_FAINT)
        _footer(dr, '출처: 없음(커버리지 미확인)')
        return im
    if t.get('tone'):
        y = _wrap_draw(dr, PAD, y, f'경영진 톤: {t["tone"]}', _font(True, 20), ACCENT, S - 2 * PAD, line_h=28) + 24
    for h in (t.get('highlights') or [])[:4]:
        dr.ellipse([PAD + 2, y + 10, PAD + 8, y + 16], fill=INK_DIM)
        y = _wrap_draw(dr, PAD + 20, y, h, _font(False, 19), INK_DIM, S - 2 * PAD - 20, line_h=27) + 10
    _footer(dr, f'출처: 어닝콜 전문 · {d.get("date","")}')
    return im


# ── 슬라이드 7: 투자포인트·리스크 ─────────────────────────────────────
def slide_thesis(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '투자 포인트 · 리스크')
    sections = d.get('sections') or {}
    y = 170
    for key, label, col in (('current', '지금', INK), ('outlook', '전망', UP), ('risks', '리스크', DN)):
        items = (sections.get(key) or [])[:3]
        if not items:
            continue
        dr.text((PAD, y), label, font=_font(True, 20), fill=col)
        y += 34
        for it in items:
            it = _s(it)
            is_interp = it.startswith('해석:')
            marker_col = ACCENT if is_interp else INK_FAINT
            dr.ellipse([PAD + 2, y + 8, PAD + 8, y + 14], fill=marker_col)
            y = _wrap_draw(dr, PAD + 22, y, it, _font(False, 18), INK_DIM, S - 2 * PAD - 22, line_h=26) + 8
        y += 16
    _footer(dr, f'"해석:" 표시=여러 사실을 연결한 판단 · {d.get("date","")}')
    return im


# ── 슬라이드 8: 출처 요약 ────────────────────────────────────────────
def slide_sources(d, idx, total):
    im, dr = _new_slide()
    _header(d, dr, idx, total, '출처 요약')
    y = 170
    for src in (d.get('sources') or []):
        dr.text((PAD, y), src.get('label', ''), font=_font(True, 17), fill=INK)
        y += 24
        dr.text((PAD, y), f'{src.get("detail","")} · {src.get("date","")}',
                font=_font(False, 15), fill=INK_FAINT)
        y += 40
    dr.text((PAD, S - 200), '투자 조언 아님 · 본 리포트는 공개 데이터 기반 자동 생성',
            font=_font(False, 15), fill=INK_FAINT)
    dr.text((PAD, S - 170), 'buza_alarm_bot', font=_font(True, 18), fill=ACCENT)
    return im


def _fmt_money(v):
    if v is None:
        return '—'
    a = abs(v or 0)
    if a >= 1e9:
        return f'${a/1e9:.2f}B'
    if a >= 1e6:
        return f'${a/1e6:.1f}M'
    return f'${a:,.0f}'


def render_report(d: dict, out_dir: str) -> list:
    """8슬라이드 PNG 렌더. out_dir/slide_1.png ~ slide_8.png 경로 리스트 반환."""
    slides = [
        slide_cover(d),
        slide_profile(d, 2, 8),
        slide_vectors(d, 3, 8),
        slide_financials(d, 4, 8),
        slide_valuation(d, 5, 8),
        slide_transcript(d, 6, 8),
        slide_thesis(d, 7, 8),
        slide_sources(d, 8, 8),
    ]
    paths = []
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    for i, im in enumerate(slides, 1):
        path = str(p / f'slide_{i}.png')
        im.save(path)
        paths.append(path)
    return paths
