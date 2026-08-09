// YETA 서비스워커 — 캐릭터 답장 웹푸시 수신·표시 + 딥링크. scope=/(루트).
// 발송 = .github/scripts/push_send.py(pywebpush) / 구독 = api/push. nomute sw.js 패턴 이식(260704).
self.addEventListener('push', event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch { d = { body: event.data && event.data.text() }; }
  const title = d.title || '무음동';   // 폴백도 세계관 말(260809 몰입 감사 C) — 페이로드 title 결측 시 잠금화면에 앱 코드네임이 뜨던 자리
  const opts = {
    body: d.body || '답장이 도착했어',
    icon: d.icon || '/assets/brand/yeta-icon-192.png',
    badge: d.badge || '/assets/brand/yeta-badge.png',
    tag: d.tag || 'yeta-reply',          // 같은 tag = 교체(중복 알림 안 쌓임)
    data: { url: d.url || '/' },
    lang: 'ko',
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const raw = (event.notification.data && event.notification.data.url) || '/';
  const target = new URL(raw, self.location.origin);   // 답장 딥링크(/?yeta=<char>)
  event.waitUntil((async () => {
    const list = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    // 1) 이미 타깃 화면(경로+쿼리+해시 일치)이면 포커스만(불필요 새로고침 방지).
    for (const c of list) {
      try { const u = new URL(c.url); if (u.pathname === target.pathname && u.search === target.search && u.hash === target.hash && 'focus' in c) return c.focus(); } catch (_) {}
    }
    // 2) 열린 탭이 있으면 타깃으로 이동.
    for (const c of list) {
      if ('navigate' in c && 'focus' in c) {
        try { const nc = await c.navigate(target.href); return (nc || c).focus(); } catch (_) {}
      }
    }
    // 3) 열린 탭 없음 → 새 창.
    if (self.clients.openWindow) return self.clients.openWindow(target.href);
  })());
});

self.addEventListener('install', () => self.skipWaiting());           // 새 sw 즉시 활성
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
