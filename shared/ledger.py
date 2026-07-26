#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원장 번호 SSOT — 다음 번호 산출 + 중복 게이트.

왜 있나(260726 사고):
  세션 여러 개가 동시에 돌면 각자 "원장 끝을 눈으로 보고 다음 번호"를 정한다. 그런데 그 사이
  다른 세션이 이미 그 번호로 커밋해버리면 같은 번호가 둘이 된다 — 실제로 한 세션이 Q.55/237차를
  썼는데 main은 그때 이미 Q.68/251차까지 가 있었다(= 번호를 13개나 헛짚었다).
  사람이 매번 눈으로 세는 대신 **여기서 실측**하고, 겹치면 커밋 전에 막는다.

쓰는 법:
  python3 shared/ledger.py           # 다음에 쓸 번호를 알려준다(원장에 항목 추가하기 전에 실행)
  python3 shared/ledger.py --check   # 중복이면 rc=1 (check_refs가 커밋 전 게이트로 호출)

⚠️ 이 스크립트는 원장을 고치지 않는다. 번호를 '알려주고 막을' 뿐 — 원장 본문은 사람이 쓴다.
"""
import collections
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM = re.compile(r'\d+')

# (파일, 헤딩 정규식, 다음번호 표기, 라벨)
#   ⚠️ 접미사 자리가 원장마다 다르다 — 큐는 `Q. 53-B`(번호 뒤), 이력은 `235차-B`(‘차’ 뒤).
#      한 정규식으로 뭉뚱그리면 `235차-B`가 `235`로 잡혀 없는 중복이 생긴다(실측 260726).
LEDGERS = [
    ('docs/요구사항_큐.md', r'^## Q\.\s*([0-9]+)(-[A-Za-z])?', 'Q.%d', '요구사항 큐'),
    ('docs/작업이력.md',    r'^## ([0-9]+)차(-[A-Za-z])?',     '%d차',  '작업이력'),
]

# 이미 원장에 있는, 진짜 충돌이 아닌 같은-번호 표기(`64차 추기` `38차(예정)` `17차+`) — 신규 중복만 잡는다.
# 여기에 번호를 더하는 건 "그 중복은 의도된 표기다"라고 선언하는 것 = 함부로 늘리지 말 것.
BASE_DUP = {'docs/작업이력.md': {'17', '38', '64', '85'}}


def _keys(rel, pat):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return [n + (sfx or '') for n, sfx in re.findall(pat, f.read(), re.M)]


def nexts():
    """[(라벨, 파일, '다음 번호 표기')] — 원장별 최대 번호 + 1."""
    out = []
    for rel, pat, fmt, label in LEDGERS:
        ks = _keys(rel, pat)
        mx = max((int(NUM.match(k).group()) for k in ks), default=0)
        out.append((label, rel, fmt % (mx + 1)))
    return out


def check():
    rc = 0
    for rel, pat, _fmt, _label in LEDGERS:
        c = collections.Counter(_keys(rel, pat))
        base = BASE_DUP.get(rel, set())
        dup = sorted((k for k, v in c.items() if v > 1 and k not in base),
                     key=lambda x: (int(NUM.match(x).group()), x))
        if dup:
            print('❌ 원장 번호 중복 — %s: %s' % (rel, ', '.join(dup)))
            print('   두 세션이 같은 번호를 각각 썼다. 나중 것을 다음 빈 번호로 옮겨라 → python3 shared/ledger.py')
            rc = 1
    if rc == 0:
        print('✅ 원장 번호 게이트 — 중복 0 · 다음 번호: %s'
              % ' · '.join('%s → %s' % (lab, n) for lab, _r, n in nexts()))
    return rc


if __name__ == '__main__':
    if '--check' in sys.argv:
        sys.exit(check())
    for lab, rel, n in nexts():
        print('%s(%s) 다음 번호 = %s' % (lab, rel, n))
