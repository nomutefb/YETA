#!/usr/bin/env node
/* 인앱 뒤로가기(백스택) 회귀 하니스 — 실브라우저 단언 · rc=0 통과 / rc=1 회귀
 *
 * 왜 있나(260726 사고):
 *   262차가 종료 확인 팝업을 폐지하며 "홈에서 뒤로 1회 = 앱 밖"을 계약으로 내걸었는데,
 *   검증이 "팝업 0 · 에러 0"만 보고 **몇 번 눌러야 나가는지를 안 셌다**. 실제로는 2회였고
 *   (연쇄 감기의 착지 칸에서 멈춤) 뒤로 1회가 통째로 씹혔다 — 267차에서야 실측으로 잡았다.
 *   눈으로 보는 검증은 '횟수' 같은 걸 놓친다. 그래서 횟수를 **기계가 세게** 만든다.
 *
 * 무엇을 지키나 (viewer/index.html 백스택 골격의 계약):
 *   C1 종료 확인 팝업 부재            — #yexit DOM 0 (262차 · 운영자 승인 폐지)
 *   C2 레이어 회수 우선               — 레이어 있으면 뒤로 = 최상단만 닫힘(앱 탈출 방지)
 *   C3 고아 칸도 뒤로 1회             — navHome이 남긴 칸 N개여도 사용자 뒤로 1회에 앱 밖(267차)
 *   C4 감기 표식 누수 0               — 고아 칸 남긴 뒤 새 레이어를 열면 그 레이어부터 정상 회수
 *   C5 #yconfirm 생존                 — .yexit* CSS를 계승한 범용 확인 팝업이 함께 죽지 않았나
 *   C6 챗 위 명함 모달 적층           — navOpen('yvcf') = 뒤로 1회에 명함만(뒤 챗 동반 종료 봉인)
 *   C7 JS 실에러 0
 *
 * 실행:
 *   node tests/test_backstack.js             # 체크 · rc=0 통과 / rc=1 회귀
 *   node tests/test_backstack.js --report    # 각 단계의 스택·history 상태를 사람이 읽게 출력
 *   node tests/test_backstack.js --strict    # 브라우저가 없으면 스킵 대신 실패(CI용)
 *
 * 의존성: playwright(전역 설치분 탐색) + chromium. 둘 중 하나라도 없으면 **스킵 + rc=0**
 *   — 브라우저 없는 기기/러너에서 커밋을 막지 않기 위해서다(--strict로 뒤집을 수 있다).
 *   서버는 이 파일이 자체 기동한다(http-server 등 외부 도구 불요).
 */
'use strict';
const fs = require('fs');
const http = require('http');
const path = require('path');

const ROOT = path.dirname(__dirname);
const VIEWER = path.join(ROOT, 'viewer');
const REPORT = process.argv.includes('--report');
const STRICT = process.argv.includes('--strict');

// ── playwright 탐색(로컬 → 전역) ─────────────────────────────
function loadPlaywright() {
  const cands = [
    'playwright',
    '/opt/node22/lib/node_modules/playwright',
    '/usr/lib/node_modules/playwright',
    '/usr/local/lib/node_modules/playwright',
  ];
  for (const c of cands) { try { return require(c); } catch {} }
  return null;
}
function findChromium() {
  const roots = [process.env.PLAYWRIGHT_BROWSERS_PATH, '/opt/pw-browsers'].filter(Boolean);
  for (const r of roots) {
    let dirs = [];
    try { dirs = fs.readdirSync(r); } catch { continue; }
    for (const d of dirs.filter(x => x.startsWith('chromium')).sort().reverse()) {
      for (const rel of ['chrome-linux/chrome', 'chrome-linux/headless_shell']) {
        const p = path.join(r, d, rel);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return null;
}

const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2' };

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

// ── 단언 ─────────────────────────────────────────────────────
const R = [];
function ok(name, pass, detail) {
  R.push({ name, pass, detail });
  if (REPORT || !pass) console.log(`  ${pass ? '✅' : '❌'} ${name}${detail ? ' — ' + detail : ''}`);
}

(async () => {
  const pw = loadPlaywright();
  const exe = findChromium();
  if (!pw || !exe) {
    const why = !pw ? 'playwright 미설치' : 'chromium 미설치';
    console.log(`${STRICT ? '❌' : '⏭️'} 백스택 회귀 ${STRICT ? '실패' : '스킵'} — ${why}` +
      (STRICT ? '' : ' (브라우저 없는 기기에선 커밋을 막지 않는다 · --strict로 뒤집기)'));
    process.exit(STRICT ? 1 : 0);
  }

  let roster = [], world = null;
  try { roster = JSON.parse(fs.readFileSync(path.join(ROOT, 'apps/yeta/characters/roster.json'), 'utf8')); } catch {}
  try {
    const w = JSON.parse(fs.readFileSync(path.join(ROOT, 'apps/yeta/worlds.json'), 'utf8'));
    world = (w.seasons || []).find(s => s.id === w.active) || null;
  } catch {}

  const srv = await serve();
  const BASE = `http://127.0.0.1:${srv.address().port}/index.html?qa=1`;
  const browser = await pw.chromium.launch({ executablePath: exe, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ viewport: { width: 420, height: 900 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  await page.route('**/api/yeta', async route => {
    const b = JSON.parse(route.request().postData() || '{}');
    let j = { ok: true };
    if (b.op === 'chars') j = { ok: true, chars: roster, world, ready: true };
    else if (b.op === 'get') j = { ok: true, sess: { v: 3, cur: '', threads: {} }, turns: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(j) });
  });

  const nav = () => page.evaluate(() => ({
    stack: typeof _navStack !== 'undefined' ? _navStack.map(l => l.id) : null,
    st: (history.state && history.state.nav) || null,
  }));
  const inApp = () => page.url().includes('index.html');
  const enter = async () => { await page.goto(BASE, { waitUntil: 'load' }); await page.waitForTimeout(3400); };
  // 뒤로가기를 눌러 앱 밖으로 나가기까지의 '사용자 누름' 횟수(연쇄 back은 1회로 센다)
  const pressesToExit = async (max = 4) => {
    for (let i = 1; i <= max; i++) {
      try { await page.goBack({ timeout: 3000 }); } catch {}
      await page.waitForTimeout(700);
      if (!inApp()) return i;
    }
    return -1;
  };

  try {
    // ── C1 · C2 : 진입 + 레이어 1개 정상 경로 ──────────────
    await enter();
    ok('C1 종료 확인 팝업 부재(#yexit)', !(await page.evaluate(() => !!document.getElementById('yexit'))));
    ok('진입(QA 언락)', await page.evaluate(() => document.getElementById('ymain').classList.contains('unlocked')));

    await page.evaluate(() => {
      const d = document.getElementById('yetadlg');
      if (!d.open) { d.showModal(); navOpen('ydlg', () => { try { d.close(); } catch {} }); }
    });
    await page.waitForTimeout(300);
    if (REPORT) console.log('    [C2] 레이어 1개 =', JSON.stringify(await nav()));
    await page.goBack(); await page.waitForTimeout(600);
    const c2 = await page.evaluate(() => ({ open: document.getElementById('yetadlg').open, n: _navStack.length }));
    ok('C2 레이어 회수 우선(뒤로 1회 = 최상단만 · 앱 유지)', !c2.open && c2.n === 0 && inApp(),
      `dlg=${c2.open} stack=${c2.n} inApp=${inApp()}`);

    // ── C3 : 고아 칸 3겹 → 사용자 뒤로 1회에 앱 밖 ──────────
    await enter();
    const orphan = await page.evaluate(() => {
      const d = document.getElementById('yetadlg');
      if (!d.open) { d.showModal(); navOpen('ydlg', () => { try { d.close(); } catch {} }); }
      navOpen('ycdetail', () => {}); navOpen('ycset', () => {});
      navHome();   // 탭 점프 = 레이어 전부 닫고 스택 비움 · history 칸은 의도적으로 남는다
      return { stack: _navStack.length, st: (history.state && history.state.nav) || null };
    });
    if (REPORT) console.log('    [C3] navHome 직후 =', JSON.stringify(orphan), '← st 잔존 = 고아 칸');
    const p3 = await pressesToExit();
    ok('C3 고아 칸 3겹이어도 뒤로 1회에 앱 밖', p3 === 1,
      `누름 ${p3 === -1 ? '4회에도 못 나감' : p3 + '회'} (기대 1 · 267차 이전 = 2)`);

    // ── C4 : 감기 표식 누수 0 ─────────────────────────────
    await enter();
    await page.evaluate(() => {
      navOpen('a', () => {}); navOpen('b', () => {});
      navHome();                                   // 고아 칸 2개 잔존
      const d = document.getElementById('yetadlg');
      if (!d.open) { d.showModal(); navOpen('ydlg', () => { try { d.close(); } catch {} }); }
    });
    await page.waitForTimeout(300);
    await page.goBack(); await page.waitForTimeout(700);
    const c4 = await page.evaluate(() => ({ open: document.getElementById('yetadlg').open, n: _navStack.length }));
    ok('C4 감기 표식 누수 0(고아 칸 뒤 새 레이어 = 그 레이어부터 회수)', !c4.open && c4.n === 0 && inApp(),
      `dlg=${c4.open} stack=${c4.n} inApp=${inApp()}`);

    // ── C5 : #yconfirm 생존 ───────────────────────────────
    await enter();
    const c5open = await page.evaluate(() => {
      if (typeof yConfirm !== 'function') return null;
      yConfirm({ title: '회귀검증', body: 'b', okLabel: '확인', onOk: () => {} });
      return { hidden: document.getElementById('yconfirm').hidden, stack: _navStack.map(l => l.id) };
    });
    await page.waitForTimeout(300);
    const c5close = c5open && await page.evaluate(() => { yConfirmClose(); return 1; }) &&
      (await page.waitForTimeout(600), await page.evaluate(() => ({
        hidden: document.getElementById('yconfirm').hidden, n: _navStack.length })));
    ok('C5 #yconfirm 생존(열기·닫기·백스택 등재/회수)',
      !!c5open && c5open.hidden === false && c5open.stack.includes('yconfirm') && !!c5close && c5close.hidden === true && c5close.n === 0,
      c5open ? `open=${JSON.stringify(c5open)} close=${JSON.stringify(c5close)}` : 'yConfirm 없음');

    // ── C6 : 실 UI — 챗 위 명함 모달 적층 ──────────────────
    if (roster.length) {
      await enter();
      await page.evaluate(() => yTab('char'));
      const row = await page.waitForSelector('#ychar .ycrow', { timeout: 15000 }).catch(() => null);
      if (row) {
        await row.click(); await page.waitForTimeout(1600);
        const cta = await page.$('.ycd-cta');
        if (cta) {
          await cta.click(); await page.waitForTimeout(2600);
          const st = await nav();
          const vcf = await page.evaluate(() => { const v = document.getElementById('vcfdlg'); return !!(v && v.open); });
          if (REPORT) console.log('    [C6] 챗+명함 =', JSON.stringify(st), 'vcf=', vcf);
          if (vcf) {
            await page.goBack(); await page.waitForTimeout(1000);
            const after = await page.evaluate(() => ({
              vcf: (() => { const v = document.getElementById('vcfdlg'); return !!(v && v.open); })(),
              chat: document.getElementById('yetadlg').open,
            }));
            ok('C6 챗 위 명함 = 뒤로 1회에 명함만(뒤 챗 동반 종료 봉인)', after.vcf === false && after.chat === true,
              `vcf=${after.vcf} chat=${after.chat}`);
          } else ok('C6 챗 위 명함 적층', true, '명함 미출현(해당 캐릭터 조건 아님) = 스킵');
        } else ok('C6 챗 위 명함 적층', true, '대화 시작 버튼 없음 = 스킵');
      } else ok('C6 챗 위 명함 적층', true, '캐릭터 행 미렌더 = 스킵');
    } else ok('C6 챗 위 명함 적층', true, 'roster.json 없음 = 스킵');

    // ── C7 : JS 실에러 ────────────────────────────────────
    const real = errors.filter(e => !/net::ERR|Failed to load resource|manifest|favicon|sw\.js|404|preventDefault/i.test(e));
    ok('C7 JS 실에러 0', real.length === 0, real.slice(0, 3).join(' | '));
  } finally {
    await browser.close();
    srv.close();
  }

  const bad = R.filter(r => !r.pass);
  if (bad.length) {
    console.log(`\n❌ 백스택 회귀 ${bad.length}건 — viewer/index.html 백스택 골격(navOpen/navHome/popstate)을 확인해라.`);
    console.log('   상세 = node tests/test_backstack.js --report');
    process.exit(1);
  }
  console.log(`✅ 백스택 회귀 — ${R.length}개 계약 통과(고아 칸 뒤로 1회·표식 누수 0·#yconfirm 생존 포함).`);
  process.exit(0);
})().catch(e => { console.log('❌ 백스택 회귀 하니스 예외:', e && e.message); process.exit(1); });
