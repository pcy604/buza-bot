"""분석 엔진 — 마스터 채널 1회 분석(캐시) + 유저별 팬아웃."""
from datetime import datetime, timezone

import re
import db
import tg
import analyzer
import config
import corners
import people

KST = analyzer.KST


# ── 메시지 포맷 ──────────────────────────────────────────────────────
def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _stamp(url, sec):
    return f"{url}&t={int(sec or 0)}s"


def _pub(iso):
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(KST).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return (iso or '')[:16].replace('T', ' ')


def build_message(row: dict, channel_name: str = '', chat=None) -> str:
    a = row.get('analysis') or {}
    url = f"https://www.youtube.com/watch?v={row['video_id']}"
    head = f"[{channel_name}] " if channel_name else ''
    lines = [f"<b>{head}{_esc(row.get('title', ''))}</b>"]
    pub = _pub(row.get('published', ''))
    if pub:
        lines.append(f"🕐 업로드 {pub} KST")
    if a.get('one_liner'):
        lines.append(f"💡 {_esc(a['one_liner'])}")
    for kp in a.get('key_points', [])[:4]:
        t = kp.get('t') if isinstance(kp, dict) else None
        if isinstance(t, (int, float)) and not (0 <= t <= 6 * 3600):   # 옛 레코드의 환각 시점
            t = None
        txt = _esc(kp.get('point', '') if isinstance(kp, dict) else str(kp))
        # kind='claim' 이면 출연자 판단이다. 사실과 같은 모양으로 내보내면 사용자가
        # 그걸 근거로 매매한다 — 화면에서 구분되게 표시한다(옛 레코드는 kind 가 없어
        # 그대로 나가고, 그건 '발언: ' 접두사가 본문에 들어 있던 시기다).
        mark = '💬 ' if (isinstance(kp, dict) and kp.get('kind') == 'claim') else ''
        lines.append(f"• {mark}{txt}" + (f" <a href=\"{_stamp(url, t)}\">[{analyzer.fmt_ts(t)}]</a>" if t else ''))
    tickers = a.get('tickers', [])
    # 2026-10-20: 영상 요약과 종목 감시를 잇는다. 받는 사람이 감시 중인 종목은 ⭐ 로
    # 표시하고, 아직 안 보는 미국 종목은 한 번 눌러 감시 등록할 수 있게 한다.
    # 영상은 '들은 말'이고 감시는 '확인한 사실'이다 — 들은 종목을 사실로 추적하게 만든다.
    watched = set()
    if chat is not None:
        try:
            import ir
            watched = set(ir.watches_of(chat))
        except Exception:
            watched = set()
    us = [str(t.get('ticker') or '').upper() for t in tickers[:8]]
    us = [c for c in us if re.fullmatch(r'[A-Z]{1,5}', c)]
    if tickers:
        tags = []
        for tk in tickers[:8]:
            mk = {'긍정': '🟢', '부정': '🔴'}.get(tk.get('view', ''), '⚪')
            if str(tk.get('ticker') or '').upper() in watched:
                mk = '⭐' + mk
            nm = _esc(tk.get('name', ''))
            code = f"({tk['ticker']})" if tk.get('ticker') else ''
            t = tk.get('t')
            tags.append(f"{mk}<a href=\"{_stamp(url, t)}\">{nm}{_esc(code)}</a>" if t else f"{mk}{nm}{_esc(code)}")
        lines.append('📌 ' + ', '.join(tags))
        add = [c for c in dict.fromkeys(us) if c not in watched]
        if chat is not None and add:
            lines.append('👁️ 감시 추가: ' + ' '.join(f'/watch_{c}' for c in add[:4]))
    lines.append(f"<a href=\"{url}\">▶️ 전체 영상</a>")
    # 기본 끔. 품질 지표는 우리가 검증용으로 보는 것이지 사용자에게 내보일
    # 것이 아니라는 결정(2026-09-18). source·_coverage 는 끈 상태에서도 계속
    # 저장되므로 quality.py 의 채점에는 영향이 없다.
    if config.SHOW_QUALITY:
        q = _quality_line(row)
        if q:
            lines.append(q)
    return '\n'.join(lines)


def _quality_line(row: dict) -> str:
    """이 요약이 **무엇을 근거로** 만들어졌는지 한 줄.

    analyze() 는 예전부터 source('transcript'|'video')와 _coverage(요약이 영상의
    몇 %까지 다뤘는지)를 계산해 DB에 넣고 있었는데, 정작 사용자에게 가는
    메시지에는 둘 다 안 나왔다. 그래서 자막 전문을 읽고 만든 요약과, 자막이
    막혀 영상만 훑다가 앞 30%에서 끊긴 요약이 화면상 **완전히 똑같아 보였다**.
    품질을 보장할 수 없을 때 그걸 숨기지 않는 게 품질 보장의 출발점이다.

    ⚠️ coverage 는 '요약이 언급한 마지막 t / 영상 길이'라 근사치다. 뒷부분이
       잡담이라 정당하게 안 다룬 경우도 낮게 나온다. 그래서 '틀렸다'가 아니라
       '어디까지 다뤘다'로만 적는다.
    """
    a = row.get('analysis') or {}
    src = row.get('source') or ''
    base = {'transcript': '자막 전문', 'video': '영상 직접 분석(자막 없음)'}.get(src)
    cov = a.get('_coverage')
    if not base and cov is None:
        return ''
    bits = [f'근거: {base}'] if base else []
    if isinstance(cov, (int, float)):
        pct = round(cov * 100)
        bits.append(f'영상의 {pct}% 지점까지 다룸' + ('  ⚠️ 뒷부분 확인 권장' if cov < 0.5 else ''))
    return '🔍 <i>' + ' · '.join(bits) + '</i>'


def _within(published, hours):
    try:
        pub = datetime.fromisoformat((published or '').replace('Z', '+00:00'))
    except Exception:
        return False
    return (datetime.now(timezone.utc) - pub).total_seconds() <= hours * 3600


# ── 분석 (1회 캐시) ──────────────────────────────────────────────────
def refresh():
    channels = db.all_channels()
    print(f'📡 마스터 채널 {len(channels)}개 갱신')
    for ch in channels:
        cid, name = ch['channel_id'], ch.get('name') or ch['channel_id']
        vids = analyzer.fetch_recent_videos(cid, name)
        _alert_new_corners(cid, name, vids)
        # 코너 필터는 **수집 단계**에 건다. 발송 단계에서 걸면 아무도 원하지 않는
        # 영상을 분석한 뒤 버리는 꼴이라 Gemini 쿼터가 그대로 나간다.
        # 다만 분석은 채널당 1회만 하고 여러 사용자에게 뿌리므로, 한 사람 기준이
        # 아니라 **구독자 전체의 합집합**으로 거른다(union_for_channel).
        want = corners.union_for_channel(cid, db.subscribers_of(cid))
        if want:
            before = len(vids)
            vids = [v for v in vids if corners.keep(v['title'], want)]
            if before != len(vids):
                print(f'  [{name}] 코너 선택으로 {before - len(vids)}건 제외 (남은 {len(vids)}건)')
        vids = vids[:config.MAX_PER_CHANNEL]
        for v in vids:
            ex = db.get_analysis(v['video_id'])
            if ex and (analyzer.has_content(ex.get('analysis') or {}) or (ex.get('attempts') or 0) >= config.RETRY_MAX):
                continue
            analysis, source = analyzer.analyze(v)
            attempts = ((ex or {}).get('attempts') or 0) + 1
            db.save_analysis({'video_id': v['video_id'], 'channel_id': cid, 'title': v['title'],
                              'published': v['published'], 'analysis': analysis, 'source': source, 'attempts': attempts})
            ok = '✓' if analyzer.has_content(analysis) else f'✗({attempts})'
            print(f"  [{name[:8]}] {source} {ok} {v['title'][:30]}")
    refresh_people()
    _retry_unfinished()



def _alert_new_corners(cid: str, name: str, vids: list):
    """설정할 때 없던 코너가 나타나면 **발견 즉시** 알린다.

    코너 선택은 제목의 대괄호 표지에 기댄다. 채널이 표기를 바꾸면 고른 코너가
    사라지고 새 코너가 생기는데, 그대로 두면 요약이 조용히 안 오기 시작한다.
    설정한 사람에게만 보낸다(미설정자는 어차피 전부 받으므로 알릴 게 없다).

    ⚠️ 같은 새 코너로 매 실행(6시간마다) 알림이 가면 안 된다. 알린 코너는
       seen 에 합쳐 기준선을 올린다 — 한 번만 알리고, 다음 변화 때 다시 알린다.
    """
    titles = [v['title'] for v in vids]
    if not titles:
        return
    for chat in db.subscribers_of(cid):   # chat_id 리스트를 준다(dict 아님)
        pref = corners.get(chat, cid)
        if not pref['chosen']:
            continue
        added = corners.detect_new(pref['seen'], titles)
        if not added:
            continue
        lines = [f'🆕 <b>{name}</b> 에 새로운 영상 종류가 보여요.',
                 '제목 형식이 바뀌었을 수 있어요 — 원하시면 다시 고르세요.', '']
        lines += [f'• {k} <i>({n}건)</i>' for k, n in added[:6]]
        lines.append('')
        lines.append('<code>/corners</code> 로 다시 설정')
        tg.send_message(chat, chr(10).join(lines))
        corners.put(chat, cid, pref['chosen'], pref['seen'] | {k for k, _ in added})
        print(f'  [{name}] 새 코너 알림 → chat={chat}: {[k for k, _ in added]}')


# 인물 추적이 한 실행에서 쓸 수 있는 요약 건수. 채널 요약·/ir 과 하루 상한(모델당
# 20회 × 4모델)을 나눠 쓰므로 여기서 먼저 브레이크를 잡는다. 실측상 인물 1명이
# 타채널에 나오는 빈도가 하루 1~2건이라 2면 대개 충분하다.
PERSON_PER_RUN = 2


def refresh_people():
    """구독자가 등록한 인물의 **타채널 출연** 영상을 찾아 요약한다.

    ⚠️ 본진(이미 구독 중인 채널)은 건너뛴다. 채널 경로가 이미 처리하고 거기엔
       코너 선택까지 걸려 있다 — 여기서 또 집으면 그 선택을 우회해 들어오고
       같은 영상에 쿼터를 두 번 쓴다.
    ⚠️ 이미 요약한 영상은 db.get_analysis 로 걸러진다. 인물 경로를 위해 중복
       방지를 새로 만들 필요가 없다 — video_id 가 같으면 같은 영상이다.
    """
    subs_by_chat = {}
    watchers = {}
    for ch in db.all_channels():
        for chat in db.subscribers_of(ch['channel_id']):
            subs_by_chat.setdefault(chat, set()).add((ch.get('name') or '').strip())
    for chat, names in ((c, people.watches_of(c)) for c in {*subs_by_chat, *_people_chats()}):
        if names:
            watchers[chat] = names
    if not watchers:
        return
    done = 0
    for chat, names in watchers.items():
        mine = subs_by_chat.get(chat, set())
        for name in names:
            if done >= PERSON_PER_RUN:
                print(f'   인물 추적: 이번 실행 상한 {PERSON_PER_RUN}건 도달 — 다음 실행으로')
                return
            found, ok = people.find_many(people.queries_of(chat, name), analyzer.UA)
            if not ok:
                continue
            if not found:
                print(f'   [{name}] 검색 결과 없음')
                continue
            cands = []
            for v in found:
                if not people.is_really(name, v):
                    continue                      # 동명이인·오탐
                if (v.get('channel') or '').strip() in mine:
                    continue                      # 본진 — 채널 경로가 처리한다
                ex = db.get_analysis(v['video_id'])
                if ex and (analyzer.has_content(ex.get('analysis') or {})
                           or (ex.get('attempts') or 0) >= config.RETRY_MAX):
                    continue                      # 이미 요약했거나 재시도 소진
                cands.append(v)
            print(f'   [{name}] 타채널 신규 {len(cands)}건 '
                  f'(검색 {len(found)} · 본진/중복 제외 후)')
            for v in cands:
                if done >= PERSON_PER_RUN:
                    break
                analysis, source = analyzer.analyze(v)
                db.save_analysis({'video_id': v['video_id'], 'channel_id': '',
                                  'title': v['title'], 'published': None,
                                  'analysis': analysis, 'source': source, 'attempts': 1})
                done += 1
                mark = '✓' if analyzer.has_content(analysis) else '✗'
                print(f"      {mark} [{v['channel'][:12]}] {v['title'][:34]}")
                if analyzer.has_content(analysis) and analysis.get('relevant', True):   # 간증·잡담 영상은 안 보냄(10-24)
                    tg.send_message(chat, build_message(
                        {'video_id': v['video_id'], 'title': v['title'],
                         'analysis': analysis, 'source': source},
                        f"{v['channel']} · {name} 출연", chat=chat))


def _people_chats():
    """인물을 등록했지만 채널 구독은 없는 사용자도 포함한다."""
    try:
        return [int(k) for k in people.load().keys()]
    except Exception:
        return []

def _retry_unfinished():
    """최근 목록 밖으로 밀려난 실패 영상을 다시 붙든다.

    위 루프는 채널당 최근 MAX_PER_CHANNEL(=2)개만 본다. 6시간 주기라 실패한 영상은
    다음 실행 때 이미 top-2 밖이고, 그래서 RETRY_MAX=4 라는 재시도 예산이 **한 번도
    쓰이지 못했다**(실측 2026-09-06: 실패 67건 중 58건이 attempts=1). 분석은 실패했는데
    빈 결과가 저장되고 fanout 의 has_content 가 걸러내니, 폰에는 아무것도 안 가고
    아무도 그 사실을 모른다 — 최근 8건 중 5건이 그렇게 유실됐다.

    창을 RETRY_WINDOW_H 로 막는 이유: 오래된 영상은 다시 살려봐야 이미 지난 얘기고,
    무한정 붙들면 매 실행이 옛 실패로 채워져 새 영상이 밀린다.
    """
    now = datetime.now(timezone.utc)
    chan = {c['channel_id']: (c.get('name') or c['channel_id']) for c in db.all_channels()}
    todo = []
    for r in db.unfinished_analyses():
        if analyzer.has_content(r.get('analysis') or {}):
            continue
        if (r.get('attempts') or 0) >= config.RETRY_MAX:
            continue
        if r.get('source') == 'too_long':
            # 길이 때문에 실패한 건 다시 돌려도 같은 결과다(입력 한도는 안 변한다).
            # 재시도 예산 RETRY_PER_RUN=2 를 여기에 쓰면, 고칠 수 있는 서버 오류
            # 실패가 그만큼 밀린다. 구간 분할이 생기면 이 줄을 지우면 된다.
            continue
        try:
            age = (now - datetime.fromisoformat(str(r['published']).replace('Z', '+00:00'))).total_seconds() / 3600
        except Exception:
            continue
        if age > config.RETRY_WINDOW_H:
            continue
        todo.append((age, r))
    if not todo:
        return
    todo.sort()                      # 최신 실패부터 — 오래된 건 어차피 창에서 곧 빠진다
    print(f'♻️ 미완료 재시도 대상 {len(todo)}건 중 {min(len(todo), config.RETRY_PER_RUN)}건')
    for _age, r in todo[:config.RETRY_PER_RUN]:
        vid = r['video_id']
        v = {'video_id': vid, 'title': r.get('title') or vid, 'published': r.get('published'),
             'url': f'https://www.youtube.com/watch?v={vid}',
             'channel': chan.get(r.get('channel_id'), '')}
        analysis, source = analyzer.analyze(v)
        attempts = (r.get('attempts') or 0) + 1
        db.save_analysis({'video_id': vid, 'channel_id': r.get('channel_id'), 'title': v['title'],
                          'published': v['published'], 'analysis': analysis,
                          'source': source, 'attempts': attempts})
        ok = '✓' if analyzer.has_content(analysis) else f'✗({attempts}/{config.RETRY_MAX})'
        print(f"  ♻️ {source} {ok} {v['title'][:30]}")


# ── 팬아웃 (유저별) ──────────────────────────────────────────────────
def fanout():
    users = db.all_users()
    print(f'📨 유저 {len(users)}명 팬아웃')
    for u in users:
        chat = u['chat_id']
        sent = 0
        for sub in db.list_subscriptions(chat):
            for a in db.analyses_for_channel(sub['channel_id']):
                if not _within(a.get('published', ''), config.LOOKBACK_HOURS):
                    continue
                ana = a.get('analysis') or {}
                if not ana.get('relevant', True) or not analyzer.has_content(ana):
                    continue
                if db.already_delivered(chat, a['video_id']):
                    continue
                if tg.send_message(chat, build_message(a, sub['channel_name'], chat=chat)):
                    db.record_delivery(chat, a['video_id'])
                    sent += 1
        if sent:
            print(f'  chat={chat} {sent}건 발송')
