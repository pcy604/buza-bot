# -*- coding: utf-8 -*-
"""부서별 KPI 계기판 — 1인 기업의 계기는 한 화면에 다 들어와야 한다.

    python kpi.py            # 콘솔 출력
    python kpi.py --md       # PM/KPI.md 로도 기록
    python kpi.py --no-net   # 네트워크 안 쓰는 항목만 (오프라인/속도)

## 왜 부서당 하나인가

방(코드 팀)은 열한 개고 모듈은 아흔아홉 개다. 거기에 각각 KPI를 붙이면
대시보드가 열한 개 생기고 아무도 안 본다 — 프로젝트를 여덟 개 벌여놓고 전부
반쯤 살려둔 것과 같은 병이 지표의 형태로 재발한다. 그래서 **부서당 정확히
하나**, 그리고 그 위에 **회사 KPI 하나**를 둔다.

## 못 재는 건 KPI 자리에 넣지 않는다

값을 못 구하면 숫자를 지어내지 않고 `계기없음`으로 남긴다. 소원을 KPI 자리에
넣는 순간 계기판 전체가 장식이 된다. 계기가 없으면 계기부터 만드는 게 일이다.

## 판정

각 KPI는 목표 대비 OK / WARN / BAD로만 판정한다. 색이 세 개를 넘으면 눈이
우선순위를 못 매긴다.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BUZA = Path(__file__).resolve().parent
DESKTOP = BUZA.parent
SCREENER = DESKTOP / 'stock_screener'
PM = DESKTOP / 'PM'

OK, WARN, BAD, NONE = 'OK', 'WARN', 'BAD', '계기없음'


def _sh(args, cwd=None, timeout=25):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ''


def _gh_token():
    out = _sh(['git', 'credential', 'fill'], cwd=str(BUZA))
    # git credential fill은 stdin이 필요해 위 호출은 보통 빈 값이다 —
    # 토큰을 못 얻으면 운영팀 KPI는 신선도만으로 낮춰 잡는다(거짓값보다 낫다).
    m = re.search(r'^password=(.+)$', out, re.M)
    return m.group(1) if m else None


# ─────────────────────────── 기획팀 ───────────────────────────
def kpi_planning():
    """계약 준수율 — 주력에 실제로 시간을 썼나.

    Q3 계약: 주력(buza-bot 봇) 60% / 유지(딥리포트) 20% / 공개활동 20%.
    커밋이 시간의 완벽한 대리지표는 아니지만, 지금 있는 유일한 객관 기록이다."""
    core = 'bot.py run.py engine.py analyzer.py ir.py card.py tg.py db.py history.py config.py report.py'.split()
    n_core = len(_sh(['git', 'log', '--since=7.days', '--oneline', '--'] + core, cwd=str(BUZA)).splitlines())
    n_ci = len(_sh(['git', 'log', '--since=7.days', '--oneline', '--', '.github/'], cwd=str(BUZA)).splitlines())
    n_deck = len(_sh(['git', 'log', '--since=7.days', '--oneline', '--', 'decks/'], cwd=str(BUZA)).splitlines())
    main = n_core + n_ci
    total = main + n_deck
    if not total:
        return dict(dept='기획팀', kpi='계약 준수율(주력 비중)', value='최근 7일 커밋 없음',
                    verdict=NONE, note='')
    pct = main / total * 100
    return dict(
        dept='기획팀', kpi='계약 준수율 — 주력 비중', target='60%',
        value=f'{pct:.0f}%', verdict=OK if pct >= 60 else (WARN if pct >= 40 else BAD),
        note=f'주력(봇+CI) {main}커밋 / 유지(딥리포트) {n_deck}커밋')


# ─────────────────────────── 개발팀 ───────────────────────────
def kpi_dev():
    """미검증 부채 — '배포됨'은 완료가 아니다. 한도 3."""
    board = PM / 'buza-bot.md'
    if not board.exists():
        return dict(dept='개발팀', kpi='미검증 부채', value='보드 없음', verdict=NONE, note='')
    txt = board.read_text(encoding='utf-8')
    m = re.search(r'### 🚀 배포됨.*?\n(.*?)(?=\n### )', txt, re.S)
    n = 0
    if m:
        # 표 본문 행(| 로 시작하고 구분선이 아닌 것)만 센다
        n = sum(1 for ln in m.group(1).splitlines()
                if ln.strip().startswith('|') and not set(ln) <= set('|- :\t'))
        n = max(0, n - 1)                      # 헤더 행 제외
    return dict(dept='개발팀', kpi='미검증 부채(배포됨 열)', target='≤3',
                value=f'{n}건', verdict=OK if n <= 3 else BAD,
                note='한도 초과 시 새 기능 시작 금지' if n > 3 else '')


# ─────────────────────────── 품질팀 ───────────────────────────
def kpi_quality():
    """발행 게이트 통과율 — 만든 리포트 중 밖에 내보낼 수 있는 비율."""
    sys.path.insert(0, str(BUZA / 'decks'))
    out = BUZA / 'decks' / 'out'
    tickers = sorted(p.name.upper() for p in out.iterdir()
                     if p.is_dir() and not p.name.startswith('_')) if out.is_dir() else []
    if not tickers:
        return dict(dept='품질팀', kpi='발행 게이트 통과율', value='렌더된 덱 없음', verdict=NONE, note='')
    passed, checked, blocked = 0, 0, []
    devnull = open(os.devnull, 'w', encoding='utf-8')
    for t in tickers:
        try:
            import importlib
            import build, check                                     # noqa: E402
            cfg = build.TICKERS.get(t) or build._auto_config(t)
            if not cfg:
                continue
            mod = importlib.import_module(cfg['data_module'])
            real, sys.stdout = sys.stdout, devnull                  # report()는 콘솔에 찍는다
            try:
                n_block = check.report(t, mod)
            finally:
                sys.stdout = real
            checked += 1
            if n_block:
                blocked.append(t)
            else:
                passed += 1
        except Exception:
            continue
    if not checked:
        return dict(dept='품질팀', kpi='발행 게이트 통과율', value='판정 불가', verdict=NONE, note='')
    pct = passed / checked * 100
    return dict(dept='품질팀', kpi='발행 게이트 통과율', target='≥80%',
                value=f'{pct:.0f}% ({passed}/{checked})',
                verdict=OK if pct >= 80 else (WARN if pct >= 50 else BAD),
                note=('차단: ' + ', '.join(blocked)) if blocked else '')


def kpi_quality_guru():
    """보조 계기 — 구루 요약 성공률. 조용히 나빠지기 쉬운 자리다."""
    f = SCREENER / 'results' / 'guru_insights.json'
    if not f.exists():
        return dict(dept='품질팀', kpi='구루 요약 성공률', value='파일 없음', verdict=NONE, note='')
    d = json.loads(f.read_text(encoding='utf-8'))
    items = d.get('items', [])
    if not items:
        return dict(dept='품질팀', kpi='구루 요약 성공률', value='0건', verdict=NONE, note='')
    fail = sum(1 for i in items if i.get('source') == 'fail')
    pct = (1 - fail / len(items)) * 100
    return dict(dept='품질팀', kpi='구루 요약 성공률', target='≥80%',
                value=f'{pct:.0f}%', verdict=OK if pct >= 80 else (WARN if pct >= 60 else BAD),
                note=f'실패 {fail}/{len(items)} · 갱신 {d.get("updated","?")[:10]}')


# ─────────────────────────── 운영팀 ───────────────────────────
def kpi_ops(net=True):
    """파이프라인 신선도 — 데이터가 언제 것인가. 네트워크 없이도 잴 수 있다."""
    rdir = SCREENER / 'results'
    if not rdir.is_dir():
        return dict(dept='운영팀', kpi='데이터 신선도', value='results 없음', verdict=NONE, note='')
    newest = max((p.stat().st_mtime for p in rdir.iterdir() if p.is_file()), default=0)
    hours = (time.time() - newest) / 3600
    return dict(dept='운영팀', kpi='데이터 신선도', target='≤24h',
                value=f'{hours:.0f}시간 전',
                verdict=OK if hours <= 24 else (WARN if hours <= 72 else BAD),
                note=time.strftime('%m-%d %H:%M', time.localtime(newest)))


# ─────────────────────────── 마케팅팀 ───────────────────────────
def _tg(token, api, **params):
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f'https://api.telegram.org/bot{token}/{api}?{q}', timeout=15) as r:
        return json.load(r).get('result')


def kpi_marketing(net=True):
    """외부 도달 인원 — 나 아닌 사람 몇 명에게 닿아 있나. 회사 KPI의 뿌리."""
    if not net:
        return dict(dept='마케팅팀', kpi='외부 도달 인원', value='(--no-net)', verdict=NONE, note='')
    reach, parts = 0, []

    # 두 레포 모두 최상위에 `config.py`를 갖고 있어 sys.path만 바꾸면 먼저 임포트된
    # 쪽이 캐시에 남아 다른 레포가 그걸 집어간다(실제로 db가 스크리너 config를
    # 집어가 조회에 실패했다). 봇 쪽을 먼저 끝내고, 스크리너를 볼 땐 캐시를 비운다.

    # ① 봇 DM 사용자 — buza-bot의 config가 필요하다
    try:
        sys.path.insert(0, str(BUZA))
        import db                                                    # noqa: E402
        n_dm = max(0, len(db.all_users()) - 1)                       # 소유자 제외
        reach += n_dm
        parts.append(f'봇DM {n_dm}명')
    except Exception as e:
        parts.append(f'봇DM 조회실패({str(e)[:24]})')

    # ② 공개 채널 구독자 — 스크리너의 config가 필요하다
    saved = {k: sys.modules.pop(k) for k in ('config',) if k in sys.modules}
    try:
        sys.path.insert(0, str(SCREENER))
        import config as scfg                                        # noqa: E402
        chat = scfg.GURU_BROADCAST_CHAT or scfg.TELEGRAM_CHAT_ID
        n = _tg(scfg.TELEGRAM_TOKEN, 'getChatMemberCount', chat_id=chat)
        if isinstance(n, int):
            ext = max(0, n - 1)                                      # 본인 제외
            reach += ext
            parts.append(f'채널 {ext}명')
    except Exception as e:
        parts.append(f'채널 조회실패({str(e)[:24]})')
    finally:
        sys.modules.pop('config', None)
        sys.modules.update(saved)
        if str(SCREENER) in sys.path:
            sys.path.remove(str(SCREENER))

    # 목표는 "3명이 7일 연속 사용"인데 연속성은 아직 못 잰다(cmd_log가 08-08부터
    # 살아났으니 일주일 뒤부터 가능). 도달 인원만으로 OK를 주면 목표를 이미
    # 달성한 것처럼 보이므로, 인원이 차도 WARN에서 멈춘다.
    return dict(dept='마케팅팀', kpi='외부 도달 인원', target='3명 7일연속',
                value=f'{reach}명', verdict=BAD if reach == 0 else WARN,
                note=' · '.join(parts) + ' · 연속사용은 계기없음(08-15부터 측정가능)')


# ─────────────────────────── 출력 ───────────────────────────
# ──────────────────── 아직 사람이 없는 자리 ────────────────────
# 계기를 못 만든 게 아니라 **부서가 없어서** 잴 것이 없는 자리들이다. 빈 줄로
# 남겨두는 편이 표에서 빼는 것보다 낫다 — 빼면 없다는 사실 자체가 안 보인다.

def kpi_voice():
    """사용자 대변인 — 외부 피드백 건수/월.

    통로: /voc(자유 의견, voc_log.json) + 뉴스 요약 👍/👎(news_log). 2026-10-21 /voc 추가로 잴 수 있게 됐다.
    소유자 본인 건은 세지 않는다 — 본인 테스트가 KPI 를 부풀리면 '외부 사용자 0명'(PM/SALES.md)을 가린다."""
    try:
        import voc
        c = voc.month_counts()
    except Exception:
        c = None
    if c is None:
        return dict(dept='사용자대변인', kpi='외부 피드백 건수/월', target='≥3건',
                    value='—', verdict=NONE, note='voc_log 읽기 실패')
    n = c['external']
    return dict(dept='사용자대변인', kpi='외부 피드백 건수/월', target='≥3건',
                value=f'{n}건', verdict=(OK if n >= 3 else BAD),
                note=f"본인 {c['owner']}건 별도 · 열린 VOC {c['open']}건 (/voc list)")


def kpi_legal():
    """법무 — 미해소 규제 리스크 건수.

    PM/LEGAL.md에 등급이 매겨진 목록이 있으면 센다. 없으면 계기없음이다.
    유사투자자문업·저작권·재직 중 공개활동 셋 다 실재하는데 검토 자리가 없다."""
    f = PM / 'LEGAL.md'
    if not f.exists():
        return dict(dept='법무', kpi='미해소 규제 리스크', target='0건',
                    value='—', verdict=NONE,
                    note='PM/LEGAL.md 없음 — 리스크 목록 자체가 아직 없다')
    txt = f.read_text(encoding='utf-8')
    open_n = len(re.findall(r'^\s*[-*]\s*\[ \]', txt, re.M))
    return dict(dept='법무', kpi='미해소 규제 리스크', target='0건',
                value=f'{open_n}건', verdict=OK if open_n == 0 else BAD,
                note='PM/LEGAL.md')


def collect(net=True):
    rows = [kpi_planning(), kpi_dev(), kpi_quality(), kpi_quality_guru(),
            kpi_ops(net), kpi_marketing(net), kpi_voice(), kpi_legal()]
    return rows


def render(rows):
    icon = {OK: '○', WARN: '△', BAD: '●', NONE: '?'}
    w = max(len(r['dept']) for r in rows)
    lines = [f'{"부서":<{w}}  {"KPI":<22} {"현재":<18} {"목표":<12} 비고', '─' * 96]
    for r in rows:
        lines.append(f'{icon[r["verdict"]]} {r["dept"]:<{w-1}} {r["kpi"]:<22} '
                     f'{r["value"]:<18} {r.get("target",""):<12} {r.get("note","")}')
    bad = [r for r in rows if r['verdict'] == BAD]
    none = [r for r in rows if r['verdict'] == NONE]
    lines += ['─' * 96,
              f'● 나쁨 {len(bad)}  △ 주의 {sum(1 for r in rows if r["verdict"]==WARN)}  '
              f'○ 양호 {sum(1 for r in rows if r["verdict"]==OK)}  ? 계기없음 {len(none)}']
    if bad:
        lines.append('가장 먼저 볼 것: ' + bad[0]['dept'] + ' — ' + bad[0]['kpi'])
    return '\n'.join(lines)


def write_md(rows):
    import datetime
    icon = {OK: '🟢', WARN: '🟡', BAD: '🔴', NONE: '⚪'}
    md = [f'# KPI 계기판\n', f'_{datetime.datetime.now():%Y-%m-%d %H:%M} 자동 생성 — `python buza-bot/kpi.py --md`_\n',
          '| | 부서 | KPI | 현재 | 목표 | 비고 |', '|---|---|---|---|---|---|']
    for r in rows:
        md.append(f'| {icon[r["verdict"]]} | {r["dept"]} | {r["kpi"]} | **{r["value"]}** | '
                  f'{r.get("target","—")} | {r.get("note","")} |')
    md.append('\n> 부서당 KPI는 하나다. 못 재는 것은 숫자를 지어내지 않고 ⚪ 계기없음으로 둔다.')
    PM.mkdir(exist_ok=True)
    (PM / 'KPI.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    return PM / 'KPI.md'


def main():
    net = '--no-net' not in sys.argv
    rows = collect(net)
    print(render(rows))
    if '--md' in sys.argv:
        print(f'\n기록: {write_md(rows)}')


if __name__ == '__main__':
    main()
