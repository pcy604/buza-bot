# -*- coding: utf-8 -*-
"""12p 딥리포트를 텔레그램 앨범으로 내보낸다 — 편집국에서 배달창구로 나가는 문.

    python publish.py SATL              # 검수 게이트 통과 시 발송
    python publish.py SATL --dry        # 보낼 목록만 확인
    python publish.py SATL --chat 12345 # 다른 대상으로
    python publish.py SATL --force      # BLOCK 무시하고 강행(권장 안 함)

여기까지가 그동안 없던 한 칸이다. 렌더러는 `decks/out/{ticker}/`에 PNG를 쌓기만
했고 bot.py는 decks를 아예 import하지 않아서(grep 0건), 12p 리포트가 밖으로
나가는 경로가 아예 없었다. 보내는 함수(tg.send_media_group)는 이미 있었고
`/report` 8슬라이드가 쓰고 있었는데 12p만 그 문에 연결이 안 돼 있었다.

## 왜 봇 명령(/deck)이 아니라 로컬 스크립트인가

봇에 붙이는 게 더 그럴듯해 보이는데, 세 가지가 걸린다:

1. **러너는 PNG를 못 본다.** `decks/out/`은 .gitignore라 GitHub Actions 컨테이너엔
   존재하지 않는다. 봇이 보내려면 그 자리에서 새로 렌더해야 한다.
2. **그 자리 렌더는 예산을 넘는다.** autogen 초안만 Gemini 8회 남짓이고 run.yml은
   timeout 14분이다. 지금도 쿼터가 빠듯한데 명령 한 번에 하루치를 태운다.
3. **무검수 발행이 된다.** AAPL 초안에서 실제로 30건 넘는 오류가 나왔다. 사람 검수를
   건너뛴 리포트를 자동으로 내보내는 건 오보를 뿌리는 것과 같다.

그래서 발행은 빌드·검수가 끝난 자리(= 로컬)에서 사람이 마지막 버튼을 누르는 구조로
둔다. 파이프라인의 제자리는 여기다:

    feed.py → autogen.py → (검수) → check.py → build.py → publish.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

ALBUM_MAX = 10          # 텔레그램 sendMediaGroup 한 앨범 상한. 12장이면 10+2로 쪼갠다.


def deck_pages(ticker: str):
    """out/{ticker}/*.png를 페이지 순서대로. pptx는 앨범에 못 넣으니 제외."""
    out = HERE / 'out' / ticker.lower()
    if not out.is_dir():
        sys.exit(f'{out} 없음 — 먼저 `python build.py {ticker}` 실행할 것.')
    pages = sorted(out.glob('*.png'))
    if not pages:
        sys.exit(f'{out}에 PNG가 없다 — 렌더가 실패했을 수 있다.')
    return pages


def resolve_module(ticker: str):
    """build.py와 동일한 규칙으로 데이터 모듈을 찾는다(TICKERS 등록분 우선,
    없으면 {ticker}_data.py 자동 인식). 렌더와 검수가 서로 다른 파일을 보는
    사고를 막으려고 build의 설정을 그대로 재사용한다."""
    import importlib
    import build
    cfg = build.TICKERS.get(ticker) or build._auto_config(ticker)
    if not cfg:
        sys.exit(f'{ticker}: TICKERS 미등록 + {ticker.lower()}_data.py도 없음 — '
                 f'`python autogen.py {ticker}` 먼저.')
    return importlib.import_module(cfg['data_module'])


def resolve_chat(explicit=None):
    """--chat > PUBLISH_CHAT 환경변수 > 등록 사용자가 딱 한 명이면 그 사람.
    개인 chat_id를 레포에 박아두지 않으려고 이 순서로 찾는다."""
    import os
    if explicit:
        return explicit
    if os.environ.get('PUBLISH_CHAT'):
        return os.environ['PUBLISH_CHAT']
    try:
        import db
        users = db.all_users()
        if len(users) == 1:
            return users[0]['chat_id']
        sys.exit(f'등록 사용자가 {len(users)}명 — --chat으로 대상을 지정할 것.')
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f'대상을 못 정했다({e}) — --chat 또는 PUBLISH_CHAT을 줄 것.')


def caption(ticker: str, n_pages: int):
    import datetime
    today = datetime.date.today().isoformat()
    return (f'<b>{ticker.upper()}</b> 기업 심층 리포트 · {n_pages}p\n'
            f'stock_studian · {today}')


def main():
    args = [a for a in sys.argv[1:]]
    if not args or args[0].startswith('-'):
        sys.exit(__doc__.strip().split('\n\n')[1])
    ticker = args[0].upper()
    dry = '--dry' in args
    force = '--force' in args
    chat = None
    if '--chat' in args:
        chat = args[args.index('--chat') + 1]

    pages = deck_pages(ticker)
    print(f'{ticker}: {len(pages)}장 — {pages[0].name} … {pages[-1].name}')

    # ── 검수 게이트 ──
    # 모듈 해소는 build.py와 같은 규칙을 쓴다. check.report()에 티커만 주면
    # autogen의 작명 규칙({ticker}_data)으로만 찾는데, SATL처럼 TICKERS에서
    # 다른 모듈(satl16_data)을 가리키는 종목은 그 규칙으로 못 찾는다.
    import check
    n_block = check.report(ticker, resolve_module(ticker))
    if n_block and not force:
        sys.exit(f'\nBLOCK {n_block}건 — 발행 중단. 고치고 다시 돌리거나, '
                 f'정말 알고 내보내려면 --force.')
    if n_block and force:
        print(f'\n⚠ BLOCK {n_block}건을 무시하고 강행한다.')

    albums = [pages[i:i + ALBUM_MAX] for i in range(0, len(pages), ALBUM_MAX)]
    if dry:
        for i, al in enumerate(albums, 1):
            print(f'  [앨범 {i}] ' + ', '.join(p.name for p in al))
        print(f'\n--dry — 실제 발송 안 함. 대상: {resolve_chat(chat)}')
        return

    target = resolve_chat(chat)
    import tg
    sent, file_ids = 0, []
    for i, al in enumerate(albums):
        cap = caption(ticker, len(pages)) if i == 0 else ''
        res = tg.send_media_group(target, [str(p) for p in al], cap)
        if not res:
            sys.exit(f'앨범 {i + 1}/{len(albums)} 발송 실패 — 위 오류 참고.')
        if isinstance(res, list):
            file_ids.extend(res)
        sent += len(al)
        print(f'  앨범 {i + 1}/{len(albums)} 발송 ({len(al)}장)')
    print(f'\n{ticker} {sent}장 발송 완료 → chat {target}')

    # ── 봇이 다시 보낼 수 있도록 file_id 등록 ──
    # 이걸 안 하면 /report는 러너에 PNG가 없어서 12장을 못 보낸다.
    if len(file_ids) == len(pages):
        import deck_store
        deck_store.save(ticker, file_ids, len(pages), title=f'{ticker} 기업 심층 리포트')
        print(f'file_id {len(file_ids)}개 등록 → {deck_store.PATH.name}')
        if '--no-push' not in args:
            _push_store(ticker, deck_store.PATH)
        else:
            print('  (--no-push) 커밋 안 함 — 봇에 반영하려면 직접 커밋할 것')
    else:
        print(f'⚠ file_id를 {len(file_ids)}/{len(pages)}개만 받아 등록을 건너뛴다 — '
              f'/report로는 아직 이 종목을 못 보낸다.')


def _push_store(ticker, path):
    """deck_files.json만 커밋·푸시한다.

    봇은 러너의 체크아웃에서 이 파일을 읽으므로, 푸시가 안 되면 로컬에만 남아
    /report가 계속 "없는 종목"이라고 답한다. 사람 몫으로 남긴 수동 단계는
    반드시 잊혀진다는 걸 이 프로젝트에서 이미 여러 번 겪었으므로 자동화한다.
    다른 작업 중인 파일이 휩쓸리지 않게 이 파일 하나만 대상으로 한다."""
    import subprocess
    repo = str(HERE.parent)
    def run(*a):
        return subprocess.run(a, cwd=repo, capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
    # `git diff`는 추적 중인 파일만 본다. deck_files.json은 처음엔 untracked라
    # diff가 "변경 없음"을 돌려주고 커밋이 조용히 스킵됐다(실제로 겪음).
    # status --porcelain은 untracked도 잡으므로 이쪽으로 판정한다.
    if not run('git', 'status', '--porcelain', '--', str(path)).stdout.strip():
        print('  변경 없음 — 커밋 스킵')
        return
    run('git', 'add', str(path))
    r = run('git', 'commit', '-m', f'deck: {ticker.upper()} 12p file_id 등록')
    if r.returncode:
        print(f'  커밋 실패: {r.stderr.strip()[:120]}')
        return
    r = run('git', 'push', 'origin', 'main')
    if r.returncode:
        print(f'  ⚠ 푸시 실패 — 로컬 커밋만 됨. 직접 push 필요:\n     {r.stderr.strip()[:160]}')
    else:
        print('  커밋·푸시 완료 — 이제 /report로 받을 수 있다')


if __name__ == '__main__':
    main()
