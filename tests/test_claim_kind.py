"""사실/판단 구분이 **구조 필드**로 넘어갔는지 — 네트워크·LLM 없이 돈다.

    python tests/test_claim_kind.py

2026-09: '발언: ' 접두사 방식은 규칙 문장을 아무리 더해도 20%에서 안 움직였다.
모델이 내용이 아니라 원문 말투에 반응했기 때문이다. key_points[].kind 로 바꿨다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import engine
import quality

NEW = {'video_id': 'v1', 'title': '테스트', 'source': 'video', 'analysis': {
    'one_liner': '한 줄', 'summary': ['요약'],
    'key_points': [{'point': 'Q3 매출 $1.2B 발표', 'kind': 'fact', 't': 10},
                   {'point': '내년 성장률 둔화 가능성', 'kind': 'claim', 't': 20},
                   {'point': '자사주 매입 1조원 공시', 'kind': 'fact', 't': 30}]}}
OLD = {'video_id': 'v2', 'title': '테스트', 'source': 'video', 'analysis': {
    'key_points': [{'point': '발언: 내년엔 오른다', 't': 10}, {'point': '매출 $1B', 't': 20}]}}

m = quality.score_yt(NEW)
assert m['claim_tagged'] == 1.0, f"전부 라벨됐는데 {m['claim_tagged']}"
assert m['claim_ratio'] == round(1 / 3, 3), f"claim 비율 오류 {m['claim_ratio']}"
print(f"✅ kind 집계: 라벨율 {m['claim_tagged']} · claim 비율 {m['claim_ratio']}")

mo = quality.score_yt(OLD)
assert mo['claim_tagged'] == 0.5 and mo['claim_ratio'] is None, mo
print('✅ 옛 레코드(접두사)는 폴백으로 계속 집계 — 추세가 끊기지 않음')

# 발송 메시지에서 claim 이 눈에 보이는가
msg = engine.build_message(NEW)
assert '💬 내년 성장률 둔화 가능성' in msg, 'claim 표시가 안 붙음'
assert '💬 Q3 매출' not in msg, 'fact 에 claim 표시가 붙음'
print('✅ 발송 메시지: claim 만 표시되고 fact 는 그대로')

msg_old = engine.build_message(OLD)
assert '💬' not in msg_old and '발언: 내년엔 오른다' in msg_old, '옛 레코드가 깨짐'
print('✅ 옛 레코드는 본문 그대로 나감(이중 표시 없음)')

# kind 가 빠진 항목이 섞여도 죽지 않는다
MIX = {'video_id': 'v3', 'title': 't', 'analysis': {'key_points': [
    {'point': 'a', 'kind': 'claim'}, {'point': 'b'}]}}
mm = quality.score_yt(MIX)
assert mm['claim_tagged'] == 0.5, mm
print('✅ kind 누락이 섞여도 집계·렌더 모두 안전')
