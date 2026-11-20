"""/ir 분기 추이표 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_ir_trend.py

2026-09-17 에 한 번에 드러난 네 가지를 고정한다. 넷 다 "숫자는 맞는데 표가
이상해 보이는" 종류라 눈으로만 보면 또 놓친다.
  ① FY(연간) 열이 분기 사이에 끼어 6칸 중 4칸이 비었다
  ② 값이 하나도 없는 열이 통째로 남았다
  ③ 한 행 안에서 단위가 섞였다($22,387M 옆에 $28.24B)
  ④ '$(9.515)M' 같은 괄호 음수를 _parse_money 가 못 읽고 조용히 버렸다
"""
import sys
from pathlib import Path
# 노트북 절대경로가 박혀 있어 러너·다른 PC 에선 ir 을 못 찾았다(2026-10-20) — 레포 기준으로
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir

FILINGS = [
    {'form': '10-Q', 'acc': 'a1', 'date': '2026-08-01', 'primary': '', 'items': ''},   # Q2 2026
    {'form': '8-K',  'acc': 'a2', 'date': '2026-05-01', 'primary': '', 'items': '2.02'},  # Q1 2026
    {'form': '8-K',  'acc': 'a3', 'date': '2025-10-30', 'primary': '', 'items': '2.02'},  # Q4 가이던스만
    {'form': '10-K', 'acc': 'a4', 'date': '2025-09-01', 'primary': '', 'items': ''},   # FY2025
    {'form': '10-Q', 'acc': 'a5', 'date': '2025-08-01', 'primary': '', 'items': ''},   # Q3 2025
    {'form': '10-Q', 'acc': 'a6', 'date': '2025-05-01', 'primary': '', 'items': ''},   # Q2 2025
]
CACHE = {'TEST': {
    'a1': {'period': 'Q2 2026', 'revenue': '$26.9M', 'gross_margin': '0.296',
           'operating_income': '-$1.6M', 'fcf': '-$13.1M', 'net_income': '-$1.5M', 'cash': '$123.7M'},
    'a2': {'period': 'Q1 2026', 'revenue': '$25.1M', 'gross_margin': '28.0%',
           'operating_income': '$(1.1)M', 'fcf': None, 'net_income': '-$0.9M', 'cash': '$110.0M'},
    'a3': {'period': 'Q4 2025', 'revenue': '$22.5M-$23.5M'},          # 가이던스 범위뿐 → 빈 열이어야 함
    'a4': {'period': 'FY2025', 'revenue': '$103.2M'},                 # 연간 → 걸러져야 함
    'a5': {'period': 'Q3 2025', 'revenue': '$27.955M', 'gross_margin': '22.3%',
           'operating_income': '-$1.123M', 'fcf': None, 'net_income': '-$1.906M', 'cash': '$23.110M'},
    'a6': {'period': 'Q2 2025', 'revenue': '$24.0M', 'gross_margin': '21.0%',
           'operating_income': '-$2.0M', 'fcf': '-$3.0M', 'net_income': '-$2.2M', 'cash': '$20.0M'},
}}

ir.filing_history = lambda cik, limit=24: FILINGS
ir._load_fin_cache = lambda: CACHE
ir._save_fin_cache = lambda c: None

order, rows, _ = ir.quarterly_trend('TEST', 1, 'Test Co', n=5)
print('\n열:', order)
for r in rows:
    print(f"   {r['label']:<8} " + ' | '.join(f'{v:>10}' for v in r['values']))

assert 'FY2025' not in order, 'FY 열이 남았다'
assert 'Q4 2025' not in order, '빈 열이 남았다'
assert order == ['Q2 2025', 'Q3 2025', 'Q1 2026', 'Q2 2026'], order
gm = next(r for r in rows if r['label'] == '총마진')
assert gm['values'][-1] == '29.6%', f'소수 비율 보정 실패: {gm["values"][-1]}'
oi = next(r for r in rows if r['label'] == '영업이익')
assert oi['values'][2] == '-$1.10M', f'괄호 음수 파싱 실패: {oi["values"][2]}'
print('\n✅ FY 제거 · 빈 열 제거 · 소수마진 보정 · 괄호음수 전부 통과')
