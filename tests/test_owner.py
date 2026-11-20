"""소유자 = OWNER_CHAT → config.OWNER_CHAT. DB 첫 행으로 추측하지 않는다(2026-10-23 지인에게 시황·알림이 간 사고)."""
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.pop('OWNER_CHAT', None)
import config, brief
called = []
sys.modules['db'] = type(sys)('db'); sys.modules['db'].all_users = lambda: called.append(1) or [{'chat_id': 999}]
assert brief._owner_chat() == '5064831796' and not called, '기본값은 config, DB 를 보지 않는다'
os.environ['OWNER_CHAT'] = '42'
assert brief._owner_chat() == '42'
print('✅ 소유자 고정(환경변수 > config), DB 첫 행 추측 없음')
print('ALL PASS')
