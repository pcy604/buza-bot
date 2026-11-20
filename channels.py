# -*- coding: utf-8 -*-
"""채널별 영상 패턴 점검 — 어떤 코너가 잘 되고 어떤 코너가 죽는지.

    python channels.py              # 과거 분석분 기준 코너별 성적표
    python channels.py --live       # 구독 채널 RSS 최신분까지 같이(합본 필터 검증)

## 왜 필요한가

2026-09-17 에 합본(전체방송)을 건너뛰는 규칙을 넣었다. 그건 **제목 문자열**에
의존한다 — 채널이 표기를 바꾸거나, 새로 구독한 채널이 다른 이름을 쓰면 조용히
뚫린다. 규칙을 넣고 끝내면 그게 언제 썩었는지 알 방법이 없다.

그리고 제목 규칙만으로는 원래 부족했다. 실측에서 [월스트리트 모닝브리핑]은
'전체보기' 표시가 **없는데도** 토큰 한도를 넘겨 죽었다. 즉 "합본처럼 보이는 것"이
아니라 **"실제로 자주 죽는 코너"**를 봐야 한다.

여기서는 제목의 대괄호 표지(그 채널의 코너명)로 묶어 **코너별 실패율과
커버리지**를 낸다. 숫자가 나쁜 코너가 다음에 손볼 대상이다.

⚠️ 한계: 표본이 작은 코너(2~3건)의 실패율은 우연이다. n 을 같이 보고 판단할 것.
"""
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# 대괄호 안이 날짜뿐이면 코너명이 아니다.
_DATE_ONLY = re.compile(r'^[\d.\s년월일:\-]+$')
_TRAIL_DATE = re.compile(r'\s*/\s*\d.*$')      # [워매신박 / 26.09.16.수] → 워매신박
_LEAD_DATE = re.compile(r'^\d[\d.\s]*')        # [26.09.16 오후 방송 전체보기] → 오후 방송 전체보기
# [9월 16일 마감시황] 은 위 규칙으로 '9'만 떨어져 '월16일마감시황'이 된다.
# 날짜가 코너명에 섞이면 **매일 새 코너가 생기는 것처럼** 보여 선택도 감지도 망가진다.
_KR_DATE = re.compile(r'^\d{1,2}\s*월\s*\d{1,2}\s*일\s*')


def program(title: str) -> str:
    """제목에서 코너명을 뽑는다. 못 뽑으면 '(코너표시 없음)'."""
    for g in re.findall(r'\[([^\]]{1,24})\]', title or ''):
        g = g.strip()
        if _DATE_ONLY.match(g):
            continue
        # ⚠️ 순서 중요: _KR_DATE 를 _LEAD_DATE 보다 **먼저** 돌려야 한다.
        #    _LEAD_DATE(^\d…)가 먼저 돌면 '9월 16일 마감시황'에서 '9'만 떼어
        #    '월 16일 마감시황'이 되고, 그 뒤엔 _KR_DATE 가 못 문다.
        g = _LEAD_DATE.sub('', _KR_DATE.sub('', _TRAIL_DATE.sub('', g))).strip()
        # '주말인터뷰'와 '주말 인터뷰'가 따로 세어지면 표가 갈라진다.
        g = re.sub(r'\s+', '', g)
        # ⚠️ 코너명이 아닌 대괄호를 더 걸러낸다(2026-10-03 실측).
        #    · '[Since 2023.09.18.월]' → 채널 개설일 표식. 앞 규칙이 전부 안 물어
        #      'Since2023.09.18.월' 이 코너명으로 올라가 새 코너 알림까지 떴다.
        #    · '[3부]' → 편 번호. '3'만 떨어져 '부' 한 글자가 코너명이 됐다.
        #    숫자 비중이 높거나 한 글자면 코너명일 수 없다.
        if len(g) < 2:
            continue
        digits = sum(c.isdigit() for c in g)
        if digits / len(g) >= 0.4:
            continue
        return g
    return '(코너표시 없음)'


def report(min_n: int = 2):
    import analyzer
    import db
    rows = db.unfinished_analyses()
    names = {c['channel_id']: (c.get('name') or c['channel_id']) for c in db.all_channels()}
    agg = {}
    for r in rows:
        ch = names.get(r.get('channel_id'), r.get('channel_id') or '(직접요청)')
        key = (ch, program(r.get('title')))
        a = agg.setdefault(key, {'n': 0, 'fail': 0, 'toolong': 0, 'cov': [], 'sample': ''})
        a['n'] += 1
        a['sample'] = a['sample'] or (r.get('title') or '')[:46]
        if not analyzer.has_content(r.get('analysis') or {}):
            a['fail'] += 1
            if r.get('source') == 'too_long' or '토큰' in str((r.get('analysis') or {}).get('_error') or '') \
               or 'token count exceeds' in str((r.get('analysis') or {}).get('_error') or ''):
                a['toolong'] += 1
        c = (r.get('analysis') or {}).get('_coverage')
        if isinstance(c, (int, float)):
            a['cov'].append(c)

    print(f'코너별 성적표 — 분석 {len(rows)}건 (LLM 호출 0회)\n')
    print(f"{'채널':<10} {'코너':<20} {'건수':>4} {'실패':>4} {'실패율':>6} {'길이초과':>7} {'커버리지':>8}")
    print('-' * 66)
    flagged = []
    for (ch, pg), v in sorted(agg.items(), key=lambda x: (-x[1]['fail'] / max(x[1]['n'], 1), -x[1]['n'])):
        if v['n'] < min_n:
            continue
        rate = v['fail'] * 100 // v['n']
        cov = f"{statistics.mean(v['cov']):.2f}" if v['cov'] else '-'
        mark = '⚠️' if (rate >= 15 and v['n'] >= 5) else '  '
        print(f"{mark}{ch[:9]:<9} {pg[:19]:<20} {v['n']:>4} {v['fail']:>4} {rate:>5}% "
              f"{v['toolong']:>7} {cov:>8}")
        if mark.strip():
            flagged.append((ch, pg, v))
    if flagged:
        print('\n⚠️ 표본 5건 이상에서 실패율 15% 넘는 코너:')
        for ch, pg, v in flagged:
            why = '길이 초과가 원인' if v['toolong'] else '서버 오류·파싱 등'
            print(f'   · {ch} [{pg}] — {v["fail"]}/{v["n"]}건 실패, {why}')
            print(f'     예: {v["sample"]}')
    else:
        print('\n실패율이 튀는 코너 없음')
    return agg


def live_check():
    """구독 채널 RSS 최신분에 합본 필터가 실제로 먹는지 확인한다.

    제목 규칙은 채널이 표기를 바꾸면 조용히 뚫린다. 여기서 눈으로 확인한다.
    """
    import analyzer
    import config
    import db
    old = config.LOOKBACK_HOURS
    config.LOOKBACK_HOURS = 24 * 7          # 최근 목록을 넓게 본다(수집 동작은 안 바뀜)
    try:
        chans = db.all_channels()
        print(f'\n구독 채널 {len(chans)}개 · 최근 7일 RSS')
        for c in chans:
            name = c.get('name') or c['channel_id']
            vids = analyzer.fetch_recent_videos(c['channel_id'], name)
            kept = {v['title'] for v in vids}
            print(f'\n  {name} — 통과 {len(vids)}건')
            for v in vids[:config.MAX_PER_CHANNEL]:
                print(f'     → 요약 대상: [{program(v["title"])}] {v["title"][:44]}')
            if not kept:
                print('     (최근 7일 통과분 없음)')
    finally:
        config.LOOKBACK_HOURS = old


if __name__ == '__main__':
    report()
    if '--live' in sys.argv[1:]:
        live_check()
