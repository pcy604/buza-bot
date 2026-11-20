# -*- coding: utf-8 -*-
"""대가 관점 페이지 3장 — 오닐 CANSLIM 원전 7관문 · 차트 읽기(오닐×리버모어) · 피터 린치 2분 점검.

2026-10-20 신설(11번 문서 '대가 관점 자가진단'의 1·2·4번). 숫자는 전부 결정론(oneil.py ·
lynch.py)이고, LLM 서술은 데이터 모듈에 LYNCH 가 있을 때만 쓴다(없으면 체크포인트로 대신).
모든 페이지는 **사실과 규칙 판정까지만** 한다 — 매수·매도 의견·목표가는 넣지 않는다.

페이지 함수는 deck_pages 모듈(P)을 받아 그 전역(D·M·L·_page 등)을 쓴다.
"""
import oneil as O
import lynch as LY
from deck16 import (S, PAD, CW, SURFACE, LINE, INK, INK_DIM, INK_FAINT, ACCENT, POS, NEG,
                    _font, _wrap_draw, _wrap, _footer, _note, _kpi_tiles, _table)

OK_C = (0x1f, 0x7a, 0x4d)
NO_C = (0xb4, 0x3c, 0x3c)
NA_C = (0x9a, 0x9a, 0x9a)


def _prep(P):
    """L 에 차트·시장 판정을 한 번만 계산해 붙인다."""
    L = P.L or {}
    if '_chart' not in L:
        # 한국 종목은 시장·상대강도 기준을 코스피로(bundle 이 spy_daily 자리에 ^KS11 을 넣는다)
        ix = 'KOSPI' if _is_kr(P) else 'S&P500'
        L['_index_name'] = ix
        L['_chart'] = O.chart_read(L.get('daily') or [], L.get('spy_daily') or [], fmt=P._px, index_name=ix)
        L['_market'] = O.market_direction(L.get('spy_daily') or [], name=ix)
    return L


def _is_kr(P):
    return str(P.M.get('ticker', '')).upper().endswith(('.KS', '.KQ'))


def _fin_src(P):
    return 'DART 재무제표' if _is_kr(P) else 'SEC XBRL'


def _mark(v):
    return ('충족', OK_C) if v is True else ('미충족', NO_C) if v is False else ('판단 불가', NA_C)


# ── 1. 오닐 CANSLIM 원전 7관문 ─────────────────────────────────────────
def oneil_page(P, idx):
    L = _prep(P)
    rows = O.canslim_oneil(L)
    passed = sum(1 for r in rows if r[2] is True)
    known = sum(1 for r in rows if r[2] is not None)
    im, dr = P._page(idx, 'CANSLIM 원전 · 윌리엄 오닐', '7개 관문 통과 여부 — 앞 장 체슬리 C·A·N 점수와 다른 잣대')
    # 배지
    lbl, tt = '통과', f'{passed}/7'
    lf, tf = _font(True, 13), _font(True, 22)
    bw = 18 + lf.getlength(lbl) + 10 + tf.getlength(tt) + 16
    bx0, by0 = S - PAD - bw, 68
    dr.rectangle([bx0, by0, bx0 + bw, by0 + 34], fill=(0xfb, 0xf6, 0xec))
    dr.rectangle([bx0, by0, bx0 + 3, by0 + 34], fill=ACCENT)
    dr.text((bx0 + 14, by0 + 10), lbl, font=lf, fill=INK_DIM)
    dr.text((bx0 + 18 + lf.getlength(lbl), by0 + 5), tt, font=tf, fill=ACCENT)

    y = P.TOP2
    rh = 78
    for code, name, ok, val, rule in rows:
        word, col = _mark(ok)
        dr.rounded_rectangle([PAD, y, PAD + CW, y + rh - 8], radius=10, outline=LINE, width=1)
        dr.rounded_rectangle([PAD, y, PAD + 58, y + rh - 8], radius=10, fill=col)
        dr.rectangle([PAD + 46, y, PAD + 58, y + rh - 8], fill=col)
        dr.text((PAD + 17, y + 17), code, font=_font(True, 28), fill=(255, 255, 255))
        dr.text((PAD + 74, y + 9), name, font=_font(True, 17), fill=INK)
        dr.text((PAD + 74, y + 37), val[:70], font=_font(False, 15), fill=INK_DIM)
        rf = _font(False, 13)
        dr.text((S - PAD - 16 - rf.getlength(rule), y + 13), rule, font=rf, fill=INK_FAINT)
        wf = _font(True, 16)
        dr.text((S - PAD - 16 - wf.getlength(word), y + 38), word, font=wf, fill=col)
        y += rh
    note = ('오닐은 점수를 더하지 않는다. 7개 관문을 모두 통과한 종목이 베이스를 거래량과 함께 돌파할 때 산다. '
            '앞 장의 체슬리 방식은 C·A 를 영업이익으로, N 을 산업 지위·신시장으로 재정의한 점수제라 두 결과가 다를 수 있다. '
            f'판정 가능 {known}개 중 {passed}개 충족. L 은 전 종목 RS 백분위 대신 S&P500 대비 가중수익률(대리), '
            'A 는 연간 EPS 대신 순이익(대리).')
    _note(dr, y + 6, note)
    _footer(dr, f'EPS·주식수={_fin_src(P)} · 주가·거래량=Yahoo Finance 일봉 · '
                + ('기관=Nasdaq 기관보유 공시(13F 집계) · ' if not _is_kr(P) else '기관=외국인·기관 순매수(네이버 증권) · ')
                + '기준=오닐 『How to Make Money in Stocks』')
    return im


# ── 2. 차트 읽기: 오닐 × 리버모어 ──────────────────────────────────────
def chart_page(P, idx):
    L = _prep(P)
    cr = L['_chart']
    if not cr.get('ok'):
        return None
    im, dr = P._page(idx, '차트 읽기 · 오닐 × 리버모어', '주봉 2년 · 10/30/40주선 · 피벗(52주 고점) · 거래량')
    w = cr['weekly'][-104:]
    off = len(cr['weekly']) - len(w)
    x0, y0, cw, ch, vh = PAD + 56, P.TOP2 + 8, CW - 56, 330, 70
    lo = min(b['l'] for b in w)
    hi = max(max(b['h'] for b in w), cr['pivot'])
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad

    def yy(v):
        return y0 + ch - (v - lo) / (hi - lo) * ch
    n = len(w)
    bw = cw / n

    def xx(i):
        return x0 + (i + 0.5) * bw
    # 격자·축
    yf = _font(False, 12)
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        dr.line([(x0, yy(v)), (x0 + cw, yy(v))], fill=LINE, width=1)
        t = P._px(v)
        dr.text((x0 - 8 - yf.getlength(t), yy(v) - 8), t, font=yf, fill=INK_FAINT)
    # 베이스 구간 음영(피벗 이후)
    pi = cr['pivot_i'] - off
    if 0 <= pi < n:
        dr.rectangle([xx(pi) - bw / 2, y0, x0 + cw, y0 + ch], fill=(0xf4, 0xf1, 0xea))
    # 캔들
    for i, b in enumerate(w):
        up = b['c'] >= b['o']
        col = POS if up else NEG
        dr.line([(xx(i), yy(b['h'])), (xx(i), yy(b['l']))], fill=col, width=1)
        top, bot = yy(max(b['o'], b['c'])), yy(min(b['o'], b['c']))
        dr.rectangle([xx(i) - bw * 0.32, top, xx(i) + bw * 0.32, max(bot, top + 1)], fill=col)
    # 이동평균
    for ma, col in ((cr['ma10'], (0xd9, 0x8a, 0x1f)), (cr['ma30'], (0x2f, 0x6f, 0xb3)), (cr['ma40'], (0x6b, 0x4f, 0xa8))):
        seg = ma[-n:]
        pts = [(xx(i), yy(v)) for i, v in enumerate(seg) if v]
        if len(pts) > 1:
            dr.line(pts, fill=col, width=2)
    # 피벗선
    py = yy(cr['pivot'])
    dr.line([(x0, py), (x0 + cw, py)], fill=ACCENT, width=2)
    pt = f'피벗 {P._px(cr["pivot"])}'
    dr.text((x0 + cw - _font(True, 13).getlength(pt) - 4, py - 20), pt, font=_font(True, 13), fill=ACCENT)
    # 거래량
    vy0 = y0 + ch + 12
    vmax = max(b['v'] for b in w) or 1
    for i, b in enumerate(w):
        hh = b['v'] / vmax * vh
        dr.rectangle([xx(i) - bw * 0.32, vy0 + vh - hh, xx(i) + bw * 0.32, vy0 + vh],
                     fill=(0xc9, 0xd3, 0xdf) if b['c'] >= b['o'] else (0xe6, 0xc9, 0xc9))
    # 범례
    ly = vy0 + vh + 10
    lx = x0
    for lab, col in (('10주선', (0xd9, 0x8a, 0x1f)), ('30주선', (0x2f, 0x6f, 0xb3)), ('40주선', (0x6b, 0x4f, 0xa8)),
                     ('베이스 구간', (0xd8, 0xd2, 0xc4))):
        dr.rectangle([lx, ly + 5, lx + 18, ly + 9], fill=col)
        dr.text((lx + 24, ly - 2), lab, font=_font(False, 13), fill=INK_DIM)
        lx += 24 + _font(False, 13).getlength(lab) + 22
    # 두 대가의 읽기
    y = ly + 30
    colw = (CW - 20) / 2
    for j, (title, lines) in enumerate((('윌리엄 오닐 — 베이스·피벗·거래량', cr['oneil']),
                                         ('제시 리버모어 — 최소저항선·피벗 포인트', cr['livermore']))):
        cx = PAD + j * (colw + 20)
        dr.text((cx, y), title, font=_font(True, 17), fill=INK)
        yy2 = y + 30
        for ln in lines:
            yy2 = _wrap_draw(dr, cx, yy2, '· ' + ln, _font(False, 15), INK_DIM, colw, line_h=21) + 6
    m = L.get('_market') or {}
    _footer(dr, f'주가=Yahoo Finance 일봉→주봉 · 시장={m.get("note", "")} · 규칙 기반 판정이며 매매 권유가 아님')
    return im


# ── 3. 피터 린치 2분 점검 ──────────────────────────────────────────────
def _type_facts(P, typ, L, cons):
    """유형별 점검 항목(TYPES[...]['check'] 순서)에 맞춘 실제 값. 모르면 ''."""
    ann = L.get('annual') or {}
    last = lambda k: (lambda d: d[max(d)] if d else None)({y: v for y, v in (ann.get(k) or {}).items() if v is not None})
    cash, cfo, liab = last('cash'), last('cfo'), last('liab')
    m = P._m
    if typ == 'turnaround':
        run = (f'현금 {m(cash)} · 연간 영업현금 {m(cfo)} → 약 {cash / -cfo:.1f}년 버팀'
               if cash and cfo and cfo < 0 else f'현금 {m(cash)} · 영업현금흐름 {m(cfo)} (흑자)' if cash and cfo else '')
        q = [v for _, v in sorted(((L.get('quarterly') or {}).get('opinc') or {}).items())][-4:]
        return [run, f'총부채 {m(liab)}' if liab else '',
                '분기 영업이익 ' + ' → '.join(m(v) for v in q) if q else '']
    if typ == 'fast':
        qr = sorted(((L.get('quarterly') or {}).get('revenue') or {}).items())
        yoy = ''
        if len(qr) >= 5:
            import datetime as _d
            e = _d.date.fromisoformat(qr[-1][0][:10])
            prior = [v for k, v in qr if abs((e - _d.date.fromisoformat(k[:10])).days - 365) <= 20]
            if prior and prior[0]:
                yoy = f'최근 분기 매출 전년 대비 {(qr[-1][1] / prior[0] - 1) * 100:+.0f}%'
        eq = last('equity')
        return ['', yoy, '', f'부채/자본 {liab / eq:.1f}배' if liab and eq and eq > 0 else '']
    if typ == 'asset':
        mc = cons.get('market_cap')
        return [f'순현금 {m((cash or 0) - (liab or 0))} · 시총 {m(mc)}' if mc else '', f'영업현금흐름 {m(cfo)}' if cfo else '', '']
    if typ == 'cyclical':
        op = [v for _, v in sorted((ann.get('opinc') or {}).items()) if v is not None][-5:]
        return ['5년 영업이익 ' + ' → '.join(m(v) for v in op) if op else '', '', f'현금 {m(cash)} · 총부채 {m(liab)}']
    return []


def _fcf_tile(P, ann, mc):
    """현금창출력(윤지호: '가치의 핵심은 현금을 계속 만들어 내는 힘') — 최근 연도 FCF 수익률."""
    cfo, capex, rev = (ann.get('cfo') or {}), (ann.get('capex') or {}), (ann.get('revenue') or {})
    ys = [y for y in cfo if cfo.get(y) is not None]
    if not ys:
        return ('FCF 수익률', '—', '현금흐름 데이터 없음')
    y = max(ys)
    fcf = cfo[y] - abs(capex.get(y) or 0)
    yld = f'{fcf / mc * 100:+.1f}%' if mc else '—'
    mg = f' · 마진 {fcf / rev[y] * 100:+.0f}%' if rev.get(y) else ''
    return ('FCF 수익률', yld, f'FY{y} FCF {P._m(fcf)}{mg}')


def lynch_page(P, idx):
    L = P.L or {}
    D, M = P.D, P.M
    ann = L.get('annual') or {}
    cons = L.get('consensus') or {}
    qop = [v for _, v in sorted(((L.get('quarterly') or {}).get('opinc') or {}).items())]
    cash = (ann.get('cash') or {})
    eq = (ann.get('equity') or {})
    liab = (ann.get('liab') or {})
    ly = max(cash) if cash else None
    mc = cons.get('market_cap')
    # 부채는 총부채로 보수적으로 본다(순현금 과대평가 방지)
    t = LY.classify({'revenue': ann.get('revenue'), 'opinc': ann.get('opinc')}, qop,
                    market_cap=mc, cash=cash.get(ly) if ly else None,
                    debt=liab.get(ly) if ly else None, equity=eq.get(ly) if ly else None,
                    sector=M.get('sector', ''))
    info = LY.TYPES[t['type']]
    # PEG: 컨센서스 다음 해 EPS 성장 → PER(현재가/당해 EPS)
    p0, p1 = (cons.get('periods') or {}).get('0y') or {}, (cons.get('periods') or {}).get('+1y') or {}
    price = cons.get('price')
    pe = price / p0['eps'] if price and p0.get('eps') and p0['eps'] > 0 else None
    g = ((p1['eps'] / p0['eps'] - 1) * 100) if p0.get('eps') and p1.get('eps') and p0['eps'] > 0 else None
    peg_v, peg_tag, peg_note = LY.peg(pe, g)

    im, dr = P._page(idx, '피터 린치 2분 점검', '6가지 주식 유형 · PEG · 이야기가 맞으려면 / 깨지는 신호')
    # 유형 배지
    y = P.TOP2
    dr.rounded_rectangle([PAD, y, PAD + CW, y + 108], radius=12, fill=SURFACE)
    dr.text((PAD + 22, y + 16), '유형', font=_font(False, 15), fill=INK_FAINT)
    dr.text((PAD + 22, y + 38), f'{info["ko"]}', font=_font(True, 34), fill=ACCENT)
    tx = PAD + 30 + _font(True, 34).getlength(info['ko']) + 14
    dr.text((tx, y + 52), info['en'], font=_font(False, 16), fill=INK_FAINT)
    _wrap_draw(dr, PAD + 380, y + 18, info['what'], _font(False, 15), INK_DIM, CW - 400, line_h=21)
    _wrap_draw(dr, PAD + 380, y + 70, '판정 근거: ' + t['why'] + (' · ' + t['flags'][0] if t['flags'] else ''),
               _font(True, 14), INK, CW - 400, line_h=19)
    y += 124
    # 수치 타일
    rc = t.get('rev_cagr')
    tiles = [('PEG', f'{peg_v:.2f}' if peg_v is not None else '—', peg_tag + (f' · {peg_note}' if peg_v else f' · {peg_note}')),
             ('매출 성장(연)', f'{rc:+.0f}%' if rc is not None else '—', '최근 3년 CAGR'),
             ('순현금/시총', f'{(cash.get(ly) - liab.get(ly)) / mc * 100:+.0f}%' if ly and mc and liab.get(ly) is not None else '—',
              '현금 − 총부채 (보수적)'),
             _fcf_tile(P, ann, mc)]
    tw = (CW - 36) / 4
    for i, (k, v, s) in enumerate(tiles):
        cx = PAD + i * (tw + 12)
        dr.rounded_rectangle([cx, y, cx + tw, y + 92], radius=10, outline=LINE, width=1)
        dr.text((cx + 16, y + 10), k, font=_font(False, 14), fill=INK_FAINT)
        dr.text((cx + 16, y + 30), v, font=_font(True, 26), fill=INK)
        _wrap_draw(dr, cx + 16, y + 64, s, _font(False, 12), INK_FAINT, tw - 28, line_h=15)
    y += 108
    lyd = getattr(D, 'LYNCH', None) or {}
    # 2분 이야기 — LLM 서술(LYNCH.story)이 있으면 그것, 없으면 표지의 '무엇을 팔고 누가 사나'
    biz = getattr(D, 'BUSINESS', None) or []
    story = lyd.get('story') or (' · '.join(str(r if isinstance(r, str) else (r[1] if len(r) > 1 else r[0]))
                                            for r in biz[:3]) if biz else '')
    if story:
        dr.text((PAD, y), '2분 이야기', font=_font(True, 18), fill=INK)
        y = _wrap_draw(dr, PAD, y + 30, story, _font(False, 15), INK_DIM, CW, line_h=22) + 14
    # 유형별로 볼 것 — 점검 항목마다 우리 데이터의 실제 값을 붙인다
    dr.text((PAD, y), f'{info["ko"]}에서 린치가 보는 것', font=_font(True, 18), fill=INK)
    y += 30
    facts = _type_facts(P, t['type'], L, cons)
    for i, c in enumerate(info['check'][:4]):
        line = '· ' + c + (f'  →  {facts[i]}' if i < len(facts) and facts[i] else '')
        y = _wrap_draw(dr, PAD, y, line, _font(False, 15), INK_DIM, CW, line_h=21) + 3
    y += 10
    # 맞으려면 / 깨지는 신호 — LLM 서술이 없으면 경영진 로드맵(체크포인트 high)에서 대신 만든다
    hi = [c for c in getattr(D, 'CHECKPOINTS', []) if len(c) > 3 and c[3] == 'high']
    must = lyd.get('must_happen') or [f'{c[1]} ({c[0]})' for c in hi][:3]
    breaks = lyd.get('breaks_if') or [f'{c[1]} — 실패하거나 {c[0]}을 넘겨 지연' for c in hi][:3]
    colw = (CW - 20) / 2
    top = y
    hmax = 0
    for j, (title, items, col) in enumerate((('이야기가 맞으려면', must, OK_C), ('이야기가 깨지는 신호', breaks, NO_C))):
        cx = PAD + j * (colw + 20)
        dr.rectangle([cx, top, cx + 4, top + 26], fill=col)
        dr.text((cx + 14, top + 1), title, font=_font(True, 17), fill=INK)
        yy = top + 36
        for it in items[:3]:
            yy = _wrap_draw(dr, cx + 14, yy, '· ' + it, _font(False, 15), INK_DIM, colw - 14, line_h=21) + 4
        hmax = max(hmax, yy - top)
    y = top + hmax + 8
    src = '데이터 모듈 LYNCH' if lyd else '최근 실적·어닝콜 체크포인트(경영진 로드맵)에서 도출'
    _note(dr, y, f'매도 규칙(린치, {info["ko"]}): {info["sell"]}')
    _footer(dr, f'유형·PEG=결정론 규칙(lynch.py, 『One Up on Wall Street』 기준) · 재무={_fin_src(P)} · '
                f'컨센서스=Yahoo Finance · 맞으려면/깨지면={src}')
    return im


# ── 4. 산업 지도 · 주도성 (박세익 관점) ────────────────────────────────
def _peer_metrics(L, ticker):
    """[(티커, 매출 성장 %, 영업이익률 %, 1년 주가 %, 시총)] — 대상 기업 포함."""
    def row(tk, ann, px, mc):
        rev = sorted(((y, v) for y, v in (ann.get('revenue') or {}).items() if v), key=lambda x: x[0])
        op = ann.get('opinc') or {}
        g = (rev[-1][1] / rev[-2][1] - 1) * 100 if len(rev) >= 2 and rev[-2][1] else None
        opm = (op.get(rev[-1][0]) / rev[-1][1] * 100) if rev and op.get(rev[-1][0]) is not None else None
        r1 = (px[-1] / px[0] - 1) * 100 if px and len(px) > 200 and px[0] else None
        return (tk, g, opm, r1, mc)
    me_px = [r['c'] for r in (L.get('daily') or [])][-252:]
    rows = [row(ticker, L.get('annual') or {}, me_px, (L.get('consensus') or {}).get('market_cap'))]
    for pt, pf in (L.get('peers') or {}).items():
        rows.append(row(pt, pf.get('ann') or {}, (L.get('peer_px') or {}).get(pt) or [], pf.get('mktcap')))
    return rows


def _rank(rows, i, me):
    vals = [(r[0], r[i]) for r in rows if r[i] is not None]
    if not any(t == me for t, _ in vals):
        return None, len(vals)
    order = sorted(vals, key=lambda x: -x[1])
    return [t for t, _ in order].index(me) + 1, len(vals)


def industry_page(P, idx):
    L = P.L or {}
    D, M = P.D, P.M
    vc = getattr(D, 'VALUE_CHAIN', None) or {}
    me = M['ticker']
    rows = _peer_metrics(L, me)
    if not vc.get('chain') and len(rows) < 2:
        return None                        # 그릴 근거가 없다 — 장을 뺀다
    im, dr = P._page(idx, '산업 지도 · 주도성', (vc.get('industry') or M.get('sector', '')) +
                     ' — 밸류체인 위치 · 업종 안 순위 · 업황')
    y = P.TOP2
    chain = [str(c) for c in (vc.get('chain') or [])][:6]
    if chain:
        dr.text((PAD, y), '밸류체인 (상류 → 하류)', font=_font(True, 18), fill=INK)
        y += 34
        n = len(chain)
        gap = 14
        bw = (CW - gap * (n - 1)) / n
        try:
            pos = int(vc.get('position', -1))
        except Exception:
            pos = -1
        spans = set(int(s) for s in (vc.get('spans') or []) if str(s).lstrip('-').isdigit()) | {pos}
        for i, c in enumerate(chain):
            x = PAD + i * (bw + gap)
            main, side = i == pos, i in spans
            dr.rounded_rectangle([x, y, x + bw, y + 74], radius=10,
                                 fill=ACCENT if main else (0xfb, 0xf1, 0xe1) if side else SURFACE,
                                 outline=ACCENT if side else LINE, width=2 if side else 1)
            _wrap_draw(dr, x + 10, y + 12, c, _font(True, 15), (255, 255, 255) if main else INK, bw - 20, line_h=20)
            if i < n - 1:
                ax = x + bw + 2
                dr.polygon([(ax, y + 31), (ax + gap - 4, y + 37), (ax, y + 43)], fill=INK_FAINT)
        y += 84
        lab = f'● {me} 주력 단계' + (' · 테두리 = 함께 걸친 단계' if len(spans) > 1 else '')
        dr.text((PAD, y), lab, font=_font(False, 13), fill=ACCENT)
        y += 24
        if vc.get('position_note'):
            y = _wrap_draw(dr, PAD, y, '위치의 의미: ' + vc['position_note'], _font(False, 15), INK_DIM, CW, line_h=21) + 10
    # 업종 안 순위
    if len(rows) >= 2:
        dr.text((PAD, y), f'업종 안 순위 (비교 {len(rows)}곳)', font=_font(True, 18), fill=INK)
        y += 32
        fmt = lambda v, s='%': '—' if v is None else f'{v:+.0f}{s}'
        body = [[t + (' ◀' if t == me else ''), fmt(g), fmt(o), fmt(r), P._m(mc)] for t, g, o, r, mc in rows]
        y = _table(dr, PAD, y, CW, ['기업', '매출 성장(최근 연)', '영업이익률', '1년 주가', '시총'], body,
                   widths=[22, 20, 20, 18, 20], aligns=['l', 'r', 'r', 'r', 'r'], row_h=40,
                   emph=[i for i, r in enumerate(rows) if r[0] == me]) + 8
        ranks = [(nm, _rank(rows, i, me)) for nm, i in (('성장', 1), ('수익성', 2), ('주가 강도', 3))]
        firsts = [nm for nm, (rk, n) in ranks if rk == 1 and n >= 2]
        txt = ' · '.join(f'{nm} {rk}/{n}위' for nm, (rk, n) in ranks if rk and n >= 2) or '비교 가능한 숫자가 부족함'
        verdict = (f'업종 안 주도 신호: {", ".join(firsts)} 1위' if firsts else '업종 안 1위 항목 없음')
        y = _wrap_draw(dr, PAD, y, f'{txt}  —  {verdict}', _font(True, 15), INK, CW, line_h=21) + 12
    # 업황
    cyc = vc.get('cycle') or ''
    drv = [str(d) for d in (vc.get('drivers') or [])][:3]
    if cyc or drv:
        dr.text((PAD, y), '업황', font=_font(True, 18), fill=INK)
        y += 30
        if cyc:
            y = _wrap_draw(dr, PAD, y, '· 국면: ' + cyc, _font(False, 15), INK_DIM, CW, line_h=21) + 4
        if drv:
            y = _wrap_draw(dr, PAD, y, '· 업황을 움직이는 변수: ' + ' / '.join(drv), _font(False, 15), INK_DIM, CW,
                           line_h=21) + 4
    if not chain:
        _note(dr, y + 8, '밸류체인·업황 서술은 다음 자료 갱신 때 연차보고서에서 채워진다. 지금은 비교 기업 숫자만.',
              interp=False)
    _footer(dr, ('밸류체인·업황=사업보고서(DART) 기반 서술 · 순위=DART 연간 재무' if _is_kr(P) else
                 '밸류체인·업황=연차보고서(10-K) 기반 서술 · 순위=SEC XBRL 연간 재무')
            + '·Yahoo Finance 1년 종가 · 비교 기업은 리포트 경쟁사 목록')
    return im
