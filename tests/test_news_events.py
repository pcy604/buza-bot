"""2026-10-24 뉴스 사건 단위 개편 — 숫자 지문 묶기 · 출처 등급 대표 · 중요도 정렬 · 이미 알린 사건 제외 · 후속 표시. 네트워크 없이."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir
assert ir._num_sig('Tesla plans $16.8B Terafab in 2026') == frozenset({'16.8b'}), ir._num_sig('Tesla plans $16.8B Terafab in 2026')
assert '4140억' in ir._num_sig('삼성전자 특별배당 4,140억 대기') and not ir._num_sig('3분기 실적 2026년')
it = lambda t, s, d='2026-10-23', l=None: {'title': t, 'source': s, 'date': d, 'link': l or t}
c = ir._news_cluster([it('Tesla eyes $16.8B Terafab chip plant', 'TradingView'),
                      it('Musk confirms $16.8B Terafab project for Tesla', 'Reuters', '2026-10-22'),
                      it('Tesla Cybertruck Australia exit', 'Benzinga')], 'Tesla')
assert len(c) == 2 and c[0]['echo'] == 2 and c[0]['source'] == 'Reuters', c
print('✅ 숫자 지문으로 묶기(하루 경계 넘어도) · 대표는 출처 등급 높은 기사')
assert ir._tier('Reuters') == 3 and ir._tier('GlobeNewswire') == 4 and ir._tier('TradingView') == 1 and ir._tier('일간대한뉴스') == 2
hi = ir._materiality({'title': 'Tesla Q3 earnings beat, raises guidance', 'source': 'Reuters', 'echo': 3})
lo = ir._materiality({'title': 'Is it time to buy Tesla?', 'source': 'Motley Fool', 'echo': 1})
mid = ir._materiality({'title': 'Tesla Cybertruck Australia exit', 'source': 'Benzinga', 'echo': 1})
assert hi > mid > lo, (hi, mid, lo)
print('✅ 중요도: 실적·주요매체 > 일반 소식 > 낚시성 재가공')

# 이미 알린 사건 — LLM 이 다시 내도 기계적으로 빠지고, followup 은 남는다
class Resp:  text = '{"digest":[{"headline":"SpaceX 합병 협상 진행","so_what":"","src":[1]},{"headline":"SpaceX 합병 협상, 이사회 승인으로 확정","so_what":"","src":[1],"followup":true},{"headline":"3분기 영업이익 $2.1B","so_what":"","src":[2]}],"skip_reason":""}'
ir.analyzer._client = lambda *a, **k: None
ir.analyzer._generate = lambda c, p: Resp()
TMP = Path(tempfile.mkdtemp()); ir.NEWS_LOG_PATH = TMP / 'n.json'
ir._enrich_snippets = lambda *a, **k: None
PROMPTS = []
_g = ir.analyzer._generate
ir.analyzer._generate = lambda c, p: (PROMPTS.append(p), Resp())[1]
d = ir.summarize_news('TSLA', 'Tesla', [it('a', 'Reuters'), it('b', 'CNBC')], known=['SpaceX와의 합병 협상 진행 중'], filed=['8-K 2026-10-22 실적 발표'])
hs = [x['headline'] for x in d]
assert hs == ['SpaceX 합병 협상, 이사회 승인으로 확정', '3분기 영업이익 $2.1B'], hs
assert '이미 알린 사건' in PROMPTS[-1] and '(공시 알림) 8-K 2026-10-22 실적 발표' in PROMPTS[-1]
print('✅ 이미 알린 사건 재발송 차단 · 후속은 통과 · 공시 알린 것 프롬프트에 전달')

import prefs, tg
prefs.PREFS_PATH = TMP / 'p.json'; ir.STATE_PATH = TMP / 's.json'
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append(t), True)[1]
import bot
ev = [dict(it(f'기사 {i}', 'S', l=f'https://n/{i}'), _pool=27) for i in range(1, 4)]
bot.send_ir_news(1, 'TSLA', ev, [{'headline': '합병 확정', 'followup': True, 'links': ['https://n/1']}], lang='ko')
assert '🔁 후속' in OUT[-1] and '새 사건 27건 중' in OUT[-1], OUT[-1]
st = {}
ir.note_filed(st, 'TSLA', '8-K 2026-10-22 실적 발표')
assert st['filed']['TSLA'][0]['t'].startswith('8-K')
print('✅ 후속 표시 · 자르기 전 사건 수 표기 · 공시 기록')
print('ALL PASS')
