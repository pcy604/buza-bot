# -*- coding: utf-8 -*-
"""📇 종목 스냅샷 카드 (2026-11-13, 통폐합 P2)

원칙: **계산은 대시보드 한 곳에서.** 봇은 stock-dashboard 가 매일 만드는 results/snap/{코드}.json(종목 분석 탭이 그대로
저장한 7블록 판정)을 읽어 그리기만 한다 — 같은 종목이 홈페이지와 봇에서 다른 숫자로 나오던 3중 엔진을 없애기 위함.
시황(market.py)이 market_report.json 을 읽는 방식과 같다.

summary(snap)  → PNG 1장: 결론 → 깨지는 조건 → 펀더멘탈(기업 요약 + 흐름 카드) → 히스토리 → 수급
deck(snap)     → PNG 여러 장: 결론 1장 + 탭마다 1장(깨지는 조건은 근거 줄까지)
2026-11-16 — 홈페이지 종목 분석 3탭(펀더멘탈·히스토리·수급)과 같은 순서·같은 카드. 카드엔 흐름선(실선 실적·점선 컨센서스).
"""
from __future__ import annotations

import os
import re
import tempfile

import requests
from PIL import Image, ImageDraw

import market_card as mc

RAW = 'https://raw.githubusercontent.com/pcy604/stock-dashboard/main/results/snap/{code}.json'
API = 'https://api.github.com/repos/pcy604/stock-dashboard/contents/results/snap/{code}.json?ref=main'
DASH = 'https://stock-dashboard-dmfvhcig7brge7utl7et5r.streamlit.app/?sym={code}'
FRESH_DAYS = 4

W, PAD = mc.W, mc.PAD
CW = W - 2 * PAD
GAP = 20
TONE = {'good': (0x15, 0x80, 0x3d), 'bad': (0xb9, 0x1c, 0x1c), 'mid': (0xb4, 0x53, 0x09), 'na': (0x8a, 0x90, 0x99)}
TONE_BG = {'good': (0xec, 0xfd, 0xf3), 'bad': (0xfe, 0xf2, 0xf2), 'mid': (0xff, 0xf7, 0xed), 'na': (0xf6, 0xf7, 0xf9)}
ORDER = ['깨지는 조건·촉매', '이익 방향', '밸류에이션', '가격', '수급']   # 스냅샷 v3 블록 키(정본) — 화면 이름은 TITLE
TITLE = {'깨지는 조건·촉매': '보유 리스크', '이익 방향': '펀더멘탈', '밸류에이션': '밸류에이션', '가격': '히스토리', '수급': '수급·업종'}
_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]')


def _t(s) -> str:
    return _EMOJI.sub('', str(s if s is not None else '-')).strip() or '-'


def fetch(code: str, timeout: int = 15) -> dict | None:
    hdr = {'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'buza-alarm-bot'}
    tok = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if tok:
        hdr['Authorization'] = f'Bearer {tok}'
    for url, h in ((API.format(code=code), hdr), (RAW.format(code=code), {})):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.status_code == 404:
                return None
            if r.ok:
                return r.json()
        except Exception as e:
            print(f'[snap] 가져오기 실패({code}): {e}')
    return None


def age_days(snap: dict) -> int:
    from datetime import date
    try:
        return (date.today() - date.fromisoformat(str(snap.get('asof'))[:10])).days
    except Exception:
        return 9999


def is_fresh(snap: dict | None) -> bool:
    return bool(snap) and age_days(snap) <= FRESH_DAYS


# ── 그리기 조각 ───────────────────────────────────────────────────────────
def _card(dr, x, y, w, c, big: bool, fixed_h: int | None = None) -> int:
    """카드 하나. 돌려주는 값 = 높이. 왼쪽 톤 막대 + 라벨 / 값 / 설명."""
    tone = c.get('tone') or 'na'
    fl, fv, fs = mc.F(False, 20 if not big else 24), mc.F(True, 30 if not big else 40), mc.F(False, 20 if not big else 24)
    inner = w - 44
    label = mc._wrap(dr, _t(c.get('label')), fl, inner, 2)
    value = mc._wrap(dr, _t(c.get('value')), fv, inner, 2)
    sub = mc._wrap(dr, _t(c.get('sub')), fs, inner, 3)
    lh_l, lh_v, lh_s = fl.size + 6, fv.size + 8, fs.size + 6
    sp_h = (56 if not big else 72) if (c.get('spark') or {}).get('y') else 0
    h = 16 + lh_l + 4 + lh_v * len(value) + 4 + sp_h + lh_s * len(sub) + 16
    if fixed_h:
        h = max(h, fixed_h)
    dr.rounded_rectangle([x, y, x + w, y + h], 14, fill=TONE_BG[tone], outline=mc.LINE)
    dr.rounded_rectangle([x, y + 10, x + 6, y + h - 10], 3, fill=TONE[tone])
    cy = y + 16
    for ln in label:
        dr.text((x + 24, cy), ln, font=fl, fill=mc.DIM)
        cy += lh_l
    cy += 4
    for ln in value:
        dr.text((x + 24, cy), ln, font=fv, fill=TONE[tone] if tone != 'na' else mc.INK)
        cy += lh_v
    cy += 4
    if sp_h:
        _spark(dr, x + 24, cy, inner, sp_h - 10, c['spark'], TONE[tone] if tone != 'na' else mc.DIM)
        cy += sp_h
    for ln in sub:
        dr.text((x + 24, cy), ln, font=fs, fill=mc.DIM)
        cy += lh_s
    return h


def _spark(dr, x, y, w, h, sp, col):
    """흐름선 — 실선 = 실적·가격, 점선 = 컨센서스(fwd), 회색 점선 = 기준(ref). 홈페이지 flow_cards.spark_svg 와 같은 규칙."""
    ys = [v for v in (sp.get('y') or []) if v is not None]
    fw = [v for v in (sp.get('fwd') or []) if v is not None]
    if len(ys) < 2:
        return
    allv = ys + fw + ([sp['ref']] if sp.get('ref') is not None else [])
    lo, hi = min(allv), max(allv)
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    n = len(ys) + len(fw)
    X = lambda i: x + w * i / max(1, n - 1)
    Y = lambda v: y + h * (1 - (v - lo) / (hi - lo))

    def dashed(p0, p1, fill, width, seg=8):
        (x0, y0), (x1, y1) = p0, p1
        L = max(1.0, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** .5)
        k = 0.0
        while k < L:
            a, b = k / L, min(k + seg, L) / L
            dr.line([(x0 + (x1 - x0) * a, y0 + (y1 - y0) * a), (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b)], fill=fill, width=width)
            k += seg * 2
    if sp.get('ref') is not None:
        dashed((x, Y(sp['ref'])), (x + w, Y(sp['ref'])), mc.LINE, 2, 6)
    if sp.get('kind') == 'bar':
        bw = max(2, int(w / n * 0.7))
        base = Y(max(lo, 0))
        for i, v in enumerate(ys):
            dr.rectangle([X(i) - bw / 2, min(Y(v), base), X(i) + bw / 2, max(Y(v), base)],
                         fill=col if i >= len(ys) - 5 else mc.LINE)
        return
    dr.line([(X(i), Y(v)) for i, v in enumerate(ys)], fill=col, width=3, joint='curve')
    pts = [(X(len(ys) - 1 + k), Y(v)) for k, v in enumerate([ys[-1]] + fw)]
    for a, b in zip(pts, pts[1:]):
        dashed(a, b, col, 3)
    cx, cy = X(len(ys) - 1), Y(ys[-1])
    dr.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=col)


def _company(dr, y, co) -> int:
    """기업 요약 카드(홈페이지 flow_cards.company_html 과 같은 내용) — 한 줄 정의 · 핵심 수치 · 수익 구조/경쟁 우위/핵심 리스크."""
    if not co:
        return y
    f1, f2, fs, fv = mc.F(True, 28), mc.F(False, 24), mc.F(False, 20), mc.F(True, 28)
    y0 = y
    y += 18
    dr.text((PAD + 24, y), mc._fit(dr, _t(co.get('name')), f1, CW - 300), font=f1, fill=mc.INK)
    if co.get('type'):
        tw = int(dr.textlength(_t(co['type']), font=fs)) + 28
        dr.rounded_rectangle([W - PAD - 24 - tw, y, W - PAD - 24, y + 34], 10, fill=(0xfe, 0xf3, 0xc7))
        dr.text((W - PAD - 24 - tw + 14, y + 6), _t(co['type']), font=fs, fill=(0x92, 0x40, 0x0e))
    y += 40
    for ln in mc._wrap(dr, _t(co.get('definition')), f2, CW - 48, 3):
        dr.text((PAD + 24, y), ln, font=f2, fill=mc.INK)
        y += 32
    kp = co.get('kpis') or []
    if kp:
        y += 10
        n = len(kp)
        kw = (CW - 48 - 12 * (n - 1)) // n
        for i, k in enumerate(kp):
            kx = PAD + 24 + i * (kw + 12)
            dr.rounded_rectangle([kx, y, kx + kw, y + 92], 10, fill=TONE_BG['na'])
            dr.text((kx + 12, y + 8), mc._fit(dr, _t(k.get('label')), fs, kw - 24), font=fs, fill=mc.DIM)
            dr.text((kx + 12, y + 34), mc._fit(dr, _t(k.get('value')), fv, kw - 24), font=fv,
                    fill=TONE.get(k.get('tone') or 'na') if k.get('tone') not in (None, 'na') else mc.INK)
            if k.get('sub'):
                dr.text((kx + 12, y + 66), mc._fit(dr, _t(k['sub']), fs, kw - 24), font=fs, fill=mc.DIM)
        y += 104
    tx = [(lb, co.get(k)) for k, lb in (('revenue', '수익 구조'), ('moat', '경쟁 우위'), ('risk', '핵심 리스크')) if co.get(k)]
    for lb, t in tx:
        dr.text((PAD + 24, y), lb, font=mc.F(True, 20), fill=mc.DIM)
        for ln in mc._wrap(dr, _t(t), f2, CW - 200, 2):
            dr.text((PAD + 180, y - 2), ln, font=f2, fill=mc.INK)
            y += 32
        y += 4
    y += 12
    # 테두리는 내용 높이를 안 뒤에 그리면 글을 덮으므로 선만 긋는다
    dr.rounded_rectangle([PAD, y0, W - PAD, y], 14, outline=mc.LINE, width=2)
    return y


def _row(dr, y, cards, big=False) -> int:
    """카드 n장을 한 줄에. 높이는 가장 큰 카드에 맞춰 다시 그린다(같은 줄 같은 높이)."""
    cards = [c for c in cards if c] or [{'label': '-', 'value': '-', 'sub': ''}]
    if len(cards) > 3:            # 2026-11-16 — 결론 5장(4축 + 판단 철회) 등은 3장씩 줄을 나눈다(사이트와 같은 카드 수)
        per = 2 if len(cards) == 4 else 3
        tot = 0
        for k in range(0, len(cards), per):
            tot += _row(dr, y + tot, cards[k:k + per], big) + GAP
        return tot - GAP
    n = len(cards)
    w = (CW - GAP * (n - 1)) // n
    probe = Image.new('RGB', (W, 10))
    hs = [_card(ImageDraw.Draw(probe), 0, 0, w, c, big) for c in cards]
    h = max(hs)
    for i, c in enumerate(cards):
        _card(dr, PAD + i * (w + GAP), y, w, c, big, fixed_h=h)
    return h


def _header(dr, y, snap) -> int:
    name = _t(snap.get('name') or snap.get('sym'))
    dr.text((PAD, y), mc._fit(dr, name, mc.F(True, 44), CW), font=mc.F(True, 44), fill=mc.INK)
    y += 58
    meta = f"{snap.get('sym')} · {'한국' if snap.get('market') == 'KR' else '미국'} · 기준 {mc._day(snap.get('asof'))} · STOCK DASHBOARD 종목 분석과 같은 계산"
    dr.text((PAD, y), mc._fit(dr, meta, mc.F(False, 24), CW), font=mc.F(False, 24), fill=mc.FAINT)
    return y + 44


def _verdict(dr, y, snap, big=False) -> int:
    v = snap.get('verdict') or {}
    f = mc.F(True, 34)
    head = mc._wrap(dr, '결론 — ' + _t(v.get('head')), f, CW - 260, 2)
    for ln in head:
        dr.text((PAD, y), ln, font=f, fill=mc.INK)
        y += 42
    chip = f"유형 {_t(v.get('type_chip') or (snap.get('type') or {}).get('label'))}"
    fc = mc.F(True, 22)
    cw = int(dr.textlength(chip, font=fc)) + 32
    cy = y - 42 * len(head)
    dr.rounded_rectangle([W - PAD - cw, cy + 4, W - PAD, cy + 40], 18, fill=mc.TRACK)
    dr.text((W - PAD - cw + 16, cy + 10), chip, font=fc, fill=mc.DIM)
    y += 10
    y += _row(dr, y, v.get('cards') or [], big) + 12
    hl = v.get('halt')              # 2026-11-16 — 사이트와 같이: 매도 점검은 4축 아래 한 줄 주석
    if hl:
        fh = mc.F(False, 22)
        for ln in mc._wrap(dr, f"🛑 매도 점검 {_t(hl.get('value'))} — {_t(hl.get('sub'))}", fh, CW, 2):
            dr.text((PAD, y), ln, font=fh, fill=mc.DIM)
            y += 30
        y += 8
    return y


def _section_title(dr, y, name) -> int:
    dr.text((PAD, y), name, font=mc.F(True, 30), fill=mc.INK)
    dr.line([PAD, y + 44, W - PAD, y + 44], fill=mc.LINE, width=2)
    return y + 56


def _footer(dr, y) -> int:
    f = mc.F(False, 20)
    lines = mc._wrap(dr, '규칙 계산이며 투자 권유가 아니다 · 자세한 표·차트는 홈페이지 종목 분석 · 부자알람 @buza_alarm_bot', f, CW, 2)
    for ln in lines:
        dr.text((PAD, y), ln, font=f, fill=mc.FAINT)
        y += 28
    return y + PAD // 2


def _canvas(h: int):
    im = Image.new('RGB', (W, h), mc.BG)
    return im, ImageDraw.Draw(im)


def _save(im, tag) -> str:
    p = os.path.join(tempfile.gettempdir(), f'snap_{tag}.png')
    im.save(p, optimize=True)
    return p


def _draw_twice(fn) -> Image.Image:
    """높이를 모르니 큰 캔버스에 한 번 그려 끝 y 를 재고, 그 높이로 다시 그린다."""
    im, dr = _canvas(6000)
    end = fn(dr)
    im2, dr2 = _canvas(min(max(end, 400), 9000))
    fn(dr2)
    return im2


# ── 공개 API ──────────────────────────────────────────────────────────────
def summary(snap: dict) -> str:
    blocks = snap.get('blocks') or {}

    def draw(dr):
        y = PAD
        y = _header(dr, y, snap)
        y = _verdict(dr, y + 8, snap)
        for name in ORDER:
            b = blocks.get(name) or {}
            if not b.get('cards') and not b.get('error'):
                continue
            y = _section_title(dr, y + 10, TITLE.get(name, name))
            if name == '이익 방향' and snap.get('company'):
                y = _company(dr, y, snap['company']) + 14
            if b.get('error'):
                dr.text((PAD, y), mc._fit(dr, f"판정 실패: {b['error']}", mc.F(False, 22), CW), font=mc.F(False, 22), fill=mc.FAINT)
                y += 40
            else:
                y += _row(dr, y, b['cards']) + 6
        return _footer(dr, y + 16)

    return _save(_draw_twice(draw), f"{snap.get('sym')}_sum")


def deck(snap: dict) -> list[str]:
    """결론 1장 + 블록마다 1장. 깨지는 조건은 근거 줄(지금 거리)까지 적는다."""
    out = []
    blocks = snap.get('blocks') or {}

    def first(dr):
        y = _header(dr, PAD, snap)
        y = _verdict(dr, y + 8, snap, big=True)
        t = snap.get('type') or {}
        f = mc.F(False, 24)
        for ln in mc._wrap(dr, f"유형 {_t(t.get('label'))} — {_t(t.get('sub'))}", f, CW, 3):
            dr.text((PAD, y), ln, font=f, fill=mc.DIM)
            y += 32
        return _footer(dr, y + 20)

    out.append(_save(_draw_twice(first), f"{snap.get('sym')}_0"))
    for i, name in enumerate(ORDER, 1):
        b = blocks.get(name) or {}
        if not b.get('cards'):
            continue

        def page(dr, name=name, b=b):
            y = _header(dr, PAD, snap)
            y = _section_title(dr, y + 8, TITLE.get(name, name))
            if name == '이익 방향' and snap.get('company'):
                y = _company(dr, y, snap['company']) + 14
            y += _row(dr, y, b['cards'], big=True) + 16
            det = b.get('detail') or []
            if det:
                f = mc.F(False, 24)
                dr.text((PAD, y), '근거 — 지금 거리', font=mc.F(True, 26), fill=mc.INK)
                y += 40
                for r in det[:12]:
                    mark = '!' if r.get('state') == 'warn' else '·'
                    for ln in mc._wrap(dr, f"{mark} {_t(r.get('name'))} — {_t(r.get('detail'))}", f, CW, 2):
                        dr.text((PAD, y), ln, font=f, fill=TONE['bad'] if r.get('state') == 'warn' else mc.DIM)
                        y += 32
            return _footer(dr, y + 20)

        out.append(_save(_draw_twice(page), f"{snap.get('sym')}_{i}"))
    return out


def caption(snap: dict) -> str:
    v = snap.get('verdict') or {}
    bc = ((snap.get('blocks') or {}).get('깨지는 조건·촉매') or {}).get('cards') or []
    brk = next((c for c in bc if '깨지는' in str(c.get('label'))), None)
    parts = [f"<b>{snap.get('name') or snap.get('sym')}</b> ({snap.get('sym')}) · {snap.get('asof')} 기준",
             f"🧭 {v.get('head', '-')} · 🪪 {v.get('type_chip', '-')}"]
    if brk:
        parts.append(f"⚡ 깨지는 조건 {brk.get('value')}" + (f" — {brk.get('sub')}" if brk.get('tone') != 'good' else ''))
    parts.append(f'🔎 <a href="{DASH.format(code=snap.get("sym"))}">홈페이지에서 전체 보기</a>')
    return '\n'.join(parts)
