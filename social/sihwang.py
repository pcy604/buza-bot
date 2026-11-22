# -*- coding: utf-8 -*-
"""시황 생성기 — market_report.json 을 읽어 content/sihwang_*.json 을 쓴다 (2026-11-23).

  python -m social.sihwang kr            # 한국 장 마감판 (KST 15:50)
  python -m social.sihwang daily         # 미국 장 마감판 (KST 06:30)
  python -m social.sihwang kr --print    # 파일로 안 쓰고 화면에만

무엇을 만드나
  ① 훅 후보 3개  — 절댓값이 가장 큰 사실부터. 승인 때 사람이 고른다
  ② 카드 배열    — 1카드 = 1문단 = 1포토카드 = 1숏츠컷. card/capture/text/say
  ③ 숫자 블록    — numbers
  ④ 고정 블록    — takeaway · caveat · cta · tags

자동화하지 않는 것
  해석 문장("자금이 좁은 곳으로 몰렸다")은 사실이 아니라 추론이다. 카드마다 1개만
  `guess` 로 제안하고, 승인 때 사람이 지우거나 고친다. 기본값은 비워 두지 않고 넣되
  **반드시 사람 눈을 거친다**(social draft → 텔레그램 미리보기 → approve).

문체
  stock_screener/CLAUDE.md 공개 문구 규칙 — 평서 종결(~했다)·명사형·전문 용어.
  구어체·질문형 금지. `say`(TTS)만 ~습니다 체이고 숫자를 한글로 읽어 준다.
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCREENER = ROOT.parent / 'stock_screener'
REPORT = SCREENER / 'results' / 'market_report.json'
FLOW = SCREENER / 'results' / 'kr_flow.json'
BOT_LOG = SCREENER / 'data' / 'live_bot.log'
V19 = SCREENER / 'results' / 'v19_bt.json'
OUT = ROOT / 'content'

DASH = 'https://stock-dashboard-dmfvhcig7brge7utl7et5r.streamlit.app/'

# ── TTS 발음 ──────────────────────────────────────────────────────────────────
_DIG = '영일이삼사오육칠팔구'


def _say_num(s: str) -> str:
    """'−10.73%' → '마이너스 십 점 칠삼 퍼센트'. 숫자를 그냥 넘기면 TTS 가 제멋대로 읽는다."""
    def rd(m):
        sign = '마이너스 ' if m.group(1) in ('-', '−') else ('플러스 ' if m.group(1) == '+' else '')
        whole, frac = m.group(2).replace(',', ''), m.group(3)
        out = sign + _say_int(whole)
        if frac:
            out += ' 점 ' + ''.join(_DIG[int(c)] for c in frac)
        return out
    # 날짜는 숫자 변환에서 먼저 빼 둔다 — '11-19' 가 '십일 마이너스 십구' 로 읽히던 것(2026-11-23).
    #   자리표시는 본문에 나올 수 없는 기호로 감싼다. 공백으로 감싸면 '5일 32bp' 같은
    #   평범한 숫자까지 날짜로 되돌려져 더 크게 망가진다.
    keep = []
    MK = '␟'                      # 기호 ␟ — 시황 본문에 쓰일 일이 없다

    def hide(m):
        keep.append(m.group(0))
        # 자리표시에 숫자를 쓰면 아래 숫자 변환이 그것까지 한글로 바꿔 복원이 깨진다
        # (실측: '11-19' → 'MK0MK' → 'MK영MK' → 복원 실패). 그래서 글자로 센다.
        return f'{MK}{chr(ord("A") + len(keep) - 1)}{MK}'
    s = re.sub(r'\d{4}-\d\d-\d\d|\d\d-\d\d', hide, s)
    s = re.sub(r'([-−+]?)([\d,]+)(?:\.(\d+))?', rd, s)
    s = re.sub(MK + r'([A-Z])' + MK, lambda m: _say_date(keep[ord(m.group(1)) - ord('A')]), s)
    return s.replace('%', ' 퍼센트').replace('조원', '조 원').replace('bp', '베이시스포인트')


def _say_date(t: str) -> str:
    """'2026-11-12' → '십일월 십이일'. 연도는 읽지 않는다(같은 해라 군더더기)."""
    p = t.split('-')
    mm, dd = (p[-2], p[-1])
    return f'{_say_int(mm)}월 {_say_int(dd)}일'


def _say_int(n: str) -> str:
    """한국어 수사. 4자리 넘으면 TTS 가 더 잘 읽으므로 숫자 그대로 둔다."""
    try:
        v = int(n)
    except ValueError:
        return n
    if v >= 10000:
        return f'{v:,}'
    units = ['', '십', '백', '천']
    out, s = '', str(v)
    for i, c in enumerate(s):
        d, u = int(c), units[len(s) - 1 - i]
        if d == 0:
            continue
        out += ('' if (d == 1 and u) else _DIG[d]) + u
    return out or '영'


def say(text: str) -> str:
    """자막 문장 → 음성 문장. 평서 종결을 높임말로 바꾸고 숫자를 한글로."""
    t = _say_num(text)
    for a, b in (('했다.', '했습니다.'), ('이다.', '입니다.'), ('았다.', '았습니다.'), ('었다.', '었습니다.'),
                 ('린다.', '립니다.'), ('린다 ', '립니다 '), ('없다.', '없습니다.'), ('있다.', '있습니다.'),
                 ('아니다.', '아닙니다.'), ('된다.', '됩니다.'), ('난다.', '납니다.'), ('진다.', '집니다.')):
        t = t.replace(a, b)
    return t


def card(key, capture, text, guess='', big='', big_label=''):
    """big/big_label — 숏츠 프레임 윗부분에 크게 띄울 숫자 한 개.
    카드 이미지는 가로로 넓어 9:16 화면에서 위가 비는데, 그 자리를 '오늘의 숫자' 로 쓴다."""
    return dict(card=key, capture=capture, text=text, say=say(text), guess=guess,
                big=big, big_label=big_label)


# ── 원천 읽기 ────────────────────────────────────────────────────────────────
def _j(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception:
        return default if default is not None else {}


def _ix(facts, name):
    for i in facts.get('indices') or []:
        if i.get('name') == name:
            return i
    return {}


def _pct(v, nd=1):
    return '-' if v is None else f'{v:+.{nd}f}%'


def rule_state():
    """내 규칙이 지금 무엇을 하고 있나 — 모든 콘텐츠의 ⑤번 블록. 사실만 쓴다."""
    rc = (_j(REPORT).get('latest_kr') or {}).get('facts', {}).get('rule_checks') or []
    gate = [r for r in rc if '5주선' in r and '재개' in r]
    last_buy, holds = None, set()
    try:
        log = BOT_LOG.read_text(encoding='utf-8', errors='replace')
        buys = re.findall(r'주문 봇 (\d{4}-\d\d-\d\d).{0,4000}?🔴 매수', log, re.S)
        last_buy = buys[-1] if buys else None
        for d, nm in re.findall(r'※ (\S+) 불타기 조건 충족 — 소속 시장 5주선 아래라 보류', log) and []:
            pass
        holds = set(re.findall(r'※ (\S+) 불타기 조건 충족', log))
    except Exception:
        pass
    return dict(gate_lines=[re.sub(r'\*\*', '', g) for g in gate], last_buy=last_buy, blocked=sorted(holds))


# ── 한국 장 마감판 ────────────────────────────────────────────────────────────
def build_kr():
    rep = _j(REPORT)
    kf = (rep.get('latest_kr') or {}).get('facts') or {}
    df = (rep.get('latest_daily') or {}).get('facts') or {}
    if not kf:
        raise RuntimeError('latest_kr 없음 — market_report.json 확인')
    ik = kf.get('internals_kr') or {}
    d = kf.get('date') or (rep.get('latest_kr') or {}).get('date') or str(date.today())

    ks, kq = _ix(kf, '코스피'), _ix(kf, '코스닥')
    sox, vix, ndq = _ix(df, '필라델피아 반도체'), _ix(df, 'VIX'), _ix(df, '나스닥')
    b = ik.get('breadth_all') or {}
    up, dn, fl = b.get('up', 0), b.get('down', 0), b.get('flat', 0)
    uni = ik.get('universe') or (up + dn + fl)
    nh = (ik.get('new_high_52w') or {}).get('n')
    mega = [m for m in (ik.get('megacaps') or []) if not re.search(r'우$|우B$|\d우$', m.get('name', ''))]
    sec_w = sorted([s for s in (ik.get('sectors') or [])
                    if s.get('ret') is not None and not re.match(r'그외|기타', s.get('name', ''))],
                   key=lambda s: s['ret'])[:3]
    th_t = (ik.get('themes_top') or [])[:2]
    feat = [f for f in (ik.get('featured') or []) if (f.get('ret') or 0) >= 25][:4]
    flow = (_j(FLOW).get('summary') or {})
    cr = flow.get('credit') or {}
    rs = rule_state()

    cards, numbers, hooks = [], [], []

    # ① 글로벌 — 원인이 밖에 있으면 밖부터
    if sox.get('d1') is not None:
        t = (f"간밤 미국 증시가 먼저 무너졌다. 필라델피아 반도체 {_pct(sox['d1'])}, "
             f"나스닥 {_pct(ndq.get('d1'))}. 변동성지수 VIX는 {vix.get('close')}로 하루 "
             f"{abs(vix.get('d1') or 0):.1f}% 올랐고 5일 누적으로는 {abs(vix.get('d5') or 0):.0f}% 상승했다. "
             f"코스피 {_pct(ks.get('d1'))}, 코스닥 {_pct(kq.get('d1'))}는 이 흐름의 연장선에 있다.")
        cards.append(card('글로벌 마켓', 'global', t,
                          big=_pct(sox['d1']), big_label='필라델피아 반도체'))
        numbers += [f"필라델피아 반도체 {sox.get('close'):,.0f} · {_pct(sox['d1'])} · 5일 {_pct(sox.get('d5'))}",
                    f"VIX {vix.get('close')} · {_pct(vix.get('d1'))} · 5일 {_pct(vix.get('d5'))}"]
        hooks.append(f"코스피 {_pct(ks.get('d1'))}는 결과였다. 간밤 필라델피아 반도체가 "
                     f"{abs(sox['d1']):.1f}% 빠졌고, 변동성지수는 하루 만에 {abs(vix.get('d1') or 0):.0f}% 올랐다.")

    # ② 시장 폭 — 지수보다 체감에 가깝다
    rate = (up / uni * 100) if uni else 0
    t = (f"국내 지표에서 지수보다 무거운 것은 폭이다. 시가총액 1,000억원 이상 {uni:,}종목 가운데 "
         f"상승 {up:,}종, 하락 {dn:,}종으로 상승 비율은 {rate:.0f}%에 그쳤다. "
         f"52주 신고가를 낸 종목은 {nh}종이다. 거래대금은 {ik.get('turnover_txt', '-')}원이었다.")
    cards.append(card('시장 폭', 'breadth', t,
                      big=f'{up:,} / {uni:,}', big_label='오른 종목 / 전체'))
    numbers += [f"시장 폭 상승 {up:,} / 하락 {dn:,} ({uni:,}종) · 상승 비율 {rate:.0f}%",
                f"코스피 {ks.get('close'):,.0f} · {_pct(ks.get('d1'))} · 52주 고점 대비 {_pct(ks.get('from_52w_high'))}"]
    hooks.append(f"{uni:,}개 종목 중 오른 건 {up:,}개다. 52주 신고가는 {nh}개뿐이었다.")

    # ③ 히트맵 — 무엇이 끌어내렸나
    mg = ', '.join(f"{m['name']} {_pct(m.get('ret'))}" for m in mega[:3])
    sw = ', '.join(f"{s['name']} {_pct(s.get('ret'))}" for s in sec_w)
    if mg:
        t = (f"하락의 중심은 시가총액 상위주다. {mg}. "
             + (f"업종 단위로는 {sw}의 낙폭이 가장 깊다. " if sw else '')
             + "히트맵에서 면적이 큰 칸이 그대로 붉다.")
        cards.append(card('업종 히트맵', 'heatmap', t,
                          big=_pct(mega[0].get('ret')) if mega else '',
                          big_label=mega[0]['name'] if mega else '',
                          guess='미국 반도체의 하락폭이 국내 후방 산업에서 증폭되어 반영된 형태다.'))

    # ④ 반대쪽 — 반드시 초록을 보여 준다
    bits = []
    if th_t:
        bits.append('강세 테마는 ' + ', '.join(f"{x['name']} {_pct(x.get('ret'))}" for x in th_t) + '이다')
    if feat:
        _n = {1: '한', 2: '두', 3: '세', 4: '네'}.get(len(feat), str(len(feat)))
        bits.append('상한가·급등은 ' + ', '.join(f"{x['name']} {_pct(x.get('ret'))}" for x in feat)
                    + f' {_n} 종목이 나왔다')
    if bits:
        t = ('전 종목이 하락한 것은 아니다. ' + '. '.join(bits) + '. '
             '다만 이 종목들은 분석 대상이 아니며 아래 규칙에도 해당하지 않는다.')
        cards.append(card('강세 테마·특징주', 'theme', t,
                          big=_pct(th_t[0].get('ret')) if th_t else '',
                          big_label=th_t[0]['name'] if th_t else '',
                          guess='지수가 크게 빠진 날 상한가가 복수로 나왔다는 것은 자금이 시장을 떠난 것이 아니라 극히 좁은 범위로 집중됐다는 신호에 가깝다.'))

    # ⑤ 수급
    fx = [x for x in (kf.get('rule_checks') or []) if '외국인' in x]
    if cr or fx:
        t = '수급은 방향이 일치했다. ' + (re.sub(r'\*\*', '', fx[0]).replace('코스피 외국인: ', '코스피 외국인 ') + '. ' if fx else '')
        if cr.get('v'):
            t += (f"신용융자 잔고는 {cr['v'] / 1e4:,.1f}조원으로 고점 대비 {cr.get('from_peak', 0):+.1f}% 줄었다.")
            numbers.append(f"신용융자 잔고 {cr['v'] / 1e4:,.1f}조 · 고점 대비 {cr.get('from_peak', 0):+.1f}%")
        cards.append(card('수급', 'flow', t,
                          big=f"{cr['v'] / 1e4:,.1f}조" if cr.get('v') else '',
                          big_label='신용융자 잔고', guess='빌려서 산 물량의 정리가 진행 중인 구간이다.'))

    # ⑥ 내 규칙 — 이 연재의 전부
    g = ' '.join(rs['gate_lines'][:2])
    t = '규칙 기준 현재 상태는 분명하다. ' + (g + ' ' if g else '')
    if rs['last_buy']:
        t += f"실제 체결 기록상 마지막 매수는 {rs['last_buy']}이다. "
    if rs['blocked']:
        t += f"보유 종목 {len(rs['blocked'])}종이 추가 매수 조건을 충족했으나 전량 소속 시장 5주선 이탈로 보류됐다."
    _need = re.search(r'([\d.]+)% 더 올라야', ' '.join(rs['gate_lines'])) if rs['gate_lines'] else None
    cards.append(card('내 규칙', 'rule', t.strip(),
                      big=(f'+{_need.group(1)}%' if _need else '매수 중지'),
                      big_label='매수 재개까지'))
    numbers += [re.sub(r'\*\*', '', x) for x in rs['gate_lines'][:1]]
    if rs['last_buy']:
        hooks.append(f"코스피가 {_pct(ks.get('d1'))} 빠졌다. 그런데 내 매수는 {rs['last_buy']} 이후로 멈춰 있었다.")

    v19 = _j(V19)
    return dict(
        slug=f'sihwang_{d}', kind='kr', date=d,
        hook=hooks[0] if hooks else '',
        hook_candidates=hooks,
        cards=cards,
        core=[c['text'] for c in cards],
        numbers=numbers,
        takeaway='규칙이 옳았다는 뜻이 아니다. 판단 기준을 미리 고정해 두면 급락 당일에 새로 내릴 결정이 남지 않는다는 뜻이다.',
        caveat=('이 조건은 상승 전환 초기에도 똑같이 매수를 막는다. 급락 후 V자 반등 국면에서는 회복 구간을 놓친다. '
                '백테스트 기준 2019년 7월부터 2021년 7월까지 이 규칙의 연 수익률은 3.7%, 같은 기간 코스피는 24.8%였다. '
                '낙폭을 줄이는 장치와 반등을 포기하는 장치가 같다는 점은 이 규칙의 설계상 비용이다.'),
        cta='오늘 수치의 원본 화면',
        cta_url=DASH,
        images=[],
        tags=['코스피', '코스닥', '시황', '주식', 'stock_studian'],
        _v19=f"{v19.get('CAGR')}% / MDD {v19.get('MDD')}%" if v19 else None,
    )


# ── 미국 장 마감판 ────────────────────────────────────────────────────────────
def build_daily():
    rep = _j(REPORT)
    df = (rep.get('latest_daily') or {}).get('facts') or {}
    if not df:
        raise RuntimeError('latest_daily 없음')
    d = (rep.get('latest_daily') or {}).get('date') or str(date.today())
    sp, ndq, dow = _ix(df, 'S&P500'), _ix(df, '나스닥'), _ix(df, '다우')
    sox, vix, fx = _ix(df, '필라델피아 반도체'), _ix(df, 'VIX'), _ix(df, '원/달러')
    ks, kq = _ix(df, '코스피'), _ix(df, '코스닥')
    hy = df.get('hy') or {}
    rs = rule_state()
    cards, numbers = [], []

    t = (f"간밤 미국 증시는 S&P500 {_pct(sp.get('d1'))}, 나스닥 {_pct(ndq.get('d1'))}, "
         f"다우 {_pct(dow.get('d1'))}로 마감했다. 필라델피아 반도체는 {_pct(sox.get('d1'))}로 낙폭이 가장 깊다.")
    cards.append(card('글로벌 마켓', 'global', t))
    numbers += [f"S&P500 {sp.get('close'):,.0f} · {_pct(sp.get('d1'))} · 52주 고점 대비 {_pct(sp.get('from_52w_high'))}",
                f"나스닥 {ndq.get('close'):,.0f} · {_pct(ndq.get('d1'))}",
                f"필라델피아 반도체 {sox.get('close'):,.0f} · {_pct(sox.get('d1'))} · 5일 {_pct(sox.get('d5'))}"]

    t = (f"위험 지표를 같이 본다. 변동성지수 VIX {vix.get('close')}, 하루 {_pct(vix.get('d1'))}. "
         + (f"하이일드 스프레드는 {hy.get('close')}%로 {hy.get('d1'):+.0f}bp 움직였다. " if hy.get('close') else '')
         + f"원/달러는 {fx.get('close'):,.2f}원이다.")
    cards.append(card('위험 지표', 'global_risk', t))
    numbers.append(f"VIX {vix.get('close')} · {_pct(vix.get('d1'))} · 5일 {_pct(vix.get('d5'))}")

    t = (f"오늘 한국 장의 출발선이다. 직전 거래일 코스피 {ks.get('close'):,.0f}({_pct(ks.get('d1'))}), "
         f"코스닥 {kq.get('close'):,.0f}({_pct(kq.get('d1'))}). "
         f"52주 고점 대비로는 각각 {_pct(ks.get('from_52w_high'))}, {_pct(kq.get('from_52w_high'))} 자리다.")
    cards.append(card('한국 출발선', 'breadth', t))

    g = ' '.join(rs['gate_lines'][:2])
    cards.append(card('내 규칙', 'rule', ('규칙 기준 오늘 매수 가능 여부는 다음과 같다. ' + g).strip()))
    numbers += [re.sub(r'\*\*', '', x) for x in rs['gate_lines'][:2]]

    hooks = [f"간밤 필라델피아 반도체 {_pct(sox.get('d1'))}, VIX {_pct(vix.get('d1'))}. 오늘 한국 장이 받는다.",
             f"나스닥 {_pct(ndq.get('d1'))}. 코스피는 52주 고점에서 이미 {_pct(ks.get('from_52w_high'))} 내려와 있다."]
    return dict(
        slug=f'sihwang_us_{d}', kind='daily', date=d,
        hook=hooks[0], hook_candidates=hooks, cards=cards,
        core=[c['text'] for c in cards], numbers=numbers,
        takeaway='밤사이 숫자는 오늘 한국 장의 출발선이다. 방향을 맞히는 용도가 아니라 규칙이 열리는지 닫히는지를 보는 용도다.',
        caveat='간밤 미국 등락이 한국 장의 당일 방향을 결정하지는 않는다. 상관은 구간마다 크게 달라진다.',
        cta='오늘 수치의 원본 화면', cta_url=DASH, images=[],
        tags=['나스닥', 'S&P500', '증시', '시황', 'stock_studian'])


def main(argv):
    kind = (argv[0] if argv else 'kr').lower()
    doc = build_kr() if kind == 'kr' else build_daily()
    if '--print' in argv:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{doc['slug']}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
    if '--path-only' in argv:          # 배치 파일이 받아 쓰는 모드 — 경로 한 줄만
        print(p)
        return 0
    print(f"{p}  · 카드 {len(doc['cards'])}장 · 훅 후보 {len(doc['hook_candidates'])}개")
    for i, h in enumerate(doc['hook_candidates'], 1):
        print(f'  [{i}] {h}')
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv[1:]))
