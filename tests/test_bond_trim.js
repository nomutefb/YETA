#!/usr/bin/env node
/**
 * 절단 내성 친밀도 + 해금 영속 회귀 (260804 평의회 #3·#4·#5·#11)
 *
 * 무엇을 지키나 — 세 계약이 **같은 뿌리**(op get이 비활성 방을 꼬리 2턴으로 절단해 보낸다)에서 나온다:
 *   ① yUTurns  = 절단본을 세지 않고 게이트웨이가 실어 보낸 원본 유저 발화 수(uturns)를 쓴다.
 *   ② yBond·yFarOK = 그 값을 쓰므로, 24h 방치한 핀 방이 「소원」으로 잠기거나 원거리가 상시 차단되지 않는다.
 *   ③ yUnmet   = 방이 휘발로 소멸해도 sess.met[id] 가 있으면 다시 ???로 재잠기지 않는다.
 *
 * 방식 = 순수 함수 이식 검증(뷰어 DOM 무의존) — viewer/index.html 의 해당 함수 본문을 여기에 **복제하지 않고**
 * 계약만 재현한다(복제 = 드리프트). 실제 함수 문자열은 아래 §정합 검사에서 index.html 을 읽어 확인한다.
 */
const fs = require('fs');
const path = require('path');
const SRC = fs.readFileSync(path.join(__dirname, '..', 'viewer', 'index.html'), 'utf8');
const GW = fs.readFileSync(path.join(__dirname, '..', 'functions', 'api', 'yeta.js'), 'utf8');

let fail = 0;
const ok = (cond, msg) => { if (!cond) { console.error('❌', msg); fail++; } };

// ── ① 게이트웨이가 uturns 를 실어 보내는가(절단과 같은 자리) ──
ok(/uturns:\s*\(th\.turns \|\| \[\]\)\.filter\(x => x && x\.role === 'user'\)\.length/.test(GW),
   'op get 절단부에 uturns(원본 유저 발화 수) 동봉이 없다');
ok(/slice\(-2\), trim:/.test(GW), '절단(꼬리 2턴) 자체는 유지돼야 한다(페이로드 방어)');

// ── ② 뷰어가 uturns 를 소비하는가 ──
ok(/function yUTurns\(th\)/.test(SRC), 'yUTurns SSOT가 없다');
ok(/const n = yUTurns\(th\); if \(!n\) return 0;/.test(SRC), 'yBond가 yUTurns를 안 쓴다(절단본 카운트 잔존)');
ok(/function yFarOK\(c\) \{ const th = YTH\(c && c\.id\); return yUTurns\(th\) >= yFarNeed\(c\); \}/.test(SRC),
   'yFarOK가 yUTurns를 안 쓴다');
ok(/const _u = yUTurns\(t\[id\]\);/.test(SRC), '프로필 통계(yProfDerive)가 절단 보정을 안 한다');
ok(!/const n = \(th\.turns \|\| \[\]\)\.filter\(t => t\.role === 'user'\)\.length; if \(!n\) return 0;/.test(SRC),
   '구 yBond 카운트(절단본 순회)가 남아 있다');

// ── ③ 해금 영속 ──
ok(/if \(\(\(YSESS \|\| \{\}\)\.met \|\| \{\}\)\[c\.id\]\) return false;/.test(SRC),
   'yUnmet이 세션 영속 met 키를 안 본다');
ok(/s\.met = s\.met \|\| \{\};/.test(GW), 'sweepSess가 방 소멸 전에 met를 박제하지 않는다');
ok(/for \(const mid of \[tid, \.\.\.\(\(th\.room \|\| \[\]\)/.test(GW), '단톡(room) 멤버까지 met 박제가 안 된다');

// ── ④ 계약 시뮬 — 24h 방치한 핀 방(원본 40턴, 절단 2턴)이 잠기지 않는가 ──
const yUTurns = th => {
  if (!th) return 0;
  const u = th.uturns;
  if (Number.isFinite(+u)) return Math.max(+u, (th.turns || []).filter(t => t && t.role === 'user').length);
  return (th.turns || []).filter(t => t && t.role === 'user').length;
};
const YBOND_ESTRANGED = 1.5;
const bond = th => {                                   // yBond 커브 이식(감쇠 공식 = 뷰어와 같은 식)
  const n = yUTurns(th); if (!n) return 0;
  const d = Math.max(0, (Date.now() - (th.updated || 0)) / 86400e3);
  const t = Math.min(1, Math.max(0, (d - 1) / 6)), ease = t * t * (3 - 2 * t);
  return n * (1 - .5 * ease);
};
const pinned24h = { pin: 1, updated: Date.now() - 24 * 3600e3, uturns: 40,
                    turns: [{ role: 'user', text: 'x' }, { role: 'assistant', text: 'y' }] };
ok(bond(pinned24h) >= YBOND_ESTRANGED, `24h 방치 핀 방(원본 40턴)이 소원 판정에 걸린다 — bond=${bond(pinned24h).toFixed(2)}`);
const legacy = { updated: Date.now(), turns: [{ role: 'user' }, { role: 'user' }] };   // uturns 없는 구 응답 = 종전 동작
ok(bond(legacy) === 2, `구 응답(uturns 없음) 폴백이 깨졌다 — bond=${bond(legacy)}`);
const fresh = { updated: Date.now(), uturns: 2, turns: [{ role: 'user' }, { role: 'user' }, { role: 'user' }] };   // 절단 뒤 새 턴 = max로 흡수
ok(yUTurns(fresh) === 3, `절단 뒤 새 턴 흡수(max) 실패 — ${yUTurns(fresh)}`);

if (fail) { console.error(`\n❌ 절단 내성/해금 영속 회귀 — ${fail}건 실패`); process.exit(1); }
console.log('✅ 절단 내성 친밀도 + 해금 영속 — 11개 계약 통과(게이트웨이 동봉·뷰어 소비·구응답 폴백·핀 방 잠금 해소 포함).');
