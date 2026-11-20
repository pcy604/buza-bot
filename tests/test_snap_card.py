# -*- coding: utf-8 -*-
"""snap_card — 대시보드 스냅샷(JSON)을 그리기만 하는지, 낡으면 폴백하는지 (2026-11-13 통폐합 P2)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIX = os.path.join(os.path.dirname(__file__), 'fixtures', 'snap_AAA.json')


def _snap():
    return json.load(open(FIX, encoding='utf-8'))


def test_summary_and_deck_render():
    import snap_card as sc
    from PIL import Image
    snap = _snap()
    snap['asof'] = __import__('datetime').date.today().isoformat()
    p = sc.summary(snap)
    im = Image.open(p)
    assert im.size[0] == 1080 and 900 < im.size[1] < 4000
    d = sc.deck(snap)
    assert 2 <= len(d) <= 7 and all(Image.open(x).size[0] == 1080 for x in d)
    cap = sc.caption(snap)
    assert 'Triple A' in cap and '깨지는 조건' in cap and 'sym=AAA' in cap


def test_fresh_rule():
    import snap_card as sc
    snap = _snap()
    snap['asof'] = '2020-01-01'
    assert not sc.is_fresh(snap)
    assert not sc.is_fresh(None)
    snap['asof'] = __import__('datetime').date.today().isoformat()
    assert sc.is_fresh(snap)


def test_send_snap_falls_back_when_missing(monkeypatch):
    os.environ.setdefault('SUPABASE_URL', 'https://x.supabase.co')
    os.environ.setdefault('SUPABASE_KEY', 'x')
    os.environ.setdefault('TELEGRAM_BOT_TOKEN', '1:x')
    import bot
    import snap_card as sc
    monkeypatch.setattr(sc, 'fetch', lambda code, timeout=15: None)
    sent = []
    monkeypatch.setattr(bot.tg, 'send_photo', lambda *a, **k: sent.append(a) or True)
    assert bot.send_snap(1, 'ZZZ') is False and not sent        # 스냅샷 없음 → False(호출자가 옛 엔진으로)
    monkeypatch.setattr(sc, 'fetch', lambda code, timeout=15: {**_snap(), 'asof': __import__('datetime').date.today().isoformat()})
    monkeypatch.setattr(bot.history, 'log', lambda *a, **k: None)
    assert bot.send_snap(1, 'AAA') is True and len(sent) == 1
