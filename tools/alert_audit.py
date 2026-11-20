"""알림 오탐·누락 점검 (2026-10-21, 지인 베타 전) — 수동 실행 전용, 러너에서 돈다.

    python tools/alert_audit.py [일수=30]   → audit_out.md / audit_out.json

무엇을 재나
  ① 미국 공시 누락: 감시 종목마다 SEC 원천의 최근 N일 관심 폼(config.IR_FORMS)을 받아,
     **실제 buza-run 실행 시각**에 지금 코드의 규칙(6시간 게이트 · '최신 1건'만 비교)을 다시 돌려 본다.
     어떤 실행에서도 '최신 1건'이 되지 못한 공시 = 그 규칙으로는 알림이 안 나가는 공시.
  ② 한국 공시 누락: DART 최근 N일 공시가 '마지막 이후 전부' 규칙에서 빠지는지(14일 조회창 밖 정지 등).
  ③ 막힘: 지금 기준선(seen)이 원천 최신과 다른 종목 = 보내지 못하고 걸려 있는 알림.
  ④ 뉴스 오탐: news_log 의 발송 중 '요약 0건인데 발송'(중요한 것 없음인데 보냄)·요약 실패 링크 발송·나쁨 피드백.

오탐의 기준은 봇 자신의 정의다(관심 폼·★ 규칙). 그 정의가 맞는지는 이 스크립트가 판정하지 않는다.
"""
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402
import ir  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
NOW = datetime.now(timezone.utc)
SINCE = NOW - timedelta(days=DAYS)


def _dt(s):
    d = datetime.fromisoformat(s.replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def run_times():
    """buza-run 실제 시작 시각(성공·실패 모두 — 실패해도 공시 감시 단계까지는 갔을 수 있어 낙관적 쪽)."""
    tok, repo = os.environ.get('GITHUB_TOKEN'), os.environ.get('GITHUB_REPOSITORY')
    out = []
    for page in range(1, 11):
        r = requests.get(f'https://api.github.com/repos/{repo}/actions/runs',
                         params={'per_page': 100, 'page': page, 'created': f'>={SINCE:%Y-%m-%d}'},
                         headers={'Authorization': f'Bearer {tok}'}, timeout=30).json()
        rs = r.get('workflow_runs') or []
        out += [_dt(x['run_started_at']) for x in rs if x['name'] == 'buza-run' and x.get('run_started_at')]
        if len(rs) < 100:
            break
    return sorted(out)


def gated(times, hours=config.JOB_INTERVAL_H):
    """run.py 의 주기작업 게이트 근사 — 마지막 통과 후 hours 가 지난 첫 실행만 공시 감시를 돈다."""
    out, last = [], None
    for t in times:
        if last is None or (t - last) >= timedelta(hours=hours) - timedelta(minutes=5):
            out.append(t)
            last = t
    return out


def us_filings(cik):
    r = requests.get(f'https://data.sec.gov/submissions/CIK{cik:010d}.json', headers=ir.SEC_HEADERS, timeout=30)
    r.raise_for_status()
    rec = r.json()['filings']['recent']
    out = []
    for i, form in enumerate(rec['form']):
        if form not in config.IR_FORMS:
            continue
        at = _dt(rec['acceptanceDateTime'][i])
        if at < SINCE - timedelta(days=7):
            break
        out.append({'form': form, 'acc': rec['accessionNumber'][i], 'at': at,
                    'items': (rec.get('items') or [''] * len(rec['form']))[i]})
    return out          # 최신순


def main():
    st = ir.load_state()
    watch = Counter(t for lst in st['watches'].values() for t in lst)
    # AUDIT_TICKERS='AAPL NVDA …' — 실제 감시 목록 대신 가상의 감시 목록으로 규칙만 시험(막힘 판정은 끔)
    if os.environ.get('AUDIT_TICKERS'):
        watch = Counter(os.environ['AUDIT_TICKERS'].split())
        st = dict(st, seen={t: '__sim__' for t in watch})
    checks = gated(run_times())
    res = {'days': DAYS, 'since': SINCE.isoformat(), 'checks': len(checks), 'us': [], 'kr': [], 'stuck': []}

    for t in sorted(x for x in watch if not ir.is_kr(x)):
        cik, _ = ir.resolve_ticker(t)
        if not cik:
            res['us'].append({'ticker': t, 'error': 'CIK 없음'})
            continue
        try:
            fs = us_filings(cik)
        except Exception as e:
            res['us'].append({'ticker': t, 'error': str(e)[:80]})
            continue
        alerted = set()
        for c in checks:
            avail = [f for f in fs if f['at'] <= c]
            if avail:
                alerted.add(avail[0]['acc'])
        win = [f for f in fs if f['at'] >= SINCE]
        miss = [f for f in win if f['acc'] not in alerted]
        res['us'].append({'ticker': t, 'watchers': watch[t], 'filings': len(win),
                          'missed': [f"{f['form']} {f['at']:%m-%d %H:%M}Z" for f in miss]})
        if fs and st['seen'].get(t) not in ('__sim__', fs[0]['acc']):
            res['stuck'].append({'ticker': t, 'seen': st['seen'].get(t), 'latest': fs[0]['acc'],
                                 'latest_at': fs[0]['at'].isoformat()})

    for t in sorted(x for x in watch if ir.is_kr(x)):
        try:
            fs = ir.kr_filings(t, days=DAYS)
        except Exception as e:
            res['kr'].append({'ticker': t, 'error': str(e)[:80]})
            continue
        res['kr'].append({'ticker': t, 'watchers': watch[t], 'filings': len(fs),
                          'major': sum(f['major'] for f in fs), 'folded': sum(f['fold'] for f in fs)})
        if fs and st['seen'].get(t) != '__sim__' and (st['seen'].get(t) or '') < fs[0]['rcept_no']:
            res['stuck'].append({'ticker': t, 'seen': st['seen'].get(t), 'latest': fs[0]['rcept_no']})

    try:
        L = json.load(open(ROOT / 'news_log.json', encoding='utf-8'))
    except Exception:
        L = []
    sends = [x for x in L if x.get('stage') == 'send' and _dt(x['at']) >= SINCE]
    res['news'] = {'sends': len(sends), 'empty_digest_sent': sum(1 for x in sends if x.get('digest') == 0),
                   'link_only': sum(1 for x in sends if x.get('fallback')),
                   'skips': sum(1 for x in L if x.get('stage') == 'skip' and _dt(x['at']) >= SINCE),
                   'bad_votes': sum(1 for x in L if x.get('stage') == 'feedback' and x.get('vote') == 'bad'),
                   'good_votes': sum(1 for x in L if x.get('stage') == 'feedback' and x.get('vote') == 'good')}

    us_n = sum(r.get('filings', 0) for r in res['us'])
    us_m = sum(len(r.get('missed', [])) for r in res['us'])
    lines = [f'# 알림 오탐·누락 점검 — 최근 {DAYS}일 (실행 {NOW:%Y-%m-%d %H:%M}Z)', '',
             f'- 공시 감시가 실제로 돈 횟수(6시간 게이트 근사): {len(checks)}회',
             f'- 미국 공시: {us_n}건 중 누락 {us_m}건' + (f' ({us_m / us_n:.0%})' if us_n else ''),
             f'- 한국 공시: {sum(r.get("filings", 0) for r in res["kr"])}건 · 규칙상 누락 0(‘마지막 이후 전부’) · 조회 실패 '
             f'{sum(1 for r in res["kr"] if r.get("error"))}종목',
             f'- 지금 걸려 있는(못 보낸) 종목: {len(res["stuck"])}', '']
    for r in res['us']:
        lines.append(f"  · US {r['ticker']}: " + (r.get('error') or f"{r['filings']}건, 누락 {len(r['missed'])} {r['missed']}"))
    for r in res['kr']:
        lines.append(f"  · KR {r['ticker']}: " + (r.get('error') or f"{r['filings']}건(★{r['major']} · 접기 {r['folded']})"))
    for s in res['stuck']:
        lines.append(f'  · 막힘 {s}')
    n = res['news']
    lines += ['', f"- 뉴스 발송 {n['sends']}건 · 요약 0건인데 발송 {n['empty_digest_sent']} · 링크만 {n['link_only']} · "
                  f"건너뜀 {n['skips']} · 피드백 좋음 {n['good_votes']}/나쁨 {n['bad_votes']}"]
    txt = '\n'.join(lines)
    print(txt)
    Path('audit_out.md').write_text(txt, encoding='utf-8')
    Path('audit_out.json').write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding='utf-8')


if __name__ == '__main__':
    main()
