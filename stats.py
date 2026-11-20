"""사용자 수·활동 현황 — /stats(소유자 전용) + 매일 아침 소유자에게 일간 리포트 (2026-10-23).

데이터
- activity_log.json: 봇이 받은 메시지마다 {ts, chat, cmd} 한 줄(내용은 저장하지 않는다 — 명령 이름만).
  cmd_log.json(/recap 용)은 일부 명령만 기록해 활동량을 재기엔 빠짐이 많았다(10-23 기준 3개월 82줄).
- Supabase users: 가입자 수·가입일.
- 감시 종목·유튜브 구독·시황 구독 수.

지표 정의(앱 업계 표준): DAU = 최근 24시간 1회 이상 명령 보낸 사람, WAU = 7일, MAU = 30일.
소유자 본인은 따로 센다 — 본인 테스트가 지표를 부풀리면 '외부 사용자 0명'(PM/SALES.md)이 가려진다.
"""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parent / 'activity_log.json'
MAX_ENTRIES = 20000
KST = timezone(timedelta(hours=9))


def _load() -> list:
    try:
        return json.loads(LOG_PATH.read_text(encoding='utf-8')) or []
    except Exception:
        return []


def log(chat, cmd: str):
    # 테스트 스크립트(tests/)가 bot.handle 을 부르면 가짜 chat(1·3·7…)이 실제 로그에 쌓였다(2026-10-23 /report 18회 중 18회가 테스트).
    import sys
    if any(('/' + str(a).replace('\\', '/')).count('/tests/') for a in sys.argv[:1]):
        return
    rows = _load()
    rows.append({'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'chat': chat, 'cmd': cmd})
    LOG_PATH.write_text(json.dumps(rows[-MAX_ENTRIES:], ensure_ascii=False), encoding='utf-8')


# 인자 없이 치면 '사용법'만 보여 주는 명령 — 그건 사용이 아니라 구경이라 세지 않는다(2026-10-23 차니 지적).
#   답장으로 종목을 보내면 '/report TSLA' 로 바뀌어 그때 한 번 센다.
NEEDS_ARG = {'/report', '/watch', '/unwatch', '/ir', '/dd', '/yt', '/add', '/person', '/remove', '/voc'}


def cmd_of(text: str):
    """세지 않을 메시지면 None."""
    t = (text or '').strip()
    if t.startswith('/'):
        c = t.split()[0].split('@')[0].lower()[:24]
        if c in NEEDS_ARG and len(t.split()) == 1:
            return None
        return c
    if 'youtu' in t:
        return '(유튜브 링크)'
    return '(텍스트)'


def _ts(r):
    try:
        return datetime.fromisoformat(r['ts'])
    except Exception:
        return None


def _owner() -> str:
    try:
        import brief
        return str(brief._owner_chat() or '')
    except Exception:
        return ''


def compute(now=None, users=None) -> dict:
    now = now or datetime.now(timezone.utc)
    owner = _owner()
    rows = [(r, _ts(r)) for r in _load()]
    rows = [(r, t) for r, t in rows if t]

    def active(days, ext=True):
        cut = now - timedelta(days=days)
        return {str(r['chat']) for r, t in rows if t >= cut and (str(r['chat']) != owner) == ext}

    if users is None:
        try:
            import db
            users = db.all_users() or []
        except Exception:
            users = []
    ext_users = [u for u in users if str(u.get('chat_id')) != owner]

    def joined(days):
        cut = now - timedelta(days=days)
        n = 0
        for u in ext_users:
            try:
                if datetime.fromisoformat(str(u.get('created_at')).replace('Z', '+00:00')) >= cut:
                    n += 1
            except Exception:
                pass
        return n

    wk = now - timedelta(days=7)
    cmds = Counter(r['cmd'] for r, t in rows if t >= wk and str(r['chat']) != owner)
    msgs_1d = sum(1 for r, t in rows if t >= now - timedelta(days=1) and str(r['chat']) != owner)
    names = {str(u.get('chat_id')): (u.get('username') or '') for u in users}
    last = {}
    for r, t in rows:
        c = str(r['chat'])
        if c != owner and (c not in last or t > last[c][0]):
            last[c] = (t, r['cmd'])
    per_user = Counter(str(r['chat']) for r, t in rows if t >= wk and str(r['chat']) != owner)

    extra = {}
    try:
        import ir
        st = ir.load_state()
        w = (st or {}).get('watches') or {}
        extra['watch_users'] = sum(1 for c, v in w.items() if v and str(c) != owner)
        extra['watch_tickers'] = len({t for c, v in w.items() if str(c) != owner for t in (v or [])})
    except Exception:
        pass
    try:
        import market
        extra['market_subs'] = sum(1 for c in market.subscribers() if str(c) != owner)
    except Exception:
        pass

    return dict(
        asof=now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST'),
        users=len(ext_users), new_1d=joined(1), new_7d=joined(7),
        dau=len(active(1)), wau=len(active(7)), mau=len(active(30)),
        owner_msgs_7d=sum(1 for r, t in rows if t >= wk and str(r['chat']) == owner),
        msgs_1d=msgs_1d, top_cmds=cmds.most_common(6),
        top_users=[(names.get(c) or c, n) for c, n in per_user.most_common(5)],
        last_seen=sorted(((names.get(c) or c, t.astimezone(KST).strftime('%m/%d %H:%M'), cmd)
                          for c, (t, cmd) in last.items()), key=lambda x: x[1], reverse=True)[:5],
        **extra)


FUNNEL_VALUE = {'/report', '/dashboard', '/market', '/watch', '/ir', '/yt', '/add', '/person',
                '(유튜브 링크)', '/watchlist', '/recap'}


def funnel(now=None, rows=None, watched=None) -> dict:
    """활성화 퍼널(본인 제외) — 시작 → 첫 사용 → 감시 등록 → D7 재방문. 2026-11-12.

    D7 재방문 = 첫 사용 후 7일 이상 지난 날 다시 명령을 보낸 사람 / 첫 사용이 7일 이상 지난 사람."""
    now = now or datetime.now(timezone.utc)
    owner = _owner()
    rows = _load() if rows is None else rows
    if watched is None:
        try:
            import ir
            watched = {str(c) for c, v in ((ir.load_state() or {}).get('watches') or {}).items() if v}
        except Exception:
            watched = set()
    seen, first_val, later = set(), {}, {}
    for r in rows:
        t, c = _ts(r), str(r.get('chat'))
        if not t or c == owner:
            continue
        seen.add(c)
        if r.get('cmd') in FUNNEL_VALUE and c not in first_val:
            first_val[c] = t
        later.setdefault(c, []).append(t)
    base = [c for c, t in first_val.items() if now - t >= timedelta(days=7)]
    d7 = [c for c in base if any(x - first_val[c] >= timedelta(days=7) for x in later[c])]
    return dict(started=len(seen), activated=len(first_val),
                watching=len({c for c in seen if c in watched}), d7=len(d7), d7_base=len(base))


def text(s: dict = None) -> str:
    s = s or compute()
    esc = lambda v: str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    stick = f"{s['dau'] / s['mau'] * 100:.0f}%" if s['mau'] else '-'
    L = [f"📈 <b>부자알람 사용 현황</b> · {s['asof']}", '━━━━━━━━━━━━',
         f"👥 가입자 <b>{s['users']}명</b> (오늘 +{s['new_1d']} · 7일 +{s['new_7d']}) <i>· 본인 제외</i>",
         f"🔥 DAU <b>{s['dau']}</b> · WAU <b>{s['wau']}</b> · MAU <b>{s['mau']}</b> · 고착도(DAU/MAU) {stick}",
         f"💬 최근 24시간 명령 {s['msgs_1d']}건"]
    if 'watch_users' in s or 'market_subs' in s:
        L.append(f"👁 감시 사용 {s.get('watch_users', '-')}명·{s.get('watch_tickers', '-')}종목 · 📰 시황 구독 {s.get('market_subs', '-')}명")
    if s['top_cmds']:
        L += ['', '<b>많이 쓴 기능 (7일)</b>', ' · '.join(f'{esc(c)} {n}' for c, n in s['top_cmds'])]
    if s['last_seen']:
        L += ['', '<b>최근 활동</b>'] + [f"• @{esc(u)} {t} {esc(c)}" for u, t, c in s['last_seen']]
    try:
        f = funnel()
        L += ['', '<b>퍼널 (누적)</b>',
              f"시작 {f['started']} → 첫 사용 {f['activated']} → 감시 {f['watching']} → D7 재방문 {f['d7']}/{f['d7_base']}"]
    except Exception:
        pass
    L += ['', f"<i>본인 명령 7일 {s['owner_msgs_7d']}건은 위 숫자에서 뺐어요 · 상시 조회 /stats</i>"]
    return '\n'.join(L)
