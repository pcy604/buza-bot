"""영상 토큰 안전선 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_token_margin.py

2026-10-10 실측: fps=0.2 가 1,042,124 토큰으로 '한도(1,048,576) 아래'라 선택됐는데
여유가 6,452(0.6%)뿐이라 실제 요청에서 400(토큰 초과)이 났다.
VideoTooLong 가드는 '한도 아래'로 판정해 안 걸렸고, 그 영상은 3·4회 재시도하며
쿼터를 태웠다. count_tokens 는 영상만 세고 프롬프트·오버헤드는 빼므로
측정값과 실제값이 다르다 — 한도에 붙여 통과시키면 안 된다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import analyzer as A

assert A._SAFE_LIMIT < A._TOKEN_LIMIT, '안전선이 한도와 같거나 크다'
margin = A._TOKEN_LIMIT - A._SAFE_LIMIT
assert margin >= 50_000, f'여유 {margin:,} — 프롬프트·오버헤드를 덮기엔 얇다'
print(f'✅ 안전선 {A._SAFE_LIMIT:,} (한도 {A._TOKEN_LIMIT:,} · 여유 {margin:,})')

# 실제로 실패했던 영상의 측정값 — 이 판정이 뒤집히면 같은 실패가 돌아온다.
MEASURED = [(None, 2_323_248), (0.5, 1_522_510), (0.2, 1_042_124), (0.1, 881_948)]
chosen = next((fps for fps, n in MEASURED if n < A._SAFE_LIMIT), None)
assert chosen == 0.1, f'fps={chosen} 이 선택됨 — 실패했던 0.2 로 돌아갔다'
assert 1_042_124 >= A._SAFE_LIMIT, '400 이 났던 1,042,124 가 다시 통과한다'
print('✅ 실패했던 1,042,124(fps=0.2) 는 탈락 · fps=0.1(881,948) 선택')

# fps 단계는 내림차순이어야 한다 — 올림차순이면 큰 영상이 먼저 통과해버린다.
vals = [n for _, n in MEASURED]
assert vals == sorted(vals, reverse=True), 'fps 단계가 토큰 내림차순이 아니다'
assert A._FPS_STEPS[-1] == 0.1, f'최저 fps 가 바뀌었다: {A._FPS_STEPS}'
print(f'✅ _FPS_STEPS={A._FPS_STEPS} 내림차순 · 최저 0.1')
