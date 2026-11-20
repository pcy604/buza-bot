"""사용자 상태 JSON 을 git 대신 Supabase(state_files)에 보관 — 2026-11-20

왜: 레포를 공개로 바꿔 Actions 분을 무료로 쓰려면 지인 텔레그램 ID·명령 기록·관심종목이
레포(와 그 이력)에 있으면 안 된다. 이 파일들은 실행 시작에 내려받고, 끝에 병합해 올린다.

  python tools/state_store.py pull   # 실행 전 — 실패하면 exit 1 (빈 상태로 돌다가 덮어쓰는 사고 방지)
  python tools/state_store.py push   # 실행 후(always) — pull 이 성공한 파일만, 바뀐 것만
  python tools/state_store.py seed   # 1회 — 지금 디스크의 파일을 그대로 올림(이전용)

병렬 실행(웹훅) 대비: 올릴 때 원격 최신본을 다시 읽어 tools/state_merge.merge 로 3-way 병합한다
(공통 조상 = 이번 실행이 pull 한 내용). git 시절 merge=jsonstate 와 같은 규칙.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

# 사람(채팅 ID)이 들어 있는 상태 파일 — 여기 있는 이름은 .gitignore 에도 있어야 한다
PERSONAL = ['user_prefs.json', 'cmd_log.json', 'activity_log.json', 'ir_state.json',
            'nudge_state.json', 'people_state.json', 'corner_prefs.json', 'voc_log.json']
BASE = os.path.join(ROOT, '.state_base')


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _sb():
    import config
    from supabase import create_client
    return create_client(config.SUPABASE_URL, config.SUPABASE_KEY)


def _remote(sb):
    r = sb.table('state_files').select('name,data').in_('name', PERSONAL).execute()
    return {x['name']: x['data'] for x in r.data or []}


def pull():
    got = _remote(_sb())
    os.makedirs(BASE, exist_ok=True)
    for n in PERSONAL:
        p = os.path.join(ROOT, n)
        if n in got:
            txt = json.dumps(got[n], ensure_ascii=False)
            open(p, 'w', encoding='utf-8').write(txt)
            open(os.path.join(BASE, n), 'w', encoding='utf-8').write(txt)
        else:
            # 원격에 아직 없는 파일 — 앱이 새로 만들면 push 가 올린다(조상 = 없음)
            if os.path.exists(p):
                os.remove(p)
            open(os.path.join(BASE, n + '.none'), 'w').close()
    print(f'⬇️ 상태 내려받기 {len(got)}/{len(PERSONAL)}개')


def push():
    if not os.path.isdir(BASE):
        print('⏭️ pull 기록 없음 — 올리지 않음(빈 상태로 덮어쓰기 방지)')
        return
    from state_merge import merge
    sb = _sb()
    todo = []
    for n in PERSONAL:
        p, b = os.path.join(ROOT, n), os.path.join(BASE, n)
        if not os.path.exists(p):
            continue
        if not (os.path.exists(b) or os.path.exists(b + '.none')):
            continue
        try:
            mine = json.load(open(p, encoding='utf-8'))
        except Exception as e:
            print(f'⚠️ {n} 읽기 실패 — 건너뜀: {e}')
            continue
        base = json.load(open(b, encoding='utf-8')) if os.path.exists(b) else None
        if mine != base:
            todo.append((n, base, mine))
    if not todo:
        print('상태 변경 없음')
        return
    remote = _remote(sb)
    rows = []
    for n, base, mine in todo:
        cur = remote.get(n)
        data = mine if cur is None or cur == base else merge(base if base is not None else type(mine)(), cur, mine)
        rows.append({'name': n, 'data': data, 'updated_at': _now()})
    sb.table('state_files').upsert(rows).execute()
    print('⬆️ 상태 올리기: ' + ', '.join(r['name'] for r in rows))


def seed():
    rows = []
    for n in PERSONAL:
        p = os.path.join(ROOT, n)
        if os.path.exists(p):
            rows.append({'name': n, 'data': json.load(open(p, encoding='utf-8')), 'updated_at': _now()})
    _sb().table('state_files').upsert(rows).execute()
    print('seed:', [r['name'] for r in rows])


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        {'pull': pull, 'push': push, 'seed': seed}[cmd]()
    except KeyError:
        sys.exit('사용: state_store.py pull|push|seed')
    except Exception as e:
        print(f'::error::상태 저장소 {cmd} 실패: {e}')
        sys.exit(1)
