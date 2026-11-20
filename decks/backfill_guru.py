# -*- coding: utf-8 -*-
"""이미 만든 리포트 데이터에 대가 관점 서술(VALUE_CHAIN · LYNCH)을 채워 넣는다 — LLM 1회/종목.

2026-10-20: 산업 지도·린치 2분 점검 페이지는 autogen 이 새로 만들 때 채우지만, 기존
24종은 다음 재생성(21일 주기)까지 비어 있다. 전체를 재생성하면 종목당 LLM 8회라
비싸다. 이 스크립트는 **데이터 파일에 이미 있는 사실**(사업·세그먼트·연혁·TAM·
체크포인트·최근 실적)만 근거로 두 필드를 쓰고, 파일 끝에 덧붙인다(기존 값은 안 건드림).

    python backfill_guru.py            # 비어 있는 종목 전부
    python backfill_guru.py SATL PLTR  # 지정 종목만 (이미 있어도 덮어씀)
"""
import importlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

PROMPT = """당신은 15년 경력의 셀사이드 애널리스트입니다. {company}({ticker})에 대해 아래 [자료]에 있는 사실만
근거로 두 가지를 한국어로 채우세요. 자료에 없는 숫자·사건을 지어내지 말 것. 개조식("~함/~됨"), 클리셰 금지.
금액은 자료에 적힌 표기를 **그대로** 옮길 것 — 단위를 바꿔 쓰지 말 것(원화를 '3조 336,059억원'처럼 조·억을
섞어 다시 쓰면 1,000배씩 틀린다. 실제로 그렇게 나갔다). 확신이 없으면 숫자를 빼고 방향만 쓸 것.
순수 JSON만 출력:

{{
  "value_chain": {{
    "industry": "산업 이름 15자 이내",
    "chain": ["밸류체인 단계 4~6개, 상류→하류 순서, 각 10자 이내"],
    "position": 이 회사 주력 단계 번호(0부터, 정수),
    "spans": [걸쳐 있는 단계 번호들],
    "position_note": "그 위치의 의미 — 가격 결정력·병목·수직계열화 관점 1문장",
    "cycle": "업황 국면 1문장 — 자료에 수요·가격·수주 근거가 있을 때만, 없으면 빈 문자열",
    "drivers": ["업황을 움직이는 변수 2~3개"]
  }},
  "lynch": {{
    "story": "피터 린치식 2분 설명 — 무엇으로 돈을 벌고 지금 무엇이 달라지는지 3문장, 숫자 1~2개",
    "must_happen": ["이 이야기가 맞으려면 일어나야 할 일 3개 — 확인 가능한 사건·숫자·시점"],
    "breaks_if": ["이야기가 깨졌다고 볼 신호 3개 — 확인 가능한 형태"]
  }}
}}

[자료]
{facts}
"""


def _facts(D) -> str:
    g = lambda n, d=None: getattr(D, n, d)
    parts = [f"업종: {(g('COMPANY') or {}).get('sector', '')}",
             '사업: ' + ' / '.join(map(str, g('BUSINESS', []) or [])),
             '세그먼트: ' + json.dumps(g('SEGMENTS', {}), ensure_ascii=False, default=str)[:1500],
             '연혁: ' + str((g('HISTORY') or {}).get('note', ''))[:600],
             'TAM: ' + json.dumps(g('TAM', {}), ensure_ascii=False, default=str)[:800],
             '최근 실적: ' + json.dumps((g('RESULTS') or {}).get('facts', []), ensure_ascii=False, default=str)[:1200],
             '체크포인트(경영진 로드맵): ' + json.dumps(g('CHECKPOINTS', []), ensure_ascii=False)[:1500],
             '경쟁: ' + json.dumps(g('CANSLIM_N_DETAIL', {}), ensure_ascii=False)[:600],
             '요약: ' + str(g('SUMMARY', ''))]
    return '\n'.join(parts)


def backfill(tk: str, force=False) -> bool:
    import analyzer
    import check
    mod = check.module_for(tk)
    have_vc, have_ly = bool(getattr(mod, 'VALUE_CHAIN', None)), bool(getattr(mod, 'LYNCH', None))
    if have_vc and have_ly and not force:
        print(f'[{tk}] 이미 있음 — 건너뜀')
        return False
    company = (getattr(mod, 'COMPANY', {}) or {}).get('name', tk)
    prompt = PROMPT.format(company=company, ticker=tk, facts=_facts(mod))
    data = analyzer._parse(analyzer._generate(analyzer._client(), prompt).text)
    if data.get('_parse_error'):
        print(f'[{tk}] 파싱 실패 — 건너뜀')
        return False
    vc = data.get('value_chain') if isinstance(data.get('value_chain'), dict) else {}
    ly = data.get('lynch') if isinstance(data.get('lynch'), dict) else {}
    path = Path(mod.__file__)
    src = path.read_text(encoding='utf-8')
    add = '\n\n# ── 대가 관점 서술(backfill_guru.py, 데이터 파일의 기존 사실만 근거) ──\n'
    if vc and (force or not have_vc):
        add += f'VALUE_CHAIN = {vc!r}\n'
    if ly and (force or not have_ly):
        add += f'LYNCH = {ly!r}\n'
    path.write_text(src.rstrip('\n') + add, encoding='utf-8')
    importlib.reload(mod)
    print(f'[{tk}] 채움: ' + ', '.join(k for k, v in (('VALUE_CHAIN', vc), ('LYNCH', ly)) if v))
    return True


if __name__ == '__main__':
    import check
    args = [a.upper() for a in sys.argv[1:]]
    tickers = args or check._all_tickers()
    n = 0
    for tk in tickers:
        try:
            n += backfill(tk, force=bool(args))
        except SystemExit as e:
            print(f'[{tk}] 중단: {e}')
            break
        except Exception as e:
            print(f'[{tk}] 실패: {type(e).__name__}: {e}')
        time.sleep(4)            # 무료 티어 분당 한도
    print(f'완료 {n}/{len(tickers)}')
