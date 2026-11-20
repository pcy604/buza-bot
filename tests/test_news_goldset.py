"""골드셋 채점 — 네트워크 없이 (2026-11-12)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tools'))
import news_goldset as G
p = Path(tempfile.mkdtemp()) / 'g.md'
p.write_text('''| No | 날짜 | 출처 | 제목 | 봇 | 판정 |
|---|---|---|---|---|---|
| 1 | 2026-11-12 | T3 Reuters | 실적 발표 | ✔ | O |
| 2 | 2026-11-12 | T1 blog | 살까? | ✔ | X |
| 3 | 2026-11-12 | T4 PR | 대형 계약 |  | O |
| 4 | 2026-11-12 | T2 x | 행사 |  | x |
| 5 | 2026-11-12 | T2 x | 미판정 | ✔ |  |
''', encoding='utf-8')
r = G.score([p])
assert (r['tp'], r['fp'], r['fn'], r['tn'], r['unlabeled']) == (1, 1, 1, 1, 1), r
assert r['precision'] == 0.5 and r['recall'] == 0.5
print('ALL PASS')
