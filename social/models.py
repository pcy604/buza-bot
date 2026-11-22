"""콘텐츠(플랫폼 무관 코어)와 포스트(플랫폼별 산출물)."""
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

DISCLAIMER = ('본 내용은 과거 데이터의 정리이며 특정 종목의 매수·매도 권유가 아닙니다. '
              '투자 판단과 책임은 본인에게 있습니다.')

@dataclass
class Content:
    slug: str                      # soxx_mdd_001
    hook: str                      # 첫 줄. 스크롤 멈추게 하는 한 문장
    core: list                     # 핵심 문단 list[str] — 모든 플랫폼 공통
    numbers: list = field(default_factory=list)   # 표로 나갈 수치 list[str] ("2008년 -67% → 회복 1,856일")
    takeaway: str = ''             # 한 줄 결론
    caveat: str = ''               # 이게 틀릴 수 있는 경우(정직 원칙)
    cta: str = ''                  # 다음 행동 한 가지
    cta_url: str = ''
    images: list = field(default_factory=list)    # 로컬 PNG 경로. 첫 장이 대표
    tags: list = field(default_factory=list)
    disclaimer: str = DISCLAIMER
    # ── 2026-11-23 시황 생성기(social/sihwang.py)가 채우는 것들 ────────────────
    cards: list = field(default_factory=list)     # [{card, capture, text, say, guess, big, big_label}]
    hook_candidates: list = field(default_factory=list)   # 승인 때 사람이 고른다
    kind: str = ''                                # kr | daily
    date: str = ''
    title_naver: str = ''                         # 네이버는 검색 유입 — 제목을 따로 만든다

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        # 생성기가 내부용 키(_v19 등)를 붙여도 깨지지 않게 — 모르는 키는 버린다
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

@dataclass
class Post:
    platform: str      # threads | x | instagram | naver
    texts: list        # 1개면 단일 포스트, 2개 이상이면 스레드(첫 글 + 답글 체인)
    images: list       # 로컬 경로 (게시 시 공개 URL로 변환)
    note: str = ''     # 사람 보라고 남기는 메모(예: "캐러셀 10장 제한으로 2장 생략")

    def dump(self):
        return asdict(self)
