"""run.main() 안에서 모듈 전역(config 등)을 다시 import 하면 그 이름이 main 전체의 지역 변수가 돼
첫 줄부터 NameError 로 죽는다(2026-10-21 실제 사고: 'import market, config' 한 줄로 봇 전체 정지)."""
import ast
from pathlib import Path

src = (Path(__file__).resolve().parent.parent / 'run.py').read_text(encoding='utf-8')
tree = ast.parse(src)
top = {a.asname or a.name for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
bad = []
for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
    for n in ast.walk(fn):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            bad += [f'{fn.name}: {a.asname or a.name}' for a in n.names if (a.asname or a.name) in top]
assert not bad, f'함수 안에서 전역 모듈을 다시 import — 지역 변수로 가려진다: {bad}'
print('✅ run.py 함수 안 전역 모듈 재import 없음')
print('ALL PASS')
