"""사용법 (buza-bot 루트에서):
  python -m social dry     content/soxx_mdd_001.json        # 플랫폼별 결과를 화면에만 (API·DB 불필요)
  python -m social draft   content/soxx_mdd_001.json        # 큐에 draft 적재 + 텔레그램 미리보기
  python -m social list    [draft|approved|published]
  python -m social approve 12 13 14                          # 사람이 승인
  python -m social publish 12 ...  /  python -m social publish approved   # 승인된 것만 API 게시
  python -m social naver   content/soxx_mdd_001.json         # 네이버용 마크다운을 social/out/<slug>_naver.md 로
  python -m social check                                     # 발행 직전: 토큰이 살아 있는지 (게시 없음)
  python -m social refresh                                   # Threads·IG 장기 토큰 60일 연장 — 새 토큰을 화면에 출력, .env 는 사람이 갱신
"""
import sys
from pathlib import Path
from .models import Content
from .adapt import adapt

_PUB = {}


def _publisher(platform):
    if platform not in _PUB:
        mod = __import__(f'social.publish_{platform}', fromlist=['publish'])
        _PUB[platform] = mod.publish
    return _PUB[platform]


def _show(post):
    print(f'\n===== {post.platform.upper()}  ({len(post.texts)}개 글, 이미지 {len(post.images)}장)  {post.note}')
    for i, t in enumerate(post.texts, 1):
        print(f'--- [{i}] ({len(t)}자)\n{t}')


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == 'dry':
        for p in adapt(Content.load(args[0]), args[1:] or None):
            _show(p)
    elif cmd == 'naver':
        c = Content.load(args[0])
        p = adapt(c, ['naver'])[0]
        out = Path('social/out') / f'{c.slug}_naver.md'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(p.texts[0], encoding='utf-8')
        print('wrote', out)
    elif cmd == 'draft':
        from . import queue
        import tg, config
        c = Content.load(args[0])
        ids = []
        for p in adapt(c, args[1:] or ['threads', 'x', 'instagram']):
            pid = queue.enqueue(c.slug, p)
            ids.append(pid)
            _show(p)
            preview = f'📝 social #{pid} [{p.platform}] {c.slug}\n\n' + p.texts[0][:800]
            tg.send_message(config.OWNER_CHAT, preview + f'\n\n승인: python -m social approve {pid}')
        print('\nqueued:', ids)
    elif cmd == 'check':
        from . import tokens
        for k, v in tokens.check_all().items():
            print(('OK  ' if v.get('ok') else 'FAIL'), k, v.get('why') or v.get('resp'))
    elif cmd == 'refresh':
        from . import tokens
        for k, f in (('threads', tokens.refresh_threads), ('instagram', tokens.refresh_instagram)):
            j = f(); print(k, 'expires_in(days)=', round(j.get('expires_in', 0) / 86400, 1), 'error=' + str(j['error']) if 'error' in j else '→ .env 에 새 access_token 붙여넣기')
    elif cmd == 'list':
        from . import queue
        for r in queue.list_by(args[0] if args else None):
            print(r['id'], r['status'], r['platform'], r['content_slug'],
                  r.get('external_id') or '', (r.get('error') or '')[:80])
    elif cmd == 'approve':
        from . import queue
        for a in args:
            queue.set_status(int(a), 'approved')
            print('approved', a)
    elif cmd == 'publish':
        from . import queue
        rows = queue.list_by('approved') if args and args[0] == 'approved' else [queue.get(int(a)) for a in args]
        for r in rows:
            if not r or r['status'] != 'approved':
                print('skip (not approved):', r and r['id'])
                continue
            pl = r['payload']
            try:
                ext = _publisher(r['platform'])(pl['texts'], pl['images'])
                queue.set_status(r['id'], 'published', external_id=str(ext))
                print('published', r['id'], r['platform'], ext)
            except Exception as e:
                queue.set_status(r['id'], 'failed', error=str(e))
                print('FAILED', r['id'], r['platform'], e)
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
