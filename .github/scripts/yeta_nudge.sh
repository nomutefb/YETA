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
    if _md.get("pray") or _el > 60*24*3: print(json.dumps(no)); sys.exit()
    # 두 잡을 순서로 나눈다(운영자 260725) — ① 20분 후 '성향 퀴즈'(부활 시간을 스스로 줄이는 수단) ② 60분 후 '신당 기도'(즉시 부활).
    #   기도가 먼저 오면 퀴즈가 무의미해지므로 퀴즈가 반드시 앞선다. 퀴즈 대상 = 만난 사람만(threads에 유저 턴이 있는 캐릭터 · 운영자 "만난사람만").
    if not _md.get("quiz"):
        if _el < 20: print(json.dumps(no)); sys.exit()
        _met = [p for p, t in (S_ROOT.get("threads") or {}).items()
                if not p.startswith("g") and any(x.get("role") == "user" for x in (t.get("turns") or []))]
        if not _met: print(json.dumps(no)); sys.exit()
        print(json.dumps({"go": 1, "mode": "quiz", "persona": persona, "hours": round(_el/60, 1), "today": today, "count": 0,
                          "me_call": me_call, "me_about": me_about, "dead_why": (_md.get("why") or "")[:120],
                          "met": _met, "tunes": {p: (S_ROOT.get("tunes") or {}).get(p) for p in _met}}, ensure_ascii=False))
        sys.exit()
    if _el < 60: print(json.dumps(no)); sys.exit()
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
MODE="$(gv mode)"; DEAD_WHY="$(gv dead_why)"   # 'pray' = 신당 기도 · 'quiz' = 성향 퀴즈 출제(운영자 260725) · 빈값 = 종전 읽씹 재촉
MET="$(printf '%s' "$GATE" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("met") or [], ensure_ascii=False))')"
TUNES="$(printf '%s' "$GATE" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("tunes") or {}, ensure_ascii=False))')"

if [ "$MODE" = "quiz" ]; then   # 성향 퀴즈(운영자 260725) — 한 명 카드가 아니라 '만난 사람들' 요약이 재료다(카드 전문 = 10명이면 컨텍스트 폭발)
  CBLOCK="$(python3 - "$MET" "$TUNES" <<'PY'
import json, os, re, sys
met = json.loads(sys.argv[1]); tunes = json.loads(sys.argv[2])
AX = ["말수","장난기","어투 강도","답장 길이","친절도","온기(다정함)","인내심","삐짐·질투","츤데레 낙차(겉과 속 차이)","초기 친밀도","친밀해지는 속도","경계심(비밀 방어)","플러팅 수위","신비 노출(판타지 누설)","이중성 스위치 빈도","위험한 분위기(밤 모드)"]   # 축 순서 = yeta_chat.sh AX·뷰어 TUNE_AX와 짝(정본 3점 동기)
try: roster = {c.get("id"): c for c in json.load(open("apps/yeta/characters/roster.json", encoding="utf-8"))}
except Exception: roster = {}
L = ["[출제 대상 — 유저가 실제로 만난 사람들. 이 밖의 인물을 지어내지 마라]"]
for p in met[:10]:
    c = roster.get(p) or {}
    nm = c.get("name") or p
    head = ""
    try:   # 카드 §성격 첫 두 줄 = 그 인물을 한눈에 잡는 최소 재료(지문·예시대사는 뺀다 = 정답을 흘리지 않기 위해)
        raw = open(f"apps/yeta/characters/{p}.md", encoding="utf-8").read()
        m = re.search(r'^## 성격\s*$(.*?)(?=^## )', raw, flags=re.M | re.S)
        if m:
            bl = [re.sub(r'[*_`]', '', x).strip("- ").strip() for x in m.group(1).strip().splitlines() if x.strip().startswith("-")]
            head = " / ".join(b[:90] for b in bl[:2])
    except Exception: pass
    tn = tunes.get(p)
    ax_hi = ""
    if isinstance(tn, list) and len(tn) == 16:
        top = sorted(range(16), key=lambda i: -(tn[i] or 0))[:3]
        ax_hi = " · 지금 높은 축: " + ", ".join(f"{AX[i]}({tn[i]})" for i in top)
    L.append(f"- {nm}({p}) — {c.get('tagline') or ''}{(' · ' + head) if head else ''}{ax_hi}")
L.append("")
L.append("[성향 16축 — 선택지가 가리킬 번호]")
L.append(" · ".join(f"{i} {a}" for i, a in enumerate(AX)))
print("\n".join(L))
PY
)"
else
  CBLOCK="$(character_block "$PERSONA")" || { echo "::warning::지침 주입 실패 — 생략"; exit 0; }
fi
ME_BLOCK="$(me_block)"   # 유저 프로필 블록(shared/inject_character.sh 정본) — 넛지 호격에 유저 이름 반영(비신뢰 격리 · 260708)

if [ "$MODE" = "quiz" ]; then   # 유저 사망 → 성향 퀴즈 출제(운영자 260725 "각 캐릭터의 성향 만들기 느낌 · 내가 고르면 누적시켜서 캐릭터 성격 일원화")
  SITU="[할 일 — 유저는 지금 죽어 있다]
죽은 사람이 할 수 있는 건 기억을 더듬는 것뿐이다. 유저가 그 사람들을 얼마나 아는지 되짚는 문항 **10개**를 만들어라.
문항 하나 = ⓐ 위 사람 중 한 명 ⓑ 그 사람의 성격을 한 줄로 짚은 말(trait) ⓒ 그 사람이 놓인 상황 한 줄(q) ⓓ 그 상황에서 그 사람이 했을 법한 말 **4개**(o).
중요 — 4개 중 '정답' 하나와 들러리 셋이 아니다. **넷 다 그 사람이 할 법한 말**이되 결이 서로 달라야 한다(다정/장난/서늘/회피처럼). 유저가 고른 결이 그 사람의 성향을 실제로 조금씩 움직인다.
선택지는 미연시 선택지처럼 **그 사람의 대사 그대로**(따옴표·이름표 없이). 각 선택지에 그 결이 가리키는 축 번호 ax(0~15)와 방향 d(1 또는 -1)를 붙여라.
한 사람에게 몰지 말고 위 사람들에게 고루 배분해라. 유저(사용자)의 말·행동은 지어내지 마라.

출력 = **JSON 배열 하나만**(설명·코드펜스·인사 금지):
[{\"p\":\"캐릭터id\",\"trait\":\"성격 한 줄\",\"q\":\"상황 한 줄\",\"o\":[{\"t\":\"대사\",\"ax\":5,\"d\":1},{\"t\":\"대사\",\"ax\":1,\"d\":1},{\"t\":\"대사\",\"ax\":11,\"d\":1},{\"t\":\"대사\",\"ax\":0,\"d\":-1}]}, … 총 10개]"
elif [ "$MODE" = "pray" ]; then   # 유저 사망 → 신당 기도(운영자 260725 "나랑 대화할 수 있는 상태의 누군가가 간절하게 신당에 가서 빌어야")
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

case "$MODE" in
  quiz) echo "yeta-nudge: 유저 사망 ${HOURS}h · 성향 퀴즈 출제" ;;
  pray) echo "yeta-nudge: ${PERSONA} · 유저 사망 ${HOURS}h · 신당 기도" ;;
  *)    echo "yeta-nudge: ${PERSONA} · ${HOURS}h 읽씹 · 오늘 ${COUNT}회째" ;;
esac
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
if [ "$MODE" = "quiz" ]; then   # JSON 배열 = 대사 캡(sed·head -4)을 태우면 깨진다 → 관대 파싱 + 구조 검증을 거친 정규화 JSON만 통과
  out="$(printf '%s' "$out" | python3 - "$MET" <<'PYQ'
import json, re, sys
met = set(json.loads(sys.argv[1]))
raw = re.sub(r'^\s*```(?:json)?|```\s*$', '', sys.stdin.read().strip(), flags=re.M)   # 코드펜스 방어
i, j = raw.find('['), raw.rfind(']')
try: arr = json.loads(raw[i:j+1]) if i >= 0 and j > i else []
except Exception: arr = []
ok = []
for it in arr if isinstance(arr, list) else []:
    if not isinstance(it, dict): continue
    p, q, o = it.get("p"), (it.get("q") or "").strip(), it.get("o")
    if p not in met or not q or not isinstance(o, list) or len(o) < 4: continue   # 만난 사람 밖 = 폐기(운영자 "만난사람만")
    opts = []
    for x in o[:4]:
        if not isinstance(x, dict): continue
        t = (x.get("t") or "").strip()
        try: ax = int(x.get("ax")); d = 1 if int(x.get("d", 1)) >= 0 else -1
        except Exception: continue
        if not t or not (0 <= ax <= 15): continue
        opts.append({"t": t[:120], "ax": ax, "d": d})
    if len(opts) == 4: ok.append({"p": p, "trait": (it.get("trait") or "").strip()[:80], "q": q[:160], "o": opts})
print(json.dumps(ok[:10], ensure_ascii=False) if len(ok) >= 4 else "")   # 4문항도 못 건지면 폐기(다음 주기 재시도 = 반쪽 퀴즈 방지)
PYQ
)"
  [ -n "${out// }" ] || { echo "::warning::퀴즈 파싱 실패 — 생략(다음 주기에 재판정)"; exit 0; }
else
  out="$(printf '%s' "$out" | sed -e 's/<<[^>]*>>//g' | awk 'NF' | head -4)"   # 태그 잔재 제거 + 과출력 캡
  [ -n "${out// }" ] || { echo "::warning::빈 대사 — 생략(다음 주기에 재판정)"; exit 0; }
fi

# ── 반영(fresh 재확인 — 그새 유저가 답했으면 폐기) ──
aws s3 cp "s3://${YETA_R2_BUCKET}/${KEY}" "$SESS" --endpoint-url "$EP" --only-show-errors || { echo "::warning::fresh 재로드 실패 — 폐기"; exit 0; }
APPLIED="$(python3 - "$SESS" "$PERSONA" "$TODAY" "${MODE:-}" "$out" <<PY
import json, sys, time
sys.path.insert(0, ".github/scripts")
from yeta_v3 import migrate_v3
S = migrate_v3(json.load(open(sys.argv[1], encoding="utf-8")))
persona, today, mode = sys.argv[2], sys.argv[3], (sys.argv[4] if len(sys.argv) > 4 else "")
raw_out = sys.argv[5] if len(sys.argv) > 5 else ""   # 생성 원문 = argv 전달(퀴즈 JSON의 따옴표·역슬래시가 heredoc 삽입에서 깨지는 것 차단)
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
  if [ "$MODE" = "pray" ]; then NM="${NM} — 신당에서 빌고 있어"; fi
  if [ "$MODE" = "quiz" ]; then NM="기억이 떠오른다"; PREV="죽어 있는 동안 떠올릴 수 있는 게 생겼어 — 부활 시간을 줄일 수 있다"; fi   # 사망 중 = 알림 제목으로 상황을 먼저 알린다(대화 재촉이 아니라 부활 신호) · set -e 안전형 if(단축 && 는 조건 false에서 스크립트를 죽인다)
  python3 .github/scripts/push_send.py --notify "$NM" "$PREV" --url "/?yeta=${PERSONA}" --tag "nomute-yeta-${PERSONA}" >/dev/null 2>&1 || true
fi
case "$MODE" in
  quiz) echo "yeta-nudge: 성향 퀴즈 박제 완료(${#out}바이트)" ;;
  pray) echo "yeta-nudge: 신당 기도 발신 완료(${#out}자) — 유저 즉시 부활 가능" ;;
  *)    echo "yeta-nudge: 발신 완료(${#out}자)" ;;
esac
