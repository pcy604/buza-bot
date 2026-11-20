"""대시보드 '사이클 비교 — 겹쳐 보기(같은 출발점)' 차트를 **대시보드 코드 그대로** 헤드리스로 뽑는다.
ui_cycle.render_for 의 figure 로직을 재사용(색·구간 정의·중앙 경로 동일). 콘텐츠 이미지는 여기서 나온다.
사용: python -m social.chart_cycle SOXX [기간년수=10] [되돌림%=30]"""
import sys
sys.path.insert(0, r'C:\Users\lg\Desktop\stock_screener')
import pandas as pd
import plotly.graph_objects as go
import cycle_compare as C
import ui_cycle as U                      # _segments · _PAL · _RED 재사용 (streamlit import 는 되지만 실행은 안 됨)


def build(sym: str, years: int = 10, pct: float = 30.0):
    close = C.load_close(sym, 'US')
    close = close.dropna(); close = close[close > 0]
    cl = close if years <= 0 else close[close.index >= close.index[-1] - pd.DateOffset(years=years)]
    segs, _ = U._segments(cl, C.swing_rows(cl, float(pct)))
    sub = [s for s in segs if s['direction'] == '하락']
    live = next((s for s in sub if s.get('live')), None)
    w = C.where_now(segs, live) if live else None
    fig = go.Figure()
    for i, s in enumerate(sub):
        lv = s.get('live')
        c_ = '#111827' if lv else U._PAL[i % len(U._PAL)]
        nm = f"{s['label']} ({s['start']}~{'진행 중' if lv else s['end']})".replace(' (진행 중) (', ' (')
        fig.add_trace(go.Scatter(x=list(s['series'].index), y=s['series'].values, name=nm, mode='lines',
                                 line=dict(color=c_, width=4 if lv else 2)))
    mp = C.median_path([s for s in sub if not s.get('live')])
    if mp is not None and len(mp) > 1:
        fig.add_trace(go.Scatter(x=list(mp.index), y=mp.values, name='과거 중앙', line=dict(color='#6B7280', width=3, dash='dot')))
    fig.add_hline(y=0, line=dict(color='#999', width=1, dash='dot'))
    return fig, sub, live, w, str(cl.index[-1].date())


def render(sym: str, years: int, pct: float, out: str):
    fig, sub, live, w, asof = build(sym, years, pct)
    sub_t = f"{sym} · 꼭짓점 기준 {pct:.0f}% 되돌림 · 최근 {years}년 · 가로=고점부터 경과 거래일 · 세로=고점 대비 %"
    fig.update_layout(template='plotly_white', width=1080, height=1350, font=dict(family='Malgun Gothic', size=20),
                      title=dict(text=f"<b>하락 사이클 겹쳐 보기 — 같은 출발점</b><br><sup>{sub_t}</sup>", x=0.02, font=dict(size=30)),
                      legend=dict(orientation='h', y=-0.08, yanchor='top', font=dict(size=17)),
                      margin=dict(l=70, r=30, t=130, b=260),
                      xaxis=dict(title='고점 이후 경과 거래일'), yaxis=dict(ticksuffix='%'))
    if live and w:
        txt = (f"지금: 하락 {live['days']}거래일째 · {live['ret']:+.1f}%<br>"
               f"과거 하락 {w['n']}회 중앙: {w['days_med']:.0f}일 · {w['ret_med']:+.0f}%<br>"
               f"과거 대비 위치: 기간 {w['days_pct']:.0f} · 폭 {w['ret_pct']:.0f} 백분위")
        fig.add_annotation(x=0.98, y=0.02, xref='paper', yref='paper', text=txt, showarrow=False, align='right',
                           font=dict(size=19), bgcolor='rgba(255,255,255,0.85)', bordercolor='#111827', borderwidth=1)
    fig.add_annotation(x=0.0, y=-0.19, xref='paper', yref='paper', showarrow=False, xanchor='left', font=dict(size=14, color='#6B7280'),
                       text=f"stock_studian · stock-dashboard 종목분석 → 사이클 비교 · {asof} 종가 · 투자 권유 아님")
    fig.write_image(out, scale=1)
    return sub, live, w, asof


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sym = sys.argv[1] if len(sys.argv) > 1 else 'SOXX'
    yrs = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    pct = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0
    out = f'social/out/{sym.lower()}_cycle_{yrs}y_{int(pct)}.png'
    sub, live, w, asof = render(sym, yrs, pct, out)
    print('asof', asof, '->', out)
    for s in sub:
        print(f"{s['label']:14s} {s['start']} ~ {s['end']}  {s['days']:4d}일  {s['ret']:+.1f}%  회복 {s.get('recover')}")
    print('where_now', w)
