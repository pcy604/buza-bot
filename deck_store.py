# -*- coding: utf-8 -*-
"""발행된 12p 포토카드의 텔레그램 file_id 보관소.

## 왜 이런 게 필요한가

12장 포토카드(`decks/`, stock_studian)는 로컬에서 만들어 `decks/out/{ticker}/`에
쌓인다. 그런데 봇은 GitHub Actions 러너에서 도는데 그 폴더는 `.gitignore`라
러너엔 존재하지 않는다. 그래서 `/report`가 12장을 보내려 해도 보낼 파일이 없다.

텔레그램은 한 번 올린 사진마다 `file_id`를 돌려주고, 그 id만 있으면 파일 없이
다시 보낼 수 있다. 그래서 로컬에서 `publish.py`로 한 번 발행할 때 id를 여기
적어두고, 봇은 그 id로 재전송만 한다. 러너에 PNG가 없어도 되고, Gemini를 다시
태우지도 않고, 응답이 즉시다.

## 검수 게이트가 그대로 살아있다

id는 **로컬에서 `check.py`를 통과해 실제로 발행한 종목에만** 생긴다. 검수를 안
거친 덱은 여기 등록되지 않으므로 봇으로도 나갈 수 없다. 자동 생성·자동 발행을
막아둔 원칙(AAPL 무검수 초안에서 30건 넘게 나왔다)이 유지된다.

## 알려진 한계

- **덱을 다시 만들면 옛 id가 낡는다.** 그래서 발행할 때마다 덮어쓰고 `published`
  날짜를 같이 적는다. 봇이 보낼 때 그 날짜를 캡션에 넣어 언제 만든 건지 드러낸다.
- **아직 안 만든 종목은 줄 수 없다.** 봇이 "없다"고 답하고 끝낸다.
- **텔레그램이 file_id 영속을 보장하진 않는다.** 실무상 오래 살지만, 실패하면
  로컬에서 다시 발행하는 게 복구 절차다.
"""
import json
import os
from pathlib import Path

PATH = Path(__file__).resolve().parent / 'deck_files.json'


def _load() -> dict:
    if not PATH.exists():
        return {}
    try:
        with open(PATH, encoding='utf-8') as fp:
            return json.load(fp)
    except Exception as e:
        print(f'[deck_store 읽기 실패] {e}')
        return {}


def get(ticker: str):
    """등록된 덱 정보. 없으면 None."""
    return _load().get(ticker.upper())


def tickers() -> list:
    return sorted(_load().keys())


def save(ticker: str, file_ids: list, n_pages: int, title: str = '') -> bool:
    """발행 결과를 기록한다. 같은 티커면 덮어쓴다(재발행 시 옛 id는 버린다)."""
    import datetime
    if not file_ids:
        return False
    data = _load()
    data[ticker.upper()] = {
        'file_ids': list(file_ids),
        'pages': n_pages,
        'title': title,
        'published': datetime.date.today().isoformat(),
    }
    with open(PATH, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    return True
