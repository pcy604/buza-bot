"""요약 카드 렌더 — Pillow로 직접 그리기 (브라우저 헤드리스 비의존).

이 PC는 회사 보안정책으로 Edge 헤드리스 자동화가 막혀있어(2026-07-18 확인,
--dump-dom조차 무응답) 브라우저 스크린샷 방식을 버리고 폰트 렌더링으로 전환.
"""
import functools
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W = 1000
PAD = 36
CANVAS_H = 4000  # 넉넉히 그린 뒤 실제 콘텐츠 높이로 크롭

# ── 라이트 테마 ── /report 13장 포토카드(report.py)와 **같은 값**을 쓴다.
#
# 예전엔 여기만 어두운 팔레트였다. 그래서 같은 봇이 보내는 카드인데 /ir·/dd 는
# 검은 바탕, /report 는 흰 바탕이라 두 제품처럼 보였다(2026-09-17 지적).
#
# ⚠️ report.py 가 card.py 를 임포트하므로(순환) 여기서 `from report import ...` 로
#    당겨올 수 없다. 값을 바꿀 땐 report.py 의 BG/SURFACE/LINE/INK/INK_DIM/
#    INK_FAINT/ACCENT/UP/DN/FLAT/SEGMENT_COLORS 와 **함께** 고쳐야 한다.
BG = (0xff, 0xff, 0xff)          # report.BG
LINE = (0xe2, 0xe4, 0xe8)        # report.LINE
TICK = (0xb8, 0x6a, 0x00)        # report.ACCENT — 티커·섹션 제목
CO = (0x54, 0x5b, 0x64)          # report.INK_DIM — 회사명
DOC = (0x96, 0x9d, 0xa6)         # report.INK_FAINT — 공시 메타
ONE = (0x1a, 0x1d, 0x22)         # report.INK — 한 줄 요약(어두운 바탕에선 옅은 금색이었다)
BODY = (0x54, 0x5b, 0x64)        # report.INK_DIM
MUTED = (0x96, 0x9d, 0xa6)       # report.INK_FAINT
KPI_BG = (0xf3, 0xf4, 0xf6)      # report.SURFACE
FG = (0x1a, 0x1d, 0x22)          # report.INK
INTERP = (0xb8, 0x6a, 0x00)      # report.ACCENT — "해석:" 항목을 사실과 시각적으로 구분
DIR_COLOR = {'up': (0x1a, 0x8a, 0x4c),    # report.UP
             'dn': (0xc4, 0x38, 0x2c),    # report.DN
             'flat': (0x7c, 0x83, 0x8c)}  # report.FLAT
SEGMENT_COLORS = [(0x2f, 0x6e, 0xa8), (0x86, 0x4f, 0xa8), (0x1f, 0x8a, 0x82),
                  (0xb8, 0x4a, 0x71), (0x8a, 0x84, 0x2c)]

# (regular, bold) 후보 경로 — 로컬 Windows(Malgun Gothic)와 GH Actions Ubuntu(fonts-nanum
# apt 패키지, run.yml에서 설치)를 둘 다 지원. 존재하는 첫 쌍을 사용.
FONT_CANDIDATES = [
    (r'C:\Windows\Fonts\malgun.ttf', r'C:\Windows\Fonts\malgunbd.ttf'),
    # 2026-08-22: 러너에서 apt 대신 캐시된 .fonts/ 를 먼저 본다(apt 20초 → 캐시 2초).
    # 캐시가 미스나면 run.yml 이 apt 로 설치한 뒤 여기로 복사하므로 아래 경로도 남긴다.
    ('.fonts/NanumGothic.ttf', '.fonts/NanumGothicBold.ttf'),
    ('/usr/share/fonts/truetype/nanum/NanumGothic.ttf', '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
    # 2026-11-13: 저장소에 든 Pretendard(한글 포함) — apt 없는 환경(Claude 작업 환경·새 러너)에서도 렌더되게 마지막 후보
    (str(Path(__file__).parent / 'fonts' / 'Pretendard-Regular.otf'), str(Path(__file__).parent / 'fonts' / 'Pretendard-Bold.otf')),
]
SECTIONS = [('current', '현재 상태'), ('outlook', '향후 전망'), ('tam', 'TAM · 시장'), ('notes', '주요사항 · 리스크')]


def _resolve_fonts():
    for reg, bold in FONT_CANDIDATES:
        if Path(reg).exists() and Path(bold).exists():
            return reg, bold
    raise FileNotFoundError(
        '한글 폰트를 찾을 수 없음 — Windows는 Malgun Gothic 기본 내장, '
        'Linux는 `apt-get install -y fonts-nanum` 필요')


_FONT_REG, _FONT_BOLD = _resolve_fonts()


@functools.lru_cache(maxsize=None)
def _font(bold: bool, size: int):
    return ImageFont.truetype(_FONT_BOLD if bold else _FONT_REG, size)


def _s(x):
    return str(x or '')


def _wrap(text, font, max_width):
    """줄바꿈 문자(\\n)는 강제 개행으로 취급 — 예전엔 그냥 한 단어에 눌러붙어(공백이
    없으니 split(' ')이 못 가름) 화면에 문장이 다닥다닥 붙은 벽처럼 보였다. 여러
    문단을 나눠 쓰고 싶은 요약문(종합평가 등)에서 실제로 필요해졌다."""
    lines = []
    for para in _s(text).split('\n'):
        words = para.split(' ')
        cur = ''
        for w in words:
            trial = f'{cur} {w}'.strip()
            if not cur or font.getlength(trial) <= max_width:
                cur = trial
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines or ['']


def _draw_wrapped(draw, x, y, text, font, color, max_width, line_h=None):
    line_h = line_h or int(font.size * 1.45)
    for line in _wrap(text, font, max_width):
        draw.text((x, y), line, font=font, fill=color)
        y += line_h
    return y


class _Card:
    def __init__(self, data: dict):
        self.c = data
        self.im = Image.new('RGB', (W, CANVAS_H), BG)
        self.d = ImageDraw.Draw(self.im)
        self.y = 0
        self.cw = W - 2 * PAD  # 콘텐츠 폭

    def _hline(self, y, color=LINE):
        self.d.line([(0, y), (W, y)], fill=color, width=1)

    def header(self):
        c = self.c
        self.y += 28
        f_tick = _font(True, 32)
        self.d.text((PAD, self.y), _s(c.get('ticker')), font=f_tick, fill=TICK)
        self.y += 40
        f_co = _font(False, 18)
        self.d.text((PAD, self.y), _s(c.get('company')), font=f_co, fill=CO)
        self.y += 26
        f_doc = _font(False, 14)
        meta = ' · '.join(x for x in (c.get('form'), c.get('date'), c.get('doc_title')) if x)
        self.y = _draw_wrapped(self.d, PAD, self.y, meta, f_doc, DOC, self.cw, line_h=20)
        self.y += 14
        self._hline(self.y)

    def one_liner(self):
        self.y += 18
        top = self.y
        f = _font(True, 19)
        text_y = _draw_wrapped(self.d, PAD + 14, self.y, _s(self.c.get('one_liner')), f, ONE, self.cw - 14, line_h=27)
        self.d.rectangle([PAD - 10, top + 3, PAD - 6, text_y - 10], fill=TICK)
        self.y = text_y + 16
        self._hline(self.y)

    def profile(self):
        p = self.c.get('profile')
        if not p:
            return
        self.y += 18
        self.d.text((PAD, self.y), '회사 개요', font=_font(True, 15), fill=TICK)
        self.y += 26
        f_body = _font(False, 16)
        self.y = _draw_wrapped(self.d, PAD, self.y, p.get('business'), f_body, BODY, self.cw, line_h=24) + 4
        hq = _s(p.get('founded_hq'))
        if hq:
            self.d.text((PAD, self.y), hq, font=_font(False, 13), fill=DOC)
            self.y += 22

        segs = [s for s in (p.get('segments') or []) if s.get('name')]
        segs_pct = [s for s in segs if isinstance(s.get('pct'), (int, float))]
        if segs_pct:
            self.y += 10
            bar_h = 22
            total = sum(s['pct'] for s in segs_pct) or 1
            x = PAD
            for i, s in enumerate(segs_pct):
                w = self.cw * (s['pct'] / total)
                self.d.rectangle([x, self.y, x + w, self.y + bar_h], fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
                x += w
            self.y += bar_h + 12
            f_leg = _font(False, 13)
            lx, ly = PAD, self.y
            for i, s in enumerate(segs_pct):
                label = f'{s["name"]} {s["pct"]:.0f}%'
                lw = f_leg.getlength(label) + 34
                if lx + lw > PAD + self.cw and lx > PAD:
                    lx, ly = PAD, ly + 22
                self.d.ellipse([lx, ly + 3, lx + 10, ly + 13], fill=SEGMENT_COLORS[i % len(SEGMENT_COLORS)])
                self.d.text((lx + 16, ly), label, font=f_leg, fill=CO)
                lx += lw
            self.y = ly + 26
        elif segs:
            names = ', '.join(s['name'] for s in segs)
            self.y = _draw_wrapped(self.d, PAD, self.y, f'사업부문: {names}', _font(False, 14), DOC,
                                   self.cw, line_h=20) + 10
        self.y += 8
        self._hline(self.y)

    def kpis(self):
        items = (self.c.get('kpis') or [])[:6]
        if not items:
            return
        cols = 3
        rows = (len(items) + cols - 1) // cols
        cell_w = W // cols
        cell_h = 78
        top = self.y
        self.d.rectangle([0, top, W, top + rows * cell_h], fill=KPI_BG)
        for i, k in enumerate(items):
            col, row = i % cols, i // cols
            x0, y0 = col * cell_w, top + row * cell_h
            if col:
                self.d.line([(x0, y0), (x0, y0 + cell_h)], fill=LINE, width=1)
            if row:
                self.d.line([(x0, y0), (x0 + cell_w, y0)], fill=LINE, width=1)
            px, py = x0 + 20, y0 + 12
            self.d.text((px, py), _s(k.get('label')), font=_font(False, 13), fill=DOC)
            self.d.text((px, py + 18), _s(k.get('value')), font=_font(True, 24), fill=FG)
            self.d.text((px, py + 48), _s(k.get('delta')), font=_font(False, 13),
                        fill=DIR_COLOR.get(k.get('dir'), FG))
        self.y = top + rows * cell_h
        self._hline(self.y)

    def trend(self):
        tr = self.c.get('trend')
        if not tr or not tr.get('periods'):
            return
        periods = tr['periods']
        rows = tr.get('rows', [])
        self.y += 20
        self.d.text((PAD, self.y), '분기 추이', font=_font(True, 15), fill=TICK)
        self.y += 28
        label_w = 110
        col_w = (self.cw - label_w) / max(len(periods), 1)
        f_h = _font(False, 13)
        f_v = _font(True, 14)
        row_h = 30
        top = self.y
        for i, p in enumerate(periods):
            cx = PAD + label_w + i * col_w + col_w
            tw = f_h.getlength(p)
            self.d.text((cx - tw, top), p, font=f_h, fill=DOC)
        self.y = top + row_h
        self._hline(self.y, (0x23, 0x2b, 0x36))
        for row in rows:
            ry = self.y + 8
            self.d.text((PAD, ry), _s(row.get('label')), font=_font(True, 14), fill=CO)
            for i, v in enumerate(row.get('values', [])):
                cx = PAD + label_w + i * col_w + col_w
                tw = f_v.getlength(_s(v))
                self.d.text((cx - tw, ry), _s(v), font=f_v, fill=FG)
            self.y += row_h
            self._hline(self.y, (0x23, 0x2b, 0x36))
        self.y += 4

    def sections(self):
        for key, label in (self.c.get('_sections') or SECTIONS):
            items = (self.c.get(key) or [])[:4]
            if not items:
                continue
            self.y += 18
            self.d.text((PAD, self.y), label, font=_font(True, 15), fill=TICK)
            self.y += 26
            f_body = _font(False, 16)
            f_tag = _font(True, 16)
            for it in items:
                it = _s(it)
                is_interp = it.startswith('해석:') or it.startswith('해석 :')
                color = INTERP if is_interp else BODY
                self.d.ellipse([PAD + 2, self.y + 8, PAD + 6, self.y + 12], fill=color)
                if is_interp:
                    tag = '해석'
                    rest = it.split(':', 1)[1].strip() if ':' in it else it
                    self.d.text((PAD + 16, self.y), tag, font=f_tag, fill=INTERP)
                    tag_w = f_tag.getlength(tag) + 6
                    self.y = _draw_wrapped(self.d, PAD + 16 + tag_w, self.y, rest, f_body, BODY,
                                           self.cw - 16 - tag_w, line_h=24) + 4
                else:
                    self.y = _draw_wrapped(self.d, PAD + 16, self.y, it, f_body, BODY, self.cw - 16, line_h=24) + 4

    def news(self):
        f_meta = _font(False, 13)
        f_title = _font(False, 16)
        # 요약본(news_digest)이 있으면 그걸 쓴다. 없을 때만 정제된 원본 헤드라인으로
        # 떨어진다 — 뉴스 칸을 비우는 것보다 제목이라도 보이는 게 낫다.
        digest = (self.c.get('news_digest') or [])[:5]
        if digest:
            self.y += 18
            self.d.text((PAD, self.y), '이번 달 알아야 할 뉴스', font=_font(True, 15), fill=TICK)
            self.y += 26
            for n in digest:
                if n.get('date'):
                    self.d.text((PAD, self.y), n['date'], font=f_meta, fill=DOC)
                    self.y += 18
                self.y = _draw_wrapped(self.d, PAD, self.y, n.get('headline'),
                                       f_title, FG, self.cw, line_h=22) + 2
                if n.get('so_what'):
                    # 사실(headline)과 해석(so_what)을 색으로 구분한다 — INTERP 는
                    # 카드 다른 곳에서 "해석:" 항목에 쓰는 것과 같은 색이다.
                    self.y = _draw_wrapped(self.d, PAD + 12, self.y, n['so_what'],
                                           f_meta, INTERP, self.cw - 12, line_h=19) + 8
            return
        items = (self.c.get('news') or [])[:6]
        if not items:
            return
        self.y += 18
        self.d.text((PAD, self.y), '최근 뉴스', font=_font(True, 15), fill=TICK)
        self.y += 26
        for n in items:
            meta = f'{n.get("date","")} · {n.get("source","")}'
            if n.get('echo', 1) > 1:
                meta += f' 외 {n["echo"] - 1}곳'
            self.d.text((PAD, self.y), meta, font=f_meta, fill=DOC)
            self.y += 18
            self.y = _draw_wrapped(self.d, PAD, self.y, n.get('title'), f_title, BODY, self.cw, line_h=22) + 6

    def footer(self):
        self.y += 10
        self._hline(self.y)
        self.y += 14
        # ⚠️ 출처 표기는 실제로 카드에 들어간 것만 적는다. 뉴스 섹션이 붙은 카드에
        #    'SEC EDGAR 공시 원문'만 적어두면 언론보도를 공시로 오인하게 만든다.
        src = 'SEC EDGAR 공시 원문'
        if self.c.get('news_digest') or self.c.get('news'):
            src += ' + 언론보도(구글 뉴스)'
        self.d.text((PAD, self.y), f'부자알람 IR 다이제스트 · 출처: {src} · 투자 조언 아님',
                    font=_font(False, 13), fill=DOC)
        self.y += 22

    def save(self, path: str):
        self.im.crop((0, 0, W, self.y)).save(path)


def render_png(card: dict, out_path: str) -> str:
    cd = _Card(card)
    cd.header()
    cd.one_liner()
    cd.profile()
    cd.kpis()
    cd.trend()
    cd.sections()
    cd.news()
    cd.footer()
    cd.save(out_path)
    return out_path
