import sys
try:                                   # Windows 콘솔 cp949 → 이모지 출력 에러 방지
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
from .cli import main
main(sys.argv[1:])
