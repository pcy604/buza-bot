# -*- coding: utf-8 -*-
"""주간 소집 브리핑 — 부서를 사람이 기억해서 부르지 않아도 되게.

    python brief.py            # 텍스트만 출력(발송 안 함)
    python brief.py --send     # 텔레그램 발송
    run.py가 7일마다 자동 발송

## 왜 만들었나

감시 로직은 이미 다 있었다. `check.report_all()`은 전 종목의 차단·발행대기·재렌더
필요를 한 화면에 뽑고, `kpi.py`는 부서별 계기를 잰다. 문제는 **둘 다 사람이 기억해서
쳐야 돈다**는 것이었다. 게이트는 발행할 때만 돌기 때문에, 아무도 발행하지 않는 주에는
아무도 상태를 안 본다 — 데이터 소스가 바뀌어 예전에 통과한 종목이 깨져도 모른다.

그래서 새 감시를 만들지 않고 **이미 있는 감시에 주기와 출구를 달았다.**

## 무시당하지 않게 만드는 법

주기 알림의 기본 운명은 무시다. 매주 같은 문구가 오면 3주 안에 안 읽게 된다.
그래서 이 브리핑은 두 가지를 지킨다:

1. **실제 수치만 싣는다** — "PM 돌릴 시간입니다"가 아니라 "차단 3종, 발행대기 5종".
2. **소집 대상이 매주 다르다** — 고정 목록이 아니라 상태에서 유도한다. 차단이 있으면
   품질팀을, 발행대기가 오래됐으면 마케팅을, 분기말이면 이사회를 부른다. 부를 이유가
   없는 부서는 아예 안 적는다.

## 한계 — 러너에서는 렌더 상태를 못 본다

`decks/out/`은 gitignore라 GitHub Actions 컨테이너엔 PNG가 없다. 그래서 러너 실행분은
**차단·발행 여부만** 판정하고 "렌더 필요/재렌더 필요"는 로컬 실행에서만 나온다.
없는 것을 아는 척하지 않으려고 이 차이를 브리핑에 명시한다.
"""
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'decks'))

# Q3 계약 채점일 — 이사회 소집 판단에 쓴다([[project-q3-2026-contract]])
QUARTER_END = datetime(2026, 9, 30, tzinfo=timezone.utc)   # 옛 고정값(참고) — 아래 _quarter_end() 를 쓴다


def _quarter_end(now=None):
    """이번 분기 마지막 날. 2026-11-12: 고정 9-30 이 지나 '-44일 전 채점'을 매주 보내고 있었다."""
    now = now or datetime.now(timezone.utc)
    q_end_month = ((now.month - 1) // 3 + 1) * 3
    nxt = datetime(now.year + (q_end_month == 12), q_end_month % 12 + 1, 1, tzinfo=timezone.utc)
    return nxt - timedelta(days=1)


def _sh(*args, timeout=20):
    try:
        r = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ''


# ─────────────────────────── 회귀 감시 ───────────────────────────
def deck_state():
    """전 종목 데이터 모듈을 다시 검사한다 — 발행하지 않는 주에도 돈다.

    `check.report_all()`과 같은 판정을 쓰되 콘솔 출력 대신 구조화해서 돌려준다.
    렌더 상태(out/)는 러너에 없으므로 여기서 보지 않는다 — 차단과 발행 여부만.
    """
    try:
        import check
    except Exception as e:
        return {'error': f'check 임포트 실패: {e}'}

    published = check._published()
    blocked, waiting, broken = [], [], []
    total = 0
    for t in check._all_tickers():
        total += 1
        # ⚠️ 모듈 해석은 check.module_for 하나만 쓴다. 예전엔 여기서 자체 규칙
        # (autogen._module_name → '{ticker}_data')을 돌렸는데, 그 규칙은 한국 티커에서
        # '005930.KS' → '005930.ks_data' 를 만들어 반드시 죽는다. 그래서 멀쩡한
        # 삼성전자·에코프로비엠이 주간 브리핑에 '임포트 실패'로 떴다(2026-09-08 실측:
        # module_for 로는 둘 다 정상 임포트되고 차단 0건).
        try:
            mod = check.module_for(t)
        except Exception:
            mod = None
        if mod is None:
            broken.append(t)
            continue
        rows = check.audit(mod, t)
        n_block = sum(1 for r in rows if r[0] == check.BLOCK)
        if n_block:
            items = sorted({r[1] for r in rows if r[0] == check.BLOCK})
            blocked.append((t, n_block, items[:3]))
        elif t not in published:
            waiting.append(t)
    # 2026-11-12 차니 "옛날에 안 나간 걸 계속 문제처럼 보낸다" — /report 는 이제 요청 때 러너에서 즉석 렌더(deck_live)라
    #   '데이터는 있는데 아직 아무도 요청 안 한 종목'은 밀린 일이 아니라 준비 완료다. 문제는 차단·임포트 실패뿐.
    #   대신 실제 발송 이력(deck_files.json 의 published 날짜)으로 최근 7일 발송을 보여 준다.
    recent = []
    try:
        import deck_store
        cut = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')
        for tk, info in (deck_store._load() or {}).items():
            if str(info.get('published') or '') >= cut:
                recent.append((str(info.get('published')), tk))
    except Exception:
        pass
    return {'total': total, 'blocked': blocked, 'ready': waiting, 'waiting': waiting,
            'broken': broken, 'published': len(published), 'recent': sorted(recent, reverse=True)}


# ─────────────────────────── 저장소 상태 ───────────────────────────
def repo_state():
    """미커밋 파일 수와 마지막 사람 커밋 이후 경과일.

    미커밋이 쌓이면 daily-refresh 계열 자동 커밋이 로컬 변경을 덮을 위험이 있고,
    실제로 07-27·08-03에 22개까지 밀린 전례가 있다."""
    dirty = [ln for ln in _sh('git', 'status', '--porcelain').splitlines() if ln.strip()]
    last = _sh('git', 'log', '-1', '--format=%ct', '--invert-grep', '--grep=^auto:')
    days = None
    if last.isdigit():
        days = (datetime.now(timezone.utc)
                - datetime.fromtimestamp(int(last), timezone.utc)).days
    return {'dirty': len(dirty), 'days_since_human_commit': days}


def user_count():
    """봇 사용자 수 — Q3 계약의 유일한 목표 지표(3명)."""
    try:
        import db
        return len(db.all_users() or [])
    except Exception:
        return None



def factcheck_flags(days: int = 7):
    """생성 시점 사실 검사(factcheck.sanitize)가 최근에 걸어둔 플래그.

    sanitize 는 고칠 수 있는 건 조용히 고치고(잘못된 티커 코드 제거), 고칠 수
    없는 건 _flags 에 남긴다. 남기기만 하고 아무도 안 보면 안 남긴 것과 같아서
    주간 브리핑으로 끌어올린다. **과거분은 소급해 고치지 않기로 했으므로
    (2026-09-18 결정) 여기서는 최근 것만 본다** — 옛 데이터가 계속 쌓여 보이면
    새로 생긴 문제가 묻힌다.
    """
    try:
        import db
        from datetime import datetime, timezone, timedelta
        cut = datetime.now(timezone.utc) - timedelta(days=days)
        amt, tick = [], []
        for r in db.unfinished_analyses():
            f = ((r.get('analysis') or {}).get('_flags') or {})
            if not f:
                continue
            try:
                pub = datetime.fromisoformat(str(r['published']).replace('Z', '+00:00'))
            except Exception:
                continue
            if pub < cut:
                continue
            if f.get('amount_suspect'):
                amt.append((r.get('title', '')[:34], f['amount_suspect'][0][:60]))
            if f.get('ticker_cleared'):
                tick.append((r.get('title', '')[:34], ', '.join(f['ticker_cleared'])[:40]))
        return {'amount': amt, 'ticker': tick}
    except Exception as e:
        print(f'[factcheck_flags 실패] {e}')
        return None


def news_push_health(days: int = 7):
    """뉴스 푸시가 요약으로 나갔는지, 링크 폴백이었는지, 아예 못 갔는지.

    2026-09-22 자가점검에서 이 기능만 계측이 없어 "경로는 돌았는데 결과는 모름"
    상태였다. 생성(summarize_news)과 발송(send_ir_news)을 따로 센다 —
    요약을 만들어놓고 발송이 실패하면 사용자는 아무것도 못 받기 때문이다.
    """
    try:
        import ir
        recs = ir.news_log(days)
    except Exception as e:
        print(f'[news_push_health 실패] {e}')
        return None
    # skip = 잡음뿐이라 안 보낸 기록(2026-10-20). 생성 건수에 섞이면 안 된다.
    gen = [r for r in recs if r.get('stage') not in ('send', 'skip')]
    snd = [r for r in recs if r.get('stage') == 'send']
    return {'runs': len(gen),
            'ok': sum(1 for r in gen if r.get('result') == 'ok'),
            'empty': sum(1 for r in gen if r.get('result') == 'empty'),
            'failed': sum(1 for r in gen if r.get('result') in ('error', 'parse_error')),
            'sends': len(snd),
            'send_fail': sum(1 for r in snd if not r.get('sent')),
            'fallback': sum(1 for r in snd if r.get('fallback')),
            'last_why': next((r.get('why') for r in reversed(gen) if r.get('why')), '')}

def screener_feed_health():
    """리포트 종목 공급선이 살아 있는지 — 두 번 조용히 끊겼던 자리.

    2026-08-05 스크리너가 leaders_v2 → leaders_signal 로 갈아타며 옛 파일을
    지웠고 feed.py 는 이틀간 죽은 줄도 모르고 돌았다. 2026-10-10 점검에서
    **같은 일이 또** 드러났다 — leaders_signal 마저 사라지고 leaders_accel.json
    이 그 자리에 생겼는데 한 달 넘게 아무도 몰랐다.

    그래서 "feed 가 아는 파일이 있나"만 보지 않는다. 그것만 보면 파일이 전부
    사라졌을 때 "없음"이라고만 말하고 **왜 없는지는 영영 모른다.** 디렉터리에
    feed 가 모르는 신호 파일이 생겼는지까지 같이 본다. 이름이 바뀌는 게 이
    사고의 형태였고, 바뀐 이름은 디렉터리에 그대로 남아 있었다.
    """
    try:
        import sys as _sys
        from datetime import date
        _sys.path.insert(0, str(Path(__file__).resolve().parent / 'decks'))
        import feed
    except Exception as e:
        print(f'[screener_feed_health 실패] {e}')
        return None
    try:
        d = feed._results_dir()
        if not d.exists():
            return {'dir': str(d), 'dir_missing': True,
                    'alive': None, 'candidates': 0, 'age': None, 'unknown': []}
        known = {f for f, _, _ in feed.SOURCES}
        alive, cand, age = None, 0, None
        for fname, parser, label in feed.SOURCES:
            doc = feed._load(fname)
            if doc is None:
                continue
            alive = f'{fname} ({label})'
            try:
                cand = len(parser(doc, set()) or [])
            except Exception:
                cand = -1          # 파싱이 깨진 것과 후보 0건은 다른 사고다
            p = d / fname
            age = (date.today() - date.fromtimestamp(p.stat().st_mtime)).days
            break
        # feed 가 모르는, 신호처럼 생긴 파일 — 이름이 바뀐 흔적
        unknown = sorted(p.name for p in d.glob('*.json')
                         if p.name not in known
                         and any(k in p.name for k in ('leader', 'signal', 'pick')))
        return {'dir': str(d), 'dir_missing': False, 'alive': alive,
                'candidates': cand, 'age': age, 'unknown': unknown}
    except Exception as e:
        print(f'[screener_feed_health 실패] {e}')
        return None


def youtube_health():
    """유튜브 요약의 유실률 — 조용히 새던 것을 숫자로 드러낸다.

    2026-09-06 실측에서 272건 중 67건(25%)이 내용 없이 저장돼 발송되지 않았는데,
    화면에도 로그에도 아무 표시가 없어 사용자가 직접 "요약이 안 온다"고 물을 때까지
    아무도 몰랐다. 실패는 성공보다 눈에 띄어야 한다.
    """
    try:
        import db, analyzer, config
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        rows = db.unfinished_analyses()
        recent, bad, retryable = 0, 0, 0
        for r in rows:
            try:
                age = (now - datetime.fromisoformat(str(r['published']).replace('Z', '+00:00'))).total_seconds() / 3600
            except Exception:
                continue
            if age > 24 * 7:
                continue
            recent += 1
            if analyzer.has_content(r.get('analysis') or {}):
                continue
            bad += 1
            if (r.get('attempts') or 0) < config.RETRY_MAX and age <= config.RETRY_WINDOW_H:
                retryable += 1
        return {'recent': recent, 'bad': bad, 'retryable': retryable}
    except Exception:
        return None


# ─────────────────────────── 소집 ───────────────────────────
def roster(deck, repo, users):
    """상태에서 이번 주 부를 부서를 유도한다. 부를 이유가 없으면 안 적는다.

    반환: [(부서, 이유, 실행할 것)]
    """
    out = []
    _qe = _quarter_end()
    d_left = (_qe - datetime.now(timezone.utc)).days

    if deck.get('blocked'):
        names = ', '.join(t for t, _, _ in deck['blocked'])
        out.append(('품질팀', f'발행 차단 {len(deck["blocked"])}종({names})',
                    'report-auditor 에이전트 또는 python decks/check.py <티커>'))
    if deck.get('broken'):
        out.append(('개발팀', f'임포트 실패 {len(deck["broken"])}종 — 데이터 파일이 깨졌다',
                    'python decks/preflight.py'))
    if repo.get('dirty', 0) >= 10:
        out.append(('개발팀', f'미커밋 {repo["dirty"]}개 — 자동 커밋이 덮을 수 있다',
                    'git status 확인 후 커밋'))
    if users is not None and users < 3:
        out.append(('세일즈', f'외부 사용자 {users}명 / 목표 3명 · 분기 마감 {d_left}일 전',
                    'PM/SALES.md 의 이번 주 대상 1명'))
    if 0 <= d_left <= 14:
        out.append(('이사회', f'Q{(_qe.month - 1) // 3 + 1} 계약 채점 {d_left}일 전',
                    '/kill-or-keep — 계약을 지켰는지 먼저 채점'))

    # 매주 고정으로 부르는 것은 하나뿐 — 많아지면 전부 무시된다.
    out.append(('PM', '주간 정기', '/loose-ends'))
    return out


# ─────────────────────────── 조립 ───────────────────────────
def build_text(on_runner=None):
    if on_runner is None:
        on_runner = bool(os.environ.get('GITHUB_ACTIONS'))
    deck, repo = deck_state(), repo_state()
    users = user_count()
    today = datetime.now(timezone.utc).strftime('%m-%d')

    L = [f'📋 <b>주간 소집 브리핑</b> · {today}', '']

    if deck.get('error'):
        L.append(f'⚠️ 덱 검사 실패 — {deck["error"]}')
    else:
        rc = deck.get('recent') or []
        L.append(f'<b>리포트</b> · 데이터 {deck["total"]}종 · 최근 7일 발송 {len(rc)}종'
                 + (f' ({", ".join(f"{t} {d[5:]}" for d, t in rc[:6])})' if rc else '')
                 + f' · 누적 발송 {deck["published"]}종 · 요청 시 바로 렌더 가능 {len(deck["ready"])}종')
        for t, n, items in deck['blocked']:
            L.append(f'  🔴 {t} — 차단 {n}건: {", ".join(items)}')
        if deck['broken']:
            L.append(f'  ⚫ 임포트 실패: {", ".join(deck["broken"])}')

    days = repo.get('days_since_human_commit')
    L.append('')
    L.append(f'<b>저장소</b> · 미커밋 {repo["dirty"]}개 · '
             f'마지막 사람 커밋 {days if days is not None else "?"}일 전')
    L.append(f'<b>사용자</b> · {users if users is not None else "?"}명 / 목표 3명')
    try:   # 2026-11-12: 활성화 퍼널·설문·측정 신선도 — '기능은 80점인데 쓰는 사람이 없다'를 매주 숫자로
        import stats, nudge, quality
        f = stats.funnel()
        L.append(f"<b>퍼널</b> · 시작 {f['started']} → 첫 사용 {f['activated']} → 감시 등록 {f['watching']} "
                 f"→ 7일 뒤 재방문 {f['d7']}/{f['d7_base']}")
        sv = nudge.summary()
        if sv['asked'] or sv['reminded']:
            L.append(f"<b>설문</b> · 보냄 {sv['asked']} · 응답 {sv['answered']} "
                     f"(👍{sv['good']} 😐{sv['meh']} 👎{sv['bad']}) · 미등록 리마인드 {sv['reminded']}")
        q = quality.trend('report', 1)
        if q:
            from datetime import datetime as _d, timezone as _tz
            age = (_d.now(_tz.utc) - _d.fromisoformat(q[-1]['at'])).days
            L.append(f"{'⚠️ ' if age > 14 else ''}<b>리포트 채점</b> · {q[-1]['at'][:10]}({age}일 전) "
                     f"평균 {q[-1]['mean']} · {q[-1]['n']}종 · {q[-1].get('note', '')}")
        else:
            L.append('⚠️ <b>리포트 채점</b> · 기록 없음')
    except Exception as e:
        L.append(f'· ⚠️ 퍼널·채점 점검 실패: {type(e).__name__}')
    yh = youtube_health()
    if yh and yh['recent']:
        rate = yh['bad'] * 100 // yh['recent']
        mark = '⚠️ ' if rate >= 10 else ''
        L.append(f'{mark}<b>유튜브 요약</b> · 최근 7일 {yh["recent"]}건 중 '
                 f'미발송 {yh["bad"]}건({rate}%) · 재시도 대기 {yh["retryable"]}건')

    nh = news_push_health()
    if nh and (nh['runs'] or nh['sends']):
        bad = nh['failed'] + nh['send_fail']
        mark = '⚠️ ' if bad else ''
        L.append(f"{mark}<b>뉴스 푸시</b> · 최근 7일 요약 {nh['ok']}건 · "
                 f"추릴 것 없음 {nh['empty']}건 · 요약실패 {nh['failed']}건 · "
                 f"발송 {nh['sends']}건(실패 {nh['send_fail']}, 링크폴백 {nh['fallback']})")
        if nh['last_why']:
            L.append(f"  · 최근 사유: {html.escape(str(nh['last_why'])[:70])}")

    sf = screener_feed_health()
    if sf:
        if sf['dir_missing']:
            L.append(f'⚠️ <b>종목 공급</b> · 스크리너 results 폴더 없음 — {html.escape(sf["dir"])}')
        elif not sf['alive']:
            L.append('🔴 <b>종목 공급</b> · feed 가 아는 신호 파일이 하나도 없음')
        else:
            mark = '⚠️ ' if (sf['candidates'] <= 0 or (sf['age'] or 0) > 10) else ''
            cand = '파싱 실패' if sf['candidates'] < 0 else f'후보 {sf["candidates"]}건'
            L.append(f'{mark}<b>종목 공급</b> · {html.escape(sf["alive"])} · '
                     f'{cand} · {sf["age"]}일 전')
        if sf['unknown']:
            # 이름이 바뀐 흔적. 두 번 다 이 형태였다.
            L.append('  🔴 feed 가 모르는 신호 파일: '
                     + html.escape(', '.join(sf['unknown'][:4])))

    fc = factcheck_flags()
    if fc and (fc['amount'] or fc['ticker']):
        L.append('⚠️ <b>사실 검사</b> · 최근 7일')
        if fc['ticker']:
            L.append(f'  · 잘못된 종목코드 {len(fc["ticker"])}건 자동 제거'
                     f'(이름은 유지) — {html.escape(fc["ticker"][0][1])}')
        for t, snip in fc['amount'][:3]:
            L.append(f'  · 금액 확인 필요: {html.escape(t)} — {html.escape(snip)}')
        if len(fc['amount']) > 3:
            L.append(f'  · 외 {len(fc["amount"]) - 3}건')

    L.append('')
    L.append('<b>이번 주 소집</b>')
    # tg.send_message는 parse_mode=HTML이다. 소집 명령에 들어가는 <티커> 같은
    # 자리표시자를 그대로 실으면 텔레그램이 "Unsupported start tag"로 400을 내며
    # 브리핑 전체가 발송 실패한다 — 실제로 첫 초안이 그 상태였다.
    for dept, why, how in roster(deck, repo, users):
        L.append(f'• <b>{dept}</b> — {html.escape(why)}')
        L.append(f'  ↳ <code>{html.escape(how)}</code>')

    if on_runner:
        L.append('')
        L.append('<i>러너 실행분이라 렌더 상태(재렌더 필요 여부)는 안 봄 — '
                 '로컬에서 python decks/check.py 로 전수 확인 가능</i>')
    return '\n'.join(L)


VERIFY_LOG = Path(__file__).resolve().parent / 'verify_log.json'
KEEP_DAYS = 60          # 이력 보존 일수 — 파일이 무한히 커지지 않게
STICKY_DAYS = 3         # 같은 항목이 이만큼 연속이면 '일시적'이 아니라고 본다


def verify_load() -> list:
    try:
        return json.loads(VERIFY_LOG.read_text(encoding='utf-8')) or []
    except Exception:
        return []


def verify_record(snap: dict) -> list:
    """오늘 스냅샷을 이력에 남긴다. 같은 날짜는 덮어쓴다(하루 여러 번 돌아도 1건).

    스냅샷만 매일 보내면 '오늘 6종 차단'은 알지만 **어제도 그랬는지**를 모른다.
    그 차이가 판단을 가른다 — 어제 8종이었으면 배치가 따라잡는 중이고, 사흘째
    같은 6종이면 배치로는 안 풀리는 것이라 사람이 손대야 한다.
    """
    log = [e for e in verify_load() if e.get('date') != snap.get('date')]
    log.append(snap)
    log = sorted(log, key=lambda e: str(e.get('date')))[-KEEP_DAYS:]
    try:
        VERIFY_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding='utf-8')
    except Exception as e:
        print(f'검증 이력 기록 실패: {e}')
    return log


def verify_trend(log: list) -> list:
    """이력에서 '반복되는 것'만 골라 코멘트를 만든다.

    ## 무엇을 근본개선 대상으로 볼 것인가

    세 가지를 구분한다. 이걸 안 나누면 API 가 하루 죽은 것과 코드가 틀린 것이
    같은 경보로 보인다.

    · **매번 다른 종목/사유** → 일시적(네트워크·쿼터). 손대지 않는다.
    · **같은 종목이 같은 사유로 연속** → 그 종목의 데이터 문제. 사람이 본다.
    · **같은 사유가 여러 종목에서 연속** → 구조적. **코드로 고쳐야 한다.**

    마지막 것이 근본개선 대상이다. 예: AS_OF 차단이 5종에서 사흘째면 배치가
    하루 1건으로 못 따라간다는 뜻이지, 종목 다섯 개가 각자 아픈 게 아니다.
    """
    if len(log) < 2:
        return ['· 이력 1일치 — 추세는 내일부터']
    out = []
    cur, prev = log[-1], log[-2]
    old = log[-min(len(log), 8)]

    nb, pb, ob = (len(e.get('blocked') or {}) for e in (cur, prev, old))
    arrow = '↓ 줄고 있다' if nb < pb else ('↑ 늘고 있다' if nb > pb else '→ 그대로')
    out.append(f'· 차단 {nb}종 {arrow} (어제 {pb} · {len(log)}일 전 {ob})')

    # 며칠 연속 같은 (종목, 사유) 인가
    sticky = {}
    for tk, item in (cur.get('blocked') or {}).items():
        n = 0
        for e in reversed(log):
            if (e.get('blocked') or {}).get(tk) == item:
                n += 1
            else:
                break
        if n >= STICKY_DAYS:
            sticky[tk] = (item, n)
    # ⚠️ '며칠 연속 차단' 을 곧바로 '안 풀린다' 로 읽으면 안 된다. 배치가 하루 1건이라
    #    큐에 5종이 있으면 4종은 그냥 **차례가 안 온 것**이다. 실측(2026-09-10): 자물쇠
    #    5개를 띄웠는데 그중 4종은 fails=0(재생성을 시도조차 안 함)이었고, 같은 리포트
    #    맨 위에서 PLTR 이 재생성으로 되살아났다 — '안 풀린다'는 그 자리에서 거짓이었다.
    #    판정 근거는 연속 일수가 아니라 **실제 재생성 시도 기록(fails)** 이어야 한다.
    try:
        import deck_live
        deck_live._decks_path()
        import refresh as _rf
        state = _rf.load()
    except Exception:
        state = {}

    hard, queued = {}, []
    for tk, (item, n) in sorted(sticky.items()):
        if int((state.get(tk) or {}).get('fails', 0)) > 0:
            hard[tk] = (item, n)
        else:
            queued.append(tk)

    for tk, (item, n) in sorted(hard.items()):
        out.append(f'· 🔒 {tk} — {item} · {n}일 연속이고 재생성해도 그대로다. 사람이 봐야 한다')
    if queued:
        out.append(f'· ⏳ 차례 대기 {len(queued)}종({", ".join(sorted(queued))}) — '
                   f'배치가 하루 1건이라 약 {len(queued)}일 뒤 해소. 할 일 없음')

    # 같은 사유가 **재생성으로도 안 풀린 채** 여러 종목에서 반복 → 그때가 구조적이다
    by_item = {}
    for tk, (item, _n) in hard.items():
        by_item.setdefault(item, []).append(tk)
    for item, tks in by_item.items():
        if len(tks) >= 2:
            out.append(f'· 🔧 <b>근본개선 대상</b>: {item} 이 {len(tks)}종({", ".join(sorted(tks))})에서 '
                       f'재생성으로도 안 풀린다 — 종목별 문제가 아니라 규칙 문제다')

    # 유튜브 실패 사유 7일 누적 — 한 번은 일시적, 반복은 구조적
    agg = {}
    for e in log[-7:]:
        for k, v in ((e.get('yt') or {}).get('errs') or {}).items():
            agg[k] = agg.get(k, 0) + v
    if agg:
        out.append('· 유튜브 실패 7일 누적: ' + ', '.join(f'{k} {v}건' for k, v in sorted(agg.items(), key=lambda x: -x[1])))
        if agg.get('토큰초과', 0) >= 2:
            out.append('· 🔧 <b>근본개선 대상</b>: 토큰초과가 반복된다 — fps 적응만으론 부족, 구간 분할 필요')
    return out


def verify_text():
    """파이프라인 검증 한 장 — 러너가 매일 만들어 텔레그램으로 보낸다.

    ## 왜 러너에서 만드나
    사용자 노트북의 예약 작업으로도 만들 수 있지만, 그건 **앱이 열려 있을 때만** 돈다.
    노트북을 끄면 검증이 통째로 멈추는데, 정작 그 사이에도 러너는 3시간마다 돌고
    있으므로 "돌고 있는데 아무도 안 보는" 상태가 된다 — 이 프로젝트에서 반복해서
    사고를 낸 바로 그 형태다(2026-09-06: 유튜브 요약 25% 유실이 아무 표시 없이 진행,
    리포트 6종이 발행 불가로 죽은 채 방치). 감시는 감시 대상과 같은 곳에서 돌아야 한다.

    ⚠️ Gemini 생성 쿼터를 쓰지 않는다. DB 조회와 파일 읽기만으로 판정한다 —
    하루 상한이 2회뿐이라 검증이 그걸 먹으면 정작 리포트를 못 만든다.
    """
    from datetime import datetime, timezone, timedelta
    snap = {'date': datetime.now(timezone.utc).date().isoformat(), 'blocked': {}, 'yt': {}}
    L = [f'🔍 <b>파이프라인 검증</b> · {datetime.now(timezone.utc).strftime("%m-%d")}', '']

    # ── 리포트 배치 ──
    L.append('📊 <b>리포트 배치</b>')
    try:
        import deck_live
        deck_live._decks_path()
        import refresh
        st = refresh.load()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
        tried = [(k, v) for k, v in st.items()
                 if str(v.get('last_try') or '') and
                 datetime.fromisoformat(v['last_try']) >= cutoff]
        if tried:
            for k, v in tried:
                mark = '✅ 되살림' if v.get('last_ok') else ('❌ ' + str(v.get('last_reason') or v.get('last_error') or '실패')[:40])
                L.append(f'· {k} — {mark}')
        else:
            L.append('· 어제 재생성 없음')
        blocked = refresh.scan()
        snap['blocked'] = {t: r[0][0] for t, r in blocked}   # 사유 '항목'만 — 문구는 길어서 이력엔 안 넣는다
        L.append(f'· 차단 잔여 {len(blocked)}종' + (f' — {", ".join(t for t, _ in blocked[:6])}' if blocked else ''))
        stuck = refresh.stuck()
        if stuck:
            L.append(f'· ⚠️ 사람 확인 필요 {len(stuck)}종: {", ".join(sorted(stuck))}')
        L.append(f'· 오늘 생성 가능 {deck_live.autogen_left()}회')
    except Exception as e:
        L.append(f'· ⚠️ 점검 실패: {type(e).__name__}: {str(e)[:60]}')

    # ── 유튜브 ──
    L.append('')
    L.append('🎬 <b>유튜브 요약</b>')
    try:
        import db, analyzer
        from datetime import datetime as _dt
        now = datetime.now(timezone.utc)
        rows = db.unfinished_analyses()
        n24 = ok24 = 0
        srcs = {}
        errs = {}
        samples = []   # 2026-10-23: '기타'가 대부분이라 원인을 못 봤다 → 원문 일부를 남긴다
        for r in rows:
            try:
                age = (now - _dt.fromisoformat(str(r['published']).replace('Z', '+00:00'))).total_seconds() / 3600
            except Exception:
                continue
            if age > 24:
                continue
            n24 += 1
            srcs[r.get('source')] = srcs.get(r.get('source'), 0) + 1
            a = r.get('analysis') or {}
            if isinstance(a, str):
                import json as _j
                try:
                    a = _j.loads(a)
                except Exception:
                    a = {}
            if analyzer.has_content(a):
                ok24 += 1
            else:
                e = str(a.get('_error') or '')
                k = ('토큰초과' if ('1048576' in e or 'token count exceeds' in e)
                     else '503/504' if ('503' in e or '504' in e or 'DEADLINE' in e)
                     else '타임아웃' if 'timed out' in e.lower()
                     else '처리 전(오류 없음)' if not e and not a.get('_parse_error')
                     else 'JSON 파싱' if a.get('_parse_error') else '기타')
                errs[k] = errs.get(k, 0) + 1
                if len(samples) < 3:
                    samples.append(f"{r.get('video_id', '?')}: {e[:120] or k}")
        sent = 0
        try:
            for d in db._sb.table('deliveries').select('*').execute().data or []:
                t = str(d.get('sent_at') or '')
                if t and (now - _dt.fromisoformat(t.replace('Z', '+00:00'))).total_seconds() <= 86400:
                    sent += 1
        except Exception:
            sent = -1
        L.append(f'· 최근 24h 분석 {n24}건 · 내용 있음 {ok24}건 · 발송 {sent if sent >= 0 else "?"}건')
        if srcs:
            L.append('· 경로: ' + ', '.join(f'{k}={v}' for k, v in srcs.items()))
        if errs:
            L.append('· 실패: ' + ', '.join(f'{k} {v}건' for k, v in errs.items()))
            if '토큰초과' in errs:
                L.append('· ⚠️ fps 적응으로도 한도 초과 — 구간 분할이 필요하다')
        elif n24:
            L.append('· fps 적응: 토큰초과 0건 ✅')
        snap['yt'] = {'n24': n24, 'ok24': ok24, 'errs': errs, 'samples': samples}
        yh = youtube_health()
        if yh:
            L.append(f'· 7일 미발송 {yh["bad"]}/{yh["recent"]}건 · 재시도 대기 {yh["retryable"]}건')
    except Exception as e:
        L.append(f'· ⚠️ 점검 실패: {type(e).__name__}: {str(e)[:60]}')
    # ── 추세 ── 스냅샷만으로는 '오늘 6종'이 좋아지는 중인지 굳은 건지 알 수 없다.
    L.append('')
    L.append('📈 <b>추세 · 코멘트</b>')
    try:
        L += verify_trend(verify_record(snap))
    except Exception as e:
        L.append(f'· ⚠️ 추세 분석 실패: {type(e).__name__}: {str(e)[:60]}')
    return chr(10).join(L)


def verify_send() -> bool:
    """검증 결과를 소유자에게 보낸다."""
    import tg
    chat = _owner_chat()
    if not chat:
        print('검증 리포트: 받을 사람 없음')
        return False
    return bool(tg.send_message(chat, verify_text()))


def _owner_chat():
    """받을 사람 = 소유자. OWNER_CHAT 환경변수 → config.OWNER_CHAT(고정값).

    2026-10-23: 예전 폴백은 'db.all_users() 의 첫 행'이었다. Supabase 는 정렬을 보장하지 않아
    지인이 가입하자 첫 행이 그 사람으로 바뀌었고, 시황·운영 알림·VOC 가 소유자 대신 지인에게 갔다.
    추측하는 폴백은 두지 않는다."""
    chat = os.environ.get('OWNER_CHAT', '').strip()
    if chat:
        return chat
    try:
        import config
        return str(getattr(config, 'OWNER_CHAT', '') or '')
    except Exception:
        return ''


def main_send() -> bool:
    """run.py가 부르는 진입점. 성공해야만 호출부가 주기 게이트를 찍는다 —
    발송이 실패했는데 '보냈다'고 기록하면 그 주 브리핑은 영영 사라진다."""
    import tg
    chat = _owner_chat()
    if not chat:
        print('❌ 보낼 대상이 없다 — OWNER_CHAT 미설정이고 등록 사용자도 없음')
        return False
    return bool(tg.send_message(chat, build_text()))


def main():
    if '--send' in sys.argv:
        return 0 if main_send() else 1
    # 이 PC의 콘솔은 CP949라 브리핑의 이모지에서 UnicodeEncodeError로 죽는다
    # (실제로 첫 실행이 여기서 터졌다). 텔레그램 발송 경로는 영향 없지만,
    # 로컬에서 눈으로 확인하는 용도가 이 분기이므로 출력만 UTF-8로 돌린다.
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    print(build_text(on_runner=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
