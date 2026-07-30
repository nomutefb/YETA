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


def world_dhm(now_ts=None):
    """world_dh + 분 — 이동 구간(transit_of) 진행도 계산용. 시·날짜는 world_dh와 **완전히 같은 값**(공식 재구현 아님)."""
    import time as _t
    eff = ((now_ts if now_ts is not None else _t.time()) - _FRZ_MS / 1000)
    if _ANCH: wt = (_ANCH.get("wmin") or 0) + (eff - _ANCH["eff"] / 1000) / 60 * _RATE
    else: wt = eff / 60 * _RATE
    d, h = world_dh(now_ts)
    return d, h, int(wt % 60)


def slot_of(hour):
    """state_block 시간대와 동일 경계 — late(0~3)·dawn(3~7)·morning(7~11)·day(11~17)·evening(17~21)·night(21~24)."""
    if hour < 3: return "late"
    if hour < 7: return "dawn"
    if hour < 11: return "morning"
    if hour < 17: return "day"
    if hour < 21: return "evening"
    return "night"


SLOTS = ("late", "dawn", "morning", "day", "evening", "night")


# ── rv = 결정적 난수 축(운영자 260730 Q.144 "랜덤 변수 하나 정해서 0부터 1까지 · 소숫점 0.000에 따라 변수가 되도록") ──
#   0.000 ~ 0.999(1/1000 입도)의 실수 하나. **저장 안 하고 시드에서 뽑는다** = 뷰어·러너가 같은 입력이면 같은 값(동기화 불필요).
#   ⚠ 진짜 난수(random())를 쓰면 안 된다 — 뷰어와 러너가 서로 다른 위치를 말하게 되고, 새로고침마다 사람이 순간이동한다.
#   "매번 똑같지 않게"는 **시드 입력에 세계 날짜·시간 버킷이 들어 있어서** 나온다(날마다·2시간마다 새 값).
#   뷰어 등가 = ymRv() — 문자열 조합·모듈로 1000 규약 완전 동일(check_refs 동선 로직 게이트가 대조).
def rv(*parts):
    """결정적 난수 0.000~0.999 — parts를 ':'로 이어 sha256 → mod 1000 / 1000. 같은 입력 = 항상 같은 값."""
    h = int(hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest(), 16)
    return (h % 1000) / 1000.0


def tuning(pl):
    """동선 튜닝 블록(places.json `tuning`) — 없으면 종전 동작과 같은 기본값. 값 = 데이터 축(코드 수정 없이 조정)."""
    t = (pl or {}).get("tuning") or {}
    return {
        "wander": t.get("wander", 0.5),              # 인접 장소로 나갈 확률 기본값(0.500 = 종전 seed%2 등가 = 회귀 0)
        "wander_by": t.get("wander_by") or {},        # 인물별 오버라이드(붙박이 0.1x ~ 역마 0.7x)
        "no_place": set(t.get("no_place") or []),     # 위치 축 OFF(난입 전용 등) — 폴백 생성 제외 = 지도·근처·마주침 전부에서 빠진다
        "transit_min": int(t.get("transit_min", 12) or 12),   # 자리를 옮긴 직후 '가는 중'으로 보는 세계 분(12분 ≈ 6배속 기준 현실 2분)
        "bucket_h": max(1, int(t.get("bucket_h", 2) or 2)),   # 재판정 입도(세계 시간) — 2 = 2시간마다 새 rv
    }


def _public(pl):
    """공용 장소 id 정렬 목록 — private(집)·offlimits 제외. 폴백 동선의 후보 풀."""
    P = (pl or {}).get("places") or {}
    return sorted(k for k, v in P.items() if not (v or {}).get("private") and not (v or {}).get("offlimits"))


def routine_of(pl, char_id):
    """이 인물의 6슬롯 동선 — ⓐ places.json routine 등재분이 **항상 이긴다**(손으로 쓴 게 정본).
    ⓑ 미등재면 rv로 **결정적 생성**(운영자 260730 Q.144 — 17명 중 9명만 등재라 8명이 지도에서 통째로 사라져 있었다).
    생성 시드에 **날짜가 없다** = 그 사람의 동선은 매일 같다(사람에겐 습관이 있어야 한다 · 날마다 다른 건 rv가 붙는 외출뿐)."""
    got = ((pl or {}).get("routine") or {}).get(char_id)
    if isinstance(got, dict) and got:
        return got
    if char_id in tuning(pl)["no_place"]:
        return {}                                                       # 위치 축 OFF = 종전(미등재) 그대로 "" — 난입 전용 인물이 폴백으로 지도에 상주하던 것 차단
    pub = _public(pl)
    if not pub:
        return {}
    anchor = pub[int(rv(char_id, "anchor") * len(pub)) % len(pub)]      # 그 사람의 단골자리
    second = pub[int(rv(char_id, "anchor2") * len(pub)) % len(pub)]     # 두 번째 자리(같을 수도 = 완전 붙박이)
    out = {}
    for s in SLOTS:
        out[s] = anchor if rv(char_id, "slot", s) < 0.62 else second    # 0.62 = 단골 비중(하루의 약 2/3을 한 자리에서)
    return out


def place_of(pl, char_id, date_str, hour):
    """캐릭터의 지금 장소 id — 동선표(등재 or 폴백 생성) 기본 · rv < wander면 인접 장소로 외출.
    집(private)은 변주 없음(사생활). 장소 데이터 자체가 비면 ""(위치 축 비활성).
    ⚠ 뷰어 ymPlaceOf와 **시드 문자열·확률 규약이 한 글자도 달라선 안 된다**(달라지면 러너와 지도가 다른 사람을 다른 데 둔다)."""
    T = tuning(pl)
    slot = slot_of(hour)
    base = (routine_of(pl, char_id) or {}).get(slot) or ""
    if not base:
        return ""
    info = ((pl.get("places") or {}).get(base)) or {}
    if info.get("private"):
        return base
    nb = [n for n in (info.get("neighbors") or []) if not ((pl.get("places") or {}).get(n) or {}).get("private")]
    if nb:
        bk = hour // T["bucket_h"]                                       # 재판정 버킷(2시간 = 현실 20분 · 260709 "장소 이동 많이")
        w = T["wander_by"].get(char_id, T["wander"])                     # 인물별 이동 성향(데이터 축 · 미등재 = 기본 0.500)
        if rv(char_id, date_str, slot, bk, "go") < w:                    # ⓐ 나갈까 — 0.000~0.999 대 임계값
            i = int(rv(char_id, date_str, slot, bk, "pick") * len(nb))   # ⓑ 어디로 — **별도 rv**(같은 시드로 둘 다 정하면 "나간다=항상 첫 이웃" 같은 상관이 생긴다)
            return nb[i % len(nb)]
    return base


def _prev_bucket(date_str, hour, bucket_h):
    """직전 재판정 버킷의 (날짜열, 시각) — 자정을 넘으면 전날 마지막 버킷으로."""
    h = hour - bucket_h
    if h >= 0:
        return date_str, h
    try:
        n = int(str(date_str)[1:])
    except Exception:
        return date_str, 0
    return f"w{n - 1}", (24 + h) % 24


def transit_of(pl, char_id, date_str, hour, minute=0):
    """지금 '가는 중'인가 — {from, to, p}. p = 0.000~1.000 진행도(1.0 = 도착·머무는 중).
    자리가 바뀐 직후 transit_min(세계 분) 동안만 이동 구간으로 본다. 저장 0 · 순수함수(같은 시각 = 같은 답).
    ⚠ 지도 워커의 '건물 관통 직선 행진'은 운영자 260716이 폐지한 연출이라 **되살리지 않는다** — 이 값은 말과 라벨의 축이다
      (「정류장에서 찻집 가는 길」). 지도는 종전대로 페이드 점프."""
    T = tuning(pl)
    cur = place_of(pl, char_id, date_str, hour)
    if not cur:
        return {"from": "", "to": "", "p": 1.0}
    pd, ph = _prev_bucket(date_str, hour, T["bucket_h"])
    prev = place_of(pl, char_id, pd, ph)
    into = (hour % T["bucket_h"]) * 60 + max(0, min(59, int(minute)))    # 이 버킷에 들어온 지 몇 분 됐나(세계 분)
    if prev and prev != cur and into < T["transit_min"]:
        return {"from": prev, "to": cur, "p": round(into / T["transit_min"], 3)}
    return {"from": cur, "to": cur, "p": 1.0}


def occupancy(pl, char_ids, date_str, hour):
    """{장소 id: [인물 id]} — 「지금 찻집에 누구 있어?」의 역인덱스. 순수함수 N번이라 저장·크론 0."""
    out = {}
    for cid in (char_ids or []):
        p = place_of(pl, cid, date_str, hour)
        if p:
            out.setdefault(p, []).append(cid)
    return out


def next_change_h(pl, char_id, date_str, hour, span=24):
    """자리가 다음에 바뀌는 세계 시각(시). 못 찾으면 None — 폴링 대신 '바뀌는 순간에만' 재계산하기 위한 축."""
    T = tuning(pl)
    cur = place_of(pl, char_id, date_str, hour)
    h = hour - (hour % T["bucket_h"]) + T["bucket_h"]
    while h < hour + span:
        d, hh = (date_str, h) if h < 24 else (f"w{int(str(date_str)[1:]) + h // 24}", h % 24)
        if place_of(pl, char_id, d, hh) != cur:
            return h
        h += T["bucket_h"]
    return None


def place_name(pl, place_id):
    return (((pl.get("places") or {}).get(place_id) or {}).get("name")) or ""
