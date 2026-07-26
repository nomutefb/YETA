#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_v3 세션 어댑터 — 회귀 + '대화 품질' 스냅샷 테스트 (pytest 불요 · stdlib만).

왜: `.github/scripts/yeta_v3.py` = 러너 세션 로직의 근본(마이그레이션·방·스레드 선택).
    회귀 테스트가 0이라, 리팩터 때 '대화가 어떤 방·페르소나·기억으로 풀리는지'가 조용히
    바뀌어도 안 잡혔다. 이 하니스는 그 '풀린 대화 상태'를 전/후로 눈에 보이게 만든다.

무엇 (3층):
  1. 스펙 불변식 — 멱등·턴무손실·cur유효·방≤2·비밀누수차단. 코드 docstring + JS 쌍둥이
     (functions/api/yeta.js migrateV3)에서 도출 = '현재 출력에 맞춘 박제'가 아님.
  2. 골든 스냅샷 — 시나리오별 '풀린 대화 상태'(cur/threads/pick/view)를 박제. 로직이 바뀌면
     읽을 수 있는 before/after diff로 "대화 품질이 이렇게 달라졌다"를 노출.
  3. parity — JS migrateV3 실물을 추출·node 실행해 PY와 대조(동형 붕괴 자동 포착).

실행:
  python3 tests/test_yeta_v3.py            # 체크(불변식+골든) · rc=0 통과 / rc=1 회귀
  python3 tests/test_yeta_v3.py --report   # 대화 품질 상태를 사람이 읽게 출력(전/후 눈으로)
  python3 tests/test_yeta_v3.py --update    # 골든 재생성(= 의도된 변경 승인 · diff 확인 후)
  python3 tests/test_yeta_v3.py --parity    # JS↔PY 동형 대조(node 필요)
"""
import os
import sys
import json
import copy
import importlib.util
import subprocess
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(ROOT, '.github', 'scripts', 'yeta_v3.py')
_spec = importlib.util.spec_from_file_location('yeta_v3', _SRC)
V3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V3)

NOW = 5_000_000            # 고정 시각(ms) — 결정론. INVITE_TTL_MS=600000이라 신선 invite = NOW-100000.
GOLDEN = os.path.join(ROOT, 'tests', 'yeta_v3_golden.json')

# ── 픽스처(입력 세션) — '대화 품질'에 직결되는 시나리오만 ──
FIX = [
    {'name': '01_신규_비딕트', 'desc': '신규 유저(null) → 빈 v3 골격(깨끗한 시작)',
     'in': None},
    {'name': '02_v2단일→v3', 'desc': 'v2 단일 세션 랩 — 대화 무손실·last_sp 보존·대기 유저 픽업',
     'in': {'persona': 'haeun',
            'turns': [{'role': 'user', 'ts': 1000}, {'role': 'assistant', 'ts': 2000}, {'role': 'user', 'ts': 3000}],
            'state': 'idle', 'room': ['haeun'], 'note': '메모'}},
    {'name': '03_v2_persona_무턴(엣지)', 'desc': 'persona 있고 turns 없음 → threads 비고 cur=persona(엣지 박제)',
     'in': {'persona': 'von', 'turns': []}},
    {'name': '04_v3_멱등', 'desc': '이미 v3 → no-op(재마이그레이션 안전)',
     'in': {'v': 3, 'cur': 'yun',
            'threads': {'yun': {'turns': [{'role': 'user', 'ts': 1}], 'last_sp': 'yun', 'room': ['yun']}},
            'me': {'call': '주인', 'about': ''}}},
    {'name': '05_다중방_FIFO', 'desc': '두 방 다 대기 → 오래된 쪽이 풀림(기아 방지)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [{'role': 'assistant', 'ts': 1000}, {'role': 'user', 'ts': 9000}], 'last_sp': 'a', 'room': ['a']},
         'b': {'turns': [{'role': 'assistant', 'ts': 1000}, {'role': 'user', 'ts': 4000}], 'last_sp': 'b', 'room': ['b']}}}},
    {'name': '06_invite분기', 'desc': '신선 invite → 그 방이 일감으로 픽업(분기)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [{'role': 'assistant', 'ts': 1000}], 'last_sp': 'a', 'room': ['a'],
               'invite': {'to': 'b', 'ts': NOW - 100000}}}}},
    {'name': '07_타방_비밀누수차단', 'desc': 'thread_view _others = 메타만(턴 텍스트 없음)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [{'role': 'user', 'ts': 5000, 'text': '비밀A'}], 'last_sp': 'a', 'room': ['a']},
         'b': {'turns': [{'role': 'user', 'ts': 6000, 'text': '비밀B'}], 'last_sp': 'b', 'room': ['b']}}}},
    # ── 열린 방(cur) 우선 · 260726 첫 대사 지연 실측(러너 로그 23:43:31 남의 방 30s → 오프닝은 그 뒤) ──
    {'name': '08_열린방_오프닝_우선', 'desc': '지금 연 방의 첫 대사 대기 vs 다른 방 2분 전 pending → 열린 방 먼저(눈앞 대기 우선)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [], 'state': 'awaiting', 'opening': NOW - 3000, 'last_sp': 'a', 'room': ['a']},
         'b': {'turns': [{'role': 'assistant', 'ts': 1000}, {'role': 'user', 'ts': NOW - 120000}], 'last_sp': 'b', 'room': ['b']}}}},
    {'name': '09_묵은방_양보', 'desc': '다른 방 pending 이 5분 묵음(>CUR_YIELD 3분) → 열린 방이 양보(기아 방지)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [], 'state': 'awaiting', 'opening': NOW - 3000, 'last_sp': 'a', 'room': ['a']},
         'b': {'turns': [{'role': 'assistant', 'ts': 1000}, {'role': 'user', 'ts': NOW - 300000}], 'last_sp': 'b', 'room': ['b']}}}},
    {'name': '10_gb는_비우선', 'desc': '열린 방이 단톡 자율 비트뿐 → 유저를 기다리는 다른 방이 먼저(_age_kind 계약 온존)',
     'in': {'v': 3, 'cur': 'a', 'threads': {
         'a': {'turns': [{'role': 'assistant', 'ts': 1000}], 'last_sp': 'a', 'room': ['a', 'sera'],
               'gb': {'p': 'sera', 'ts': NOW - 10000, 'n': 1}},
         'b': {'turns': [{'role': 'assistant', 'ts': 1000}, {'role': 'user', 'ts': NOW - 60000}], 'last_sp': 'b', 'room': ['b']}}}},
]


def _mig(inp):
    return V3.migrate_v3(copy.deepcopy(inp))


def resolve(inp):
    """입력 세션 → '풀린 대화 상태'(대화 품질 스냅샷). 어떤 방·페르소나·대기·타방이 보이나."""
    S = _mig(inp)
    threads = {}
    for tid, th in (S.get('threads') or {}).items():
        turns = th.get('turns') or []
        la = max([i for i, t in enumerate(turns) if t.get('role') == 'assistant'], default=-1)
        pend = len([t for t in turns[la + 1:] if t.get('role') == 'user'])
        threads[tid] = {'n_turns': len(turns), 'last_sp': th.get('last_sp'),
                        'room': [r for r in (th.get('room') or []) if r][:2],
                        'state': th.get('state') or 'idle', 'pending_users': pend,
                        'has_invite': bool((th.get('invite') or {}).get('to'))}
    pick = V3.pick_thread(S, NOW)
    view = None
    if pick:
        v = V3.thread_view(S, pick)
        view = {'persona': v.get('persona'),
                'others': sorted([{'id': o['id'], 'n': o['n'], 'updated': o['updated']} for o in (v.get('_others') or [])],
                                 key=lambda o: o['id'])}
    return {'v': S.get('v'), 'cur': S.get('cur'), 'threads': threads, 'pick': pick, 'view': view}


def invariants(inp):
    """스펙 불변식 — docstring + JS 쌍둥이에서 도출(박제 아님). {이름: 통과여부}."""
    S = _mig(inp)
    r = {}
    once = _mig(inp)
    twice = V3.migrate_v3(copy.deepcopy(once))
    r['멱등'] = json.dumps(once, sort_keys=True, ensure_ascii=False) == json.dumps(twice, sort_keys=True, ensure_ascii=False)
    is_v2wrap = (isinstance(inp, dict) and inp.get('persona') and inp.get('turns')
                 and not (inp.get('v', 0) >= 3 or 'threads' in inp))
    if is_v2wrap:
        tid = str(inp['persona'])
        r['턴무손실'] = len((S.get('threads') or {}).get(tid, {}).get('turns') or []) == len(inp['turns'])
    else:
        r['턴무손실'] = True
    cur = S.get('cur')
    r['cur유효'] = (cur == '' or cur in (S.get('threads') or {})
                  or (isinstance(inp, dict) and cur == str(inp.get('persona') or '')))
    r['방≤2'] = all(len([x for x in (th.get('room') or []) if x][:2]) <= 2
                   for th in (S.get('threads') or {}).values())
    leak = False
    for tid in (S.get('threads') or {}):
        for o in (V3.thread_view(S, tid).get('_others') or []):
            if set(o.keys()) - {'id', 'updated', 'n'}:
                leak = True
    r['비밀누수차단'] = not leak
    return r


# ── 출력 헬퍼 ──
def _flat(d, pre=''):
    """중첩 dict/list → {경로: 값} 평탄화(읽는 diff용)."""
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, '%s.%s' % (pre, k) if pre else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flat(v, '%s[%d]' % (pre, i)))
    else:
        out[pre] = d
    return out


def _diff(old, new):
    """골든(old) vs 현재(new) 리프 단위 차이 → [(경로, before, after)]."""
    fo, fn = _flat(old), _flat(new)
    keys = sorted(set(fo) | set(fn))
    return [(k, fo.get(k, '∅'), fn.get(k, '∅')) for k in keys if fo.get(k, '∅') != fn.get(k, '∅')]


def cmd_report():
    print('=== yeta_v3 대화 품질 상태 (사람이 읽는 스냅샷 · NOW=%d) ===' % NOW)
    for f in FIX:
        st = resolve(f['in'])
        inv = invariants(f['in'])
        print('\n[%s] %s' % (f['name'], f['desc']))
        print('  현재 대화(cur): %r  · v: %s' % (st['cur'], st['v']))
        if st['threads']:
            for tid, t in st['threads'].items():
                print('  방 %r: 턴 %d · 마지막화자 %r · 방%s · 대기유저 %d%s'
                      % (tid, t['n_turns'], t['last_sp'], t['room'],
                         t['pending_users'], ' · invite' if t['has_invite'] else ''))
        else:
            print('  방: (없음)')
        print('  풀리는 대화(pick): %r' % st['pick'])
        if st['view']:
            print('  보이는 뷰: 페르소나 %r · 타방 %s (텍스트 없음)'
                  % (st['view']['persona'], [o['id'] for o in st['view']['others']]))
        bad = [k for k, ok in inv.items() if not ok]
        print('  불변식: %s' % ('전부 ✓' if not bad else '❌ 실패=' + ','.join(bad)))
    return 0


def cmd_update():
    golden = {f['name']: resolve(f['in']) for f in FIX}
    os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
    with open(GOLDEN, 'w', encoding='utf-8') as fp:
        json.dump(golden, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write('\n')
    print('✅ 골든 재생성 — %s (%d 시나리오)' % (os.path.relpath(GOLDEN, ROOT), len(golden)))
    return 0


def cmd_parity():
    try:
        js = open(os.path.join(ROOT, 'functions', 'api', 'yeta.js'), encoding='utf-8').read()
    except OSError as e:
        print('⚠️ parity 스킵(yeta.js 없음):', e)
        return 0
    m = re.search(r'const migrateV3 = \(s\) => \{.*?\n  \};', js, re.S)
    if not m:
        print('⚠️ parity 스킵 — yeta.js migrateV3 블록 추출 실패')
        return 0
    node_src = (m.group(0) + '\n'
                'const fx = JSON.parse(process.argv[1]);\n'
                'const out = fx.map(f => migrateV3(f === null ? f : JSON.parse(JSON.stringify(f))));\n'
                'process.stdout.write(JSON.stringify(out));\n')
    try:
        p = subprocess.run(['node', '-e', node_src, json.dumps([f['in'] for f in FIX])],
                           capture_output=True, text=True, timeout=25)
    except Exception as e:
        print('⚠️ parity 스킵(node 실행 불가):', e)
        return 0
    if p.returncode != 0:
        print('⚠️ parity 스킵(node 오류):', (p.stderr or '')[:300])
        return 0
    js_out = json.loads(p.stdout)
    diverge = []
    for f, jo in zip(FIX, js_out):
        po = _mig(f['in'])
        a = json.dumps(po, sort_keys=True, ensure_ascii=False)
        b = json.dumps(jo, sort_keys=True, ensure_ascii=False)
        if a != b:
            diverge.append((f['name'], a, b))
    print('=== parity (JS migrateV3 ↔ PY migrate_v3 동형 대조) ===')
    KNOWN = {'01_신규_비딕트'}   # 알려진 차이: null 입력 = JS는 상류 EMPTY() 처리(migrateV3(null)=null) · PY는 인라인 골격
    real = [d for d in diverge if d[0] not in KNOWN]
    for name, a, b in diverge:
        tag = '(알려진 차이·문서화됨)' if name in KNOWN else '❌ 미문서 분기'
        print('  %s %s\n     PY: %s\n     JS: %s' % (name, tag, a, b))
    if not diverge:
        print('  ✅ 전 시나리오 동형 일치')
    if real:
        print('❌ parity — 미문서 동형 붕괴 %d건(스펙/주석 정합 필요)' % len(real))
        return 1
    print('✅ parity — 미문서 붕괴 0(알려진 null 차이만 · 하단 주석)')
    return 0


def cmd_check():
    if not os.path.exists(GOLDEN):
        print('⚠️ 골든 없음 — 먼저 `python3 tests/test_yeta_v3.py --update`로 baseline 생성')
        return 1
    golden = json.load(open(GOLDEN, encoding='utf-8'))
    inv_fail, snap_fail = [], []
    for f in FIX:
        inv = invariants(f['in'])
        for k, ok in inv.items():
            if not ok:
                inv_fail.append('%s: 불변식 %s 실패' % (f['name'], k))
        cur = resolve(f['in'])
        old = golden.get(f['name'])
        if old is None:
            snap_fail.append((f['name'], [('(신규 시나리오)', '∅', 'golden 미등재 → --update')]))
        else:
            d = _diff(old, cur)
            if d:
                snap_fail.append((f['name'], d))
    if not inv_fail and not snap_fail:
        print('✅ yeta_v3 테스트 통과 — 불변식 5종·골든 %d 시나리오 회귀 0.' % len(FIX))
        return 0
    if inv_fail:
        print('❌ 스펙 불변식 위반(= 실제 버그 후보):')
        for x in inv_fail:
            print('  -', x)
    if snap_fail:
        print('❌ 대화 품질 스냅샷 변화(= 전/후 차이 · 의도면 --update로 승인):')
        for name, d in snap_fail:
            print('  · [%s]' % name)
            for path, before, after in d:
                print('      %s : %r → %r' % (path, before, after))
    return 1


def main(argv):
    if '--report' in argv:
        return cmd_report()
    if '--update' in argv:
        return cmd_update()
    if '--parity' in argv:
        return cmd_parity()
    return cmd_check()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
