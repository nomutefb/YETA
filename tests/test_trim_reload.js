#!/usr/bin/env node
/**
 * 방 재진입 「직전 대화 다시 로딩」 회귀 하니스 (260809 Q.166 · 운영자 "직전 대화가 다시 로딩되는거 같은데")
 *
 * 무엇을 지키나 — 세 조각이 겹쳐야 터지는 결함이라 눈검증이 반복해서 놓쳤다:
 *   ① op get은 비활성 방을 꼬리 2턴으로 절단해 보낸다(trim=원턴수 · 페이로드 방어 — test_bond_trim의 그 절단).
 *   ② 낙관적 재진입(260712)은 그 절단본을 draw 왕복 '전에' 즉시 그린다(_yLastN=2로 착지).
 *   ③ draw 전체본이 도착하면 fresh = i >= prevN(2) 판정이 옛 대화 전체를 신규 턴으로 오인
 *      → 히스토리 통째 등장 애니(.in) 재생 = 「직전 대화가 다시 로딩」 체감(수정 전 실측 = 42턴 중 41노드 재생).
 * 계약: 절단본→전체본 전환 렌더 = 첫 렌더 취급(전체 무애니 · _yWasTrim 래치) · 히스토리 42행 무손실.
 *
 * 재현 조건(1차 하니스의 함정 2개 — 기록):
 *   ⓐ 방 A에 먼저 들어가 YSESS를 세운 '뒤' 방 B로 전환해야 절단본 캐시 경로가 산다(콜드 첫 진입 = YSESS 空 = 낙관 렌더 스킵).
 *   ⓑ 재생은 일시적이다 — 다음 렌더(답장 페이스 타이머)가 reconcile로 .in을 벗겨 스냅샷 1방이면 놓친다
 *      → MutationObserver로 '한 번이라도 .in으로 붙은' 노드를 누계한다.
 *
 * 실행: node tests/test_trim_reload.js [--report] [--strict]
 * 의존성: playwright + chromium(백스택 하니스와 동일 탐색) — 없으면 스킵 + rc=0(--strict로 뒤집기).
 */
'use strict';
const fs = require('fs');
const http = require('http');
const path = require('path');

const ROOT = path.dirname(__dirname);
const VIEWER = path.join(ROOT, 'viewer');
const REPORT = process.argv.includes('--report');
const STRICT = process.argv.includes('--strict');

function loadPlaywright() {
  const cands = ['playwright', '/opt/node22/lib/node_modules/playwright', '/usr/lib/node_modules/playwright', '/usr/local/lib/node_modules/playwright'];
  for (const c of cands) { try { return require(c); } catch {} }
  return null;
}
function findChromium() {
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH, '/opt/pw-browsers'].filter(Boolean);
  for (const r of roots) {
    let dirs = []; try { dirs = fs.readdirSync(r); } catch { continue; }
    for (const d of dirs.filter(x => x.startsWith('chromium')).sort().reverse())
      for (const rel of ['chrome-linux/chrome', 'chrome-linux/headless_shell']) {
        const p = path.join(r, d, rel); if (fs.existsSync(p)) return p;
      }
  }
  return null;
}
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp' };
function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'index.html';
      const f = path.join(VIEWER, rel);
      if (!f.startsWith(VIEWER) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end('nf'); }
      res.writeHead(200, { 'content-type': MIME[path.extname(f).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(f).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

// ── 세션 재료 — A방(6턴)에서 대화 후 B방(42턴 · 절단본 캐시)으로 전환(운영자 260809 실사용 = 한나↔루시 왕복) ──
const A = 'winter', B = 'lucy';
function mk(n, who) { const t0 = Date.now() - n * 60000, a = []; for (let i = 0; i < n; i++) a.push(i % 2 === 0 ? { role: 'user', text: `내 말 ${who} ${i}`, ts: t0 + i * 60000 } : { role: 'assistant', persona: who, text: `${who} 답 ${i}`, ts: t0 + i * 60000 }); return a; }
const FA = mk(6, A), FB = mk(42, B);
const th = (who, turns) => ({ turns, state: 'idle', opening: 0, room: [who], pin: 0, updated: Date.now(), last_sp: who });
const trim = (who, full) => ({ ...th(who, full.slice(-2)), trim: full.length, uturns: Math.ceil(full.length / 2) });   // 게이트웨이 op get 절단 계약 미러(slice(-2)+trim+uturns)
const base = () => ({ v: 3, cur: '', barge_day: '', call: null, note_pub: '', notes: {}, tunes: {}, policy: {}, pref: {}, me: { call: '', about: '' } });

(async () => {
  const pw = loadPlaywright(), exe = findChromium();
  if (!pw || !exe) {
    console.log('SKIP: playwright/chromium 없음' + (STRICT ? '' : ' (커밋 비차단 · --strict로 뒤집기)'));
    process.exit(STRICT ? 1 : 0);
  }
  let fail = 0;
  const ok = (cond, msg, det) => { console.log((cond ? '✅' : '❌') + ' ' + msg + (det ? ` — ${det}` : '')); if (!cond) fail++; };

  const srv = await serve();
  const BASE = `http://127.0.0.1:${srv.address().port}/index.html?qa=1`;
  const browser = await pw.chromium.launch({ executablePath: exe, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  let roster = [], world = null;
  try { roster = JSON.parse(fs.readFileSync(path.join(ROOT, 'apps/yeta/characters/roster.json'), 'utf8')); } catch {}
  try { const w = JSON.parse(fs.readFileSync(path.join(ROOT, 'apps/yeta/worlds.json'), 'utf8')); world = (w.seasons || []).find(s => s.id === w.active) || null; } catch {}
  let cur = A;   // 서버 상태 — draw/focus {persona|t}가 cur 이동 = 비활성 방 절단 재현
  const sess = () => { const s = base(); s.cur = cur;
    s.threads = { [A]: cur === A ? th(A, FA) : trim(A, FA), [B]: cur === B ? th(B, FB) : trim(B, FB) }; return s; };
  await page.route('**/api/yeta', async route => {
    const b = JSON.parse(route.request().postData() || '{}');
    let j = { ok: true };
    if (b.op === 'chars') j = { ok: true, chars: roster, world, ready: true };
    else if (b.op === 'get') j = { ok: true, sess: sess() };
    else if (b.op === 'draw') { cur = String(b.persona || cur); j = { ok: true, sess: sess() }; }
    else if (b.op === 'focus') { cur = String(b.t || cur); j = { ok: true, sess: sess() }; }
    else if (b.op === 'watch') { await new Promise(r => setTimeout(r, 900)); j = { ok: true, etag: 'e1', detag: '', none: true }; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(j) });
  });

  try {
    await page.goto(BASE, { waitUntil: 'load' });
    await page.waitForTimeout(3400);   // 언락 안무
    await page.evaluate(a => openYeta(a), A);   // A방 진입 = YSESS 구축(B = 절단본 캐시로 적재)
    await page.waitForTimeout(1500);
    const pre = await page.evaluate(b => ({ n: ((YSESS || {}).threads || {})[b] ? YSESS.threads[b].turns.length : -1, trim: (((YSESS || {}).threads || {})[b] || {}).trim || 0 }), B);
    ok(pre.n === 2 && pre.trim === FB.length, '전환 직전 B방 = 절단본 캐시(꼬리 2턴 + trim)', `n=${pre.n} trim=${pre.trim}`);
    await page.evaluate(() => {   // '한 번이라도 .in으로 붙은' 노드 누계 — 재생은 일시적이라 스냅샷으론 못 잡는다
      window._everIn = 0;
      new MutationObserver(ms => { for (const m of ms) for (const n of m.addedNodes) { if (n.nodeType === 1) { const c = (n.classList && n.classList.contains('in') ? 1 : 0) + (n.querySelectorAll ? n.querySelectorAll('.in').length : 0); if (c) window._everIn += c; } } }).observe(document.getElementById('yetaLog'), { childList: true, subtree: true });
    });
    await page.evaluate(b => openYeta(b), B);   // B방 전환 = 절단본 낙관 렌더 → draw 전체본
    await page.waitForTimeout(3000);
    const fin = await page.evaluate(() => ({ ever: window._everIn, rows: document.querySelectorAll('#yetaLog .ymsg,#yetaLog .ymrow').length }));
    if (REPORT) console.log(`  [실측] 재생 노드 누계=${fin.ever} · 렌더 행=${fin.rows} (수정 전 기준치 = 41 재생)`);
    ok(fin.rows >= FB.length, `전환 후 전체 히스토리 렌더(${FB.length}행 무손실)`, `rows=${fin.rows}`);
    ok(fin.ever === 0, '절단본→전체본 전환 = 무애니(직전 대화 재로딩 0)', `everIn=${fin.ever}`);
    ok(errors.length === 0, 'JS 실에러 0', errors.join(' | ').slice(0, 200));
  } finally { await browser.close(); srv.close(); }
  process.exit(fail ? 1 : 0);
})();
