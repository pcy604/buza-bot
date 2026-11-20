"""R&D 2 — 한국어 '같은 사건' 묶기 실험 (2026-11-12).

문제(10-24 실측): 같은 사건을 다른 숫자로 보도하면(특별배당 4,140억 vs 6,800억) 숫자 지문도, 낱말 겹침도
  못 묶는다 — 한국어는 조사·어순 변화가 커서 낱말 단위가 잘 안 맞는다.
가설: 글자 2-gram(바이그램) 겹침계수는 조사·띄어쓰기에 덜 민감하다.
실험: 같은 원천 기사(최근 48h, raw)에 ① 현행 ir._news_cluster ② 현행 + 바이그램 병합(같은 날·±1일, 겹침 ≥ θ)
  을 걸어 사건 수를 비교하고, ②가 '새로 합친 쌍'을 표로 내 사람이 O(같은 사건)/X(다른 사건)를 찍는다.
  → 오합침률 = X / 새로 합친 쌍. 기준: 오합침 ≤ 10% 이고 사건 수가 의미 있게 줄면 운영 반영.
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def bigrams(title: str, company: str) -> frozenset:
    # 숫자·단위는 뺀다 — 이 실험의 대상이 '숫자가 달라 못 묶인 같은 사건'이다
    t = (title or '').lower().replace(company.lower(), '')
    t = re.sub(r'\d[\d,.]*\s*(조|억|만|원|%)?', '', t)
    t = re.sub(r'[^가-힣a-z]', '', t)
    return frozenset(t[i:i + 2] for i in range(len(t) - 1))


def overlap(a: frozenset, b: frozenset) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def extra_merges(reps: list, company: str, theta: float = 0.4, days: int = 1) -> list:
    """현행 군집 대표들 중 바이그램으로 추가로 합쳐질 쌍 (i, j, 점수)."""
    bg = [bigrams(r.get('title', ''), company) for r in reps]
    out = []
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            try:
                gap = abs((datetime.strptime(reps[i]['date'], '%Y-%m-%d')
                           - datetime.strptime(reps[j]['date'], '%Y-%m-%d')).days)
            except Exception:
                gap = 0
            if gap > days:
                continue
            s = overlap(bg[i], bg[j])
            if s >= theta and len(bg[i] & bg[j]) >= 3:
                out.append((i, j, round(s, 2)))
    return out


def run(tickers, hours=48, theta=0.4):
    import ir
    now = datetime.now(timezone.utc)
    L = [f'# 한국어 사건 묶기 실험 {now:%Y-%m-%d %H:%M} UTC · θ={theta}', '',
         '판정 칸: 두 제목이 **같은 사건**이면 O, 다른 사건이면 X.', '']
    for t in tickers:
        cik, company = ir.watch_company(t)
        raw = ir.company_news(company, limit=200, since=now - timedelta(hours=hours), raw=True,
                              locales=ir.NEWS_LOCALES_KR)
        reps = ir._news_cluster(raw, company)
        ex = extra_merges(reps, company, theta)
        L += [f'## {t} {company} — 원문 {len(raw)} → 현행 사건 {len(reps)} → 바이그램 추가 병합 후보 {len(ex)}쌍', '',
              '| No | 제목 A | 제목 B | 겹침 | 판정 |', '|---|---|---|---|---|']
        for k, (i, j, s) in enumerate(ex, 1):
            a = str(reps[i].get('title', '')).replace('|', '／')[:70]
            b = str(reps[j].get('title', '')).replace('|', '／')[:70]
            L.append(f'| {k} | {a} | {b} | {s} |  |')
        L.append('')
    p = ROOT / 'goldset' / f'kr_cluster_{now:%Y%m%d_%H%M}.md'
    p.parent.mkdir(exist_ok=True)
    p.write_text('\n'.join(L) + '\n', encoding='utf-8')
    print(p)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    run(sys.argv[1:] or ['005930.KS', '000660.KS', '247540.KQ'])
