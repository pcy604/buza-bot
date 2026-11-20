"""상태 JSON 3-way 병합 드라이버 (git merge driver) — 2026-10-23

왜: 웹훅 실행은 병렬로 돈다(run.yml concurrency). 두 실행이 같은 cmd_log.json·news_log.json
에 줄을 하나씩 붙이면 rebase 가 텍스트 충돌로 멈추고, 3회 재시도 뒤 '이번 실행분 유실'로
끝났다(2026-10-21 14:27, 10-22 06:46 실패가 이것). 내용은 충돌이 아니라 '둘 다 추가'다.

사용: .gitattributes 의 `merge=jsonstate` +
      git config merge.jsonstate.driver "python tools/state_merge.py %O %A %B"
  %O 공통 조상 · %A 현재(rebase 중에는 원격 최신) · %B 다른 쪽(이번 실행 커밋). 결과는 %A 에 쓴다.

규칙
- 리스트: A 순서를 유지하고 B 에만 있는 항목을 뒤에 붙인다(롤링 상한은 앱이 다음 쓰기에서 자름).
- 딕셔너리: 키별 3-way. 한쪽만 바뀌었으면 그쪽, 둘 다 바뀌었으면 재귀, 값이 스칼라면 B(새 실행).
  한쪽에서 지운 키는 다른 쪽이 그 키를 안 바꿨을 때만 지운다.
- JSON 이 아니면 실패(exit 1) → git 이 평소처럼 충돌로 처리.
"""
import json
import sys

_MISSING = object()


def _key(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


def merge(o, a, b):
    if a == b:
        return a
    if b == o:
        return a
    if a == o:
        return b
    if isinstance(a, list) and isinstance(b, list):
        seen = {_key(x) for x in a}
        return list(a) + [x for x in b if _key(x) not in seen]  # 상한은 앱이 다음 쓰기에서 자른다
    if isinstance(a, dict) and isinstance(b, dict):
        o = o if isinstance(o, dict) else {}
        out = {}
        for k in list(a) + [k for k in b if k not in a]:
            ov, av, bv = o.get(k, _MISSING), a.get(k, _MISSING), b.get(k, _MISSING)
            if av is _MISSING:          # A 에 없음: A 가 지웠거나 B 가 새로 만듦
                if ov is _MISSING or bv != ov:
                    out[k] = bv
                continue
            if bv is _MISSING:          # B 에 없음
                if ov is _MISSING or av != ov:
                    out[k] = av
                continue
            out[k] = merge(None if ov is _MISSING else ov, av, bv)
        return out
    return b  # 스칼라 양쪽 변경 — 이번 실행 값


def _load(p):
    with open(p, encoding='utf-8') as f:
        txt = f.read()
    return json.loads(txt) if txt.strip() else None


def main(argv):
    o_p, a_p, b_p = argv[1:4]
    try:
        o, a, b = _load(o_p), _load(a_p), _load(b_p)
    except Exception as e:  # JSON 이 아니면 git 기본 충돌 처리로
        print(f"state_merge: JSON 아님 — {e}", file=sys.stderr)
        return 1
    res = merge(o, a, b)
    with open(a_p, encoding='utf-8') as f:
        pretty = '\n' in f.read().strip()   # 원래 서식 유지(한 줄 JSON 이면 한 줄로)
    with open(a_p, 'w', encoding='utf-8') as f:
        f.write(json.dumps(res, ensure_ascii=False, indent=1 if pretty else None))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
