#!/usr/bin/env python3
"""account_failover.py — 활성 계정(vars.ACTIVE_ACCOUNT) 자동 승격(sticky failover).

활성 계정이 '이번 런에 쿼터로 폴오버'된 걸 누적 카운트해서, 임계(기본 2) 도달 시 vars.ACTIVE_ACCOUNT 를
계정 체인의 다음 계정으로 전진(PATCH). 순환이라 막혔던 계정이 리셋되면 자연 복귀(원복 로직 0).

no-op 안전장치(라이브 무해):
  · GH_VARS_TOKEN(Variables 쓰기 PAT) 미설정 → 아무것도 안 함(exit 0). PAT 넣는 순간 켜짐.
  · 신호 파일(NOMUTE_QUOTA_SIGNAL · 기본 $GITHUB_WORKSPACE/.nomute_active_quota) 없음 → hits 불변(exit 0).
  · 모든 예외 = 삼키고 exit 0 (승격 실패가 파이프라인을 절대 안 깸).

상태 저장 = GitHub Actions repo Variables: ACTIVE_ACCOUNT(활성 계정명) · ACTIVE_QUOTA_HITS(누적 카운트).
"""
import json
import os
import sys
import urllib.error
import urllib.request

# ⚠️ 이식 시 여기만 그 레포의 계정명·순서(순환)로 교체. 워크플로 env 매핑 순서와 반드시 동일.
#   yeta 4계정 폴오버 체인(CLAUDE.md §🔑 · yeta-chat.yml env 매핑과 정합) = MUTENO→NOMUTEFB→EMS1130G→EMS1130M.
CHAIN = ["MUTENO", "NOMUTEFB", "EMS1130G", "EMS1130M"]
THRESHOLD = int(os.environ.get("PROMOTE_THRESHOLD", "2") or "2")   # 활성 계정 쿼터 몇 회 누적 시 승격
API = "https://api.github.com"


def _repo():
    return os.environ.get("GITHUB_REPOSITORY", "muteno/yeta")   # Actions 가 자동 주입(fallback만 교체)


def _req(method, path, token, body=None):
    url = "%s/repos/%s/actions/variables%s" % (API, _repo(), path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "account-failover")
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw.strip() else {})


def _get_var(name, token):
    try:
        _st, obj = _req("GET", "/" + name, token)
        return obj.get("value")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _set_var(name, value, token):
    """있으면 PATCH, 없으면(404) POST 로 생성."""
    try:
        _req("PATCH", "/" + name, token, {"name": name, "value": str(value)})
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _req("POST", "", token, {"name": name, "value": str(value)})
        else:
            raise


def _del_var(name, token):
    """변수 삭제(self-test 정리용)."""
    _req("DELETE", "/" + name, token)


def selftest():
    """GH_VARS_TOKEN 이 Variables 를 실제로 읽고/쓰고/지울 수 있는지 실측(PAT 권한 확인).
    ⚠️ 활성 계정·카운터는 안 건드림 — 전용 probe 변수만 왕복. 통과 = rc0 / 문제 = rc1."""
    token = (os.environ.get("GH_VARS_TOKEN") or "").strip()
    if not token:
        print("❌ GH_VARS_TOKEN 미설정 — Secrets 탭에 등록됐는지 확인(이름 철자 GH_VARS_TOKEN).")
        return 1
    active = (os.environ.get("ACTIVE_ACCOUNT") or CHAIN[0]).strip()
    print("현재 활성 계정(ACTIVE_ACCOUNT) = %s · 체인 = %s" % (active, "→".join(CHAIN)))
    probe = "ACCOUNT_FAILOVER_SELFTEST"
    try:
        _set_var(probe, "probe-write-ok", token)
        print("  ✅ 쓰기(POST/PATCH) 성공 — %s 생성/갱신" % probe)
        v = _get_var(probe, token)
        print("  ✅ 읽기(GET) 성공 — 값 = %r" % v)
        _del_var(probe, token)
        print("  ✅ 삭제(DELETE) 성공 — %s 정리" % probe)
        hits = _get_var("ACTIVE_QUOTA_HITS", token)
        print("  ℹ️ 현재 ACTIVE_QUOTA_HITS = %r (없으면 아직 승격 카운트 0)" % hits)
        print("🎉 PAT 실측 통과 — Variables read/write/delete 전부 정상. 승격 준비 완료(ACTIVE_ACCOUNT 무손상).")
        return 0
    except urllib.error.HTTPError as e:
        print("  ❌ 실패 — HTTP %s %s" % (e.code, getattr(e, "reason", "")))
        if e.code in (403, 404):
            print("     → PAT 에 'Variables: Read and write' 권한이 없거나 이 레포 접근이 없음. 토큰 권한을 확인해.")
        return 1
    except Exception as e:   # noqa: BLE001
        print("  ❌ 실패 — %s" % e)
        return 1


def main():
    token = (os.environ.get("GH_VARS_TOKEN") or "").strip()
    if not token:
        print("  ⏭️  GH_VARS_TOKEN 미설정 — 활성 계정 자동 승격 비활성(no-op · 라이브 무해).")
        return 0

    sig = os.environ.get("NOMUTE_QUOTA_SIGNAL") or os.path.join(
        os.environ.get("GITHUB_WORKSPACE", "."), ".nomute_active_quota")
    if not os.path.exists(sig):
        return 0   # 이번 런에 활성 계정이 쿼터로 안 막힘 = 조용히 종료(hits 불변)

    active = (os.environ.get("ACTIVE_ACCOUNT") or CHAIN[0]).strip()
    if active not in CHAIN:
        print("  ⚠️  활성 계정 '%s' 이 체인에 없음 — 승격 생략(체인=%s)." % (active, "→".join(CHAIN)))
        return 0

    try:
        hits_raw = _get_var("ACTIVE_QUOTA_HITS", token)
        hits = int(hits_raw) if (hits_raw or "").strip().isdigit() else 0
    except Exception as e:   # noqa: BLE001
        print("  ⚠️  ACTIVE_QUOTA_HITS 조회 실패(%s) — 승격 생략." % e)
        return 0

    hits += 1
    if hits < THRESHOLD:
        try:
            _set_var("ACTIVE_QUOTA_HITS", hits, token)
        except Exception as e:   # noqa: BLE001
            print("  ⚠️  hits 기록 실패(%s) — 다음 런 재시도." % e)
        print("  📉 활성 계정 '%s' 쿼터 누적 %d/%d회 — 아직 승격 안 함." % (active, hits, THRESHOLD))
        return 0

    nxt = CHAIN[(CHAIN.index(active) + 1) % len(CHAIN)]   # 임계 도달 → 다음 계정(순환) + hits 리셋
    try:
        _set_var("ACTIVE_ACCOUNT", nxt, token)
        _set_var("ACTIVE_QUOTA_HITS", 0, token)
        print("  🔀 활성 계정 자동 승격: %s → %s (쿼터 %d회 누적 · 다음 런부터 %s 로 시작)." % (active, nxt, hits, nxt))
    except Exception as e:   # noqa: BLE001
        print("  ⚠️  활성 계정 승격 실패(%s) — hits 유지·다음 런 재시도." % e)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())   # PAT 실측(실패 = rc1 노출)
    try:
        sys.exit(main())
    except Exception as e:   # noqa: BLE001  최후 방어 — 승격은 파이프라인을 절대 안 깸
        print("  ⚠️  account_failover 예외(무시하고 통과): %s" % e)
        sys.exit(0)
