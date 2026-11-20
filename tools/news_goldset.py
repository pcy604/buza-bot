"""R&D 1 — 뉴스 선별 정답셋(골드셋) 만들기·채점 (2026-11-12).

왜: 뉴스 '선별 품질'을 👍/👎 로 재려 했지만 3주간 외부 표본 1쌍 — 통계가 안 된다.
  사람이 후보 사건 전체에 '중요/아님'을 한 번 찍어 두면, 그 뒤 선별 규칙을 바꿀 때마다
  정밀도(보낸 것 중 중요한 비율)·재현율(중요한 것 중 보낸 비율)을 숫자로 비교할 수 있다.
  목표: 종목 5~10개 × 이틀치 ≈ 사건 50건 이상.

사용
  make  TICKER ...   (러너: news-goldset 워크플로) → goldset/news_YYYYMMDD_HHMM.md
        표: No · 날짜 · 출처등급 · 제목 · 봇 선택(✔) · 판정(빈칸 → 사람이 O/X)
  score FILE.md ...  → 정밀도·재현율·F1 (여러 파일 합산)
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT_DIR = ROOT / 'goldset'
ROW = re.compile(r'^\|\s*(\d+)\s*\|(.*)\|\s*(✔?)\s*\|\s*([OoXx○×]?)\s*\|\s*$')


def make(tickers, hours=48):
    import ir
    ir.note_news = lambda r: None
    now = datetime.now(timezone.utc)
    L = [f'# 뉴스 골드셋 {now:%Y-%m-%d %H:%M} UTC · 최근 {hours}시간', '',
         '판정 칸에 **O(알려야 할 사건) / X(아님)** 만 적고 커밋하세요. 봇 선택(✔)은 보지 말고 제목만 보고 판단.',
         '기준: 이 종목을 가진 사람이 오늘 알아야 하나? (실적·가이던스·합병·대형 계약·규제·소송·증자·자사주 = 대개 O)', '']
    for t in tickers:
        try:
            cik, company = ir.watch_company(t)
            loc = ir.NEWS_LOCALES_KR if ir.is_kr(t) else None
            items = ir.company_news(company, limit=ir.NEWS_DIGEST_LIMIT, since=now - timedelta(hours=hours),
                                    locales=loc, rank=True)
            dg = ir.summarize_news(t, company, items, lang='ko')
        except Exception as e:
            L += [f'## {t}', f'(실패: {type(e).__name__}: {str(e)[:80]})', '']
            continue
        failed = dg is None and bool(items)     # Gemini 503 등 — '선택 0'과 구분해야 정밀도가 왜곡되지 않는다
        picked = {int(x) for d in (dg or []) for x in (d.get('src') or []) if str(x).isdigit()}
        L += [f'## {t} · {company} — 후보 {len(items)}건 · '
              + ('봇 요약 실패 — 채점 제외' if failed else f'봇 선택 {len(picked)}건'), '',
              '| No | 날짜 | 출처 | 제목 | 봇 | 판정 |', '|---|---|---|---|---|---|']
        for i, n in enumerate(items, 1):
            title = str(n.get('title') or '').replace('|', '／')[:110]
            L.append(f"| {i} | {str(n.get('date') or '')[:16]} | T{ir._tier(n.get('source'))} {str(n.get('source') or '')[:18]} "
                     f"| {title} | {'✔' if i in picked else ''} |  |")
        L.append('')
    OUT_DIR.mkdir(exist_ok=True)
    p = OUT_DIR / f'news_{now:%Y%m%d_%H%M}.md'
    p.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(p)
    return p


def score(paths):
    tp = fp = fn = tn = blank = 0
    for p in paths:
        skip = False
        for line in Path(p).read_text(encoding='utf-8').splitlines():
            if line.startswith('## '):
                skip = '채점 제외' in line
            if skip:
                continue
            m = ROW.match(line.strip())
            if not m:
                continue
            sel, lab = bool(m.group(3)), m.group(4).upper().replace('○', 'O').replace('×', 'X')
            if not lab:
                blank += 1
                continue
            pos = lab == 'O'
            tp += sel and pos
            fp += sel and not pos
            fn += (not sel) and pos
            tn += (not sel) and not pos
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, unlabeled=blank, precision=prec, recall=rec, f1=f1)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    cmd, args = (sys.argv[1] if len(sys.argv) > 1 else ''), sys.argv[2:]
    if cmd == 'make':
        make(args or ['TSLA', 'NVDA', '005930.KS'])
    elif cmd == 'score':
        r = score(args or sorted(OUT_DIR.glob('news_*.md')))
        f = lambda v: '-' if v is None else f'{v:.0%}'
        print(f"정밀도 {f(r['precision'])} · 재현율 {f(r['recall'])} · F1 {f(r['f1'])} "
              f"(TP {r['tp']} FP {r['fp']} FN {r['fn']} TN {r['tn']} · 미판정 {r['unlabeled']})")
    else:
        sys.exit(__doc__)
