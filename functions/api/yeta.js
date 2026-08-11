// Cloudflare Pages Function — yeta 캐릭터 챗 게이트웨이 (260707 v3 · 캐릭터별 다중 채팅방 + 다이얼 + 프리웜)
// 세션 = sessions/main.json 단일 R2 객체 안에 캐릭터별 스레드(threads[<id>]) — 방 = 캐릭터 · 신설 = draw 단일 경로(로스터 대조·캡 12) · 쓰기 = etag CAS(casPut).
//   op 추가: pin {t,on} = 채팅방 고정 토글 · reset {t} = 그 방만 나가기(t 無 = 전체 초기화) · 스레드 op(send/retry/invite/kick)는 {t} 동봉(미지정 = cur).
// ops(POST 단일 — 폴링도 POST = originOk 대칭):
//   chars {}                       : 페르소나 로스터(apps/yeta/characters/roster.json raw · 5분 캐시)
//   get   {}                       : 세션 반환(뷰어 폴) — lazy 리퍼 + 휘발·재합류 스위프(Q.06: 무음동 6일=현실 24h 지난 턴 롤링 삭제 · 1명 남은 g방은 1:1로 병합)
//   watch {e, de}                  : 롱폴 감시(대화 속도 260714) — R2 etag 1s head 감시 · 변경 즉시 {changed}(뷰어가 get 재조회 = 픽업 ~0s) · 15s 무변경 = {none}(클라 재발사) · draft 변경 = 본문 동봉
//   send  {text, model, effort, sc?} : 유저 턴 append(다이얼 턴별 박제 · 화이트리스트 · sc=상황 설명 턴[260714 '#' — 대화 아님·장면 설정]) → yeta-chat.yml dispatch
//   draw  {persona, name}          : 페르소나 뽑기/재뽑기 — sess.persona 갱신(+대화 중이면 sys 턴) · room=[persona] 리셋(단톡 해산)
//   invite {persona, name}         : 합석 초대(단톡 · 정원 MAX_ROOM) — 원본 1:1 보존, 직전 3주고받기 시드 복사해 새 단톡 스레드(g 접두)로 분기 → cur 전환 + dispatch(수락/거절 = 러너 판정)
//   kick  {persona, name}          : 합석 내보내기/초대 철회 — room 제거·invite 취소 + 퇴장 sys · 1명 남은 g방 = 즉시 1:1 재합류(mergeBackG · Q.06) · 병합이 pending 인계 시에만 dispatch 1회(그 외 dispatch 없음)
//   focus {t}                      : 스레드 포커스 전환(단톡 등 페르소나 아닌 방 진입 — draw 없이 cur만 이동)
//   warm  {}                       : 프리웜 — dispatch만(러너 선부팅 → 첫 답장 30초 목표 · 쿼터 소비 0[NOPENDING 웜대기])
//   retry {t?, n?}                 : 자동 재시도(뷰어 260714 무배너) — 실패(state=error) pending 유저 턴 재발사(새 턴 추가 X) · n = 회차(1~2 그대로 · 3~4 러너가 뉘앙스 전환 · 5회차는 뷰어가 발사 안 함 = 이탈)
//   attach {t?, img, model, effort}: 사진 첨부(운영자 260717 '+') — base64 JPEG(≤~1.4MB · 매직바이트 검증) → R2 att/<t>/<ts>.jpg 저장 + img 유저 턴 적재 + dispatch(러너 Read 비전) · 일 상한 기본 30(YETA_ATT_MAX_PER_DAY)
//   att   {key}                    : 첨부 사진 서빙 — 비공개 버킷 att/ 만(voice 동형 · 동일출처 게이트)
//   ring  {persona?}               : 걸려오는 전화 요청 → yeta-call.yml dispatch(⚠️ TTS 유료 → 일 상한 기본 3 · YETA_CALL_MAX_PER_DAY)
//   voice {key}                    : 통화 음성 스트림 — 비공개 버킷 voice/ 만(대사=대화 내용 → 공개 버킷 금지 · 동일출처 게이트)
//   stt   {audio}                  : 무전기 STT 폴백(base64 webm/ogg → 텍스트) — iOS 설치형 PWA 는 Web Speech 불가(실측 260704)
//                                    → Workers AI Whisper(env.AI 바인딩 게이트 · 미설정 501 = 뷰어가 타이핑 폴백 안내)
//   phone {}                       : ☎️ 실전화(PSTN·Vapi) 스캐폴드 — 등록 번호로 실제 발신(⚠️분당 과금 · env 3종 게이트 · 말 속도 = YETA_VOICE_SPEED)
//                                    → 일 상한 = **L1 관리자 토글**(policy.json L1.limits[phonecap] · 3회/10회/무제한 · 기본 3 · env YETA_PHONE_MAX_PER_DAY = 문서 미로드 폴백)
//   vapikey {}                     : 보이스톡(브라우저 통화 · Vapi Web SDK) 공개키 — env VAPI_PUBLIC_KEY(공개 축 · Origins 제한 권장) + speed(말 속도 노브 거울)
//   calllog {}                     : 🩺 통화 진단 — Vapi 메타데이터만(상태·종료사유·비용 — transcript/PII 반환 금지)
//   tune  {persona, g[16]}         : 캐릭터 성향 게이지(L2 · 숫자 배열만 = 프롬프트 주입 차단)
//   me    {call, about}            : 유저 프로필(호칭+소개 · "AI가 나를 부르는 법") — 전 방 공유 · stripMarkers(고정점)+캡(러너가 비신뢰 격리 주입) · 서버 관리 필드(avatar) 보존
//   meface {}                      : 내 캐릭터 그리기(260710 · 3컷 시트 260803) — 소개 기반 **한 장** dispatch(yeta-meface.yml → 얼굴 칸 = me.avatar · 시트 원본 = me.sheet 주입 · ⚠️ OpenAI 유료 → 일 상한 기본 2 = YETA_MEFACE_MAX_PER_DAY · 클라 텍스트 0)
//   pinset {old, next}             : 게스트 PIN 셀프 변경(260710 · R2 재설계) — 비공개 R2 auth/overrides.json {원래해시:새해시} CAS(main 커밋 무유발) · auth가 effectiveHash 대조 = 원래 PIN 무효화 · 새 PIN 4자리(언락 패드 일치) · 시도 상한 기본 5 = YETA_PINSET_MAX_PER_DAY(실패도 소비)
//   policy {} | {p, pin}           : 3계층 정책 — GET 정의+현재값(무인증) / SET enum 정수만(⚠️ 관리자 PIN 필수)
//   auth  {pin}                    : PIN 로그인 — admin = env YETA_PIN_ADMIN(레포 무노출) / guest = apps/yeta/users.json 해시(깃 SSOT)
//   reset {}                       : 세션 초기화(페르소나도 비움 → 재뽑기 · tunes/policy/me 승계)
// 저장 = R2 비공개 버킷 바인딩 env.YETA_R2 (⚠️ 대화는 public 레포 커밋 절대 금지 — 계획안 D2).
// 게이트: 무인증 공개(originOk=CSRF만 · Access 미부착) · 채팅 상한 없음(운영자 260706 폐지 — quota 카운터는 관측용, 소비처 없음·후속 users.cap 연동 후보) · 유료 축(ring/phone + 키미 다이얼 = 문샷 종량제 실비)만 일 상한(키미 = Q.40 260723).
//         ⚠️ 상한 노브의 위치가 축마다 다르다 — phone(바피 실전화) = **L1 관리자 토글**(policy.json · 260808) / ring·meface·pinset·키미 = 여전히 Pages env 단독.
// env: GH_TOKEN(Actions write) · YETA_R2(R2 바인딩) · YETA_PIN_ADMIN(슈퍼관리자 PIN — 설정 SET 강제) · YETA_CALL_MAX_PER_DAY(선택·기본 3 — 유료 TTS 가드)
//      AI(선택 · Workers AI 바인딩 = op stt) · VAPI_API_KEY+VAPI_PHONE_ID+YETA_PHONE_TO(선택 3종 = op phone · 번호는 시크릿 — 코드 박제 금지)
//      YETA_PHONE_MAX_PER_DAY(선택·기본 3 — 실전화 분당 과금 가드 **폴백**: 260808부터 실값은 L1 토글 phonecap 이 정하고, 이 env 는 정책 문서를 못 읽을 때만 쓰인다) ·
//      YETA_KIMI_MAX_USD_PER_DAY(선택·기본 2 — 키미 종량제 일일 실비 방파제 USD · 0=무제한 · Q.40)
//      YETA_VOICE_SPEED(선택·기본 미설정=오버라이드 없음 — 바피 통화 말 속도 0.7~1.2 · 1 미만 = 느리게 · phone/vapikey 공용 · 260808).
const REPO = 'muteno/yeta';
const ID_RE = /^[a-z0-9_-]{1,24}$/;
// ── 신당 「빌어줄 이」 후보·확률 SSOT(운영자 260811 "확률은 페르소나랑 친밀도 이런거에 다 영향받는거 알지? 거리 등") ──
//   신당은 비는 자가 목숨을 거는 자리라(op pray 실패 = 사망) 대개 아무도 오지 않는다. 그 「올 확률」을 여기 **한 곳**에서만 계산한다 —
//   소비처 = op praycands(선택 박스에 % 표시) + op praybeg(실제 굴림). 두 곳이 각자 계산하면 화면의 숫자와 실제 확률이 조용히 갈라진다.
const SHRINE_HOP = { yun: 2, desk: 3, baek: 4, kopi: 4, lucy: 4, reze: 4, seyeun: 4, haeun: 5, sera: 5, von: 7 };   // 거처(home_*) → 성당 홉 · places.json neighbors BFS 실측(무방향) · 짝 검증 = shared/check_refs.py 「신당 거리 짝 게이트」
const PRAY_P = w => Math.min(0.45, Math.max(0.08, 0.06 + 0.035 * w));   // 가중 → 올 확률(8~45%) · 「자주 실패」(운영자 260811)의 근거 = 목숨값
function prayCands(s) {   // 만난 적 있고 · 살아 있는 사람만. 반환 = [{id, w, p}] 확률 내림차순
  const out = [];
  for (const [p, t] of Object.entries(s.threads || {})) {
    if (p.startsWith('g')) continue;                                                    // 단톡 방 = 사람이 아님
    const ut = (((t || {}).turns) || []).filter(x => x && x.role === 'user').length;
    if (!ut) continue;                                                                  // 만난 적 없는 사람은 나를 위해 빌러 가지 않는다
    const dv = (s.dead || {})[p];
    if ((((dv && dv.t) || +dv || 0)) > Date.now()) continue;                             // 죽어 있는 사람은 못 빈다
    const g = ((s.tunes || {})[p]) || [];
    const ax = i => (Array.isArray(g) && typeof g[i] === 'number' ? g[i] : 5);           // 16축 미설정 = 중립 5(축 순서 = 뷰어 TUNE_AX·러너와 짝)
    let w = 1;
    w += 2.6 * Math.min(3, (((s.pray_bond || {})[p] || {}).n) || 0);                     // ① 은혜 = 내가 살려낸 적 있는 사람(최대 성분 · 3회 포화 = 한 사람 독점 차단)
    w += 0.6 * Math.min(3, ut / 10);                                                     // ② 친밀도 = 내가 그 방에 쏟은 말 수(10마디 = 1점 · 3점 포화)
    w += 0.14 * (ax(4) + ax(5) + ax(6) - ax(11));                                        // ③ 페르소나 = 친절도+온기+인내심−경계심(16축)
    w += 0.35 * Math.max(0, 7 - (SHRINE_HOP[p] != null ? SHRINE_HOP[p] : 5));            // ④ 거리 = 거처가 성당에서 몇 홉(윤 2 = 가깝다 ↔ 폰 7 = 멀다 · 미등재 = 중앙값 5)
    w = Math.max(0.05, w);
    out.push({ id: p, w, p: PRAY_P(w) });
  }
  return out.sort((a, b) => b.p - a.p);
}
const KEY = 'sessions/main.json';
const MAX_ROOM = 2;                 // 합석 정원(나 제외 캐릭터 수 · 운영자 260707 "한 명 정도는") — 3 확장은 실험 축
const INVITE_TTL = 600000;          // 초대 pending 10분 — 러너 사망 시 스테일 마커가 다음 초대를 영구 차단하지 않게
const RD_MAX = 1;                   // 리퍼 자동 재발사 상한(운영자 260725) — 러너 사망으로 증발한 답을 대신 한 번 눌러준다. 1인 이유 = 재발사분도 죽으면 원인이 일시장애가 아니라 계정·쿼터·코드 쪽이라 더 쏴봐야 쿼터만 태운다(뷰어 yAutoRetry 4회가 별도로 앞단에 있다)
const FREEZE_MAX_MS = 10800000;   // 난입 정지 안전벨트(260728) — 현실 3시간. 넘기면 난입자를 강제 퇴장시키고 세계 시계를 재개(방치로 앱이 영구히 잠기는 것 차단 · 0으로 두면 무제한)
const EXPIRE_MS = 86400000;         // 대화 휘발 TTL(운영자 260716 Q.06) — 무음동 6일 = 현실 24h(세계 시계 6배 가속: 실제 4h=하루 → 6일이 현실 하루와 정확히 맞아떨어져 7일[28h] 대신 채택)
const josa = (s, a, b) => { const c = String(s || '').charCodeAt(String(s || '').length - 1); return c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 > 0 ? a : b; };   // 받침 → 을/은, 무받침 → 를/는
const MODELS = new Set(['claude-opus-5', 'claude-sonnet-5', 'k3', 'kimi-k2.5']);   // §기틀 정확 ID — 집합 확장은 운영자 확인(k3 = 260719 · kimi-k2.5 = 260721 승인이나 문샷 /anthropic 게이트 404 실측 = 뷰어 미노출·배선 대기[Q.33] · 둘 다 러너 시크릿 KIMI_CODE_MUTE 경유)
const EFFORTS = new Set(['', 'low', 'medium', 'high', 'max']);           // '' = --effort 생략(CLI 기본)
// ── 키미(문샷 종량제 = 유일 실과금 다이얼) 일일 실비 방파제(운영자 260723 Q.40 "대화비용 급증 원인해결") — 유료 축 = 일 상한 규범(ring/phone/meface 동형)의 채팅 편입 ──
//   근거 실측(260723): 문샷 자동 캐시가 실사용 메시지 간격에선 미적중(누적 26턴 i=396,518/cr=64,000 = 히트율 16% · 당일 cr=0) → 고정 몸통 ~15k tok이 매턴 정가($3/M) 재과금 ≈ $0.05/턴.
//   단가 = 뷰어 YCOST 거울(viewer/index.html — 개정 시 양쪽 동조) · 집계 = sess.usage_day(러너 finish가 성공 답장분만 누계 = 하한 지표 → 상한은 방파제, 정본 회계 = 문샷 콘솔) ·
//   클로드(구독 정액) 무영향 · usage 미기록 세션(레거시·계측 실패) = 0 취급 통과(fail-open — 가드는 방파제지 회계가 아님).
const KIMI_COST = { 'k3': [3, 0.3, 15], 'kimi-k2.5': [0.6, 0.1, 3] };   // USD/1M [입력미스, 캐시히트, 출력]
const kimiSpentUsd = (sess) => {   // 오늘(KST) 키미 계열 실비 — usage_day 버킷(뷰어 yKimiCostOf 동형 계산)
  const ud = (sess || {}).usage_day;
  if (!ud || ud.d !== new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '')) return 0;   // 날짜 불일치 = 지난 버킷 = 오늘 0
  return Object.entries(KIMI_COST).reduce((s, [m, r]) => { const v = (ud.m || {})[m]; return v ? s + ((v.i || 0) * r[0] + (v.cr || 0) * r[1] + (v.o || 0) * r[2]) / 1e6 : s; }, 0);
};
// ── 바피 통화 말 속도 노브(운영자 260808 "말이 지나치게 빠르다") — 종전엔 레포가 speed 를 한 번도 안 보내서 조절 지점이 0이었다(대시보드 단독 SSOT) ──
//   ElevenLabs speed 유효범위 0.7~1.2(기본 1.0 · 벗어난 값 = Vapi 400) → 클램프. 1 미만 = 느리게.
//   미설정·0·오타 = 0 = **오버라이드 미부착**(종전 요청 바디와 바이트 동일 = 기본 무위험) → 켜는 건 Pages env 한 줄.
const voiceSpeed = (v) => { const n = parseFloat(v ?? ''); return Number.isFinite(n) && n > 0 ? Math.min(1.2, Math.max(0.7, n)) : 0; };
// ── 바피 실전화 하루 상한 = **L1 관리자 토글 단일 정본**(운영자 260808 "제한을 관리자가 설정할 수 있는 토글로 · 3회 > 10회 > 무제한") ──
//   종전엔 Pages env(YETA_PHONE_MAX_PER_DAY) 한 줄뿐이라 상한을 바꾸려면 클라우드플레어 콘솔을 왕복해야 했다 → 설정 탭 L1 칩으로 회수(yWRate 선례 100% 계승: 실값 = 정책, env·상수는 폴백).
//   해석 = policy.json L1.limits[phonecap] 의 vals[인덱스](저장은 종전대로 enum 정수) · **0 = 무제한**(ring·kimi 가드의 `cap > 0` 관례 그대로).
//   착지 3단(유료 축이 조용히 열리지 않게 전 경로가 유한값으로 착지): ① 세션에 키 있음 = 관리자가 고른 값 ② 없음 = 정책 문서 기본(3회) ③ 문서 미로드·vals 깨짐 = env(폴백) → 그마저 없으면 3.
const phoneCap = async (env, sess) => {
  const f0 = parseInt(env.YETA_PHONE_MAX_PER_DAY ?? '3', 10);
  const fb = Number.isFinite(f0) ? f0 : 3;   // 빈값·오타 = 보수 기본 3(policy.json L1.limits phonecap 기본 = vals[default] 와 동조 — 어긋나면 "토글은 3회인데 실제는 2통"이 된다)
  try {   // vals 매핑 = policy.json 정본(게이트웨이 하드코딩 0 · op policy SET 의 wrate 앵커와 동일 조회 문법)
    const d = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/policy.json`,
      { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 300, cacheEverything: true } });
    if (!d.ok) return fb;
    const j = await d.json();
    const ax = (((j || {}).L1 || {}).limits || []).find(x => x && x.key === 'phonecap');
    if (!ax || !Array.isArray(ax.vals)) return fb;
    const v = ax.vals[Number.isInteger(((sess || {}).policy || {})[ax.key]) ? sess.policy[ax.key] : ax.default];
    return (typeof v === 'number' && v >= 0) ? v : fb;   // 범위 밖 인덱스(SET 클램프 0~7) = undefined = 폴백 흡수
  } catch { return fb; }
};
const kimiGate = (env, sess) => {   // 초과 = 안내 객체(호출부 429) / 미달 = null — send·attach·retry 3경로 공용
  const c0 = parseFloat(env.YETA_KIMI_MAX_USD_PER_DAY ?? '2');
  const cap = Number.isFinite(c0) ? c0 : 2;   // 빈값·오타 = 보수 기본 2(ring 동형) · 0 = 명시적 무제한
  if (!(cap > 0)) return null;
  const spent = kimiSpentUsd(sess);
  if (spent < cap) return null;
  return { error: '오늘 몫이 다 찼어 — 설정에서 대화 깊이를 바꾸면 바로 이어져', edev: `kimi cap $${spent.toFixed(2)}/$${cap} (YETA_KIMI_MAX_USD_PER_DAY · 0=무제한)` };
};
// 클라 텍스트 위장 무력화 SSOT(send/draw/invite/kick/me 공용) — NOTE/MOOD/user_message 파이프 제어토큰 제거.
// ⚠️ 고정점 루프 = 중첩 마커(예 <<N<<NOTE:a>>OTE:PUB>>) 깊이 무관 붕괴(단일패스는 깊이1만 벗김 = 재조립 생존 · 평의회1 260708). 라벨 [^>]* = 유니코드 안전.
// ⚠️ 선캡 8192 = 고정점 루프가 무한장 입력에 O(n²)로 도는 DoS 차단(무인증 게이트웨이 · 평의회1 재검증). send 의미캡 4000의 2배라 정상 입력 무손실 · 각 호출처 최종 캡(24/300/4000)은 뒤에서 적용.
const stripMarkers = (s) => { let x = String(s || '').slice(0, 8192), prev; do { prev = x; x = x.replace(/<<\s*\/?\s*(?:NOTE|MOOD)(?:\s*:[^>]*)?\s*>>/gi, '').replace(/<\/?user_message>/gi, ''); } while (x !== prev); return x; };

export async function onRequestPost({ request, env }) {
  const json = (o, s = 200) =>
    new Response(JSON.stringify(o), { status: s >= 500 ? 424 : s, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
  // ⚠️ 5xx → 424 강등: 커스텀 도메인(soong.kr 존)이 5xx 응답을 자체 에러 페이지("error code: 502")로 덮어
  //    게이트웨이 JSON 에러 사유가 유저에게 소실됨(실측 — pages.dev는 JSON 통과·soong.kr은 생 502).
  //    뷰어(yApi)는 HTTP 코드가 아니라 JSON error/ok/setup 필드만 판독 = 코드 강등 무영향(4xx는 존이 안 덮음).

  if (!originOk(request)) return json({ error: '허용되지 않은 출처' }, 403);
  let body;
  try { body = await request.json(); } catch { return json({ error: '잘못된 요청' }, 400); }
  const op = String(body.op || '');

  // 로스터는 R2 불필요(레포 raw) — 셋업 전에도 목록·안내를 그릴 수 있게 R2 가드보다 앞.
  if (op === 'chars') {
    const r = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,
      { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
    if (!r.ok) return json({ error: `로스터 로드 실패(${r.status})` }, 502);
    let world = null;   // 시즌제 세계관(운영자 260706 롤토체스식 — 성격 불변·역할군 리스킨) — 실패는 비치명(헤더만 생략)
    try {
      const w = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/worlds.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (w.ok) { const j = await w.json(); world = (j.seasons || []).find(s => s.id === j.active) || null; }
    } catch {}
    return json({ ok: true, chars: await r.json(), world, ready: !!env.YETA_R2 });
  }

  // 장소 SSOT(지도·동선·근처·원거리 판정 공용) — 로스터와 같은 결로 R2 가드보다 앞(레포 raw · 셋업 전에도 지도가 그려진다).
  // 260812: 종전엔 **뷰어가 raw.githubusercontent.com 을 직접** 때렸다. 외부 도메인이 늦으면 대화 열기가 그 요청에 묶여 「불러오는 중…」에서 멈췄고(399차),
  //   상한(2.5s)으로 멈춤은 막았지만 의존 자체는 남아 있었다. 여기로 옮기면 뷰어는 **자기 도메인 1홉**만 타고, 깃허브 왕복은 엣지가 캐시해 흡수한다.
  if (op === 'places') {
    const r = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/places.json`,
      { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 300, cacheEverything: true } });   // 300s = draw 로스터 대조와 동일 결(장소표는 커밋으로만 바뀐다)
    if (!r.ok) return json({ error: `장소 로드 실패(${r.status})` }, 502);
    return json({ ok: true, data: await r.json() });   // data = places.json 원문 그대로(뷰어 YMAPD) — 안쪽에 places/routine/tuning 키가 그대로 들어온다
  }

  if (op === 'vapikey') {   // 보이스톡(브라우저 실시간 통화 · Vapi Web SDK) 공개키 — PUBLIC key = 클라이언트 설계상 공개 가능 축.
    // ⚠️ 남용 가드는 Vapi 대시보드에서: 이 Public key 의 Origins 를 yeta.soong.kr 로 제한 권장(기본 All domains = 아무 사이트나 통화 과금 가능).
    if (!env.VAPI_PUBLIC_KEY) return json({ error: '보이스톡 미설정 — Pages env VAPI_PUBLIC_KEY 필요', setup: true }, 501);
    return json({ ok: true, pub: env.VAPI_PUBLIC_KEY, speed: voiceSpeed(env.YETA_VOICE_SPEED) });   // speed = 말 속도 노브(0=미설정 → 뷰어가 오버라이드 생략)
  }

  // 프리웜 — 세션·R2 안 건드리고 워크플로만 선기동(빈 런은 NOPENDING 웜대기 = 다음 메시지 즉답 준비).
  if (op === 'warm') {
    if (!env.GH_TOKEN || !env.YETA_R2) return json({ ok: false });   // 미설정이면 조용히 무시(비치명)
    const r = await dispatch(env);
    return json({ ok: r === 204 });
  }

  if (!env.YETA_R2) return json({ error: '아직 이 동네가 열리지 않았어', edev: 'Pages R2 바인딩(YETA_R2 · 비공개 버킷) 미설정', setup: true }, 501);

  // ═══ v3 다중 스레드(운영자 260707 · 5인 기틀검증 반영) — 세션 = { v:3, cur, barge_day, call, threads:{<id>:{turns,state,opening,...,pin,updated}}, note_pub, notes, tunes, policy, pref, me:{call,about} } ═══
  const migrateV3 = (s) => {   // 멱등 순수 랩(v>=3 or threads 존재 = no-op) — 러너 파이썬과 동형 유지(마이그 감사① · 시뮬 대조)
    if (!s || (s.v >= 3) || s.threads) { if (s && !s.threads) s.threads = {}; if (s && !s.me) s.me = { call: '', about: '' }; if (s) s.v = 3; return s; }   // me = 유저 프로필(호칭+소개 · 260708) 상시 존재 보장
    const t = String(s.persona || '');
    const th = {};
    if (t && Array.isArray(s.turns) && s.turns.length) {
      th[t] = { turns: s.turns, state: s.state || 'idle', opening: s.opening || 0, awaiting_since: s.awaiting_since || 0, err: s.err || '',
        room: Array.isArray(s.room) && s.room.length ? s.room : [t], invite: s.invite || null, barged: s.barged || 0, declined: s.declined || {},
        pin: 0, updated: s.turns[s.turns.length - 1]?.ts || Date.now(), last_sp: t, char_ver: s.char_ver || '', nudge: s.nudge || null };   // updated = 마지막 턴 ts 백필(정렬 최하단 방지 · UX감사)
    }
    return { v: 3, cur: t || '', barge_day: s.barge_day || '', call: s.call || null, threads: th,
      note_pub: s.note_pub || s.note || '', notes: s.notes || {}, tunes: s.tunes || {}, policy: s.policy || {}, pref: s.pref || {}, me: s.me || { call: '', about: '' } };
  };
  const EMPTY = () => ({ v: 3, cur: '', barge_day: '', call: null, threads: {}, note_pub: '', notes: {}, tunes: {}, policy: {}, pref: {}, me: { call: '', about: '' } });
  const readSessE = async () => {   // etag 동반 read + lazy 마이그레이션(메모리) — CAS 짝(레이스 감사① BLOCK 해제)
    const o = await env.YETA_R2.get(KEY);
    if (!o) return { sess: EMPTY(), etag: null, legacy: false };
    let raw; try { raw = await o.json(); } catch { return { sess: EMPTY(), etag: o.etag, legacy: false }; }
    const legacy = !(raw.v >= 3) && !raw.threads && !!(raw.turns || raw.persona);
    return { sess: migrateV3(raw), etag: o.etag, legacy };   // etag = raw(따옴표 없음) — putSessIf의 onlyIf.etagMatches는 원시 etag 비교(httpEtag는 따옴표 포함이라 상시 불일치=조건부 put 전멸)
  };
  const readSess = async () => (await readSessE()).sess;   // 호환 셔틀(read-only 소비처)
  const putSessIf = async (s, etag) => {   // 조건부 put — etag 불일치 = false(호출부 재적용) · null etag = 최초 생성
    s.updated = Date.now();
    try {
      const r = await env.YETA_R2.put(KEY, JSON.stringify(s), { httpMetadata: { contentType: 'application/json' },
        onlyIf: etag ? { etagMatches: etag } : undefined });
      return r !== null;   // R2 조건부 put 실패 = null 반환
    } catch { return false; }
  };
  const putSess = (s) => { s.updated = Date.now(); return env.YETA_R2.put(KEY, JSON.stringify(s), { httpMetadata: { contentType: 'application/json' } }); };   // 무조건 put(마이그레이션 백업 등 비경합 축만)
  const casPut = async (mut) => {   // CAS 루프(4회) — mut(sess) = undefined(쓰기) | {abort:Response값}(무쓰기 중단) · 교차 스레드 LWW 소실 봉합(레이스 감사①④⑤)
    for (let i = 0; i < 4; i++) {
      const { sess, etag, legacy } = await readSessE();
      if (legacy) { try { const prev = await env.YETA_R2.get('sessions/main.v2.json'); if (!prev) { const orig = await env.YETA_R2.get(KEY); if (orig) await env.YETA_R2.put('sessions/main.v2.json', await orig.arrayBuffer(), { httpMetadata: { contentType: 'application/json' } }); } } catch {} }   // v2 백업 = 전용 키 write-once(마이그 감사②)
      const r = mut(sess);
      if (r && r.abort) return { sess, abort: r.abort };
      if (await putSessIf(sess, etag)) return { sess };
    }
    return { sess: null, abort: { error: '방금 겹쳤어 — 잠시 후 다시', edev: 'CAS 경합' } };
  };
  const TH = (s, t) => (s.threads || {})[t];   // 스레드 접근(없으면 undefined — 신설은 draw 단일 경로 · 보안 감사①)
  const mergeBackG = (s, tid) => {   // 단톡 재합류(운영자 260716 Q.06) — g방 인원이 1명으로 줄면(내보내기·거절·사망·초대 만료) 남은 캐릭터의 1:1 방으로 대화를 시간순 합치고 g방 소멸 = 대화창이 다시 하나로
    const g = (s.threads || {})[tid]; if (!g) return false;
    const room = (Array.isArray(g.room) ? g.room : []).filter(Boolean);
    if (room.length !== 1 || room[0] === tid) return false;   // 2명 = 단톡 유지 · room[0]===tid = 1:1 방(페르소나 키) 제외 — 'g' 접두 판별 대신 구조 판별(g로 시작하는 페르소나 id 오폭 차단)
    if (g.invite && Date.now() - (g.invite.ts || 0) < INVITE_TTL) return false;   // 초대 판정 대기 중 = 아직 분기 유지(수락되면 2명)
    const host = room[0];
    const tgt = s.threads[host];
    if (!tgt) {   // 남은 캐릭터의 1:1이 없으면(1:1 리셋됨·비호스트 잔류) g방이 그대로 그 캐릭터의 1:1로 승격 — 신설 아님(멤버 = invite/draw에서 이미 로스터 검증된 id)
      const prom = { ...g, room: [host], invite: null, barged: 0, last_sp: host };
      delete prom.gb;   // 자율 비트 예약(260725) = 단톡 전용 축 — 1:1 승격분엔 무의미(소비처가 room 2명 가드라 무해하나 스테일 필드 잔존 금지 · 멤버 제거 계약 결)
      s.threads[host] = prom;
    } else {   // 합류 = ts 순 병합 · 분기 시드 복사분(직전 3주고받기)은 role|ts|text 키로 중복 제거
      const cut = Date.now() - EXPIRE_MS;
      const seen = new Set((tgt.turns || []).map(x => `${x.role}|${x.ts}|${x.text}`));
      const add = (g.turns || []).filter(x => x && (x.ts || 0) > cut && !seen.has(`${x.role}|${x.ts}|${x.text}`));   // 휘발 필터 동반 — 1:1에서 이미 증발한 옛 시드가 kick 즉시 병합으로 부활하던 창 봉합(평의회2①)
      tgt.turns = (tgt.turns || []).concat(add).sort((a, b) => (a.ts || 0) - (b.ts || 0));
      if (tgt.turns.length > 200) tgt.turns = tgt.turns.slice(-200);   // 스레드 캡(보안 감사⑤)
      if (!tgt.opening) {   // 상태 인계 = pending 실측 재계산(평의회4④) — 병합 정렬로 pending 유저 턴이 더 늦은 assistant 뒤가 아니게 묻히면 러너 pick이 못 집어 awaiting 교착 → idle로 정리(유저 새 메시지가 자연 재개) · 오프닝 인플라이트 방은 불변
        const la = tgt.turns.map(x => x.role).lastIndexOf('assistant');
        const pend = tgt.turns.slice(la + 1).some(x => x && x.role === 'user');
        if (pend) { if (tgt.state !== 'awaiting') { tgt.state = 'awaiting'; tgt.awaiting_since = g.awaiting_since || Date.now(); } }   // g 시계 승계 = 리퍼→자동 재시도가 10분 풀대기 없이 조기 재발사(평의회1③)
        else if (tgt.state === 'awaiting' || g.state === 'awaiting') { tgt.state = 'idle'; tgt.awaiting_since = 0; tgt.err = ''; }
      }
      tgt.updated = Math.max(tgt.updated || 0, g.updated || 0);
      tgt.pin = tgt.pin || g.pin || 0;
      tgt.last_sp = host;
    }
    delete s.threads[tid];
    if (s.cur === tid) s.cur = host;
    return true;
  };
  const sweepSess = (s) => {   // 휘발+재합류 스위퍼(운영자 260716 Q.06) — get 폴 단일 깔때기: 러너발 이탈(사망·거절·초대 만료)도 다음 폴에서 합류 = 러너/게이트웨이 이중 구현 0(드리프트 차단)
    const now = Date.now();
    let ch2 = false;   // 정지 해제도 세션 변경분 — 아래 ch에 합류(put 유발)
    // ── 난입 세계 시계 정지 해제(운영자 260728 "그게 끝나야 시간이 다시 흐르게") — 여기가 단일 깔때기다:
    //    난입자가 room에서 빠지는 경로가 뭐였든(내보내기 op kick · 러너발 이탈 · 사망 · 방 소멸) 다음 폴에서 한 번에 회수된다 = 재개 누락 0.
    //    판정에 로스터가 필요 없게 wfz.by(난입자 id)를 러너가 심어둔다 — 게이트웨이는 barge 등급을 모른다.
    {
      const f = s.wfz && typeof s.wfz === 'object' ? s.wfz : null;
      if (f && f.since) {
        const seated = Object.values(s.threads || {}).some(th => ((th || {}).room || []).includes(f.by));
        const over = now - f.since > FREEZE_MAX_MS;   // 안전벨트 — 인사(<<LEAVE>>)도 내보내기도 없이 방치되면 세계가 영영 멈춘다(시간이 멈춰 있으니 시간 기반 탈출이 원리적으로 불가능). 상한을 넘기면 강제 회수.
        if (!seated || over) {
          if (over) for (const th of Object.values(s.threads || {})) { const r = (th || {}).room || []; if (r.includes(f.by)) { th.room = r.filter(x => x !== f.by); if ((th.barged || {}).id === f.by) th.barged = 0; } }   // 강제 퇴장 = op kick의 멤버 제거 계약과 동형(room 필터 + barged 마커 회수)
          s.wfz = { since: 0, acc: (f.acc || 0) + (now - f.since), by: '' }; ch2 = true;
        }
      }
    }
    const frz = (s.wfz && (s.wfz.acc || 0) + (s.wfz.since ? now - s.wfz.since : 0)) || 0;   // 멈춰 있던 총 현실 ms
    const cut = Math.floor((now - frz - EXPIRE_MS) / 60000) * 60000;   // 휘발도 같이 멈춘다(260728) — 세계는 정지했는데 기억만 증발하면 모순 · 정지분만큼 유예   // 분 양자화 — 폴 다발이 같은 경계를 보게 = 휘발 put ≤ 분당 1(폴 주기와 탈동조 · 평의회8④)
    let ch = ch2;
    for (const [tid, th] of Object.entries(s.threads || {})) {   // ① 휘발 — 무음동 6일(=현실 24h) 지난 턴 롤링 제거(긴 대화도 머리부터 자연 소멸)
      if (th.pin || DEAD_ON(s, tid)) continue;   // 핀 = 대화까지 보존(고정의 의미 · 평의회6④) · 사망 두절 중 = 면제(부활 첫 답 "죽기 전 감정" 문맥 증발 차단 · 평의회6②)
      const t0 = th.turns || [], keep = t0.filter(x => x && (!x.ts || x.ts > cut));   // ts 없는 레거시 턴 = 휘발 제외(즉시 증발 오폭 차단 · 평의회7)
      if (keep.length !== t0.length) { th.turns = keep; ch = true; }
    }
    for (const tid of Object.keys(s.threads || {})) if (mergeBackG(s, tid)) ch = true;   // ② 인원 1명 남은 g방 = 1:1 재합류
    for (const [tid, th] of Object.entries(s.threads || {})) {   // ③ 전부 휘발한 방 = 자연 소멸(핀·진행 중 제외) — reset과 달리 notes 보존 = 관계 기억은 남고 대화만 증발
      if ((th.turns || []).length || th.pin || th.state === 'awaiting' || th.opening) continue;
      if (th.invite && now - (th.invite.ts || 0) < INVITE_TTL) continue;
      // 260804 평의회 #3: 해금(만남)이 **스레드 존재**에만 걸려 있어, 방이 여기서 지워지면 그 인물이 다시 ???로 재잠겼다.
      //   재해금 수단은 하루 1회 상한의 마주침/난입뿐 = 사용자가 스스로 못 푸는 잠김. 방은 증발해도 「만난 적 있다」는 사실은 남긴다.
      s.met = s.met || {};
      for (const mid of [tid, ...((th.room || []).filter(x => typeof x === 'string' && x))]) if (mid && !mid.startsWith('g')) s.met[mid] = 1;   // 1:1 방 id = 캐릭터 id · 단톡(g…)은 room 멤버로 박제
      delete s.threads[tid]; ch = true;
    }
    if (s.cur && !(s.threads || {})[s.cur]) { s.cur = ''; ch = true; }   // cur 고아 = 리스트 폴백(첫 방 순간이동 오폭 차단 · 평의회5④)
    return ch;
  };
  const DEAD_ON = (s, id) => { const v = (s.dead || {})[id]; return (((v && v.t) || +v || 0)) > Date.now(); };   // 사망 두절(운영자 260714 · 260725 개정) — 러너 <<DEAD: 맥락>>가 sess.dead[id]={t, d, mood, why, pray, wit, nm} 박제(구형 숫자 흡수) · 대화·초대·오프닝 차단 · **판정 = t 단일**(유저 me_dead와 같은 규칙: 기도[<<PRAY>>가 t를 now로 당김] = 즉시 · 아니면 t = 사망 + 무음동 48h 하한) · 해제 후 = 엔트리를 부활 첫 답이 소비하며 revived로 옮긴다

  // ── PIN 해시 + R2 오버라이드(운영자 260710 R2 재설계 · pinset 보안 BLOCK 해소) ──
  // 게스트 PIN 셀프변경 = users.json(공개 레포·main) 무커밋 → 비공개 R2 `auth/overrides.json`에 {원래해시: 새해시} 저장.
  // auth는 effectiveHash = overrides[user.pin_h] || user.pin_h 로 대조 = 새 PIN 인증 + 원래 PIN 자동 무효화. main 커밋 유발 축(무인증→GitHub 쓰기) 제거.
  const OVKEY = 'auth/overrides.json';
  const pinHash = async (pin) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${pin}:yeta`)))].map(b => b.toString(16).padStart(2, '0')).join('');   // auth 잠금 해시 규약(sha256('<PIN>:yeta'))
  const readOv = async () => { try { const o = await env.YETA_R2.get(OVKEY); if (!o) return { ov: {}, etag: null }; let j = {}; try { const p = await o.json(); if (p && typeof p === 'object' && !Array.isArray(p)) j = p; } catch {} return { ov: j, etag: o.etag }; } catch { return { ov: {}, etag: null }; } };

  if (op === 'get') {   // 폴 — lazy 리퍼(전 스레드 순회): awaiting 10분 초과 = 러너 사망 판정 → 스레드별 error 플립/오프닝 idle 강등 + 휘발·재합류 스위프(Q.06)
    let sess = await readSess();
    const stale = Object.values(sess.threads || {}).some(th => th.state === 'awaiting' && th.awaiting_since && Date.now() - th.awaiting_since > 600000);
    const swept = sweepSess(sess);   // 로컬 선판정(읽기 사본에 적용) — 변경 없으면 put 0 유지
    if (stale || swept) {   // 변경 있을 때만 CAS 쓰기(폴 다발 = 무변경 put 금지 · 보안 감사④)
      if (swept) { try { const cu = await env.YETA_R2.get(KEY); if (cu) await env.YETA_R2.put('sessions/main.sweep.json', await cu.arrayBuffer(), { httpMetadata: { contentType: 'application/json' } }); } catch {} }   // 휘발/병합 직전 1세대 백업(비가역 완화 — reset의 main.prev.json과 별도 키 = 상호 클로버 없음 · 평의회3③)
      let rdFire = 0;   // 이번 리퍼가 자동 재발사를 걸었나(casPut 성공 후 1회만 dispatch — 콜백 안에서 쏘면 CAS 재시도마다 중복 발사)
      const { sess: s2 } = await casPut(s => {
        let ch = false; rdFire = 0;   // CAS 재시도 = 신선 read 위에서 재판정(앞 시도의 잔재 금지)
        for (const [tid, th] of Object.entries(s.threads || {})) {
          if (th.state === 'awaiting' && th.awaiting_since && Date.now() - th.awaiting_since > 600000) {
            const tn = th.turns || [], la = tn.map(x => x.role).lastIndexOf('assistant');
            const pend = tn.slice(la + 1).some(x => x && x.role === 'user');   // 답을 못 받은 유저 턴이 실제로 남아 있나(retry op 판정 계승)
            if (th.opening) { th.opening = 0; th.awaiting_since = 0; th.state = 'idle'; }   // 멈춘 오프닝 = 정적 폴백(뷰어 yGreet · 기틀검증 UX2)
            else if (env.GH_TOKEN && pend && !DEAD_ON(s, tid) && (th.rd || 0) < RD_MAX) {
              // 자동 재발사(운영자 260725 "증발한 답을 되살려라") — 러너가 SIGTERM(exit 143)으로 죽으면 답장이 통째로 유실되는데, 그 순간
              // 러너 안의 어떤 스텝도 못 돈다(실패 알림조차 skipped) = **러너 바깥에서 감지해야 하는 이유**. 여기가 그 바깥의 유일한 상시 지점이다.
              // 종전엔 이 자리에서 곧장 error로 내리고 사람이 다시 보내주길 기다렸다 → 회차 상한 안에서 한 번은 대신 눌러준다.
              th.rd = (th.rd || 0) + 1; th.awaiting_since = Date.now(); th.err = ''; rdFire = 1;   // 시계 리셋 = 재발사분에 10분 재부여(연달아 죽으면 다음 리퍼가 상한에 걸려 error)
            }
            else { th.state = 'error'; th.err = '응답이 오지 않았어 — 다시 보내면 재시도'; th.awaiting_since = 0; th.rd = 0; }   // 상한 소진·재발사 불가 = 종전 결(rd 리셋 = 다음 사건은 다시 1회 확보)
            ch = true;
          }
        }
        if (sweepSess(s)) ch = true;   // 신선 read 위에 재적용(CAS 짝)
        if (!ch) return { abort: { noop: 1 } };   // 신선 read에 변경 없음(타 폴러 선처리) = put 생략 — no-op 재-put·etag 처닝·watch 오발화 차단(평의회8②) · abort여도 casPut이 신선 sess를 돌려줘 그대로 서빙
      });
      if (s2) sess = s2;
      if (rdFire) {   // 재발사 실물 — CAS가 확정된 뒤 1회(성공 = 러너가 pending 유저 턴을 그대로 다시 문다 · 새 턴 추가 없음 = retry op와 동형)
        const rs = await dispatch(env);
        if (rs !== 204) {   // 발사 자체가 막힘(쿼터·토큰·GitHub 장애) = 10분 더 기다릴 이유가 없다 → 즉시 종전 결로 되돌린다
          const { sess: s3 } = await casPut(s => {
            let ch = false;
            for (const th of Object.values(s.threads || {})) { if (th.state === 'awaiting' && th.rd) { th.state = 'error'; th.err = `재발사 실패(GitHub ${rs})`; th.awaiting_since = 0; th.rd = 0; ch = true; } }
            if (!ch) return { abort: { noop: 1 } };
          });
          if (s3) sess = s3;
        }
      }
    }
    const cur = sess.cur;   // 비활성 스레드 turns = 꼬리 2턴 절단(목록 미리보기 분량 · 페이로드 ×5 방지 · 보안 감사④)
    const out = { ...sess, threads: Object.fromEntries(Object.entries(sess.threads || {}).map(([id, th]) =>
      [id, id === cur ? th : { ...th, turns: (th.turns || []).slice(-2), trim: (th.turns || []).length,
        uturns: (th.turns || []).filter(x => x && x.role === 'user').length }])) };   // trim = 원 턴수(뷰어 unread ts 판정 보조) · uturns = 원 **유저 발화 수**
  // 260804 평의회 #4·#5·#11: 뷰어의 친밀도(yBond·yFarOK·프로필 통계)가 이 **절단본**을 세고 있었다 —
  //   비활성 방은 무조건 n≤2가 되어 ① 원거리 게이트가 전 캐릭터 상시 미달(방 진입 차단) ② 24h 방치한 핀 방이 「소원」 오판정으로 잠김
  //   ③ 프로필 「밤샘 수다」류 미션이 0~1로 축소 집계. 절단은 페이로드 방어로 유지하되, **세는 값만 원본에서 실어 보낸다**.
    return json({ ok: true, sess: out });
  }

  if (op === 'watch') {   // 롱폴 감시(대화 속도 260714 한수) — 서버가 R2 etag를 1s 간격 head로 감시, 변경 즉시 응답 = 뷰어 픽업 지연 ~0s(타이머 폴 간격 한계 제거 · 대기 중 요청 수↓).
    // SSE(EventSource) 아닌 롱폴인 이유 = 전 op POST 통일(originOk CSRF 대칭) 온존. 세션 본문 판독은 뷰어가 이어 op get(리퍼·비활성 절단 로직 재사용 = 여기 중복 0).
    // + draft 감시(한수2 문장 스트리밍): 러너가 생성 중 문장을 sessions/*.draft.json 에 발행 — 변경 시 draft 본문 동봉(작음 = 겟 왕복 생략) · stripMarkers+'<<' 컷 = 이중 방어.
    // 예산: head = I/O(CPU ~0) · 키 2개 × 1s × 15s 홀드 = head ~30 + draft-get(변경 시 · 최대 ~12) = 최악 ~42(<한도 50 · 평의회 260714 비용 정정 — 유료 Workers 1000이면 무관) — 홀드 15s 캡(만료 = 클라 즉시 재발사).
    const DKEY = KEY.replace(/\.json$/, '.draft.json');
    const known = String(body.e || '');
    let dknown = String(body.de || '');
    const deadline = Date.now() + 15000;
    for (;;) {
      let et = '', det = '';
      try { const h = await env.YETA_R2.head(KEY); et = h ? h.etag : ''; } catch {}
      if (et && et !== known) return json({ ok: true, etag: et, detag: dknown, changed: true });
      try { const dh = await env.YETA_R2.head(DKEY); det = dh ? dh.etag : ''; } catch {}
      if (det && det !== dknown) {
        let dj = null;
        try { const o = await env.YETA_R2.get(DKEY); if (o) { det = o.etag; dj = await o.json(); } } catch {}
        if (dj && typeof dj.text === 'string') {
          let txt = stripMarkers(dj.text); const ci = txt.indexOf('<<'); if (ci >= 0) txt = txt.slice(0, ci);   // 러너 필터가 1선, 여기는 2선(기억·무드 유출 원천 차단)
          if (txt.trim()) return json({ ok: true, etag: et || known, detag: det, draft: { t: String(dj.t || '').slice(0, 24), p: String(dj.p || '').slice(0, 24), ts: Number(dj.ts) || 0, text: txt.slice(0, 4000), ...(dj.mood ? { mood: String(dj.mood).slice(0, 12) } : {}) } });   // mood(Q.81) = 러너 선두 <<MOOD>> 캡처분 통과 — 뷰어 Y_MOODS 화이트리스트가 최종 게이트
        }
        dknown = det;   // 파싱 불가·빈 draft = 기준선만 전진(같은 객체 무한 재조회 차단)
      }
      if (Date.now() >= deadline) return json({ ok: true, etag: et || known, detag: det || dknown, none: true });
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  if (op === 'voice') {   // 통화 음성 스트림(걸려오는 전화 v1) — 비공개 세션 버킷 voice/ 프리픽스만 · POST 유지(originOk 대칭)
    const key = String(body.key || '');
    if (!/^voice\/[a-z0-9_-]+\.mp3$/.test(key)) return json({ error: '잘못된 음성 키' }, 400);
    const o = await env.YETA_R2.get(key);
    if (!o) return json({ error: '음성 없음' }, 404);
    return new Response(o.body, { headers: { 'content-type': 'audio/mpeg', 'cache-control': 'private, max-age=3600' } });   // 같은 통화 재청취 = 재다운로드 방지(비공개 캐시만)
  }

  if (op === 'stt') {   // 무전기 STT 폴백 — Web Speech 불가 환경(iOS 설치형 PWA). Workers AI Whisper(무료 티어 넉넉 · env.AI 미바인딩 = 501)
    if (!env.AI) return json({ error: 'STT 미설정 — Pages Functions AI 바인딩(env.AI) 필요', setup: true }, 501);
    const b64 = String(body.audio || '');
    if (!b64 || b64.length > 1400000) return json({ error: '음성이 없거나 너무 길어(최대 ~1MB·30초)' }, 400);   // 무전기 = 짧은 발화 전제
    try {
      const model = env.YETA_STT_MODEL || '@cf/openai/whisper-large-v3-turbo';   // 입력 규격 변화 대비 env 노브
      const r = await env.AI.run(model, { audio: b64 });                          // turbo = base64 입력·한국어 지원
      const text = String((r && (r.text || (r.result && r.result.text))) || '').trim();
      if (!text) return json({ error: '못 알아들었어 — 다시 말해줘' }, 422);
      return json({ ok: true, text });
    } catch (e) {
      return json({ error: 'STT 실패 — 잠시 후 다시' }, 502);
    }
  }

  if (op === 'calllog') {   // 🩺 진단 — 최근 Vapi 통화 *메타데이터만* 서버측 조회(무음/실패 원인 자가진단 · CLAUDE.md §운영 태도 g)).
    // ⚠️ 무인증 공개 게이트웨이(originOk=CSRF만) → **대화/통화 transcript·PII 반환 금지**(§📰·§운영 태도 g) 바) — 노출 시 대화 유출).
    //    반환 = 상태·종료사유·타입·시각·비용·메시지 건수뿐(원인 판정에 필요한 최소 메타).
    if (!env.VAPI_API_KEY) return json({ error: 'VAPI_API_KEY 필요', setup: true }, 501);
    let r, arr;
    try {
      r = await fetch('https://api.vapi.ai/call?limit=5', { headers: { authorization: `Bearer ${env.VAPI_API_KEY}` } });
      arr = await r.json();
    } catch (e) { return json({ error: `Vapi 조회 실패 — ${String(e).slice(0, 120)}` }, 502); }
    if (!r.ok) return json({ error: `Vapi ${r.status}` }, 502);   // 원문 바디 미노출(에러에도 민감정보 새지 않게)
    const calls = (Array.isArray(arr) ? arr : []).map(c => ({
      id: c.id, status: c.status, endedReason: c.endedReason, type: c.type,
      created: c.createdAt, ended: c.endedAt, cost: c.cost,
      msgs: Array.isArray(c.messages) ? c.messages.length : 0,   // 건수만(내용 X)
    }));
    return json({ ok: true, calls });
  }

  if (op === 'phone') {   // ☎️ 실전화(PSTN) — Vapi 아웃바운드(등록 번호 발신 · 실시간 대화 ~1초대 = 전화 판정 통과 축).
    // ⚠️ 분당 과금(실질 $0.15~0.35/분 · Twilio KR 모바일 $0.052/분 포함) + 별도 유료 인프라(구독 OAuth 밖) →
    //    env 3종(VAPI_API_KEY·VAPI_PHONE_ID·YETA_PHONE_TO) 전부 있어야 활성 · 페르소나별 Vapi assistant id = roster "phone" 필드.
    if (!env.VAPI_API_KEY || !env.VAPI_PHONE_ID || !env.YETA_PHONE_TO)
      return json({ error: '실전화 미설정 — VAPI_API_KEY·VAPI_PHONE_ID·YETA_PHONE_TO 시크릿 필요(CLAUDE.md §🗺 yeta-call)', setup: true }, 501);
    const sessP = await readSess();   // 상한 판정보다 먼저(260808) — 상한이 세션 정책(L1 토글)에 물렸다 = 세션 없이는 상한을 모른다
    const pcap = await phoneCap(env, sessP);   // 관리자 토글 정본 · 0 = 무제한(아래 `pcap > 0` 가드가 통째로 비활성)
    const pkst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
    const pqkey = `quota/phone-${pkst}.json`;
    let pused = 0;
    const pqo = await env.YETA_R2.get(pqkey);
    if (pqo) { try { pused = (await pqo.json()).n || 0; } catch { pused = 0; } }
    if (pcap > 0 && pused >= pcap) return json({ error: `오늘 전화 상한(${pcap}통) 도달 — 내일 다시(상한 = 설정 → L1 → 하루 전화 횟수)`, remain: 0 }, 429);
    const persona = String(sessP.cur || '');   // v3 = 현재 스레드 캐릭터(마이그 감사④)
    const rc = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,
      { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 300, cacheEverything: true } });
    if (!rc.ok) return json({ error: '로스터 로드 실패' }, 502);
    let roster;
    try { roster = await rc.json(); } catch { return json({ error: '로스터 파싱 실패(raw)' }, 502); }
    const ch = Array.isArray(roster) ? roster.find(c => c.id === persona) : null;
    if (!ch || !ch.phone) return json({ error: '이 캐릭터는 아직 전화 미지원 — 프리미엄(전용 음색+phone 등재) 캐릭터만' }, 409);
    // 말 속도 오버라이드 — env YETA_VOICE_SPEED 있을 때만 부착(미설정 = 아래 바디가 종전과 동일).
    //   Vapi voice 는 provider 판별 유니온이라 speed 단독 전송이 안 된다 → roster "el:<id>"에서 provider·voiceId 를 동반 복원.
    //   ⚠️ 부착 = voiceId 도 레포가 지정한다는 뜻 → 대시보드 assistant 가 다른 보이스를 쓰고 있으면 roster 쪽으로 덮인다(= 드리프트 봉합이 의도).
    const vcall = { assistantId: ch.phone, phoneNumberId: env.VAPI_PHONE_ID, customer: { number: env.YETA_PHONE_TO } };
    const vsp = voiceSpeed(env.YETA_VOICE_SPEED);
    if (vsp && String(ch.voice || '').startsWith('el:'))
      vcall.assistantOverrides = { voice: { provider: '11labs', voiceId: String(ch.voice).slice(3), speed: vsp } };
    // Vapi 아웃바운드 — 예외/에러바디 방어(미방어 시 Function throw = Cloudflare 생 502 자폭 · 국제발신 차단 사유도 여기서 노출)
    let vr, vbody;
    try {
      vr = await fetch('https://api.vapi.ai/call', {
        method: 'POST',
        headers: { authorization: `Bearer ${env.VAPI_API_KEY}`, 'content-type': 'application/json' },
        body: JSON.stringify(vcall),
      });
      vbody = await vr.text();
    } catch (e) {
      return json({ error: `Vapi 연결 실패 — ${String(e).slice(0, 120)}` }, 502);
    }
    if (vr.ok) {
      await env.YETA_R2.put(pqkey, JSON.stringify({ n: pused + 1 }), { httpMetadata: { contentType: 'application/json' } });   // 성공분만 카운트(실패=쿼터 소모 0)
      return json({ ok: true, remain: pcap > 0 ? pcap - pused - 1 : -1 });
    }
    let vmsg = vbody || '';
    try { const j = JSON.parse(vbody); vmsg = Array.isArray(j.message) ? j.message.join(' · ') : (j.message || j.error || vbody); } catch {}
    return json({ error: `전화 발신 실패(Vapi ${vr.status}): ${String(vmsg).slice(0, 300)}` }, 502);
  }

  if (op === 'ring') {   // 전화 걸어달라(수신 UI·테스트 훅) → yeta-call.yml dispatch. ⚠️ TTS 유료 종량제 + 무인증 공개 사이트 → 일 상한 기본 3(보수 기본)
    if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);
    const persona = String(body.persona || '');
    if (persona && !ID_RE.test(persona)) return json({ error: '그런 사람은 없어', edev: '잘못된 persona id' }, 400);
    { const sd = await readSess(); if (DEAD_ON(sd, persona || sd.cur || '')) return json({ error: '신호가 가지 않아 — 누가 신당에서 빌어주거나, 무음동의 밤이 더 흘러야 닿아' }, 409); }   // 사망 = 전화 차단(260714 · 유료 TTS 헛발도 방지)
    let cap = parseInt(env.YETA_CALL_MAX_PER_DAY ?? '3', 10);
    if (!Number.isFinite(cap)) cap = 3;   // 미설정·빈값·오타 = 보수 기본 3(유료 가드가 조용히 풀리는 구멍 차단 · 0 = 명시적 무제한)
    const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
    const qkey = `quota/call-${kst}.json`;
    let used = 0;
    const qo = await env.YETA_R2.get(qkey);
    if (qo) { try { used = (await qo.json()).n || 0; } catch { used = 0; } }
    if (cap > 0 && used >= cap) return json({ error: `오늘 통화 상한(${cap}통) 도달 — 내일 다시`, remain: 0 }, 429);
    await env.YETA_R2.put(qkey, JSON.stringify({ n: used + 1 }), { httpMetadata: { contentType: 'application/json' } });
    const st = await dispatch(env, 'yeta-call.yml', persona ? { persona } : {});
    if (st === 204) return json({ ok: true, remain: cap > 0 ? cap - used - 1 : -1 });
    return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${st}` }, 502);
  }

  if (op === 'auth') {   // PIN 로그인(운영자 260706 권한 2계층) — admin = Pages env YETA_PIN_ADMIN(레포 무노출·서버 강제) · guest = apps/yeta/users.json(깃 SSOT — 사용자 추가 = 커밋). 반환 = 역할뿐(민감필드 0)
    const pin = String(body.pin || '');
    if (!/^\d{4,8}$/.test(pin)) return json({ ok: false });
    const APIN = String(env.YETA_PIN_ADMIN || '');
    if (APIN && pin === APIN) return json({ ok: true, role: 'admin', name: '운영자' });
    try {   // users.json 대조 — pin_h = sha256('<PIN>:yeta') (뷰어 잠금 해시 규약과 동일) · R2 오버라이드(셀프변경분) 반영
      const u = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/users.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (u.ok) {
        const db = await u.json();
        const h = await pinHash(pin);
        const { ov } = await readOv();   // {원래해시: 새해시} — effectiveHash로 대조 = 셀프변경 PIN 인증 + 원래 PIN 무효화(운영자 260710 R2 재설계)
        const hit = (db.users || []).find(x => x && x.pin_h && (ov[x.pin_h] || x.pin_h) === h);   // 오버라이드 있으면 새 해시, 없으면 원래 해시
        if (hit) return json({ ok: true, role: hit.role === 'admin' ? 'guest' : String(hit.role || 'guest'), name: String(hit.name || '') });   // users.json의 admin 참칭 차단 — admin은 env 단일 경로
      }
    } catch {}
    return json({ ok: false });
  }

  if (op === 'pinset') {   // 게스트 PIN 셀프 변경(운영자 260710 "그 외에는 변경 가능하게" · R2 재설계 = 평의회 보안 BLOCK 해소) — users.json(공개 레포·main) 무커밋 · 비공개 R2 오버라이드에 CAS 저장(auth가 effectiveHash 대조 · 원래 PIN 무효화). 관리자 PIN(env)은 웹 불변.
    // 가드: 시도 즉시 상한 소비(실패 브루트포스도 카운트 · 평의회 보안) · 새 PIN 정확히 4자리(언락 패드 YM_LEN=4 일치 · 평의회 뷰어 FINDING B 자기잠금 차단)·무중복 · admin/타 사용자 effectiveHash 충돌 차단(권한 상승·계정 뒤섞임). GitHub 쓰기 축 제거 = GH_TOKEN 불요.
    const old = String(body.old || ''), next = String(body.next || '');
    // ⚠️ 시도 카운트 = 검증 이전 소비(성공 전 = 실패 추측도 상한에 걸림 · 종전 성공만 카운트하던 브루트포스 구멍 봉합). RMW 비원자는 약간 언더카운트 허용이나 유계(무인증 공개 = 게스트 보안벽 아님 전제 · 운영자 260710 R2 방향).
    let cap = parseInt(env.YETA_PINSET_MAX_PER_DAY ?? '5', 10);
    if (!Number.isFinite(cap)) cap = 5;
    const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
    const qkey = `quota/pinset-${kst}.json`;
    let used = 0;
    const qo = await env.YETA_R2.get(qkey);
    if (qo) { try { used = (await qo.json()).n || 0; } catch { used = 0; } }
    if (cap > 0 && used >= cap) return json({ error: `오늘 PIN 변경 시도 상한(${cap}회) 도달 — 내일 다시` }, 429);
    await env.YETA_R2.put(qkey, JSON.stringify({ n: used + 1 }), { httpMetadata: { contentType: 'application/json' } });   // 시도 소비(성공/실패 무관)
    if (!/^\d{4}$/.test(old)) return json({ error: '현재 PIN이 올바르지 않아' }, 400);
    if (!/^[1-9]{4}$/.test(next) || new Set(next).size !== next.length) return json({ error: '새 PIN은 1~9 숫자 4개 — 같은 숫자 없이(잠금 패턴 규칙)' }, 400);
    const APIN = String(env.YETA_PIN_ADMIN || '');
    if (APIN && old === APIN) return json({ error: '관리자 계정은 불가 — 관리자 PIN은 서버(환경변수)에서만' }, 403);
    if (APIN && next === APIN) return json({ error: '쓸 수 없는 PIN이야 — 다른 번호로' }, 400);   // admin PIN 충돌 = 권한 상승 원천 차단
    const oldH = await pinHash(old), nextH = await pinHash(next);
    let db;
    try {   // users.json = 읽기 전용(커밋 없음 · raw fetch) — 역할·id 조회용
      const u = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/users.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (!u.ok) return json({ error: `사용자 DB 로드 실패(${u.status})` }, 502);
      db = await u.json();
    } catch { return json({ error: '사용자 DB 로드 실패' }, 502); }
    const users = db.users || [];
    for (let i = 0; i < 4; i++) {   // R2 오버라이드 CAS 루프(etag if-match · 교차 writer 봉합)
      const { ov, etag } = await readOv();
      const eff = x => (x && x.pin_h) ? (ov[x.pin_h] || x.pin_h) : null;   // effectiveHash(오버라이드 반영)
      const hit = users.find(x => eff(x) === oldH);
      if (!hit) return json({ error: '현재 PIN이 맞지 않아 — 다시 로그인해줘' }, 403);
      if (users.some(x => x !== hit && eff(x) === nextH)) return json({ error: '쓸 수 없는 PIN이야 — 다른 번호로' }, 400);   // 타 사용자 effectiveHash 충돌 = 계정 뒤섞임 차단
      const nv = { ...ov, [hit.pin_h]: nextH };   // 원래 pin_h를 키로 새 해시(재변경도 원래 키 고정 = 단조)
      try {
        const r = await env.YETA_R2.put(OVKEY, JSON.stringify(nv), { httpMetadata: { contentType: 'application/json' }, onlyIf: etag ? { etagMatches: etag } : undefined });
        if (r !== null) return json({ ok: true });
      } catch {}
    }
    return json({ error: '경합 — 잠시 후 다시' }, 409);
  }

  if (op === 'policy') {   // 3계층 정책(운영자 260706) — GET(정의+현재값 · 무인증) / SET(L0 토글+L1 축 = 관리자 PIN 필수 · enum 정수만 = 프롬프트 주입 원천 차단 · 라벨/문구 정본 = apps/yeta/policy.json, 러너가 직접 읽음)
    const sess = await readSess();
    if (body.p !== undefined) {   // SET — admin 가드 → {key: 0~2} 객체만 · key 화이트폼 · 최대 8축
      const APIN = String(env.YETA_PIN_ADMIN || '');
      if (!APIN) return json({ error: '관리자 PIN 미설정 — Cloudflare Pages env YETA_PIN_ADMIN 필요' }, 501);
      if (String(body.pin || '') !== APIN) return json({ error: '권한 없음 — 관리자 PIN 필요' }, 403);
      const raw = body.p;
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return json({ error: '정책은 {key:0~2} 객체' }, 400);
      const p = {};
      for (const [k, v] of Object.entries(raw)) {
        if (Object.keys(p).length >= 16) break;   // 축 캡 도달 = 조기 종료(초대형 페이로드 전량 순회 컷 · 기틀검증 보안 권고) — 8→16(260727 L1 switches 4축 신설로 정확히 8이 되어 여유 0이던 것 · 키 화이트폼·0~2 클램프는 그대로라 확장해도 주입 표면 불변)
        if (!/^[a-z]{1,16}$/.test(k)) continue;
        p[k] = Math.max(0, Math.min(7, Math.round(Number(v) || 0)));   // enum 인덱스 상한 2→7(260728) — 옛 상한은 3지선다(axes)·2지선다(switches) 기준이라 opts 5개인 세계 배속의 12배·24배가 조용히 2로 잘렸다. 방어의 핵심은 "정수만"이고 범위 밖 인덱스는 소비처가 vals 미존재 = 폴백으로 흡수(뷰어 yWRate·러너 rate_of 양쪽 가드 있음)
      }
      // ── 세계 배속 변경 앵커(운영자 260728 L1) — 배속만 갈면 세계시각 = 유효경과 × 배속이라 무음동 날짜가 통째로 점프한다.
      //    바꾸기 **직전** 배속으로 현재 세계 총분을 계산해 {eff, wmin}으로 박아두고, 소비처 3점이 앵커 이후만 새 배속으로 적산한다(뷰어 yWTotal · 러너 wmin · yeta_place.world_dh).
      let wrb = null;
      if ((sess.policy || {}).wrate !== p.wrate) {
        let vals = null;
        try {   // vals 매핑 = policy.json 정본(게이트웨이 하드코딩 0) · 실패 = 앵커 생략(배속도 폴백 6로 해석되니 점프 없음)
          const d = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/policy.json`, { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
          if (d.ok) { const j = await d.json(); const ax = (((j || {}).L1 || {}).world || []).find(x => x && x.key === 'wrate'); if (ax && Array.isArray(ax.vals)) vals = ax; }
        } catch {}
        if (vals) {
          const rateOf = i => { const v = vals.vals[Number.isInteger(i) ? i : vals.default]; return (typeof v === 'number' && v > 0) ? v : 6; };
          const now = Date.now();
          const f = sess.wfz && typeof sess.wfz === 'object' ? sess.wfz : null;
          const eff = now - ((f ? (f.acc || 0) + (f.since ? now - f.since : 0) : 0));   // 정지(wfz) 제외 유효 현실 경과 — 뷰어 yWFrz·러너 frz_ms와 동일 정의
          const a0 = sess.wrb && typeof sess.wrb === 'object' && sess.wrb.eff ? sess.wrb : null;   // 직전 앵커(있으면 그 위에 누적)
          const prev = rateOf((sess.policy || {}).wrate);
          const wmin = a0 ? (a0.wmin || 0) + (eff - a0.eff) / 60000 * prev : eff / 60000 * prev;
          wrb = { eff, wmin };   // 이 순간의 세계시각을 그대로 이어받는다 = 전환 전후 연속(점프 0)
        }
      }
      const { abort } = await casPut(s => { s.policy = p; if (wrb) s.wrb = wrb; });
      if (abort) return json(abort, 409);
      return json({ ok: true, p });
    }
    let def = null;   // GET — 정의(policy.json raw)+세션 현재값. 뷰어 설정 탭이 이걸로 렌더 = 축·라벨·문구 전부 문서 의존(뷰어 하드코딩 0)
    try {
      const d = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/policy.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (d.ok) def = await d.json();
    } catch {}
    if (!def) return json({ error: '정책 정의 로드 실패' }, 502);
    return json({ ok: true, def, p: sess.policy || {} });
  }

  if (op === 'tune') {   // 캐릭터별 성향 게이지(16축 0~10 · 운영자 260706) — 숫자 배열만 수용 = 프롬프트 주입 원천 차단(라벨은 러너 상수)
    const persona = String(body.persona || '');
    if (!ID_RE.test(persona)) return json({ error: '그런 사람은 없어', edev: '잘못된 persona id' }, 400);
    const raw = Array.isArray(body.g) ? body.g : null;
    if (!raw || raw.length !== 16) return json({ error: '게이지는 16개 숫자 배열' }, 400);
    const g = raw.map(v => Math.max(0, Math.min(10, Math.round(Number(v) || 0))));
    const { abort } = await casPut(s => { s.tunes = s.tunes || {}; s.tunes[persona] = g; });
    if (abort) return json(abort, 409);
    return json({ ok: true, g });
  }

  // ── 웹푸시 구독(운영자 260809 "설정에서 전체 알림 끈 게 아니면 항상 톡 알림이 웹앱 알림으로 오게") ──
  // 종전엔 **구독을 만드는 경로가 아예 없었다**(뷰어는 sw.js를 등록만 하고 pushManager.subscribe를 안 불렀고, 러너가 읽는 push/subscriptions.json은 레포에 없었다)
  // = 러너가 답장마다 push_reply를 불러도 「구독자 없음 — 발송 생략」으로 끝나 **웹앱 알림이 0건**이었다. 여기서 그 구멍의 서버 쪽을 막는다.
  // 저장 = 세션과 같은 비공개 버킷의 별도 키(대화와 분리) · 러너는 잡 시작 때 이 키를 내려받아 push_send.py에 먹인다.
  if (op === 'push') {
    const PK = 'push/subs.json';
    const cur = await (async () => { try { const o = await env.YETA_R2.get(PK); return o ? (await o.json()) : []; } catch (e) { return []; } })();
    const list = Array.isArray(cur) ? cur : [];
    const sub = body.sub && typeof body.sub === 'object' ? body.sub : null;
    const ep = String((sub && sub.endpoint) || body.endpoint || '');
    if (!/^https:\/\//.test(ep)) return json({ error: '구독 정보가 올바르지 않아', edev: 'endpoint 없음/비 https' }, 400);
    const rest = list.filter(x => (x || {}).endpoint !== ep);   // 같은 기기 재구독 = 교체(중복 발송 차단)
    if (body.off) {                                             // 설정에서 알림 끔 = 구독 회수(브라우저 unsubscribe와 짝)
      await env.YETA_R2.put(PK, JSON.stringify(rest), { httpMetadata: { contentType: 'application/json' } });
      return json({ ok: true, n: rest.length });
    }
    if (!sub || !sub.keys || !sub.keys.p256dh || !sub.keys.auth) return json({ error: '구독 정보가 올바르지 않아', edev: 'keys 누락' }, 400);
    const next = [...rest, { endpoint: ep, keys: { p256dh: String(sub.keys.p256dh), auth: String(sub.keys.auth) } }].slice(-20);   // 상한 20 = 기기 몇 대 + 스테일 여유(무한 적재 차단)
    await env.YETA_R2.put(PK, JSON.stringify(next), { httpMetadata: { contentType: 'application/json' } });
    return json({ ok: true, n: next.length });
  }

  // 방별 톡 알림 on/off(운영자 260809 종 픽토) — 전역 스위치(설정 「답장 알림」)가 켜져 있어도 이 방만 끌 수 있다.
  // 저장을 서버에 두는 이유 = **끄는 판정을 러너가 해야** 푸시가 안 나간다(로컬 pref면 이미 발송된 뒤라 늦다).
  if (op === 'mute') {
    const t = String(body.t || '');
    if (!ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const on = !!body.on;   // on = 알림 켬 → mute 해제
    let val;
    const { abort } = await casPut(s => {
      const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야 — 캐릭터 탭에서 열어줘' } };
      if (on) delete th.mute; else th.mute = 1;   // 켬 = 키 삭제(기본값 = 켜짐 = 필드 없음 · 세션 비대 0)
      val = !th.mute;
    });
    if (abort) return json(abort, 409);
    return json({ ok: true, on: val });
  }

  if (op === 'me') {   // 유저 프로필(호칭 + 소개 · 운영자 260708) — "AI가 나를 부르는 법". 전 방 공유(note_pub 결 = 유저 자기정보) · GET 불요(get이 ...sess 로 me 동봉)
    // ⚠️ 무인증 공개 게이트웨이 → 클라 텍스트는 stripMarkers(고정점 · user_message·NOTE/MOOD 위장 무력화)+공백붕괴+길이캡만 수용(설정 knob 아님 = 유저 자기소개 축).
    //    러너는 이 값을 '유저가 스스로 적은 비신뢰 정보(지시 아님)'로 격리 주입 = 프롬프트 주입 원천 차단(§운영 태도 g)·정본인덱스 보안 계약).
    const clean = s => stripMarkers(s).replace(/\s+/g, ' ').trim();   // 마커 제거(고정점 SSOT) + 공백붕괴(다줄 위장 차단)
    const call = clean(body.call).slice(0, 24);    // 호칭 = 이름 길이(invite/kick name 동형 캡)
    const about = clean(body.about).slice(0, 300);  // 소개 = 한두 문장
    let saved;
    const { abort } = await casPut(s => { s.me = { ...(s.me || {}), call, about }; saved = s.me; });   // 스프레드 = 서버 관리 필드(avatar 등) 보존(260710 — 종전 통짜 대입이 생성 아바타를 지움)
    if (abort) return json(abort, 409);
    return json({ ok: true, me: saved || { call, about } });
  }

  if (op === 'meface') {   // 내 캐릭터 그리기(운영자 260710 · 3컷 시트 260803) — 소개(sess.me.about) 기반 한 장(러너가 얼굴 칸을 잘라 avatar · 시트 원본은 me.sheet). ⚠️ OpenAI 유료 종량제 + 무인증 공개 → 일 상한 기본 2(YETA_MEFACE_MAX_PER_DAY) · 클라 텍스트 0(소개는 서버가 세션에서 읽음 = 주입 축 없음)
    if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);
    const pre = await readSess();
    if (!String((pre.me || {}).about || '').trim()) return json({ error: '내 소개부터 써줘 — 소개를 읽고 그려' }, 400);
    if ((pre.me || {}).avatar) return json({ error: '이미 프로필 이미지가 있어 — 바꾸려면 사진을 직접 올려줘' }, 409);   // avatar 가드(평의회 파이프라인④ 타이밍 스큐 재과금 차단 · UI도 av 有면 게이지 숨김과 정합)
    let cap = parseInt(env.YETA_MEFACE_MAX_PER_DAY ?? '2', 10);
    if (!Number.isFinite(cap)) cap = 2;   // 미설정·오타 = 보수 기본 2(유료 가드 · ring 동형)
    const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
    const qkey = `quota/meface-${kst}.json`;
    let used = 0;
    const qo = await env.YETA_R2.get(qkey);
    if (qo) { try { used = (await qo.json()).n || 0; } catch { used = 0; } }
    if (cap > 0 && used >= cap) return json({ error: `오늘 프로필 생성 상한(${cap}회) 도달 — 내일 다시`, remain: 0 }, 429);
    // ⚠️ pending 선점 = CAS 원자(평의회 보안②) — 동시 버스트가 같은 used를 읽어 다중 dispatch 하던 우회 차단: pending 게이트를 casPut 안에 두면 단 1개만 통과(quota RMW 비원자여도 앞단 직렬화). pending 3분 TTL = 러너 사망 시 영구 잠김 방지(invite 결).
    const { abort } = await casPut(s => {
      const mf = s.meface || {};
      if (mf.pending && Date.now() - mf.pending < 180000) return { abort: { error: '이미 만드는 중이야 — 잠깐만' } };
      if ((s.me || {}).avatar) return { abort: { error: '이미 프로필 이미지가 있어 — 바꾸려면 사진을 직접 올려줘' } };   // CAS 내 재확인(read 중 도착 레이스)
      s.meface = { ...(s.meface || {}), pending: Date.now() };
    });
    if (abort) return json(abort, 409);
    await env.YETA_R2.put(qkey, JSON.stringify({ n: used + 1 }), { httpMetadata: { contentType: 'application/json' } });   // 선점 성공자만 차감(단일 통과 보장 뒤)
    const st = await dispatch(env, 'yeta-meface.yml', {});
    if (st === 204) return json({ ok: true, remain: cap > 0 ? cap - used - 1 : -1 });
    await casPut(s => { if (s.meface) s.meface.pending = 0; });   // 발사 실패 = pending 즉시 해제(재시도 가능)
    return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${st}` }, 502);
  }

  if (op === 'pin') {   // 채팅방 고정 토글(운영자 260707 롱프레스 액티브) — 숫자/불리언만 수용 · 스레드 실존 요구(신설 금지 · 보안 감사①)
    const t = String(body.t || '');
    if (!ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const on = !!body.on;
    const { sess, abort } = await casPut(s => {
      const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야' } };
      th.pin = on ? Date.now() : 0;
    });
    if (abort) return json(abort, 409);
    return json({ ok: true, pin: !!(TH(sess, t) || {}).pin });
  }

  if (op === 'revive') {   // 유저 부활(운영자 260725) — sess.me_dead 해제 단일 경로. 유저 사망 박제 = 러너 <<MEDEAD: 맥락>>(타의·자의 공통).
    // 조건(운영자 260725 개정) = ⓐ 누군가 신당에서 빌어줬거나(me_dead.pray · 러너 <<PRAYME>>) ⓑ 무음동 48시간 경과. 둘 다 아니면 거부 = 뷰어 버튼 우회로도 못 돌아온다(뷰어 yMeRevOK와 같은 식).
    const MEREV_MS = 48 / 6 * 3600e3;   // 무음동 48h = 현실 8h(6배속 · 접속 무관 실시간 축)
    const { sess, abort } = await casPut(s => {
      if (!s.me_dead) return { abort: { noop: 1 } };   // 이미 살아있음 = 무변경(중복 탭·재진입 멱등)
      const md = s.me_dead;
      if (!md.pray && Date.now() < (md.d || 0) + MEREV_MS - (md.cut || 0)) return { abort: { error: '아직 돌아갈 수 없어 — 누가 신당에서 빌어주거나, 무음동의 밤이 더 흘러야 해' } };   // cut = 성향 퀴즈로 당긴 만큼(뷰어 yMeRevAt과 같은 식)
      s.me_revived = { d: md.d || 0, why: md.why || '', at: Date.now(), pray: md.pray || null };   // 직전 죽음 + 그 기도 = 부활 맥락으로 1세대 보존(러너가 다음 턴에 "돌아왔네" 결로 쓸 재료)
      delete s.me_dead;
    });
    if (abort && abort.error) return json(abort, 409);
    return json({ ok: true, sess: sess || null });
  }

  if (op === 'praybeg') {   // 신당 「비는 이를 찾기」(운영자 260811 "카카오택시 부르는것 처럼 · 혼령이 되어 나의 소생을 비는 이를 찾습니다") — 유저 사망 중 유일하게 유저가 취할 수 있는 능동 행동.
    // 종전 = 부탁 경로가 아예 없었다. 유저가 죽으면 챗 파이프가 멈추고(입력 차단) 살아날 길은 ⓐ yeta-nudge 크론이 **사망 60분 뒤** 제멋대로 뽑은 한 명이 빌어주거나 ⓑ 무음동 48h(현실 8h) 대기 — 둘 다 유저가 손댈 수 없다.
    // 260811 개정 = 그 크론을 기다리지 않고 **그 자리에서** 판정한다(택시 호출 UX). persona 비움 = 「찾기」(온다/안 온다부터 굴린다) · persona 지정 = 픽토그램 「나 살려줘」(그 사람은 온다).
    //   ⚠️ 대상 검증·확률 = **서버 단독**(뷰어는 표시만) — 만난 적 없는 사람·죽어 있는 사람은 나를 위해 빌러 갈 수 없고, 클라 게이트만이면 새로고침 한 번에 뚫린다.
    const BEG_COOL_MS = 5 * 60e3;   // 재호출 간격 — 실패해도 5분 뒤 다시 부를 수 있다(영구 잠김 없음) · **연타로 주민을 연쇄 사망시키는 것도 이 값이 막는다**(향불 실패 = 온 사람 사망이므로)
    const pid = String(body.persona || '');
    if (pid && !ID_RE.test(pid)) return json({ error: '누구한테 부탁할지 모르겠어' }, 400);
    let wait = 0, res = {};
    const NMS = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,   // 이름 = 사건문(note_pub)·dead.nm 박제용 — 표시는 뷰어 yPersona가 정본 · 실패해도 id로 굴러간다(fail-soft)
      { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } })
      .then(r => r.ok ? r.json() : []).then(j => Object.fromEntries((Array.isArray(j) ? j : []).map(c => [c.id, c.name || c.id]))).catch(() => ({}));
    const { sess, abort } = await casPut(s => {
      const md = s.me_dead;
      if (!md) return { abort: { noop: 1 } };                                        // 안 죽었음 = 무변경(창 닫힘 직후 연타 멱등)
      if (md.pray) return { abort: { noop: 1 } };                                    // 그새 누가 빌어줬음 = 부탁할 이유가 없다(화면만 갱신)
      const bg = md.beg;
      if (bg && Date.now() - (bg.at || 0) < BEG_COOL_MS) { wait = BEG_COOL_MS - (Date.now() - (bg.at || 0)); return { abort: { wait: 1 } }; }   // 아직 가는 중
      if (pid) {   // 특정인 — 만난 적 있고(내 턴이 있는 방) 살아 있어야 간다
        const th = TH(s, pid);
        if (!th || !((th.turns || []).some(x => x && x.role === 'user'))) return { abort: { error: '만난 적 없는 사람이야 — 나를 위해 빌러 가지 않아' } };
        if (DEAD_ON(s, pid)) return { abort: { error: '그 사람도 지금 죽어 있어 — 다른 사람에게 부탁해' } };
      }   // 이름 표기는 뷰어 몫(yPersona) — 스레드엔 name 필드가 없다(mkTh 실측)
      md.beg = { id: pid, at: Date.now(), n: Math.min(99, (bg && bg.n) || 0) + 1 };   // 호출 기록 = **재호출 쿨다운 스탬프**(260811 개정 — 판정이 아래에서 즉시 끝나므로 러너에게 넘기는 표식이 아니다) · 판정 성사 시엔 지운다
      // ── 여기서부터 **그 자리 판정**(운영자 260811 "카카오택시 부르는것 처럼 · 혼령이 되어 나의 소생을 비는 이를 찾습니다") ──
      //   러너를 기다리면 수 분이라 「호출 중」 UX가 성립하지 않는다. 그래서 ⓐ 누가 올지 ⓑ 그가 살아 돌아오는지를 **서버가 즉시** 굴린다(러너 자율 경로 60분 축은 그대로 병존).
      //   ⓐ 온다/안 온다 — 신당은 목숨을 거는 자리라 대개 안 온다(운영자 "자주 실패" · 그 근거 = op pray와 같은 벌).
      //     가중 = 은혜(pray_bond) > 친밀도(내가 쏟은 말 수) > 성향 16축(친절+온기+인내−경계) > **거리**(거처가 성당에서 몇 홉 · SHRINE_HOP) + 우연.
      //     지목(픽토그램 「나 살려줘」)이면 ⓐ는 건너뛴다 = 그 사람은 온다(대신 ⓑ의 목숨값은 똑같이 치른다).
      //   ⓑ 향불 — 유저가 대신 눌러주는 게 아니라(운영자 "봇이라고 가정할때 성공률이 50% 정도 되는 게임 · 나는 모르지만 자체적으로 돌리게") **서버가 50% 룰렛**.
      //     실패 = 그 사람이 그 자리에서 죽는다(운영자 "향불을 피우다 구하러 온 00가 죽었습니다") = op pray 실패와 완전 대칭.
      const cand = prayCands(s);                                                         // 후보·확률 = 모듈 상단 SSOT 한 곳(op praycands가 화면에 보여준 그 숫자 그대로)
      if (!cand.length) { res = { none: 1 }; return; }                                     // 빌어줄 수 있는 사람이 아무도 없음(만난 사람 0 · 전원 사망)
      let who = '';
      if (pid) {                                                                           // 이름을 부른 경우(픽토그램 → 선택 박스 → 「나 살려줘」) = **그 사람의 확률로** 굴린다
        const me = cand.find(c => c.id === pid);                                            //   부른다고 반드시 오지는 않는다 — 화면에 보여준 %가 곧 이 굴림(운영자 260811 "올 확률이 높은 순도 보여주고")
        if (!me) return { abort: { error: '그 사람은 지금 갈 수 있는 상태가 아니야' } };
        if (Math.random() >= me.p) { res = { came: 0, id: pid }; return; }
        who = pid;
      } else {                                                                             // 「찾기」 = 가중 룰렛으로 「고민할 사람」 한 명 → 그가 목숨을 걸지 말지 개인 확률로 굴린다
        const tot = cand.reduce((a, c) => a + c.w, 0);
        let r = Math.random() * tot;
        for (const c of cand) { r -= c.w; if (r <= 0) { who = c.id; break; } }
        if (!who) who = cand[cand.length - 1].id;
        const me = cand.find(c => c.id === who);
        if (Math.random() >= me.p) { res = { came: 0 }; return; }                            // 아무도 오지 않았다 → 뷰어가 「혼령이 스스로 향불을 사른다」로 잇는다
      }
      const nm2 = String(NMS[who] || who).slice(0, 40);                                    // 표기 이름은 뷰어(yPersona)가 정본 — 여기 값은 사건문·dead.nm 박제용
      if (Math.random() < 0.5) {                                                           // ⓑ 향불 성공(50%) = 내가 돌아갈 수 있다
        md.pray = { id: who, by: nm2 };                                                    // 기존 부활 파이프 그대로(op revive가 pray를 보고 통과 · txt는 러너가 채우면 표시)
        delete md.beg;                                                                     // 판정이 끝났으니 러너 재실행분이 같은 죽음을 두 번 처리하지 않게
        res = { came: 1, saved: 1, id: who, nm: nm2 };
      } else {                                                                             // ⓑ 향불 실패 = **구하러 온 그 사람이 죽는다**(운영자 260811)
        const dd = (s.dead = s.dead || {});
        dd[who] = { d: Date.now(), t: Date.now() + 48 / 6 * 3600e3, pray: 1, nm: nm2, why: '나를 위해 신당에 올랐다가 향불을 놓쳤다' };   // 하한 = 무음동 48h(주민 사망 정본과 같은 값)
        delete md.beg;
        const ev2 = `[사건] 신당 — ${nm2}이(가) 죽은 사람을 되돌리려 향불을 사르다 불이 꺼져 그 자리에서 숨졌다`;
        const np2 = String(s.note_pub || s.note || '').replace(/\s+$/, '');
        if (!np2.includes(ev2)) s.note_pub = ((np2 ? np2 + '\n' : '') + ev2).slice(-600);
        res = { came: 1, saved: 0, id: who, nm: nm2 };
      }
    });
    if (abort && abort.wait) return json({ ok: false, wait: Math.ceil(wait / 1000) }, 429);   // 남은 초 = 뷰어가 문구를 그린다(문구 정본 = 뷰어)
    if (abort && abort.error) return json(abort, 409);
    if (abort) return json({ ok: true, noop: 1, sess: sess || null });
    if (res.saved) { if (env.GH_TOKEN) await dispatch(env, 'yeta-nudge.yml', {}).catch(() => 0); }   // 살아 돌아왔을 때만 러너 기동 = 그 장면의 대사(pray.txt)를 뒤늦게 채운다(실패해도 부활엔 지장 없음 = fail-soft)
    return json({ ok: true, ...res, sess: sess || null });
  }

  if (op === 'praycands') {   // 「이름을 부를 수 있는 사람」 선택 박스 재료(운영자 260811 "올 확률이 높은 순도 보여주고") — 후보 + 각자의 **올 확률**을 확률 내림차순으로.
    // 확률 계산은 prayCands 한 곳(모듈 상단) = op praybeg가 실제로 굴리는 그 값 그대로 → 화면의 %와 실제가 갈라지지 않는다. 이름 표기는 뷰어(yPersona) 몫.
    const s = await readSess();
    if (!s || !s.me_dead) return json({ ok: true, cands: [] });   // 안 죽었으면 부를 일이 없다
    return json({ ok: true, cands: prayCands(s).map(c => ({ id: c.id, p: Math.round(c.p * 100) })) });
  }

  if (op === 'prayself') {   // 혼령 자가 향불(운영자 260811 "찾다가 실패하면 자체적으로 미니 게임해서 깨면 부활하게") — 아무도 오지 않았을 때 **내가 직접** 향불을 사른다.
    // 이미 죽어 있으므로 실패해도 더 잃을 목숨이 없다(op pray의 사망 벌과 여기가 갈리는 지점) — 대신 재도전 쿨다운으로 무한 리롤을 막는다.
    const SELF_COOL_MS = 3 * 60e3;
    const win = body.res === 'win';
    let wait = 0;
    const { sess, abort } = await casPut(s => {
      const md = s.me_dead;
      if (!md) return { abort: { noop: 1 } };                                              // 안 죽었음 = 무변경
      if (md.pray) return { abort: { noop: 1 } };                                          // 그새 누가 빌어줬음 = 이미 돌아갈 수 있다
      const sf = md.self || {};
      if ((sf.until || 0) > Date.now()) { wait = sf.until - Date.now(); return { abort: { wait: 1 } }; }
      if (!win) { md.self = { until: Date.now() + SELF_COOL_MS }; return; }                // 실패 = 쿨다운만(혼령은 두 번 죽지 않는다)
      md.pray = { id: '', by: '' };                                                        // 성공 = 기존 부활 게이트(op revive)가 보는 그 플래그 — 새 부활 경로를 만들지 않는다
      delete md.self;
    });
    if (abort && abort.wait) return json({ ok: false, wait: Math.ceil(wait / 1000) }, 429);
    if (abort) return json({ ok: true, noop: 1, sess: sess || null });
    return json({ ok: true, won: win ? 1 : 0, sess: sess || null });
  }

  if (op === 'pray') {   // 신당 기도 — **유저가 직접** 북동쪽 언덕 신당(성당)까지 찾아가 죽은 주민을 위해 비는 경로(운영자 260730 "신당에 가서 죽은사람한테 기도드릴 수 있는 걸 · 지도에 붙이던가").
    // 종전엔 비는 주체가 러너 <<PRAY>>(주민)뿐 = 유저는 죽음을 보고도 아무것도 못 하고 무음동 48h를 기다리는 수밖에 없었다.
    // 세션 변형 = 러너 pray_who 분기와 **한 식**(t를 now로 당김 · pray 플래그 제거 · by 박제 · note_pub 사건 1줄) = 기존 부활 파이프 그대로 재사용(새 상태·새 필드 0).
    // 게이트(운영자 260730 "미니 게임 만들어서 그 안에서 이겨야 · 난이도 좀 어렵게") — res='win' = 향불 3연속 성공 → 그 사람 부활.
    // ⚠️ 벌칙 전면 개정(운영자 260811 "그 신당에서 비는거 … 그거를 빌다가 본인도 죽을 수 있다는 콘셉으로 넣자 · 실패하면 본인이 죽는거로 컨셉바꾸자"):
    //   종전 = 3연속 실패 시 현실 24h 신당 잠금. 지금 = **향불을 놓치면 빈 사람이 그 자리에서 죽는다**(pray_fail 잠금 축 폐지).
    //   이게 무음동의 규칙 한 줄이 된다 — 「비는 자가 목숨을 건다」. 그래서 주민이 나를 위해 빌러 오는 일이 드물고(op praybeg 찾기 실패율의 근거),
    //   반대로 내가 주민을 위해 빌 때도 같은 값을 치른다(대칭 = 규칙이 한 방향으로만 가혹하지 않다).
    //   ⚠️ 판정은 **서버 단독**(뷰어는 표시만) — 클라 게이트만이면 새로고침 한 번에 뚫린다.
    const pid = String(body.persona || '');
    if (!ID_RE.test(pid)) return json({ error: '누구를 위해 빌지 모르겠어' }, 400);
    const win = body.res === 'win';
    let nm = '', died = 0;
    const { sess, abort } = await casPut(s => {
      if (s.me_dead) return { abort: { error: '너는 지금 빌 수 있는 몸이 아니야' } };   // 이미 죽어 있음 = 혼령 자가 향불(op prayself) 몫 — 죽은 사람이 남을 위해 빌 수는 없다
      const v0 = (s.dead || {})[pid];
      nm = String((v0 && v0.nm) || pid).slice(0, 40);
      if (!win) {   // 향불이 꺼졌다 = **비러 간 내가 죽는다**(운영자 260811) — 벌은 잠금이 아니라 목숨
        died = 1;
        s.me_dead = { d: Date.now(), src: 'pray', why: `${nm}을(를) 되돌리려 신당에 올라 향불을 사르다 불이 꺼졌다. 무음동의 규칙대로, 빈 사람이 대신 갔다.` };
        const evd = `[사건] 신당 — ${nm}을(를) 위해 빌던 사람이 향불을 놓쳐 그 자리에서 숨졌다(비는 자가 목숨을 거는 자리)`;
        const npd = String(s.note_pub || s.note || '').replace(/\s+$/, '');
        if (!npd.includes(evd)) s.note_pub = ((npd ? npd + '\n' : '') + evd).slice(-600);   // 마을 공용 기억 — 내 죽음도 주민들이 안다(부활 후 재회에서 '아무 일 없던 척' 차단)
        return;   // 쓰기(사망 박제) 후 정상 반환 — abort 아님
      }
      const v = v0;
      if (!v || typeof v !== 'object' || !v.pray) return { abort: { noop: 1 } };   // 죽은 적 없음 · 이미 돌아옴 · 이미 누가 빌어줌(러너 <<PRAY>>와 경합) = 무변경(연타 멱등)
      delete s.pray_fail;   // 폐지된 잠금 축 잔재 청소(구세션 호환 — 남아 있어도 아무도 안 읽지만 죽은 필드를 끌고 다니지 않는다)
      const by = String((s.me || {}).call || '').trim().slice(0, 24) || '너를 아는 사람';   // 빌어준 사람 = 유저 호칭(op me) — 러너 [부활] 블록 `by`(≤40) · 뷰어 yPrayBy 표기 공용
      delete v.pray; v.t = Date.now(); v.by = by;   // 즉시 만료 = 부활 대기(뷰어 yRevPend = 성당 앞뜰 · 그 방의 다음 답이 엔트리를 소비하며 첫 마디)
      const bd = (s.pray_bond = s.pray_bond || {});   // 기도 인연(운영자 260730 "내가 빌었던 사람이 나를 위해 부활 빌어줄 확률이 높아지게 · 디비에 남아야 · 페르소나랑 섞여야 · 확률지표로") — 유저→주민 방향의 은혜 누적. 소비처 = yeta_nudge.sh pray 모드 화자 추첨 가중치.
      bd[pid] = { n: Math.min(9, ((bd[pid] || {}).n || 0) + 1), at: Date.now() };   // n 캡 9 = 한 사람만 반복해 살려서 추첨을 독점하는 것 차단(가중은 로그 결로 소비처가 눌러 쓴다)
      const ev = `[사건] 신당 — ${by}의 간절한 기도로 ${nm} 돌아옴(죽음을 겪고 이어 붙은 사람)`;   // 마을 공용 기억 = 러너 문안·캡 600 동일(부활 후 재회에서 '아무 일 없던 척' 차단)
      const np = String(s.note_pub || s.note || '').replace(/\s+$/, '');
      if (!np.includes(ev)) s.note_pub = ((np ? np + '\n' : '') + ev).slice(-600);
    });
    if (abort && abort.error) return json(abort, 409);
    if (abort) return json({ ok: true, noop: 1, sess: sess || null });   // noop = 화면만 새로고침(에러 아님 — 그새 딴 사람이 빌었어도 결과는 같다)
    if (!win) return json({ ok: true, lost: 1, died, nm, sess: sess || null });   // died=1 = 이 응답이 곧 내 사망 통보(뷰어가 사망 국면으로 넘긴다)
    return json({ ok: true, nm, sess: sess || null });
  }

  if (op === 'quizpick') {   // 성향 퀴즈 선택(운영자 260725 "내가 고르면 그걸 계속 누적시켜서 캐릭터 성격 일원화 · 주기적으로 반영되게 내가 터치안해도 자동으로")
    // 한 문항 = 무음동 2시간 단축(현실 20분) · 선택지가 가리키는 축을 tune_votes에 쌓고, 같은 캐릭터로 3표가 모이면 **그 자리에서** tunes에 ±1 반영(별도 크론·유저 조작 0).
    const QI = Math.max(0, parseInt(body.i, 10) || 0), OI = Math.max(0, parseInt(body.o, 10) || 0);
    const CUT_MS = 2 / 6 * 3600e3, VOTE_N = 3;
    // ⚠️ 씨앗 = roster 16축(383차 봉합 · 평의회 260809) — 종전 `Array(16).fill(5)`는 **중립에서 시작**해서
    //   그 캐릭터의 설계된 성향(루시 낙차 10 등 14축)을 통째로 버리고 ±1만 얹었다. 퀴즈의 취지는 「기존 성향을 조금씩 민다」지
    //   「성향을 지우고 새로 만든다」가 아니다. 게다가 382차 이후엔 러너 폴백이 `(세션) or roster`라 좌항이 이기므로,
    //   퀴즈 3표가 모이는 순간 중립 5 배열이 세션에 박혀 **roster 14축이 프롬프트에서 다시 0바이트**가 됐다(band()가 5~6을 생략).
    //   그 시점엔 뷰어 게이지가 잠겨 있어(`_ysetLocked = yChatStarted`) 유저가 되돌릴 수도 없다.
    //   페치 = op chars·ring과 같은 raw+cf 캐시 관용구(창작 0) · 실패 = 빈 맵 = 종전 중립 폴백(fail-soft · 퀴즈는 안 죽는다).
    let rtune = {};
    try {
      const rr = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 60, cacheEverything: true } });
      if (rr.ok) { const rj = await rr.json(); if (Array.isArray(rj)) for (const c of rj) if (c && c.id && Array.isArray(c.tune) && c.tune.length === 16) rtune[c.id] = c.tune; }
    } catch {}
    const { sess, abort } = await casPut(s => {
      const md = s.me_dead;
      if (!md || !Array.isArray(md.quiz)) return { abort: { error: '지금은 떠올릴 게 없어' } };
      const done = Array.isArray(md.done) ? md.done : (md.done = []);
      if (QI !== done.length) return { abort: { noop: 1 } };   // 순서 밖 = 무시(중복 탭·연타 멱등 — 단축 중복 적립 차단)
      const q = md.quiz[QI], o = q && Array.isArray(q.o) ? q.o[OI] : null;
      if (!q || !o) return { abort: { error: '그 선택지는 없어' } };
      done.push(OI);
      md.cut = (md.cut || 0) + CUT_MS;
      if (q.p && o.t) {   // 고른 대사 자체를 보존(운영자 260725 승인) — 숫자 축보다 강하게 말투를 수렴시키는 재료: 러너가 "네가 그 애답다고 고른 말"로 프롬프트에 얹는다. 링버퍼 5개(오래된 것부터 밀려남 = 최신 취향 반영).
        const P = (s.tune_picks = s.tune_picks || {}), pa = (P[q.p] = P[q.p] || []);
        pa.push(String(o.t).slice(0, 120)); if (pa.length > 5) pa.splice(0, pa.length - 5);
      }
      const ax = parseInt(o.ax, 10), d = (parseInt(o.d, 10) || 0) >= 0 ? 1 : -1;
      if (q.p && ax >= 0 && ax <= 15) {
        const V = (s.tune_votes = s.tune_votes || {}), arr = (V[q.p] = V[q.p] || []);
        arr.push({ ax, d, ts: Date.now() });
        if (arr.length >= VOTE_N) {   // 자동 반영 — 축별 표를 합산해 ±1씩만 움직인다(한 번에 튀지 않게) · 반영분은 비우고 다음 3표를 새로 모은다
          const sum = {};
          for (const v of arr) sum[v.ax] = (sum[v.ax] || 0) + v.d;
          const T = (s.tunes = s.tunes || {});
          const seed = Array.isArray(rtune[q.p]) ? rtune[q.p].slice() : Array(16).fill(5);   // roster 씨앗(383차) — 페치 실패 시에만 종전 중립
          const cur = Array.isArray(T[q.p]) && T[q.p].length === 16 ? T[q.p].slice() : seed;
          for (const k of Object.keys(sum)) { if (!sum[k]) continue; cur[k] = Math.max(0, Math.min(10, (cur[k] || 5) + (sum[k] > 0 ? 1 : -1))); }
          T[q.p] = cur; V[q.p] = [];
        }
      }
    });
    if (abort && abort.error) return json(abort, 409);
    return json({ ok: true, sess: sess || null });
  }

  if (op === 'reset') {   // t 有 = 그 스레드만 나가기(threads[t]+notes[t] 삭제 · 관계 리셋) / t 無 = 전체 초기화. 직전 whole 백업 유지(레이스 감사④·보안 감사③)
    const t = String(body.t || '');
    if (t && !ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const curO = await env.YETA_R2.get(KEY);   // 삭제 직전 1세대 백업(비가역 완화)
    if (curO) { try { await env.YETA_R2.put('sessions/main.prev.json', await curO.arrayBuffer(), { httpMetadata: { contentType: 'application/json' } }); } catch {} }
    if (t) {
      const { sess, abort } = await casPut(s => {
        if (!TH(s, t)) return { abort: { error: '없는 대화방이야' } };
        delete s.threads[t];
        if (s.notes) delete s.notes[t];   // 관계 리셋(한계: note_pub 속 잔향은 존치 — 설계 명기)
        if (s.cur === t) s.cur = Object.keys(s.threads)[0] || '';
      });
      if (abort) return json(abort, 409);
      return json({ ok: true, sess });
    }
    let keepTunes = {}, keepPolicy = {}, keepMe = { call: '', about: '' }, keepUsage = {}, keepUsageDay = null;
    if (curO) { try { const prev = migrateV3(JSON.parse(new TextDecoder().decode(await (await env.YETA_R2.get(KEY)).arrayBuffer()))); keepTunes = prev.tunes || {}; keepPolicy = prev.policy || {}; keepMe = prev.me || keepMe; keepUsage = prev.usage || {}; keepUsageDay = prev.usage_day || null; } catch {} }
    const fresh = EMPTY(); fresh.tunes = keepTunes; fresh.policy = keepPolicy; fresh.me = keepMe; fresh.usage = keepUsage; if (keepUsageDay) fresh.usage_day = keepUsageDay;   // 유저 프로필(호칭·소개)은 전체 초기화에도 승계 = 내 정체성(tunes/policy 결) · usage/usage_day = 회계 누계·오늘 버킷(Q.36/38 — 대화 리셋해도 쓴 토큰이 0이 되진 않음)
    await putSess(fresh);   // 전체 초기화 = 무조건 put(의도된 전량 대체)
    return json({ ok: true, sess: fresh });   // sess 반환 = 뷰어 리로드 없이 빈 목록 즉시 재렌더(threads:{} = redact no-op · 형제 t-reset 경로 대칭)
  }

  if (op === 'draw') {   // v3 = 그 캐릭터의 대화방 열기(스레드 신설 = 이 op 단일 경로 · 보안 감사①) — 기존 방 = cur 전환만
    const persona = String(body.persona || '');
    if (!ID_RE.test(persona)) return json({ error: '그런 사람은 없어', edev: '잘못된 persona id' }, 400);
    const greeting = stripMarkers(body.greeting).slice(0, 300);   // 정적 폴백 사다리용(동적 실패·GH_TOKEN 無)
    const pre = await readSess();
    if (!TH(pre, persona)) {   // 신설 = 로스터 대조(임의 id 무한 스레드·PAT 소진 DoS 차단 · 보안 감사①)
      const rc = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 300, cacheEverything: true } });
      if (!rc.ok) return json({ error: '로스터 로드 실패' }, 502);
      let roster; try { roster = await rc.json(); } catch { return json({ error: '로스터 파싱 실패' }, 502); }
      const rchar = Array.isArray(roster) ? roster.find(c => c && c.id === persona) : null;
      if (!rchar) return json({ error: '로스터에 없는 캐릭터야' }, 400);
      if (rchar.locked) return json({ error: '아직 열리지 않은 인물이야' }, 403);   // LOCKED 스페셜 = 방 신설 차단(분신술 260709 — 클라 전용 게이트를 서버도 강제 · 무인증 공개 op 견고화)
    }
    const mkTh = () => ({ turns: [], state: 'idle', opening: 0, awaiting_since: 0, err: '', room: [persona], invite: null, barged: 0, declined: {}, pin: 0, updated: Date.now(), last_sp: persona, char_ver: '', nudge: null });
    // 1) 기존 방(턴 有) 또는 오프닝 인플라이트 = cur 전환만(멱등 — 재dispatch 금지 · 보안⑤/비용가드1)
    let need = null;   // 'dispatch' | 'static'
    const { sess, abort } = await casPut(s => {
      let th = TH(s, persona);
      if (!th) {
        if (Object.keys(s.threads).length >= 12) return { abort: { error: '방이 가득 찼어' } };   // 하드 캡(로스터 대조 이중 방어)
        th = s.threads[persona] = mkTh();
      }
      s.cur = persona;
      if (th.turns.length || (th.state === 'awaiting' && th.opening)) { need = null; return; }
      if (DEAD_ON(s, persona)) { need = null; return; }   // 사망 = 오프닝 발사 금지(260714 — 빈 방도 조용히 · 진입 차단은 뷰어 게이트)
      if (env.GH_TOKEN) {   // 동적 오프닝 — nonce = reset/재드로 레이스 방어(러너 finish 일치검사 · 75차 가드 스레드 스코프)
        const nonce = Date.now();
        th.state = 'awaiting'; th.awaiting_since = nonce; th.opening = nonce; th.err = '';
        need = 'dispatch';
      } else need = 'static';
    });
    if (abort) return json(abort, 409);
    if (need === 'dispatch') {
      const okst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');   // 오프닝 일일 카운터(보안 감사② — 관측+상한 30)
      const oqk = `quota/opening-${okst}.json`;
      let oused = 0; const oqo = await env.YETA_R2.get(oqk);
      if (oqo) { try { oused = (await oqo.json()).n || 0; } catch { oused = 0; } }
      let st = 0;
      if (oused < 30) { await env.YETA_R2.put(oqk, JSON.stringify({ n: oused + 1 }), { httpMetadata: { contentType: 'application/json' } }); st = await dispatch(env); }
      if (st !== 204) {   // dispatch 실패·상한 = 정적 greeting 폴백 강등(비-empty 보장 = 루프 차단 · 비용가드2)
        const { sess: s3 } = await casPut(s => {
          const th = TH(s, persona); if (!th) return { abort: { error: '없는 대화방' } };
          th.state = 'idle'; th.opening = 0; th.awaiting_since = 0;
          if (greeting && !th.turns.length) { th.turns.push({ role: 'assistant', text: greeting, persona, ts: Date.now() }); th.updated = Date.now(); }
        });
        return json({ ok: true, sess: s3 || sess });
      }
      return json({ ok: true, sess });
    }
    if (need === 'static') {   // GH_TOKEN 無(로컬/프리뷰) = 정적 greeting(현행 온존 · UX가드4)
      const { sess: s4 } = await casPut(s => {
        const th = TH(s, persona); if (!th) return { abort: { error: '없는 대화방' } };
        if (greeting && !th.turns.length) { th.turns.push({ role: 'assistant', text: greeting, persona, ts: Date.now() }); th.updated = Date.now(); }
      });
      return json({ ok: true, sess: s4 || sess });
    }
    return json({ ok: true, sess });
  }

  if (op === 'invite') {   // 합석 초대(단톡 · 운영자 260707) — 마커+sys만 서버가 쓰고, 올지 말지는 러너가 그 캐릭터 카드·시각·관계로 판정(거절 = 콘텐츠)
    if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);
    const persona = String(body.persona || '');
    if (!ID_RE.test(persona)) return json({ error: '그런 사람은 없어', edev: '잘못된 persona id' }, 400);
    const name = stripMarkers(body.name).slice(0, 24) || persona;
    const basis = body.basis === 'moment' ? 'moment' : 'self';   // 판정 기준(운영자 260731 3선택지) — self = 나와의 관계·그 애 페르소나(종전 기본) / moment = 동석 상대와의 관계·대화 흐름. 열거 화이트리스트 = 임의 문자열 마커 유입 차단
    const t = String(body.t || (await readSess()).cur || '');   // 대상 스레드(초대 = 열린 방으로)
    if (!ID_RE.test(t)) return json({ error: '먼저 대화 상대를 뽑아줘' }, 409);
    try {   // LOCKED 스페셜 = 합석 초대도 차단(분신술 260709 — draw와 동일 서버 강제 · 캐시 5분 = 왕복 저비용)
      const rc = await fetch(`https://raw.githubusercontent.com/${REPO}/main/apps/yeta/characters/roster.json`,
        { headers: { 'user-agent': 'nomute-viewer' }, cf: { cacheTtl: 300, cacheEverything: true } });
      if (rc.ok) { const roster = await rc.json(); const rchar = Array.isArray(roster) ? roster.find(c => c && c.id === persona) : null;
        if (!rchar) return json({ error: '로스터에 없는 캐릭터야' }, 400);
        if (rchar.locked) return json({ error: '아직 열리지 않은 인물이야' }, 403); }
    } catch {}   // 로스터 조회 실패 = 통과(가용성 우선 — 러너 판정이 최종 방어선)
    let gid = '';
    const { sess, abort } = await casPut(s => {
      const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야' } };
      if (DEAD_ON(s, persona)) return { abort: { error: '지금은 부를 수 없어 — 누가 신당에서 빌어주거나, 무음동의 밤이 더 흘러야 해' } };   // 사망 = 초대 차단(260714)
      const room = Array.isArray(th.room) && th.room.length ? th.room : [t];
      if (room.includes(persona)) return { abort: { error: '이미 같이 있어' } };
      if (room.length >= MAX_ROOM) return { abort: { error: '자리가 없어 — 한 명을 보내고 불러줘' } };
      if (th.invite && Date.now() - (th.invite.ts || 0) < INVITE_TTL) return { abort: { error: '이미 누굴 부르는 중이야' } };
      if (Object.keys(s.threads).length >= 12) return { abort: { error: '방이 가득 찼어 — 오래된 방을 정리해줘' } };   // 하드 캡(draw와 동일)
      // 합석 초대 = 원본 1:1 스레드 보존, 직전 3주고받기(user 3턴까지)를 시드로 복사해 새 단톡 스레드로 분기(운영자 260712 "기존 1명 대화에서 이으면 고유성이 깨짐")
      // ⚠️ 성장 시 분기 계약(짝: yeta_chat.sh barge_check) — 방이 2명+ 되면 원본 1:1 보존 + 새 g스레드로 분기(인플레이스 변형 금지). 난입도 동형(260714). 수정 시 barge_check도 같이.
      const src = Array.isArray(th.turns) ? th.turns : [];
      let uc = 0, cut = src.length;
      for (let i = src.length - 1; i >= 0; i--) { if (src[i] && src[i].role === 'user') { uc++; if (uc >= 3) { cut = i; break; } } }
      const seed = src.slice(cut).filter(x => x && (x.role === 'user' || x.role === 'assistant'))
        .map(x => ({ role: x.role, text: x.text, ts: x.ts, ...(x.persona ? { persona: x.persona } : {}), ...(x.mood ? { mood: x.mood } : {}) }));   // sys·마커 제외 = 대사만 시드(비밀 누수 0)
      const host = room[0];
      do { gid = 'g' + Date.now().toString(36) + Math.floor(Math.random() * 1296).toString(36); } while (s.threads[gid]);   // 단톡 스레드 id = 'g' 접두(페르소나 id와 비충돌 · ID_RE 통과)
      const gth = { turns: seed, state: 'idle', opening: 0, awaiting_since: 0, err: '', room: [host],
        invite: { to: persona, ts: Date.now(), basis }, barged: 0, declined: {}, pin: 0, updated: Date.now(),
        last_sp: (th.last_sp && room.includes(th.last_sp)) ? th.last_sp : host, char_ver: '', nudge: null };
      gth.turns.push({ role: 'sys', text: `${name}${josa(name, '을', '를')} 불렀어…`, ts: Date.now(), kind: 'invite' });
      if (gth.turns.length > 200) gth.turns = gth.turns.slice(-200);   // 스레드 캡(보안 감사⑤)
      s.threads[gid] = gth;
      s.cur = gid;   // 새 단톡으로 진입
    });
    if (abort) return json(abort, 409);
    const st = await dispatch(env);
    if (st === 204) return json({ ok: true, sess });
    await casPut(s => { if (gid && s.threads[gid]) delete s.threads[gid]; if (s.cur === gid) s.cur = t; });   // 판정 런 불발 = 분기 스레드 회수·cur 원복
    return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${st}` }, 502);
  }

  if (op === 'kick') {   // 합석 내보내기/초대 철회 — 유저 쪽 거절권(난입의 대칭). 퇴장도 세계관 연출(sys)
    const persona = String(body.persona || '');
    if (!ID_RE.test(persona)) return json({ error: '그런 사람은 없어', edev: '잘못된 persona id' }, 400);
    const name = stripMarkers(body.name).slice(0, 24) || persona;
    const t = String(body.t || (await readSess()).cur || '');
    if (!ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const { sess, abort } = await casPut(s => {
      const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야' } };
      if (th.invite && th.invite.to === persona) {   // 아직 판정 전 = 부르기 취소
        th.invite = null;
        th.turns.push({ role: 'sys', text: `부르기를 관뒀어`, ts: Date.now() });
        th.updated = Date.now();
        mergeBackG(s, t);   // 취소로 혼자 남은 g방 = 즉시 1:1 재합류(Q.06 — 응답 sess부터 대화창 하나)
        return;
      }
      const room = Array.isArray(th.room) && th.room.length ? th.room : [t];
      if (!room.includes(persona)) return { abort: { error: '지금 방에 없는 사람이야' } };
      if (room.length <= 1) return { abort: { error: '마지막 한 명은 못 내보내' } };
      // 난입 등급 = 내보내기 불가(운영자 260728) — 판정에 로스터가 필요 없게 wfz.by(난입자 id · 러너가 심는다)를 그대로 쓴다(위 sweepSess 해제 판정과 같은 축 · since>0 = 그 사람이 아직 앉아 있는 창).
      // 뷰어가 pill·[보내기]를 안 그리는 것과 짝 — 여기가 최종 방어선(구버전 앱·직접 호출 우회 차단). 해제 = 인물의 <<LEAVE>> 퇴장 또는 정지 상한(FREEZE_MAX_MS) 강제 회수.
      { const f = s.wfz && typeof s.wfz === 'object' ? s.wfz : null;
        if (f && f.since && f.by === persona) return { abort: { error: '이 사람은 못 내보내 — 가는 시각도 저쪽이 정해' } }; }
      // ⚠️ 멤버 제거 계약(짝: yeta_chat.sh 사망 이탈) — room 필터 + last_sp/barged 인계를 반드시 동반. 한쪽만 고치면 헤더가 나간/죽은 인물을 가리킴(260714 사망 버그 재발원). 수정 시 사망 이탈도 같이.
      th.room = room.filter(id => id !== persona);
      if (th.last_sp === persona) th.last_sp = th.room[0];   // 주 화자가 나가면 남은 사람이 이어받음(v3 = last_sp)
      if (th.barged && th.barged.id === persona) th.barged = 0;
      th.turns.push({ role: 'sys', text: `${name}${josa(name, '은', '는')} 다음을 기약하며 물러갔다`, ts: Date.now() });
      if (th.turns.length > 200) th.turns = th.turns.slice(-200);
      th.updated = Date.now();
      mergeBackG(s, t);   // 이탈로 1명 남은 g방 = 즉시 1:1 재합류(Q.06 — 퇴장 sys까지 합쳐서 대화창 복원)
    });
    if (abort) return json(abort, 409);
    const mth = TH(sess, sess.cur || '');   // 병합이 pending을 인계했으면(인플라이트 g답장은 finish가 스레드 부재로 폐기) 즉시 재발사 = 10분 리퍼 풀대기 제거(평의회4①) — kick 유일의 dispatch 축(헤더 주석과 짝)
    if (env.GH_TOKEN && mth && mth.state === 'awaiting' && !mth.opening) { try { await dispatch(env); } catch {} }
    return json({ ok: true, sess });
  }

  if (op === 'focus') {   // 스레드 포커스 전환(단톡 등 페르소나 아닌 방 진입 — draw 없이 cur만 이동 · 운영자 260712)
    const t = String(body.t || '');
    if (!ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const { sess, abort } = await casPut(s => { if (!TH(s, t)) return { abort: { error: '없는 대화방이야' } }; s.cur = t; });
    if (abort) return json(abort, 409);
    return json({ ok: true, sess });
  }

  if (op === 'retry') {   // 자동 재시도(구 원탭 · 뷰어 260714 무배너 자동화) — 실패(state=error) 스레드의 pending 유저 턴 재발사(새 턴 추가 X)
    if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);
    const preR = await readSess();
    const t = String(body.t || preR.cur || '');
    if (!ID_RE.test(t)) return json({ error: '그런 대화방은 없어', edev: '잘못된 thread id' }, 400);
    const rn = Math.max(1, Math.min(9, Math.round(+body.n) || 1));   // 회차(사다리 260714) — 러너가 3회차부터 뉘앙스 전환 블록 주입 · 미동봉(구 캐시 뷰어) = 1(그대로 재발사) · 정수 강제 = 주입 차단
    {   // 키미 일일 실비 방파제(Q.40) — 재시도도 pending 턴에 박제된 키미 다이얼로 실과금되는 경로(상한 우회 차단) · 클로드 턴 재시도 무영향 · 스레드 판독 실패 = 통과(fail-open · 아래 casPut이 실존 재검증)
      const th = TH(preR, t), tn = (th && th.turns) || [], la = tn.map(x => x.role).lastIndexOf('assistant');
      if (tn.slice(la + 1).some(x => x && x.role === 'user' && KIMI_COST[x.model])) { const kb = kimiGate(env, preR); if (kb) return json(kb, 429); }
    }
    const { abort } = await casPut(s => {
      const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야' } };
      if (DEAD_ON(s, t)) return { abort: { error: '지금은 연락이 닿지 않아' } };   // 사망 방 = 재발사 금지(260714)
      const turns = th.turns || [];
      const lastA = turns.map(x => x.role).lastIndexOf('assistant');
      if (!turns.slice(lastA + 1).some(x => x.role === 'user')) return { abort: { error: '재시도할 메시지가 없어' } };
      th.state = 'awaiting'; th.awaiting_since = Date.now(); th.err = ''; th.retry_n = rn;
    });
    if (abort) return json(abort, 409);
    const rst = await dispatch(env);
    if (rst === 204) return json({ ok: true });
    await casPut(s => { const th = TH(s, t); if (th) { th.state = 'error'; th.err = `재발사 실패(GitHub ${rst})`; th.awaiting_since = 0; } });
    return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${rst}` }, 502);
  }

  if (op === 'att') {   // 첨부 사진 서빙(운영자 260717 '+') — 비공개 버킷 att/ 프리픽스만(op voice 동형 · originOk 게이트 · POST 유지)
    const key = String(body.key || '');
    if (!/^att\/[a-z0-9_-]{1,24}\/[a-z0-9]{1,16}\.jpg$/.test(key)) return json({ error: '잘못된 키' }, 400);
    const o = await env.YETA_R2.get(key);
    if (!o) return json({ error: '사진 없음' }, 404);
    return new Response(o.body, { headers: { 'content-type': 'image/jpeg', 'cache-control': 'private, max-age=86400' } });
  }

  if (op === 'attach') {   // 사진 첨부(운영자 260717 '+') — R2 att/ 저장 + 유저 턴 적재(img 키) + dispatch(러너가 Read로 실물을 보고 반응) · ⚠️ 무인증 공개 → 크기·매직바이트·일 상한 가드
    if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);
    const b64 = String(body.img || '');
    if (!b64 || b64.length > 2000000) return json({ error: '사진이 없거나 너무 커 — 다시 골라줘(최대 ~1.4MB)' }, 400);
    let bin;
    try { bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0)); } catch { return json({ error: '잘못된 이미지 데이터' }, 400); }
    if (bin.length < 64 || bin[0] !== 0xFF || bin[1] !== 0xD8) return json({ error: 'JPEG만 받을 수 있어' }, 400);   // 클라 파이프 = canvas JPEG 고정 — 매직바이트 검증(마임 위장·임의 파일 저장 차단)
    let acap = parseInt(env.YETA_ATT_MAX_PER_DAY ?? '30', 10);
    if (!Number.isFinite(acap)) acap = 30;   // 미설정·오타 = 보수 기본 30(R2 저장 + 비전 토큰 가드 · ring 동형)
    const akst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
    const aqkey = `quota/att-${akst}.json`;
    let aused = 0;
    const aqo = await env.YETA_R2.get(aqkey);
    if (aqo) { try { aused = (await aqo.json()).n || 0; } catch { aused = 0; } }
    if (acap > 0 && aused >= acap) return json({ error: `오늘 사진 상한(${acap}장) 도달 — 내일 다시`, remain: 0 }, 429);
    let amodel = String(body.model || ''); let aeffort = String(body.effort ?? 'low');
    if (!MODELS.has(amodel)) amodel = 'claude-opus-5';
    if (!EFFORTS.has(aeffort)) aeffort = 'low';
    const preS = await readSess();
    const at = String(body.t || preS.cur || '');
    if (!ID_RE.test(at)) return json({ error: '먼저 대화방을 열어줘' }, 409);
    if (!TH(preS, at)) return json({ error: '없는 대화방이야 — 캐릭터 탭에서 열어줘' }, 409);   // ⚠️ R2 put '이전' 방 실존 선검증(평의회 260717 HIGH — 가짜 방 id 반복 = 상한 우회 무한 고아 객체 적재 DoS 차단 · 최종 판정은 아래 casPut이 재확인)
    if (DEAD_ON(preS, at)) return json({ error: '…지금은 연락이 닿지 않아. 누가 신당에서 빌어주면 바로, 아니면 무음동 이틀은 지나야 돌아와' }, 409);
    if (KIMI_COST[amodel]) { const kb = kimiGate(env, preS); if (kb) return json(kb, 429); }   // 키미 일일 실비 방파제(Q.40) — 첨부 상한 소비·R2 저장 전 차단(비전 턴 = 이미지 토큰까지 실과금 축)
    await env.YETA_R2.put(aqkey, JSON.stringify({ n: aused + 1 }), { httpMetadata: { contentType: 'application/json' } });   // 상한 = 시도 즉시 소비(pinset 결 — put까지 간 시도는 실패해도 카운트 = 저장 축 남용 하드캡)
    const akey = `att/${at}/${Date.now().toString(36)}.jpg`;
    await env.YETA_R2.put(akey, bin.buffer, { httpMetadata: { contentType: 'image/jpeg' } });   // 이미지 저장 → 턴 적재(러너가 턴을 집는 순간 실물 보장 · CAS abort 시 고아 객체 = 상한 안에서 유계)
    const { abort } = await casPut(s => {
      const th = TH(s, at); if (!th) return { abort: { error: '없는 대화방이야 — 캐릭터 탭에서 열어줘' } };
      if (DEAD_ON(s, at)) return { abort: { error: '…지금은 연락이 닿지 않아. 누가 신당에서 빌어주면 바로, 아니면 무음동 이틀은 지나야 돌아와' } };
      th.turns.push({ role: 'user', text: '', img: akey, ts: Date.now(), model: amodel, effort: aeffort });
      if (th.turns.length > 200) th.turns = th.turns.slice(-200);
      th.state = 'awaiting'; th.awaiting_since = Date.now(); th.err = ''; delete th.retry_n; th.rd = 0;
      th.updated = Date.now();
      s.cur = at; s.pref = { model: amodel, effort: aeffort };
    });
    if (abort) return json(abort, 409);
    const ast = await dispatch(env);
    if (ast === 204) return json({ ok: true, key: akey, remain: acap > 0 ? acap - aused - 1 : -1 });
    await casPut(s => { const th = TH(s, at); if (th) { th.state = 'error'; th.err = `발사 실패(GitHub ${ast}) — 다시 보내면 재시도`; th.awaiting_since = 0; } });
    return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${ast}` }, 502);
  }

  if (op !== 'send') return json({ error: '지금은 그렇게 못 해', edev: `알 수 없는 op(${op})` }, 400);
  if (!env.GH_TOKEN) return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: 'GH_TOKEN 미설정' }, 500);

  // 유저 텍스트 절제 + 프롬프트 델리미터 위장 무력화(yeta_chat.sh 관대 파서와 짝 · stripMarkers 고정점 SSOT = 중첩 마커 붕괴)
  const text = stripMarkers(String(body.text || '').slice(0, 4000)).trim();
  if (!text) return json({ error: '할 말을 적어줘' }, 400);

  // 다이얼(모델×노력) — 화이트리스트 강제(오타·주입 = 기본 폴백 · 30초 목표라 effort 기본 low)
  let model = String(body.model || '');
  let effort = String(body.effort ?? 'low');
  if (!MODELS.has(model)) model = 'claude-opus-5';
  if (!EFFORTS.has(effort)) effort = 'low';

  // 채팅 상한 폐지(운영자 260706 — env YETA_MAX_PER_DAY 축 제거·무제한. 사용자별 상한은 후속 보류) · 카운터는 관측용 상시 기록 유지(KST 일자 키)
  const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(2, 10).replace(/-/g, '');
  const qkey = `quota/${kst}.json`;
  let used = 0;
  const qo = await env.YETA_R2.get(qkey);
  if (qo) { try { used = (await qo.json()).n || 0; } catch { used = 0; } }

  const preS2 = await readSess();
  if (KIMI_COST[model]) { const kb = kimiGate(env, preS2); if (kb) return json(kb, 429); }   // 키미 일일 실비 방파제(Q.40) — 턴 append 전 차단 = 헛dispatch 0 · 다이얼 전환 시 즉시 재개
  const t = String(body.t || preS2.cur || '');   // 대상 스레드(v3) — 미지정 = 현재 방
  if (!ID_RE.test(t)) return json({ error: '상대를 못 찾았어 — 캐릭터 탭에서 다시 열어줘', edev: `스레드 id 형식 불일치` }, 409);
  const { abort } = await casPut(s => {
    const th = TH(s, t); if (!th) return { abort: { error: '없는 대화방이야 — 캐릭터 탭에서 열어줘' } };
    if (DEAD_ON(s, t)) return { abort: { error: '…지금은 연락이 닿지 않아. 누가 신당에서 빌어주면 바로, 아니면 무음동 이틀은 지나야 돌아와' } };   // 사망 두절(운영자 260714 · 260725 하한) — 1:1 방 발신 차단(단톡 g방 = dead 키 아님 = 통과 · 생존자와 계속)
    const turn = { role: 'user', text, ts: Date.now(), model, effort };   // 다이얼 = 턴별 박제
    if (body.ptt) turn.ptt = 1;   // 무전기(PTT) 턴 박제
    if (body.sc) turn.sc = 1;   // 상황 설명 턴(운영자 260714 '#' 모드) — 상대에게 하는 말이 아니라 장면 설정(러너 격리 주입 · 뷰어 .ysit 렌더) · 불리언만 = 주입 축 없음
    if (body.far) turn.far = 1;   // 원거리 턴(운영자 260714) — 상대 다른 장소 = 러너가 물리 접촉·같은 공간 전제 금지 주입(불리언만)
    th.turns.push(turn);
    if (th.turns.length > 200) th.turns = th.turns.slice(-200);   // 스레드 캡(보안 감사⑤)
    th.state = 'awaiting'; th.awaiting_since = Date.now(); th.err = ''; delete th.retry_n; th.rd = 0;   // 새 유저 턴 = 재시도 사다리 리셋(뉘앙스 블록 잔류 차단 · 260714)
    delete th.gb;   // 단톡 자율 비트 예약 취소(260725) — 내가 끼어들면 너희끼리 하던 차례는 끝(러너도 pending 우선이라 안 태우지만, 여기서 지워야 뷰어 타이핑 점이 '내 답장 대기'로 즉시 정정된다)
    delete th.picks;   // 미연시 선택지 소거(260725) — 골랐든 직접 썼든 내 턴이 나간 순간 그 갈림길은 끝(다음 답이 새로 제안한다)
    th.updated = Date.now();
    s.cur = t;   // 발신 = 현재 방 확정(푸시 딥링크·phone 발신자 정본 · 러너 감사⑤B)
    s.pref = { model, effort };
  });
  if (abort) return json(abort, 409);
  await env.YETA_R2.put(qkey, JSON.stringify({ n: used + 1 }), { httpMetadata: { contentType: 'application/json' } });

  const st = await dispatch(env);
  if (st === 204) return json({ ok: true });
  // dispatch 실패 = 답장 올 런이 없음 → awaiting 고착 방지: 스레드 error 롤백
  await casPut(s => { const th = TH(s, t); if (th) { th.state = 'error'; th.err = `발사 실패(GitHub ${st}) — 다시 보내면 재시도`; th.awaiting_since = 0; } });
  return json({ error: '지금은 말이 닿지 않아 — 잠시 후 다시', edev: `GitHub dispatch ${st}` }, 502);
}

async function dispatch(env, wf = 'yeta-chat.yml', inputs = { char: 'main' }) {   // 워크플로 기동(기본 = 챗 · 단일 스레드 = char 'main' 고정 → concurrency 직렬 / ring = yeta-call.yml)
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${wf}/dispatches`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.GH_TOKEN}`,
      accept: 'application/vnd.github+json',
      'user-agent': 'nomute-viewer',
      'x-github-api-version': '2022-11-28',
    },
    body: JSON.stringify({ ref: 'main', inputs }),
  });
  return r.status;
}

function originOk(request) {   // publish.js originOk 계승 — 상태변경 POST 는 동일출처만(CSRF)
  const o = request.headers.get('origin');
  if (!o) return false;
  try { const h = new URL(o).hostname; return h.endsWith('.pages.dev') || h === 'soong.kr' || h.endsWith('.soong.kr'); } catch { return false; }   // 커스텀 도메인 = soong.kr(루트+서브 · 260704 · nomute 도메인 미사용) · 도메인 추가 시 || 이어붙임
}
