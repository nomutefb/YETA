# yeta_place.py — 무음동 위치 판정(260707 마주침 이벤트 · 정본 데이터 = apps/yeta/places.json)
# place_of = 동선표(routine) 기본 + 결정적 시드(sha256)로 가끔(1/4) 인접 장소 외출 — 같은 날·같은 슬롯 = 같은 위치(무저장·재현 가능).
# 러너(extract_mat·barge_check·초대 판정)와 향후 지도 UI가 이 함수 하나만 쓴다(사본 금지 — 드리프트 씨앗).
import hashlib
import json


def load_places(path="apps/yeta/places.json"):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {"places": {}, "routine": {}}


_FRZ_MS = 0   # 난입 정지 누적(현실 ms · 운영자 260728 "일단 들어오면 그 순간 시간이 멈추는 개념") — 세션 wfz에서 진입점이 1회 주입. 배속 리터럴은 안 건드린다(세계율 3점 게이트 불변).


def set_freeze(ms):
    """이 프로세스의 세계 시계를 ms(현실)만큼 뒤로 민다 — 난입 중 멈춰 있던 시간. 세션을 읽은 직후 1회 호출."""
    global _FRZ_MS
    try: _FRZ_MS = max(0, int(ms or 0))
    except Exception: _FRZ_MS = 0


def frz_ms(root, now_ms=None):
    """세션 top-level wfz={since,acc,by} → 지금까지 멈춰 있던 총 현실 ms(진행 중인 정지분 포함). 필드 없음 = 0 = 종전 동작."""
    import time as _t
    f = (root or {}).get("wfz") or {}
    if not isinstance(f, dict): return 0
    now = now_ms if now_ms is not None else _t.time() * 1000
    since = f.get("since") or 0
    return int((f.get("acc") or 0) + ((now - since) if since else 0))


_RATE = 6      # 세계 배속 폴백(운영자 260728 L1 노브 — 정책 미설정·읽기 실패 시 이 값. 세계율 3점 게이트가 이 리터럴을 대조한다)
_ANCH = None   # 배속 변경 앵커 {"eff": 유효경과ms, "wmin": 그 시점 세계 총분} — 없으면 종전 공식(회귀 0)


def set_rate(rate, anchor=None):
    """이 프로세스의 세계 배속 + 변경 앵커를 세팅 — 세션을 읽은 직후 set_freeze와 함께 1회 호출."""
    global _RATE, _ANCH
    try:
        r = float(rate or 0)
        _RATE = r if r > 0 else 6
    except Exception: _RATE = 6
    _ANCH = anchor if isinstance(anchor, dict) and anchor.get("eff") else None


def load_policy_def(path="apps/yeta/policy.json"):
    """L1 정책 정의(축·기본값·vals) — load_places와 동일 규약(러너 CWD = 레포 루트 · 실패 = 빈 dict = 폴백 6배)."""
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def rate_of(root, pol_def=None):
    """세션 정책(L1.world[wrate] 인덱스) → 실 배속. policy.json의 vals 매핑이 정본이고, 못 읽으면 6."""
    try:
        if pol_def is None: pol_def = load_policy_def()
        p = (root or {}).get("policy") or {}
        ax = None
        for e in (((pol_def or {}).get("L1") or {}).get("world") or []):
            if isinstance(e, dict) and e.get("key") == "wrate": ax = e; break
        if not ax or not isinstance(ax.get("vals"), list): return 6
        i = p.get("wrate")
        if not isinstance(i, int): i = ax.get("default") or 0
        v = ax["vals"][i] if 0 <= i < len(ax["vals"]) else None
        return v if isinstance(v, (int, float)) and v > 0 else 6
    except Exception: return 6


def anchor_of(root):
    """세션 top-level wrb={eff,wmin} → 배속 변경 앵커(게이트웨이 op policy SET이 찍는다). 없으면 None."""
    a = (root or {}).get("wrb")
    return a if isinstance(a, dict) and a.get("eff") else None


def world_dh(now_ts=None):
    """무음동 세계 (날짜열 'w<일련일>', 시각 0~23) — 기본 6배 가속(운영자 260716 지도 싱크: 동선·지도·근처·원거리 시간축을 세계 시각으로 통일).
    공식 짝 3점(드리프트 금지): 뷰어 window.yWTotal · 러너 state_block wmin(yeta_chat.sh) · 여기.
    ⚠ 난입 정지(260728) = _FRZ_MS만큼 뺀 시각으로 계산 — 배속은 그대로다(멈춘 만큼 세계가 안 흐를 뿐).
    ⚠ 배속 변경(260728 L1) = 앵커 이후만 새 배속으로 적산 — 안 그러면 rate를 갈아끼우는 순간 세계 날짜가 통째로 점프한다."""
    import time as _t
    eff = ((now_ts if now_ts is not None else _t.time()) - _FRZ_MS / 1000)   # 정지 제외 유효 현실 초
    if _ANCH: wt = (_ANCH.get("wmin") or 0) + (eff - _ANCH["eff"] / 1000) / 60 * _RATE
    else: wt = eff / 60 * _RATE
    return f"w{int(wt // 1440)}", int(wt % 1440 // 60)


def slot_of(hour):
    """state_block 시간대와 동일 경계 — late(0~3)·dawn(3~7)·morning(7~11)·day(11~17)·evening(17~21)·night(21~24)."""
    if hour < 3: return "late"
    if hour < 7: return "dawn"
    if hour < 11: return "morning"
    if hour < 17: return "day"
    if hour < 21: return "evening"
    return "night"


def place_of(pl, char_id, date_str, hour):
    """캐릭터의 지금 장소 id — 동선표 기본 · 시드 1/4로 인접 외출(집(private)은 변주 없음 — 사생활). 미등재 캐릭터 = ""(위치 축 비활성)."""
    slot = slot_of(hour)
    base = ((pl.get("routine") or {}).get(char_id) or {}).get(slot) or ""
    if not base:
        return ""
    info = (pl.get("places") or {}).get(base) or {}
    if info.get("private"):
        return base
    nb = [n for n in (info.get("neighbors") or []) if not ((pl.get("places") or {}).get(n) or {}).get("private")]
    if nb:
        # 이동 빈도 상향(운영자 260709 "장소 이동 많이 — 소통이 자유롭지 않게"): 1/4→1/2 + 2시간 입도(같은 슬롯에도 h//2 단위 재판정 = 결정적 유지) · 뷰어 ymPlaceOf와 시드 문자열 완전 동일(드리프트 금지)
        seed = int(hashlib.sha256(f"{char_id}:{date_str}:{slot}:{hour // 2}:go".encode()).hexdigest(), 16)
        if seed % 2 == 0:
            return nb[seed % len(nb)]
    return base


def place_name(pl, place_id):
    return (((pl.get("places") or {}).get(place_id) or {}).get("name")) or ""
