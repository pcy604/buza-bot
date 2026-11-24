"""시황 요약 — stock-dashboard 의 일간·주간 시황 리포트를 텔레그램으로 (2026-10-21).

원칙: **계산은 대시보드 한 곳에서.** 봇은 대시보드가 매일 만드는 results/market_report.json 을 읽어
텔레그램 형식으로 다시 쓰기만 한다(숫자를 새로 계산하지 않는다 — 같은 날 두 화면 숫자가 다르면 안 된다).

- /market          가장 최근 장 마감 시황(한국 또는 미국)
- /market kr · us · week   한국 장 · 미국 장 · 주간
- /market on|off   자동 받기 (기본 꺼짐)
- deliver()        run.py 가 매 크론(매시 :07) 호출. 새 리포트를 1회만 보낸다.

발송 시각(2026-10-21): 대시보드 market-report 워크플로가 장 마감 직후 고정 시각에 만든다 —
  🇰🇷 한국 장: KST 15:50 생성 → 16시대 발송 · 🇺🇸 미국 장: KST 06:30 생성(서머타임 무관) → 7시대 발송.
  사용자 설정 시각이 아니라 '장'에 묶인다. 늦게 생성돼도 창(한국 15~22시 · 미국 6~12시) 안이면 보낸다.

빼는 것: 대시보드 리포트의 '이번 주 판정'(코어/위성/현금 목표 비중)은 소유자 개인 원칙(v1.3)에 따른
자산배분이라 다른 사람에게 보내면 투자 권유가 된다 — 봇에는 싣지 않는다.
"""
import json
import re

import requests

import prefs

SRC = 'https://raw.githubusercontent.com/pcy604/stock-dashboard/main/results/market_report.json'
FLAG = {'KR': '🇰🇷', 'US': '🇺🇸'}
KINDS = ('kr', 'daily', 'weekly')
TITLE = {'kr': '🇰🇷 <b>한국 장 마감</b>', 'daily': '🇺🇸 <b>미국 장 마감</b>', 'weekly': '📰 <b>주간 시황</b>'}
WINDOW = {'kr': (15, 22), 'daily': (6, 12), 'weekly': (6, 22)}   # KST 시각 창
BASIS = {'d1': '오늘', 'ret_1w': '1주', 'ret_4w': '4주'}
KR_SYMS = {'^KS11', '^KQ11'}


# raw.githubusercontent.com 은 최대 5분 캐시라, 리포트 커밋 직후엔 옛 판을 준다(→ 발송이 한 회차 밀림).
# GitHub API(contents, raw)는 캐시가 없다 — 먼저 쓰고 실패하면 raw. 2026-11-06
SRC_API = 'https://api.github.com/repos/pcy604/stock-dashboard/contents/results/market_report.json?ref=main'


def fetch(timeout: int = 20) -> dict:
    import os
    hdr = {'Accept': 'application/vnd.github.raw+json', 'User-Agent': 'buza-alarm-bot'}
    tok = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if tok:
        hdr['Authorization'] = f'Bearer {tok}'
    for url, h in ((SRC_API, hdr), (SRC, {})):
        try:
            r = requests.get(url, headers=h, timeout=timeout)
            if r.ok:
                return r.json()
        except Exception as e:
            print(f'[시황] 가져오기 실패({url[:30]}): {e}')
    return {}


def _josa(word: str, a: str = '은', b: str = '는') -> str:
    """받침 있으면 a, 없으면 b — '나스닥는' 같은 조사 오류(11-05 실측) 방지. 영문·숫자 끝은 b."""
    ch = (word or ' ')[-1]
    if '가' <= ch <= '힣':
        return a if (ord(ch) - 0xAC00) % 28 else b
    return b


def _esc(s) -> str:
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _pct(v) -> str:
    return '-' if v is None else f'{v:+.1f}%'


_SUFFIX = re.compile(r',?\s+(inc\.?|corp\.?|corporation|co\.?|ltd\.?|plc|holdings,?|n\.v\.|s\.a\.|/[a-z]{2,3}/?)$', re.I)


def clean_name(n: str) -> str:
    """'HASBRO, INC.' → 'Hasbro' · 'Moderna, Inc.' → 'Moderna'. 한글 이름은 그대로."""
    n = (n or '').strip()
    for _ in range(2):
        n = _SUFFIX.sub('', n).strip(' ,')
    if n.isupper() and re.search('[A-Z]{4,}', n):
        n = n.title()
    return n


def _round_ai(t: str) -> str:
    """AI 문장 속 '3.29%' → '3.3%' — 표와 같은 소수 1자리로(2026-10-21: 문장 3.29% · 표 +3.3% 로 어긋났다)."""
    return re.sub(r'(-?\d+\.\d{2,})(\s*%)', lambda m: f'{float(m.group(1)):.1f}{m.group(2)}', t or '')


def _section(md: str, title: str, numbered: bool = False) -> str:
    """AI 판 마크다운에서 '## 제목' 아래 본문만 꺼낸다(없으면 '')."""
    m = re.search(rf'^##\s*{re.escape(title)}[^\n]*\n(.*?)(?=^##\s|\Z|^※)', md or '', re.S | re.M)
    if not m:
        return ''
    body = re.sub(r'\*\*(.+?)\*\*', r'\1', m.group(1)).strip()
    lines = [re.sub(r'^\s*(?:[*\-•]|\d+\.)\s+', '', ln).strip() for ln in body.splitlines() if ln.strip()]
    lines = [_round_ai(x) for x in lines]
    return '\n'.join(f'{i}. {x}' for i, x in enumerate(lines, 1)) if numbered else ' '.join(lines)


# 색: 상승 🟢 · 하락 🔴 — 대시보드 표 규칙(+ 초록 / − 빨강, CLAUDE.md 표 규칙)과 같게(2026-10-21).
#   한국식(빨강↑·파랑↓)과 미국식이 섞이면 같은 🔴 가 화면마다 뜻이 뒤집힌다. 한 서비스 안에서는 하나로.
UP, DOWN, FLAT = '🟢', '🔴', '⚪'


def _dot(v) -> str:
    return FLAT if v is None or abs(v) < 0.05 else (UP if v > 0 else DOWN)


def _chg(v) -> str:
    return '-' if v is None else f'{v:+.1f}%'


_WD = '월화수목금토일'


def _day(d: str) -> str:
    try:
        from datetime import date as _d
        x = _d.fromisoformat(d)
        return f'{x.month}/{x.day}({_WD[x.weekday()]})'
    except Exception:
        return d or ''


def _num(v) -> str:
    return f'{v:,.2f}' if v < 100 else f'{v:,.1f}' if v < 10000 else f'{v:,.0f}'


def _idx_line(x, kind) -> str:
    a, b, lb = ('d5', 'm1', '1개월') if kind == 'weekly' else ('d1', 'd5', '5일')
    if x.get('sym') == '^TNX' and x.get(a) is not None:   # 금리는 % 변화가 아니라 bp 로 읽는다
        c, r = x['close'], x[a] / 100
        bp = round(c * r / (1 + r) * 100)
        return f"{_dot(x.get(a))} 미국 10년물 {c:.2f}% <b>{bp:+d}bp</b> · {lb} {_chg(x.get(b))}"
    return f"{_dot(x.get(a))} {_esc(x['name'])} {_num(x['close'])} <b>{_chg(x.get(a))}</b> · {lb} {_chg(x.get(b))}"


def _chips(rows, key='ret', name=lambda r: r['name'], n=5, extra=None) -> str:
    out = []
    for r in rows[:n]:
        e = extra(r) if extra else ''
        out.append(f"{_esc(clean_name(name(r)))} {_chg(r.get(key))}{e}")
    return ' · '.join(out)


def _amt(b) -> str:
    """억원 → '2.6조' · '3,739억'."""
    return f'{b / 10000:,.1f}조' if b >= 10000 else f'{b:,}억'


def gate_line(f: dict) -> str:
    """실전 신호등 — 코스피·코스닥 주봉 5주선(봇 v1.9 지수 게이트와 같은 계산). 지난주 확정 + 이번 주 지금까지."""
    idx = {x.get('sym'): x for x in f.get('indices', [])}
    g = [(nm, (idx.get(s) or {}).get('gate5w')) for s, nm in (('^KS11', '코스피'), ('^KQ11', '코스닥'))]
    g = [(nm, x) for nm, x in g if x]
    if not g:
        return ''
    n = sum(1 for _, x in g if x.get('on'))
    head = '신규 매수 가능' if n == len(g) else '신규 매수 중지' if n == 0 else '일부만 가능'
    body = ' · '.join(f"{nm} {_chg(x.get('gap'))}" for nm, x in g)
    live = ' · '.join(f"{nm} {_chg(x.get('live_gap'))}" for nm, x in g if x.get('partial') and x.get('live_gap') is not None)
    return f"{head} — 주봉 5주선 대비 {body}" + (f" (이번 주 지금까지 {live})" if live else '')


def flow_line(kr: dict) -> str:
    fl = (kr.get('flow') or {}).get('KOSPI') or {}
    if not fl:
        return ''
    return '코스피 수급(잠정) ' + ' · '.join(f"{k} {_amt_signed(fl[k])}" for k in ('외국인', '기관', '개인') if k in fl)


def _amt_signed(v) -> str:
    """억원 → '+1.7조'·'−520억'."""
    a = abs(v)
    t = f'{a / 10000:,.1f}조' if a >= 10000 else f'{a:,.0f}억'
    return ('+' if v > 0 else '-' if v < 0 else '') + t


def sector_groups(kr: dict) -> list:
    """히트맵 행(네이버 업종 16묶음)을 시총가중 등락으로 — 업종 목록용. 대장주 = 묶음 안 시총 1위."""
    g = {}
    for r in kr.get('heatmap') or []:
        if (r.get('mc') or 0) > 0 and r.get('ret') is not None and r.get('sec') != '기타':
            g.setdefault(r['sec'], []).append(r)
    out = []
    for name, rows in g.items():
        if len(rows) < 3:
            continue
        mc = sum(r['mc'] for r in rows)
        lead = max(rows, key=lambda r: r['mc'])
        out.append(dict(name=name, n=len(rows), ret=round(sum(r['ret'] * r['mc'] for r in rows) / mc, 1),
                        lead=lead['name'], lead_ret=lead['ret']))
    return sorted(out, key=lambda d: -d['ret'])


def movers_lines(kr: dict) -> list:
    """52주 신고가·특징주·거래대금 상위 — 대시보드 market_report.kr_movers 가 계산한 것 그대로(2026-11-11 차니 요청)."""
    L = []
    nh = kr.get('new_high_52w') or {}
    if nh:
        L += ['', f"🏆 <b>52주 신고가 {nh['n']}종</b> <i>(시총 1천억+ {nh['universe']:,}종 · 장중 고가 기준)</i>"]
        if nh.get('top'):
            L.append(' · '.join(f"{_dot(r['ret'])} {_esc(r['name'])} {_chg(r['ret'])}" + (' 🆕' if r.get('young') else '')
                                for r in nh['top'][:6]))
    if kr.get('themes_top'):
        L += ['', '🧩 <b>강세 테마</b> <i>(네이버 테마 · 구성 종목 평균)</i>']
        L += [f"{_dot(t['ret'])} {_esc(t['name'])} <b>{_chg(t['ret'])}</b> — " + ' · '.join(_esc(x['name']) for x in t['lead'][:3])
              for t in kr['themes_top'][:3]]
        if kr.get('themes_bottom'):
            L.append(f'{DOWN} 약세 ' + ' · '.join(f"{_esc(t['name'])} {_chg(t['ret'])}" for t in kr['themes_bottom'][:3]))
    if kr.get('featured'):
        L += ['', '🔥 <b>특징주</b> <i>(상한가·+10% 급등 중 거래대금 순)</i>',
              ' · '.join(f"{_esc(r['name'])} {_chg(r['ret'])} <i>{_esc(r['tag'])}</i>" for r in kr['featured'][:6])]
    lu = kr.get('limit_up') or []
    if lu:
        more = f' 외 {len(lu) - 5}' if len(lu) > 5 else ''
        L.append(f"⬆️ 상한가 {len(lu)}종: " + ' · '.join(_esc(r['name']) for r in lu[:5]) + more)
    if kr.get('turnover_top'):
        L += ['', '💰 <b>거래대금 상위 5</b>',
              ' · '.join(f"{_dot(r['ret'])} {_esc(r['name'])} {_chg(r['ret'])} ({_amt(r['amt_b'])})" for r in kr['turnover_top'][:5])]
    return L


def _insights(f, kind) -> list:
    """숫자에서 바로 읽히는 것만 규칙으로(예측·원인 추정 없음)."""
    out = []
    idx = {x.get('sym'): x for x in f.get('indices', []) if x.get('close') is not None}
    kr = (f.get('stocks') or {}).get('KR') or {}
    b = kr.get('breadth_all') or {}
    ks = idx.get('^KS11')
    if kind == 'kr' and ks and b.get('up') is not None:
        if (ks.get('d1') or 0) > 0 and b['down'] > b['up']:
            out.append(f"지수는 올랐는데 하락 종목이 더 많아요({b['up']:,} vs {b['down']:,}) — 대형주로 쏠린 장")
        elif (ks.get('d1') or 0) < 0 and b['up'] > b['down']:
            out.append(f"지수는 내렸는데 상승 종목이 더 많아요({b['up']:,} vs {b['down']:,}) — 대형주만 약한 장")
    for sym, nm in (('^KS11', '코스피'),) if kind == 'kr' else (('^GSPC', 'S&P500'), ('^IXIC', '나스닥')):
        x = idx.get(sym)
        if x and x.get('above_200d') is False:
            out.append(f'{nm}{_josa(nm)} 아직 200일선 아래 — 52주 고점 대비 {_chg(x.get("from_52w_high"))}')
    v = idx.get('^VIX')
    if kind != 'kr' and v and v['close'] >= 20:
        out.append(f"VIX {v['close']:.1f} — 변동성 {'높음' if v['close'] >= 25 else '경계'} 구간(20 이상)")
    return out[:3]


def render(rec: dict, dash_url: str = '') -> str:
    f = rec.get('facts') or {}
    kind = rec.get('kind') or f.get('kind') or 'daily'
    md = rec.get('markdown', '')
    L = [f"{TITLE.get(kind, '📰 시황')} · {_day(rec.get('date', ''))}", '━━━━━━━━━━━━']
    idx = [x for x in f.get('indices', []) if x.get('close') is not None
           and not (kind == 'daily' and x.get('sym') in KR_SYMS)]   # 한국 지수는 오후 리포트 몫
    head = [x for x in idx if x.get('sym') in ('^KS11', '^KQ11', '^GSPC', '^IXIC')][:2]
    if head:
        k = 'd5' if kind == 'weekly' else 'd1'
        L.append('<b>' + ' · '.join(f"{_esc(x['name'])} {_chg(x.get(k))}" for x in head) + '</b>')
    one = _section(md, '한 줄 요약')
    if one:
        L.append(_esc(one))
    tips = _insights(f, kind)
    if tips:
        L += [''] + [f'💡 {_esc(t)}' for t in tips]
    gl = gate_line(f) if kind == 'kr' else ''
    if gl:
        L += ['', f'🚦 <b>실전 규칙</b> {_esc(gl)}']

    L += ['', '📊 <b>지수</b>'] + [_idx_line(x, kind) for x in idx]

    us = f.get('us') or {}
    if us.get('assets'):
        L += ['', '🌍 <b>자산</b>', ' · '.join(f"{_dot(a.get('d1'))} {_esc(a['name'])} {_chg(a.get('d1'))}" for a in us['assets'])]

    st = {k: v for k, v in (f.get('stocks') or {}).items() if isinstance(v, dict)}
    kr = st.get('KR') if kind in ('kr', 'weekly') else None
    if kind == 'kr' and kr:
        b, t = kr.get('breadth_all') or {}, kr.get('turnover_tn') or {}
        if b:
            tot = b['up'] + b['down'] + b['flat']
            L += ['', '🌡 <b>시장 폭</b>',
                  f"{UP} 상승 {b['up']:,} · {DOWN} 하락 {b['down']:,} · {FLAT} 보합 {b['flat']:,} — 상승 {round(b['up'] / tot * 100) if tot else 0}%",
                  f"상한가 {b['limit_up']} · 하한가 {b['limit_down']}"
                  + (' · 거래대금 ' + ' · '.join(f'{k} {v:,.1f}조' for k, v in t.items()) if t else '')]
        if flow_line(kr):
            L.append(_esc(flow_line(kr)))
        L += movers_lines(kr)
        if kr.get('megacaps'):
            m = kr['megacaps']
            L += ['', '🏢 <b>시총 상위 10</b>',
                  ' · '.join(f"{_dot(r['ret'])} {_esc(r['name'])} {_chg(r['ret'])}" for r in m[:5]),
                  ' · '.join(f"{_dot(r['ret'])} {_esc(r['name'])} {_chg(r['ret'])}" for r in m[5:10])]
        sg = sector_groups(kr)
        if sg or kr.get('sectors'):
            sc = sg or kr['sectors']   # 네이버 업종 묶음(사람이 쓰는 이름) 우선, 없으면 옛 KSIC
            lead = lambda r: f" ({_esc(r['lead'])})" if r.get('lead') else ''
            L += ['', '🏭 <b>업종</b> <i>(시총 1조+, 시총가중)</i>',
                  f'{UP} ' + _chips(sc, n=3, extra=lead), f'{DOWN} ' + _chips(list(reversed(sc)), n=3, extra=lead)]
    if kind == 'daily':
        if us.get('sectors'):
            sc = us['sectors']
            L += ['', '🏭 <b>업종</b> <i>(S&amp;P500 섹터 ETF)</i>',
                  '강세 ' + ' · '.join(f"{_dot(r['d1'])} {_esc(r['name'])} {_chg(r['d1'])}" for r in sc[:3]),
                  '약세 ' + ' · '.join(f"{_dot(r['d1'])} {_esc(r['name'])} {_chg(r['d1'])}" for r in reversed(sc[-3:]))]
        if us.get('megacaps'):
            m = us['megacaps']
            L += ['', '🏢 <b>대형 기술·대장주</b>',
                  ' · '.join(f"{_dot(r['d1'])} {_esc(r['name'])} {_chg(r['d1'])}" for r in m[:5]),
                  ' · '.join(f"{_dot(r['d1'])} {_esc(r['name'])} {_chg(r['d1'])}" for r in m[5:10])]

    mv = {'kr': ['KR'], 'daily': ['US'], 'weekly': ['KR', 'US']}.get(kind, [])
    mv = [m for m in mv if st.get(m, {}).get('top')]
    if mv:
        basis = st[mv[0]].get('basis', 'ret_1w')
        pd_ = (f.get('stocks') or {}).get('perf_date')
        when = f' · {pd_} 기준' if basis != 'd1' and pd_ else ''
        L += ['', f"🚀 <b>대형주 급등·급락</b> <i>({BASIS.get(basis, basis)}{when})</i>"]
        for m in mv:
            fl = f'{FLAG[m]} ' if len(mv) > 1 else ''
            L.append(f"{fl}{UP} " + _chips(st[m]['top'], n=4))
            L.append(f"{fl}{DOWN} " + _chips(st[m]['bottom'], n=4))
        if kind == 'weekly':
            L.append('상승 비율 ' + ' · '.join(f"{FLAG[m]} {st[m]['breadth_up']}%" for m in mv)
                     + ' · 52주 신고가 근접 ' + ' · '.join(f"{FLAG[m]} {st[m].get('near_52w', '-')}종" for m in mv))

    sg = f.get('signals') or {}
    md_ = {k: v for k, v in (sg.get('market_direction') or {}).items() if v and (kind == 'weekly' or k == {'kr': 'KR', 'daily': 'US'}.get(kind))}
    if md_:
        L += ['', '🧭 <b>신호</b>', 'CANSLIM 시장 방향 ' + ' · '.join(f'{FLAG[m]} {_esc(v)}' for m, v in md_.items())]
        acc = [c.get('sym') for c in sg.get('accel_new') or [] if c.get('sym')]
        if acc and kind != 'kr':
            L.append(f"이익 가속 신규 <i>({_esc(sg.get('accel_week', ''))} 주)</i>: {_esc(', '.join(acc[:10]))}")
    chk = _rule_checks(rec, md)
    if chk:
        L += ['', '✅ <b>확인할 것</b>', f'<blockquote expandable>{_esc(chk)}</blockquote>']
    tail = f'📊 <a href="{dash_url}">대시보드</a> · ' if dash_url else ''
    L += ['', f'{tail}<i>숫자 자동 집계 · 문장 AI · 투자 권유 아님</i>']
    return '\n'.join(L)[:4000]



def _rule_checks(rec: dict, md: str) -> str:
    """확인할 것 — 2026-11-12: 대시보드와 같은 숫자 조건(facts.rule_checks, market_report.rule_checks)이 있으면 그것,
    없으면 예전 AI 체크포인트. AI 문장은 '~할지'처럼 판정 기준이 없어 행동으로 못 옮긴다."""
    rc = ((rec.get('facts') or {}).get('rule_checks')) or []
    if rc:
        return '\n'.join(f"{i}. {str(r).replace('**', '')}" for i, r in enumerate(rc, 1))
    return _section(md, '체크포인트', numbered=True)

def latest_kind(db: dict) -> str:
    """한국·미국 장 리포트 중 더 최근에 만든 것."""
    c = [(db[f'latest_{k}'].get('generated', ''), k) for k in ('kr', 'daily') if db.get(f'latest_{k}')]
    return max(c)[1] if c else 'daily'


def caption(rec: dict, dash_url: str = '') -> str:
    """포토카드 아래 글 — 헤드라인·한 줄 요약·💡·확인할 것(접힘)·링크. 텔레그램 캡션 1024자 안."""
    f = rec.get('facts') or {}
    kind = rec.get('kind') or f.get('kind') or 'daily'
    md = rec.get('markdown', '')
    idx = [x for x in f.get('indices', []) if x.get('close') is not None
           and not (kind == 'daily' and x.get('sym') in KR_SYMS)]
    head = [x for x in idx if x.get('sym') in ('^KS11', '^KQ11', '^GSPC', '^IXIC')][:2]
    k = 'd5' if kind == 'weekly' else 'd1'
    L = [f"{TITLE.get(kind, '📰 시황')} · {_day(rec.get('date', ''))}"]
    if head:
        L.append(' · '.join(f"{_dot(x.get(k))} {_esc(x['name'])} <b>{_chg(x.get(k))}</b>" for x in head))
    tips = _insights(f, kind)   # 한 줄 요약은 카드 이미지에 있다 — 캡션에서 되풀이하지 않는다
    if tips:
        L += [''] + [f'💡 {_esc(t)}' for t in tips]
    tail = (f'\n\n📊 <a href="{dash_url}">대시보드</a> · ' if dash_url else '\n\n') + '<i>투자 권유 아님</i>'
    chk = _rule_checks(rec, md)
    body = '\n'.join(L)
    if chk:
        room = 1000 - len(body) - len(tail) - 60
        if room > 80:
            c = _esc(chk)
            c = c if len(c) <= room else c[:room - 1].rsplit('\n', 1)[0]
            body += f'\n\n✅ <b>확인할 것</b>\n<blockquote expandable>{c}</blockquote>'
    return (body + tail)[:1024]


def _send_one(chat, rec: dict, dash_url: str = '') -> bool:
    """기본은 포토카드(이미지+캡션). /market text 로 바꾼 사람·이미지 실패 때는 예전 텍스트.
    2026-11-11 3장 앨범(히트맵)은 차니 판단 '작게 보면 별로·종목명 잘림'으로 접고 1장 카드에 엣지를 더함."""
    import tg
    if prefs.get(chat).get('market_fmt') != 'text':
        f = rec.get('facts') or {}
        kind = rec.get('kind') or f.get('kind') or 'daily'
        if kind in ('kr', 'daily'):   # 2장(시장 판단 / 오늘의 종목) — 2026-11-14 미국 장도(대시보드 종합 탭과 같은 구성). 실패하면 아래 1장
            try:
                import tempfile, market_card
                ps = market_card.render_kr2(rec, tempfile.mkdtemp(), one_liner=_section(rec.get('markdown', ''), '한 줄 요약'),
                                            tips=_insights(f, kind))
                if len(ps) == 2 and tg.send_media_group(chat, ps, caption(rec, dash_url)):
                    return True
            except Exception as e:
                print(f'[시황 2장 실패 → 1장] {e}')
        try:
            import tempfile, market_card
            path = market_card.render(rec, tempfile.mktemp(suffix='.png'),
                                      one_liner=_section(rec.get('markdown', ''), '한 줄 요약'),
                                      tips=_insights(f, rec.get('kind') or f.get('kind') or 'daily'))
            if tg.send_photo(chat, path, caption(rec, dash_url)):
                return True
        except Exception as e:
            print(f'[시황 카드 실패 → 텍스트] {e}')
    return bool(tg.send_message(chat, render(rec, dash_url)))


def send(chat, kind: str = None, db: dict = None, dash_url: str = '') -> bool:
    import tg
    db = db if db is not None else fetch()
    kind = kind or latest_kind(db)
    rec = db.get(f'latest_{kind}')
    if not rec:
        return bool(tg.send_message(chat, '시황 리포트를 아직 못 가져왔어요. 잠시 뒤 다시 시도해 주세요.'))
    return _send_one(chat, rec, dash_url)


def subscribers() -> list:
    """/market on 한 사람 + 소유자(기본 켜짐, /market off 로 끔). 2026-10-22: 소유자가 구독을 안 켜 둬서 아무것도 안 왔다."""
    d = prefs._load()
    subs = {int(c) for c, p in d.items() if p.get('market')}
    try:
        import brief
        o = str(brief._owner_chat() or '')
        if o and d.get(o, {}).get('market') is not False:
            subs.add(int(o))
    except Exception:
        pass
    return sorted(subs)


def set_sub(chat, on: bool):
    prefs._set(chat, market=bool(on))


STALE_H = 20   # 생성 후 이 시간이 지난 리포트는 안 보낸다(다음 장 리포트가 곧 나온다)


def _due(rec: dict, p: dict, now=None) -> bool:
    """안 받은 리포트이고, 만든 지 STALE_H 시간 안이고, KST 06~23시면 보낸다.
    2026-10-24: 예전엔 장마다 고정 창(한국 15~22시·미국 6~12시)이라, 리포트나 봇 실행이 늦으면
    창을 지나 그날 시황이 아예 안 갔다(10-23 미국·한국 모두). 늦게라도 가는 게 안 가는 것보다 낫다."""
    if not rec or p.get(f"market_sent_{rec.get('kind')}") == rec.get('date'):
        return False
    from datetime import datetime, timezone
    kst = prefs.local_now({'tz': 'Asia/Seoul'}, now)   # 시계는 prefs 한 곳(테스트가 바꿔 끼운다)
    now = kst.astimezone(timezone.utc)
    try:
        # 2026-11-24: 대시보드는 11-12 부터 generated 를 **KST** 로 찍는다(market_report._now_kst). 여기서 UTC 로 읽어
        #   리포트가 9시간 '미래'로 보였고(age < -600 → 거름), 한국판은 다음 날 08시·미국판은 그날 20시 tick 에야 갔다.
        from zoneinfo import ZoneInfo
        gen = datetime.strptime(str(rec.get('generated', ''))[:16], '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Seoul'))
        age = (now - gen).total_seconds()
        if age > STALE_H * 3600 or age < -600:   # 미래 시각(시계 어긋남·테스트 자료)도 거른다
            return False
    except ValueError:
        pass
    return 5 <= kst.hour <= 23   # 미국 서머타임 땐 05시대에 나온다(장 마감 05:00 KST + 20분)


def deliver(dash_url: str = '') -> int:
    subs = subscribers()
    if not subs:
        return 0
    db = fetch()
    if not db:
        return 0
    import tg
    n = 0
    for chat in subs:
        p = prefs.get(chat)
        for kind in KINDS:
            rec = db.get(f'latest_{kind}')
            if _due(rec, p) and _send_one(chat, rec, dash_url):
                prefs._set(chat, **{f'market_sent_{kind}': rec.get('date')})
                n += 1
    return n
