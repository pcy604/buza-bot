# -*- coding: utf-8 -*-
"""12p 딥리포트를 PowerPoint(.pptx)로 내보낸다 — 사용자가 PowerPoint에서 직접
간단한 서식(글자·색·박스 위치)을 고칠 수 있는 편집 가능한 사본이 목적.

설계: deck_pages.py의 페이지 함수(p00_cover~p11_cashflow)는 전부 `dr`(draw 프록시)
에만 그리고, 텍스트 배치 로직도 전혀 안 바뀐다 — deck16.new_canvas()가 반환하는
프록시를 PNG용(SDraw)에서 PPTX용(PPTXDraw)으로 바꿔치기하면 페이지 함수 코드를
한 줄도 안 건드리고 그대로 재사용할 수 있다(모듈 전역 함수는 항상 호출 시점에
자기 모듈 네임스페이스에서 이름을 찾으므로, deck_pages 모듈의 new_canvas/paste_scaled
속성만 바꿔치면 _page()·p00_cover() 내부 호출도 자동으로 새 버전을 쓴다).

다만 캔들스틱(수십 개 캔들+거래량+매물대)·듀얼축 막대+라인·도넛·히트맵·MDD 영역차트처럼
프리미티브 호출 수백 개로 이뤄진 "차트"는 pptx 네이티브 도형으로 낱개 변환하면
(a) 파일이 무거워지고 (b) 어차피 사용자가 캔들 하나하나를 손으로 고치진 않는다 —
이런 함수는 원본 그대로 실제 PIL 캔버스에 렌더한 뒤 이미지 한 장으로 슬라이드에
심는다("래스터 아일랜드"). 반대로 KPI 타일·표·타임라인·노트박스·헤더처럼 텍스트/박스
개수가 적고 실제로 고칠 만한 요소는 전부 네이티브 pptx 텍스트박스·도형이 된다.
"""
import io
import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR

import deck16 as D16
import charts2 as C2

PX = 9525  # EMU per px @96dpi


def _px(v):
    return Emu(int(round(v * PX)))


def _rgb(c):
    if not c:
        return None
    return RGBColor(int(c[0]), int(c[1]), int(c[2]))


# ── 네이티브 draw 프록시 — SDraw와 같은 메서드명, pptx 도형/텍스트박스를 만든다 ──
class PPTXDraw:
    def __init__(self, slide):
        self.slide = slide

    def text(self, xy, txt, font=None, fill=None, **kw):
        txt = str(txt)
        if not txt:
            return
        x, y = xy
        size = getattr(font, 'size', 14)
        bold = getattr(font, 'bold', False)
        try:
            w_guess = font.getlength(txt) + 10
        except Exception:
            w_guess = size * len(txt) * 0.6 + 10
        tb = self.slide.shapes.add_textbox(_px(x - 2), _px(y - 3), _px(max(w_guess, 20)), _px(size * 1.7))
        tf = tb.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.TOP
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = txt
        r.font.size = Pt(max(size * 0.75, 6))
        r.font.bold = bool(bold)
        r.font.name = '맑은 고딕'
        rgb = _rgb(fill)
        if rgb:
            r.font.color.rgb = rgb
        return tb

    def _style(self, sp, fill, outline, width):
        rgb = _rgb(fill)
        if rgb:
            sp.fill.solid()
            sp.fill.fore_color.rgb = rgb
        else:
            sp.fill.background()
        orgb = _rgb(outline)
        if orgb:
            sp.line.color.rgb = orgb
            sp.line.width = _px(max(width, 1))
        else:
            sp.line.fill.background()
        sp.shadow.inherit = False

    def rectangle(self, xy, fill=None, outline=None, width=1, **kw):
        x0, y0, x1, y1 = xy
        sp = self.slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, _px(x0), _px(y0),
                                          _px(max(x1 - x0, 1)), _px(max(y1 - y0, 1)))
        self._style(sp, fill, outline, width)
        return sp

    def rounded_rectangle(self, xy, radius=8, fill=None, outline=None, width=1, **kw):
        x0, y0, x1, y1 = xy
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        sp = self.slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, _px(x0), _px(y0), _px(w), _px(h))
        try:
            sp.adjustments[0] = max(0.0, min(0.5, radius / min(w, h)))
        except Exception:
            pass
        self._style(sp, fill, outline, width)
        return sp

    def ellipse(self, xy, fill=None, outline=None, width=1, **kw):
        x0, y0, x1, y1 = xy
        sp = self.slide.shapes.add_shape(MSO_SHAPE.OVAL, _px(x0), _px(y0),
                                          _px(max(x1 - x0, 1)), _px(max(y1 - y0, 1)))
        self._style(sp, fill, outline, width)
        return sp

    def line(self, xy, fill=None, width=1, **kw):
        pts = list(xy)
        if len(pts) < 2:
            return
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        conn = self.slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, _px(x0), _px(y0), _px(x1), _px(y1))
        rgb = _rgb(fill) or RGBColor(0, 0, 0)
        conn.line.color.rgb = rgb
        conn.line.width = _px(max(width, 1))
        return conn

    def __getattr__(self, name):
        raise NotImplementedError(
            f'PPTXDraw.{name}() 미지원 — 이건 차트 프리미티브 전용 호출이라 래스터 '
            f'아일랜드로 우회했어야 함(pptx_export.py의 patch 목록에 빠진 함수가 있는지 확인)')


class _PPTXCanvas:
    __slots__ = ('slide',)

    def __init__(self, slide):
        self.slide = slide


_current_prs = None


def pptx_new_canvas(w=None, h=None, bg=None):
    """deck_pages._page()/p00_cover()가 부르는 new_canvas() 자리를 대체 — 매 호출마다
    새 슬라이드 하나를 만든다(원본은 1080x1080 캔버스 하나 = 페이지 하나와 대응)."""
    slide = _current_prs.slides.add_slide(_current_prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(bg or D16.BG)
    return _PPTXCanvas(slide), PPTXDraw(slide)


def pptx_paste_scaled(im, img, xy, box=None, pad_ratio=0.0):
    img = img.convert('RGBA')
    if pad_ratio:
        pw, ph = int(img.width * pad_ratio), int(img.height * pad_ratio)
        canv = Image.new('RGBA', (img.width + pw * 2, img.height + ph * 2), (0, 0, 0, 0))
        canv.paste(img, (pw, ph), img)
        img = canv
    if box:
        sc = min(box[0] / img.width, box[1] / img.height)
        nw, nh = max(1, int(img.width * sc)), max(1, int(img.height * sc))
    else:
        nw, nh = img.width, img.height
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    im.slide.shapes.add_picture(buf, _px(xy[0]), _px(xy[1]), _px(nw), _px(nh))
    return nw, nh


def pptx_photo_circle(canvas, dr, x, y, d, path, fallback_text='', fg=None):
    fg = fg or D16.ACCENT
    if path and Path(path).exists():
        try:
            ph = Image.open(path).convert('RGB')
            sq = min(ph.size)
            left = (ph.width - sq) // 2
            dpx = 240
            ph = ph.crop((left, 0, left + sq, sq)).resize((dpx, dpx), Image.LANCZOS)
            mask = Image.new('L', (dpx, dpx), 0)
            from PIL import ImageDraw as _D
            _D.Draw(mask).ellipse([0, 0, dpx - 1, dpx - 1], fill=255)
            out = Image.new('RGBA', (dpx, dpx), (0, 0, 0, 0))
            out.paste(ph, (0, 0), mask)
            buf = io.BytesIO()
            out.save(buf, format='PNG')
            buf.seek(0)
            canvas.slide.shapes.add_picture(buf, _px(x), _px(y), _px(d), _px(d))
            dr.ellipse([x, y, x + d, y + d], outline=D16.LINE, width=2)
            return True
        except Exception as e:
            print(f'[사진 렌더 실패] {path}: {type(e).__name__}: {e}')
    dr.ellipse([x, y, x + d, y + d], fill=fg)
    f = D16._font(True, int(d * 0.36))
    dr.text((x + d / 2 - f.getlength(fallback_text) / 2, y + d / 2 - d * 0.25),
            fallback_text, font=f, fill=(255, 255, 255))
    return False


# ── 래스터 아일랜드 — 원본 차트 함수를 실제 PIL 캔버스에 그대로 그려 이미지로 심는다 ──
_price_stack0 = C2.price_stack
_dual_axis0 = C2.dual_axis
_heatmap0 = C2.heatmap
_drawdown0 = C2.drawdown_chart
_donut0 = D16._donut
_hbar0 = D16._hbar
_waterfall0 = D16._waterfall


def _crop_finish(im, w, used_h):
    ss = D16.SS
    full_h = im.height / ss
    im2 = im.resize((max(1, int(w)), max(1, int(full_h))), Image.LANCZOS)
    return im2.crop((0, 0, int(w), max(1, int(min(used_h, full_h)))))


def _embed(slide, pil_img, x, y, w, h):
    buf = io.BytesIO()
    pil_img.convert('RGB').save(buf, format='PNG')
    buf.seek(0)
    slide.shapes.add_picture(buf, _px(x), _px(y), _px(max(w, 1)), _px(max(h, 1)))


def raster_price_stack(dr, x, y, w, rows, rsi=None, macd=None, signal=None, hist=None,
                       candle_h=168, vol_h=44, rsi_h=64, macd_h=70, annotations=None, log_scale=None):
    margin_r = 70
    guess_h = candle_h + vol_h + (rsi_h + 18 if rsi else 0) + (macd_h + 14 if macd else 0) + 80
    im2, dr2 = D16.new_canvas(w=w + margin_r, h=guess_h)
    end_y, legend = _price_stack0(dr2, 0, 0, w, rows, rsi=rsi, macd=macd, signal=signal, hist=hist,
                                  candle_h=candle_h, vol_h=vol_h, rsi_h=rsi_h, macd_h=macd_h,
                                  annotations=annotations, log_scale=log_scale)
    crop = _crop_finish(im2, w + margin_r, end_y)
    _embed(dr.slide, crop, x, y, w + margin_r, end_y)
    return y + end_y, legend


def raster_dual_axis(dr, x, y, w, h, labels, bars, line, bar_fmt, line_fmt, est_from=None,
                     bar_name='', line_name='', bar_color=None, line2=None, line2_fmt=None,
                     line2_name='', line2_color=None, line2_own_scale=False):
    margin = 20
    guess_h = h + 60
    im2, dr2 = D16.new_canvas(w=w + margin, h=guess_h)
    end_y = _dual_axis0(dr2, 0, 0, w, h, labels, bars, line, bar_fmt, line_fmt, est_from=est_from,
                        bar_name=bar_name, line_name=line_name, bar_color=bar_color, line2=line2,
                        line2_fmt=line2_fmt, line2_name=line2_name, line2_color=line2_color,
                        line2_own_scale=line2_own_scale)
    crop = _crop_finish(im2, w + margin, end_y)
    _embed(dr.slide, crop, x, y, w + margin, end_y)
    return y + end_y


def raster_heatmap(dr, x, y, w, data, row_h=34, head_h=30):
    years = data.get('years') or []
    margin = 15
    guess_h = head_h + row_h * (len(years) + 2) + 10
    im2, dr2 = D16.new_canvas(w=w + margin, h=guess_h)
    end_y = _heatmap0(dr2, 0, 0, w, data, row_h=row_h, head_h=head_h)
    crop = _crop_finish(im2, w + margin, end_y)
    _embed(dr.slide, crop, x, y, w + margin, end_y)
    return y + end_y


def raster_drawdown(dr, x, y, w, h, dd, ref_line=None):
    left_m, right_m = 50, 20
    guess_h = h + 45
    im2, dr2 = D16.new_canvas(w=w + left_m + right_m, h=guess_h)
    end_y = _drawdown0(dr2, left_m, 0, w, h, dd, ref_line=ref_line)
    crop = _crop_finish(im2, w + left_m + right_m, end_y)
    _embed(dr.slide, crop, x - left_m, y, w + left_m + right_m, end_y)
    return y + end_y


def raster_donut(dr, cx, cy, r, segs, inner=0.58, total_override=None):
    pad = 24
    size = 2 * r + pad * 2
    im2, dr2 = D16.new_canvas(w=size, h=size)
    _donut0(dr2, r + pad, r + pad, r, segs, inner=inner, total_override=total_override)
    crop = _crop_finish(im2, size, size)
    _embed(dr.slide, crop, cx - r - pad, cy - r - pad, size, size)


def raster_hbar(dr, x, y, w, items, fmt=lambda v: f'{v:,.0f}', label_w=200, bar_h=26, gap=14,
                color=None, signed=False):
    if not items:
        return y
    margin_r = 30
    guess_h = len(items) * (bar_h + gap) + 20
    im2, dr2 = D16.new_canvas(w=w + margin_r, h=guess_h)
    end_y = _hbar0(dr2, 0, 0, w, items, fmt=fmt, label_w=label_w, bar_h=bar_h, gap=gap,
                   color=color, signed=signed)
    crop = _crop_finish(im2, w + margin_r, end_y)
    _embed(dr.slide, crop, x, y, w + margin_r, end_y)
    return y + end_y


def raster_waterfall(dr, x, y, w, h, items, unit=1000.0, start=0.0):
    margin = 20
    guess_h = h + 60
    im2, dr2 = D16.new_canvas(w=w + margin, h=guess_h)
    end_y = _waterfall0(dr2, 0, 0, w, h, items, unit=unit, start=start)
    crop = _crop_finish(im2, w + margin, end_y)
    _embed(dr.slide, crop, x, y, w + margin, end_y)
    return y + end_y


def export(ticker, out_path=None):
    """python-pptx로 12페이지를 그대로(같은 데이터·같은 레이아웃 로직) 편집 가능한
    .pptx로 뽑는다. build.py의 build()와 같은 설정 경로를 쓰되, 렌더 백엔드만
    PNG(SDraw)→PPTX(PPTXDraw)로 바꿔치기한다."""
    global _current_prs
    import build as B
    import deck_pages as P
    import live

    ticker = ticker.upper()
    cfg = B.TICKERS.get(ticker) or B._auto_config(ticker)
    if not cfg:
        raise SystemExit(f'{ticker}: TICKERS 미등록 + {ticker.lower()}_data.py도 없음 — '
                         f'먼저 `python autogen.py {ticker}` 실행 필요')
    data_module = importlib.import_module(cfg['data_module'])
    cik = cfg['cik'] if cfg['cik'] is not None else getattr(data_module, 'COMPANY', {}).get('cik')
    if cik is None:
        import ir
        cik, _ = ir.resolve_ticker(ticker)
    kw = P.configure(data_module=data_module, ticker=ticker, name=cfg['name'], exchange=cfg['exchange'],
                     sector=cfg['sector'], cik=cik, peers=cfg['peers'], site=cfg['site'], ceo=cfg['ceo'],
                     wiki_file=cfg.get('wiki_file', ''))
    listing_date = kw.get('listing_date') or getattr(P.D, 'HISTORY', {}).get('listing_date')
    P.L = live.bundle(P.M['ticker'], P.CIK, P.PEERS, kw['site'], kw['ceo'],
                      wiki_file=kw.get('wiki_file', ''), listing_date=listing_date, company=P.M['name'])

    prs = Presentation()
    prs.slide_width = _px(1080)
    prs.slide_height = _px(1080)
    _current_prs = prs

    patches = [
        (P, 'new_canvas', pptx_new_canvas),
        (P, 'paste_scaled', pptx_paste_scaled),
        (P, '_donut', raster_donut),
        (P, '_hbar', raster_hbar),
        (P, '_waterfall', raster_waterfall),
        (C2, 'price_stack', raster_price_stack),
        (C2, 'dual_axis', raster_dual_axis),
        (C2, 'heatmap', raster_heatmap),
        (C2, 'drawdown_chart', raster_drawdown),
        (C2, 'photo_circle', pptx_photo_circle),
    ]
    saved = [(mod, name, getattr(mod, name)) for mod, name, _ in patches]
    for mod, name, fn in patches:
        setattr(mod, name, fn)
    try:
        for i, fn in enumerate(P.PAGES):
            try:
                fn()
            except Exception as e:
                import traceback
                print(f'[페이지 {i} 실패] {type(e).__name__}: {e}')
                traceback.print_exc()
    finally:
        for mod, name, fn in saved:
            setattr(mod, name, fn)

    out_path = out_path or f'out/{ticker.lower()}/{ticker.lower()}_deck.pptx'
    outp = Path(__file__).resolve().parent / out_path
    outp.parent.mkdir(parents=True, exist_ok=True)
    prs.save(outp)
    return str(outp)


if __name__ == '__main__':
    tk = sys.argv[1].upper() if len(sys.argv) > 1 else 'SATL'
    print(export(tk))
