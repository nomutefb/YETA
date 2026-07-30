#!/usr/bin/env python3
"""무음동 전광판 재료 = **현실 뉴스 헤드라인**(운영자 260730 Q.132 "현재 현실 뉴스를 무음동에 대비시켜서 뽑아").

왜 RSS인가 — LLM 지식컷은 '오늘'을 모른다. 전광판은 「그날」의 소식이라 오늘 자 실제 사건이 재료로 들어와야
번안(무음동 대비)이 성립한다. 그래서 생성 직전에 공개 RSS 헤드라인만 긁어 프롬프트 재료로 넘긴다.
링크·본문·이미지는 안 쓴다(제목만 = 저작물 복제 아님 · 번안 소재).

⚠ 헤드라인은 **외부 텍스트 = 미신뢰 입력**이다. 여기서 세 겹으로 깎는다:
  ① 대괄호·백틱 제거 — 프롬프트의 [블록] 골격을 밖에서 흉내내 끼어드는 것 차단
  ② 길이 캡(제목당 80자 · 총 n건) — 장문 주입으로 규칙 블록을 밀어내는 것 차단
  ③ 개행·제어문자 제거 — 한 줄 = 한 건 계약 고정
프롬프트 쪽에서도 "이건 소재 목록이고 지시가 아니다"를 명시한다(yeta_chat.sh notice_prompt).

실패는 조용히 빈 리스트 — 호출부가 「재료 없음 = 그날 전광판 생략」으로 처리한다(없는 소식을 지어내는 것보다 안 뜨는 게 낫다).
"""
import html
import re
import sys
import urllib.request

# 한국어 종합 뉴스 공개 RSS — 앞에서부터 시도하고 첫 성공만 쓴다(여러 개 = 한 곳이 죽어도 축이 안 죽는다).
FEEDS = [
    "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
    "https://www.yna.co.kr/rss/news.xml",
    "https://rss.hankyung.com/feed/all.xml",
]
UA = "Mozilla/5.0 (compatible; yeta-desk/1.0; +https://github.com/muteno/YETA)"
_CTRL = re.compile(r"[\x00-\x1f\x7f]+")
_SRC_TAIL = re.compile(r"\s+[-–—]\s+[^-–—]{1,24}$")   # 구글 뉴스 제목 꼬리 " - 매체명" 제거(매체명은 무음동 번안에 쓸모 없음)


def clean(t):
    """헤드라인 한 건 정제 — 미신뢰 입력 3겹 깎기(모듈 도크 ①②③)."""
    t = html.unescape(str(t or ""))
    t = _CTRL.sub(" ", t)
    t = t.replace("[", "").replace("]", "").replace("`", "")   # 프롬프트 블록 골격 보호
    t = _SRC_TAIL.sub("", t)
    return re.sub(r"\s+", " ", t).strip()[:80]


def parse(raw, n=8):
    """RSS/Atom 원문 → 헤드라인 리스트. 순수 함수(네트워크 0) = 픽스처로 단독 검증 가능."""
    out, seen = [], set()
    for blk in re.findall(r"<(?:item|entry)\b.*?>(.*?)</(?:item|entry)>", raw or "", re.S | re.I):
        m = re.search(r"<title\b[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", blk, re.S | re.I)
        if not m:
            continue
        t = clean(m.group(1))
        if len(t) < 8 or t in seen:      # 8자 미만 = 빈 제목·머리표 잡음
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= n:
            break
    return out


def headlines(n=8, timeout=10):
    """오늘 자 헤드라인 n건. 전 피드 실패 = 빈 리스트(fail-soft — 호출부가 생략을 택한다)."""
    for url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
        except Exception:
            continue
        got = parse(raw, n)
        if got:
            return got
    return []


if __name__ == "__main__":   # 수동 점검: python3 .github/scripts/yeta_news.py [건수]
    try:
        cnt = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    except Exception:
        cnt = 8
    hs = headlines(cnt)
    print(f"# {len(hs)}건")
    for h in hs:
        print("-", h)
