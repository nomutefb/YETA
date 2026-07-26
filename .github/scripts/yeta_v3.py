# yeta v3 세션 어댑터 SSOT (260707 다중 채팅방 · 5인 기틀검증 반영)
# — migrate_v3: functions/api/yeta.js migrateV3와 **동형**(멱등 순수 랩 · 시뮬 대조 게이트 대상 · 마이그 감사①)
# — pick_thread: 통합 age 큐(신선 invite / pending 최고령 / opening nonce — 가장 오래된 것 우선 · 러너 감사①A·레이스 감사②)
# — thread_view: 스레드 dict + 공유 필드 오버레이(기존 단일 세션 로직 재사용용 읽기 뷰)
import time

INVITE_TTL_MS = 600000
GB_TTL_MS = 120000        # 단톡 자율 비트 예약(s.gb) 유효 시간 — yeta_chat.sh GB_TTL_MS·뷰어 gbP TTL과 3점 짝(러너 사망 시 자연 소멸)

def migrate_v3(s):
    """v>=3 or threads 존재 = no-op(멱등). v2 = threads[persona] 랩 · updated = 마지막 턴 ts 백필."""
    if not isinstance(s, dict):
        return {"v": 3, "cur": "", "barge_day": "", "call": None, "threads": {},
                "note_pub": "", "notes": {}, "tunes": {}, "policy": {}, "pref": {},
                "me": {"call": "", "about": ""}}
    if s.get("v", 0) >= 3 or "threads" in s:
        s.setdefault("threads", {}); s.setdefault("me", {"call": "", "about": ""}); s["v"] = 3   # me = 유저 프로필(호칭+소개 · 260708) 상시 존재(JS migrateV3 동형)
        return s
    t = str(s.get("persona") or "")
    th = {}
    turns = s.get("turns") or []
    if t and turns:
        room = [r for r in (s.get("room") or []) if isinstance(r, str) and r] or [t]
        th[t] = {"turns": turns, "state": s.get("state") or "idle", "opening": s.get("opening") or 0,
                 "awaiting_since": s.get("awaiting_since") or 0, "err": s.get("err") or "",
                 "room": room, "invite": s.get("invite") or None, "barged": s.get("barged") or 0,
                 "declined": s.get("declined") or {}, "pin": 0,
                 "updated": (turns[-1].get("ts") if isinstance(turns[-1], dict) else 0) or int(time.time() * 1000),
                 "last_sp": t, "char_ver": s.get("char_ver") or "", "nudge": s.get("nudge") or None}
    return {"v": 3, "cur": t or "", "barge_day": s.get("barge_day") or "", "call": s.get("call") or None,
            "threads": th, "note_pub": s.get("note_pub") or s.get("note") or "",
            "notes": s.get("notes") or {}, "tunes": s.get("tunes") or {},
            "policy": s.get("policy") or {}, "pref": s.get("pref") or {},
            "me": s.get("me") if isinstance(s.get("me"), dict) else {"call": "", "about": ""}}

def _age_kind(th, now_ms):
    """(일감 나이 ts, 종류) — 없으면 (None, ""). 종류 'gb' = 단톡 자율 비트(유저가 화면에서 기다리는 일감 아님) · 그 외(invite·pending·opening) = 대기 축."""
    turns = th.get("turns") or []
    la = max([i for i, t in enumerate(turns) if t.get("role") == "assistant"], default=-1)
    pend = [t for t in turns[la + 1:] if t.get("role") == "user"]
    cands = []
    inv = th.get("invite") or {}
    room = [r for r in (th.get("room") or []) if r][:2]
    if inv.get("to") and now_ms - (inv.get("ts") or 0) < INVITE_TTL_MS and inv["to"] not in room and len(room) < 2:
        cands.append((inv.get("ts") or 0, "invite"))
    if pend:
        cands.append((pend[0].get("ts") or 0, "pending"))
    if th.get("opening") and not any(t.get("role") == "assistant" for t in turns):
        cands.append((th.get("opening") or 0, "opening"))
    gb = th.get("gb") if isinstance(th.get("gb"), dict) else None
    if gb and not pend and len(room) == 2 and now_ms - (gb.get("ts") or 0) < GB_TTL_MS:
        cands.append((now_ms, "gb"))   # 자율 비트 = **항상 최연소**(유저를 기다리는 진짜 일감이 언제나 먼저 · 발동 게이트 전량은 extract_mat 정본)
    return min(cands) if cands else (None, "")

def _age(th, now_ms):
    """스레드의 일감 나이(ts) — 없으면 None(호환 래퍼 · 종류가 필요하면 _age_kind)."""
    return _age_kind(th, now_ms)[0]

CUR_YIELD_MS = 180000     # 열린 방 우선의 상한(운영자 260726) — 다른 방 일감이 이만큼 묵으면 양보해 그쪽부터. 3분 = 게이트웨이 좀비 리퍼(10분)·뷰어 좀비 임계(5분)보다 앞 = 양보가 늦어 error 플립을 부르는 일 없음

def pick_thread(S, now_ms=None):
    """일감 스레드 id(없으면 None) — **열린 방(cur) 우선**, 그 외는 스레드 간 FIFO(기아 방지).

    cur 우선인 이유(260726 실측): 종전 순수 FIFO는 지금 화면을 켜두고 첫 대사를 기다리는 방을,
    아무도 안 보는 옛 방의 밀린 답장 뒤로 밀었다(실측 23:43:31 루시 밀린 턴 30s → 23:44:01에야 고죠 오프닝 = 첫 대사 60s 중 30s가 남의 방 대기).
    양보 규칙(CUR_YIELD_MS)이 기아를 막는다 — 밀린 방이 3분을 넘기면 그 방이 먼저다.
    'gb'(단톡 자율 비트)는 우선 대상에서 제외 = 유저를 기다리는 진짜 일감이 언제나 먼저라는 _age_kind 계약 온존.
    """
    now = now_ms or time.time() * 1000
    jobs = {}
    for tid, th in (S.get("threads") or {}).items():
        a, kind = _age_kind(th, now)
        if a is not None:
            jobs[tid] = (a, kind)
    if not jobs:
        return None
    cur = S.get("cur") or ""
    if cur in jobs and jobs[cur][1] != "gb":
        stale = any(tid != cur and now - a > CUR_YIELD_MS for tid, (a, _k) in jobs.items())
        if not stale:
            return cur
    return min(jobs.items(), key=lambda kv: kv[1][0])[0]

def thread_view(S, tid):
    """기존 단일 세션 로직 호환 읽기 뷰 — 스레드 필드 + 공유 필드 오버레이 + 타 스레드 메타(_others · 턴 텍스트 접근 금지 = 비밀 누수 차단)."""
    th = (S.get("threads") or {}).get(tid) or {}
    v = dict(th)
    v["persona"] = th.get("last_sp") or tid
    for k in ("note_pub", "note", "notes", "tunes", "policy", "pref"):
        v[k] = S.get(k)
    v["_others"] = [{"id": o, "updated": (S["threads"][o] or {}).get("updated") or 0,
                     "n": len((S["threads"][o] or {}).get("turns") or [])}
                    for o in (S.get("threads") or {}) if o != tid]
    return v
