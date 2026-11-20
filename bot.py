"""인바운드 봇 — 명령 처리 (멀티유저)."""
import os
import time
from datetime import datetime, timezone
import re
import tempfile

import config
import corners
import prefs
import people
import db
import tg
import ir
import card
import deck_store
import deck_live
import history
import analyzer
import engine
from analyzer import resolve_channel_id, channel_title

URL_RE = re.compile(r'(https?://\S*youtu\S+|@[\w.\-]+|UC[\w\-]{20,})')
VIDEO_RE = re.compile(r'(?:youtu\.be/|[?&]v=|/shorts/|/live/)([\w\-]{11})')
TICKER_RE = re.compile(r'^[A-Za-z][A-Za-z.\-]{0,9}$')
FEEDBACK_RE = re.compile(r'^/(good|bad)_([a-z0-9_]{1,12})(?:@\w+)?$')
# 온보딩 중 '티커만 나열한 메시지' — 1~8개, $ 붙여도 됨, 쉼표·공백 구분
# 2026-10-21: 한국인 베타 — '삼성전자'·'005930' 도 온보딩에서 받는다(예전엔 영문 티커만 통과해 첫 단계에서 막혔다)
_OB_TOK = r'(?:\$?[A-Za-z][A-Za-z.\-]{0,9}|\d{6}|[가-힣][가-힣A-Za-z0-9&]{0,14})'
ONBOARD_RE = re.compile(rf'^\s*{_OB_TOK}(?:[\s,]+{_OB_TOK}){{0,7}}\s*$')

# 2026-10-21 서식 개편: 한 줄 = 명령 + 무엇을 주는지 + 지원 시장. 자세한 설명은 접힌 인용(expandable
# blockquote)으로 내렸다 — 처음 보는 사람은 명령 목록만 훑고, 궁금한 사람만 펼친다.
# 표(<table>)는 텔레그램이 지원하지 않고, 고정폭(<pre>) 표는 한글 폭이 달라 휴대폰에서 줄이 어긋난다.
# 명령은 <code> 로 감싸지 않는다 — 감싸면 눌러서 보내기가 안 된다.
WELCOME = ("👋 <b>부자알람</b> — 공시 · 시황 · 유튜브 요약 알림 봇\n\n"
           "⚡ <b>빠른 시작</b>\n"
           "/watch 삼성전자 · /market · /dashboard 삼성전자 · /report TSLA · 유튜브 링크 입력\n"
           "<i>종목 입력: 티커 · 6자리 코드 · 한글 종목명</i>\n\n"
           # 2026-11-16 명세 문체(사이트 설명서와 동일) — 구어체 '~해요' 제거. 처음 보는 사람은 아래 4줄만 읽는다.
           "📰 /watch <i>종목</i> — 공시 실시간 · 주요 뉴스 08·20시 요약  🇺🇸🇰🇷\n"
           "📊 /market — 장 마감 시황 카드(한국 15:50 이후 · 미국 익일 오전)  🇺🇸🇰🇷\n"
           "🔍 /dashboard <i>종목</i> — 사이트 종목 분석 결론 카드  🇺🇸🇰🇷\n"
           "🎬 유튜브 링크 입력 — 영상 요약\n\n"
           "<b>전체 명령어</b> (눌러서 펼치기)\n"
           "<blockquote expandable>"
           "📊 1. 사이트 분석\n"
           "1-1 /dashboard 종목 — 종목 분석 결론\n"
           "1-2 /market — 장 마감 시황 (kr · us · week · on · text)\n\n"
           "📑 2. 심층 리포트\n"
           "2-1 /report 티커 — 16장 카드 리포트 🇺🇸 (🇰🇷 개선 중)\n"
           "2-2 /ir 티커 — 최근 공시 · 분기 재무 1장 🇺🇸 (/report 로 통합 예정)\n"
           "기업 개요 · 사업부문 · 재무 추이 · 밸류에이션 · 경쟁사 · 내부자 · CANSLIM · 린치 6유형 · 차트. "
           "첫 요청 종목은 생성에 3~5분.\n\n"
           "🎬 3. 유튜브 요약\n"
           "3-1 /add 채널URL — 채널 구독, 신규 영상 자동 요약\n"
           "3-2 /person 이름 — 인물 출연 영상 추적 (예: /person 박세익)\n"
           "3-3 /yt 링크 — 영상 요약\n"
           "3-4 /list — 구독 채널 목록\n"
           "3-5 /corners — 채널별 수신 코너 선택\n"
           "3-6 /remove 번호 — 구독 해제\n\n"
           "📰 4. 공시 · 뉴스 감시\n"
           "4-1 /watch 종목 — 등록 (공시 실시간 · 뉴스 08·20시 · 해당 없으면 미발송 · 한국 종목 수급 포함)\n"
           "4-2 /watchlist — 감시 종목 목록\n"
           "4-3 /unwatch 종목 — 해제\n\n"
           "💬 5. 기타\n"
           "5-1 /voc 내용 — 오류 · 건의 접수 (반영 시 회신)\n"
           "5-2 /recap 일수 — 최근 요청 내역\n"
           "5-3 /terms — 이용 안내 · 면책"
           "</blockquote>\n"
           "<i>투자 권유가 아닌 정보 요약. 입력창 왼쪽 메뉴(☰) 또는 /help 로 다시 보기.</i>")


# ── IR: /ir 종합 다이제스트 ──────────────────────────────────────────
def send_ir_digest(chat, ticker: str) -> bool:
    try:
        c, anchor = ir.build_digest(ticker)
    except Exception as e:
        print(f'[다이제스트 생성 예외] {ticker}: {e}')
        c = None
    if not c:
        tg.send_message(chat, f'❌ <b>{ticker}</b> IR 자료 종합에 실패했어요 — Gemini 쿼터가 소진됐을 수 있어요. '
                              f'잠시 후 다시 시도해주세요.')
        return False
    png = os.path.join(tempfile.gettempdir(), f'irdigest_{ticker}_{anchor["acc"].replace("-", "")}.png')
    try:
        card.render_png(c, png)
        cap = (f'📡 <b>{ticker.upper()}</b> {c.get("doc_title", "")}\n'
               f'<a href="{ir.filing_url(ticker, anchor)}">기준 공시 원문</a> · '
               + dash_link(ticker, prefs.get(chat)['lang']))
        ok = tg.send_photo(chat, png, cap)
        news = c.get('news') or []
        if news:
            lines = ['📰 <b>최근 뉴스 원문 링크</b>']
            lines += [f'{i}. <a href="{n["link"]}">{n["title"]}</a> — {n.get("source","")} ({n.get("date","")})'
                     for i, n in enumerate(news[:6], 1)]
            tg.send_message(chat, '\n'.join(lines))
        return ok
    except Exception as e:
        print(f'[다이제스트 렌더 실패] {e} → 텍스트 폴백')
        lines = [f'📡 <b>{ticker.upper()}</b> {c.get("doc_title", "")}', f'💡 {c.get("one_liner", "")}']
        trend = c.get('trend')
        if trend and trend.get('periods'):
            lines.append('📊 ' + ' · '.join(trend['periods']))
            for row in trend['rows']:
                lines.append(f'{row["label"]}: ' + ' → '.join(row['values']))
        for label, key in (('현재 상태', 'current'), ('전망', 'outlook'), ('주요사항', 'notes')):
            items = c.get(key) or []
            if items:
                lines.append(f'[{label}] ' + ' / '.join(items))
        lines.append(f'<a href="{ir.filing_url(ticker, anchor)}">공시 원문</a>')
        return tg.send_message(chat, '\n'.join(lines))


# ── /recap 히스토리 요약 ─────────────────────────────────────────────
# ⚠️ 예전 /recap 은 명령 로그를 통째로 Gemini 에 넣어 "관심사·패턴"을 서술하게 했다.
#    두 가지가 잘못됐다.
#      ① **세는 일에 하루 쿼터를 썼다.** '가장 많이 조회한 종목'은 Counter 면 된다.
#         하루 한도가 모델당 20회인데 집계에 한 칸을 태우는 건 비싸다.
#      ② 결과가 사용자가 이미 아는 내용의 재서술이었다("SATL에 관심이 많으시군요").
#    그래서 LLM 을 걷어내고, 로그에서 **사용자가 모르는 것**만 뽑는다:
#    자주 보는데 감시를 안 걸어둔 종목, 마지막으로 본 뒤 올라온 새 공시.
RECAP_FRESH_N = 3  # 새 공시를 확인할 상위 종목 수 — SEC 왕복이라 무료지만 느리다


def send_recap(chat, days: int = 7):
    entries = history.recent(chat, days=days)
    if not entries:
        tg.send_message(chat, f'최근 {days}일간 기록된 요청이 없어요.\n'
                              f'<code>/ir TSLA</code> 처럼 종목을 한 번 조회해보세요.')
        return
    from collections import Counter
    tickers = Counter()
    last_seen = {}
    for e in entries:
        tk = (e.get('arg') or '').split()[0].upper() if e.get('arg') else ''
        if tk and TICKER_RE.match(tk):
            tickers[tk] += 1
            last_seen[tk] = max(last_seen.get(tk, ''), e['ts'])
    cmds = Counter(e['cmd'] for e in entries)

    lines = [f'🗂️ <b>최근 {days}일</b> — 요청 {len(entries)}건']
    lines.append('· ' + ' · '.join(f'{c} {n}' for c, n in cmds.most_common(5)))
    top = tickers.most_common(5)
    if top:
        lines.append('📌 많이 본 종목: ' + ' · '.join(f'<b>{t}</b> {n}회' for t, n in top))

    # 자주 보는데 감시를 안 걸어둔 종목 — 사용자가 직접 세어보지 않으면 모르는 정보다.
    try:
        watching = set(ir.watches_of(chat))
    except Exception:
        watching = set()
    unwatched = [t for t, n in top if t not in watching and n >= 2]
    if unwatched:
        lines.append(f'👁️ 감시 미등록: {", ".join(unwatched)} '
                     f'→ <code>/watch {unwatched[0]}</code>')

    # 마지막으로 본 뒤 새로 올라온 공시. 이게 /recap 의 존재 이유다 —
    # "네가 신경 쓰던 종목에 그 뒤로 이런 게 생겼다".
    fresh = []
    for t, _ in top[:RECAP_FRESH_N]:
        try:
            cik, _name = ir.resolve_ticker(t)
            f = ir.latest_filing(cik) if cik else None
        except Exception as e:
            print(f'[recap] {t} 공시 조회 실패: {e}')
            continue
        if f and f['date'] > last_seen.get(t, '')[:10]:
            fresh.append(f'{t} {f["form"]} ({f["date"]})')
    if fresh:
        lines.append('🆕 마지막 조회 이후 새 공시: ' + ' · '.join(fresh))
        lines.append(f'· 보기: <code>/ir {fresh[0].split()[0]}</code>')
    tg.send_message(chat, '\n'.join(lines))


# ── /report: 13장 포토카드(stock_studian) 재전송 ──────────────────────
SNAP_FULL_PREFIX, SNAP_WATCH_PREFIX = '📚 전체 카드 ', '👁 감시 '


def send_snap(chat, code: str, name: str | None = None) -> bool:
    """통폐합 P2(2026-11-13): /report 는 먼저 대시보드가 계산해 둔 종목 스냅샷(results/snap/{코드}.json)을 그려 보낸다.
    없거나 4일 넘게 낡았으면 False → 호출자가 옛 엔진(16장 덱)으로 폴백. 한국·미국 같은 경로."""
    import snap_card
    try:
        snap = snap_card.fetch(code)
    except Exception as e:
        print(f'[snap] {code}: {e}')
        return False
    if not snap_card.is_fresh(snap):
        return False
    try:
        png = snap_card.summary(snap)
    except Exception as e:
        print(f'[snap 렌더 실패] {code}: {e}')
        return False
    kb = {'keyboard': [[{'text': f'{SNAP_FULL_PREFIX}{code}'}, {'text': f'{SNAP_WATCH_PREFIX}{code}'}]],
          'resize_keyboard': True, 'one_time_keyboard': True}
    ok = tg.send_photo(chat, png, snap_card.caption(snap), reply_markup=kb)
    if ok:
        history.log(chat, '/report', code)
    return ok


def send_snap_full(chat, code: str) -> bool:
    import snap_card
    snap = snap_card.fetch(code)
    if not snap_card.is_fresh(snap):
        tg.send_message(chat, f'<b>{tg_esc(code)}</b> 스냅샷이 없어요 — <code>/report {tg_esc(code)}</code> 로 다시 받아 보세요.',
                        reply_markup={'remove_keyboard': True})
        return False
    pngs = snap_card.deck(snap)
    ok = tg.send_media_group(chat, pngs, snap_card.caption(snap)) if len(pngs) > 1 else tg.send_photo(chat, pngs[0], snap_card.caption(snap))
    if ok:
        history.log(chat, '/report_full', code)
    return ok


def send_deck(chat, ticker: str) -> bool:
    """13장 포토카드를 폰으로 보낸다 — 가능하면 지금 새로 그려서.

        probe(8초·LLM 0콜) → 데이터 있으면 렌더(24초·Gemini 0회)
                           → 없으면 autogen(하루 상한) → 렌더
                           → check 게이트 → 발송

    렌더 경로는 Gemini를 안 쓰고 SEC·Yahoo·위키미디어만 읽으므로 무료이고,
    덤으로 주가·시총이 오늘 값으로 갱신된다(옛 file_id 재전송과 다른 점).

    검수는 게이트지 관문이 아니다. `check.py`가 BLOCK을 내면 멈추고 무엇이
    막혔는지 알리며, 그 게이트 자체가 "사람이 13장을 눈으로 훑어야만 빈 항목을
    찾던 구조"를 없애려고 만들어진 것이다. 렌더가 실패하면 예전에 발행해 둔
    file_id로 폴백한다."""
    tk = ticker.upper()

    # ① 지원 가능한 종목인지 8초·LLM 0콜로 먼저 판정 — 안 되는 종목에 시간을 안 쓴다
    try:
        pr = deck_live.probe(tk)
    except Exception as e:
        print(f'[probe 실패] {tk}: {e}')
        pr = None
    if pr and pr.get('blockers'):
        tg.send_message(chat, f'🚫 <b>{tk}</b> 는 지원할 수 없어요.\n· ' +
                        '\n· '.join(pr['blockers'][:3]))
        return False

    # ② 데이터가 있으면 즉석 렌더 — Gemini 0회, 주가·시총이 오늘 값으로 갱신된다.
    #    단, 있어도 **낡았으면** 먼저 다시 만든다. 예전엔 '없을 때만' 재생성했는데,
    #    check.py 신선도 게이트가 30일에서 막으므로 한 번 만든 종목은 그 뒤로 영원히
    #    발행 불가가 됐다(2026-09-06 실측: 19종 중 6종이 그 상태로 죽어 있었다).
    #    러너는 스스로 못 고치고 사람이 로컬에서 autogen 을 돌려 커밋해야만 풀렸다.
    if deck_live.has_data(tk):
        blocked = deck_live.block_reasons(tk)
        if not blocked:
            tg.send_message(chat, f'🎨 <b>{tk}</b> 16장 리포트를 최신 데이터로 그리는 중… (30초쯤)')
        else:
            why = blocked[0][1]
            left = deck_live.autogen_left()
            if left <= 0:
                # 사유를 그대로 실어 보낸다. '차단 1건'만 오면 뭘 해야 할지 모른다.
                tg.send_message(chat, f'🛑 <b>{tk}</b> 자료가 오래돼 다시 만들어야 하는데 '
                                      f'오늘 생성 한도를 다 썼어요.\n· {why}\n'
                                      f'{deck_live.quota_reset_in()} 리셋돼요.')
                return _send_cached(chat, tk, fallback_only=True)
            tg.send_message(chat, f'🔄 <b>{tk}</b> 자료가 오래돼 다시 만들고 있어요… '
                                  f'(3~5분, {left}회 남음)\n· {why}')
            try:
                deck_live.generate(tk)
            except Exception as e:
                print(f'[재생성 실패] {tk}: {e}')
                tg.send_message(chat, f'❌ <b>{tk}</b> 자료 재생성에 실패했어요. '
                                      f'잠시 후 다시 시도해주세요.')
                return _send_cached(chat, tk, fallback_only=True)
    else:
        left = deck_live.autogen_left()
        if left <= 0:
            tg.send_message(chat, f'⏳ <b>{tk}</b>는 처음 만드는 종목인데 신규 생성 한도를 다 썼어요'
                                  f'(무료 AI 쿼터).\n'
                                  f'{deck_live.quota_reset_in()} 리셋돼요. '
                                  f'그전엔 이미 만든 종목을 요청해주세요.')
            return _send_cached(chat, tk, fallback_only=True)
        tg.send_message(chat, f'🆕 <b>{tk}</b> 는 처음이라 자료부터 만들어요… (3~5분, {left}회 남음)')
        try:
            deck_live.generate(tk)
        except Exception as e:
            print(f'[autogen 실패] {tk}: {e}')
            tg.send_message(chat, f'❌ <b>{tk}</b> 자료 생성에 실패했어요. 잠시 후 다시 시도해주세요.')
            return False

    paths, n_block = deck_live.render(tk)
    if paths and n_block == 0:
        gaps = (pr or {}).get('gaps') or []
        cap = (f'📊 <b>{tk}</b> 기업 심층 리포트 · {len(paths)}p\n'
               f'stock_studian · {deck_live._today()} 기준\n' + dash_link(tk, prefs.get(chat)['lang']))
        if gaps:
            cap += '\n⚠️ ' + gaps[0]
        ok = True
        ids_new = []
        for i in range(0, len(paths), 10):
            res = tg.send_media_group(chat, paths[i:i + 10], cap if i == 0 else '')
            if isinstance(res, list):
                ids_new.extend(res)
            ok = bool(res) and ok
        if ok and len(ids_new) == len(paths):
            deck_store.save(tk, ids_new, len(paths), title=f'{tk} 기업 심층 리포트')
        return ok
    if paths and n_block > 0:
        # 게이트가 막았다 — 무엇이 막았는지 알리고, 옛 발행본이 있으면 그거라도 보낸다.
        # 사유를 빼고 '차단 N건'만 보내면 폰에서는 그냥 '안 되네'로 보인다. 실제로
        # 사용자가 09-04 에 TSLA·AXTI 를 요청했다가 이유를 모른 채 넘어갔다.
        why = deck_live.block_reasons(tk)
        lines = [f'🛑 <b>{tk}</b> 리포트가 발행 기준에 걸렸어요 (차단 {n_block}건).']
        lines += [f'· {m}' for _k, m in why[:2]]
        lines.append('재생성으로 안 풀리는 항목이라 데이터를 직접 고쳐야 해요.')
        tg.send_message(chat, '\n'.join(lines))
        return _send_cached(chat, tk, fallback_only=True)

    # ③ 렌더가 실패하면 예전에 발행해 둔 것으로 폴백
    return _send_cached(chat, tk)


def _send_cached(chat, ticker: str, fallback_only: bool = False) -> bool:
    """예전에 로컬에서 발행해 둔 13장을 file_id로 재전송한다(그림은 발행 당시 것)."""
    info = deck_store.get(ticker)
    if not info:
        if fallback_only:
            return False
        have = deck_store.tickers()
        msg = f'📭 <b>{ticker.upper()}</b> 리포트를 만들지 못했어요.'
        if have:
            msg += '\n\n지금 바로 받을 수 있는 종목: <code>' + '</code> <code>'.join(have) + '</code>'
        tg.send_message(chat, msg)
        return False

    ids = info['file_ids']
    cap = (f'📊 <b>{ticker.upper()}</b> 기업 심층 리포트 · {info.get("pages", len(ids))}p\n'
           f'stock_studian · {info.get("published", "")} 기준')
    # 텔레그램 앨범은 한 번에 10장까지라 13장이면 10+3으로 나눠 보낸다.
    ok = True
    for i in range(0, len(ids), 10):
        chunk = ids[i:i + 10]
        ok = tg.send_media_group_ids(chat, chunk, cap if i == 0 else '') and ok
    if not ok:
        tg.send_message(chat, f'❌ 전송에 실패했어요. 파일 참조가 만료됐을 수 있어요 — '
                              f'로컬에서 <code>publish.py {ticker.upper()}</code>로 다시 발행하면 복구돼요.')
    return ok


# ── 한국 종목: 새 DART 공시 알림 ─────────────────────────────────────
def send_kr_filings(chat, ticker: str, filings: list) -> bool:
    """새 DART 공시를 한 메시지로. 주가 영향이 큰 것(★)을 위로, 하루 수십 건씩 나오는
    지분 변동 보고는 '외 N건'으로 접는다. 공시명이 곧 사건이라(예: '단일판매ㆍ공급계약체결')
    요약 LLM 없이 보낸다 — 대신 원문 링크를 바로 단다."""
    if not filings:
        return False
    major = [f for f in filings if f['major']]
    rest = [f for f in filings if not f['major'] and not f['fold']]
    folded = [f for f in filings if f['fold'] and not f['major']]
    lines = [f'📑 <b>{tg_esc(ir.display_name(ticker))}</b> 새 공시 {len(filings)}건 (DART)']
    for f in major[:8]:
        lines.append(f'★ <a href="{f["url"]}">{tg_esc(f["report_nm"])}</a> <i>{f["rcept_dt"][4:6]}/{f["rcept_dt"][6:]}</i>')
    for f in rest[:8]:
        lines.append(f'· <a href="{f["url"]}">{tg_esc(f["report_nm"])}</a> <i>{f["rcept_dt"][4:6]}/{f["rcept_dt"][6:]}</i>')
    if folded:
        lines.append(f'· 지분 변동·발행 보고 {len(folded)}건 '
                     f'(<a href="{folded[0]["url"]}">최근 1건</a>)')
    hidden = max(0, len(major) - 8) + max(0, len(rest) - 8)
    if hidden:
        lines.append(f'· 외 {hidden}건')
    if major:
        lines.append('\n<i>★ = 실적·계약·증자·자사주·합병 등 주가 영향이 큰 공시</i>')
    return tg.send_message(chat, '\n'.join(lines))


def _kr_one(q: str):
    """한국 종목 질의 → (심볼, 이름, 후보목록). 하나로 정해지면 심볼, 아니면 None."""
    import kr
    hits = kr.search(q)
    if len(hits) != 1:
        return None, None, hits
    code, name = hits[0]
    sym, why = kr.to_symbol(code)
    return sym, name if sym else why, hits


# ── IR: /watch 신규공시 알림용 단일 카드 (기존) ──────────────────────
# 한 실행 안에서 같은 공시 카드는 한 번만 만든다(2026-10-21). 예전엔 감시자 수만큼 LLM 을 불렀다 —
# '분석 1회 → 다수 팬아웃' 원칙 위반이고, 사용자가 늘면 쿼터가 사람 수에 비례해 녹는다.
_IR_CARD = {}


def _also_lines(ticker: str, also) -> str:
    """같은 기간에 함께 나온 다른 공시(최신 1건 외) — 카드 아래 목록."""
    if not also:
        return ''
    rows = [f'· <a href="{ir.filing_url(ticker, f)}">{f["form"]}</a> {f["date"]}' for f in also[:6]]
    more = f'\n· 외 {len(also) - 6}건' if len(also) > 6 else ''
    return f'\n\n함께 나온 공시 {len(also)}건\n' + '\n'.join(rows) + more


def send_ir_card(chat, ticker: str, earnings_only: bool = False, also=None,
                 quiet: bool = False, text_only: bool = False) -> bool:
    """공시 카드. 감시 경로(quiet=True)는 요약 실패 시 사용자에게 오류문을 보내지 않는다 —
    LLM 쿼터 소진은 사용자 탓이 아닌데 '티커를 확인해 주세요'가 6시간마다 반복됐다.
    text_only=True(요약이 계속 실패)면 LLM 없이 공시 종류·날짜·원문 링크만 보낸다(알림 누락 방지)."""
    if text_only:
        cik, _co = ir.resolve_ticker(ticker)
        f = ir.latest_filing(cik) if cik else None
        if not f:
            return False
        return tg.send_message(chat, f'📡 <b>{ticker.upper()}</b> 새 공시 {f["form"]} {f["date"]}\n'
                                     f'<a href="{ir.filing_url(ticker, f)}">공시 원문</a>'
                                     f'\n<i>요약은 일시적으로 만들지 못했어요.</i>' + _also_lines(ticker, also))
    k = (ticker.upper(), earnings_only)
    if k not in _IR_CARD or time.time() - _IR_CARD[k][0] > 1800:     # 30분 — 오래 도는 데몬에서 옛 카드 재사용 방지
        _IR_CARD[k] = (time.time(), ir.summarize_filing(ticker, earnings_only=earnings_only))
    c, filing = _IR_CARD[k][1]
    if not c:
        _IR_CARD.pop(k, None)      # 실패는 기억하지 않는다 — 다음 사람·다음 실행에 다시 시도
        if not quiet:
            tg.send_message(chat, f'❌ <b>{ticker}</b> 공시 요약에 실패했어요. 티커가 맞는지 확인해주세요.')
        return False
    png = os.path.join(tempfile.gettempdir(), f'ir_{ticker}_{filing["acc"].replace("-", "")}.png')
    try:
        if not os.path.exists(png):
            card.render_png(c, png)
        cap = (f'📡 <b>{ticker.upper()}</b> {c.get("doc_title", "")} · {filing["form"]} {filing["date"]}\n'
               f'<a href="{ir.filing_url(ticker, filing)}">공시 원문</a>' + _also_lines(ticker, also))
        return tg.send_photo(chat, png, cap[:1024])
    except Exception as e:
        print(f'[카드 렌더 실패] {e} → 텍스트 폴백')
        lines = [f'📡 <b>{ticker.upper()}</b> {filing["form"]} {filing["date"]}', f'💡 {c.get("one_liner", "")}']
        for k in c.get('kpis', [])[:6]:
            lines.append(f'• {k.get("label")}: <b>{k.get("value")}</b> {k.get("delta", "")}')
        lines.append(f'<a href="{ir.filing_url(ticker, filing)}">공시 원문</a>')
        return tg.send_message(chat, '\n'.join(lines) + _also_lines(ticker, also))


# ── IR: /watch 신규 뉴스 알림 ─────────────────────────────────────────
def send_ir_news(chat, ticker: str, events, digest=None, lang: str = 'ko', reaction=None) -> bool:
    """감시 종목의 새 뉴스를 **한 메시지로** 보낸다.

    예전엔 사건마다 링크 한 줄씩 따로 나갔다. 6건이면 알림이 6번 울리는데
    무엇이 중요한지는 사용자가 직접 골라야 했다. 이제 요약을 위에 얹고
    원문 링크는 아래에 접어둔다.

    digest=None(요약 실패·쿼터 소진)이면 링크 목록만 보낸다 — 요약을 못 한다고
    뉴스 자체가 사라지면 안 된다. (2026-10-20: 감시 경로는 digest=[] 면 아예 안 부른다)

    lang — 틀 문구 언어(prefs.TEXT). 요약 본문은 이미 그 언어로 만들어져 들어온다.
    """
    if isinstance(events, dict):          # 옛 호출부 호환(단건)
        events = [events]
    if not events:
        return False
    # 2026-10-24 개편: 제목 줄은 '중요 n건 · 전체 m건'(예전 '새 뉴스 15건'은 잡음까지 센 숫자), 헤드라인은
    #   근거 기사로 바로 연결, 나머지 원문은 접힌 인용으로 — 메시지가 300자짜리 구글 리다이렉트 링크로 덮였다.
    n_dg = len(digest or [])
    pool = max(len(events), int((events[0] or {}).get('_pool') or 0))   # 자르기 전 사건 수(2026-10-24)
    head_n = (prefs.t(lang, 'news_head2', t=tg_esc(ir.display_name(ticker)), k=n_dg, n=pool)
              if digest else prefs.t(lang, 'news_head', t=tg_esc(ir.display_name(ticker)), n=len(events)))
    lines = [head_n]
    used = set()
    if digest:
        lines.append('')
        for d in digest[:4]:
            th = str(d.get('thesis') or '')
            mark = (prefs.t(lang, 'thesis_against') + ' · ' if th in ('반대', 'against') else
                    prefs.t(lang, 'thesis_for') + ' · ' if th in ('지지', 'supports', 'for') else '')
            hl = f'<b>{tg_esc(d.get("headline", ""))}</b>'
            lk = (d.get('links') or [None])[0]
            if lk:
                hl = f'<a href="{lk}">{hl}</a>'
                used.update(d.get('links') or [])
            if d.get('followup'):
                mark = prefs.t(lang, 'followup') + ' · ' + mark
            lines.append(f'• {mark}{hl}')
            if d.get('so_what'):
                lines.append(f'  ↳ {tg_esc(d["so_what"])}')
    elif digest is None:
        # 요약이 없는 이유를 적는다. 조용히 링크만 오면 "요약 기능이 죽었나"가 된다.
        lines.append(prefs.t(lang, 'no_digest'))
    elif reaction and reaction.get('notable'):
        lines.append(prefs.t(lang, 'move_only'))
    rl = reaction_line(reaction, lang)
    if rl:
        lines += ['', rl]
    head = list(lines)
    lines.append('')
    lines.append(f"<b>{prefs.t(lang, 'sources')}</b>" + ('' if not digest else f" <i>({prefs.t(lang, 'other_news')})</i>"))
    lines.append('<blockquote expandable>')
    events = [n for n in events if n.get('link') not in used] if digest else events
    # ⚠️ 구글 뉴스 링크는 리다이렉트 URL이라 **하나에 300자가 넘는다**. 화면엔 안
    #    보이지만 텔레그램 4096자 한도에는 그대로 잡힌다. 6건이면 2,000자가 URL이다.
    #    넘치면 텔레그램이 400을 내고 **메시지 전체가 안 간다** — 요약까지 같이 사라진다.
    #    그래서 한도에 닿으면 링크부터 줄인다(요약은 반드시 지킨다).
    LIMIT = 3800
    shown = 0
    for n in events[:6]:
        meta = f'{n.get("source", "")} · {n.get("date", "")}'
        if n.get('echo', 1) > 1:
            meta += ' · ' + prefs.t(lang, 'outlets', n=n['echo'])
        row = f'· <a href="{n["link"]}">{tg_esc(n.get("title", ""))}</a> <i>{tg_esc(meta)}</i>'
        if sum(len(x) + 1 for x in lines) + len(row) + 20 > LIMIT:
            break
        lines.append(row)
        shown += 1
    if shown < len(events):
        lines.append('· ' + prefs.t(lang, 'more', n=len(events) - shown))
    lines.append('</blockquote>')
    if not events:                     # 원문이 전부 헤드라인 링크로 들어갔으면 빈 상자를 안 남긴다
        lines = head
    elif not shown:                    # 요약만으로도 한도를 넘는 극단적 경우
        lines = head + ['', prefs.t(lang, 'links_cut', n=len(events))]
    # 봇은 메시지를 읽었는지 알 수 없다 — 이 한 줄이 요약 품질의 유일한 신호다(2026-10-20).
    _dl = dash_link(ticker, lang)
    lines += ['', (_dl + ' · ' if _dl else '') + prefs.t(lang, 'feedback_ask', tk=re.sub(r'[^A-Za-z0-9]', '_', ticker))]
    msg = '\n'.join(lines)
    ok = tg.send_message(chat, msg)
    # 요약을 만들어놓고 발송이 실패하면 사용자는 아무것도 못 받는다 — 생성과 발송을
    # 따로 남겨야 "요약이 없었나, 안 갔나"를 나중에 가릴 수 있다.
    ir.note_news({'ticker': ticker, 'stage': 'send', 'sent': bool(ok), 'lang': lang,
                  'events': len(events), 'digest': len(digest or []),
                  'links_shown': shown, 'chars': len(msg),
                  'fallback': digest is None})
    return ok


def add_watch_one(chat, tok: str):
    """티커·6자리 코드·한글 이름 하나를 감시 등록 → 등록된 심볼(실패 None). 계정 연결 동기화가 쓴다."""
    import kr
    tk = str(tok).strip().lstrip('$').upper()
    if not tk:
        return None
    if kr.is_kr_query(tk):
        sym = _kr_one(tk)[0]
    else:
        sym = tk if ir.resolve_ticker(tk)[0] else None
    if sym:
        ir.add_watch(chat, sym)
    return sym


def onboard_watch(chat, text: str):
    """온보딩 중 받은 티커 목록을 한 번에 감시 등록한다."""
    p = prefs.get(chat)
    toks = [t.lstrip('$').upper() for t in re.split(r'[\s,]+', text.strip()) if t]
    ok, bad = [], []
    import kr
    for tk in dict.fromkeys(toks):
        if kr.is_kr_query(tk):
            sym, _nm, _h = _kr_one(tk)
            if sym:
                ir.add_watch(chat, sym)
                ok.append(sym)
            else:
                bad.append(tk)
        elif ir.resolve_ticker(tk)[0]:
            ir.add_watch(chat, tk)
            ok.append(tk)
        else:
            bad.append(tk)
    history.log(chat, '/watch', ' '.join(ok))
    if not ok:
        tg.send_message(chat, prefs.t(p['lang'], 'onboard_bad', bad=', '.join(bad)).strip())
        return
    prefs.set_onboarding(chat, False)
    tg.send_message(chat, prefs.t(p['lang'], 'onboard_done', ok=', '.join(ok),
                                  bad=prefs.t(p['lang'], 'onboard_bad', bad=', '.join(bad)) if bad else '',
                                  hour=int(p['hour']), tz=p['tz'], first=ok[0]))


KR_REPORT_OWNER_ONLY = True   # 2026-10-23: 한국 리포트 품질 개선 중 — 소유자만(개선 확인용), 다른 사용자는 대시보드 안내


def route_kr(chat, cmd: str, q: str):
    """한국 종목 명령 — /report · /watch · /unwatch. (/ir 은 SEC 전용이라 아직)"""
    if cmd not in ('/report', '/watch', '/unwatch'):
        tg.send_message(chat, f'🇰🇷 한국 종목은 <code>/report</code> · <code>/watch</code> 가 돼요 '
                              f'(예: <code>/watch {tg_esc(q)}</code>). <code>{cmd}</code> 는 미국 종목 전용이에요.')
        return
    import kr
    if cmd == '/unwatch':
        hits = kr.search(q)
        mine = [t for t in ir.watches_of(chat) if ir.is_kr(t) and any(t[:6] == c for c, _ in hits)]
        if not mine:
            tg.send_message(chat, f'❌ <b>{tg_esc(q)}</b> — 감시 중인 한국 종목이 아니에요. <code>/watchlist</code> 로 확인하세요.')
            return
        for t in mine:
            ir.remove_watch(chat, t)
        tg.send_message(chat, '🗑️ ' + ', '.join(f'<b>{tg_esc(ir.display_name(t))}</b>' for t in mine) + ' 감시 해제.')
        return
    hits = kr.search(q)
    if not hits:
        tg.send_message(chat, f'❌ <b>{tg_esc(q)}</b> — 상장 종목을 못 찾았어요. 6자리 코드나 정확한 종목명으로 다시 시도해 주세요.')
        return
    if len(hits) > 1:
        tg.send_message(chat, f'🔎 <b>{tg_esc(q)}</b> 와 비슷한 종목이 여러 개예요. 눌러서 고르세요.\n' +
                        '\n'.join(f'• {cmd}_{c}  {tg_esc(n)}' for c, n in hits))
        return
    code, name = hits[0]
    sym, why = kr.to_symbol(code)
    if not sym:
        tg.send_message(chat, f'❌ <b>{tg_esc(name)}</b>({code}) — {tg_esc(why)}')
        return
    history.log(chat, cmd, sym)
    if cmd == '/watch':
        ir.add_watch(chat, sym)
        p = prefs.get(chat)
        tg.send_message(chat, f'👁️ <b>{tg_esc(name)}</b> ({sym}) 감시 시작.\n'
                              f'• 새 DART 공시 — 매시간 확인, 나오면 바로\n'
                              f'• 한국어 뉴스 요약 + 주가 반응 + 외국인·기관 수급 — 매일 {int(p["hour"]):02d}시·{(int(p["hour"]) + 12) % 24:02d}시 ({tg_esc(p["tz"])})\n'
                              f'해제: <code>/unwatch {code}</code>')
        return
    if send_snap(chat, code, name):
        return
    import brief
    if KR_REPORT_OWNER_ONLY and str(chat) != str(brief._owner_chat()):
        tg.send_message(chat, f'🇰🇷 한국 종목 리포트는 품질을 손보는 중이라 잠시 쉬어요.\n'
                              f'그동안 분석 화면에서 보세요: {dash_link(sym, prefs.get(chat)["lang"])}\n'
                              f'공시·뉴스 알림은 그대로 돼요: <code>/watch {code}</code>')
        return
    tg.send_message(chat, f'🇰🇷 <b>{tg_esc(name)}</b> ({sym}) 리포트를 준비할게요.')
    send_deck(chat, sym)


def route_settings(chat, text: str):
    """/settings · /time <시> · /tz <시간대> · /lang <언어>."""
    cmd, _, arg = text.strip().partition(' ')
    cmd, arg = cmd.lower(), arg.strip()
    p = prefs.get(chat)
    lang = p['lang']
    if cmd == '/time':
        h = prefs.parse_hour(arg)
        if h is None:
            tg.send_message(chat, prefs.t(lang, 'time_bad'))
            return
        p = prefs.set_hour(chat, h)
        tg.send_message(chat, prefs.t(lang, 'time_ok', hour=h, tz=p['tz']))
        return
    if cmd == '/tz':
        tz = prefs.parse_tz(arg)
        if not tz:
            tg.send_message(chat, prefs.t(lang, 'tz_bad'))
            return
        p = prefs.set_tz(chat, tz)
        tg.send_message(chat, prefs.t(lang, 'tz_ok', tz=tz,
                                      now=prefs.local_now(p).strftime('%H:%M')))
        return
    if cmd == '/lang':
        code = prefs.parse_lang(arg)
        if not code:
            tg.send_message(chat, prefs.t(lang, 'lang_bad', langs=prefs.langs_line()))
            return
        prefs.set_lang(chat, code)
        tg.send_message(chat, prefs.t(code, 'lang_ok', lang=prefs.LANGS[code]))
        return
    tg.send_message(chat, prefs.t(lang, 'settings', hour=int(p['hour']), tz=p['tz'],
                                  now=prefs.local_now(p).strftime('%H:%M'),
                                  lang=prefs.LANGS.get(lang, lang), langs=prefs.langs_line()))


def _won(v: float) -> str:
    """원 금액 → '+1,234억' / '-56억' / '+3.2조'."""
    a = abs(v)
    s = f'{a / 1e12:,.1f}조' if a >= 1e12 else f'{a / 1e8:,.0f}억' if a >= 1e8 else f'{a / 1e4:,.0f}만'
    return ('+' if v > 0 else '-' if v < 0 else '') + s + '원'


def flow_line(fl, lang='ko') -> str:
    """외국인·기관 순매수 한 줄(ir.kr_flow). 금액은 순매수 주식 수 × 종가 추정."""
    if not fl:
        return ''
    ko = lang == 'ko'
    best = max((('foreign', fl.get('f_streak', 0)), ('inst', fl.get('i_streak', 0))), key=lambda x: abs(x[1]))
    streak = ''
    if abs(best[1]) >= 3:
        who = ({'foreign': '외국인', 'inst': '기관'} if ko else {'foreign': 'foreigners', 'inst': 'institutions'})[best[0]]
        side = ('순매수' if best[1] > 0 else '순매도') if ko else ('net buying' if best[1] > 0 else 'net selling')
        streak = prefs.t(lang, 'flow_streak', who=who, n=abs(best[1]), side=side)
    return prefs.t(lang, 'react_flow', days=fl['days'], f=_won(fl['foreign_amt']), i=_won(fl['inst_amt']),
                   streak=streak)


def reaction_line(r, lang='ko') -> str:
    """주가 반응 한 줄(ir.price_reaction) + 한국 종목이면 수급 한 줄. 없으면 ''."""
    fl = flow_line((r or {}).get('flow'), lang)
    if not r or not r.get('big'):
        return fl
    b = r['big']
    vol = prefs.t(lang, 'react_vol', x=b['vol_x']) if b.get('vol_x') else ''
    gap = prefs.t(lang, 'react_gap', g=b['gap']) if abs(b.get('gap') or 0) >= 2 else ''
    held = ''
    if abs(b['ret']) >= 3:
        held = prefs.t(lang, 'react_held' if b.get('held') else 'react_faded')
    out = prefs.t(lang, 'react', chg=r['chg'], date=b['date'], ret=b['ret'], vol=vol, gap=gap, held=held)
    return out + ('\n' + fl if fl else '')


def send_ir_deck(chat, ticker: str, item: dict, digest=None, lang: str = 'ko') -> bool:
    """새 IR 발표자료 알림(ir_site.check). digest=None 이면 제목·링크만."""
    L = lambda k, **kw: prefs.t(lang, k, **kw)
    lines = [L('deck_head', t=ticker),
             f'<b>{tg_esc(item.get("title", ""))}</b> <i>{tg_esc(item.get("date", ""))}</i>']
    if digest:
        lines += ['', f'• {tg_esc(digest.get("headline", ""))}']
        for key, label in (('changes', 'deck_changes'), ('key_points', 'deck_points'), ('watch', 'deck_watch')):
            vals = [v for v in (digest.get(key) or []) if str(v).strip()]
            if vals:
                lines += ['', f'<b>{L(label)}</b>'] + [f'· {tg_esc(v)}' for v in vals[:5]]
    else:
        lines.append(L('deck_nosum'))
    lines += ['', f'<a href="{item["url"]}">{L("deck_link")}</a> · ' + dash_link(ticker, lang)]
    msg = '\n'.join(lines)
    if len(msg) > 4000:
        msg = msg[:3990] + '…'
    ok = tg.send_message(chat, msg)
    ir.note_news({'ticker': ticker, 'stage': 'deck', 'sent': bool(ok), 'lang': lang,
                  'summary': bool(digest), 'chars': len(msg)})
    return ok


def dash_link(ticker=None, lang: str = 'ko', watch=None) -> str:
    """대시보드 딥링크 한 줄(HTML). 종목 하나 → ?sym=, 목록 → ?watch=. URL 이 비어 있으면 ''."""
    from urllib.parse import quote
    base = getattr(config, 'DASHBOARD_URL', '')
    if not base:
        return ''
    if watch:
        ts = ','.join(re.sub(r'[^A-Za-z0-9.\-]', '', str(t)).upper() for t in watch if t)
        return f'<a href="{base}/?watch={quote(ts, safe=",")}">{prefs.t(lang, "dash_list")}</a>' if ts else ''
    tk = re.sub(r'[^A-Za-z0-9.\-]', '', str(ticker or '')).upper()
    return f'<a href="{base}/?sym={quote(tk)}">{prefs.t(lang, "dash_one")}</a>' if tk else ''


def tg_esc(s) -> str:
    """텔레그램 HTML 파싱을 깨뜨리는 문자만 막는다. 기사 제목에 &·<·>가 섞이면
    parse_mode=HTML 이 400을 내고 **메시지 전체가 안 간다**(브리핑에서 겪은 적 있음)."""
    return (str(s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ── 유튜브 즉석 요약 ─────────────────────────────────────────────────
def yt_summary(chat, vid: str):
    ex = db.get_analysis(vid)
    if ex and analyzer.has_content(ex.get('analysis') or {}):
        tg.send_message(chat, engine.build_message(ex, chat=chat))
        return
    url = f'https://www.youtube.com/watch?v={vid}'
    title, author = vid, ''
    try:
        import requests
        o = requests.get('https://www.youtube.com/oembed', params={'url': url, 'format': 'json'}, timeout=15).json()
        title, author = o.get('title', vid), o.get('author_name', '')
    except Exception:
        pass
    tg.send_message(chat, f'⏳ 분석 중: <b>{title}</b> (1~3분)')
    video = {'video_id': vid, 'title': title, 'channel': author, 'published': '', 'url': url}
    analysis, source = analyzer.analyze(video)
    if not analyzer.has_content(analysis):
        tg.send_message(chat, '❌ 요약 실패 — 자막이 없거나 분석이 막혔어요. 잠시 후 다시 시도해주세요.')
        return
    db.save_analysis({'video_id': vid, 'channel_id': '', 'title': title,
                      'published': None, 'analysis': analysis, 'source': source, 'attempts': 1})
    # ⚠️ source 를 반드시 같이 넘긴다. DB에는 저장하면서 여기서만 빠뜨려서,
    #    같은 영상이 즉석 요약일 땐 근거 줄이 없고 캐시 재전송일 땐 나오는
    #    불일치가 있었다(engine._quality_line 은 row['source'] 를 본다).
    tg.send_message(chat, engine.build_message(
        {'video_id': vid, 'title': title, 'analysis': analysis, 'source': source}, author, chat=chat))


# ── 인자 없이 누른 명령 → 사용법 + 답장 모드 (2026-10-21) ──────────────────
# ☰ 메뉴에서 /dd 를 누르면 인자 없이 '/dd' 만 온다. 예전엔 Worker 가 '딥다이브 생성 시작했어요'를
# 먼저 보내고 20초 뒤 봇이 '사용법'을 보내 순서가 거꾸로였다. 이제 사용법을 **답장 모드**(force_reply)로
# 보내고, 사용자가 그 메시지에 답장으로 'TSLA' 만 치면 '/dd TSLA' 로 처리한다. 상태 저장이 필요 없다 —
# 답장에는 원래 메시지(명령이 적힌 사용법)가 같이 실려 온다. webhook/worker.js 에 같은 표가 있다.
USAGE = {
    '/watch':   ('👁️ /watch 감시 등록 — 종목을 답장으로 보내 주세요\n예: TSLA · 삼성전자 · 005930', 'TSLA · 삼성전자'),
    '/unwatch': ('🗑️ /unwatch 감시 해제 — 종목을 답장으로 보내 주세요\n목록은 /watchlist', 'TSLA · 삼성전자'),
    '/report':  ('📑 /report 종목 분석 카드 — 종목명이나 티커를 답장으로 보내 주세요\n예: 삼성전자 · TSLA (홈페이지 종목 분석과 같은 계산 · 사전 계산 안 된 종목은 16장 리포트)', '삼성전자 · TSLA'),
    '/ir':      ('📡 /ir 공시·분기 재무 — 미국 티커를 답장으로 보내 주세요\n예: TSLA', 'TSLA'),
    '/yt':      ('🎬 /yt 영상 요약 — 유튜브 링크를 답장으로 보내 주세요\n(링크만 그냥 보내도 돼요)', 'https://youtu.be/…'),
    '/add':     ('➕ /add 채널 구독 — 유튜브 채널 주소를 답장으로 보내 주세요\n예: https://youtube.com/@채널이름', 'https://youtube.com/@…'),
    '/person':  ('🧑 /person 인물 영상 — 이름을 답장으로 보내 주세요\n예: 박세익', '박세익'),
    '/remove':  ('➖ /remove 구독 해제 — /list 의 번호를 답장으로 보내 주세요', '1'),
    '/voc':     ('💬 /voc 불편·건의 — 내용을 답장으로 보내 주세요\n예: 삼성전자 리포트 숫자가 틀려요', '불편했던 점·원하는 기능'),
}
USAGE_EN = {
    '/watch': '👁️ /watch — reply with a ticker\ne.g. TSLA · 005930', '/unwatch': '🗑️ /unwatch — reply with a ticker',
    '/report': '📑 /report — reply with a ticker\ne.g. TSLA', '/ir': '📡 /ir — reply with a US ticker\ne.g. TSLA',
    '/yt': '🎬 /yt — reply with a YouTube link',
    '/add': '➕ /add — reply with a YouTube channel URL', '/person': '🧑 /person — reply with a name',
    '/remove': '➖ /remove — reply with the number from /list',
    '/voc': '💬 /voc — reply with your feedback or a feature request',
}


def send_usage(chat, cmd: str):
    lang = prefs.get(chat)['lang']
    txt, ph = USAGE[cmd]
    if lang != 'ko':
        txt = USAGE_EN.get(cmd, txt)
    tg.send_message(chat, tg_esc(txt), reply_markup={'force_reply': True, 'input_field_placeholder': ph[:64]})


def route_market(chat, arg: str):
    """/market(최근 장) · /market kr|us|week · /market on|off(자동 받기)."""
    import market
    history.log(chat, '/market', arg)
    if arg in ('text', '글', 'card', '카드'):   # 2026-11-06 포토카드 기본, 글로 받고 싶으면 /market text
        prefs._set(chat, market_fmt='text' if arg in ('text', '글') else 'card')
        tg.send_message(chat, '📝 시황을 글로 보내드려요. 카드로: /market card' if arg in ('text', '글')
                        else '🖼 시황을 포토카드로 보내드려요. 글로: /market text')
        return
    if arg in ('on', '켜기', 'off', '끄기'):
        on = arg in ('on', '켜기')
        market.set_sub(chat, on)
        if on:   # 이미 나와 있는 리포트를 구독 직후 또 보내지 않게 기준선만 찍는다
            db = market.fetch()
            prefs._set(chat, **{f"market_sent_{k}": (db.get(f'latest_{k}') or {}).get('date') for k in market.KINDS})
        tg.send_message(chat, "✅ 장 마감 시황을 보내드려요 — 🇰🇷 한국 장 오후 4시쯤 · 🇺🇸 미국 장 오전 6시 20분쯤(서머타임 5시 20분, 한국 시간) · 주간은 월요일. 끄기: /market off"
                        if on else '🔕 시황 자동 발송을 껐어요. 다시 켜기: /market on')
        return
    kind = {'week': 'weekly', 'weekly': 'weekly', '주간': 'weekly', 'kr': 'kr', '한국': 'kr',
            'us': 'daily', '미국': 'daily'}.get(arg)
    market.send(chat, kind, dash_url=getattr(config, 'DASHBOARD_URL', ''))
    if not prefs.get(chat).get('market'):
        tg.send_message(chat, '한국 /market kr · 미국 /market us · 주간 /market week · 자동 받기 /market on')


def route_voc(chat, uname, body: str):
    """사용자: /voc 내용 → 접수 + 소유자 알림. 소유자: /voc list · /voc done <번호> 로 관리."""
    import voc
    import brief
    owner = str(brief._owner_chat() or '')
    is_owner = owner and str(chat) == owner
    lang = prefs.get(chat)['lang']
    head = body.split(' ')[0].lower() if body else ''
    if is_owner and head in ('list', '목록'):
        items = voc.open_items()
        tg.send_message(chat, ('<b>💬 열린 VOC</b>\n' + '\n'.join(
            f"#{r['id']} {r['ts'][:10]} {'(나)' if r.get('owner') else '@' + tg_esc(r.get('user') or str(r['chat']))}"
            f"\n  {tg_esc(r['text'][:200])}" for r in items) + '\n\n처리 후: /voc done 번호 [사용자에게 보낼 한 줄]') if items
            else '💬 열린 VOC 없음')
        return
    if is_owner and head in ('done', '완료'):
        # /voc done 3 [사용자에게 보낼 한 줄] — 접수 때 '고치면 알려드릴게요'라고 약속했으니 실제로 알린다(2026-11-12)
        parts = body.split(maxsplit=2)
        n = parts[1] if len(parts) > 1 else ''
        note = parts[2].strip() if len(parts) > 2 else ''
        row = voc.close(int(n)) if n.isdigit() else None
        if not row:
            tg.send_message(chat, '번호를 못 찾았어요. /voc list 로 확인')
            return
        told = ''
        if not row.get('owner') and str(row.get('chat')) != owner:
            msg = (f"✅ 보내 주신 의견 #{row['id']}을(를) 반영했어요.\n"
                   f"<i>“{tg_esc(row['text'][:120])}”</i>"
                   + (f"\n\n{tg_esc(note)}" if note else '')
                   + '\n\n또 불편한 점이 있으면 /voc 로 알려 주세요. 고마워요!')
            told = ' · 사용자에게 알림 보냄' if tg.send_message(row['chat'], msg) else ' · ⚠ 사용자 알림 실패'
        tg.send_message(chat, f'✅ VOC #{n} 처리 완료{told}')
        return
    if not body:
        send_usage(chat, '/voc')
        return
    row = voc.add(chat, uname, body, is_owner=bool(is_owner))
    history.log(chat, '/voc', str(row['id']))
    tg.send_message(chat, f"💬 접수했어요 (#{row['id']}). 고치면 알려드릴게요." if lang == 'ko'
                    else f"💬 Got it (#{row['id']}). Thanks — we'll follow up.")
    if owner and not is_owner:
        who = '@' + uname if uname else str(chat)
        tg.send_message(owner, f"📮 <b>새 VOC #{row['id']}</b> — {tg_esc(who)}\n{tg_esc(row['text'])}\n\n목록: /voc list")


def _from_reply(msg: dict, text: str) -> str:
    """사용법 메시지에 답장한 거면 '/dd' + 답장 내용으로 바꾼다."""
    rt = msg.get('reply_to_message') or {}
    if not text or text.startswith('/') or not (rt.get('from') or {}).get('is_bot'):
        return text
    m = re.search(r'(/[a-z]+)\b', rt.get('text') or '')
    return f'{m.group(1)} {text}' if m and m.group(1) in USAGE else text


def handle(msg: dict):
    chat = msg.get('chat', {}).get('id')
    if not chat:
        return
    text = _from_reply(msg, (msg.get('text') or '').strip())
    uname = (msg.get('from') or {}).get('username')
    db.upsert_user(chat, uname)
    try:   # 활동 집계(명령 이름만, 내용 X) — /stats·일간 사용 현황(2026-10-23)
        import stats
        _c = stats.cmd_of(text)
        if _c:
            stats.log(chat, _c)
    except Exception as e:
        print(f'[활동 기록 실패] {e}')
    prefs.remember_client_language(chat, (msg.get('from') or {}).get('language_code'))
    # '/watch_SATL' (영상 요약 등에서 한 번 눌러 감시 추가) → '/watch SATL'
    # 대시보드 '봇에서 감시' 링크(t.me/<봇>?start=watch_TSLA)는 '/start watch_TSLA' 로 들어온다(2026-10-20)
    # ── 대시보드 계정 연결: t.me/<봇>?start=link_CODE → '/start link_CODE' · 또는 /link CODE (2026-11-12) ──
    m_l = re.match(r'^/(?:start\s+link_|link\s+)([A-Za-z0-9]{6,10})$', text)
    if m_l:
        import account_link
        r = account_link.link(chat, m_l.group(1))
        tg.send_message(chat, {
            'ok': '🔗 대시보드 계정과 연결됐어요. 대시보드 🛡️ 내 포트폴리오에서 <b>보유 종목을 봇 감시에 추가</b>를 누르면 '
                  '그 종목들의 공시·중요 뉴스가 여기로 와요.',
            'expired': '⌛ 연결 코드가 만료됐어요(30분). 대시보드에서 다시 눌러 주세요.',
            'bad': '연결 코드를 못 찾았어요. 대시보드 🛡️ 내 포트폴리오 → 🤖 텔레그램 봇 연결에서 새로 받아 주세요.',
        }.get(r, '⚠️ 지금 연결이 안 돼요. 잠시 뒤 다시 눌러 주세요(문제가 계속되면 /voc).'))
        return
    m_s = re.match(r'^/start\s+(watch|ir|dd|report)_([A-Za-z0-9]{1,10})$', text)
    if m_s:
        text = f'/{m_s.group(1)}_{m_s.group(2)}'
    m_w = re.match(r'^/(watch|unwatch|ir|dd|report)_([A-Za-z0-9]{1,10})(?:@\w+)?$', text)
    if m_w:
        text = f'/{m_w.group(1)} {m_w.group(2).upper()}'
    low = text.lower()
    bare = low.split('@')[0]
    if bare in USAGE:
        # Worker 가 이미 사용법을 보냈으면(_usage_sent) 중복으로 안 보낸다. 재배포 전 Worker 면 봇이 보낸다.
        if not msg.get('_usage_sent'):
            send_usage(chat, bare)
        return

    # ── 사용자 설정: 받는 시각·시간대·언어 ──
    if low.split(' ')[0] in ('/settings', '/time', '/tz', '/lang'):
        history.log(chat, low.split(' ')[0], text.partition(' ')[2])
        route_settings(chat, text)
        return

    # ── 온보딩: 처음 온 사람은 기능 목록이 아니라 '종목을 보내 달라'부터 ──
    # 2026-10-20: 예전 /start 는 유튜브부터 나오는 긴 목록이었다. 첫 3분 안에 감시 등록까지
    # 끝나야 다음 날 첫 요약을 받고, 그게 이 봇을 계속 쓰게 되는 유일한 경로다.
    if low.split(' ')[0] in ('/start', '/help'):
        p = prefs.get(chat)
        if low.startswith('/start') and not ir.watches_of(chat):
            prefs.set_onboarding(chat, True)
            import nudge
            tg.send_message(chat, prefs.t(p['lang'], 'onboard', hour=int(p['hour']), tz=p['tz']),
                            reply_markup=nudge.ONBOARD_KB)   # 2026-11-12: 버튼 한 번으로 첫 감시 등록
            return
        tg.send_message(chat, WELCOME if p['lang'] == 'ko' else prefs.t('en', 'help_en'))
        return

    # ── /stats 사용 현황 — 소유자 전용 (2026-10-23) ──
    if bare == '/stats':
        import brief, stats
        if str(chat) == str(brief._owner_chat()):
            tg.send_message(chat, stats.text())
        else:
            tg.send_message(chat, '채널 URL을 보내거나 /help 를 눌러보세요.')
        return

    # ── 이용 안내·면책 (2026-10-21) ──
    if bare in ('/terms', '/disclaimer', '/면책'):
        tg.send_message(chat, prefs.t(prefs.get(chat)['lang'], 'terms'))
        return

    # ── 요약 피드백: /good_SATL · /bad_SATL (뉴스 요약 꼬리에 붙는 링크) ──
    fb = FEEDBACK_RE.match(low)
    if fb:
        vote, tk = fb.group(1), fb.group(2).upper()
        ir.note_news({'stage': 'feedback', 'ticker': tk, 'vote': vote, 'chat': chat})
        tg.send_message(chat, prefs.t(prefs.get(chat)['lang'], 'feedback_thanks'))
        return

    # ── VOC: /voc <불편·건의> — 소유자에게 즉시 전달, voc_log.json 한 곳에 쌓음 (2026-10-21) ──
    if bare in ('/voc', '/feedback') or low.startswith(('/voc ', '/feedback ')):
        route_voc(chat, uname, text.partition(' ')[2].strip())
        return

    # ── 스냅샷 카드 아래 버튼(답장 키보드) — 2026-11-13 ──
    if text.startswith(SNAP_FULL_PREFIX):
        send_snap_full(chat, text[len(SNAP_FULL_PREFIX):].strip().upper())
        return
    if text.startswith(SNAP_WATCH_PREFIX):
        _c = text[len(SNAP_WATCH_PREFIX):].strip()
        tg.send_message(chat, '👁 감시 등록할게요.', reply_markup={'remove_keyboard': True})
        return handle({'chat': {'id': chat}, 'from': {'username': uname}, 'text': f'/watch {_c}'})

    # ── 첫 경험 1문항 설문 응답(nudge.SURVEY_KB 버튼) — 2026-11-12 ──
    import nudge
    if text in nudge.RATINGS:
        r = nudge.record_rating(chat, text)
        import voc
        import brief
        owner = str(brief._owner_chat() or '')
        row = voc.add(chat, uname, f'[설문] {text}', is_owner=(str(chat) == owner))
        if owner and str(chat) != owner:
            tg.send_message(owner, f"📮 <b>새 VOC #{row['id']}</b> — 설문 응답 "
                                   f"{tg_esc('@' + uname if uname else str(chat))}: {text}\n목록: /voc list")
        rm = {'remove_keyboard': True}
        if r == 'good':
            voc.close(row['id'])   # 칭찬은 처리할 일이 아니라 열린 목록을 어지럽히지 않게
            tg.send_message(chat, '고마워요! 🙌 더 바라는 기능이 생기면 /voc 로 알려 주세요.', reply_markup=rm)
        else:
            tg.send_message(chat, '알려 주셔서 고마워요. 어떤 점이 아쉬웠는지 한 줄만 답장해 주시면 바로 고칠게요.',
                            reply_markup=rm)
            send_usage(chat, '/voc')
        return

    if prefs.get(chat).get('onboarding') and ONBOARD_RE.match(text):
        onboard_watch(chat, text)
        return

    # ── /recap 히스토리 요약 ──
    if low.startswith('/recap'):
        parts = text.split()
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 7
        send_recap(chat, days=days)
        return

    # ── /person 인물 추적 ──
    if low.startswith('/person'):
        parts = text.split(maxsplit=1)
        history.log(chat, '/person', parts[1] if len(parts) > 1 else '')
        route_person(chat, parts[1:])
        return

    # ── /corners 코너 선택 ──
    if low.startswith('/corners'):
        parts = text.split(maxsplit=2)
        history.log(chat, '/corners', ' '.join(parts[1:]))
        route_corners(chat, parts[1:])
        return

    # ── IR 명령 ──
    if low.startswith(('/ir', '/dd', '/report', '/watch', '/unwatch')) and low != '/watchlist':
        parts = text.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ''
        # 한국 종목: 6자리 코드·'005930.KS'·한글 종목명(띄어쓰기 포함)
        import kr
        q = ' '.join(parts[1:])
        if cmd == '/dd':
            # 2026-11-13 통폐합 P0: 딥다이브는 /report 로 합쳤다(3주 사용 5회·1명). 코드는 지웠고 안내만 남긴다.
            ex = tg_esc(q) if q else 'TSLA'
            tg.send_message(chat, f'🔍 딥다이브는 <b>/report</b> 로 합쳐졌어요 → <code>/report {ex}</code>')
            return
        if q and kr.is_kr_query(q):
            route_kr(chat, cmd, q)
            return
        if not TICKER_RE.match(arg):
            tg.send_message(chat, f'사용법: <code>{cmd} &lt;티커&gt;</code> (예: {cmd} TSLA · 한국은 {cmd} 005930 또는 {cmd} 삼성전자)')
            return
        tk = arg.upper()
        if cmd == '/ir':
            cik, name = ir.resolve_ticker(tk)
            if not cik:
                tg.send_message(chat, f'❌ <b>{tk}</b> — SEC에 등록된 티커가 아니에요. (미국 상장사만 지원)')
                return
            history.log(chat, '/ir', tk)
            tg.send_message(chat, f'⏳ <b>{tk}</b> ({name}) 최근 IR 자료 종합 분석 중… (2~3분)')
            send_ir_digest(chat, tk)
            tg.send_message(chat, '📌 <i>/ir 은 곧 /report 한 장으로 합쳐져요(공시 요약은 /watch 알림으로).</i>')
        elif cmd == '/report':
            # 13장 포토카드(stock_studian). 로컬에서 검수·발행해 둔 것을 file_id로
            # 즉시 재전송한다 — 러너엔 PNG가 없고, 여기서 새로 렌더하면 Gemini
            # 쿼터와 14분 타임아웃에 걸리며 무엇보다 검수를 건너뛰게 된다.
            if send_snap(chat, tk):
                return
            history.log(chat, '/report', tk)
            send_deck(chat, tk)
        elif cmd == '/watch':
            cik, name = ir.resolve_ticker(tk)
            if not cik:
                tg.send_message(chat, f'❌ <b>{tk}</b> — SEC에 등록된 티커가 아니에요.')
                return
            history.log(chat, '/watch', tk)
            ir.add_watch(chat, tk)
            # ⚠️ 실제 동작대로 적는다. 예전 멘트("새 공시가 뜨면 카드로 보내드려요")는
            #    ①뉴스도 보낸다는 걸 빼먹었고 ②즉시 오는 것처럼 읽혔다. 실제로는
            #    ir.check_watches 가 공시 카드와 뉴스를 둘 다 보내고, 주기는
            #    config.JOB_INTERVAL_H(6시간)다. 못 지킬 약속을 적으면 사용자가
            #    "안 온다"고 느끼는 지점이 그 간격이 된다.
            p = prefs.get(chat)
            tg.send_message(chat, prefs.t(p['lang'], 'watch_ok', t=tk, name=name,
                                          hour=int(p['hour']), tz=p['tz']))
        else:
            ir.remove_watch(chat, tk)
            tg.send_message(chat, f'🗑️ <b>{tk}</b> 감시 해제.')
        return

    if low == '/watchlist':
        w = ir.watches_of(chat)
        tg.send_message(chat, ('<b>👁️ IR 감시 종목</b>\n' + '\n'.join(f'• {tg_esc(ir.display_name(t))}' for t in w)
                               + '\n\n' + dash_link(lang=prefs.get(chat)['lang'], watch=w)) if w
                        else 'IR 감시 종목이 없어요. <code>/watch &lt;티커&gt;</code> 로 등록하세요.')
        return

    # ── /market — 대시보드 일간·주간 시황 (2026-10-21) ──
    if low.split(' ')[0] in ('/market', '/시황'):
        route_market(chat, low.partition(' ')[2].strip())
        return

    # ── /dashboard [종목] — 홈페이지 분석 화면으로 (2026-10-21) ──
    if low.split(' ')[0] == '/dashboard':
        lang = prefs.get(chat)['lang']
        arg = text.split(maxsplit=1)[1].strip() if ' ' in text.strip() else ''
        if arg:
            import kr
            if kr.is_kr_query(arg):
                sym, _nm, hits = _kr_one(arg)
                arg = sym or (hits[0][0] + '.KS' if hits else '')
            link = dash_link(arg.upper(), lang)
        else:
            w = ir.watches_of(chat)
            link = dash_link(lang=lang, watch=w) if w else ''
        base = getattr(config, 'DASHBOARD_URL', '')
        tg.send_message(chat, link if link else
                        (f'📊 <a href="{base}">종목 분석 대시보드</a>' if base else '대시보드 주소가 설정돼 있지 않아요.'))
        history.log(chat, '/dashboard', arg)
        return

    # ── 유튜브 영상 링크 → 즉석 요약 ──
    vm = VIDEO_RE.search(text)
    if vm and (low.startswith('/yt') or '/channel/' not in text):
        history.log(chat, '/yt', vm.group(1))
        yt_summary(chat, vm.group(1))
        return
    if low.startswith('/yt'):
        tg.send_message(chat, '사용법: <code>/yt &lt;유튜브 영상 링크&gt;</code>')
        return

    if low == '/list':
        subs = db.list_subscriptions(chat)
        if not subs:
            tg.send_message(chat, '구독 중인 채널이 없어요. <code>/add &lt;채널URL&gt;</code> 로 추가하세요.')
        else:
            lines = ['<b>📋 내 구독 채널</b>']
            lines += [f"{i}. {s['channel_name']}" for i, s in enumerate(subs, 1)]
            tg.send_message(chat, '\n'.join(lines))
        return

    if low.startswith('/remove'):
        subs = db.list_subscriptions(chat)
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            tg.send_message(chat, '사용법: <code>/remove &lt;번호&gt;</code> (/list 로 번호 확인)')
            return
        idx = int(parts[1]) - 1
        if 0 <= idx < len(subs):
            db.remove_subscription(chat, subs[idx]['channel_id'])
            tg.send_message(chat, f"🗑️ 삭제됨: {subs[idx]['channel_name']}")
        else:
            tg.send_message(chat, '번호가 범위를 벗어났어요.')
        return

    m = URL_RE.search(text)
    if not m:
        if low.startswith('/add'):
            tg.send_message(chat, '사용법: <code>/add &lt;유튜브 채널 URL&gt;</code>')
        else:
            tg.send_message(chat, '채널 URL을 보내거나 /help 를 눌러보세요.')
        return

    cid = resolve_channel_id(m.group(1))
    if not cid:
        tg.send_message(chat, '❌ 채널을 못 찾았어요. 영상 말고 <b>채널</b> URL인지 확인해주세요.')
        return
    if any(s['channel_id'] == cid for s in db.list_subscriptions(chat)):
        tg.send_message(chat, 'ℹ️ 이미 구독 중인 채널이에요.')
        return
    name = channel_title(cid)
    db.add_subscription(chat, cid, name)
    history.log(chat, '/add', name)
    tg.send_message(chat, f'✅ 구독 추가: <b>{name}</b>\n다음 요약부터 받아보실 수 있어요.')
    print(f'  구독추가 chat={chat} {name}({cid})')
    # 채널 하나가 하루 14개를 올리기도 한다(삼프로TV 실측). 지금 뭘 받을지 고르게 한다.
    # 안 고르면 전부 받으므로, 이 단계를 건너뛰어도 동작에는 문제가 없다.
    try:
        idx = next((i for i, x in enumerate(db.list_subscriptions(chat), 1)
                    if x['channel_id'] == cid), None)
        if idx:
            send_corner_menu(chat, only_idx=idx)
    except Exception as e:
        print(f'[코너 메뉴 실패] {name}: {e}')


# ── /corners 코너 선택 ───────────────────────────────────────────────
def _survey_channel(cid: str, name: str):
    """이 채널의 코너 목록 [(코너, 건수)] 와 표본 설명.

    반환: (choices, 설명문자열)

    ⚠️ RSS 만으로는 부족하다. 유튜브 RSS 는 **최신 15개**만 주는데(기간이 아니라
       개수 상한), 삼프로TV 는 하루에 15개를 올린다 — 실측 2026-09-17 기준
       RSS 15건이 전부 **같은 날**이었다. 그러면 주 1회짜리 코너(주말인터뷰)는
       주말에 /corners 를 치지 않는 한 목록에 아예 안 나타난다.
       그래서 **과거 분석분(DB)의 제목을 함께** 센다. 네트워크 추가 비용은 없다.

    ⚠️ fetch_recent_videos 가 아니라 원본 RSS 를 본다. 그 함수는 합본을 걸러내는데,
       고를 때는 걸러지기 전 전체를 보여줘야 "왜 전체보기가 목록에 없지"가 안 생긴다.
    """
    import xml.etree.ElementTree as ET
    import requests
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    titles, dates = [], []
    try:
        r = requests.get(f'https://www.youtube.com/feeds/videos.xml?channel_id={cid}',
                         headers={'User-Agent': analyzer.UA}, cookies={'SOCS': 'CAI'}, timeout=15)
        for e in ET.fromstring(r.content).findall('a:entry', ns):
            titles.append(e.findtext('a:title', '', ns) or '')
            dates.append((e.findtext('a:published', '', ns) or '')[:10])
    except Exception as e:
        print(f'[코너 조사 실패] {name}: {e}')
    n_rss = len(titles)
    try:
        past = [r for r in db.unfinished_analyses() if r.get('channel_id') == cid]
        titles += [r.get('title') or '' for r in past]
        dates += [str(r.get('published') or '')[:10] for r in past]
    except Exception as e:
        print(f'[과거분 조회 실패] {name}: {e}')
        past = []
    if not titles:
        return [], ''
    span = sorted(d for d in dates if d)
    basis = f'최근 영상 {n_rss}건'
    if past:
        basis += f' + 과거 분석분 {len(past)}건'
    if span:
        basis += f' ({span[0]} ~ {span[-1]})'
    return corners.survey(titles), basis




# ── /person 인물 추적 ────────────────────────────────────────────────
def route_person(chat, args):
    """`/person` 목록 · `/person 박세익` 등록 · `/person -박세익` 해제."""
    cur = people.watches_of(chat)
    arg = ' '.join(a for a in args if a.strip()).strip()
    if not arg:
        if not cur:
            tg.send_message(chat, chr(10).join([
                '👤 <b>인물 추적</b> — 등록된 인물이 없어요.',
                '한 사람이 여러 채널에 출연해도 모아서 요약해드려요.',
                '· 등록: <code>/person 박세익</code>  (소속을 붙이면 검색어가 늘어요: <code>/person 박세익 체슬리</code>)',
                '· 해제: <code>/person -박세익</code>',
                '<i>이미 구독 중인 채널 영상은 중복이라 제외합니다.</i>']))
        else:
            tg.send_message(chat, '👤 <b>추적 중인 인물</b>' + chr(10)
                            + chr(10).join(f'• {n}  <code>/person -{n}</code>' for n in cur))
        return
    if arg.startswith('-'):
        name = arg[1:].strip()
        ok = people.remove(chat, name)
        tg.send_message(chat, f'🗑️ <b>{name}</b> 추적 해제.' if ok
                        else f'<b>{name}</b> 은 추적 목록에 없어요. <code>/person</code> 으로 확인하세요.')
        return
    # '박세익 체슬리' 처럼 뒤에 소속을 붙이면 **검색어를 하나 더** 만든다(판정 조건 아님).
    parts = arg.split()
    name, extra = parts[0], ' '.join(parts[1:])
    if len(name) < 2 or len(name) > 20:
        tg.send_message(chat, '이름은 2~20자로 넣어주세요. 예: <code>/person 박세익</code>')
        return
    if not people.add(chat, name, extra):
        tg.send_message(chat, f'ℹ️ <b>{name}</b> 은 이미 같은 검색어로 추적 중이에요.')
        return
    arg = name
    # 등록 즉시 지금 뭐가 잡히는지 보여준다 — 안 보여주면 "되는 건가" 가 된다.
    found, ok = people.find_many(people.queries_of(chat, name), analyzer.UA)
    mine = {(c.get('channel_name') or '').strip() for c in db.list_subscriptions(chat)}
    hits = [v for v in found if people.is_really(arg, v)]
    other = [v for v in hits if (v.get('channel') or '').strip() not in mine]
    lines = [f'👤 <b>{arg}</b> 추적 시작.']
    if not ok:
        lines.append('⚠️ 지금은 검색이 안 돼요 — 다음 실행에서 다시 시도합니다.')
    elif not hits:
        lines.append('최근 출연 영상을 못 찾았어요. 이름 표기를 확인해주세요.')
    else:
        from collections import Counter
        by = Counter(v['channel'] for v in other)
        qs = people.queries_of(chat, arg)
        lines.append(f'검색어 {len(qs)}개({" · ".join(qs)}) 합쳐 최근 출연 {len(hits)}건 중 '
                     f'<b>타채널 {len(other)}건</b>이 요약 대상이에요.')
        if by:
            lines.append(chr(10).join(f'• {c} {n}건' for c, n in by.most_common(5)))
        if len(hits) - len(other):
            lines.append(f'<i>구독 중인 채널 {len(hits) - len(other)}건은 중복이라 제외</i>')
    lines.append(f'<i>다음 갱신({config.JOB_INTERVAL_H}시간 이내)부터 요약이 옵니다.</i>')
    tg.send_message(chat, chr(10).join(lines))

def route_corners(chat, args):
    """/corners 인자 해석.

    ⚠️ 2026-09-17: 처음엔 '채널번호 + 코너번호'만 받았는데, 채널이 하나뿐인
       사용자가 자연스럽게 친 `/corners 1,3` 이 선택으로 안 읽히고 메뉴만 다시
       떴다. 저장된 게 없는데 화면은 그대로라 "된 건가?" 가 된다.
       **채널이 하나면 채널 번호를 요구하지 않는다.**

    받는 형태:
      /corners            → 메뉴
      /corners 1,3        → (채널 1개일 때) 코너 1·3 선택
      /corners all        → (채널 1개일 때) 전체
      /corners 2          → (채널 여러 개) 2번 채널 메뉴
      /corners 2 1,3      → 2번 채널의 코너 1·3
    """
    subs = db.list_subscriptions(chat)
    if not subs:
        tg.send_message(chat, '구독 중인 채널이 없어요. <code>/add &lt;채널 URL&gt;</code> 로 추가해주세요.')
        return
    args = [a for a in args if a.strip()]
    if not args:
        send_corner_menu(chat)
        return

    def is_spec(tok):
        """코너 목록처럼 보이는가 — 쉼표가 있거나 all."""
        return (',' in tok) or tok.strip().lower() in ('all', '전체')

    # 채널 번호 + 코너 목록
    if len(args) >= 2 and args[0].isdigit():
        set_corners(chat, int(args[0]), ' '.join(args[1:]))
        return
    tok = args[0]
    if is_spec(tok) or (tok.isdigit() and len(subs) == 1):
        if len(subs) == 1:
            set_corners(chat, 1, ' '.join(args))
        else:
            tg.send_message(
                chat, '채널이 여러 개라 번호가 필요해요.' + chr(10)
                      + chr(10).join(f'{i}. {x["channel_name"]}' for i, x in enumerate(subs, 1))
                      + chr(10) + f'예: <code>/corners 1 {tok}</code>')
        return
    if tok.isdigit():
        send_corner_menu(chat, only_idx=int(tok))
        return
    send_corner_menu(chat)

def send_corner_menu(chat, only_idx=None):
    """구독 채널별 코너 목록을 번호와 함께 보여준다."""
    subs = db.list_subscriptions(chat)
    if not subs:
        tg.send_message(chat, '구독 중인 채널이 없어요. <code>/add &lt;채널 URL&gt;</code> 로 추가해주세요.')
        return
    # 범위 밖 번호를 주면 예전엔 제목만 있고 내용이 없는 메시지가 나갔다.
    if only_idx and not (1 <= only_idx <= len(subs)):
        tg.send_message(chat, f'채널 번호는 1~{len(subs)} 사이예요. '
                              f'<code>/corners</code> 로 목록을 보세요.')
        return
    lines = ['🎛️ <b>코너 선택</b> — 채널마다 요약받을 영상 종류를 고를 수 있어요.', '']
    for ci, sub in enumerate(subs, 1):
        if only_idx and ci != only_idx:
            continue
        pref = corners.get(chat, sub['channel_id'])
        choices, basis = _survey_channel(sub['channel_id'], sub['channel_name'])
        lines.append(f"<b>{ci}. {sub['channel_name']}</b>")
        if not choices:
            lines.append('   (최근 영상을 못 읽었어요)')
        elif not corners.worth_choosing(choices):
            lines.append('   이 채널은 코너 구분이 없어 전부 받습니다.')
        else:
            lines.append(corners.format_list(choices, pref['chosen']))
            if basis:
                lines.append(f'   <i>집계 기준: {basis}</i>')
            if not pref['chosen']:
                lines.append('   <i>아직 안 고르셨어요 — 지금은 전부 받는 중입니다.</i>')
            # 안내 문구는 **실제로 먹히는 형태**여야 한다. 채널이 하나면 채널 번호를
            # 안 받으므로, 있지도 않은 번호를 예시로 보여주면 그대로 쳤다가 실패한다.
            pre = '' if len(subs) == 1 else f'{ci} '
            lines.append(f"   → <code>/corners {pre}1,2</code> 처럼 번호로 고르기 · "
                         f"<code>/corners {pre}all</code> 전체")
        lines.append('')
    tg.send_message(chat, chr(10).join(lines))


def set_corners(chat, ci: int, spec: str):
    subs = db.list_subscriptions(chat)
    if not (1 <= ci <= len(subs)):
        tg.send_message(chat, f'채널 번호는 1~{len(subs)} 사이예요. <code>/corners</code> 로 목록을 보세요.')
        return
    sub = subs[ci - 1]
    choices, _basis = _survey_channel(sub['channel_id'], sub['channel_name'])
    if not choices:
        tg.send_message(chat, '최근 영상을 못 읽어서 코너를 파악하지 못했어요. 잠시 후 다시 시도해주세요.')
        return
    names = [c for c, _ in choices]
    seen = {c for c in names if c != corners.NO_TAG}
    if spec.strip().lower() in ('all', '전체'):
        chosen = set()          # 빈 집합 = 전부. '전부'를 명시적으로 나열하면
                                # 나중에 생긴 코너가 자동으로 빠져버린다.
    else:
        picked = set()
        for tok in re.split(r'[,\s]+', spec.strip()):
            if tok.isdigit() and 1 <= int(tok) <= len(names):
                picked.add(names[int(tok) - 1])
        if not picked:
            tg.send_message(chat, f'번호를 못 알아들었어요. 예: <code>/corners {ci} 1,3</code>')
            return
        chosen = picked
    corners.put(chat, sub['channel_id'], chosen, seen)
    if chosen:
        tg.send_message(chat, f"✅ <b>{sub['channel_name']}</b> — 이제 이 코너만 요약해요:"
                              + chr(10) + chr(10).join(f'• {c}' for c in sorted(chosen)))
    else:
        tg.send_message(chat, f"✅ <b>{sub['channel_name']}</b> — 전체 코너를 받습니다.")


def poll(timeout: int = 0):
    offset = db.get_offset()
    updates = tg.get_updates(offset, timeout=timeout)
    if not updates:
        if not timeout:
            print('새 메시지 없음')
        return
    last = offset
    for u in updates:
        last = max(last, u['update_id'])
        if u.get('message'):
            try:
                handle(u['message'])
            except Exception as e:
                print(f'[handle 오류] {e}')
    db.set_offset(last)
    print(f'인바운드 처리 {len(updates)}건, offset={last}')
