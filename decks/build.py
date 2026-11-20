# -*- coding: utf-8 -*-
"""티커 지정 렌더 진입점.

    python build.py PLTR      # 이미 손으로 다듬은 종목(TICKERS에 수동 등록)
    python build.py IONQ      # {ticker}_data.py만 있으면 자동등록(아래 _auto_config)

TICKERS는 사람이 site·ceo 등을 직접 다듬은(手) 종목만 남긴다 — SATL/PLTR/TSLA처럼
로고·경영진 사진을 검증해본 종목. 그 외(autogen.py가 만든 신규 종목)는 데이터 파일
자체에 COMPANY·SITE·PEERS.ciks가 다 들어있어(autogen.py가 그렇게 씀) TICKERS에 손으로
한 줄 추가할 필요 없이 자동 등록된다 — "티커만 치면 된다"의 마지막 연결고리.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TICKERS = {
    'SATL': dict(data_module='satl16_data', name='Satellogic Inc.', exchange='NASDAQ',
                sector='지구관측(EO) · 지리공간 인텔리전스', cik=1874315,
                peers={'PL': 1836833, 'BKSY': 1753539}, site='https://satellogic.com',
                ceo='Emiliano Kargieman', wiki_file='5/5f/Satellogic.png'),
    # exchange가 원래 'NASDAQ'로 잘못 手등록돼 있었음 — Palantir는 2020-09-30
    # NYSE 직상장(traditional IPO 아님)이 맞음(공개적으로 확립된 사실, 실제 발견해 수정).
    'PLTR': dict(data_module='pltr_data', name='Palantir Technologies Inc.', exchange='NYSE',
                sector='빅데이터 분석·AI 운영 플랫폼', cik=1321655,
                peers={'SNOW': 1640147, 'AI': 1577526}, site='https://www.palantir.com',
                ceo='Alexander Karp', wiki_file=''),
    'TSLA': dict(data_module='tsla_data', name='Tesla, Inc.', exchange='NASDAQ',
                sector='전기차·에너지저장·AI/로보틱스', cik=1318605,
                peers={'RIVN': 1874178, 'LCID': 1811210}, site='https://www.tesla.com',
                ceo='Elon Musk', wiki_file=''),
}


def _auto_config(ticker: str):
    """TICKERS에 없는 티커 — {ticker}_data.py를 직접 열어 필요한 값을 뽑는다.
    autogen.py가 만든 파일엔 COMPANY·PEERS.ciks·SITE·LEADERSHIP.ceo.name이 전부
    있으므로(2026-08 이후 버전) 사람이 따로 등록 안 해도 됨."""
    import importlib
    # 한국 종목은 티커가 숫자로 시작해(247540.KQ) 파이썬 모듈명이 될 수 없다 —
    # autogen_kr.module_name()과 같은 규칙으로 'kr247540_data'를 쓴다.
    if ticker.upper().endswith(('.KS', '.KQ')):
        import sources_kr
        mod_name = sources_kr.module_name(ticker)
    else:
        mod_name = f'{ticker.lower()}_data'
    try:
        data_module = importlib.import_module(mod_name)
    except ImportError:
        return None
    company = getattr(data_module, 'COMPANY', {})
    peers = getattr(data_module, 'PEERS', {})
    leadership = getattr(data_module, 'LEADERSHIP', {})
    ceo_name = (leadership.get('ceo') or {}).get('name', '')
    if ceo_name.startswith('('):   # "(CEO 성명 확인 필요)" 같은 플레이스홀더
        ceo_name = ''
    return dict(data_module=mod_name, name=company.get('name', ticker),
               exchange=company.get('exchange', ''), sector=company.get('sector', ''),
               cik=None, peers=peers.get('ciks', {}), site=getattr(data_module, 'SITE', ''),
               ceo=ceo_name, wiki_file='')


def build(ticker: str, out_dir=None):
    import importlib
    import deck_pages as P

    cfg = TICKERS.get(ticker) or _auto_config(ticker)
    if not cfg:
        raise SystemExit(f'{ticker}: TICKERS 미등록 + {ticker.lower()}_data.py도 없음 — '
                         f'먼저 `python autogen.py {ticker}` 실행 필요')
    data_module = importlib.import_module(cfg['data_module'])
    cik = cfg['cik'] if cfg['cik'] is not None else getattr(data_module, 'COMPANY', {}).get('cik')
    if cik is None:
        if ticker.upper().endswith(('.KS', '.KQ')):
            # 한국 종목은 SEC CIK가 없다 — 그 자리에 DART corp_code를 넣는다.
            # (sources_kr 이 같은 인자 자리를 corp_code 로 해석한다.)
            import sources_kr
            cik = sources_kr.to_corp_code(ticker)
            if cik is None:
                raise SystemExit(f'{ticker}: DART corp_code를 못 찾음 — 종목코드 오타이거나 '
                                 f'비상장/상장폐지일 수 있음')
        else:
            # autogen.py가 만든 파일은 COMPANY에 cik를 안 담아뒀을 수 있어(과거 버전) —
            # ir.resolve_ticker로 즉석 조회(느리지만 안전).
            import ir
            cik, _ = ir.resolve_ticker(ticker)
    kw = P.configure(data_module=data_module, ticker=ticker, name=cfg['name'],
                     exchange=cfg['exchange'], sector=cfg['sector'], cik=cik,
                     peers=cfg['peers'], site=cfg['site'], ceo=cfg['ceo'],
                     wiki_file=cfg.get('wiki_file', ''))
    build.data_module = data_module      # 렌더 후 점검(check.py)이 재임포트 없이 쓰도록
    return P.render_all(out_dir=out_dir or f'out/{ticker.lower()}', **kw)


if __name__ == '__main__':
    tk = sys.argv[1].upper() if len(sys.argv) > 1 else 'SATL'
    # 렌더 **전에** 교차검증을 고친다 — 고친 뒤 렌더해야 카드에 반영된다.
    # (2026-08-17 WDAY: 같은 2p에 영업이익 증가율이 767%와 762%로 갈려 있었다.
    #  kpis는 XBRL 결정론이고 facts는 LLM 서술이라, kpis 쪽을 원천으로 교정한다.)
    try:
        import crosscheck
        crosscheck.report(tk, do_fix=True)
        import importlib
        for m in list(sys.modules):
            if m.endswith('_data'):
                importlib.reload(sys.modules[m])       # 고친 값으로 렌더하도록 다시 읽는다
    except Exception as e:
        print(f'[교차검증 생략] {e}')
    for p in build(tk):
        print(p)
    # 렌더가 끝나면 항상 발행 전 점검을 같이 돌린다 — 사람이 12장을 눈으로 훑어야만
    # 빈 항목·자리표시자를 발견하던 구조가 "같은 지적 반복"의 직접적 원인이었다.
    try:
        import check
        n_block = check.report(tk, getattr(build, 'data_module', None))
        # 2026-08-16: 종목 하나만 보고 끝내던 게 "12종 중 3종만 발행" 상태를 몇 주간
        # 아무도 모르게 만든 원인이었다. 렌더할 때마다 전체 밀린 것을 같이 보여준다.
        # (out/*.png는 gitignore라 러너에선 못 보므로, 이 감시는 로컬에서만 유효하다)
        try:
            check.pending_line()
        except Exception:
            pass
        sys.exit(1 if n_block else 0)
    except SystemExit:
        raise
    except Exception as e:
        print(f'[점검 실패] {e}')
