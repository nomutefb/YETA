// 회귀 하니스 — 웹푸시 구독(op push) + 방별 톡 알림(op mute) · 260809 신설
// 실행: node tests/test_push_mute.mjs   (의존 0 · R2·Request는 스텁/Node 내장)
// 지키는 계약: 구독 중복 0 · 비-https/keys 누락 거절 · off = 그 기기만 회수 · mute 켬 = 키 삭제(기본 ON) · 없는 방 거절
import { onRequestPost } from '../functions/api/yeta.js';

// ── R2 스텁(세션 + 구독 키 2개) ──
const store = new Map();
const enc = o => JSON.stringify(o);
const mkObj = (txt, etag='"e1"') => ({ json: async () => JSON.parse(txt), text: async () => txt, httpEtag: etag, etag });
const R2 = {
  async get(k) { return store.has(k) ? mkObj(store.get(k)) : null; },
  async put(k, v) { store.set(k, typeof v === 'string' ? v : String(v)); return { httpEtag: '"e1"' }; },
  async delete(k) { store.delete(k); },
  async head(k) { return store.has(k) ? { httpEtag: '"e1"' } : null; },
};
const env = { YETA_R2: R2, GH_TOKEN: 't', YETA_PIN: '' };
const post = async body => {
  const req = new Request('https://x/api/yeta', { method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://yeta.pages.dev' }, body: JSON.stringify(body) });
  const res = await onRequestPost({ request: req, env });
  let j = null; try { j = await res.json(); } catch (e) {}
  return { status: res.status, j };
};
const SUB = ep => ({ endpoint: ep, keys: { p256dh: 'p', auth: 'a' } });

let pass = 0, fail = 0;
const t = (name, ok, extra='') => { ok ? pass++ : fail++; console.log(`${ok ? '✓' : '✗'} ${name}${extra ? ' — ' + extra : ''}`); };

// 세션 시드(스레드 1개)
store.set('sessions/main.json', enc({ cur: 'lucy', threads: { lucy: { room: ['lucy'], turns: [] } }, updated: 1 }));

// ① op push — 구독 적재
let r = await post({ op: 'push', sub: SUB('https://fcm.example/a') });
t('op push 저장', r.status === 200 && r.j?.ok && r.j.n === 1, JSON.stringify(r.j));
// ② 같은 endpoint 재구독 = 교체(중복 0)
r = await post({ op: 'push', sub: SUB('https://fcm.example/a') });
t('재구독 = 교체(중복 없음)', r.j?.n === 1, 'n=' + r.j?.n);
// ③ 다른 기기 추가
r = await post({ op: 'push', sub: SUB('https://fcm.example/b') });
t('다른 기기 추가', r.j?.n === 2, 'n=' + r.j?.n);
// ④ 잘못된 구독 거절
r = await post({ op: 'push', sub: { endpoint: 'http://insecure/x', keys: { p256dh: 'p', auth: 'a' } } });
t('비-https 거절', r.status === 400, 'status=' + r.status);
r = await post({ op: 'push', sub: { endpoint: 'https://fcm.example/c' } });
t('keys 누락 거절', r.status === 400, 'status=' + r.status);
// ⑤ off = 회수
r = await post({ op: 'push', off: 1, endpoint: 'https://fcm.example/a' });
t('off = 해당 기기만 회수', r.j?.n === 1, 'n=' + r.j?.n);
const left = JSON.parse(store.get('push/subs.json'));
t('남은 구독 = b', left.length === 1 && left[0].endpoint === 'https://fcm.example/b', JSON.stringify(left.map(x=>x.endpoint)));

// ⑥ op mute — 끄기/켜기
r = await post({ op: 'mute', t: 'lucy', on: false });
t('mute 끄기', r.j?.ok && r.j.on === false, JSON.stringify(r.j));
t('세션에 mute=1 박제', JSON.parse(store.get('sessions/main.json')).threads.lucy.mute === 1);
r = await post({ op: 'mute', t: 'lucy', on: true });
t('mute 켜기', r.j?.ok && r.j.on === true, JSON.stringify(r.j));
t('켜면 키 삭제(기본=켜짐)', !('mute' in JSON.parse(store.get('sessions/main.json')).threads.lucy));
// ⑦ 없는 방
r = await post({ op: 'mute', t: 'nosuch', on: false });
t('없는 방 = 거절', r.status === 409 || !!r.j?.error, 'status=' + r.status + ' ' + JSON.stringify(r.j));

console.log(`\n결과: ${pass} 통과 / ${fail} 실패`);
process.exit(fail ? 1 : 0);
