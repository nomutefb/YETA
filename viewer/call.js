// call.js — yeta 음성 모듈: 걸려오는 전화 수신 + 무전기(PTT) + 프리미엄 배지 (플러그인 · 260704 · CLAUDE.md §🗺 yeta-call 항목이 정본)
//
// [설치 = index.html 훅 · 제거 = 훅 삭제(본체 무손상 = 붙였다 뗄 수 있는 모듈)]
//   ① <script src="call.js" defer></script>            (본체 스크립트 뒤 — 전역 yApi/esc/yAva/YCHARS 계승)
//   ② yLoad()의 `YSESS = r.sess` 직후 1줄:  if (window.YCALL) YCALL.onSess(YSESS);
//   ③ (선택) 캐릭터 이름 옆 프리미엄 배지 = 템플릿에 `window.yPremBadge ? yPremBadge(c) : ''` — 모듈 제거 시 자동 소멸
//   본체 전역이 없으면(다른 페이지에 실수 로드) 모듈은 스스로 비활성(no-op).
//
// [서버 계약 — yeta_call.sh · yeta_chat.sh(ptt_voice) · functions/api/yeta.js]
//   sess.call = {ts, persona, text, voice}  (voice = 비공개 R2 키 'voice/….mp3' · ''=무음 전화)
//   답장 턴.voice = 무전기 답장 음성 키(텍스트 반영 후 수 초 뒤 부착 — "무전기 수신" 페이스)
//   음성 재생 = POST api/yeta {op:'voice', key}  → audio/mpeg 스트림(동일출처 게이트)
//   무전 STT 폴백 = POST {op:'stt', audio:<base64>} → {text} (Workers AI Whisper · 미설정 501)
//   무전 전송 = {op:'send', text, model:'claude-sonnet-5', effort:'low', ptt:1} — 낮은 모델 = 응답속도(운영자 요구)
//   전화 요청 = {op:'ring'} · 실전화(PSTN) = {op:'phone'} · 보이스톡 공개키 = {op:'vapikey'}
//   보이스톡 = 헤더 수화기(모듈 주입) → 벨 연출 → 받기 → Vapi Web SDK(esm.sh 동적 import) 실시간 통화 —
//     assistant = roster "phone" 재사용(PSTN과 동일 배선) · ⚠️분당 과금 = 발신 확인 화면 [통화] 재확인(260731 · 구 2탭 무장) · 키는 Pages env(Origins 제한 권장)
//
// [소비 규약 — 기틀 CLAUDE.md §🗺]
//   seen = localStorage 'yeta_call_seen'(ts) — call.ts ≤ seen = 무시(기기별 각자 울림 = 자연스러움)
//   신선도 TTL 120s — 지난 call 은 조용히 부재중 처리(대사는 이미 챗 로그에 있음) · 벨 타임아웃 45s
//   자체 폴 20s — 문서 visible + 챗 폴(_yPoll) 비활성일 때만(이중 폴 방지 · 메인 화면에서도 울림)
//   무전 STT = Web Speech(ko-KR·무료·즉시) → 불가 환경(⚠️ iOS 설치형 PWA 실측 260704)은 MediaRecorder→op stt → 그마저 없으면 타이핑
//   벨소리 = WebAudio 합성(에셋 0) — 첫 제스처 후에만 소리(자동재생 정책) · 진동 = 항상 시도
//   답장 음성 자동재생 = WebAudio(제스처로 unlock 된 컨텍스트 = 자동재생 정책 통과) · <audio> 폴백
//
// [디자인 — 절대명령#1 계승] 값 = :root 토큰만(신규 토큰 0) · 컴포넌트 = CII 계승:
//   dialog 결 = #yetadlg(글래스 엣지·::backdrop·모바일 margin:auto 교정) · 아바타/이름/태그 = .yintro-*
//   받기/거절 = .yeta-send 원형 CTA 스펙 계승(크기만 토큰 조합 확대) · 마이크 = .yeta-send 스펙·무채 글래스 플레이트
//   눌림 = --press-m · 파동 링/녹음 점멸 = 키프레임(안무 raw 예외) · 배지 = --r-pill + accent 12%(.dlbtn 결)
//   수화기·마이크·파형 아이콘 = SVG 단일 path(거절 = 같은 path 회전 135° — "같은 의미 = 같은 path")
(() => {
'use strict';
if (typeof window === 'undefined') return;

const SEEN_KEY = 'yeta_call_seen';
const RING_TTL = 120000;      // 이 안에 도착한 call 만 벨(스테일 = 부재중)
const RING_TIMEOUT = 45000;   // 벨 자동 종료(부재중)
const POLL_MS = 20000;        // 자체 폴(챗 폴 비활성 시 백스톱)

const PHONE = 'M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.9a2 2 0 0 1-.5 2.1L8.1 10a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.9.6 2.9.7a2 2 0 0 1 1.7 2z';
const PHONE_SVG = `<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${PHONE}"/></svg>`;
const MIC_SVG = '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/><path d="M19 11a7 7 0 0 1-14 0"/><path d="M12 18v4"/></svg>';
const WAVE_SVG = '<svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></svg>';

// ── 스타일 주입(토큰만 · 신규 raw = 키프레임 안무·기하 계산·::backdrop[#yetadlg 동값]뿐) ──
const css = `
#calldlg { width:100vw; height:100dvh; max-width:100vw; max-height:100dvh; margin:0; padding:0; border:none; border-radius:0; box-shadow:none;
  background:var(--bg); color:var(--fg); overflow:hidden;
  backdrop-filter:none; -webkit-backdrop-filter:none; }   /* 풀스크린 = #yetadlg(챗) 정본 선언 100% 계승(운영자 260809 "배경을 화면 가득") — 창 테두리·라운드·그림자 폐지 = 캐릭터 배경이 화면 끝까지 · 불투명 bg = 전역 dialog blur 상속 낭비 차단 */
#calldlg::backdrop { background:rgba(0,0,0,.6); }          /* #yetadlg::backdrop 동값 계승 */
.ycall-wrap { position:relative; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:space-between;
  padding:calc(var(--sp-3) + env(safe-area-inset-top)) var(--sp-3) calc(var(--sp-3) + env(safe-area-inset-bottom)); }   /* 풀스크린 전환 = 노치·홈바 회피(safe-area = OS축 raw 예외 · .yeta-h 선례) */
.ycall-bg { position:absolute; inset:0; background-size:cover; background-position:center; }
.ycall-bg::after { content:''; position:absolute; inset:0; background:var(--bg-scrim); }   /* 하단 딤 = 버튼 가독(토큰) */
/* 이름·번호 = 화면 정중앙 못박기(운영자 260809 "화면 중앙에 박으셈") — 상단 정렬 폐지.
   벨/발신 국면은 중앙 절대배치, 통화중(.talk)은 자막(.ycall-line)과 겹치므로 흐름 배치로 복귀.
   .ycall-top 이 흐름에서 빠지면 space-between 이 버튼을 위로 끌어올리므로 버튼은 margin-top:auto 로 바닥 고정. */
.ycall-top { position:absolute; left:var(--sp-3); right:var(--sp-3); top:50%; transform:translateY(-50%);
  display:flex; flex-direction:column; align-items:center; gap:6px; text-align:center; }
#calldlg.talk .ycall-top { position:static; transform:none; padding-top:calc(var(--sp-3) * 3); }   /* 통화중 = 자막 위 흐름 배치(토큰 배수 = .ycall-btns gap 관용구 계승) */
.ycall-status { font-size:var(--fs-label); font-weight:var(--fw-b); color:var(--fg-2); }   /* 사진 위 회색(--mut #8B8F8A)은 밝은 캐릭터 아트에 묻힌다(실측) — 서브텍스트 리프트 토큰(--fg-2)으로 계단 이동(위계 유지·새 값 0 · 운영자 260809 "이 톤 배경에서 회색이 안 보인다") */
/* 파문 = 이름 기준(운영자 260809 "가운데 얼굴 삭제 · 은은하게 퍼져나가는 것만 그 아래 이름 기준으로") — 배경이 이미 그 캐릭터 얼굴이라 중앙 프사 = 얼굴 위 얼굴(중복).
   프사(.ycall-ava)만 걷고 파문 선언·키프레임은 글자 하나 안 바꾸고 #ycallName 으로 옮겨 실었다(테두리·인셋·주기·딜레이·정지조건 100% 동일 · 새 값 0). */
/* 35% 확대(운영자 260809 "그거 35% 더 키워서") — 타이포 SSOT(:root)는 건드리지 않고 배율만 곱한다(새 px 하드코딩 0 · 토큰 갱신 0). 파문 인셋도 같은 배율로 따라간다 = 커진 이름과 동심 유지. */
#calldlg .yintro-name { position:relative; font-size:calc(var(--fs-h2) * 1.35); }
#calldlg .yintro-tag { font-size:calc(var(--fs-sm) * 1.35); }
#calldlg #ycallNum { font-size:calc(var(--fs-sm) * 1.35); }
#calldlg .yintro-name::before, #calldlg .yintro-name::after { content:''; position:absolute; inset:calc(var(--sp-2) * -1.35);
  border:1px solid rgba(var(--accent-rgb),.55); border-radius:50%; animation:ycallPulse 2s var(--ease) infinite; pointer-events:none; }
#calldlg .yintro-name::after { animation-delay:1s; }
#calldlg.talk .yintro-name::before, #calldlg.talk .yintro-name::after { animation:none; opacity:0; }
@keyframes ycallPulse { 0% { transform:scale(.92); opacity:.9; } 100% { transform:scale(1.55); opacity:0; } }
@media (prefers-reduced-motion:reduce) { #calldlg .yintro-name::before, #calldlg .yintro-name::after { animation:none; opacity:0; } }
.ycall-line { position:relative; max-width:34ch; background:var(--glass); border:1px solid var(--glass-line); border-radius:var(--r-l);
  backdrop-filter:blur(var(--blur-m)); -webkit-backdrop-filter:blur(var(--blur-m));
  padding:var(--sp-2); font-size:var(--fs-body); line-height:var(--lh-base); }   /* 통화 자막 = 글래스 카드 */
.ycall-line[hidden] { display:none; }
.ycall-line i.yn { font-style:italic; color:var(--fg-2); opacity:.75; }   /* *지문* 이탤릭 = .yb 결 계승 */
.ycall-btns { position:relative; margin-top:auto; display:flex; gap:calc(var(--sp-3) * 3); padding-bottom:var(--sp-3); }   /* margin-top:auto = .ycall-top 절대배치 전환분 바닥 고정(space-between 만으로는 위로 붙음) */
.ycall-act { display:flex; flex-direction:column; align-items:center; gap:8px; }
.ycall-act > span { font-size:var(--fs-xs); color:var(--fg-2); font-weight:var(--fw-b); }   /* 취소·통화 라벨 = .ycall-status 와 같은 처방(사진 위 --mut 묻힘 → --fg-2) */
.ycall-btn { width:calc(var(--btn) + var(--sp-3) * 2); height:calc(var(--btn) + var(--sp-3) * 2); border-radius:50%; border:none;
  display:grid; place-items:center; cursor:pointer; touch-action:manipulation; }   /* .yeta-send 원형 CTA 스펙 계승(토큰 조합 확대) */
.ycall-btn:active { transform:scale(var(--press-m,.9)); }
.ycall-btn.take { background:var(--accent); color:var(--bg); }
.ycall-btn.drop { background:var(--danger); color:var(--fg); }
.ycall-btn.drop svg { transform:rotate(135deg); }   /* 거절 = 같은 path 회전(같은 의미 = 같은 path) */
.ycall-act[hidden] { display:none; }
.ycall-mic { flex:none; width:var(--btn); height:var(--btn); align-self:center; border-radius:50%;
  border:none; background:none; color:var(--fg-2);
  display:grid; place-items:center; cursor:pointer; touch-action:manipulation; }   /* 무전 마이크 = 픽토그램-온리·무채(운영자 260705 #9 강조색 빼기) · 도형 제거 · 입력행 좌측 · 중앙정렬 */
.ycall-mic:active { transform:scale(var(--press-m,.9)); }
.ycall-mic svg { width:22px; height:22px; }   /* 전송 버튼과 동일 크기(#5) */
.ycall-mic.rec { color:var(--danger); animation:ycallRec 1.2s ease-in-out infinite; }   /* 녹음 = 픽토 danger 점멸(도형 없음) */
@keyframes ycallRec { 0%,100% { opacity:1; } 50% { opacity:.55; } }
@media (prefers-reduced-motion:reduce) { .ycall-mic.rec { animation:none; } }
.yprem { display:inline-flex; align-items:center; gap:6px; margin-left:6px; padding:1px 8px; border-radius:var(--r-pill);
  background:var(--accent); border:1px solid var(--accent); color:var(--bg);
  font-size:var(--fs-xs); font-weight:var(--fw-b); vertical-align:middle; white-space:nowrap; box-shadow:0 0 7px rgba(var(--accent-rgb),.45); }   /* 보이스 = 라임네온 솔리드 칩(운영자 260708 "라임네온" · 아웃라인 라임 링과 겹침 해소 = 솔리드 칩↔링 대비 · gap 6 = 배지 통일) */
#yetaCallBtn { width:var(--btn); height:var(--btn); flex:none; display:grid; place-items:center; background:none; border:none; color:var(--fg-2); cursor:pointer; touch-action:manipulation; transition:transform .3s var(--ease), color .2s; }   /* 전화·연락처저장 = 픽토그램-온리(감싸는 도형 제거 · 운영자 260705) · 무채 — 마이크/+ 결 · 히트영역 --btn 유지 */
#yetaCallBtn svg { width:19px; height:19px; }
#yetaCallBtn:active { transform:scale(var(--press-m,.9)); }
#yetaCallBtn:focus-visible { outline:none; box-shadow:0 0 0 2px rgba(var(--accent-rgb),.5); border-radius:50%; }   /* 포커스 링 = .tool-x 계승(라임) — UA 흰 사각 아웃라인 차단 */
#yetaCallBtn { position:relative; }
#yetaCallBtn.nophone { color:var(--mut); }   /* 실전화 미배선 캐릭터 = 전화 픽토 mut만(자물쇠 오버레이 폐지 = 운영자 260709 "픽토 유지·자물쇠만 제거") · 탭 = 인앱 걸려오는 전화 폴백 유지 */
#yetaCallBtn.able { color:var(--think); }   /* 바피 연결+친밀도 = 터콰이즈 가능(운영자 260717 · [문자·대화가능]과 통일) */
#yetaCallBtn.slash { opacity:.6; }
#yetaCallBtn.slash::after { content:''; position:absolute; left:5px; right:5px; top:50%; height:2px; background:var(--danger); transform:translateY(-50%) rotate(-32deg); border-radius:2px; box-shadow:0 0 0 1.5px var(--bg); }   /* 미배선(바피 미연결) = 빗금(운영자 260717) */
/* #yetaFarBtn(원거리 전파 픽토) 제거 — 원거리 개념 폐지(운영자 260717) · 전화 미배선 = #yetaCallBtn.slash 빗금으로 대체 */
#vcfdlg { width:min(340px,92vw); padding:0; border:1px solid var(--glass-line); border-radius:var(--r-modal);
  background:var(--bg); color:var(--fg); box-shadow:inset 0 1px 0 var(--glass-line), var(--shadow-card); }   /* 명함 시트 = #calldlg/#yetadlg 모달 결 계승(글래스 엣지+sheen) */
#vcfdlg::backdrop { background:rgba(0,0,0,.6); }                /* #yetadlg::backdrop 동값 계승 */
@media (max-width:640px) { #vcfdlg { margin:auto; } }           /* 모바일 좌상단 쏠림 교정(#yetadlg 동형) */
.yvcf-wrap { display:flex; flex-direction:column; align-items:center; text-align:center; gap:7px; padding:var(--sp-3); }
.yvcf-wrap > * { animation:yvcfIn .34s cubic-bezier(.22,.61,.36,1) backwards; }   /* 등장 = 쪼개서 stagger(ypickIn 커브 계승) */
.yvcf-wrap > *:nth-child(2) { animation-delay:.05s } .yvcf-wrap > *:nth-child(3) { animation-delay:.1s }
.yvcf-wrap > *:nth-child(4) { animation-delay:.15s } .yvcf-wrap > *:nth-child(5) { animation-delay:.2s }
.yvcf-wrap > *:nth-child(6) { animation-delay:.25s }
@keyframes yvcfIn { from { opacity:0; transform:translateY(8px); } }
@media (prefers-reduced-motion:reduce) { .yvcf-wrap > * { animation:none; } }
.yvcf-nar { font-size:var(--fs-sm); font-style:italic; color:var(--fg-2); opacity:.75; margin-top:var(--sp-2); word-break:keep-all; }   /* *지문* 이탤릭 = .yb i.yn 결 계승 · 프로필과 간격 --sp-2 추가(운영자 260706) */
.yvcf-num { font-size:var(--fs-sm); color:var(--mut); font-variant-numeric:tabular-nums; }   /* 번호 = tabular(.ytime 결) */
.yvcf-desc { font-size:var(--fs-xs); color:var(--fg); line-height:var(--lh-base); max-width:30ch; text-wrap:pretty;
  word-break:keep-all; white-space:pre-line; }   /* 대사 = 발화(--fg) · 크기 75%(15→11 ≈ --fs-xs 계승 · 운영자 260706) · keep-all=음절 잘림 방지 · pre-line=대사 \n = 구 단위 개행 */
.yvcf-steps { display:flex; flex-direction:column; gap:8px; margin-top:var(--sp-2); }
.yvcf-steps[hidden] { display:none; }
.yvcf-step { display:flex; align-items:center; gap:8px; font-size:var(--fs-sm); color:var(--fg); text-align:left; }
.yvcf-stepn { min-width:19px; height:19px; padding:0 6px; border-radius:var(--r-pill); background:var(--accent); color:var(--bg);
  font-size:var(--fs-xs); font-weight:var(--fw-x); display:grid; place-items:center; flex:none; }   /* 단계 번호 = .ylist-badge 정본 동일 선언(강조 CTA축) */
.yvcf-btns { display:flex; flex-direction:column; gap:8px; align-self:stretch; margin-top:var(--sp-2); }
.yvcf-cta { height:var(--btn); border:none; border-radius:var(--r-pill); background:var(--accent); color:var(--bg);
  font:inherit; font-size:var(--fs-label); font-weight:var(--fw-x); cursor:pointer; touch-action:manipulation;
  display:flex; align-items:center; justify-content:center; gap:8px; }   /* 주 CTA = 받기(.ycall-btn.take) accent 플레이트 결 · 알약(--r-pill) */
.yvcf-cta:active { transform:scale(var(--press-l,.95)); }
.yvcf-cta svg { width:17px; height:17px; }
.yvcf-later { height:var(--btn); border:1px solid var(--glass-line); border-radius:var(--r-pill); background:var(--glass); color:var(--fg-2);
  font:inherit; font-size:var(--fs-label); font-weight:var(--fw-b); cursor:pointer; touch-action:manipulation;
  backdrop-filter:blur(var(--blur-m)); -webkit-backdrop-filter:blur(var(--blur-m)); }   /* 보조 = 무채 글래스 플레이트(.ycall-mic 결) */
.yvcf-later:active { transform:scale(var(--press-l,.95)); }
#calldlg.talk .ycall-status { font-variant-numeric:tabular-nums; }   /* 보이스톡 타이머 = tabular(.yb-cap 결) */
/* 발신 번호 = 플로팅 알약(운영자 260809 "스포티파이 블랙 투명도 40 알약에 담아서 흰색") — 배경이 밝은 캐릭터 아트라 --mut 회색 글자는 사진에 묻힌다(실측 #8B8F8A on 베이지 ≒ 1.6:1).
   구성은 .yeta-h(챗 헤더 알약) 정본 그대로: 글래스 틴트 위에 스포티파이 블랙 밑칠 + --glass-line 엣지 + --blur-l + 인셋 하이라이트. 밑칠 알파만 운영자 지시값 .4(헤더는 .75) · padding 1px 8px = .yprem/.ygrade 배지 정본 계승. 명함 시트(.yvcf-num)는 #ycallNum 스코프라 무영향. */
#ycallNum { display:inline-flex; align-items:center; padding:1px 8px; border-radius:var(--r-pill); color:var(--fg);
  background:linear-gradient(var(--glass), var(--glass)), rgba(18,18,18,.4); border:1px solid var(--glass-line);
  backdrop-filter:blur(var(--blur-l)) saturate(1); -webkit-backdrop-filter:blur(var(--blur-l)) saturate(1);
  box-shadow:inset 0 1px 0 var(--glass-line); }
#ycallNum[hidden] { display:none; }   /* display 선언이 UA [hidden]을 이기는 구멍 봉합 — 없으면 수신 화면(번호 없음)에 빈 알약이 뜬다(실측) · .ycall-line[hidden] 선례 계승 */`;

// ── 상태 ──
let dlg = null, cur = null, ringT = 0, vibT = 0, toneT = 0, audio = null, actx = null;
let vapiSdk = null, vapiInst = null, vapiPub = null, vapiSpeed = 0, webTick = 0, webSec = 0;   // 보이스톡(Vapi Web SDK — 운영자 목업 이식 260705) · vapiSpeed = 말 속도 노브(op vapikey 거울 · 0=미설정)
const fmtSec = s => String(s / 60 | 0).padStart(2, '0') + ':' + String(s % 60 | 0).padStart(2, '0');

const seen = () => { try { return +localStorage.getItem(SEEN_KEY) || 0; } catch { return 0; } };
const markSeen = ts => { try { localStorage.setItem(SEEN_KEY, String(Math.max(seen(), +ts || 0))); } catch {} };
const alive = () => typeof yApi === 'function' && typeof esc === 'function';   // 본체 전역 부재 = 모듈 비활성

function ensureCss() {   // 스타일 주입 = 로드 시(입력행 마이크 즉시 스타일) + 콜 생성 시 공용 · 멱등(id 가드) — 옛 버그: ensureDom(콜 때만)에만 있어 마이크가 전화 전까지 기본 버튼(흰 박스)로 렌더됐음(운영자 260705)
  if (document.getElementById('ycallCss')) return;
  const st = document.createElement('style'); st.id = 'ycallCss'; st.textContent = css; document.head.appendChild(st);
}
function ensureDom() {
  if (dlg) return;
  ensureCss();
  dlg = document.createElement('dialog'); dlg.id = 'calldlg'; dlg.setAttribute('aria-label', '걸려오는 전화');
  dlg.innerHTML = `<div class="ycall-wrap">
  <div class="ycall-bg" id="ycallBg" aria-hidden="true"></div>
  <div class="ycall-top">
    <span class="ycall-status" id="ycallStatus"></span>
    <span class="yintro-name" id="ycallName"></span>
    <span class="yintro-tag" id="ycallTag"></span>
    <span class="yvcf-num" id="ycallNum" hidden></span>
  </div>
  <div class="ycall-line" id="ycallLine" hidden></div>
  <div class="ycall-btns">
    <span class="ycall-act"><button type="button" class="ycall-btn drop" id="ycallDrop" aria-label="거절">${PHONE_SVG}</button><span id="ycallDropLbl">거절</span></span>
    <span class="ycall-act" id="ycallTakeWrap"><button type="button" class="ycall-btn take" id="ycallTake" aria-label="받기">${PHONE_SVG}</button><span id="ycallTakeLbl">받기</span></span>
  </div>
</div>`;
  document.body.appendChild(dlg);
  dlg.querySelector('#ycallTake').addEventListener('click', accept);
  dlg.querySelector('#ycallDrop').addEventListener('click', ycallNavClose);
  dlg.addEventListener('cancel', e => { e.preventDefault(); ycallNavClose(); });    // Esc = 거절(백스택 경유)
}
// 본체 navOpen 통합 스택 편입(155차 감사 — 자체 popstate 리스너 = 하드웨어 뒤로 1회에 본체 종료가드와 이중 발화{홈 벨 = 거절+종료팝업 동시 · 챗 위 명함 = 뒤 챗 동반 종료} → 리스너 폐지 · 닫기 = navBack 위임 = popstate 단일 경로. navOpen 부재(독립 배포) = 직접 닫기 폴백).
function ycallNavClose() {
  if (typeof navBack === 'function' && typeof _navStack !== 'undefined' && _navStack.some(l => l.id === 'ycall')) navBack('ycall');
  else decline();
}

// ── 벨 연출(진동 = 항상 시도 · 소리 = WebAudio 합성, 첫 제스처 후에만) ──
document.addEventListener('pointerdown', () => {   // 자동재생 정책 — 제스처 1회로 오디오 컨텍스트 해제
  try { if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === 'suspended') actx.resume(); } catch {}
}, { once: true, capture: true });
function beep(f, at, dur) {
  const o = actx.createOscillator(), g = actx.createGain();
  o.frequency.value = f; o.type = 'sine'; o.connect(g); g.connect(actx.destination);
  g.gain.setValueAtTime(0, at); g.gain.linearRampToValueAtTime(.12, at + .02); g.gain.exponentialRampToValueAtTime(.001, at + dur);
  o.start(at); o.stop(at + dur + .05);
}
function ringFx() {
  const vib = () => { try { navigator.vibrate && navigator.vibrate([500, 250, 500]); } catch {} };
  vib(); vibT = setInterval(vib, 2000);
  const tone = () => { try { if (actx && actx.state === 'running') { const t = actx.currentTime; beep(740, t, .35); beep(880, t + .45, .5); } } catch {} };
  tone(); toneT = setInterval(tone, 2200);
}
function stopFx() {
  clearInterval(vibT); clearInterval(toneT); clearTimeout(ringT); vibT = toneT = ringT = 0;
  try { navigator.vibrate && navigator.vibrate(0); } catch {}
}

// ── 수신 화면 ──
async function open(call) {
  if (!alive() || !call) return;
  ensureDom();
  if (dlg.open && cur && cur.ts === call.ts) return;   // 같은 통화 재진입 = no-op(폴 재트리거 방지)
  cur = call;
  if (typeof YCHARS !== 'undefined' && !YCHARS.length) {   // 메인 화면(챗 미진입)에서 울릴 때 로스터 셀프 로드
    const r = await yApi('chars').catch(() => null);
    if (r && r.ok) YCHARS = r.chars || [];
  }
  const p = (typeof yPersona === 'function' && yPersona(call.persona)) || { name: call.persona || '?', initial: '?' };
  dlg.querySelector('#ycallBg').style.backgroundImage = p.bg ? `url('${p.bg}')` : '';
  dlg.querySelector('#ycallName').textContent = p.name || '';
  dlg.querySelector('#ycallTag').textContent = p.tagline || '';
  dlg.querySelector('#ycallStatus').textContent = '';   // 수신 상태문구 폐지(운영자 260809 "전화가 오고있어 없애고") — 인앱 수신은 실전화(op phone)가 폰 앱으로 울려 화면 자체가 거의 안 뜬다(운영자 실측). 칸은 남긴다 = 발신 '전화를 겁니다'·대기·통화 타이머·에러가 같은 칸을 쓴다
  dlg.querySelector('#ycallLine').hidden = true;
  dlg.querySelector('#ycallNum').hidden = true;   // 발신 화면 잔재(번호) 회수 — 수신은 번호 없이 얼굴·이름만
  dlg.querySelector('#ycallTakeWrap').hidden = false;
  dlg.querySelector('#ycallTake').setAttribute('aria-label', '받기'); dlg.querySelector('#ycallTakeLbl').textContent = '받기';
  dlg.querySelector('#ycallDropLbl').textContent = '거절';
  outStage = 0;   // 발신 흐름 종료 — 같은 dlg 위에 수신이 덮으면 발신 상태 소거
  dlg.classList.remove('talk');
  if (!dlg.open) dlg.showModal();
  if (typeof navOpen === 'function') navOpen('ycall', decline);   // 백스택 등재 — 뒤로 = 거절(등재 콜백 = decline 본체 · 챗 위 벨이면 [ydlg, ycall] 적층 = 뒤로 1회에 벨만)
  stopFx(); ringFx();
  if (call.web) vapiPreload();   // 보이스톡 = 벨 우는 동안 키+SDK 미리 로드(받기 탭 순간 iOS 제스처 소실 회피 = 핵심)
  ringT = setTimeout(() => { if (dlg.open && !dlg.classList.contains('talk')) ycallNavClose(); }, RING_TIMEOUT);   // 부재중(백스택 경유)
}
// ── 음성 재생 유틸(공용) — WebAudio 우선(제스처로 unlock 된 actx = 무전 답장 *자동*재생 허용) · <audio> 폴백 ──
let srcNode = null;
async function fetchVoiceBuf(key) {
  try {
    const r = await fetch('api/yeta', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ op: 'voice', key }) });
    if (r.ok && (r.headers.get('content-type') || '').includes('audio')) return await r.arrayBuffer();
  } catch {}
  return null;
}
function stopVoice() {
  if (srcNode) { try { srcNode.onended = null; srcNode.stop(); } catch {} srcNode = null; }
  if (audio) { try { audio.pause(); } catch {} audio = null; }
}
async function playVoice(key, onended) {
  const buf = await fetchVoiceBuf(key);
  if (!buf) return false;
  try {
    if (actx && actx.state === 'running') {
      const ab = await actx.decodeAudioData(buf.slice(0));
      stopVoice();
      srcNode = actx.createBufferSource(); srcNode.buffer = ab; srcNode.connect(actx.destination);
      srcNode.onended = () => { srcNode = null; onended && onended(); };
      srcNode.start(); return true;
    }
  } catch {}
  try {   // 폴백 — 제스처 문맥(전화 받기 탭)에서는 <audio> 재생 허용
    stopVoice();
    audio = new Audio(URL.createObjectURL(new Blob([buf], { type: 'audio/mpeg' })));
    if (onended) audio.addEventListener('ended', onended);
    await audio.play(); return true;
  } catch {}
  return false;
}

function closeDlg() {
  stopFx(); stopVoice();
  clearInterval(webTick); webTick = 0;
  if (vapiInst) { try { vapiInst.stop(); } catch {} vapiInst = null; }   // 보이스톡 세션 종료(과금 차단)
  cur = null; outStage = 0; if (dlg && dlg.open) dlg.close();
}
function decline() { if (cur && cur.ts && !cur.web) markSeen(cur.ts); closeDlg(); }

// ── 보이스톡(브라우저 실시간 통화) — Vapi Web SDK · 벨 우는 동안 프리로드(iOS 제스처 소실 회피) · 운영자 목업 이식 ──
let vapiPreloading = null;
function vapiPreload() {   // 벨 시점 = 키 fetch + SDK import 백그라운드 완료(받기 탭 땐 await 0 = 제스처 안에서 마이크 즉시)
  if (vapiPreloading) return vapiPreloading;
  vapiPreloading = (async () => {
    try {
      if (!vapiPub) { const r = await yApi('vapikey').catch(() => null); if (r && r.ok && r.pub) { vapiPub = r.pub; vapiSpeed = +r.speed || 0; } }   // speed = Pages env YETA_VOICE_SPEED 거울(0=미설정 = 오버라이드 생략)
      if (!vapiSdk) vapiSdk = (await import('https://esm.sh/@vapi-ai/web')).default;
    } catch {}
  })();
  return vapiPreloading;
}
function webOverrides(call) {   // 말 속도 오버라이드 — 노브 미설정(vapiSpeed 0)이면 undefined = start() 종전 1인자 호출과 동일.
  // Vapi voice = provider 판별 유니온이라 speed 단독 전송 불가 → roster "el:<id>"에서 voiceId 동반(서버 op phone 과 같은 계약).
  const pid = (typeof YSESS !== 'undefined' && YSESS && (YSESS.cur || YSESS.persona)) || '';
  const p = (typeof yPersona === 'function' && yPersona(pid)) || {};
  const v = String(call.voice || p.voice || '');
  if (!vapiSpeed || !v.startsWith('el:')) return undefined;
  return { voice: { provider: '11labs', voiceId: v.slice(3), speed: vapiSpeed } };
}
async function webAccept(call) {
  const st = dlg.querySelector('#ycallStatus');
  let stage = 'load', ended = false;
  const fail = m => { if (ended) return; ended = true; st.textContent = '연결 실패 — ' + m; setTimeout(ycallNavClose, 3000); };
  const guard = setTimeout(() => fail(stage === 'mic' ? '마이크 권한을 확인해줘' : '닿지 않아 — 잠시 후 다시'), 20000);   // 무한 '연결 중' 차단
  try {
    // ① 마이크 먼저 — 받기 탭 제스처 안에서 동기적으로 잡아야 iOS 가 hang 안 함(제스처 소실 방지의 핵심)
    stage = 'mic'; st.textContent = '마이크 여는 중…';
    try { const ms = await navigator.mediaDevices.getUserMedia({ audio: true }); ms.getTracks().forEach(t => t.stop()); }
    catch { clearTimeout(guard); return fail('마이크 권한이 필요해 — 브라우저 설정에서 허용'); }
    // ② 키·SDK — 벨 때 프리로드됐으면 즉시 완료
    stage = 'sdk'; st.textContent = '연결 중…';
    await vapiPreload();
    if (!vapiPub) { clearTimeout(guard); return fail('지금은 통화가 안 열려'); }
    if (!vapiSdk) { clearTimeout(guard); return fail('지금은 통화가 안 열려'); }
    // ③ 통화 시작
    stage = 'start';
    vapiInst = new vapiSdk(vapiPub);
    vapiInst.on('call-start', () => { clearTimeout(guard); ended = true; webSec = 0; clearInterval(webTick); webTick = setInterval(() => { st.textContent = fmtSec(++webSec); }, 1000); });
    vapiInst.on('speech-start', () => { if (webTick) st.textContent = fmtSec(webSec) + ' · 말하는 중…'; });
    vapiInst.on('speech-end', () => { if (webTick) st.textContent = fmtSec(webSec); });
    vapiInst.on('call-end', () => ycallNavClose());
    vapiInst.on('error', e => { clearTimeout(guard); (console.warn('[call]', e), fail('연결이 끊겼어 — 잠시 후 다시'))   /* SDK 원문(영문·기술문)이 통화 화면에 그대로 뜨던 자리 — 진단은 콘솔로(260809 몰입 감사 C) */; });
    await vapiInst.start(call.assistant, webOverrides(call));   // 2인자 = assistantOverrides(말 속도 · 노브 미설정이면 undefined = 종전 호출과 동일)
  } catch (e) {
    clearTimeout(guard); (console.warn('[call]', e), fail('연결이 끊겼어 — 잠시 후 다시'));
  }
}

async function accept() {
  if (!cur) { if (outStage === 1) return outPlace(); return ycallNavClose(); }   // 발신 확인 화면의 [통화] = 실제 발신(수신 cur 없음 축)
  const call = cur;
  stopFx();
  dlg.classList.add('talk');
  dlg.querySelector('#ycallStatus').textContent = '통화 중';
  dlg.querySelector('#ycallTakeWrap').hidden = true;
  dlg.querySelector('#ycallDropLbl').textContent = '끊기';
  const line = dlg.querySelector('#ycallLine');
  if (call.web) { line.hidden = true; return webAccept(call); }   // 보이스톡 = 실시간 대화(자막·mp3 없음)
  markSeen(call.ts);
  line.innerHTML = typeof yFmt === 'function' ? yFmt(call.text || '') : esc(call.text || '');   // 자막(무음 전화 폴백 겸용)
  line.hidden = !call.text;
  const played = call.voice ? await playVoice(call.voice, () => setTimeout(ycallNavClose, 1200)) : false;   // 받기 탭 = 제스처(재생 허용)
  if (!played) setTimeout(() => { if (dlg.classList.contains('talk')) ycallNavClose(); }, 5000);   // 무음 전화 = 자막 5초 후 종료(대사는 챗에 남음)
}

// ── 무전기(PTT) — 마이크 버튼을 입력행에 *주입*(본체 마크업 무수정) · Web Speech → 서버 STT → 타이핑 3단 폴백 ──
const PTT_DIAL = { model: 'claude-sonnet-5', effort: 'low' };   // 낮은 모델 = 응답속도 우선(운영자 요구⑥ · 웜 루프 후속턴 ~10~20s = "무전기 수신" 페이스)
let pttPending = false, lastVoiceTs = Date.now(), voiceWait = 0;
let recOnFlag = false, sr = null, rec = null, recT = 0;
const toast = m => { try { typeof miniToast === 'function' ? miniToast(m) : console.warn(m); } catch {} };

function initPtt() {
  const row = document.querySelector('#yetaIn');
  if (!row || document.querySelector('#yetaMic')) return;
  const b = document.createElement('button');
  b.type = 'button'; b.id = 'yetaMic'; b.className = 'ycall-mic';
  b.setAttribute('aria-label', '무전 — 탭해서 말하기(끝나면 자동 전송)'); b.title = '무전';
  b.innerHTML = MIC_SVG;
  row.insertBefore(b, row.firstChild);
  b.addEventListener('click', () => { recOnFlag ? pttStop() : pttStart(); });
}
function recUi(on, hint) {
  recOnFlag = on;
  const b = document.querySelector('#yetaMic'), ta = document.querySelector('#yetaText');
  if (b) b.classList.toggle('rec', on);
  if (ta) ta.placeholder = on ? (hint || '듣는 중…') : '메시지';
}
function pttStart() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const ta = document.querySelector('#yetaText');
  if (SR) {   // 1순위 = 기기 내장 인식(무료·즉시 · ko-KR)
    try {
      sr = new SR(); sr.lang = 'ko-KR'; sr.interimResults = true; sr.continuous = false;
      let fin = '';
      sr.onresult = e => { let s = ''; for (const res of e.results) { s += res[0].transcript; if (res.isFinal) fin = s; } if (ta) ta.value = s; };
      sr.onerror = ev => { recUi(false); if (ev && ev.error === 'not-allowed') toast('마이크 권한을 허용해줘'); };
      sr.onend = () => { recUi(false); const t = (fin || (ta && ta.value) || '').trim(); sr = null; if (t) pttSend(t); };
      sr.start(); recUi(true, '듣는 중… 말이 끝나면 자동 전송'); return;
    } catch { sr = null; }
  }
  recStart();   // 2순위 = 녹음 → 서버 STT(op stt · iOS 설치형 PWA — Web Speech 불가 실측 260704)
}
function recStart() {
  if (!navigator.mediaDevices || !window.MediaRecorder) { toast('여기선 말로 못 받아 — 적어줘'); return; }
  navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
    const chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop()); recUi(false); clearTimeout(recT);
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' }); rec = null;
      if (blob.size < 1200) return;                       // 빈 탭(실수) 무시
      if (blob.size > 1000000) { toast('너무 길어 — 30초 안으로 말해줘'); return; }
      const b64 = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(',')[1] || ''); fr.readAsDataURL(blob); });
      const r = await yApi('stt', { audio: b64 }).catch(() => null);
      if (r && r.ok && r.text) pttSend(r.text);
      else if (r && r.setup) toast('지금은 말로 못 받아 — 일단 적어줘');
      else toast((r && r.error) || '못 알아들었어 — 다시');
    };
    rec.start(); recUi(true, '녹음 중 — 다시 탭하면 보냄');
    recT = setTimeout(() => pttStop(), 30000);            // 무전 = 짧은 발화(서버 상한과 짝)
  }).catch(() => toast('마이크를 못 열었어 — 권한 확인'));
}
function pttStop() { try { if (sr) { sr.stop(); return; } } catch {} try { if (rec && rec.state !== 'inactive') rec.stop(); } catch {} recUi(false); }
async function pttSend(text) {
  const ta = document.querySelector('#yetaText'); if (ta) ta.value = '';
  pttPending = true; voiceWait = 0;
  const r = await yApi('send', { text, model: PTT_DIAL.model, effort: PTT_DIAL.effort, ptt: 1 }).catch(() => null);
  if (!r || !r.ok) { pttPending = false; toast((r && r.error) || '말이 닿지 않았어'); if (ta) ta.value = text; return; }
  if (typeof yLoad === 'function') yLoad();               // 내 턴 즉시 반영(낙관 버블 대신 확정 렌더 — 이미 R2 반영됨)
  if (typeof yStartPoll === 'function') yStartPoll();
}
function checkReplyVoice(sess) {   // 무전 답장 음성 자동재생 — 텍스트 먼저, 음성 키(turn.voice)는 수 초 뒤 부착
  if (!pttPending) return;
  const turns = (sess && (sess.threads && sess.cur ? (sess.threads[sess.cur] || {}).turns : sess.turns)) || [];   // v3 = 현재 방 스레드(구형 폴백 병행 · 260707)
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    if (t.role === 'user') return;                        // 아직 답장 전(sys 는 스킵하고 계속)
    if (t.role !== 'assistant') continue;
    if (t.voice && t.ts > lastVoiceTs) { lastVoiceTs = t.ts; pttPending = false; playVoice(t.voice); return; }
    // 답장 텍스트는 왔는데 음성 미부착 — 챗 폴은 idle 로 멈추므로 모듈이 짧게 재확인(최대 ~30s)
    if (!t.voice && voiceWait < 12) {
      voiceWait += 1;
      setTimeout(async () => { const r = await yApi('get').catch(() => null); if (r && r.ok) checkReplyVoice(r.sess); }, 2500);
    } else if (voiceWait >= 12) { pttPending = false; }   // 음성 실패(fail-soft) = 텍스트만으로 종료
    return;
  }
}

// ── 프리미엄(전용 음색) 배지 — 본체 템플릿 훅(③): 이름 옆 `yPremBadge(c)` · 모듈 제거 시 자동 소멸 ──
window.yPremBadge = c => (c && c.voice) ? `<span class="yprem" title="이 사람의 목소리">${WAVE_SVG}보이스</span>` : '';

// ── 헤더 수화기 버튼(모듈 주입 · 본체 무수정) ──
// 정책(260705 실측 결정 · 260731 UX 개편 = 2탭 무장 → 발신 확인 화면): phone 배선 캐릭터 = **실전화(op phone)** 발신 = 네 폰이 울림.
//   근거 = Vapi 통화 로그 실측: outboundPhoneCall = 정상 대화(transcript 있음·클론 음색) /
//          webCall(보이스톡) = 'assistant-did-not-receive-customer-audio'(모바일 WebRTC 오디오 미전달) 반복 실패.
//   → 흔들리는 브라우저 통화 대신 증명된 PSTN 로. 보이스톡(open web:1)은 코드 잔존하나 버튼 기본 경로에서 제외.
//   phone 미배선 캐릭터 = op ring 폴백(인앱 걸려오는 전화·첫마디 TTS).
// ── 발신 화면(운영자 260731 "2탭 무장 폐지 — 전화를 겁니다 확인 → [통화] → 기다리는 중") ──
//   확인·대기 화면 = 수신 #calldlg 재사용(같은 의미 = 같은 화면 · 번호 = .yvcf-num 결 · 대기 점 = 본체 .gdots 계승)
let outStage = 0, outReal = false;   // 0=없음 · 1=확인(통화 대기) · 2=발신 후 기다리는 중
async function dialOut() {
  if (!alive()) return;
  ensureDom();
  const pid = (typeof YSESS !== 'undefined' && YSESS && (YSESS.cur || YSESS.persona)) || '';
  const p = (typeof yPersona === 'function' && yPersona(pid)) || { name: pid || '?', initial: '?' };
  outReal = !!p.phone; outStage = 1; cur = null;
  stopFx(); dlg.classList.remove('talk');
  dlg.querySelector('#ycallBg').style.backgroundImage = p.bg ? `url('${p.bg}')` : '';
  dlg.querySelector('#ycallName').textContent = p.name || '';
  dlg.querySelector('#ycallTag').textContent = p.tagline || '';
  const num = dlg.querySelector('#ycallNum'), tel = (VCF[pid] && VCF[pid].tel) || '';
  num.textContent = tel; num.hidden = !tel;   // 번호 배선 캐릭터 = 명함(.yvcf-num) 번호 그대로
  dlg.querySelector('#ycallStatus').textContent = '전화를 겁니다';
  dlg.querySelector('#ycallLine').hidden = true;
  dlg.querySelector('#ycallTakeWrap').hidden = false;
  dlg.querySelector('#ycallTake').setAttribute('aria-label', '통화'); dlg.querySelector('#ycallTakeLbl').textContent = '통화';
  dlg.querySelector('#ycallDropLbl').textContent = '취소';
  if (!dlg.open) dlg.showModal();
  if (typeof navOpen === 'function') navOpen('ycall', closeDlg);   // 뒤로 = 취소(수신 스택과 같은 칸)
}
async function outPlace() {   // [통화] 확정 — 유료 발동은 여기 한 곳뿐(구 2탭 가드의 실발신 차단 역할 승계)
  outStage = 2;
  const st = dlg.querySelector('#ycallStatus');
  st.innerHTML = '전화를 기다리는 중<span class="gdots"><i>.</i><i>.</i><i>.</i></span>';   // gdots = 본체 점 애니 계승
  dlg.querySelector('#ycallTakeWrap').hidden = true;
  dlg.querySelector('#ycallDropLbl').textContent = '닫기';
  const r = await yApi(outReal ? 'phone' : 'ring').catch(() => null);   // 실전화(PSTN) / 미배선 = 인앱 걸려오는 전화 폴백(기존 경로 그대로)
  if (outStage !== 2 || !dlg.open) return;   // 기다리다 닫았거나 수신이 덮음 = 결과 무시
  if (!(r && r.ok)) { st.textContent = (r && r.error) || '전화가 걸리지 않아'; setTimeout(() => { if (dlg.open && outStage === 2) ycallNavClose(); }, 3000); return; }
  clearTimeout(ringT);
  ringT = setTimeout(() => { if (dlg.open && outStage === 2) ycallNavClose(); }, RING_TIMEOUT);   // 벨 대기 상한 뒤 조용히 회수(실전화 = 내 폰이 울리는 중 · 인앱 = 수신 화면이 이 dlg 를 덮음)
}
function initCallBtn() {
  const hr = document.querySelector('#yetadlg .yh-r');
  if (!hr || document.querySelector('#yetaCallBtn')) return;
  const b = document.createElement('button');
  b.type = 'button'; b.id = 'yetaCallBtn';   // 픽토그램-온리(도형 제거 · 운영자 260705) — 스타일 = css의 #yetaCallBtn
  b.setAttribute('aria-label', '통화'); b.title = '통화';
  b.innerHTML = `<svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${PHONE}"/></svg>`;   // 자물쇠 오버레이 폐지(운영자 260709 "픽토 유지·자물쇠만") — 미배선(바피 미연결) = .slash 빗금(운영자 260717)
  hr.insertBefore(b, hr.firstChild);   // 전화 = 우측 끝(헤더 [문자][초대][대화가능][전화] 순 · 원거리 전파 픽토 폐지 260717)
  b.addEventListener('click', dialOut);   // 1탭 = 발신 확인 화면(운영자 260731 — 구 2탭 무장 폐지 · 유료 확정은 화면 안 [통화] 한 곳)
  callBtnSync();   // 생성 직후 초기 상태(실전화 미배선 = mut+락 · 항목8)
}

// ── 연락처 저장(프로필 카드 배포) — 폰 주소록에 사진+번호 원탭 등록 = 실전화 걸려올 때 그 캐릭터 얼굴·이름이 뜨게(운영자 260706) ──
// 소재 = viewer/assets/contacts/<id>.vcf(vCard 2.1 · 사진 base64 임베드 · 번호 = Vapi 발신번호 국제 2표기 — 안드로이드 뒷자리 매칭이 둘 다 잡음).
// 탭 = 같은출처 .vcf 다운로드(a[download]) → 갤럭시 "연락처에 추가"가 이름·사진·번호 프리필 = 저장 한 번이면 끝.
const VCF = { haeun: {   // vcf 보유 캐릭터 — 추가 = vcf 생성 + 이 행(nar=지문·line=대사 = 페르소나 결 · 운영자 260706 문구 — 페르소나 대개편 확정 시 카드와 동기)
  name: '하서연', tel: '+1 240-616-4569',
  nar: '하서연이 폰 번호를 적어서 건넨다',                                // 행동 = 이탤릭 지문
  line: '연락처에 저장하면 이름 뜰거야.\n아직도 저장 안 한건 아니지?',   // 대사 = 잘 삐지는 페르소나 · \n = 구 단위 개행(pre-line 렌더 — 운영자 "쉼표 들어갈 부분 단위")
} };
const VCF_AUTO_KEY = 'yeta_vcf_auto';   // {id: ts} — 명함 시트 자동 노출은 기기당 1회(재오픈 = 헤더 연락처 버튼)
const vcfAutoDone = () => { try { return JSON.parse(localStorage.getItem(VCF_AUTO_KEY) || '{}') || {}; } catch { return {}; } };
function vcfMarkDone(pid) { try { const d = vcfAutoDone(); d[pid] = Date.now(); localStorage.setItem(VCF_AUTO_KEY, JSON.stringify(d)); } catch {} }
function vcfDownload(pid) {   // 같은출처 .vcf — 갤럭시 "연락처에 추가"가 이름·사진·번호 프리필
  const a = document.createElement('a');
  a.href = 'assets/contacts/' + pid + '.vcf'; a.download = VCF[pid].name + '.vcf';
  document.body.appendChild(a); a.click(); a.remove();
}
// ── 명함 시트 — 웹은 주소록 무단 기록 불가·Web Share도 vcf 비허용(Chromium FILE_TYPES 실측 260706) →
//    최대 자동화 = 탭 1회(진입) 시트 자동 노출 + [연락처 받기] 제스처 다운로드 + 남은 2탭을 단계 가이드로 안내 ──
let vdlg = null;
function vcfSheet(pid) {
  const c = VCF[pid]; if (!c) return;
  const p = (typeof yPersona === 'function' && yPersona(pid)) || { id: pid, name: c.name, initial: c.name[0] };
  ensureCss();
  if (!vdlg) {
    vdlg = document.createElement('dialog'); vdlg.id = 'vcfdlg'; vdlg.setAttribute('aria-label', '연락처 저장');
    vdlg.innerHTML = `<div class="yvcf-wrap">
    <span id="yvcfAva"></span>
    <span class="yvcf-nar" id="yvcfNar"></span>
    <span class="yvcf-desc" id="yvcfDesc"></span>
    <span class="yvcf-num" id="yvcfNum"></span>
    <div class="yvcf-steps" id="yvcfSteps" hidden>
      <span class="yvcf-step"><span class="yvcf-stepn" aria-hidden="true">1</span><span>알림에서 방금 받은 <b id="yvcfFile"></b> 열기</span></span>
      <span class="yvcf-step"><span class="yvcf-stepn" aria-hidden="true">2</span><span><b>저장</b> 탭 — 그럼 전화 올 때 얼굴이 떠</span></span>
    </div>
    <div class="yvcf-btns">
      <button type="button" class="yvcf-cta" id="yvcfGet"></button>
      <button type="button" class="yvcf-later" id="yvcfLater">다음에</button>
    </div>
  </div>`;
    document.body.appendChild(vdlg);
    vdlg.addEventListener('cancel', e => { e.preventDefault(); yvcfNavClose(); });   // Esc = 닫기(백스택 경유 — 자체 popstate 폐지 = 본체 종료가드 이중 발화 봉인 · 155차 감사)
    vdlg.querySelector('#yvcfLater').addEventListener('click', yvcfNavClose);
    vdlg.querySelector('#yvcfGet').addEventListener('click', () => {
      const id = vdlg.dataset.pid, done = vdlg.dataset.got === '1';
      if (done) return yvcfNavClose();                                 // 가이드 상태의 [확인] = 닫기(백스택 경유)
      vcfDownload(id);                                                 // CTA 탭 = 제스처 안 다운로드(차단 정책 통과)
      vdlg.dataset.got = '1';
      vdlg.querySelector('#yvcfDesc').hidden = true;
      vdlg.querySelector('#yvcfSteps').hidden = false;
      vdlg.querySelector('#yvcfLater').hidden = true;
      vdlg.querySelector('#yvcfGet').textContent = '확인';
    });
  }
  vdlg.dataset.pid = pid; vdlg.dataset.got = '';
  vdlg.querySelector('#yvcfNar').textContent = c.nar;
  vdlg.querySelector('#yvcfAva').innerHTML = typeof yAva === 'function' ? yAva(p, 'yintro-ava') : '';
  vdlg.querySelector('#yvcfNum').textContent = c.tel;
  vdlg.querySelector('#yvcfDesc').hidden = false;
  vdlg.querySelector('#yvcfDesc').textContent = '"' + c.line + '"';   // 대사 = 페르소나 말투(따옴표 = 발화)
  vdlg.querySelector('#yvcfSteps').hidden = true;
  vdlg.querySelector('#yvcfFile').textContent = c.name + '.vcf';
  vdlg.querySelector('#yvcfLater').hidden = false;
  vdlg.querySelector('#yvcfGet').textContent = '연락처 받기';
  if (!vdlg.open) vdlg.showModal();   // 챗(#yetadlg) 위 top-layer = #calldlg 선례
  if (typeof navOpen === 'function') navOpen('yvcf', () => { if (vdlg && vdlg.open) vdlg.close(); });   // 백스택 등재 — 챗 위 명함이면 [ydlg, yvcf] 적층 = 뒤로 1회에 명함만(뒤 챗 동반 종료 봉인)
}
function yvcfNavClose() {
  if (typeof navBack === 'function' && typeof _navStack !== 'undefined' && _navStack.some(l => l.id === 'yvcf')) navBack('yvcf');
  else if (vdlg && vdlg.open) vdlg.close();
}
// 자동 노출 — 보이스(전화) 배선 캐릭터를 *탭해 진입한* 첫 1회, 챗이 열린 뒤 명함 시트(운영자 260706 "눌렀을 때 자동" + UIUX).
document.addEventListener('click', e => {
  const el = e.target && e.target.closest && e.target.closest('.ycd-cta[data-id], .ypick-row[data-id], .ys-row[data-id]');
  if (!el || !VCF[el.dataset.id] || vcfAutoDone()[el.dataset.id]) return;   // 진입 경로(대화 시작 CTA·뽑기·대화목록)만 · 기기당 1회 가드
  const pid = el.dataset.id; vcfMarkDone(pid);
  setTimeout(() => vcfSheet(pid), 700);   // 챗 진입 애니 자리 잡은 뒤(시트 = top-layer라 순서만 보장하면 됨)
}, true);
// 캐릭터 디테일(.ycd) 연락처 교환 = index.html `.ycd-sub`(직접 .vcf 내비 = iOS 연락처 시트/Android 열기 자동) 단일화 — call.js 중복 주입(vcfSheet 경유 = a[download] 저장만) 폐지(운영자 260708)
// 헤더 연락처 버튼(#yetaVcfBtn) 폐지 = 운영자 260709 "연락처 등록 = 프로필로" — 캐릭터 디테일 .ycd-sub(연락처 교환하기)가 단일 정본 · 첫 진입 자동 명함 시트(vcfSheet)는 존치
function callBtnSync() {   // 전화 픽토 페르소나별 상태(운영자 260717 재편 — 원거리 전파 픽토 폐지) · 바피 연결(p.phone)+친밀도 = 터콰이즈 able / 미연결 = 빗금
  const pid = (typeof YSESS !== 'undefined' && YSESS && (YSESS.cur || YSESS.persona)) || '';
  const p = (typeof yPersona === 'function' && yPersona(pid)) || {};
  const b = document.querySelector('#yetaCallBtn'); if (!b) return;
  const wired = !!p.phone;   // 바피(전화) 연결 상대(예: 서연)에 한함 — 미연결 = 빗금
  const ok = wired && (typeof yTalkGate !== 'function' || yTalkGate(p).phone);   // 친밀도·거리 게이트(index yTalkGate — 2단계 배선 · 부재 시 배선여부만)
  b.classList.toggle('slash', !wired);
  b.classList.toggle('able', !!ok);
  b.classList.toggle('nophone', !wired);   // 기존 CSS(.nophone mut) 호환 유지
}

// ── 감지 — 본체 yLoad 훅(①) + 자체 백스톱 폴(챗 폴 비활성·visible 시만) ──
function onSess(sess) {
  if (!alive()) return;
  callBtnSync();   // 전화버튼 mut+락 상태 갱신(실전화 미배선 = 항목8)
  checkReplyVoice(sess);
  const call = sess && sess.call;
  if (!call || !call.ts || call.ts <= seen()) return;
  if (Date.now() - call.ts > RING_TTL) { markSeen(call.ts); return; }   // 스테일 = 부재중(대사는 챗 로그에)
  if (typeof yPrefOn === 'function' && !yPrefOn('call', true)) { markSeen(call.ts); return; }   // 설정 '걸려오는 전화' OFF = 벨 없이 부재중 처리(대사는 챗 로그에 · 운영자 260709 설정 실동작)
  open(call);
}
async function check() {
  if (!alive() || document.visibilityState !== 'visible') return;
  if (typeof _yPoll !== 'undefined' && _yPoll) return;   // 챗 적응형 폴이 도는 중 = yLoad 훅이 감지(이중 폴 방지)
  const r = await yApi('get').catch(() => null);
  if (r && r.ok && r.sess) onSess(r.sess);
}
setInterval(check, POLL_MS);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') setTimeout(check, 600); });   // 푸시 탭 복귀 = 즉시 픽업
setTimeout(check, 1500);   // 첫 로드(딥링크 /?yeta=main&call=1 포함) — 기존 ?yeta= 오픈에 편승 + 벨은 여기서
const initInject = () => { ensureCss(); initPtt(); initCallBtn(); };   // 스타일 주입 먼저(마이크 즉시 스타일) + 입력행 마이크 + 헤더 수화기(전부 모듈 주입 = 본체 무수정) · 연락처 = 디테일 .ycd-sub 단일 정본(헤더 버튼 폐지 260709)
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initInject); else initInject();

window.YCALL = { onSess, open, playVoice, sync: () => { callBtnSync(); } };   // open/playVoice = 테스트 훅 · onSess = 본체 yLoad 훅 계약 · sync = 방 전환(yApply) 즉시 수화기 상태 동기(260709)
})();
