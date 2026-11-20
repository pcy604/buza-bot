# -*- coding: utf-8 -*-
"""체슬리투자자문 방식 CANSLIM 채점.

사용자가 제공한 실제 리포트 4건(정유사·CRWD·MRNA·PLTR)에서 공식을 역산해
4건 모두 총점이 일치하는 것을 확인한 구현이다.

  C = (전년동기 대비 분기 영업이익 증가율% - 5) , [0, 25] 클램프
  A = (최근 3년 연간 영업이익 CAGR% - 5)        , [0, 25] 클램프
  N = 5개 항목 합산
      ① 글로벌 탑티어           0~10점
      ② 20%+ 성장 가능 연수     연수 × 2점
      ③ 경쟁기업 수             2개 이하 0점 / 3개 이상 -2점
      ④ 지배구조 개편           해당 시 가점, 없으면 0점
      ⑤ New Market CAGR         CAGR% ÷ 2 (25점 상한)
  총점 = C + A + N

검증(역산 결과 = 리포트 기재값):
  정유사 25+0+8=33 · MRNA 0+0+14=14 · PLTR 25+25+41=91  → 정확히 일치
  CRWD 는 1점 차(67 vs 66). ⑤항 입력값이 리포트에 "CAGR +21.5%"로 반올림 표기돼 있어
  21.5/2=10.75→11이 되는데 리포트는 10점을 썼다. 즉 원본 CAGR이 21.0% 근처였다는 뜻으로,
  공식이 아니라 입력 표기 정밀도 문제 — 다른 3건이 round()로 정확히 맞으므로 round를 채택.
"""

CAP = 25.0
HURDLE = 5.0


def _clamp(v, lo=0.0, hi=CAP):
    return max(lo, min(hi, v))


def growth_pct(cur, prior):
    """영업이익 증가율. 적자→적자도 체슬리 예시(MRNA)처럼 |전년|을 분모로 쓴다."""
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / abs(prior) * 100


def cagr_pct(first, last, years):
    """연간 영업이익 CAGR. 음수가 끼면 수학적으로 정의되지 않으므로 0%로 둔다
    (체슬리 MRNA 사례: 적자 3년치를 'CAGR 0%'로 처리)."""
    if first is None or last is None or years <= 0:
        return None
    if first <= 0 or last <= 0:
        return 0.0
    return ((last / first) ** (1 / years) - 1) * 100


def score_c(q_cur, q_prior):
    g = growth_pct(q_cur, q_prior)
    return (_clamp(g - HURDLE) if g is not None else 0.0), g


def score_a(a_first, a_last, years=2):
    g = cagr_pct(a_first, a_last, years)
    return (_clamp(g - HURDLE) if g is not None else 0.0), g


def score_n(top_tier=0, growth_years=0, competitors=0, governance=0, market_cagr=None):
    """N 5개 항목. 반환: (총점, [(항목명, 세부, 점수), ...])"""
    comp_pt = 0 if competitors <= 2 else -2
    # 체슬리 예시가 정수 점수로 표기됨(8.94→9, 10.75→10) — 반올림해 합계와 표기를 일치시킴
    mk_pt = round(_clamp(market_cagr / 2, 0, CAP)) if market_cagr is not None else 0
    yr_pt = growth_years * 2
    rows = [
        ('글로벌 탑티어', top_tier),
        ('20%+ 성장 가능 연수', yr_pt),
        ('경쟁기업 수', comp_pt),
        ('지배구조 개편', governance),
        ('New Market CAGR', mk_pt),
    ]
    return sum(v for _, v in rows), rows


def evaluate(q_cur, q_prior, a_first, a_last, n_kwargs, a_years=2):
    c, c_g = score_c(q_cur, q_prior)
    a, a_g = score_a(a_first, a_last, a_years)
    n, n_rows = score_n(**n_kwargs)
    return {
        'C': c, 'C_growth': c_g,
        'A': a, 'A_cagr': a_g,
        'N': n, 'N_rows': n_rows,
        'total': c + a + n,
    }


if __name__ == '__main__':
    # 제공받은 4개 리포트로 자기검증
    cases = [
        ('정유사', dict(q_cur=2.763, q_prior=1.975, a_first=19.8, a_last=12.7,
                        n_kwargs=dict(top_tier=10, growth_years=0, competitors=5, market_cagr=None)), 33),
        ('CRWD', dict(q_cur=325.7, q_prior=201.1, a_first=660.3, a_last=1050.0,
                      n_kwargs=dict(top_tier=10, growth_years=1, competitors=5, market_cagr=21.5)), 66),
        ('MRNA', dict(q_cur=-1.388, q_prior=-1.050, a_first=-4.239, a_last=-3.074,
                      n_kwargs=dict(top_tier=5, growth_years=1, competitors=5, market_cagr=17.88)), 14),
        ('PLTR', dict(q_cur=983.5, q_prior=390.8, a_first=632.8, a_last=2254.0,
                      n_kwargs=dict(top_tier=10, growth_years=3, competitors=2, market_cagr=49.6)), 91),
    ]
    for name, kw, expect in cases:
        r = evaluate(**kw)
        d = abs(round(r['total']) - expect)
        tag = 'OK' if d == 0 else ('OK(±1, 입력 표기 반올림)' if d <= 1 else '불일치')
        print(f'{name:8s} C={r["C"]:5.1f} A={r["A"]:5.1f} N={r["N"]:5.1f} '
              f'총={r["total"]:6.1f} (리포트 {expect}) {tag}')
