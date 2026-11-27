# -*- coding: utf-8 -*-
"""시황 → SNS 초안 자동화 + 폰에서 한 번 눌러 승인·발행 (2026-11-28 차니: "제안한 flow 맘에 들어 — ㄱㄱ").

흐름 (사람 손 = 버튼 한 번)
  장 마감 시황(market.deliver) ─ 카드뉴스 사진·문장 ─┬─▶ 텔레그램 구독자(기존)
                                                    └─▶ draft_from_market(): 같은 문장·같은 사진으로
                                                          스레드·인스타 초안 → 큐(draft) → 차니에게 미리보기
                                                          + 하단 버튼 [✅ 발행 #id] [🗑 버리기 #id]
  차니가 버튼을 누름 = 메시지 '✅ 발행 #12,13' ─ 웹훅 ─▶ bot.handle ─▶ handle_owner_text()
                                                          → approved → **그 자리에서** API 게시 → 결과 회신

왜 버튼이 '하단 키보드(메시지)'인가: 웹훅이 allowed_updates=["message"] 로 걸려 있어 인라인 버튼
  (callback_query)은 봇에 도착하지 않는다. 하단 키보드 버튼은 누르면 글자 메시지가 되니 지금 경로 그대로 탄다.
맥이 같다(차니 2번): 텔레그램 카드뉴스와 SNS 글은 **같은 rec.facts.narrative**·**같은 사진**에서 나온다.
  플랫폼별 차이는 adapt.py(길이·쪼개기·링크 위치)와 CHANNEL(첫 줄·태그·CTA)만.
사진: 러너가 끝나면 파일이 사라지므로 초안 때 Supabase Storage 에 올리고 URL 을 큐에 넣는다.
"""
import re

import config

DASH = 'https://stock-dashboard-dmfvhcig7brge7utl7et5r.streamlit.app/'
# 2026-11-28 차니: 게시글 = 스레드 + 네이버(초안·수동) · 쇼츠 = 유튜브 쇼츠 + 인스타 릴스 · 인스타 피드(4:5 잘림)·X 는 안 함
PLATFORMS = ('threads',)
VIDEO = ('reels', 'youtube')
TITLE = {'kr': '한국 증시 마감', 'daily': '미국 증시 마감'}
# 채널마다 다른 것 '만' — 문장 내용은 같다
CHANNEL = {
    'threads':   dict(src='threads', tags=[]),
    'instagram': dict(src='instagram', tags=['#주식', '#시황', '#코스피', '#나스닥', '#주식공부', '#퀀트']),
}
CAVEAT = '규칙과 숫자는 과거 데이터 기준이다. 규칙이 틀리는 구간(급반전·갭 하락)이 있고, 그때도 원장에 그대로 남긴다.'


def _plain(s: str) -> str:
    return re.sub(r'<[^>]+>', '', str(s or '')).strip()


def content_from_rec(rec: dict, photos: list):
    """카드뉴스 캡션과 같은 재료(narrative)로 플랫폼 무관 Content 를 만든다."""
    from .models import Content
    kind, date = rec.get('kind'), rec.get('date')
    n = (rec.get('facts') or {}).get('narrative') or {}
    why = [e for e in (n.get('econ') or [])[:2]]
    if n.get('explain'):
        why.append(n['explain'])
    why += [w for w in (n.get('why') or [])[:3]]
    core = []
    if why:
        core.append('📰 시장을 움직인 재료\n' + '\n'.join(_plain(x) for x in why))
    # 2026-11-28 투자 신호등 제거(차니)
    if n.get('ledger'):
        core.append('📒 실전 원장\n' + _plain(n['ledger']))
    for lab, k in (('📊 시장 폭', 'breadth'), ('💰 돈의 흐름', 'flow'), ('🏷 업종', 'sector'), ('📈 종목', 'stocks')):
        if n.get(k):
            core.append(f'{lab}\n{_plain(n[k])}')
    hook = f"{TITLE.get(kind, '시황')} {str(date)[5:].replace('-', '/')} — {_plain(n.get('summary'))}"
    return Content(slug=f'sihwang_{kind}_{date}', hook=hook[:480], core=core,
                   takeaway=('체크포인트 — ' + ' / '.join(_plain(c) for c in (n.get('checkpoints') or [])[:2])) if n.get('checkpoints') else '',
                   caveat=CAVEAT, cta='오늘 수치의 원본 화면', cta_url=DASH, images=list(photos),
                   kind=kind, date=str(date))


def report_album_photos_600(rec):
    """쇼츠용 600px 캡처(글로벌 마켓 3열 · 오늘의 시장 2×4). 실패하면 None → 카드뉴스 사진으로."""
    try:
        import tempfile
        from pathlib import Path
        import report_album as RA
        return RA.build(rec, Path(tempfile.mkdtemp()), width=600) or None
    except Exception as e:
        print('[social auto] 600px 캡처 실패', e)
        return None


def _keyboard(ids):
    j = ','.join(str(i) for i in ids)
    return {'keyboard': [[{'text': f'✅ 발행 #{j}'}, {'text': f'🗑 버리기 #{j}'}]],
            'resize_keyboard': True, 'one_time_keyboard': True}


def draft_from_market(rec: dict, photos: list) -> list:
    """같은 판(slug)이 이미 큐에 있으면 다시 만들지 않는다. 돌려주는 값 = 새 큐 id 목록."""
    from . import queue
    from .adapt import adapt
    from .storage import public_url
    import tg
    c = content_from_rec(rec, photos)
    if not c.core or not photos:
        print('[social auto] 재료·사진 부족 — 초안 생략')
        return []
    if queue.list_by(slug=c.slug):
        print(f'[social auto] {c.slug} 이미 큐에 있음')
        return []
    urls = [public_url(p) for p in photos]
    ids, preview = [], []
    for post in adapt(c, list(PLATFORMS)):
        ch = CHANNEL.get(post.platform, {})
        post.images = urls
        post.texts = [t.replace(DASH, DASH + f"?src={ch.get('src', post.platform)}") for t in post.texts]
        if ch.get('tags') and post.texts:
            post.texts[0] = post.texts[0].rstrip() + '\n\n' + ' '.join(ch['tags'])
        pid = queue.enqueue(c.slug, post)
        ids.append(pid)
        preview.append(f"<b>[{post.platform} #{pid}]</b> 글 {len(post.texts)}개 · 사진 {len(post.images)}장\n"
                       + tg_esc(post.texts[0][:350]))
    # 쇼츠 — 같은 사진·같은 문장(report_shorts). 실패해도 글 초안은 그대로 간다
    vid = None
    try:
        import tempfile
        from pathlib import Path
        import report_shorts as RS
        mp4 = RS.build(rec, report_album_photos_600(rec) or photos, Path(tempfile.mkdtemp()))
        vid = public_url(str(mp4))
        title = f"{TITLE.get(c.kind, '시황')} {str(c.date)[5:].replace('-', '/')} — {_plain(((rec.get('facts') or {}).get('narrative') or {}).get('summary'))}"
        desc = f"오늘 수치의 원본 화면: {DASH}?src=shorts\n\n{c.caveat}\n{c.disclaimer}"
        from .models import Post
        for plat, texts in (('reels', [title + '\n\n' + desc + '\n\n#주식 #시황 #쇼츠']), ('youtube', [title, desc])):
            pid = queue.enqueue(c.slug, Post(plat, texts, [vid], note='쇼츠 1080x1920'))
            ids.append(pid)
            preview.append(f"<b>[{plat} #{pid}]</b> 쇼츠 · {tg_esc(title[:80])}")
        try:
            RS.send_video(config.OWNER_CHAT, mp4, '쇼츠 미리보기 — 아래 버튼으로 발행')
        except Exception as e:
            print('[social auto] 쇼츠 미리보기 전송 실패', e)
    except Exception as e:
        preview.append(f'⚠️ 쇼츠 생성 실패: {tg_esc(str(e)[:150])}')
    # 네이버 — API 없음 → 마크다운 초안을 텔레그램으로(복사해 붙여넣기)
    try:
        nv = adapt(c, ['naver'])[0].texts[0].replace(DASH, DASH + '?src=naver')
        tg.send_message(config.OWNER_CHAT, '📗 <b>네이버 블로그 초안</b> (복사해 붙여넣기)\n\n' + tg_esc(nv)[:3800])
    except Exception as e:
        print('[social auto] 네이버 초안 실패', e)
    msg = (f"📝 <b>SNS 초안</b> {c.slug}\n\n" + '\n\n'.join(preview)
           + "\n\n아래 버튼: ✅ 발행 = 바로 게시 · 🗑 버리기")
    tg.send_message(config.OWNER_CHAT, msg[:4000], reply_markup=_keyboard(ids))
    print(f'[social auto] 초안 {ids}')
    return ids


def tg_esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


_CMD = re.compile(r'^(?:(✅ ?발행|🗑 ?버리기)|/(ok|no))\s*#?\s*([\d,\s]+)$')


def handle_owner_text(chat, text: str) -> bool:
    """차니(OWNER_CHAT)의 '✅ 발행 #12,13' · '🗑 버리기 #12' · '/ok 12 13' · '/no 12'. 처리했으면 True."""
    if str(chat) != str(config.OWNER_CHAT):
        return False
    m = _CMD.match((text or '').strip())
    if not m:
        return False
    ok = bool(m.group(1) and m.group(1).startswith('✅')) or m.group(2) == 'ok'
    ids = [int(x) for x in re.split(r'[,\s]+', m.group(3)) if x]
    from . import queue
    from .cli import _publisher
    import tg
    out = []
    for pid in ids:
        r = queue.get(pid)
        if not r:
            out.append(f'#{pid} 없음')
            continue
        if r['status'] in ('published',):
            out.append(f"#{pid} 이미 게시됨({r.get('external_id')})")
            continue
        if not ok:
            queue.set_status(pid, 'failed', error='버림(차니 · 텔레그램)')   # status check 제약에 rejected 없음
            out.append(f"#{pid} {r['platform']} 버림")  # noqa
            continue
        queue.set_status(pid, 'approved')
        pl = r['payload']
        try:
            ext = _publisher(r['platform'])(pl['texts'], pl['images'])
            queue.set_status(pid, 'published', external_id=str(ext))
            out.append(f"✅ #{pid} {r['platform']} 게시 {ext}")
        except Exception as e:
            queue.set_status(pid, 'failed', error=str(e))
            out.append(f"❌ #{pid} {r['platform']} 실패: {str(e)[:200]}")
    tg.send_message(chat, '\n'.join(tg_esc(x) for x in out) or '처리할 것 없음', reply_markup={'remove_keyboard': True})
    return True
