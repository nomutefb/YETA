#!/usr/bin/env python3
# fb_incidents.py — SessionStart 훅: 프레임이탈 관찰 리포트 자동 부각(운영자 260721 Q.35)
# 러너(yeta_chat.sh fb_report)가 남긴 열린 이슈(라벨 yeta-frame-break)를 세션 시작 시 조회해 표출 —
# "우려했던 내용 발생 시 다음 예타 작업 세션에서 자동으로 부각" 축의 구현체.
# 공개 레포 = 무인증 GET(프록시는 urllib이 env로 자동 인지) · 실패/타임아웃/0건 = 완전 무음(세션 시작 방해 금지 · fail-soft).
import json
import urllib.request

try:
    req = urllib.request.Request(
        "https://api.github.com/repos/nomutefb/YETA/issues?labels=yeta-frame-break&state=open&per_page=5",
        headers={"accept": "application/vnd.github+json", "user-agent": "yeta-fb-hook"},
    )
    with urllib.request.urlopen(req, timeout=4) as r:
        issues = json.load(r)
    if isinstance(issues, list) and issues:
        print("🚨 [프레임이탈 관찰 리포트 — 자동 부각(Q.35)] YETA_SYS=2(전 모델 시스템 교체) 이후 캐릭터 이탈이 실제 발생해 러너가 기록해뒀다:")
        for i in issues:
            print(f"  · #{i.get('number')} {i.get('title', '')} (코멘트 {i.get('comments', 0)}건) {i.get('html_url', '')}")
        print("→ 이 세션 최우선: 운영자에게 이 사실을 먼저 보고하고, 이슈 코멘트(발생 메타)를 읽어 원인 진단·조치(빈발이면 yeta-chat.yml YETA_SYS 롤백 제안) 후 운영자 승인 하에 이슈를 닫아라.")
except Exception:
    pass
