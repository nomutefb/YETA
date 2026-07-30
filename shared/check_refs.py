#!/usr/bin/env python3
"""노뮤트 플랫폼 — 참조·버전 정합 점검 (수정 모드 ③ 커밋 전 실행).

v1.15.2류 사본 드리프트(파일 rename 후 참조 미갱신·파일명↔내부 버전 불일치)를
사람 눈 대신 기계로 잡는다. 통과 = exit 0 / 실패 = exit 1 + 목록.

검사 2종:
  1) 경로 참조 실존 — md 문서(라우터·SKILL·앱 지침·메모리·README)의 백틱 참조 중
     레포 경로 꼴(`apps/...`·`shared/...`·`.claude/...`·`_산출/...` + 확장자,
     또는 앱 문서 안의 `NN_*.md` 상대 참조)이 실제로 존재하는지.
     (글롭 `*`·플레이스홀더 `{}`·`<>`·공백 포함 표기는 검사 제외 = 오탐 방지.)
  2) 파일명↔내부 버전 일치 — apps/ 의 `*_v<버전>.md` 파일명 버전 토큰이
     1행 헤더의 버전 토큰과 정확히 같은지 (예: 00_지침_v2.5.md ↔ "... v2.5").

사용: python3 shared/check_refs.py   (레포 어디서 실행해도 됨)
"""

import hashlib
import os
import re
import sys
import glob
import json
import shutil
import subprocess
import tempfile
from pathlib import Path   # 얼빡 배경 게이트 — build_season_media.is_face/img_size가 Path를 받는다

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 훅 자동 활성화(260725) — clone·기기마다 `git config core.hooksPath .githooks`를 손으로 치는 걸
# 잊으면 게이트가 "조용히 미실행"되고 통과한 줄 착각한다. 실행기가 스스로 켠다(최초 1회).
if os.path.isdir(os.path.join(ROOT, '.githooks')):
    try:
        import subprocess as _sp
        if not _sp.run(['git', 'config', 'core.hooksPath'], cwd=ROOT,
                       capture_output=True, text=True).stdout.strip():
            _sp.run(['git', 'config', 'core.hooksPath', '.githooks'], cwd=ROOT, capture_output=True)
            print('🔧 core.hooksPath=.githooks 자동 설정(최초 1회 · pre-commit 게이트 활성화)')
    except Exception:
        pass


# 검사 대상 md (백업 폴더 _versions 제외)
SCAN_GLOBS = ('*.md', 'apps/**/*.md', '.claude/skills/**/*.md')
# 루트 기준 경로 참조로 보는 접두사 + 확장자
PATH_PREFIX = re.compile(r'^(?:apps|shared|\.claude|_산출)/')
PATH_EXT = re.compile(r'\.(?:md|py|sh|png)$')
# 앱 문서 내부의 형제 파일 참조 (NN_으로 시작하는 .md — 예: 01_지침_*.md 실명 참조)
SIBLING = re.compile(r'^\d{2}_[^/]+\.md$')
# 백틱 스팬 / 버전 토큰
BACKTICK = re.compile(r'`([^`\n]+)`')
VTOKEN = re.compile(r'v\d+(?:\.\d+)*')
# 검사 제외(플레이스홀더·글롭·예시)
SKIP_CHARS = set('*{}<>… ')


def md_files():
    seen = []
    for g in SCAN_GLOBS:
        for p in glob.glob(os.path.join(ROOT, g), recursive=True):
            if os.path.relpath(p, ROOT).startswith('_versions'):
                continue
            seen.append(p)
    return sorted(set(seen))


def check_paths():
    fails = []
    for md in md_files():
        rel_md = os.path.relpath(md, ROOT)
        if rel_md.startswith('_versions'):
            continue
        try:
            text = open(md, encoding='utf-8').read()
        except OSError:
            continue
        for span in BACKTICK.findall(text):
            cand = span.strip().lstrip('./')
            if not cand or any(c in SKIP_CHARS for c in cand):
                continue
            if PATH_PREFIX.match(cand) and PATH_EXT.search(cand):
                if not os.path.exists(os.path.join(ROOT, cand)):
                    fails.append('%s → `%s` 없음 (루트 기준)' % (rel_md, cand))
            elif SIBLING.match(cand):
                if not os.path.exists(os.path.join(os.path.dirname(md), cand)):
                    fails.append('%s → `%s` 없음 (같은 폴더 기준)' % (rel_md, cand))
    return fails


def check_versions():
    fails = []
    for p in glob.glob(os.path.join(ROOT, 'apps', '**', '*_v*.md'), recursive=True):
        rel = os.path.relpath(p, ROOT)
        name_tok = VTOKEN.findall(os.path.basename(p))
        if not name_tok:
            continue
        try:
            head = open(p, encoding='utf-8').readline()
        except OSError:
            continue
        head_toks = VTOKEN.findall(head)
        if name_tok[-1] not in head_toks:
            fails.append('%s → 파일명 %s ≠ 1행 헤더 %s' %
                         (rel, name_tok[-1], (head_toks or ['버전 없음'])))
    return fails


# ── 디자인시스템 토큰 게이트 (분신술 D5 · 260620) ──────────────────────────────
# 값 SSOT = viewer/index.html :root. 신규/수정 CSS는 raw hex/blur/accent-rgba 대신 var() 토큰을 써야 한다(§🎨).
# WARN-only(커밋 차단 안 함) = 점진 강제: 기존은 봐주되 raw가 *늘면* 커밋 전(수정 모드 ③)에 눈에 띈다.
# raw를 토큰으로 줄였으면 baseline도 그만큼 낮춰 재발 방지(드리프트는 늘 때만 잡힘).
# baseline = `:root` SSOT 블록 제외한 현재 raw 카운트(=드리프트는 *늘 때만* 잡힘). 260620 실측.
_DESIGN_BASELINE = {
    'viewer/index.html': {'accent_raw': 0, 'blur': 127, 'hex': 173, 'accent_hex': 0},   # blur129→127 = 메인 PIN 모드 풀스크린 backdrop blur(var(--blur-m))+webkit 2개 제거(운영자 260705 "PIN이 이미지 안 덮게" → 풀블러 딤 폐지·하단 그라데 스크림만 · §🎨 "raw 줄이면 baseline도 낮춰"). // 260704 브랜드 라임 전환: accent 패턴 #0FFD02→#CFFF40·baseline 97/32→0(옛 그린 raw 완전 제거·새 브랜드는 처음부터 var() 강제). // hex163→173 = 발행본(SUMMARY_TPL 자기완결 HTML) 검색 헤더(제목검색·K검색·한/영)·키워드 칩·이미지별 저장·영문 제목 신설 → CSP가 외부 CSS 차단이라 var() 불가 = 순수 raw hex 필수(§🎨 self-contained 예외·accent는 #0FFD02 hex만·rgba(15,253,2) 순증 0·운영자 요청 260703). // accent_raw 109→97 = 하단바(.bnav/.bnav-fab/활성 인디케이터)·탑버튼(.totop) 무채색화로 초록 raw 12개 제거(§🎨 "raw 줄이면 baseline도 낮춰"·260703). hex176→163 = 마퀴펫 v2 롤백(운영자 260703 — 원본 pet.webp가 50프레임 '공 드리블+헤딩' 애니였음·재인코딩이 애니를 죽인 실사고) → 스티커 테두리 #000×12+공 테두리 #000×1 제거 = §🎨 ratchet 복원. // hex163→175 = 마퀴 펫 글자 스티커 테두리(12방향 text-shadow 링 #000 ×12 — 순수 흑 의도적 raw·§🎨 아웃라인 원칙 '순수 흑/백만'·토큰 부재·260703). // blur128→129 = 마퀴 펫 v2 간판(.pm-sign) 글래스 backdrop var(--blur-s)+webkit +2 − 옛 산책 펫 CSS 정리 −1 = 순증 +1(토큰·raw 아님·260703). // hex 160→163 = 선존 드리프트 실측 reconcile(yeta v2·v3 페르소나/버블 hex — 발행본 픽토그램·ic-share 작업은 var() 토큰만이라 순증 0 · 주석 PR번호 '#NNNN'은 4자리 hex 오탐이라 'PR NNNN' 표기·260703). // hex 158→160 = 선존 드리프트 실측 reconcile(origin/main 이미 160 = 이전 세션이 hex +2 하고 baseline 미상향 · 발행본 어포던스는 rgba(255,255,255,…)라 hex 카운트 무관·260703). // hex 161→158 = #ff5b4a→var(--danger)(348) 토큰화分 + 선존 slack 실측까지 ratchet(§🎨 "raw 줄이면 baseline 낮춰"·260630). // STAGE1 조임(분신술10·260628): accent 122→109·hex 167→161 = 헐렁 baseline 실측까지(raw 되살아나는 구멍 차단). //   # blur126→128 = 뉴스요약 사진첨부(.askattach) 글래스 backdrop var(--blur-s) +2(토큰·raw 아님·혼자 flat이라 '따로놀던' 것 형제 .iobtn/.sbtn과 통일·운영자 260628) // accent_raw 105→123 요약본 스포티파이→노뮤트 / mkbtn 글래스 +1 / blur90→92 요약본 제목복사 글래스 / 92→90 #editdlg backdrop 제거(main 260621) / +2 요약헤더 .dlbox 글래스 알약 var(--blur-m)(260621) / 124→122 대기열 .qgo·.qb-succ accent rgba→var(--accent-rgb) 토큰화(260622) / blur 92→100 = 당겨서새로고침 #ptr 글래스 var(--blur-s) +2(토큰·raw 아님) + 기존 누적분 흡수(260623) / 100→102 = 수정중 .rev-hint 글래스 var(--blur-s) 복원(260623) / 102→104 = 뉴스요약 .askclip 하단걸침 2A 글래스 var(--blur-s) +2(토큰·복붙버튼 일괄통일·260625) / blur 104→106 = 수집함 병합박스(.mergebox) 글래스 backdrop var(--blur-m) +2(토큰·raw 아님·병합기능·260625) / blur 106→110·hex 168→167 = 병합 바 중립칩 재설계(초록알약 1표면→글래스 칩+별도 X+기준칩 3표면 var(--blur-s)·토큰·raw 아님) + #0c0c0c 제거(빈 mb-n display:none)(260625) / blur 110→112 = 병합 해제 확인 팝오버(.unmerge-go) 글래스 backdrop var(--blur-s) +2(토큰·raw 아님·260626) / blur 112→114 = 라디얼 제작메뉴 자막생성 도구 탭(.tooltab) 글래스 backdrop var(--blur-m) +2(토큰·raw 아님·thumb .tab 계승·260626) / blur 114→116 = 수정/요약 전송버튼(.asksend) 글래스 통일 backdrop var(--blur-s) +2(토큰·raw 아님·.mkbtn 정본 계승·머지시 main 114 기준 +2·260627) / blur 116→120 = 입력칸 복사/붙여넣기/지우개·되돌리기(.iobtn·.iobtn-edge) 이미지 제작 attachCopyPaste 이식 backdrop var(--blur-s)·var(--blur-m) +4(토큰·raw 아님·#revText·#crevText·260627) / blur 120→122 = 뉴스요약 최소화 선택 picker(.min-pick) 글래스 backdrop var(--blur-l) +2(토큰·raw 아님·260627) / blur 122→124 = main 실측 124 lag 흡수(선존 +2) · 필터 오버레이(.filterpop) token var(--blur-l) +2 와 옛 토글(.tk) raw 8px −2 상쇄 = 순증 0(raw→token 교체·옛 카테고리 칩바→필터 버튼 오버레이·260628) / blur124→126 = 붙여넣기 폴백 모달(.pastefb::backdrop) var(--blur-s) +2(토큰·raw 아님·통일 기틀·260628) // accent_hex 32 = 요약본 SUMMARY_TPL 독립문서(viewer :root 없음→var() 불가·의도적 raw)+JS 상수 — hex 표기 우회 봉합·늘면 차단(260703 재실측·발행본 검색헤더 반영).
    'viewer/thumb.html': {'accent_raw': 0, 'blur': 43, 'hex': 34, 'accent_hex': 0},   # STAGE1: hex 35→34 실측조임.   # blur39→41 = 빠른메뉴 코어 위 '-' 최소화(#rfab .rmin) 글래스 backdrop blur+webkit = 형제 .rc 코어 외형 계승(blur14 saturate1.3·thumb엔 blur토큰 없어 raw·창 최소화 엄지존·260627). accent rgba 토큰화 완료(--accent-rgb·260621). blur41→43 = 이미지 슬롯(.covimg) 글래스모피즘 backdrop blur+webkit(플레이트 색 제거·픽토 accent 50% · thumb엔 blur토큰 없어 raw·260626). blur43→39 = .covimg 글래스 제거(전경 완전 제거→픽토만·−2) + 상단 3탭 글자화(.tab 글래스 제거·−2)(운영자 260626). blur/hex는 thumb 독자팔레트라 잔존(후속). hex…→28 = .go.err 미입력 빨강(#ff7a7a·#ff5d5d) · hex28→27 = 흰 체크 #fff 제거. hex29→30 = 개별 변형 다운로드(.jvar-dl.dlbtn) 도형제거·픽토그램 흰색 #fff = 좌측 라벨(.jvar #fff)과 색 일치 목적(--fg #e9eaec≠#fff라 토큰화 불가·의도적 raw·260626). hex27→29 = 썸네일 통합 오버레이 포맷색(.ovfmt.post 시안 #1fd6ee · .ovfmt.reels 레몬 #e7ff2e · 후속 토큰화·260624). hex31→29 = /3 저작권 단일토글 전환으로 중복 .cpfmt 시안/레몬 hex 2개 제거(.ovfmt 계승=중복 회수 · §🎨 "raw 줄이면 baseline도 낮춰라" · 분신술7·8·260625). blur32→34 = 저작권 복사칩(.cref-kw 글래스) · blur34→36 = 축약 체크 = 수집함 확인토글(.sc-tg.ack) 글래스 박스 계승(backdrop blur·−→✓ 모프·accent는 var(--accent-rgb) 토큰·260622). blur36→38 = #rfab .rc 빠른메뉴 코어를 수정 연필 FAB(.rev-fab) 글래스 외형 계승(backdrop blur+webkit·thumb엔 blur토큰 없어 raw·260622). blur38→40 = 통합모드 OPA 롤러(260624) → blur40→38 = OPA 롤러 제거·섹션 헤더 인라인 조절 전환(글래스 팝업 폐지·blur 2개 감소·260624). blur38→39 = 축약어 등록 다이얼로그(.abdlg) cfm 글래스 계승(thumb엔 blur토큰 없어 raw·260624). blur39→41 = .iobtn-edge G1 글래스모피즘 backdrop blur13+saturate(복붙버튼 통일·thumb엔 blur토큰 없어 raw·260625). blur41→43·hex30→35 = 붙여넣기 폴백 모달(.pastefb dialog) 신설 — backdrop blur(4px) webkit+표준 +2(thumb엔 blur토큰 없어 raw) + 박스 배경 그라데이션·메시지/입력/버튼 색(#14160f·#0c0f0c·#cfd2d7·#e8eaed = 기존 모달 배경·보조텍스트 패턴 복제·적합 토큰 부재) +5(통일 기틀·readText 막힌 환경 폴백·운영자 260628).
    # ▼ 도구 3파일 게이트 편입(분신술 9·10 P0 — 옛 사각지대: 닫기/최소화 버그가 난 파일군이 무방비였음). accent_raw=0 = ly/k 토큰화 완료(--accent-rgb·260628), 늘면 즉시 잡힘. comp 7은 후속 토큰화 대상.
    'viewer/ly.html': {'accent_raw': 0, 'blur': 14, 'hex': 16, 'accent_hex': 0},   # blur12→14·hex14→16 = 붙여넣기 폴백 모달(.pastefb) 신설 — backdrop blur(4px) webkit+표준 +2(ly엔 blur토큰 없어 raw) + 박스 배경 그라데이션 #14160f·#0c0f0c +2(기존 모달 배경 패턴·통일 기틀·운영자 260628)
    'viewer/k.html': {'accent_raw': 0, 'blur': 12, 'hex': 7, 'accent_hex': 0},
    'viewer/comp.html': {'accent_raw': 0, 'blur': 2, 'hex': 5, 'accent_hex': 0},   # STAGE1: --accent-rgb 추가·raw 7곳 토큰화 → accent_raw 7→0(픽셀0·k/ly 패턴·260628).
}
_ROOT_BLOCK = re.compile(r':root\s*\{.*?\}', re.S)

# viewer :root 정의 토큰 중 var() 한 번도 안 쓰는 것 = 죽은 토큰 후보. 단 디자인시스템 어휘는
# 점진 이관(기존 raw→토큰) 중이라 '미리 선언·아직 미배선'이 의도된 게 다수(§🎨). → 현 미배선
# 집합을 baseline 으로 고정하고 그 *밖*의 새 미배선만 경고(드리프트는 늘 때만 = 새 죽은토큰 차단). 260621.
_FWD_UNUSED = {
    '--accent-2', '--amber-rgb', '--blur-backdrop', '--blur-l', '--blur-m', '--blur-s',
    '--blur-xl', '--btn', '--btn-xs', '--danger-rgb', '--dur-fast', '--ease', '--fg-2',
    '--fs-body', '--fs-display', '--fs-h1', '--fs-h2', '--fs-h3', '--fs-label', '--fs-xs',
    '--fw-b', '--fw-x', '--lh-base', '--on-arm', '--r-l', '--r-m', '--r-pill', '--sp-1', '--sp-2',
    '--sp-3', '--sp-4', '--warn',
    '--press-pico',   # 픽토온리 눌림 = thumb/ly/k의 rmin/file가 씀(index엔 .55 픽토 버튼 없음) = forward-declared(260628)
    '--arm',   # 2탭 재확인 경고색 = viewer/call.js #yetaCallBtn.armed가 씀(스캐너는 index만 봄 · "새 대화" 제거로 index 내 사용 0 · 260705)
}   # (main #4 --brand/--brand-rgb 는 이 브랜치 v2에서 --accent:#CFFF40 로 통일·배선 → 중복 제거·260704 머지)
# --on-arm(arm 채움 위 글자색) = .revsend.confirm 채움 그라데 → 표준 플랫 arm 전환(260622)으로 현재 미배선.
# 정의는 보존(--arm/--arm-rgb 짝 · 향후 채움형 arm 컴포넌트용 어휘) → forward-unused 처리(§🎨).

def _new_dead_tokens(rel='viewer/index.html'):
    """viewer :root 정의 토큰 중 var() 미사용 & baseline 밖 = 새 죽은 토큰(접두사 오탐 가드)."""
    try:
        s = open(os.path.join(ROOT, rel), encoding='utf-8').read()
    except Exception:
        return []
    m = _ROOT_BLOCK.search(s)
    if not m:
        return []
    names = set(re.findall(r'(--[a-z0-9-]+)\s*:', m.group(0)))
    body = _ROOT_BLOCK.sub('', s, count=1)   # :root 정의부 제외 = 실사용만
    return [n for n in sorted(names)
            if n not in _FWD_UNUSED
            and not re.search(r'var\(\s*' + re.escape(n) + r'(?![\w-])', body)]

# ── viewer 인라인 JS 구문 게이트 (분신술 V2/V4 · 260620) ──────────────────────────
# 머지 가산·복붙 중복 등으로 viewer 인라인 <script>에 SyntaxError(예: let 재선언)가 들어가면
# 브라우저가 스크립트 전체를 평가 안 함 = 뷰어 전면 사망. node로 *구문만* 검사해 커밋 전 차단(하드 게이트).
# node 없으면 스킵(로컬·CI 환경차 흡수).
_SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S)

def check_viewer_js():
    node = shutil.which('node')
    if not node:
        print('⚠️ viewer JS 구문검사 스킵(node 없음)'); return 0
    rc = 0
    for rel in ('viewer/index.html', 'viewer/thumb.html', 'viewer/ly.html', 'viewer/k.html'):
        try:
            html = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        js = '\n;\n'.join(_SCRIPT_RE.findall(html))
        if not js.strip():
            continue
        tmp = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
                f.write(js); tmp = f.name
            r = subprocess.run([node, '--check', tmp], capture_output=True, text=True, timeout=30)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        if r.returncode != 0:
            errs = [x for x in (r.stderr or '').splitlines() if 'Error' in x]
            print('❌ viewer JS 구문 오류 — %s: %s' % (rel, errs[0] if errs else 'syntax error'))
            rc = 1
        else:
            print('✅ viewer JS 구문 OK — %s' % rel)
    return rc

_ICON_DECL_RE = re.compile(r'^const ([A-Z0-9_]+_SVG) = ', re.M)
def check_icon_ssot():
    """공유 아이콘 SSOT 하드 게이트(운영자 260628 '하나 바꾸면 다 바뀜').
    nm-svg.js가 정의한 공유 아이콘을 뷰어가 다시 인라인 const로 선언하면(=섀도잉·드리프트 부활) rc=1.
    각 뷰어가 공유 아이콘을 *쓰면서* nm-svg.js를 로드 안 하면(런타임 ReferenceError) rc=1."""
    nm = os.path.join(ROOT, 'viewer/nm-svg.js')
    if not os.path.exists(nm):
        print('⚠️ nm-svg.js 없음 — 아이콘 SSOT 게이트 스킵'); return 0
    shared = set(_ICON_DECL_RE.findall(open(nm, encoding='utf-8').read()))
    if not shared:
        print('⚠️ nm-svg.js에 공유 상수 0 — 게이트 스킵'); return 0
    rc = 0
    for rel in ('viewer/index.html', 'viewer/thumb.html', 'viewer/ly.html', 'viewer/k.html'):
        try:
            html = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        loads = 'nm-svg.js' in html
        inlined = set(_ICON_DECL_RE.findall(html)) & shared
        if inlined:
            print('❌ 아이콘 SSOT 위반 — %s가 공유 아이콘을 인라인 재선언(섀도잉): %s → nm-svg.js만 두고 제거'
                  % (rel, ', '.join(sorted(inlined)))); rc = 1
        used = {c for c in shared if (c in html) and not loads}
        if used and not loads:
            print('❌ 아이콘 SSOT 위반 — %s가 공유 아이콘(%s)을 쓰는데 nm-svg.js 미로드 → <script src="nm-svg.js"> 추가'
                  % (rel, ', '.join(sorted(used))[:60])); rc = 1
    if rc == 0:
        print('✅ 아이콘 SSOT 정합 — 공유 아이콘 %d개 단일정본(nm-svg.js)·인라인 재선언 0' % len(shared))
    return rc

def check_design():
    # accent_raw = 차단(rc=1) 승격(운영자 ③b·STAGE1·260628). 단일 정확패턴 `rgba(15,253,2`라 오탐 0,
    #   index 빼고 전부 0(thumb/ly/k/comp) → 새 raw 강조색 박기 구조적 차단. 봇 무영향(check-refs.yml=PR전용·봇은 데이터JSON만 직푸시·A7 실측).
    # hex/blur/죽은토큰 = WARN 유지(의도적 raw·토큰글래스 +2 누적이라 차단하면 정당작업 막힘).
    warns, hard = [], []
    for rel, base in _DESIGN_BASELINE.items():
        try:
            s = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        s = _ROOT_BLOCK.sub('', s, count=1)   # :root = 토큰 SSOT 정의 자리 → 카운트 제외(D5 화이트리스트)
        cnt = {'accent_raw': s.count('rgba(207,255,64'), 'blur': s.count('blur('),
               'hex': len(re.findall(r'#[0-9a-fA-F]{3,8}\b', s)),
               'accent_hex': s.lower().count('#cfff40')}   # 강조색 hex 표기 우회 봉합(rgba만 세던 구멍) · 260704 브랜드 라임 #CFFF40로 전환(옛 #0FFD02 폐지)
        for k, b in base.items():
            if cnt[k] > b:
                msg = '%s: raw %s %d > baseline %d → var() 토큰으로(§🎨)' % (rel, k, cnt[k], b)
                (hard if k in ('accent_raw', 'accent_hex') else warns).append(msg)
    for n in _new_dead_tokens():   # 새로 추가됐는데 var() 미배선인 토큰(죽은 토큰) — 배선하거나 정의 삭제
        warns.append('viewer/index.html: 토큰 %s 정의됐으나 var() 미사용 → 배선하거나 정의 삭제(§🎨)' % n)
    if hard:
        print('❌ 디자인 토큰 게이트(차단) — raw 강조색(rgba(207,255,64)·#CFFF40) 증가 = var(--accent)/var(--accent-rgb) 토큰으로(의도적 raw는 baseline 사유 기록 후 조정):')
        for w in hard:
            print('  -', w)
    if warns:
        print('⚠️ 디자인 토큰 게이트(비차단): raw 값 증가 감지 —')
        for w in warns:
            print('  -', w)
    if not hard and not warns:
        print('✅ 디자인 토큰 게이트 — raw 값 baseline 이내(신규 미토큰 없음).')
    return 1 if hard else 0   # accent_raw·accent_hex만 차단, hex/blur/죽은토큰은 WARN


def check_backstack_contract():
    """인앱 뒤로가기(백스택) 골격 계약 — popstate 분기가 조용히 사라지면 rc=1.

    왜(260726 사고): 262차가 종료 확인 팝업을 폐지하며 "홈에서 뒤로 1회 = 앱 밖"을 계약으로
    내걸었는데, 검증이 '팝업 0'만 보고 **몇 번 눌러야 나가는지를 안 셌다**. 실제론 2회였고
    (연쇄 감기의 착지 칸에서 멈춤) 뒤로 1회가 통째로 씹혔다 — 267차에서야 실측으로 잡혔다.
    popstate는 한 함수 안에 분기가 겹겹이라 한 줄만 지워도 증상이 '조용히' 돌아온다.

    여기서 보는 것(가볍게 · 매 커밋): popstate 리스너 안에 세 계약이 살아 있나.
      ① 레이어 회수 우선(_navPopClose)  ② 고아 칸 감기(history.state → back)
      ③ 감기 착지에서 이탈(back 호출이 2회 이상 = 감기 + 착지)
    실동작 증명은 `node tests/test_backstack.js`(실브라우저 8계약 · ~1.5분)가 한다 —
    무거워서 매 커밋엔 안 붙인다. 이 게이트가 걸리면 그 하니스로 실증해라."""
    rel = 'viewer/index.html'
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        print('⚠️ viewer/index.html 없음 — 백스택 계약 게이트 스킵'); return 0
    src = open(p, encoding='utf-8').read()
    i = src.find("addEventListener('popstate'")
    if i < 0:
        print('❌ 백스택 계약 — popstate 리스너를 못 찾았다(%s).' % rel)
        print('   처방 = node tests/test_backstack.js --report 로 실동작부터 확인해라.')
        return 1
    j = src.find('\n});', i)
    body = src[i:j if j > 0 else i + 2000]
    miss = []
    if '_navPopClose' not in body:
        miss.append('① 레이어 회수(_navPopClose) — 뒤로가 최상단 레이어를 안 닫고 앱을 나간다')
    if 'history.state' not in body:
        miss.append('② 고아 칸 감기(history.state 검사) — navHome이 남긴 칸에서 뒤로가 씹힌다')
    if len(re.findall(r'history\.back\s*\(', body)) < 2:
        miss.append('③ 감기 착지 이탈(back 2회째) — 267차 이전으로 회귀 = 홈에서 뒤로 1회가 통째로 씹힌다')
    # ④ 폐지분 부활 감시 — ⚠ `.yexit*` **CSS 클래스는 살아 있는 정본**이다(#yconfirm·#ymedead·#ymdquiz가
    #    계승하는 확인 팝업 골격 · 262차 CSS 무접촉). 되살아나면 안 되는 건 DOM id와 함수뿐이라 그것만 본다.
    revived = re.findall(r'id\s*=\s*["\']yexit["\']|getElementById\(\s*["\']yexit["\']\s*\)|yExit(?:Ask|Yes|Close)\s*\(', src)
    if revived:
        miss.append('④ 폐지된 종료 확인 팝업 부활(%s) — 262차 운영자 승인 폐지분(.yexit* CSS 골격은 정상)'
                    % ', '.join(sorted(set(revived))[:3]))
    if miss:
        print('❌ 백스택 계약 게이트 — popstate 골격에서 사라진 분기:')
        for m in miss:
            print('  -', m)
        print('   실증 = node tests/test_backstack.js --report (실브라우저 8계약)')
        print('   의도된 리팩터라면: 하니스를 먼저 통과시키고 이 게이트의 기대를 갱신해라(사유 기록).')
        return 1
    print('✅ 백스택 계약 게이트 — popstate 3분기 생존(레이어 회수·고아 칸 감기·착지 이탈) · 실증 = tests/test_backstack.js')
    return 0


def check_token_lock():
    """절대명령#1 기계강제 — design-tokens.lock(승인 원장)에 없는 :root 신규 토큰 = 커밋 차단(rc=1).
    승인 = 락 등재(PR diff 리뷰). '승인 없이 조용히 :root 토큰 추가'를 기계가 봉쇄 = §🔒 진짜 강제 지렛대.
    (자기참조 완화: 추가는 반드시 락에 명시적 등재 = PR에서 운영자가 그 한 줄을 봄.)"""
    lock_path = os.path.join(ROOT, 'design-tokens.lock')
    if not os.path.exists(lock_path):
        print('⚠️ 토큰 락 스킵 — design-tokens.lock 없음')
        return 0
    try:
        import build_design_mirror
        root = build_design_mirror.extract_root()
    except Exception as e:
        print('⚠️ 토큰 락 스킵 —', e)
        return 0
    root = re.sub(r'/\*.*?\*/', '', root, flags=re.S)   # :root 주석 제거(오탐 가드)
    cur = set(re.findall(r'(--[A-Za-z0-9-]+)\s*:', root))
    lock = set(re.findall(r'^\s*(--[A-Za-z0-9-]+)\b', open(lock_path, encoding='utf-8').read(), re.M))
    new, gone = sorted(cur - lock), sorted(lock - cur)
    if new:
        print('❌ 토큰 락 게이트(차단·절대명령#1) — 미승인 신규 :root 토큰:')
        for n in new:
            print('  -', n, '→ 운영자 승인 후 design-tokens.lock 등재(임의 추가 금지)')
        return 1
    if gone:
        print('⚠️ 토큰 락 — 락 등재됐으나 :root 부재(삭제됨 → 락 정리 권장):', ' '.join(gone))
    print('✅ 토큰 락 게이트 — :root 토큰 %d개 전원 승인 등재(미승인 신규 0)' % len(cur))
    return 0

# 주입 지침 소스에 '----- ... -----' 형태 본문 줄 금지 (R6 가드 · 260624).
# inject_guidelines.sh 의 guidelines_version() 은 해시 입력에서 경로헤더('^----- path -----$')를 제외해
#   파일 rename 에도 같은 버전을 내(불필요 재생성 방지). 그런데 *주입 지침 본문*에 같은 형태의 줄이 있으면
#   그 줄도 해시에서 빠져 → 그 줄만 편집해도 버전이 안 바뀜 = 조용한 드리프트(이 시스템이 막으려는 바로 그것).
#   현재 0건. 이 게이트로 미래에 그런 줄이 들어오는 걸 차단(분신술 8인 권고 260624).
_DIVIDER_RE = re.compile(r'^----- .+ -----\s*$')
_INJECT_GLOBS = ('apps/yeta/00_지침_캐릭터챗.md', 'apps/yeta/10_세계관.md')


def check_inject_dividers():
    fails = []
    for g in _INJECT_GLOBS:
        for path in glob.glob(os.path.join(ROOT, g)):
            try:
                with open(path, encoding='utf-8') as fh:
                    for n, line in enumerate(fh, 1):
                        if _DIVIDER_RE.match(line):
                            rel = os.path.relpath(path, ROOT)
                            fails.append("주입 지침 본문에 '----- ... -----' 줄(%s:%d) — R6 해시서 제외돼 드리프트 미탐 위험. 다른 표기로 바꿔라." % (rel, n))
            except Exception:
                continue
    return fails


def check_inject_markers():
    """주입 지침 파일의 <!-- INJECT-SKIP-START/END --> 마커 짝 균형(260624 단일화 가드).
    START 가 END 없이 열리면 awk 가 EOF까지 통째로 주입에서 누락 = 조용한 드리프트(이 시스템이 막는 것).
    파일별 START 수 == END 수 가 아니면 실패."""
    fails = []
    for g in _INJECT_GLOBS:
        for path in glob.glob(os.path.join(ROOT, g)):
            try:
                txt = open(path, encoding='utf-8').read()
            except Exception:
                continue
            s, e = txt.count('INJECT-SKIP-START'), txt.count('INJECT-SKIP-END')
            if s != e:
                fails.append("INJECT-SKIP 마커 불균형(%s: START %d ≠ END %d) — 미종결 마커는 그 뒤 주입 내용을 통째 누락시킴." % (os.path.relpath(path, ROOT), s, e))
    return fails


def check_curation_constants():
    """큐레이션 랭킹 상수(viewer) ↔ docs/curation-algorithm.md §★ 정본값 정합 하드게이트.
    #1135식 stale-PR 자기-revert·코드↔문서 드리프트를 CI가 즉시 차단(260628 13인 감사 C8).
    viewer 리터럴(CROSS_POW·FOLLOW_W·BREAKING_RANK_BOOST·GRADE_W grade0 floor)을 §★ 인용값과 대조."""
    rc = 0
    try:
        v = open(os.path.join(ROOT, 'viewer', 'index.html'), encoding='utf-8').read()
        d = open(os.path.join(ROOT, 'docs', 'curation-algorithm.md'), encoding='utf-8').read()
    except Exception as e:
        print('⚠️ check_curation_constants 스킵(파일):', e); return 0
    star = next((ln for ln in d.splitlines() if '누적 랭킹' in ln and 'cross^' in ln), '')
    if not star:
        print('⚠️ check_curation_constants 스킵(§★ 랭킹식 줄 못 찾음)'); return 0
    def vcode(pat):
        m = re.search(pat, v); return m.group(1) if m else None
    def vdoc(pat):
        m = re.search(pat, star); return m.group(1) if m else None
    checks = [
        ('CROSS_POW',           vcode(r'const CROSS_POW\s*=\s*([\d.]+)'),           vdoc(r'cross\^([\d.]+)')),
        ('FOLLOW_W',            vcode(r'const FOLLOW_W\s*=\s*([\d.]+)'),            vdoc(r'FW([\d.]+)')),
        ('BREAKING_RANK_BOOST', vcode(r'const BREAKING_RANK_BOOST\s*=\s*([\d.]+)'), vdoc(r'isBreaking\?([\d.]+)')),
        ('ACC_T_HALF',          vcode(r'const ACC_T_HALF\s*=\s*([\d.]+)'),          vdoc(r'timeAcc\((\d+(?:\.\d+)?)·')),
        ('ACC_T_POW',           vcode(r'ACC_T_POW\s*=\s*([\d.]+)'),                 vdoc(r'timeAcc\([\d.]+·([\d.]+)\)')),
        ('GRADE_W.grade0',      vcode(r'GRADE_W\s*=\s*\{\s*0:\s*([\d.]+)'),         vdoc(r'gradeW\{0:([\d.]+)')),
        ('GRADE_W.grade1',      vcode(r'GRADE_W\s*=\s*\{[^}]*?1:\s*([\d.]+)'),      vdoc(r'gradeW\{[^}]*?1:([\d.]+)')),
        ('GRADE_W.grade2',      vcode(r'GRADE_W\s*=\s*\{[^}]*?2:\s*([\d.]+)'),      vdoc(r'gradeW\{[^}]*?2:([\d.]+)')),
        ('GRADE_W.grade3',      vcode(r'GRADE_W\s*=\s*\{[^}]*?3:\s*([\d.]+)'),      vdoc(r'gradeW\{[^}]*?3:([\d.]+)')),
    ]
    bad = []
    for name, code_v, doc_v in checks:
        if code_v is None or doc_v is None:
            bad.append('%s: 추출실패(code=%s·doc=%s)' % (name, code_v, doc_v)); continue
        if float(code_v) != float(doc_v):
            bad.append('%s: viewer=%s ≠ §★문서=%s (코드↔문서 드리프트/자기-revert 의심)' % (name, code_v, doc_v))
    if bad:
        print('❌ 큐레이션 상수↔문서 정합 실패(C8 게이트):')
        for b in bad: print('  -', b)
        rc = 1
    else:
        print('✅ 큐레이션 상수↔문서 정합 — CROSS_POW·FOLLOW_W·BOOST·ACC_T·GRADE_W 전체 = §★ 일치.')
    return rc


_CATKW_BUCKETS = ('국제', '경제', '문화', '테크', '정치', '사회')


def _parse_cat_kw(text):
    """CAT_KW={...} 블록 → 버킷별 토큰집합 (py 큰따옴표·js 작은따옴표 공용·//·# 주석 제거)."""
    m = re.search(r'CAT_KW\s*=\s*\{(.*?)\n\s*\}\s*;?', text, re.S)
    if not m:
        return None
    body = re.sub(r'//[^\n]*', '', m.group(1))
    body = re.sub(r'#[^\n]*', '', body)
    out = {}
    for b in _CATKW_BUCKETS:
        bm = re.search(r'(?:"%s"|%s)\s*:\s*\[(.*?)\]' % (b, b), body, re.S)
        out[b] = set(re.findall(r"""['"]([^'"]+)['"]""", bm.group(1))) if bm else set()
    return out


def check_cat_kw():
    """CAT_KW 카테고리 키워드사전 py(to_candidates.py) ↔ js(viewer/index.html) 정합 하드게이트.
    수동 미러라 매 세션 드리프트(같은 단어가 두 엔진서 다른/없는 버킷)가 누적 — 분류 오분류 재발의
    근본(260628 C9 분신술 10인). 버킷별 토큰집합 일치 + 버킷충돌(같은 토큰·다른 버킷) 둘 다 검사."""
    rc = 0
    try:
        py = open(os.path.join(ROOT, 'scraper', 'to_candidates.py'), encoding='utf-8').read()
        js = open(os.path.join(ROOT, 'viewer', 'index.html'), encoding='utf-8').read()
    except Exception as e:
        print('⚠️ check_cat_kw 스킵(파일):', e); return 0
    P = _parse_cat_kw(py); J = _parse_cat_kw(js)
    if P is None or J is None:
        print('⚠️ check_cat_kw 스킵(CAT_KW 블록 못 찾음 — py=%s·js=%s)' % (P is not None, J is not None)); return 0
    bad = []
    for b in _CATKW_BUCKETS:
        onlyP, onlyJ = P[b] - J[b], J[b] - P[b]
        if onlyP: bad.append('[%s] py에만: %s' % (b, ', '.join(sorted(onlyP))))
        if onlyJ: bad.append('[%s] js에만: %s' % (b, ', '.join(sorted(onlyJ))))
    pmap, jmap = {}, {}
    for b in _CATKW_BUCKETS:
        for t in P[b]: pmap.setdefault(t, set()).add(b)
        for t in J[b]: jmap.setdefault(t, set()).add(b)
    for t in set(pmap) & set(jmap):
        if pmap[t] != jmap[t]:
            bad.append("버킷충돌 '%s': py=%s js=%s" % (t, sorted(pmap[t]), sorted(jmap[t])))
    if bad:
        print('❌ CAT_KW py↔js 드리프트(C9 게이트 — 키워드 한쪽만 고침=분류 오분류 근본):')
        for b in bad: print('  -', b)
        rc = 1
    else:
        print('✅ CAT_KW py↔js 정합 — 6버킷 토큰집합 일치·버킷충돌 0.')
    return rc


_ISS_REGEX_NAMES = ('BJ_CRASH', 'BJ_MKT', 'BJ_HEAD', 'BJ_PR')

def check_issue_badge_parity():
    """⚡이슈 배지 게이트 viewer(issCross) ↔ build-viewer(issEligible) 규칙 동일 하드게이트(260702 · 10인 검증7).
    배지 규칙이 두 파일에 이중 구현(수집함=렌더타임·피드=빌드타임)이라 한쪽만 고치면 수집함↔피드 배지
    드리프트 — 주석 계약을 기계로 강제(check_cat_kw 선례). 검사: ISS_CROSS_MIN 값 + BJ_* 4종 정규식
    바이트 동일 + grade3 우회(`=== 3`·cross 8) 마커 양쪽 존재."""
    rc = 0
    try:
        js = open(os.path.join(ROOT, 'viewer', 'index.html'), encoding='utf-8').read()
        bv = open(os.path.join(ROOT, 'build-viewer.mjs'), encoding='utf-8').read()
    except Exception as e:
        print('⚠️ check_issue_badge_parity 스킵(파일):', e); return 0
    bad = []
    def _iss_min(src, tag):
        m = re.search(r'const ISS_CROSS_MIN = (\d+);', src)
        if not m: bad.append('%s: ISS_CROSS_MIN 선언 못 찾음' % tag); return None
        return m.group(1)
    a, b = _iss_min(js, 'viewer'), _iss_min(bv, 'build-viewer')
    if a and b and a != b: bad.append('ISS_CROSS_MIN 불일치: viewer=%s build-viewer=%s' % (a, b))
    for name in _ISS_REGEX_NAMES:
        ma = re.search(r'const %s = /(.+?)/;' % name, js)
        mb = re.search(r'const %s = /(.+?)/;' % name, bv)
        if not ma or not mb:
            bad.append('%s 정규식 선언 못 찾음(viewer=%s·build=%s)' % (name, bool(ma), bool(mb))); continue
        if ma.group(1) != mb.group(1):
            bad.append('%s 정규식 드리프트:\n      viewer: /%s/\n      build : /%s/' % (name, ma.group(1), mb.group(1)))
    for src, tag in ((js, 'viewer issCross'), (bv, 'build-viewer issEligible')):
        line = re.search(r'const issCross = .+|return \(cr >= ISS_CROSS_MIN.+', src)
        if not line or '=== 3' not in line.group(0) or '>= 8' not in line.group(0):
            bad.append('%s: grade3 우회(=== 3 · cross>=8) 마커 부재/드리프트' % tag)
    if bad:
        print('❌ 이슈 배지 게이트 viewer↔build-viewer 드리프트(한쪽만 수정 = 수집함↔피드 배지 불일치):')
        for x in bad: print('  -', x)
        rc = 1
    else:
        print('✅ 이슈 배지 패리티 — ISS_CROSS_MIN·BJ_* 4종 정규식·grade3 우회 = viewer↔build-viewer 동일.')
    return rc


# ── 얼빡(프사) 배경 차단 게이트 — 운영자 260726 「얼빡은 배경에 깔지마」 ──────────────────
# 왜 게이트인가: 같은 사고가 **두 번** 났다. ① 5인 `_face01`(파일명으로 잡음) ② 세라 `sera_k01`
#   (이름이 평범해 파일명 그물을 통과 · 640×640 얼빡이 채팅 배경에 깔림). 손 점검은 또 샌다.
# baseline = **정사각~가로형인데 배경으로 멀쩡한 것**(육안 확인 완료분). 정사각이라고 다 얼빡이 아니다 —
#   전신 풍경·여백 큰 일러스트는 세로 크롭해도 쓸 만하다. 그래서 자동 차단이 아니라 **등재제**로 둔다.
#   새 정사각이 들어오면 게이트가 막고 → 사람이 보고 → 얼빡이면 파일명에 프사 표식, 배경이면 여기 등재.
_FACE_RATIO_OK = {
    'characters/season/gojo/main/joy/gojo_n09.jpg',        # 736×736 헬스장 전신 풍경(인물 작음·배경 넓음) — 260726 육안
    'characters/season/lucy/dokkaebi/base/dokkaebi_21.jpg', # 735×825 비 오는 지붕 착석 전신 — 260726 육안
    'characters/season/lucy/dokkaebi/joy/dokkaebi_11.jpg',  # 1600×1600 소품 든 상반신 일러스트(여백 큼) — 260726 육안
    # ⚠ 최산 750×750 2장(런던 거리 전신)은 260730 오후 평면 축 이관으로 characters/idol/san/street_london_0{1,2}.jpg 이 됐다.
    #    이 표는 season/ manifest만 훑으므로(check_face_bg glob) idol/ 평면 축은 애초에 여기 오지 않는다 = 등재 불요.
    #    ⛳ 남은 구멍 = 평면 축(idol/) 전체가 얼빡·비율 게이트 사각지대(윈터도 동일) — 별건 과제.
}

def check_face_bg():
    """배경 풀에 얼빡이 섞였나 — media.json 실측(하드 게이트).
    ① 파일명 프사 표식(운영자 명명 = 정본 축)이 배경 풀에 있으면 차단.
    ② 종횡비 > FACE_RATIO 인데 _FACE_RATIO_OK 미등재면 차단(육안 확인 강제)."""
    sys.path.insert(0, os.path.join(ROOT, 'shared'))
    import build_season_media as bsm
    named, ratio, checked = [], [], 0
    for mp in sorted(glob.glob(os.path.join(ROOT, 'viewer', 'characters', 'season', '*', 'media.json'))):
        try:
            d = json.loads(open(mp, encoding='utf-8').read())
        except Exception:
            continue
        for bucket, arr in d.items():
            if bucket.startswith('_') or not isinstance(arr, list):
                continue
            for relp in arr:
                if not isinstance(relp, str):
                    continue
                p = Path(os.path.join(ROOT, 'viewer', relp.lstrip('/')))
                if p.suffix.lower() not in bsm.IMG_EXT or not p.exists():
                    continue
                checked += 1
                if bsm.is_face(p):
                    named.append(relp)
                    continue
                wh = bsm.img_size(p)
                if wh and wh[1] and wh[0] / wh[1] > bsm.FACE_RATIO and relp not in _FACE_RATIO_OK:
                    ratio.append('%s (%d×%d)' % (relp, wh[0], wh[1]))
    rc = 0
    if named:
        rc = 1
        print('❌ 얼빡 배경 게이트(차단) — 프사 표식 파일이 배경 풀에 있다 '
              '(처방 = 캐릭터 루트로 옮기고 build_season_media.py 재실행):')
        for x in named:
            print('   ·', x)
    if ratio:
        rc = 1
        print('❌ 얼빡 배경 게이트(차단) — 미확인 정사각~가로형이 배경 풀에 있다 '
              '(세로 무대 cover 시 좌우 잘림 · 얼빡이면 파일명에 프사 표식 후 재빌드 / 배경이면 _FACE_RATIO_OK 등재):')
        for x in ratio:
            print('   ·', x)
    if rc == 0:
        print('✅ 얼빡 배경 게이트 — 배경 풀 %d장 프사 0 · 정사각 미확인 0(승인 %d건).'
              % (checked, len(_FACE_RATIO_OK)))
    return rc


_INPUT_RE = re.compile(r'<input\b[^>]*>', re.I)
_AC_NEED = ('autocomplete', 'autocapitalize', 'autocorrect', 'spellcheck')

def check_autocomplete():
    """평문 텍스트 입력칸 = OS 자동완성 끔 4종 세트 하드 게이트(§🎨 · 운영자 260628).
    편집가능 <input type=text|search>가 autocomplete/autocapitalize/autocorrect/spellcheck 중 하나라도
    빠지면 rc=1 → 모바일 OS가 🔑비번·💳카드·📍주소 자동완성 바를 붙여 입력 번잡(운영자 실측 = 썸네일 '부제').
    제외: readonly/disabled/hidden(표시 전용 = 자동완성 대상 아님)·기타 type."""
    rc = 0
    for rel in ('viewer/index.html', 'viewer/thumb.html', 'viewer/ly.html', 'viewer/k.html', 'viewer/comp.html'):
        try:
            s = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        for m in _INPUT_RE.finditer(s):
            tag = m.group(0)
            tl = tag.lower()
            tm = re.search(r'type\s*=\s*["\']?(\w+)', tl)
            typ = tm.group(1) if tm else 'text'   # type 생략 = text
            if typ not in ('text', 'search'):
                continue
            if 'readonly' in tl or 'disabled' in tl:
                continue
            miss = [n for n in _AC_NEED if n not in tl]
            if miss:
                ln = s[:m.start()].count('\n') + 1
                print('❌ 자동완성 4종 누락 — %s:%d (%s 빠짐) → autocomplete/autocapitalize/autocorrect/spellcheck off 추가(§🎨)'
                      % (rel, ln, '·'.join(miss)))
                rc = 1
    if rc == 0:
        print('✅ 자동완성 게이트 — 편집가능 text/search 입력칸 전부 OS 자동완성 끔 4종 세트.')
    return rc


# render-text × (닫기/삭제 버튼이 SVG 아닌 문자 ×/✕ 사용) = 드리프트(§🎨 닫기=SVG X-path 단일 권장).
# 컴포넌트 컨텍스트(aria-label 닫기·삭제 류 또는 close/del/x 클래스)이고 *내용이 ×문자 하나뿐*일 때만 잡아
# 치수 텍스트('1080×1350')·JS 문자열 오탐 0. WARN(점진 통일 — thumb 등 병렬작업 파일이라 비차단).
_XSET = '×✕⨯╳✖'
_XEL_RE = re.compile(r'<(button|a|span|div|i)\b([^>]*)>\s*([' + _XSET + r'])\s*</\1>', re.I)
_XCTX_RE = re.compile(r'aria-label\s*=\s*["\'][^"\']*(닫기|닫음|삭제|취소|제거|지우)|class\s*=\s*["\'][^"\']*(tool-x|dlg-x|-x\b|close|abdel|del|btn-x)', re.I)

def check_x_char():
    warns = []
    for rel in ('viewer/index.html', 'viewer/thumb.html', 'viewer/ly.html', 'viewer/k.html', 'viewer/comp.html'):
        try:
            s = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        s2 = re.sub(r'<!--.*?-->', '', s, flags=re.S)   # 주석 제거(오탐 차단)
        for m in _XEL_RE.finditer(s2):
            if _XCTX_RE.search(m.group(2)):
                ln = s2[:m.start()].count('\n') + 1
                warns.append('%s:%d <%s> 닫기/삭제 = 문자 「%s」 → SVG X-path(§🎨 닫기=SVG 단일 권장)'
                             % (rel, ln, m.group(1), m.group(3)))
    if warns:
        print('⚠️ 닫기/삭제 × 문자 게이트(비차단) — SVG로 통일 권장:')
        for w in warns:
            print('  -', w)
    else:
        print('✅ 닫기/삭제 × 문자 게이트 — 문자 ×/✕ 닫기버튼 0(전부 SVG).')
    return 0   # WARN-only(병렬작업 파일 비차단)


# CLAUDE.md §<이모지> 앵커 해소 게이트(WARN-first · L8 평의회 설계 260714) — 참조는 있는데 CLAUDE.md에 그 `## <이모지>` 섹션 실물이 없으면 경고.
_EMO = '[\U0001F000-\U0001FAFF☀-➿⬀-⯿⌀-⏿←-⇿]'
_ANCHOR_REF = re.compile(r'CLAUDE\.md\s*§\s*(' + _EMO + ')')
_ANCHOR_HEAD = re.compile(r'^#{1,6}\s+(' + _EMO + ')', re.M)
_ANCHOR_GLOBS = ('*.md', 'docs/**/*.md', '구성도/**/*.md', '.claude/**/*.md')
_ANCHOR_SKIP = ('docs/작업이력.md',)   # frozen append-only 원장 = 비대상(수정 금지)


def check_claude_anchors():
    """CLAUDE.md §<이모지> 참조가 CLAUDE.md의 `## <이모지>` 섹션으로 해소되는지 — 하드 게이트(rc=1).
    260714 WARN-first 설계 → 260717 Q.19 백로그 0 청산 직후 Q.20 운영자 승인으로 하드 승격.
    해소 = 섹션 복원 or 참조를 [N]·실물 경로로 repoint(원문 인용은 백틱 감싸면 오탐 제외)."""
    try:
        have = set(_ANCHOR_HEAD.findall(open(os.path.join(ROOT, 'CLAUDE.md'), encoding='utf-8').read()))
    except OSError:
        print('⚠️ check_claude_anchors 스킵(CLAUDE.md 없음)'); return 0
    warns, seen = [], set()
    for g in _ANCHOR_GLOBS:
        for p in sorted(glob.glob(os.path.join(ROOT, g), recursive=True)):
            rel = os.path.relpath(p, ROOT)
            if rel.startswith('_versions') or rel in _ANCHOR_SKIP or rel in seen:
                continue
            seen.add(rel)
            try:
                raw = open(p, encoding='utf-8').read()
            except OSError:
                continue
            in_fence = False
            for ln, line in enumerate(raw.splitlines(), 1):
                if line.lstrip().startswith('```'):
                    in_fence = not in_fence; continue
                if in_fence:
                    continue
                for e in _ANCHOR_REF.findall(re.sub(r'`[^`\n]+`', '', line)):   # 인라인 백틱 제거(예시 오탐 차단)
                    if e not in have:
                        warns.append('%s:%d → CLAUDE.md §%s (섹션 실물 없음)' % (rel, ln, e))
    if warns:
        print('❌ CLAUDE.md §앵커 게이트(하드·Q.20 승격 260717) — 참조하나 섹션 실물 없음(%d):' % len(warns))
        for w in warns:
            print('  -', w)
        print('  (해소 = CLAUDE.md에 `## §섹션` 복원 or 참조를 [N]·실물 경로로 repoint)')
        return 1
    print('✅ CLAUDE.md §앵커 게이트 — CLAUDE.md §<이모지> 참조 전부 실물 섹션 해소.')
    return 0


def check_tokens_link():
    """공유 구조토큰 tokens.css 배선 하드게이트(§🎨 STAGE3·분신술7·260628).
    4뷰어(thumb/ly/k/comp)가 viewer/tokens.css를 <link>로 로드하는지 검증 — 미링크면 신규 컴포넌트가
    var(--r-m 등) 구조토큰을 못 써 raw로 새거나(드리프트), 옛 링크가 깨지면 침묵(check_paths가 HTML <link>
    미검증)이라 여기서 잡는다. tokens.css 파일 부재면 게이트 무력(아직 미생성=스킵)."""
    if not os.path.exists(os.path.join(ROOT, 'viewer', 'tokens.css')):
        print('⚠️ tokens.css 없음 — 구조토큰 링크 게이트 스킵'); return 0
    rc = 0
    for rel in ('viewer/thumb.html', 'viewer/ly.html', 'viewer/k.html', 'viewer/comp.html'):
        try:
            html = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        if not re.search(r'<link[^>]+href=["\']tokens\.css["\']', html):
            print('❌ 구조토큰 링크 누락 — %s가 tokens.css를 <link> 안 함 → <head>에 <link rel=stylesheet href=tokens.css> 추가(§🎨 STAGE3)' % rel)
            rc = 1
    if rc == 0:
        print('✅ 구조토큰 링크 — 4뷰어 전부 tokens.css 로드.')
    return rc


def check_soremeori():
    """소머리(구분자 •) 표준 강제 — 텍스트 흰색(--fg)·블릿 형광(--accent)·토큰 굵기(§📐·운영자 260629).
    회색(--mut) 소머리·블릿 없는 소머리·리터럴 굵기 재발을 차단(옛 흰색600 인라인 드리프트 방지).
    정본 = 뉴스 index .cref-lbl(무변경). 대상 = label.fl(thumb/k/ly/comp) + thumb .csec/.hist-bul.
    .gospec(명세 readout)은 소머리 아님 = 검사 제외."""
    rc = 0
    # 블록 소머리 label.fl = 텍스트 흰색(--fg)·800(--fw-x) + ::before 형광(--accent)·700(--fw-b)
    for rel in ('viewer/thumb.html', 'viewer/k.html', 'viewer/ly.html', 'viewer/comp.html'):
        try:
            css = open(os.path.join(ROOT, rel), encoding='utf-8').read()
        except Exception:
            continue
        m = re.search(r'label\.fl\s*\{([^}]*)\}', css)
        if not m:
            print('❌ 소머리 게이트 — %s에 label.fl 규칙 없음(소머리 = 흰색800+형광블릿·§📐)' % rel); rc = 1; continue
        if 'var(--fg)' not in m.group(1) or 'var(--fw-x)' not in m.group(1):
            print('❌ 소머리 게이트 — %s label.fl 텍스트가 흰색(--fg)·800(--fw-x) 아님(회색/리터럴 금지·§📐)' % rel); rc = 1
        mb = re.search(r'label\.fl::before\s*\{([^}]*)\}', css)
        if not mb or 'var(--accent)' not in mb.group(1) or 'var(--fw-b)' not in mb.group(1):
            print('❌ 소머리 게이트 — %s label.fl::before 블릿이 형광(--accent)·700(--fw-b) 아님(블릿 누락/색오류·§📐)' % rel); rc = 1
    # flex 소머리 thumb .csec = 텍스트 흰색800 + ::before 형광700 · .hist-bul = 특수 보라
    try:
        t = open(os.path.join(ROOT, 'viewer', 'thumb.html'), encoding='utf-8').read()
        mc = re.search(r'\.csec\s*\{([^}]*)\}', t)
        if not mc or 'var(--fg)' not in mc.group(1) or 'var(--fw-x)' not in mc.group(1):
            print('❌ 소머리 게이트 — thumb .csec 텍스트가 흰색(--fg)·800(--fw-x) 아님(§📐)'); rc = 1
        mcb = re.search(r'\.csec::before\s*\{([^}]*)\}', t)
        if not mcb or 'var(--accent)' not in mcb.group(1) or 'var(--fw-b)' not in mcb.group(1):
            print('❌ 소머리 게이트 — thumb .csec::before 블릿이 형광(--accent)·700(--fw-b) 아님(§📐)'); rc = 1
        mh = re.search(r'\.hist-bul\s*\{([^}]*)\}', t)
        if not mh or 'var(--hist-accent)' not in mh.group(1):
            print('❌ 소머리 게이트 — thumb .hist-bul 특수 블릿이 보라(--hist-accent) 아님(§📐 특수)'); rc = 1
        # 토글(.ovfmt/.onoff) 붙는 .csec 행높이 상쇄 = 토글 세로패딩(3px·탭영역)이 flex 행 키워 첫 소머리 • 내려앉는 것 차단(§📐 첫 블릿 화면선·운영자 260629 저작권탭 교정)
        mn = re.search(r'\.csec \.ovfmt\s*,\s*\.csec \.onoff\s*\{([^}]*)\}', t)
        nb = mn.group(1) if mn else ''
        if not mn or not (('margin-top:-' in nb and 'margin-bottom:-' in nb) or 'margin-block:-' in nb):
            print('❌ 소머리 게이트 — thumb .csec 토글(.ovfmt/.onoff) 행높이 상쇄(margin-block:-3px) 누락 → 토글 붙은 첫 소머리 • 내려앉음 재발(§📐 첫 블릿 화면선)'); rc = 1
    except Exception:
        pass
    if rc == 0:
        print('✅ 소머리 게이트 — 5뷰어 소머리 텍스트 흰색·블릿 형광(특수 보라)·토큰 일치(§📐).')
    return rc


def check_claude_failover():
    """모든 Claude 호출 스크립트는 폴오버 SSOT를 경유 — 계정 로테이션 통일(운영자 260629·§📰).
    자체 쿼터 정규식·자체 폴오버 금지: 한 곳만 stale돼도 전건 실패(260629 'weekly limit' 미인식 실측 = 폴오버 누락·요약/카드 전건 failed).
    스캔 범위 = .github/scripts/ + scraper/(둘 다 실제 claude 호출처 — auto_pick_breaking.py가 scraper에 있음 · 분신술10 발견).
    호출 신호 = 비-주석 라인의 claude_meter / run_claude( / 'claude -p'(주석·docstring 멘션은 제외 = ly_stt·token_report 오탐 차단 → run_claude는 *호출* `(` 요구).
    경유 = claude_failover(셸 SSOT 호출) 또는 claude_py/run_claude(파이썬 SSOT = is_quota+failover 내장)."""
    rc = 0
    miss = []
    INVOKE = re.compile(r'^(?!\s*#).*(claude_meter|run_claude\(|claude -p)', re.M)   # 실제(비-주석) Claude 호출만 — run_claude는 호출`(`만(import·docstring 제외)·주석 속 'claude -p' 멘션(ly_stt 등) 제외
    COMPLY = re.compile(r'claude_failover|claude_py|run_claude')                     # 셸=claude_failover 호출 / 파이썬=claude_py(run_claude) SSOT 경유
    for d in ('.github/scripts', 'scraper'):
        sdir = os.path.join(ROOT, d)
        try:
            names = sorted(n for n in os.listdir(sdir) if n.endswith(('.sh', '.py')))
        except Exception:
            continue
        for n in names:
            try:
                txt = open(os.path.join(sdir, n), encoding='utf-8').read()
            except Exception:
                continue
            if not INVOKE.search(txt):
                continue
            if not COMPLY.search(txt):
                miss.append(d + '/' + n)
    if miss:
        print('❌ claude 폴오버 게이트 — Claude 호출인데 폴오버 SSOT(claude_failover/claude_py) 미경유: %s · 자체 쿼터처리 금지(계정 로테이션 통일·§📰)' % ', '.join(miss))
        rc = 1
    else:
        print('✅ claude 폴오버 게이트 — 전 Claude 호출처(.github/scripts+scraper)가 폴오버 SSOT 경유(주간한도 시 4계정 자동 로테이션 통일·§📰).')
    return rc


def check_judge_bare():
    """judge(gate_judge·breaking_judge)는 라이브·구독 OAuth 전용 파이프라인 → --bare 금지, --safe-mode만.
    ⚠️ 진짜 원인(260701 실측 정정): --bare는 OAuth를 안 읽는다(CLI 2.1.197 --help 명시 "Anthropic auth is
    strictly ANTHROPIC_API_KEY or apiKeyHelper — OAuth and keychain are never read"). 이 레포는 구독 OAuth 전용
    (종량제 키 없음 · 워크플로가 ANTHROPIC_API_KEY도 unset)이라 judge에 --bare면 *인증부터* rc=1 즉사 = #1264(260630)
    #1264 사고의 진짜 원인. (당시 'MultiEdit matches no known tool' stderr는 CLI 2.1.197에선 *비치명 노이즈*(rc=0)였으나 —
    260712 러너 CLI(주28)에서 unknown deny 규칙이 *치명 rc=1*로 엄격화 = 답장/오프닝 전량 실패의 실제 원인이 됨(로컬 2.1.207은 여전히 비치명 = 버전 드리프트).
    → gen_out --disallowedTools 3곳(chat/call/nudge)에서 폐기 도구 MultiEdit 제거·실측 260712. 잔여 목록 known 스모크 rc=0.)
    ∴ CLAUDE.md 로드 스킵(cache_w 절감)이 필요하면 반드시 --safe-mode(Auth·built-in 도구·permissions 정상 유지).
    게이트: judge 스크립트가 '--bare'를 emit(코드경로)하면 rc=1 · 생성경로(claude_meter·more_images)도 --bare 기본 ON이면 rc=1(OAuth 즉사).
    정본 = CLAUDE.md §📰 + docs/인계_bare도구충돌_judge복구_프로세스개선.md."""
    rc = 0
    bad = []

    def _read(p):
        try:
            return open(os.path.join(ROOT, p), encoding='utf-8').read()
        except Exception:
            return ''

    # judge(py): '--bare' emit(코드경로)면 = OAuth 인증 즉사. 주석 속 설명('--safe-mode: … --bare 아님')은 따옴표 없어 미매칭.
    for n in ('gate_judge.py', 'breaking_judge.py'):
        txt = _read('.github/scripts/' + n)
        if re.search(r'"--bare"', txt):
            bad.append('%s (judge에 --bare emit = OAuth 안 읽어 인증 즉사 → --safe-mode 사용)' % n)

    # yeta 챗(sh): 신규 claude 스크립트가 --bare emit하면 동일 즉사 — 기존 고정 튜플의 사각지대 봉합(260703 계획안 P0).
    # judge와 동일하게 emit 형태("--bare" 따옴표)만 매칭 — 주석 속 '--bare 금지' 경고문은 오탐 안 함.
    if re.search(r'"--bare"', _read('.github/scripts/yeta_chat.sh')):
        bad.append('yeta_chat.sh ("--bare" emit = OAuth 안 읽어 인증 즉사 → --safe-mode만 · env YETA_SAFE)')

    # 생성경로: --bare 기본 ON(claude_meter :-1 / more_images "1")이면 = OAuth 즉사(현재 롤백 OFF면 통과)
    if re.search(r'CLAUDE_BARE:-1', _read('shared/claude_meter.sh')):
        bad.append('claude_meter.sh (CLAUDE_BARE 기본 ON = 생성경로 --bare = OAuth 즉사)')
    if re.search(r'CLAUDE_BARE"\s*,\s*"1"', _read('.github/scripts/more_images.py')):
        bad.append('more_images.py (CLAUDE_BARE 기본 ON = --bare = OAuth 즉사)')

    if bad:
        print('❌ judge/파이프라인 --bare 게이트 — OAuth 전용 레포에 --bare(OAuth 안 읽음=인증 즉사·260701 사고 진짜원인): %s → --safe-mode로 교체(CLAUDE.md 로드 스킵 + Auth·도구 정상 · 정본 CLAUDE.md §📰)' % ', '.join(bad))
        rc = 1
    else:
        print('✅ judge/파이프라인 --bare 게이트 — judge는 --safe-mode(OAuth 정상)·생성경로 --bare 기본 OFF(260701 사고 재발방지).')
    return rc


# ── 지침 변경 로그 게이트(WARN-only · 운영자 260714 승인) ──
# 지침 축(00_지침·캐릭터 카드·policy.json 또는 yeta_chat.sh의 출력 계약 문구)이 이번 변경에 포함됐는데
# docs/지침변경로그.md 한 줄이 같이 안 바뀌었으면 경고. 비차단 = 부담 0(운영자 "부담 되면 안 하는 게 맞다").
GLOG = 'docs/지침변경로그.md'
GUIDE_FILES = ('apps/yeta/00_지침_캐릭터챗.md', 'apps/yeta/policy.json')
GUIDE_DIR = 'apps/yeta/characters/'
CONTRACT_PAT = re.compile(r'^[+-].*(출력 계약|기억 블록|<<NOTE|<<MOOD|문장.*80자|길이\(운영자)')   # yeta_chat.sh 지침성 줄 휴리스틱(+/- 변경 줄만)


# ── SAFETY-LOCK 게이트(운영자 260714) — 콘텐츠 거절 처리 가드레일이 약화·제거되면 잡는 트립와이어 ──
# 각 (파일, 앵커) = 그 파일에 반드시 존재해야 하는 안전 가드. 앵커 소실 = 블록 삭제·이동 = ⚠️ 경고(리팩터로 앵커 옮겼으면 이 표도 함께 갱신).
# 260717 복구(Q.15): 934d46e에서 함수 소실(호출부만 잔존 = 매 커밋 '스킵') → d4f1035 원본 복원.
#   단 claude_transient.sh 앵커는 운영자가 8f5e7db로 ⛔주석을 지웠으므로(가드 함수 실물은 생존) 살아있는 함수 시그니처로 재배선.
SAFETY_LOCKS = [
    ('shared/claude_transient.sh', 'is_frame_break() {'),
    ('.github/scripts/yeta_chat.sh', '⛔ SAFETY-LOCK[flee]'),
    ('.github/scripts/yeta_stream.py', '⛔ SAFETY-LOCK[stream-guard]'),
]


def check_safety_lock():
    missing = []
    for rel, anchor in SAFETY_LOCKS:
        p = os.path.join(ROOT, rel)
        try:
            with open(p, encoding='utf-8') as f:
                if anchor not in f.read():
                    missing.append('%s → %s (앵커 소실 = 안전 가드 삭제·이동?)' % (rel, anchor))
        except Exception:
            missing.append('%s → 파일 없음(%s)' % (rel, anchor))
    if missing:
        print('⚠️ SAFETY-LOCK 게이트 — 콘텐츠 거절 가드레일 앵커 소실(약화·삭제 의심):')
        for m in missing:
            print('  -', m)
        print('  → 의도된 리팩터면 shared/check_refs.py SAFETY_LOCKS 표를 함께 갱신 · 약화면 복원(운영자 260714 안전축)')
    return 0   # WARN-only(리팩터 유연성 · 하지만 diff 리뷰에 반드시 뜸)


def check_guideline_log():
    try:
        # 스테이징+워킹 합집합 — 커밋 전(수정 모드 ③)·훅 양쪽에서 같은 판정
        out = subprocess.run(['git', '-c', 'core.quotepath=off', 'diff', '--name-only', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=15)   # quotepath off = 한글 경로 원문(이스케이프 매칭 빗나감 방지)
        changed = set(l.strip() for l in out.stdout.splitlines() if l.strip())
    except Exception:
        return 0   # git 불능 환경(CI 아카이브 등) = 조용히 통과
    if not changed:
        return 0
    hit = [f for f in changed if f in GUIDE_FILES or (f.startswith(GUIDE_DIR) and f.endswith('.md'))]
    if '.github/scripts/yeta_chat.sh' in changed:
        try:
            d = subprocess.run(['git', 'diff', '-U0', 'HEAD', '--', '.github/scripts/yeta_chat.sh'], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout
            if any(CONTRACT_PAT.match(l) for l in d.splitlines()):
                hit.append('.github/scripts/yeta_chat.sh [출력 계약]')
        except Exception:
            pass
    if hit and GLOG not in changed:
        print('⚠️ 지침 변경 로그 게이트(비차단): 지침 축이 바뀌었는데 %s 미갱신 —' % GLOG)
        for f in hit:
            print('  -', f)
        print('  → 표에 한 줄(날짜·변경·이유·PR·회귀 커밋)만 추가해줘(§docs/지침변경로그.md 머리 규칙)')
    return 0   # WARN-only


# ── 루트 청결 게이트(WARN-only · 운영자 260726 승인 "게이트 ㄱㄱ" · Q.97) ──
# 웹·앱에서 파일을 올리면 기본 착지점이 **레포 루트**다. 그래서 미가공 이미지·영상·중복 압축본이
# 루트에 쌓인다(260726 실측 = 6파일 17.3MB · 그중 3건은 docs/reports 사본과 바이트 동일한 중복).
# 화이트리스트 밖 루트 '파일'이 보이면 어디로 옮길지 알려준다. 비차단 = 업로드를 막지 않는다(정리 시점 = 운영자 선택).
ROOT_OK_FILES = {'CLAUDE.md', 'AGENTS.md', 'design-tokens.lock'}   # 루트 고정 필수 3종(lock = 토큰 락 게이트가 루트 경로로 읽어 이동 불가)
ROOT_STAGE = '_소재'   # 미가공 소재 착지점 — README에 정본 경로(viewer/characters/season/<id>/)·빌더·얼빡 규칙


def check_root_clean():
    try:
        names = os.listdir(ROOT)
    except OSError:
        return 0   # 목록 불능 = 조용히 통과
    stray = sorted(n for n in names
                   if not n.startswith('.')                              # 점파일(.gitignore 등) = 대상 아님
                   and os.path.isfile(os.path.join(ROOT, n))             # 디렉터리는 대상 아님
                   and n not in ROOT_OK_FILES)
    if stray:
        print('⚠️ 루트 청결 게이트(비차단): 최상위에 화이트리스트 밖 파일 %d개 —' % len(stray))
        for n in stray:
            try:
                kb = os.path.getsize(os.path.join(ROOT, n)) // 1024
            except OSError:
                kb = 0
            print('  - %s (%dKB)' % (n, kb))
        print('  → 미가공 이미지·영상 = `%s/`로(정본 경로 안내 = %s/README.md) · 문서·리포트 = `docs/reports/`로 · '
              '진짜 루트에 있어야 하면 shared/check_refs.py ROOT_OK_FILES에 등재' % (ROOT_STAGE, ROOT_STAGE))
    return 0   # WARN-only


def check_world_rate():
    """무음동 세계율 폴백·기본 4점 짝 하드 게이트(운영자 260716 Q.08 평의회 · 260728 L1 노브 개편).
    배속이 L1 설정값이 된 뒤(운영자 260728 「설정값에서 조정 · L1급」) 대조 대상이 '공식 안의 리터럴'에서 **폴백 상수 + 정책 기본값**으로 바뀌었다 —
    실배속은 세션 정책이 정하고, 정책을 못 읽는 경로(구세션·프리페치 전·러너 미전달)는 폴백으로 착지한다. 그 착지점 4곳이 어긋나면 지도·대화 시간축이 다시 갈라진다."""
    rc = 0
    try:
        vals = {}
        v = re.search(r'const YWORLD_RATE = (\d+)', open(os.path.join(ROOT, 'viewer/index.html'), encoding='utf-8').read())
        if v: vals['viewer YWORLD_RATE'] = v.group(1)
        c = re.search(r'_WRATE_FB = (\d+)', open(os.path.join(ROOT, '.github/scripts/yeta_chat.sh'), encoding='utf-8').read())
        if c: vals['러너 폴백(_WRATE_FB)'] = c.group(1)
        p = re.search(r'^_RATE = (\d+)', open(os.path.join(ROOT, '.github/scripts/yeta_place.py'), encoding='utf-8').read(), re.M)
        if p: vals['world_dh 폴백(_RATE)'] = p.group(1)
        try:   # ④ 노브의 기본 선택지 = L1.world[wrate].vals[default] — 폴백과 어긋나면 "설정 안 만졌는데 배속이 다른" 상태가 된다
            _pj = json.load(open(os.path.join(ROOT, 'apps/yeta/policy.json'), encoding='utf-8'))
            _ax = next((x for x in ((_pj.get('L1') or {}).get('world') or []) if isinstance(x, dict) and x.get('key') == 'wrate'), None)
            if _ax and isinstance(_ax.get('vals'), list):
                _i = _ax.get('default') or 0
                if 0 <= _i < len(_ax['vals']): vals['policy.json 기본(L1.world wrate)'] = str(_ax['vals'][_i])
        except Exception: pass
        if len(vals) != 4:
            print('❌ 세계율 게이트 — 4점 중 %d점만 검출(패턴 이동 시 게이트도 같이 수정): %s' % (len(vals), ', '.join(vals) or '없음')); return 1
        if len(set(vals.values())) != 1:
            print('❌ 세계율 게이트 — 배속 폴백·기본 4점 불일치(한쪽만 수정 = 시간축 드리프트): ' + ' · '.join(f'{k}={v}' for k, v in vals.items())); return 1
        print('✅ 세계율 게이트 — 배속 폴백·기본 4점 짝 일치(%s배: 뷰어·러너·world_dh·policy.json · 실배속 = L1 노브).' % next(iter(vals.values())))
    except Exception as e:
        print('⚠️ 세계율 게이트 스킵:', e)
    return rc


def check_map_bg_pair():
    """지도 배경↔도로 좌표 짝 하드 게이트(운영자 260716 Q.08 평의회9 — "고쳐도 그대로" 반복 절단): map_*.png 재생성 시 YMAP_ROADS_TONE 좌표가 침묵 실효하던 구멍 봉합. 배경 sha1[:8] ≠ viewer YMAP_BG_SHA 토큰 = 커밋 차단 → 재실측(shared/yeta_map_trace.py) 후 토큰 갱신."""
    rc = 0
    try:
        src = open(os.path.join(ROOT, 'viewer/index.html'), encoding='utf-8').read()
        m = re.search(r'YMAP_BG_SHA: night=([0-9a-f]{8}) day=([0-9a-f]{8})', src)
        if not m:
            print('❌ 지도 배경 짝 게이트 — viewer YMAP_BG_SHA 토큰 없음(YMAP_ROADS_TONE 위 주석)'); return 1
        want = {'night': m.group(1), 'day': m.group(2)}
        for tone, tok in want.items():
            path = os.path.join(ROOT, f'viewer/assets/yeta_map/map_{tone}.png')
            if not os.path.exists(path):
                print(f'❌ 지도 배경 짝 게이트 — map_{tone}.png 없음'); rc = 1; continue
            real = hashlib.sha1(open(path, 'rb').read()).hexdigest()[:8]
            if real != tok:
                print(f'❌ 지도 배경 짝 게이트 — map_{tone}.png 변경 감지(sha {real} ≠ 토큰 {tok}): 도로 좌표·가림체 실효 위험 → python3 shared/yeta_map_trace.py 재실측(마스크·YMAP_FG 지문 검증 포함) + 토큰 갱신'); rc = 1
        if 'YMAP_FG' in src and not re.search(r'YMAP_FG_FP: night=[0-9a-f]{8} day=[0-9a-f]{8}', src):
            print('⚠️ 지도 배경 짝 게이트(비차단) — YMAP_FG는 있는데 YMAP_FG_FP 지문 토큰 없음: yeta_map_trace.py 실행값으로 등재(가림체 스테일 침묵 방지 · Q.11)')
        if rc == 0:
            print('✅ 지도 배경 짝 게이트 — map_night/day.png ↔ 도로 좌표 토큰 일치.')
    except Exception as e:
        print('⚠️ 지도 배경 짝 게이트 스킵:', e)
    return rc


# ── 모델 ID 드리프트 게이트 (운영자 260725 한 수 · 정본 = shared/models.json) ──
# 모델 ID가 호출처마다 리터럴로 흩어져 있다 — 이 레포 실측(260725): gpt-image-2 6파일 · gemini 3파일(각자
# '실제 ID 바뀌면 함께 교체' 주석 의존) · claude 티어 20+곳. 런타임 결합은 Functions·정적 뷰어에 파일 접근이 없어 불가 → 「정본 1곳 +
# 기계 치환(shared/apply_models.py) + 이 게이트」 3점(nomute-editor 260725 확립분 이식). 치환기가 놓친 한 곳을 여기서 차단.
_MODEL_ID_RE = re.compile(r'claude-[a-z]+-[0-9][0-9a-z.-]*')
_MODEL_NAME_GUARD = '(?![인명])'   # `Opus 5인/5명`(인원) = 모델명 아님 — apply_models.py NAME_GUARD와 동일 규약


def _model_registry():
    with open(os.path.join(ROOT, 'shared', 'models.json'), encoding='utf-8') as f:
        return json.load(f)


def _model_scan_files(reg):
    drop = set()
    for g in reg['scan']['exclude']:
        drop |= {os.path.abspath(p) for p in glob.glob(os.path.join(ROOT, g), recursive=True)}
    out = []
    for g in reg['scan']['include']:
        for p in glob.glob(os.path.join(ROOT, g), recursive=True):
            ap = os.path.abspath(p)
            if os.path.isfile(ap) and ap not in drop and not any(ap.startswith(d + os.sep) for d in drop):
                out.append(ap)
    return sorted(set(out))


def check_model_ids():
    """모델 ID·표시명 드리프트 하드게이트(운영자 260725 한 수 · 정본 = `shared/models.json`).
    ① 스캔 경로의 모든 `claude-*` 리터럴이 정본 등재 ID인지 — 오타(`claude-opus5`)·미등재 모델 차단.
    ② 정본 `retired`(구세대 ID·표시명)가 한 톨도 안 남았는지 — 승격 때 '한 곳 빠뜨림' 봉쇄(이 게이트의 본체).
    승격법 = `python3 shared/apply_models.py <티어|벤더키> <새ID> ["<표시명>"] ["<한글명>"]` → 이 게이트로 검산 → 커밋.
    ⚠️ 표시명 검사는 `Opus 5인/5명`(인원 표기)을 (?![인명]) 가드로 제외 — 인원은 '명'으로 써라(모델명과 붙어 읽힌다).
    스캔 범위·제외(원장·보고서·동결본·산출물)도 models.json `scan`이 정본 = 여기 하드코딩 없음."""
    try:
        reg = _model_registry()
    except Exception as e:
        print('❌ 모델 ID 게이트: shared/models.json 못 읽음(부재/문법?) —', e); return 1   # fail-closed = 정본 소실 무성 무력화 차단
    ids = {t['id'] for t in reg['tiers'].values()}
    retired = [(r, re.compile(re.escape(r) + (_MODEL_NAME_GUARD if not r.startswith('claude-') else '')))
               for r in reg.get('retired', [])]
    # 벤더(비-Claude · 종량제) = 표시명 없이 ID만 · family 정규식으로 '그 계열의 다른 버전이 섞였나'를 본다
    vendors = [(k, v['id'], re.compile(v['family']), set(v.get('allow', [])))
               for k, v in reg.get('vendors', {}).items() if v.get('family')]
    bad = []
    for path in _model_scan_files(reg):
        try:
            src = open(path, encoding='utf-8').read()
        except (OSError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, ROOT)
        for lit in sorted(set(_MODEL_ID_RE.findall(src))):
            if lit not in ids:
                bad.append('%s: 미등재 모델 ID `%s` (정본 = %s)' % (rel, lit, ' · '.join(sorted(ids))))
        for key, vid, rx, allow in vendors:
            for lit in sorted(set(rx.findall(src))):
                if lit != vid and lit not in allow:
                    bad.append('%s: 벤더[%s] 계열 드리프트 `%s` — 정본 `%s`%s (종량제 = ID 어긋나면 실패·오과금)'
                               % (rel, key, lit, vid, (' · 허용 알리아스 %s' % ' '.join(sorted(allow))) if allow else ''))
        for raw, rx in retired:
            n = len(rx.findall(src))
            if n:
                bad.append('%s: 구세대 표기 `%s` %d곳 잔존 — `python3 shared/apply_models.py` 재실행 or 수동 교체' % (rel, raw, n))
    if bad:
        print('❌ 모델 ID 게이트 — 정본(shared/models.json) 드리프트:')
        for b in bad: print('   -', b)
        return 1
    print('✅ 모델 ID 게이트 — %d티어(%s) + 벤더 %d종(%s) 정본 일치 · 구세대 %d종 잔존 0(스캔 %d파일 · 승격 = apply_models.py).'
          % (len(ids), ' · '.join(t['id'] for t in reg['tiers'].values()), len(vendors),
             ' · '.join(k for k, *_ in vendors), len(retired), len(_model_scan_files(reg))))
    return 0


# ── 게이트 문서화 메타 게이트 (운영자 260723 Q468 "게이트 문서화 강제 = 만들어놓고 안 봄 구조 차단") ──
# 모든 게이트(def check_*)가 정본 문서에 *이름으로* 등재됐는지 대조 → 미등재 신규 게이트 = rc=1 차단.
# = 색 전파 골격(STAGE4·check_palette_sync)의 SSOT 인덱스 완전성 소프트룰("새 기틀 = 인덱스 행 추가 · 누락
# = 규칙2 위반" = 디자인기틀_SSOT.md 서문 · 기계 강제 아님이라던 그것)의 기계화. 정본 = CLAUDE.md + 디자인
# SSOT + 규칙·큐레이션 정본 문서(로그류 큐/이력 제외). 기존 미등재 = _GATE_DOC_BASELINE 면책(품질 유지 =
# 대량 소급 문서화 강제 안 함 · 신규만 래칫 · 베이스라인 = 소급 문서화 TODO·축소 지향). 자기 자신
# (check_gate_docs)도 대상 = SSOT §6·CLAUDE.md [15] 등재(자기참조 정합).
_GATE_DOC_CANON = ('CLAUDE.md', 'docs/디자인기틀_SSOT.md', 'docs/CII_컴포넌트계승인덱스.md',
                   'docs/라우터_법령전문.md', 'docs/실행계약_전문.md', 'docs/플레이그라운드_포터블.md',
                   'docs/curation-algorithm.md', 'docs/curation-rubric.md')
_GATE_DOC_BASELINE = frozenset({   # 260723 스냅샷 = 소급 문서화 대상(신규 추가 = 문서화 회피라 지양 · diff 가시 · 축소 지향)
    'check_paths', 'check_versions', 'check_viewer_js', 'check_functions_js', 'check_inject_dividers',
    'check_inject_markers', 'check_sens_vocab', 'check_fast_max_h_parity', 'check_shell_cache_parity',
    'check_tokens_link', 'check_dangling_var', 'check_candidates_size', 'check_conflict_markers',
    'check_qledger_unique', 'check_anchor_liveness', 'check_html_charset', 'check_fp_parity', 'check_label_fill'})


def main():
    fails = check_paths() + check_versions() + check_inject_dividers() + check_inject_markers()
    rc = 0
    if fails:
        print('❌ check_refs 실패 %d건:' % len(fails))
        for f in fails:
            print('  -', f)
        rc = 1
    else:
        print('✅ check_refs 통과 — 경로 참조 실존·파일명↔내부 버전 일치.')
    try:
        if check_viewer_js() != 0:   # viewer 인라인 JS 구문(하드 게이트 — SyntaxError=뷰어 전면 사망)
            rc = 1
    except Exception as e:
        print('⚠️ check_viewer_js 스킵:', e)
    try:
        if check_icon_ssot() != 0:   # 공유 아이콘 SSOT(하드 게이트 — 인라인 재선언·미로드=드리프트 부활 차단·260628)
            rc = 1
    except Exception as e:
        print('⚠️ check_icon_ssot 스킵:', e)
    try:
        import build_design_mirror   # 디자인 거울 정합: 구성도/base.css = viewer :root (하드 게이트·§🎨 ⓐ)
        if build_design_mirror.check() != 0:
            rc = 1
    except Exception as e:
        print('⚠️ 디자인 거울 check 스킵:', e)
    try:
        import subprocess as _sp, sys as _sy   # 시즌 미디어 정합(하드 게이트 · 평의회 260717): media.json = 폴더 실측 — 사진 추가/삭제 후 재생성 누락 = 죽은 경로 로테이션(검은 무대) 차단 · 처방 = python3 shared/build_season_media.py
        if _sp.run([_sy.executable, os.path.join(ROOT, 'shared', 'build_season_media.py'), '--check']).returncode != 0:
            rc = 1
    except Exception as e:
        print('⚠️ 시즌 미디어 check 스킵:', e)
    try:
        if check_design() != 0:   # accent_raw 차단(rc=1·운영자 ③b STAGE1) · hex/blur/죽은토큰은 내부 WARN
            rc = 1
    except Exception as e:
        print('⚠️ check_design 스킵:', e)
    try:
        if check_token_lock() != 0:   # 절대명령#1 기계강제 — 미승인 신규 :root 토큰 차단(승인원장 design-tokens.lock)
            rc = 1
    except Exception as e:
        print('⚠️ 토큰 락 게이트 스킵:', e)
    try:
        if check_backstack_contract() != 0:   # 백스택 popstate 3분기 생존(267차 — '뒤로 1회 씹힘' 재발 차단 · 실증 = tests/test_backstack.js)
            rc = 1
    except Exception as e:
        print('⚠️ 백스택 계약 게이트 스킵:', e)
    try:
        if check_claude_failover() != 0:   # claude -p 호출 = 폴오버 SSOT 경유 통일(자체 쿼터처리·따로놀기 차단 · 260629 weekly한도 전건실패)
            rc = 1
    except Exception as e:
        print('⚠️ claude 폴오버 게이트 스킵:', e)
    try:
        if check_judge_bare() != 0:   # judge = OAuth 전용 → --bare 금지(OAuth 안 읽어 인증 즉사 = 260701 사고 진짜원인) · --safe-mode만 · 생성경로 --bare 기본 ON도 차단
            rc = 1
    except Exception as e:
        print('⚠️ --bare 도구충돌 게이트 스킵:', e)
    try:
        if check_face_bg() != 0:   # 얼빡 배경 차단(하드 게이트 — 두 번 샌 사고: 5인 _face01 + 세라 sera_k01 · 운영자 260726 「얼빡은 배경에 깔지마」)
            rc = 1
    except Exception as e:
        print('⚠️ 얼빡 배경 게이트 스킵:', e)
    try:
        if check_autocomplete() != 0:   # 평문 텍스트칸 OS 자동완성 끔 4종(하드 게이트 — 자동완성 바 재발 차단·STAGE1b·260628)
            rc = 1
    except Exception as e:
        print('⚠️ check_autocomplete 스킵:', e)
    try:
        check_x_char()   # 닫기/삭제 × 문자 → SVG 권장(WARN-only·병렬작업 파일 비차단)
    except Exception as e:
        print('⚠️ check_x_char 스킵:', e)
    try:
        if check_claude_anchors() != 0:   # CLAUDE.md §<이모지> 앵커 해소(하드 — Q.20 승격 260717 · 백로그 0 상태에서 신규 dangling = 즉시 차단)
            rc = 1
    except Exception as e:
        print('⚠️ check_claude_anchors 스킵:', e)
    try:
        if check_tokens_link() != 0:   # 공유 구조토큰 tokens.css 4뷰어 링크(하드 게이트·§🎨 STAGE3·260628)
            rc = 1
    except Exception as e:
        print('⚠️ check_tokens_link 스킵:', e)
    try:
        if check_soremeori() != 0:   # 소머리(구분자 •) 텍스트 흰색·블릿 형광·토큰(하드 게이트 — 회색/무블릿/리터럴 재발 차단·§📐·260629)
            rc = 1
    except Exception as e:
        print('⚠️ check_soremeori 스킵:', e)
    try:
        check_guideline_log()   # 지침 축 변경 시 지침변경로그.md 동반 갱신 리마인더(WARN-only · 운영자 260714)
    except Exception as e:
        print('⚠️ 지침 변경 로그 게이트 스킵:', e)
    try:
        check_safety_lock()   # 콘텐츠 거절 가드레일(SAFETY-LOCK 앵커) 약화·소실 트립와이어(WARN-only · 운영자 260714)
    except Exception as e:
        print('⚠️ SAFETY-LOCK 게이트 스킵:', e)
    try:
        check_root_clean()   # 루트 잡파일 재오염 리마인더(WARN-only · 운영자 260726 "게이트 ㄱㄱ" · Q.97 — 웹 업로드 착지점이 루트라 또 쌓인다)
    except Exception as e:
        print('⚠️ 루트 청결 게이트 스킵:', e)
    try:
        import build_menu_kit   # 포터블 메뉴킷 신선도(WARN-only · Q.14 260717) — 정본 코어(:root/.ynav/.ydock) 변경 시 재추출 리마인더(이식 사본이라 비차단)
        build_menu_kit.check()
    except Exception as e:
        print('⚠️ 메뉴킷 신선도 게이트 스킵:', e)
    try:
        if check_world_rate() != 0:   # 무음동 세계율 6배 3점 짝(하드 게이트 — 한쪽만 수정 = 지도·대화 시간축 재분열 · Q.08 평의회)
            rc = 1
    except Exception as e:
        print('⚠️ 세계율 게이트 스킵:', e)
    try:
        if check_model_ids() != 0:   # 모델 ID 드리프트(하드 — 승격 시 '한 곳 빠뜨림' 봉쇄 + 벤더 계열 드리프트 · 정본 shared/models.json · 승격기 = apply_models.py · 운영자 260725 이식)
            rc = 1
    except Exception as e:
        print('❌ check_model_ids 예외(fail-closed):', e); rc = 1
    try:
        if check_map_bg_pair() != 0:   # 지도 배경↔도로 좌표 짝(하드 게이트 — 배경 재생성 = 좌표 침묵 실효 차단 · Q.08 평의회9)
            rc = 1
    except Exception as e:
        print('⚠️ 지도 배경 짝 게이트 스킵:', e)
    try:
        import ledger   # 원장 번호 중복(하드 게이트 260726 — 세션 여럿이 같은 번호를 각각 쓰면 이력 추적이 끊긴다 · 다음 번호 = python3 shared/ledger.py)
        if ledger.check() != 0:
            rc = 1
    except Exception as e:
        print('⚠️ 원장 번호 게이트 스킵:', e)
    return rc


if __name__ == '__main__':
    sys.exit(main())
