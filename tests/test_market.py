"""/market — 대시보드 시황 JSON → 텔레그램 형식, 자산배분 판정 제외, 구독·1회 발송. 네트워크 없이 돈다."""
import sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import prefs
TMP = Path(tempfile.mkdtemp())
prefs.PREFS_PATH = TMP / 'p.json'
import market
import config as _cfg
_cfg.OWNER_CHAT = ''   # 테스트 구독자만 보게 — 실제 소유자 기본 구독 제외

MD = ("## 이번 주 판정 (코어 스위치 ON · 목표 비중 코어 50%/위성 30%/현금 20%)\n## 한 줄 요약\n한국은 약세, 미국은 강보합.\n\n"
      "## 지수\n| a | b |\n## 체크포인트\n1.  코스피 200일선 회복 여부 확인할 것.\n2.  **VIX** 추이 확인할 것.\n\n※ 자동 생성")
F = {'kind': 'daily', 'verdict': {'core_on': True, 'target_core_sat_cash': [50, 30, 20]},
     'indices': [{'name': '코스피', 'date': '2026-10-21', 'close': 5655.55, 'd1': -1.95, 'd5': -6.29, 'm1': -14.7},
                 {'name': 'S&P500', 'date': '2026-10-21', 'close': 7712.57, 'd1': 0.3, 'd5': -1.2, 'm1': -0.7}],
     'stocks': {'KR': {'basis': 'ret_1w', 'breadth_up': 27, 'near_52w': 9,
                       'top': [{'name': '삼아알미늄', 'ret': 11.8}], 'bottom': [{'name': 'LS에코에너지', 'ret': -20.8}]},
                'US': {'basis': 'ret_1w', 'breadth_up': 10, 'near_52w': 194,
                       'top': [{'name': 'HASBRO, INC.', 'ret': 10.9}, {'name': 'Moderna, Inc.', 'ret': 11.0}],
                       'bottom': [{'name': 'General Motors Co', 'ret': -8.2}]}},
     'signals': {'market_direction': {'KR': '하락추세 ⚠️', 'US': '상승추세 ✅'}, 'accel_week': '2026-10-12',
                 'accel_new': [{'sym': 'FIGS'}, {'sym': 'CBRL'}]}}
REC = {'kind': 'daily', 'date': '2026-10-21', 'engine': 'gemini:x', 'markdown': MD, 'facts': F}

F['stocks']['perf_date'] = '2026-10-20'
F['indices'][0]['sym'] = '^KS11'
t = market.render(REC, 'https://dash')
assert '미국 장 마감</b> · 10/21(수)' in t and '한국은 약세' in t, t
assert '코스피 5,655' not in t and '🟢 S&amp;P500 7,712.6 <b>+0.3%</b> · 5일 -1.2%' in t, t
assert 'Hasbro +10.9%' in t and 'Moderna +11.0%' in t and 'General Motors -8.2%' in t and '삼아알미늄' not in t, t
assert '(1주 · 2026-10-20 기준)' in t, t
assert '1. 코스피 200일선' in t and '2. VIX 추이' in t and '**' not in t and 'blockquote expandable' in t, t
assert '코어' not in t and '위성' not in t and '현금' not in t, '자산배분 판정은 봇에 싣지 않는다'
assert 'href="https://dash"' in t and '투자 권유 아님' in t
print('✅ 미국 장 렌더: 미국만·기준일 표기·자산배분 제외')

KR = {'kind': 'kr', 'date': '2026-10-21', 'generated': '2026-10-21 15:52', 'engine': 'template', 'markdown': '',
      'facts': {'kind': 'kr', 'indices': [F['indices'][0]],
                'stocks': {'KR': {'basis': 'd1', 'breadth_up': 70, 'top': [{'name': '삼성전자', 'ret': 4.4}], 'bottom': [{'name': 'X', 'ret': -1.0}]}},
                'signals': {'market_direction': {'KR': '하락추세'}}}}
k = market.render(KR)
assert '한국 장 마감' in k and '코스피 5,655.6' in k and '(오늘)' in k and '신고가' not in k and '🇺🇸' not in k, k
assert market.latest_kind({'latest_daily': dict(REC, generated='2026-10-20 21:35'), 'latest_kr': KR}) == 'kr'
KR2 = dict(KR, facts=dict(KR['facts'], indices=[dict(F['indices'][0], d1=1.0, above_200d=False, from_52w_high=-37.1)],
          stocks={'KR': dict(KR['facts']['stocks']['KR'], breadth_all={'up': 1204, 'down': 1292, 'flat': 153, 'limit_up': 4, 'limit_down': 1},
                  turnover_tn={'코스피': 18.4}, megacaps=[{'name': '삼성전자', 'ret': 5.7}], sectors=[{'name': '반도체', 'ret': 5.8, 'lead': 'SK하이닉스'},
                  {'name': '통신서비스', 'ret': -1.6, 'lead': 'SK텔레콤'}])}))
k2 = market.render(KR2)
assert '대형주로 쏠린 장' in k2 and '200일선 아래' in k2 and '상승 1,204' in k2 and '거래대금 코스피 18.4조' in k2, k2
assert '🟢 삼성전자 +5.7%' in k2 and '반도체 +5.8% (SK하이닉스)' in k2 and '🔴 통신서비스 -1.6%' in k2, k2
# 52주 신고가·특징주·거래대금 상위 (2026-11-11)
KR3 = dict(KR2, facts=dict(KR2['facts'], stocks={'KR': dict(KR2['facts']['stocks']['KR'],
          new_high_52w={'n': 8, 'universe': 1200, 'top': [{'name': 'NHN', 'ret': 6.6}, {'name': '신규상장', 'ret': 1.0, 'young': True}]},
          featured=[{'name': '에스텍', 'ret': 30.0, 'tag': '상한가'}, {'name': '주성엔지니어링', 'ret': 12.8, 'tag': '거래대금 6위'}],
          limit_up=[{'name': '에스텍', 'ret': 30.0}],
          themes_top=[{'name': '반도체 기판', 'ret': 11.2, 'n': 14, 'up': 14, 'lead': [{'name': '심텍홀딩스', 'ret': 24.2}]}],
          themes_bottom=[{'name': '손해보험', 'ret': -2.5}],
          turnover_top=[{'name': 'SK하이닉스', 'ret': 5.9, 'amt_b': 26076}, {'name': '삼성전기', 'ret': 3.0, 'amt_b': 3739}])}))
k3 = market.render(KR3)
assert '52주 신고가 8종' in k3 and '🟢 NHN +6.6%' in k3 and '신규상장 +1.0% 🆕' in k3, k3
assert '에스텍 +30.0% <i>상한가</i>' in k3 and '상한가 1종: 에스텍' in k3 and '(2.6조)' in k3 and '(3,739억)' in k3, k3
assert '반도체 기판 <b>+11.2%</b> — 심텍홀딩스' in k3 and '약세 손해보험 -2.5%' in k3, k3
assert k3.index('시장 폭') < k3.index('52주 신고가') < k3.index('시총 상위 10'), '시장 폭 바로 뒤'
print('✅ 신고가·특징주·거래대금 상위')
tnx = market._idx_line({'sym': '^TNX', 'name': '미국 10년물(%)', 'close': 5.12, 'd1': -0.4, 'd5': -1.9}, 'daily')
assert '5.12% <b>-2bp</b>' in tnx, tnx
assert market._round_ai('코스피 3.29% 상승, 5일 -4.55%') == '코스피 3.3% 상승, 5일 -4.5%' or '-4.6%' in market._round_ai('5일 -4.55%')
print('✅ 한국 장 렌더 · 시장 폭·대장주·업종·인사이트·bp·소수 1자리')

w = market.render({'kind': 'weekly', 'date': '2026-10-19', 'engine': 'template', 'markdown': '', 'facts': dict(F, kind='weekly')})
assert '주간 시황' in w and '<b>-6.3%</b> · 1개월 -14.7%' in w and '코스피' in w, w
print('✅ 주간')

import tg
OUT = []
tg.send_message = lambda c, t, **k: (OUT.append((c, t)), True)[1]
KST = lambda d, h: datetime(2026, 10, d, h - 9 if h >= 9 else h + 15, tzinfo=timezone.utc) if h >= 9 else datetime(2026, 10, d - 1, h + 15, tzinfo=timezone.utc)
market.fetch = lambda timeout=20: {'latest_daily': REC, 'latest_kr': KR}
prefs._set(9, tz='Asia/Seoul', hour=8, lang='ko')
market.set_sub(9, True)
real_now = prefs.local_now
at = lambda d, h: (lambda p, now=None: real_now({'tz': 'Asia/Seoul'}, KST(d, h)))
prefs.local_now = at(21, 4)
assert market.deliver() == 0, '04시 — 창 밖(서머타임 미국 시황은 05시대)'
prefs.local_now = at(21, 7)
assert market.deliver() == 1 and '미국 장' in OUT[-1][1], '07시 — 미국 장만'
prefs.local_now = at(21, 16)
assert market.deliver() == 1 and '한국 장' in OUT[-1][1], '16시 — 한국 장'
assert market.deliver() == 0, '같은 장은 한 번만'
# 늦게라도 보낸다(10-23 사고: 창을 지나 아예 안 감) · 20시간 지난 건 안 보낸다
prefs._set(9, market_sent_kr=None)
prefs.local_now = at(21, 23)
assert market.deliver() == 1, '23시 — 늦었어도 발송'
prefs._set(9, market_sent_kr=None)
prefs.local_now = real_now
from datetime import datetime as _dt, timezone as _tz
assert not market._due(KR, prefs.get(9), now=_dt(2026, 10, 22, 6, 0, tzinfo=_tz.utc)), '생성 23시간 뒤는 안 보냄'
assert not market._due(KR, prefs.get(9), now=_dt(2026, 10, 21, 17, 0, tzinfo=_tz.utc)), 'KST 02시는 안 보냄'
import os
market.set_sub(9, False)
assert market.subscribers() == []
os.environ['OWNER_CHAT'] = '77'
assert market.subscribers() == [77], '소유자는 기본 구독'
market.set_sub(77, False)
assert market.subscribers() == [], '소유자도 /market off 면 끔'
del os.environ['OWNER_CHAT']
prefs.local_now = real_now
print('✅ 구독·장별 발송 창·1회 발송')
print('ALL PASS')

# 2026-11-06 포토카드 — 렌더 · 캡션 1024자 · 형식 선택
import market_card, tempfile as _tf, os as _os
KR3 = dict(KR2, markdown='## 한 줄 요약\n반도체가 끌어내린 장.\n## 체크포인트\n1. ' + '가' * 900)
pth = market_card.render(KR3, _tf.mktemp(suffix='.png'), one_liner='반도체가 끌어내린 장.', tips=['코스피는 아직 200일선 아래'])
from PIL import Image as _I
im = _I.open(pth)
assert im.width == 1080 and 900 < im.height < 3600, im.size
cap = market.caption(KR3, 'https://d')
assert len(cap) <= 1024 and '반도체가 끌어내린 장' not in cap and '💡' in cap, (len(cap), cap[:200])
assert market._josa('나스닥') == '은' and market._josa('코스피') == '는' and market._josa('S&P500') == '는'
assert market.clean_name('Idexx Laboratories Inc /De') == 'Idexx Laboratories', market.clean_name('Idexx Laboratories Inc /De')
SENT = []
tg.send_photo = lambda c, p, caption='': (SENT.append(('photo', c)), True)[1]
tg.send_message = lambda c, t, **k: (SENT.append(('text', c)), True)[1]
tg.send_media_group = lambda c, p, caption='': False   # 네트워크 없이 — 앨범 실패 시 1장 대체 경로
prefs._set(5, lang='ko')
market._send_one(5, KR3)
prefs._set(5, market_fmt='text')
market._send_one(5, KR3)
assert [x[0] for x in SENT] == ['photo', 'text'], SENT
print('✅ 포토카드 렌더 · 캡션 1024자 · 조사 · 회사명 · /market text 선택')
print('ALL PASS')

# 2026-11-11 3장 앨범 접음 → 1장 카드 + 실전 신호등·수급·업종(네이버 묶음)·테마
HM = [{'name': '삼성전자', 'sym': '005930', 'sec': '반도체', 'mc': 1200.0, 'ret': 2.8},
      {'name': 'SK하이닉스', 'sym': '000660', 'sec': '반도체', 'mc': 900.0, 'ret': 5.9},
      {'name': '한미반도체', 'sym': '042700', 'sec': '반도체', 'mc': 30.0, 'ret': 1.0},
      {'name': 'KB금융', 'sym': '105560', 'sec': '금융', 'mc': 40.0, 'ret': 0.4},
      {'name': '기타주', 'sym': '000001', 'sec': '기타', 'mc': 5.0, 'ret': None}]
g = market.sector_groups({'heatmap': HM})
assert [x['name'] for x in g] == ['반도체'] and g[0]['ret'] == round((2.8 * 1200 + 5.9 * 900 + 30) / 2130, 1) and g[0]['lead'] == '삼성전자', g
IX = [dict(F['indices'][0], sym='^KS11', gate5w={'on': False, 'gap': -11.65, 'partial': True, 'live_gap': -2.28}),
      {'name': '코스닥', 'sym': '^KQ11', 'close': 704.4, 'd1': 5.5, 'd5': -1.5, 'gate5w': {'on': False, 'gap': -15.39, 'partial': False}}]
gl = market.gate_line({'indices': IX})
assert gl.startswith('신규 매수 중지 — 주봉 5주선 대비 코스피 -11.7% · 코스닥 -15.4%') and '이번 주 지금까지 코스피 -2.3%' in gl, gl
assert market.flow_line({'flow': {'KOSPI': {'개인': 5207.0, '외국인': -26892.0, '기관': 17092.0}}}) == '코스피 수급(잠정) 외국인 -2.7조 · 기관 +1.7조 · 개인 +5,207억'
KR5 = dict(KR3, facts=dict(KR3['facts'], indices=IX, stocks={'KR': dict(KR3['facts']['stocks']['KR'], heatmap=HM,
           flow={'KOSPI': {'개인': 5207.0, '외국인': -26892.0, '기관': 17092.0}})}))
k5 = market.render(KR5)
assert '🚦 <b>실전 규칙</b> 신규 매수 중지' in k5 and '외국인 -2.7조' in k5 and '반도체 +4.1% (삼성전자)' in k5, k5
p5 = market_card.render(KR5, _tf.mktemp(suffix='.png'), one_liner='한 줄', tips=['팁'])
assert _I.open(p5).width == 1080
ps = market_card.render_kr2(KR5, _tf.mkdtemp(), one_liner='한 줄', tips=['팁'])
assert len(ps) == 2 and all(_I.open(p).width == 1080 for p in ps), ps
SENT.clear()
tg.send_media_group = lambda c, p, caption='': (SENT.append(('album', len(p))), True)[1]
prefs._set(5, market_fmt='photo')
market._send_one(5, KR5)
tg.send_media_group = lambda c, p, caption='': False
market._send_one(5, KR5)                       # 앨범 실패 → 1장
assert SENT == [('album', 2), ('photo', 5)], SENT
print('✅ 한국 장 2장(시장 판단 / 오늘의 종목) · 실전 신호등 · 수급 · 업종 묶음 · 테마 · 실패 대체')
print('ALL PASS')
