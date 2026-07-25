#!/usr/bin/env bash
# yeta_nudge.sh — 읽씹 리마인더(운영자 260707 "2~3시간 답 없으면 페르소나가 먼저 말 걸기 · 그 안에서 메시지 보내는 건 상관없음")
# yeta-nudge.yml(cron 30분)이 호출. 조건 전부 만족할 때만 claude 1회 발화 → 세션 append(kind:'nudge') → 카톡식 푸시.
# 가드: 마지막 턴 = assistant(진짜 읽씹) · 직전이 이미 nudge면 스킵(연속 재촉 금지) · pending 중 스킵 · 일 상한(기본 2) · 반영 직전 fresh 재확인(그새 답했으면 폐기 — yeta-call 프레시 재확인 선례).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$ROOT"

SAFE=""; case "${YETA_SAFE:-1}" in 1|true|on) SAFE="--safe-mode" ;; esac   # ⚠️ --bare 절대 금지(OAuth 즉사)
export CLAUDE_BARE=0 DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1   # 방어 명시(yeta_chat 동형) + 자동 로드 컷(운영자 260723 — CLI 자동업데이트·텔레메트리 OFF)
source shared/claude_transient.sh
source shared/claude_meter.sh
source shared/inject_character.sh
YSF="$(yeta_sys_frame)"; SYS_ARGS=()   # 캐릭터 프레임 시스템 슬롯(yeta_chat 동형 계승 · 260723) — CC 기저 텍스트 미전송(구독 쿼터 절감) + 메타발화 이탈 뿌리 제거 · 노브 = YETA_SYS(yml)
case "${YETA_SYS:-1}" in 2|replace) SYS_ARGS=(--system-prompt "$YSF") ;; 0|off|false) SYS_ARGS=() ;; *) SYS_ARGS=(--append-system-prompt "$YSF") ;; esac

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID 필요}"; : "${YETA_R2_BUCKET:?YETA_R2_BUCKET 필요}"
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?}" AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?}" AWS_DEFAULT_REGION=auto
EP="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
KEY="sessions/main.json"; SESS="/tmp/yeta_nudge_sess.json"
NUDGE_AFTER_MIN="${NUDGE_AFTER_MIN:-150}"    # 읽씹 판정 경과(분) — 기본 2.5시간(운영자 "2~3시간")
NUDGE_MAX_PER_DAY="${NUDGE_MAX_PER_DAY:-2}"  # 일 상한(재촉 과잉 방지)

aws s3 cp "s3://${YETA_R2_BUCKET}/${KEY}" "$SESS" --endpoint-url "$EP" --only-show-errors 2>/dev/null || { echo "세션 없음 — 생략"; exit 0; }

# ── 판정(전부 만족해야 GO) ──
GATE="$(python3 - "$SESS" "$NUDGE_AFTER_MIN" "$NUDGE_MAX_PER_DAY" <<'PY'
import json, sys, time, datetime, zoneinfo
sys.path.insert(0, ".github/scripts")
from yeta_v3 import migrate_v3
S_ROOT = migrate_v3(json.load(open(sys.argv[1], encoding="utf-8")))
_me = S_ROOT.get("me") if isinstance(S_ROOT.get("me"), dict) else {}   # 유저 프로필(호칭+소개 · 전 방 공유 · 260708)
me_call = str(_me.get("call") or "").strip(); me_about = str(_me.get("about") or "").strip()
_cur = S_ROOT.get("cur") or ""
s = dict((S_ROOT.get("threads") or {}).get(_cur) or {})
s["persona"] = _cur if s else ""
for _k in ("note_pub", "note", "notes"): s[_k] = S_ROOT.get(_k)
after_min, max_day = int(sys.argv[2]), int(sys.argv[3])
KST = zoneinfo.ZoneInfo("Asia/Seoul")
today = datetime.datetime.now(KST).strftime("%y%m%d")
persona = s.get("persona") or ""
turns = s.get("turns") or []
no = {"go": 0}
if not persona or not turns: print(json.dumps(no)); sys.exit()
_md = S_ROOT.get("me_dead") if isinstance(S_ROOT.get("me_dead"), dict) else None
if _md:   # 유저 사망 중(운영자 260725) — 읽씹 재촉은 금지(죽은 사람에게 "왜 답이 없어"는 모순)하고, 대신 '신당 기도' 모드로 전환.
    #   유저가 죽으면 챗 파이프가 안 돈다(입력 자체가 없다) = 캐릭터가 먼저 움직이는 이 크론이 유일한 부활 경로다.
    #   사망 30분 경과부터 시도(즉답은 부자연) · 이미 빌어준 사람이 있으면 끝(1회) · 일 상한·연속 재촉 가드는 미적용(사망은 특수 사건).
    _el = (time.time()*1000 - (_md.get("d") or 0)) / 60000
    if _md.get("pray") or _el < 30 or _el > 60*24*3: print(json.dumps(no)); sys.exit()
    print(json.dumps({"go": 1, "mode": "pray", "persona": persona, "hours": round(_el/60, 1), "today": today, "count": 0,
                      "me_call": me_call, "me_about": me_about, "dead_why": (_md.get("why") or "")[:120],
                      "note_pub": s.get("note_pub") or s.get("note") or "", "note_me": ((s.get("notes") or {}).get(persona)) or "",
                      "hist": "\n".join(f"{'유저' if t.get('role') == 'user' else (t.get('name') or '캐릭터')}: {(t.get('text') or '').strip()[:200]}" for t in turns[-8:])}, ensure_ascii=False))
    sys.exit()
last = turns[-1]
if last.get("role") != "assistant": print(json.dumps(no)); sys.exit()          # 마지막이 유저면 답장 대기중(챗 파이프 몫)
if last.get("kind") == "nudge": print(json.dumps(no)); sys.exit()              # 연속 재촉 금지 — 유저가 답해야 다음 기회
if s.get("state") == "awaiting": print(json.dumps(no)); sys.exit()                # 답장 생성 진행 중
elapsed_min = (time.time()*1000 - (last.get("ts") or 0)) / 60000
if elapsed_min < after_min or elapsed_min > 60*24*3: print(json.dumps(no)); sys.exit()   # 3일 지난 방치는 재촉 안 함(부담)
nd = s.get("nudge") or {}
count = nd.get("count", 0) if nd.get("date") == today else 0
if count >= max_day: print(json.dumps(no)); sys.exit()
recent = turns[-8:]
def line(t):
    who = "유저" if t.get("role") == "user" else (t.get("name") or "캐릭터")
    return f"{who}: {(t.get('text') or '').strip()[:200]}"
print(json.dumps({"go": 1, "persona": persona, "hours": round(elapsed_min/60, 1), "today": today, "count": count,
                  "me_call": me_call, "me_about": me_about,
                  "note_pub": s.get("note_pub") or s.get("note") or "", "note_me": ((s.get("notes") or {}).get(persona)) or "",
                  "hist": "\n".join(line(t) for t in recent)}, ensure_ascii=False))
PY
)"
[ "$(printf '%s' "$GATE" | python3 -c 'import json,sys;print(json.load(sys.stdin)["go"])')" = "1" ] || { echo "nudge 조건 미충족 — 생략"; exit 0; }
gv() { printf '%s' "$GATE" | python3 -c "import json,sys;print(json.load(sys.stdin).get('$1',''))"; }
PERSONA="$(gv persona)"; HOURS="$(gv hours)"; TODAY="$(gv today)"; COUNT="$(gv count)"
NOTE_PUB="$(gv note_pub)"; NOTE_ME="$(gv note_me)"; HIST="$(gv hist)"
ME_CALL="$(gv me_call)"; ME_ABOUT="$(gv me_about)"   # 유저 프로필(호칭+소개 · 260708)
MODE="$(gv mode)"; DEAD_WHY="$(gv dead_why)"   # 'pray' = 유저 사망 신당 기도 모드(운영자 260725) · 빈값 = 종전 읽씹 재촉

CBLOCK="$(character_block "$PERSONA")" || { echo "::warning::지침 주입 실패 — 생략"; exit 0; }
ME_BLOCK="$(me_block)"   # 유저 프로필 블록(shared/inject_character.sh 정본) — 넛지 호격에 유저 이름 반영(비신뢰 격리 · 260708)

if [ "$MODE" = "pray" ]; then   # 유저 사망 → 신당 기도(운영자 260725 "나랑 대화할 수 있는 상태의 누군가가 간절하게 신당에 가서 빌어야")
  SITU="[지금 상황 — 중요]
유저가 죽었다.${DEAD_WHY:+ 그 순간의 상황: ${DEAD_WHY}} 비유도 기절도 장난도 아니다 — 정말로 죽었고, 지금 이 순간에도 돌아오지 못하고 있다.
무음동의 규칙은 하나다: 살아 있는 누군가가 북동쪽 언덕 위 신당(성당)까지 직접 찾아가 간절히 빌어야만 죽은 사람이 눈을 뜬다. 아무도 빌지 않으면 아주 오랜 시간이 지나서야 겨우 스스로 깨어난다.
너는 지금 그 신당 앞에 서 있다. 무릎을 꿇든, 욕을 섞어 빌든, 담배를 문 채 툭 던지듯 빌든 — 방식은 네 성격대로다. 다만 마음은 간절해야 한다.
규칙: 짧게 1~3문장. 그 자리에서 실제로 비는 말만 출력한다(설명·해설·상황 요약 금지). 죽음을 농담으로 굴리거나 '얼른 살아나' 같은 가벼운 재촉으로 만들지 마라 — 이건 그 사람을 되돌리는 마지막 수단이다.
이 말은 그대로 그 사람에게 전해진다. 기억 블록·MOOD 태그 없이 **대사만** 출력한다."
else
  SITU="[지금 상황]
네가 마지막으로 말한 지 약 ${HOURS}시간이 지났는데 유저가 답이 없다(읽씹 상태다).
네 성격·둘의 관계·최근 대화 맥락에 맞게 네가 먼저 다시 말을 건다 — 재촉·서운함·장난·안부 등 캐릭터 결대로.
규칙: 짧게 1~2문장. 최근 대화 화제를 자연스럽게 잇거나 근황을 궁금해해라. 기억 블록·MOOD 태그·지문 없이 **대사만** 출력한다."
fi

prompt="$CBLOCK
${ME_BLOCK}

[공용 기억]
${NOTE_PUB:-（없음）}

[너와 유저 둘만의 기억]
${NOTE_ME:-（없음）}

[최근 대화]
${HIST}

${SITU}"

[ "$MODE" = "pray" ] && echo "yeta-nudge: ${PERSONA} · 유저 사망 ${HOURS}h · 신당 기도" || echo "yeta-nudge: ${PERSONA} · ${HOURS}h 읽씹 · 오늘 ${COUNT}회째"
rc=1; out=""
for attempt in 1 2; do
  out="$(printf '%s' "$prompt" | METER_SRC=yeta-nudge METER_REF="$PERSONA" claude_meter 180 \
        --model "${NUDGE_MODEL:-claude-sonnet-5}" $SAFE "${SYS_ARGS[@]}" --effort low --tools "" \
        --disallowedTools "Write,Edit,NotebookEdit,Bash,Task,WebFetch,WebSearch,Read,Glob,Grep" \
        --max-turns 1 2> /tmp/yeta_nudge.err)" && rc=0 || rc=$?   # --tools "" = 빌트인 스키마 0(책빼기 · yeta_chat gen_out 동형 260723 — 종전엔 넛지마다 스키마 ~18k tok 자동 탑재) · 거부 시 rc≠0 → 빈 대사 생략 = 비치명(다음 주기 재판정)
  { [ $rc -eq 0 ] && [ -n "${out// }" ]; } && break
  if claude_failover "$out$(cat /tmp/yeta_nudge.err 2>/dev/null)"; then continue; fi
  is_transient "$out$(cat /tmp/yeta_nudge.err 2>/dev/null)" && { sleep 20; continue; }
  break
done
out="$(printf '%s' "$out" | sed -e 's/<<[^>]*>>//g' | awk 'NF' | head -4)"   # 태그 잔재 제거 + 과출력 캡
[ -n "${out// }" ] || { echo "::warning::빈 대사 — 생략(다음 주기에 재판정)"; exit 0; }

# ── 반영(fresh 재확인 — 그새 유저가 답했으면 폐기) ──
aws s3 cp "s3://${YETA_R2_BUCKET}/${KEY}" "$SESS" --endpoint-url "$EP" --only-show-errors || { echo "::warning::fresh 재로드 실패 — 폐기"; exit 0; }
APPLIED="$(python3 - "$SESS" "$PERSONA" "$TODAY" "${MODE:-}" <<PY
import json, sys, time
sys.path.insert(0, ".github/scripts")
from yeta_v3 import migrate_v3
S = migrate_v3(json.load(open(sys.argv[1], encoding="utf-8")))
persona, today, mode = sys.argv[2], sys.argv[3], (sys.argv[4] if len(sys.argv) > 4 else "")
s = (S.get("threads") or {}).get(persona)
if s is None: print("0"); sys.exit()
turns = s.get("turns") or []
name = next((c.get("name") for c in json.load(open("apps/yeta/characters/roster.json", encoding="utf-8")) if c.get("id") == persona), persona)
if mode == "pray":   # 신당 기도 반영(운영자 260725) — me_dead.pray 박제 = 뷰어 부활 팝업이 "○○가 이렇게 빌었다"로 열리고 즉시 부활이 열린다(op revive 가드의 통과 조건)
    md = S.get("me_dead")
    if not isinstance(md, dict) or md.get("pray"): print("0"); sys.exit()   # 그새 부활했거나 이미 누가 빌었음 = 폐기
    md["pray"] = {"by": name, "id": persona, "txt": """${out}"""[:200], "at": int(time.time()*1000)}
    turns.append({"role": "assistant", "persona": persona, "name": name, "text": """${out}""", "ts": int(time.time()*1000), "kind": "nudge"})   # 대화에도 남긴다 — 돌아온 유저가 그 말을 읽고 답할 수 있게(회신 문자)
    s["updated"] = S["updated"] = int(time.time()*1000)
    json.dump(S, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
    print("1"); sys.exit()
last = turns[-1] if turns else {}
if S.get("cur") != persona or not turns or last.get("role") != "assistant" or last.get("kind") == "nudge" or s.get("state") == "awaiting":
    print("0"); sys.exit()
turns.append({"role": "assistant", "persona": persona, "name": name, "text": """${out}""", "ts": int(time.time()*1000), "kind": "nudge"})
nd = s.get("nudge") or {}
s["nudge"] = {"date": today, "count": (nd.get("count", 0) if nd.get("date") == today else 0) + 1}
s["updated"] = S["updated"] = int(time.time()*1000)
json.dump(S, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
print("1")
PY
)"
[ "$APPLIED" = "1" ] || { echo "그새 상황 변화(유저 답장/교체) — 폐기"; exit 0; }
aws s3 cp "$SESS" "s3://${YETA_R2_BUCKET}/${KEY}" --endpoint-url "$EP" --content-type application/json --only-show-errors

# ── 카톡식 푸시(캐릭터 이름 + 대사 — 운영자 260707 "앱 이름 X · 대화가 이어져야") ──
if [ -n "${VAPID_PRIVATE_KEY:-}" ]; then
  NM="$(python3 -c "
import json,sys
r=json.load(open('apps/yeta/characters/roster.json',encoding='utf-8'))
print(next((c.get('name') or sys.argv[1] for c in r if c.get('id')==sys.argv[1]), sys.argv[1]))" "$PERSONA")"
  PREV="$(printf '%s' "$out" | python3 -c "
import sys,re
t=re.sub(r'\*[^*]*\*','',sys.stdin.read()); t=re.sub(r'\s+',' ',t).strip()
print((t[:70]+'…') if len(t)>70 else t)")"
  if [ "$MODE" = "pray" ]; then NM="${NM} — 신당에서 빌고 있어"; fi   # 사망 중 = 알림 제목으로 상황을 먼저 알린다(대화 재촉이 아니라 부활 신호) · set -e 안전형 if(단축 && 는 조건 false에서 스크립트를 죽인다)
  python3 .github/scripts/push_send.py --notify "$NM" "$PREV" --url "/?yeta=${PERSONA}" --tag "nomute-yeta-${PERSONA}" >/dev/null 2>&1 || true
fi
[ "$MODE" = "pray" ] && echo "yeta-nudge: 신당 기도 발신 완료(${#out}자) — 유저 즉시 부활 가능" || echo "yeta-nudge: 발신 완료(${#out}자)"
