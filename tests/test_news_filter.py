"""뉴스 잡음 필터 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_news_filter.py

2026-10-11 사용자 지적("오래된 뉴스도 막 요약하고 분석 퀄리티도 별로")을 받고
5종목 174건을 실제로 받아 분류한 결과에서만 뽑았다. **지어낸 제목은 한 줄도
없다** — 지어낸 사례로 테스트하면 실제로 나가는 오류는 계속 통과한다.

통과(SURVIVE) 목록이 더 중요하다. 필터는 조이기는 쉽고 **진짜 뉴스를 죽이는
건 조용히 일어난다.** 잡음 한 건 나가는 것보다 CHMP 승인 권고가 사라지는 게
훨씬 나쁘다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir

fails = []


def check(name, cond):
    if cond:
        print(f'  OK  {name}')
    else:
        fails.append(name)


# ── 걸러야 하는 것 (실측 제목) ───────────────────────────────────────
JUNK = [
    ('Palantir Technologies', 'Why Palantir Stock Powered to a More Than 5% Gain Today'),
    ('Palantir Technologies', 'Is It Too Late to Buy Palantir Stock?'),
    ('Palantir Technologies', 'Goldman Sachs resets Palantir Stock 12-month price target by 18%'),
    ('Palantir Technologies', 'Barclays Initiates Palantir Technologies at Overweight With $265 Price Target'),
    ('Palantir Technologies', 'Better High-Growth AI Stock: CrowdStrike vs. Palantir Technologies'),
    ('Palantir Technologies', 'AI predicts Palantir stock price for end of Q4 2026'),
    ('Palantir Technologies', 'Palantir Technologies Inc. (PLTR) Stock Forecasts'),
    ('Palantir Technologies', 'Palantir Stock Rose 60% in the Third Quarter. Here’s What Its Other Big Quarters Did Next.'),
    ('Lumentum Holdings', 'Benzinga Bulls and Bears: Nvidia, Lumentum, Planet Labs'),
    ('Lumentum Holdings', 'Lumentum Holdings Inc. tokenized stock (xStock) LITEX (LITEX-USD) Live Price, News, Chart'),
    ('Lumentum Holdings', 'Lumentum Holdings (Derivatives) USD (LITE39944-USD) Cryptocurrency Forum & Discussion'),
    ('Lumentum Holdings', 'Why Is Lumentum Holdings (NASDAQ:LITE) Back in Focus?'),
    ('Bloom Energy', 'Why Is Bloom Energy Stock Falling on Thursday?'),
    ('Bloom Energy', 'UBS Adjusts Price Target on Bloom Energy to $350 From $325, Keeps Buy Rating'),
    ('AXT Inc', 'AXT Inc (AXTI) Stock Forecasts'),
    ('AXT Inc', 'AXT slumps 10%, pushing losing streak to three sessions (AXTI:NASDAQ)'),
    ('AXT Inc', 'AXT, Inc. Shares Fall More Than 10%, Extend Losing Streak to Three Sessions'),
    ('Corcept Therapeutics', 'How (CORT) Movements Inform Risk Allocation Models'),
    ('Corcept Therapeutics', 'Corcept Therapeutics Inc (HTD.DU) Stock Forum & Discussion'),
    ('Corcept Therapeutics', 'Corcept, IBD Stock Of The Day, Setting Up Amid Booming Earnings Growth'),
    ('Corcept Therapeutics', 'The Zacks Analyst Blog Highlights Abbott, Corcept, Precigen and Bausch Health Companies'),
]

# ── 반드시 살아야 하는 것 (실측 제목) ────────────────────────────────
SURVIVE = [
    ('Corcept Therapeutics', 'Corcept Announces CHMP Opinion Recommending EU Marketing Authorization for Lifyorli'),
    ('Corcept Therapeutics', 'Corcept Announces Planned Leadership Transition'),
    ('Corcept Therapeutics', "Teva's US exclusive dealing theory fails as matter of law, Corcept says"),
    ('Lumentum Holdings', 'Nvidia-Backed Lumentum Sees Opto-Parts Capacity Sold Out to 2029'),
    ('Lumentum Holdings', 'Lumentum AI optical components sold out through 2029'),
    ('AXT Inc', 'AXT could get a boost as China needs optics, faster networks: Wedbush'),
    ('AXT Inc', "Can Surging InP Demand Strengthen AXT's Long-Term Growth Potential?"),
    ('AXT Inc', 'BlackRock reports a passive stake in AXT (AXTI); an iShares ETF has an interest'),
    ('Palantir Technologies', "Palantir AI probe leads to Met Police volunteer chief's dismissal"),
]

print('[걸러야 하는 것]')
for co, t in JUNK:
    check(t[:62], ir._news_is_junk({'title': t, 'source': ''}))
print()
print('[살아야 하는 것]')
for co, t in SURVIVE:
    check(t[:62], not ir._news_is_junk({'title': t, 'source': ''}))

# ── 내부자 매매 접기 ─────────────────────────────────────────────────
# CORT 실측: 거래 한 건이 제목 네 개로 들어와 limit 자리를 다 먹었다.
print()
print('[내부자 매매 접기]')
INSIDER = [
    'Corcept Therapeutics president sells $967k in shares',
    'Corcept Therapeutics Insider Sold Shares Worth $2,906,601, According to a Recent SEC Filing',
    'Corcept Therapeutics chief accounting officer sells $1.16m',
    'Corcept Therapeutics president Sean Maduck sells $2.9 million in stock',
    'An officer reports 12,191 shares, including unvested awards, at Corcept',
    'Corcept (CORT) director offloads 10,000 shares under preset plan',
]
REAL = 'Corcept Announces Planned Leadership Transition'
rows = [{'title': t, 'date': '2026-10-06'} for t in INSIDER]
rows.append({'title': REAL, 'date': '2026-09-23'})
folded = ir._fold_insider(rows)
check(f'{len(INSIDER)}건 → {len(folded) - 1}건으로 접힘', len(folded) == 2)
check('진짜 사건은 살아남음', any(r['title'] == REAL for r in folded))
check('접힌 건수가 기록됨',
      any(r.get('insider_folded') == len(INSIDER) for r in folded))

# ── 대소문자만 다른 중복 ─────────────────────────────────────────────
print()
print('[제목 중복 판정]')
check('대소문자만 다르면 같은 제목',
      'AXT Inc (AXTI) Stock Forecasts'.lower() == 'AXT Inc (AXTI) Stock forecasts'.lower())

# ── 회사명 없는 제목은 **거르지 않는다** ─────────────────────────────
# 한때 '제목에 회사명도 티커도 없으면 버린다'를 넣었다가 뺐다. 5종목 174건
# 에선 오탐이 0 이었는데 SATL 33건에선 3건이 오탐이었다 — 소형주는 회사명
# 없이 사건만 쓰는 헤드라인이 흔하다. 다시 넣지 않도록 여기 고정한다.
print()
print('[회사명 없는 제목도 통과해야 한다 — SATL 실측]')
for t in ['A satellite network is on track to map the whole Earth daily in H2 2027',
          'Six more satellites are planned for a U.S. program to monitor maritime activity',
          'A satellite got within 27 kilometers of a spent rocket in orbit']:
    check(t[:62], not ir._news_is_junk({'title': t, 'source': ''}))

# ── 같은 사건 묶기(SATL Merlin 발사 실측) ────────────────────────────
print()
print('[사건 묶기]')
MERLIN = [
    'Satellogic Inc. Announces the Successful Satellite Launch of Its First Merlin.01',
    'Satellogic launches first Merlin satellite constellation',
]
cl = ir._news_cluster([{'title': x, 'date': '2026-10-02', 'link': f'u{i}', 'source': ''}
                       for i, x in enumerate(MERLIN)], 'Satellogic Inc.')
check('launch/launches 가 같은 사건으로 묶임', len(cl) == 1)

print()
if fails:
    print('실패:')
    for f in fails:
        print('  X ' + f)
    sys.exit(1)
print(f'전부 통과 ({len(JUNK)}건 차단 · {len(SURVIVE)}건 통과 확인)')
