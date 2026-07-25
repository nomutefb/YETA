#!/usr/bin/env python3
"""모델 승격 일괄 치환기 — 정본 = `shared/models.json` (운영자 260725 한 수).

왜: 모델 ID가 호출처마다 리터럴로 흩어져 있다 — 이 레포 실측(260725): `gpt-image-2` 6파일 ·
   `gemini-3.1-flash-image-preview` 3파일(각자 '실제 ID 바뀌면 함께 교체' 주석 의존) · claude 티어 20+곳.
   승격마다 전수 grep = 빠뜨림·시행착오. 런타임 결합(전 호출처가 이 json을 읽게)은 Cloudflare Functions·
   정적 뷰어에 파일 접근이 없어 불가 → 「정본 1곳 + 기계 치환(이 파일) + 드리프트 게이트(check_model_ids)」.
   (nomute-editor 260725 확립분 이식 · 조정점 = models.json `_이식노트`)

사용:
    python3 shared/apply_models.py opus claude-opus-6 "Opus 6" "오퍼스 6"
    python3 shared/apply_models.py opus claude-opus-6 "Opus 6" "오퍼스 6" --dry   # 미리보기만
    python3 shared/apply_models.py sonnet claude-sonnet-6                          # 표시명 생략 = ID만 교체

절차: 이 명령 → `git diff` 확인 → `python3 shared/check_refs.py`(rc=0) → 커밋.
치환 범위·제외 = models.json `scan`(원장·보고서·백업·캐릭터 데이터 제외 · CLAUDE.md도 제외 = 마커 전파 구간).

표시명 치환 가드: `Opus 5인`·`Opus 5명`(인원 표기)은 건드리지 않는다((?![인명]) 부정형 전방탐색).
                 인원은 항상 '명'으로 써라 — '인'은 모델명과 붙어 읽혀 혼동을 만든다.
"""

import os
import re
import sys
import json
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'shared', 'models.json')
# 표시명 뒤 인원 접미사 = 오탐(모델명 아님) — 치환·게이트 공통 가드(check_refs.check_model_ids와 동일 규약)
NAME_GUARD = r'(?![인명])'


def load():
    with open(REG, encoding='utf-8') as f:
        return json.load(f)


def scan_files(reg):
    """models.json scan.include - scan.exclude 를 해석해 대상 파일 절대경로 목록을 준다."""
    inc, exc = reg['scan']['include'], reg['scan']['exclude']
    drop = set()
    for g in exc:
        drop |= {os.path.abspath(p) for p in glob.glob(os.path.join(ROOT, g), recursive=True)}
    out = []
    for g in inc:
        for p in glob.glob(os.path.join(ROOT, g), recursive=True):
            ap = os.path.abspath(p)
            if not os.path.isfile(ap) or ap in drop:
                continue
            # 제외 글롭이 디렉터리를 가리킨 경우(_versions/** 등)도 접두사로 차단
            if any(ap.startswith(d + os.sep) for d in drop):
                continue
            out.append(ap)
    return sorted(set(out))


def name_variants(en):
    """표시명 대소문자 변형 3종 — 산문에서 `Opus 5`·`opus 5`·`OPUS 5`가 섞여 쓰인다(실측)."""
    head, _, tail = en.partition(' ')
    return [en, '%s %s' % (head.lower(), tail), '%s %s' % (head.upper(), tail)]


def build_pairs(old, new):
    """(정규식, 새 문자열) 목록 — ID는 그대로, 표시명은 인원 접미사 가드."""
    pairs = [(re.compile(re.escape(old['id'])), new['id'])]
    for key in ('en', 'ko'):
        o, n = old.get(key), new.get(key)
        if not o or not n or o == n:
            continue
        if key == 'en':
            for ov, nv in zip(name_variants(o), name_variants(n)):
                pairs.append((re.compile(re.escape(ov) + NAME_GUARD), nv))
        else:
            pairs.append((re.compile(re.escape(o) + NAME_GUARD), n))
    return pairs


def _apply_vendor(reg, key, new_id, dry):
    """벤더(비-Claude 종량제) 교체 — ID 1종만 치환. 표시명·은퇴 등재 없음(공급사 ID는 회수되면 문서 잔존도 오해를 부른다)."""
    v = reg['vendors'][key]
    old_id = v['id']
    if old_id == new_id:
        print('변경 없음 — 벤더[%s] 정본이 이미 %s' % (key, old_id))
        return 0
    rx = re.compile(re.escape(old_id))
    print('벤더 교체: [%s] %s → %s%s' % (key, old_id, new_id, '  (--dry = 미리보기)' if dry else ''))
    files = hits = 0
    for path in scan_files(reg):
        try:
            src = open(path, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        out, n = rx.subn(new_id, src)
        if n:
            files += 1
            hits += n
            print('   %-58s %d곳' % (os.path.relpath(path, ROOT), n))
            if not dry:
                open(path, 'w', encoding='utf-8').write(out)
    if dry:
        print('— 미리보기 끝: %d파일 %d곳(파일 미변경 · 정본 미갱신).' % (files, hits))
        return 0
    reg['vendors'][key] = dict(v, id=new_id)
    with open(REG, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('✅ %d파일 %d곳 치환 + 정본 갱신. 다음: git diff → python3 shared/check_refs.py (rc=0) → 커밋' % (files, hits))
    print('   ⚠️ 종량제 축 = 새 ID가 실제 서빙되는지 실호출 1회로 확인해라(모델 부재 = 런타임 실패).')
    return 0


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    tier, new_id = argv[1], argv[2]
    rest = [a for a in argv[3:] if not a.startswith('--')]
    dry = '--dry' in argv
    reg = load()
    vend = reg.get('vendors', {})
    if tier not in reg['tiers'] and tier not in vend:
        print('❌ 모르는 키: %s — 티어 = %s · 벤더 = %s' % (tier, ', '.join(reg['tiers']), ', '.join(vend) or '없음'))
        return 2
    if tier in vend:   # 벤더(비-Claude 종량제) = 표시명 없이 ID만 · 은퇴 등재도 안 한다(공급사가 구 ID를 회수해 문서 잔존도 위험)
        return _apply_vendor(reg, tier, new_id, dry)
    old = dict(reg['tiers'][tier])
    new = dict(old, id=new_id)
    if rest:
        new['en'] = rest[0]
    if len(rest) > 1:
        new['ko'] = rest[1]
    if old['id'] == new['id'] and old.get('en') == new.get('en') and old.get('ko') == new.get('ko'):
        print('변경 없음 — 정본이 이미 %s(%s / %s)' % (old['id'], old.get('en'), old.get('ko')))
        return 0

    pairs = build_pairs(old, new)
    print('승격: [%s] %s → %s  ·  표시명 %s → %s / %s → %s%s'
          % (tier, old['id'], new['id'], old.get('en'), new.get('en'), old.get('ko'), new.get('ko'),
             '  (--dry = 미리보기)' if dry else ''))
    total_files = total_hits = 0
    for path in scan_files(reg):
        try:
            src = open(path, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        out, hits = src, 0
        for rx, repl in pairs:
            out, n = rx.subn(repl, out)
            hits += n
        if hits:
            total_files += 1
            total_hits += hits
            print('   %-58s %d곳' % (os.path.relpath(path, ROOT), hits))
            if not dry:
                open(path, 'w', encoding='utf-8').write(out)
    if dry:
        print('— 미리보기 끝: %d파일 %d곳(파일 미변경 · 정본 미갱신).' % (total_files, total_hits))
        return 0

    # 정본 갱신 + 구세대 은퇴 등재(게이트가 이 목록으로 '빠뜨림'을 잡는다)
    reg['tiers'][tier] = new
    retired = list(reg.get('retired', []))
    for v in [old['id']] + (name_variants(old['en']) if old.get('en') else []) + ([old['ko']] if old.get('ko') else []):
        if v and v not in retired:
            retired.append(v)
    reg['retired'] = retired
    with open(REG, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print('✅ %d파일 %d곳 치환 + 정본 갱신(구세대 %d종 은퇴 등재).' % (total_files, total_hits, len(retired)))
    print('   다음: git diff 확인 → python3 shared/check_refs.py (rc=0) → 커밋')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
