# -*- coding: utf-8 -*-
"""부자알람 소개 포토카드 — 처음 온 사람이 "이게 뭐 하는 채널인지" 알게 하는 한 장.

## 왜 별도 파일인가

`card.render_png` 은 IR 다이제스트 전용이다(header→one_liner→profile→kpis→trend→
sections→news→footer 가 고정 순서로 박혀 있다). 소개 카드는 구조가 완전히 달라서
거기 얹으면 서로를 망친다. 대신 **팔레트와 폰트는 card.py 것을 그대로 가져다 쓴다** —
제품과 따로 노는 이미지가 되면 안 되기 때문이다.

## 내용은 코드에서 뽑았지 상상하지 않았다

명령 목록은 `bot.py` WELCOME(도움말)과 같아야 한다 — 2026-11-15 현행화(/dd 은퇴 · /ir 은 /report 로 통합 예정이라 제외 ·
/market · /dashboard · /person 추가 · 리포트 16장). 문체는 사이트 설명서와 같은 명세 문체(구어체 금지).
없는 기능을 그린 소개 카드는 처음 온 사람을 속이는 것이다.

## 고치는 법

`SPEC` 딕셔너리만 고치면 된다. 레이아웃은 아래 흐름이 알아서 재배치한다.
정사각(1080×1080)인 이유는 텔레그램 채널 고정 이미지와 인스타그램에 그대로 쓰기 위함.

    python onboarding_card.py [출력경로]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import card as _c   # 팔레트·폰트·줄바꿈을 재사용한다

W = H = 1080
PAD = 64

BG = _c.BG
GOLD = _c.TICK
FG = _c.FG
BODY = _c.BODY
MUTED = _c.DOC
LINE = _c.LINE
CHIP_BG = _c.KPI_BG

SPEC = {
    'name': '부자알람',
    'handle': '@buza_alarm_bot',
    # 한 줄 = 무엇을 하는 봇인가(명세 문체).
    'purpose': '공시 · 시황 · 유튜브를 요약해 텔레그램으로 발송하는 투자 정보 알림 봇.\n'
               '종목 입력은 티커 · 6자리 코드 · 한글 종목명 지원. 미국 · 한국 종목.',
    'blocks': [
        {'title': '시황 · 종목 분석',
         'desc': '장 마감 시황 카드(한국 15:50 이후 · 미국 익일 오전)와 종목 분석 결론 카드. 자동 수신은 /market on.',
         'cmds': ['/market', '/dashboard 삼성전자']},
        {'title': '공시 · 뉴스 감시',
         'desc': '감시 종목의 공시는 실시간, 주요 뉴스는 08·20시 요약 발송. 해당 사항이 없으면 미발송. 한국 종목은 수급 포함.',
         'cmds': ['/watch <종목>', '/watchlist', '/unwatch <종목>']},
        {'title': '심층 리포트',
         'desc': '기업 개요 · 사업부문 · 재무 추이 · 밸류에이션 · 경쟁사 · 내부자 지분. 16장 카드 구성, 미국 종목.',
         'cmds': ['/report TSLA']},
        {'title': '유튜브 요약',
         'desc': '영상 링크 입력 시 요약. 채널 · 인물 등록 시 신규 영상 자동 요약.',
         'cmds': ['/add <채널URL>', '/person <이름>', '/list']},
    ],
    # 하단 = 첫 동작. 블록이 늘어 자리가 모자라면 render 가 자동 생략한다.
    'cta_label': '시작',
    'cta_main': '/start — 명령어 목록 수신',
    'cta_sub': '유튜브 링크는 명령어 없이 입력해도 요약. 투자 권유가 아닌 정보 요약.',
    'footer_left': '/help 전체 명령어 · /terms 이용 안내',
    'footer_right': 'stock_studian',
}


def _text(d, x, y, s, *, bold=False, size=20, fill=BODY):
    d.text((x, y), s, font=_c._font(bold, size), fill=fill)


def _block(d, y, b, x=PAD, w=W - PAD * 2):
    """기능 블록 하나. 반환값은 다음 블록이 시작할 y.

    ⚠️ 아이콘에 이모지를 쓰지 않는다. Malgun Gothic(로컬)에도 NanumGothic(러너)에도
    이모지 글리프가 없어서 두부(□)로 그려진다. 컬러 이모지 폰트를 끌어오면 로컬과
    러너가 서로 다른 그림을 내므로, 폰트에 의존하지 않는 도형(금색 세로 바)으로 쓴다.
    블록이 순서를 뜻하지 않으므로 번호(01·02·03)도 쓰지 않는다.
    """
    tx = x + 26
    top = y
    _text(d, tx, y, b['title'], bold=True, size=30, fill=FG)
    y += 46
    y = _c._draw_wrapped(d, tx, y, b['desc'], _c._font(False, 20), BODY,
                         w - 26, line_h=31)
    y += 12
    cx, f = tx, _c._font(True, 19)
    for cmd in b['cmds']:
        tw = int(d.textlength(cmd, font=f))
        if cx + tw + 26 > x + w:
            cx, y = tx, y + 44
        d.rounded_rectangle([cx, y, cx + tw + 24, y + 35], radius=10, fill=CHIP_BG)
        d.text((cx + 12, y + 7), cmd, font=f, fill=GOLD)
        cx += tw + 34
    y += 35
    d.rounded_rectangle([x, top + 4, x + 5, y - 4], radius=3, fill=GOLD)
    return y + 46


def render(out_path='buza_onboarding.png'):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # 상단 금색 띠 — 제품 카드(TICK 색)와 같은 계열로 묶는다
    d.rectangle([0, 0, W, 6], fill=GOLD)

    y = PAD + 10
    _text(d, PAD, y, SPEC['name'], bold=True, size=52, fill=FG)
    nw = int(d.textlength(SPEC['name'], font=_c._font(True, 52)))
    _text(d, PAD + nw + 16, y + 26, SPEC['handle'], size=20, fill=GOLD)
    y += 76

    for line in SPEC['purpose'].split('\n'):
        y = _c._draw_wrapped(d, PAD, y, line, _c._font(False, 22), MUTED,
                             W - PAD * 2, line_h=33)
    y += 22
    d.line([PAD, y, W - PAD, y], fill=LINE, width=2)
    y += 30

    for b in SPEC['blocks']:
        y = _block(d, y, b)

    # ── 행동 유도 ── 남는 아래 공간을 채우는 게 아니라, 첫 동작을 알려주는 자리다.
    fy = H - PAD - 24
    cy0, cy1 = y - 4, fy - 40
    if cy1 - cy0 >= 112:                      # 자리가 있을 때만 (블록이 늘면 자동 생략)
        d.rounded_rectangle([PAD, cy0, W - PAD, cy1], radius=16, fill=CHIP_BG)
        d.rounded_rectangle([PAD, cy0, PAD + 5, cy1], radius=3, fill=GOLD)
        ty = cy0 + 20                        # 위 정렬 — 가운데 정렬은 마지막 줄이 바닥에 붙는다
        _text(d, PAD + 30, ty, SPEC['cta_label'], size=17, fill=GOLD)
        _text(d, PAD + 30, ty + 24, SPEC['cta_main'], bold=True, size=31, fill=FG)
        _c._draw_wrapped(d, PAD + 30, ty + 66, SPEC['cta_sub'],
                         _c._font(False, 17), MUTED, W - PAD * 2 - 60, line_h=25)

    d.line([PAD, fy - 22, W - PAD, fy - 22], fill=LINE, width=1)
    _text(d, PAD, fy, SPEC['footer_left'], size=18, fill=MUTED)
    rw = int(d.textlength(SPEC['footer_right'], font=_c._font(True, 18)))
    _text(d, W - PAD - rw, fy, SPEC['footer_right'], bold=True, size=18, fill=GOLD)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'buza_onboarding.png'
    print('저장:', render(out))
