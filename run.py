"""오케스트레이터 — 크론 실행. 인바운드 폴링 → (6시간마다) 분석·팬아웃·IR감시."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

import config

JOB_STATE_PATH = Path(__file__).parent / 'job_state.json'


class _RefreshAborted(Exception):
    """리포트 재고 갱신이 종목 탓이 아닌 이유로 중단됨 — 24시간 게이트를 찍지 않는다.

    autogen 이 SystemExit 으로 죽는 경로가 있어서(Gemini 한도·원문 없음) 그걸 그냥
    통과시키면 크론 전체가 함께 죽는다. 여기서 붙잡아 '다음 실행에서 재시도'로
    바꾸되, 게이트를 안 찍어 3시간 뒤 크론이 다시 집게 한다.
    """


def _load_state() -> dict:
    try:
        return json.loads(JOB_STATE_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return {}


def _mark(key: str):
    """상태 파일에 키 하나만 갱신한다 — 통째로 덮어쓰면 다른 게이트가 날아간다.

    예전엔 write_text로 {'last_job_run': ...}을 통째 기록했다. 주기가 하나뿐일 땐
    문제가 없었지만 주간 브리핑 게이트가 붙는 순간 서로를 지운다.
    """
    s = _load_state()
    s[key] = datetime.now(timezone.utc).isoformat()
    JOB_STATE_PATH.write_text(json.dumps(s), encoding='utf-8')


def _due(key: str, seconds: float) -> bool:
    """마지막 실행 후 지정 시간이 지났는지. 기록이 없으면 실행할 때가 된 것으로 본다.

    GitHub Actions는 매 실행이 별도 컨테이너라 상태가 안 남음 — job_state.json을
    커밋해서 다음 실행이 이어받게 함. 이 게이트가 없으면 크론 주기(예: 15분)마다
    무거운 작업(Gemini 호출 다수)이 돌아 무료 쿼터가 순식간에 소진됨.
    """
    last = _load_state().get(key)
    if not last:
        return True
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() >= seconds
    except Exception:
        return True


REFRESH_PER_DAY = 2


def _refresh_left() -> int:
    s = _load_state()
    today = datetime.now(timezone.utc).date().isoformat()
    return REFRESH_PER_DAY - (s.get('refresh_n', 0) if s.get('refresh_day') == today else 0)


def _count_refresh():
    s = _load_state()
    today = datetime.now(timezone.utc).date().isoformat()
    s['refresh_n'] = (s.get('refresh_n', 0) if s.get('refresh_day') == today else 0) + 1
    s['refresh_day'] = today
    JOB_STATE_PATH.write_text(json.dumps(s), encoding='utf-8')


def _should_run_jobs() -> bool:
    return _due('last_job_run', config.JOB_INTERVAL_H * 3600)


def _mark_jobs_run():
    _mark('last_job_run')


def main():
    # 필수 시크릿 점검 (누락 시 로그에 명확히)
    req = ('TELEGRAM_TOKEN', 'GEMINI_KEY', 'SUPABASE_URL', 'SUPABASE_KEY')
    missing = [k for k in req if not getattr(config, k, '')]
    if missing:
        print('❌ 필수 시크릿 누락:', ', '.join(missing))
        print('   → GitHub repo Settings → Secrets and variables → Actions 에 등록하세요.')
        sys.exit(1)

    import bot
    import engine
    import ir

    # 웹훅 경로: Cloudflare Worker가 텔레그램 업데이트를 client_payload로 실어
    # repository_dispatch를 쏘면, 크론을 기다리지 않고 즉시 이 분기로 들어온다.
    # (웹훅이 걸려 있으면 getUpdates는 409를 내므로 폴링을 하면 안 됨)
    # 크론/수동 실행에서는 client_payload가 없어 toJSON이 문자열 "null"·"{}"을 준다.
    # 그대로 truthy 검사를 하면 크론이 웹훅 분기로 잘못 들어가므로 걸러낸다.
    payload = os.environ.get('TG_UPDATE', '').strip()
    if payload in ('null', '{}', '""'):
        payload = ''
    def _is_tick(pl):
        try:
            return bool(json.loads(pl).get('tick'))
        except Exception:
            return False
    if payload and _is_tick(payload):
        payload = ''   # Cloudflare 정시 깨우기 — 크론 실행과 똑같이 돈다(뉴스 요약·주기 작업·시황 발송)
        print('⏰ 정시 깨우기(tick)')
    if payload:
        print('=== 부자알람 실행 (웹훅 즉시 처리) ===')
        try:
            upd = json.loads(payload)
            if upd.get('market'):   # Cloudflare 크론 → 시황 즉시 발송(2026-10-21)
                import market
                print(f"📰 시황 발송 {market.deliver(getattr(config, 'DASHBOARD_URL', ''))}건")
                print('=== 완료 (시황) ===')
                return
            m = upd.get('update', upd).get('message')
            if m:
                bot.handle(m)
            else:
                print('처리할 message 없음')
        except Exception:
            print('❌ 웹훅 페이로드 처리 실패:')
            traceback.print_exc()
        print('=== 완료 (웹훅) ===')
        return

    print('=== 부자알람 실행 (cron) ===')
    if config.USE_WEBHOOK:
        print('⏭️ 웹훅 모드 — getUpdates 폴링 생략(409 방지), 주기작업만 수행')
    else:
        bot.poll()  # 대기 중인 유저 명령 전부 처리 (즉시 반환, 롱폴링 아님)

    # 단계별 결과 — 끝에서 health.update 로 넘긴다. None=성공, 문자열=오류(2026-10-21)
    H = {}

    def _err():
        return traceback.format_exc().strip().splitlines()[-1][:160]

    def _watch_err(name):
        if ir.WATCH_ERRORS:
            H[name] = f'{len(ir.WATCH_ERRORS)}종목 조회 실패 — ' + ' · '.join(ir.WATCH_ERRORS[:3])
        ir.WATCH_ERRORS.clear()

    if _should_run_jobs():
        print(f'⏰ 주기작업 실행 (마지막 실행 후 {config.JOB_INTERVAL_H}시간 경과)')
        for name, job in (('영상 갱신', engine.refresh), ('팬아웃', engine.fanout),
                          ('IR 공시 감시', lambda: ir.check_watches(bot.send_ir_card)),
                          ('IR 발표자료 감시', lambda: __import__('ir_site').check(bot.send_ir_deck))):
            try:
                job()
                H[name] = None
            except Exception:
                print(f'❌ 주기작업 실패: {name}')
                traceback.print_exc()
                H[name] = _err()
            if name == 'IR 공시 감시':
                _watch_err(name)
        _mark_jobs_run()
    else:
        print('⏭️ 주기작업 스킵 (아직 간격 안 지남)')

    # 감시 뉴스 — 6시간 게이트와 무관하게 **매 크론 실행**마다 본다(크론은 매시).
    # 사용자마다 자기 시간대의 설정 시각이 지났고 오늘 아직 안 받았을 때만 네트워크·LLM 을
    # 쓰므로, 해당자가 없는 실행은 비용이 거의 없다(prefs.py · ir.deliver_news).
    try:
        n = ir.deliver_news(bot.send_ir_news)
        print(f'📰 감시 뉴스 요약 발송 {n}건')
        H['감시 뉴스'] = None
    except Exception:
        print('❌ 감시 뉴스 발송 실패')
        traceback.print_exc()
        H['감시 뉴스'] = _err()

    # 시황(대시보드 일간·주간 리포트) — /market on 구독자에게 새 리포트를 1회만. 구독자 없으면 네트워크도 안 씀.
    try:
        import market
        n = market.deliver(getattr(config, 'DASHBOARD_URL', ''))
        if n:
            print(f'📰 시황 발송 {n}건')
        H['시황'] = None
    except Exception:
        print('❌ 시황 발송 실패')
        traceback.print_exc()
        H['시황'] = _err()

    # 일간 사용 현황 — 소유자에게 하루 한 번(KST 09시 이후 첫 크론). 2026-10-23
    try:
        import stats, brief, tg
        from datetime import timedelta as _td
        kst = datetime.now(timezone.utc) + _td(hours=9)
        day = kst.date().isoformat()
        if kst.hour >= 9 and _load_state().get('stats_day') != day and brief._owner_chat():
            if tg.send_message(brief._owner_chat(), stats.text()):
                s = _load_state()
                s['stats_day'] = day
                JOB_STATE_PATH.write_text(json.dumps(s), encoding='utf-8')
                print('📈 일간 사용 현황 발송')
    except Exception:
        traceback.print_exc()

    # 먼저 묻기 — 신규 미등록 리마인드 · 첫 경험 24시간 뒤 1문항 설문(사람당 1회). 2026-11-12
    try:
        import nudge, brief, tg, ir as _ir
        _w = {str(c) for c, v in ((_ir.load_state() or {}).get('watches') or {}).items() if v}
        n = nudge.run(lambda c, t, kb: tg.send_message(c, t, reply_markup=kb), brief._owner_chat(), _w)
        if n:
            print(f'🙋 리마인드·설문 {n}건')
    except Exception:
        traceback.print_exc()

    # 대시보드 계정 연결 → 보유 종목 감시 동기화(account_links.watch_sync). 2026-11-12
    try:
        import account_link, tg
        n = account_link.run_sync(bot.add_watch_one, tg.send_message)
        if n:
            print(f'🔗 대시보드 → 감시 동기화 {n}명')
    except Exception:
        traceback.print_exc()

    # 실적 발표 하루 전 알림(미국 감시 종목) — KST 18시 이후 하루 한 번. 2026-11-12
    try:
        import earnings, tg, ir as _ir
        n = earnings.run(tg.send_message, (_ir.load_state() or {}).get('watches') or {})
        if n:
            print(f'🗓️ 실적 예정 알림 {n}명')
    except Exception:
        traceback.print_exc()

    # 봇 프로필(메뉴 명령·소개 문구) — tg.PROFILE 이 바뀌었을 때만 다시 건다.
    try:
        import tg
        h = tg.profile_hash()
        if _load_state().get('tg_profile') != h and tg.setup_profile():
            s = _load_state()
            s['tg_profile'] = h
            JOB_STATE_PATH.write_text(json.dumps(s), encoding='utf-8')
            print('🪪 봇 프로필 갱신')
    except Exception:
        traceback.print_exc()

    # 한국 종목 DART 공시 — 매 크론. 잠정실적·수주 공시는 장중에 나와 바로 반영된다.
    try:
        n = ir.check_kr_filings(bot.send_kr_filings)
        if n:
            print(f'📑 한국 공시 알림 {n}종목')
        H['한국 공시 감시'] = None
        _watch_err('한국 공시 감시')
    except Exception:
        print('❌ 한국 공시 알림 실패')
        traceback.print_exc()
        H['한국 공시 감시'] = _err()

    # 12장 리포트 재고 갱신 — 하루 1건.
    # check.py 신선도 게이트가 30일에서 막으므로, 아무도 안 건드리면 만들어 둔 종목이
    # 하나씩 발행 불가로 넘어간다(2026-09-06 실측: 19종 중 6종이 이미 그 상태였고
    # 09-23 이면 전부였다). 19종을 30일 주기로 유지하는 데 필요한 건 하루 0.63건이라
    # 하루 1건이면 19일에 한 바퀴 돌아 차단선보다 앞선다.
    # ⚠️ 웹훅 실행은 위에서 return 하므로 여기 안 온다 — 사용자 명령 응답에 3~5분을
    #    끼워 넣으면 안 되기 때문이다. 배치는 크론 실행에서만 돈다.
    # 2026-10-20: 24시간에 1건 → 2시간 간격으로 하루 최대 REFRESH_PER_DAY 건.
    #   하루 1건(그마저 503 으로 자주 실패)으로는 22종의 30일 신선도를 못 지켰다(refresh.py 상단).
    #   사용자가 새 종목 /report 를 칠 몫으로 하루 상한 1건은 남겨 둔다(autogen_left() > 1).
    if _due('last_deck_refresh', 2 * 3600) and _refresh_left() > 0:
        try:
            import deck_live
            deck_live._decks_path()          # decks/ 를 경로에 올리는 규칙은 한 곳에만 둔다
            import refresh
            print('🗂️ 리포트 재고:', refresh.summary())
            tk = refresh.pick()
            if not tk:
                print('   되살릴 종목 없음 — 전부 발행 가능')
            elif deck_live.autogen_left() <= 1:
                print('   오늘 생성 한도는 사용자 요청 몫만 남음 — 다음 날로 넘김')
            else:
                print(f'   재생성 시작: {tk}')
                # ⚠️ BaseException 으로 받는다. autogen 은 실패 경로에서 SystemExit 을
                #    던지는데(원문 없음·Gemini 한도 소진 등) 그건 Exception 이 아니라
                #    여기를 뚫고 나가 크론 전체를 죽인다 — 실측(2026-09-06)에서 그렇게
                #    죽어 게이트도 못 찍고 주간 브리핑까지 통째로 건너뛰었다.
                try:
                    deck_live.generate(tk)
                except BaseException as e:
                    # 종목 탓이 아니라 API·네트워크 탓일 수 있으므로 transient 로 적는다.
                    # 여기서 fails 를 올리면 API 가 죽은 날 멀쩡한 종목들이 줄줄이
                    # MAX_FAILS 에 걸려 배치에서 영구히 빠진다.
                    refresh.mark(tk, False, [f'{type(e).__name__}: {e}'], transient=True)
                    print(f'   ✗ 재생성이 끝까지 못 감 ({type(e).__name__}) — 다음 실행에서 재시도')
                    _mark('last_deck_refresh')   # 2시간 뒤 재시도 — 503 이 몰린 시간대를 피한다
                    raise _RefreshAborted from None
                left = deck_live.block_reasons(tk)
                refresh.mark(tk, not left, left)
                print('   결과:', '발행 가능' if not left else f'여전히 차단 — {left[0][1]}')
                _mark('last_deck_refresh')
                _count_refresh()
        except _RefreshAborted:
            # 2시간 게이트는 위에서 찍었고 성공 건수(_count_refresh)는 안 올린다 — 다음
            # 기회에 다시 시도한다. 하루 상한(deck_live.autogen_left)이 따로 브레이크를 잡는다.
            pass
        except Exception:
            print('❌ 리포트 재고 갱신 실패')
            traceback.print_exc()
            _mark('last_deck_refresh')

    # 리포트 자동 채점 — 주 1회(오프라인, 1초 안쪽). 2026-11-12 진단: 마지막 채점이 09-21 로 52일 묵어
    # '93.9점'이 현재 품질처럼 읽혔다. 측정은 자동으로 돌아야 묵지 않는다(주간 브리핑이 날짜를 보여 준다).
    if _due('last_quality_report', 7 * 86400):
        try:
            import quality
            quality.run_report()
            _mark('last_quality_report')
        except Exception:
            traceback.print_exc()

    # 파이프라인 검증 리포트 — 하루 1회, 소유자 텔레그램으로.
    # 사용자 노트북의 예약 작업으로도 만들 수 있지만 그건 앱이 열려 있을 때만 돈다.
    # 노트북이 꺼져 있는 동안에도 러너는 3시간마다 돌므로, 감시만 멈추면 "돌고 있는데
    # 아무도 안 보는" 상태가 된다 — 이 프로젝트가 반복해서 당한 형태다.
    # 감시는 감시 대상과 같은 곳에서 돌아야 한다.
    if _due('last_verify', 24 * 3600):
        # ⚠️ 게이트는 **발송에 성공했을 때만** 찍는다. 예전엔 성공·실패와 무관하게
        #    찍어서, 발송이 실패하면 24시간을 통째로 건너뛰고 아무도 몰랐다 —
        #    러너 로그에 '발송 실패'가 남지만 그걸 읽는 사람은 없다. 감시가 조용히
        #    죽는 그 형태를, 감시를 만들면서 그대로 재현한 것이다(2026-09-09 발견).
        #    안 찍으면 3시간 뒤 크론이 자동 재시도한다. 검증은 Gemini를 안 쓰고
        #    DB 조회 + HTTP 1회라 재시도가 싸다.
        try:
            import brief
            if brief.verify_send():
                print('🔍 검증 리포트 발송 완료')
                _mark('last_verify')
            else:
                print('⚠️ 검증 리포트 발송 실패 — 게이트 안 찍음, 다음 크론에서 재시도')
        except Exception:
            print('❌ 검증 리포트 생성 실패 — 게이트 안 찍음, 다음 크론에서 재시도')
            traceback.print_exc()

    # 주간 소집 브리핑 — 부서를 사람이 기억해서 부르지 않아도 되게.
    # 6시간 주기작업과 별개 게이트다: 브리핑이 실패해도 본 작업은 이미 끝나 있고,
    # 본 작업이 실패해도 브리핑은 그 사실을 실어 나른다.
    if _due('last_brief', config.BRIEF_INTERVAL_D * 86400):
        print(f'📋 주간 브리핑 발송 (마지막 발송 후 {config.BRIEF_INTERVAL_D}일 경과)')
        try:
            import brief
            if brief.main_send():
                _mark('last_brief')
            else:
                print('⚠️ 브리핑 발송 실패 — 다음 실행에서 재시도(게이트 안 찍음)')
        except Exception:
            print('❌ 주간 브리핑 실패')
            traceback.print_exc()

    # 조용한 실패 → 운영자 알림(같은 단계 3회 연속 실패 시 · 복구 시). health.py 상단 참고.
    try:
        import health
        for m in health.update(H):
            print('🛠️', m.splitlines()[0])
    except Exception:
        traceback.print_exc()
    print('=== 완료 ===')


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        print('❌ 실행 중 오류:')
        traceback.print_exc()
        sys.exit(1)
