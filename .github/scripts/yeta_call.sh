#!/usr/bin/env bash
# yeta_call.sh — 걸려오는 전화 v1 (yeta-call.yml dispatch · 260704 · UI 미구현 = 기능부만)
# 체인: 발신자 선정(입력→세션 페르소나→랜덤) → 첫마디 생성(claude -p·구독 OAuth·카드 주입) → OpenAI TTS(⚠️유료·fail-soft)
#       → 음성 mp3 = **비공개** 세션 버킷 voice/ (대사=대화 내용 → 공개 버킷 금지·서빙=yeta.js op voice)
#       → 세션 append(call 턴 + sess.call 마커 = 미래 수신 UI 훅) → 웹푸시 "전화가 왔어"(fail-soft).
# 규율: 대화 중(pending 유저 턴)엔 전화 안 걸림(챗 우선·매몰 방지) — 반영 직전 fresh 재-read로 재확인.
#       ⚠️ --bare 절대 금지(OAuth 즉사) · 폴오버 SSOT 4계정 체인(yeta_chat.sh 동형 · 로테이션 3 + MUTENONA 고정 꼬리).
# env: YETA_CALL_PERSONA(발신자 강제·선택) · YETA_CALL_LINE(수동 대사=테스트·claude 생략) · YETA_CALL_VOICE(TTS 보이스 강제)
#      OPENAI_API_KEY(TTS — 없으면 무음 전화) · OPENAI_TTS_MODEL(기본 gpt-4o-mini-tts)
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

DEFAULT_MODEL="claude-opus-5"
DEFAULT_EFF="low"                 # 첫마디 한 호흡 = 30초 컷과 같은 결(챗 기본 동형)
case "${YETA_CALL_MODEL:-}" in claude-opus-5|claude-sonnet-5) MODEL="$YETA_CALL_MODEL" ;; *) MODEL="$DEFAULT_MODEL" ;; esac
case "${YETA_CALL_EFF:-low}" in low|medium|high|max) EFF="${YETA_CALL_EFF:-low}" ;; *) EFF="$DEFAULT_EFF" ;; esac
SAFE=""
case "${YETA_SAFE:-1}" in 1|true|on) SAFE="--safe-mode" ;; esac   # 기본 ON — 런타임은 CLAUDE.md 미주입(개발 세션 전용 · 턴당 ~37k 토큰 절약 · 운영자 260704) · ⚠️ --bare 는 여전히 절대 금지(OAuth 즉사)
export CLAUDE_BARE=0              # 방어 명시(yeta_chat.sh 평의회① 동형)
export DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1   # 자동 로드 컷(운영자 260723 — CLI 자동업데이트·텔레메트리 OFF · yeta_chat 동형)
RECENT_TURNS="${YETA_RECENT_TURNS:-8}"
INLINE_TRIES=4   # 4계정 폴오버 체인 깊이(서브3 MUTENONA까지 실호출) + 일시 과부하 흡수 — 4계정 확장 3→4
ROSTER="apps/yeta/characters/roster.json"

source "$ROOT/shared/claude_transient.sh"   # is_transient/is_quota/claude_failover SSOT
source "$ROOT/shared/claude_meter.sh"
source "$ROOT/shared/inject_character.sh"
YSF="$(yeta_sys_frame)"; SYS_ARGS=()   # 캐릭터 프레임 시스템 슬롯(yeta_chat 동형 계승 · 260723) — CC 기저 텍스트 미전송(쿼터 절감) · 노브 = YETA_SYS(yml)
case "${YETA_SYS:-1}" in 2|replace) SYS_ARGS=(--system-prompt "$YSF") ;; 0|off|false) SYS_ARGS=() ;; *) SYS_ARGS=(--append-system-prompt "$YSF") ;; esac

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID 필요}"; : "${YETA_R2_BUCKET:?YETA_R2_BUCKET 필요}"
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?}" AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?}" AWS_DEFAULT_REGION=auto
EP="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
KEY="sessions/main.json"
SESS=/tmp/yeta_call_sess.json
r2get() { aws s3 cp "s3://${YETA_R2_BUCKET}/${KEY}" "$SESS" --endpoint-url "$EP" --only-show-errors; }
r2put() { aws s3 cp "$SESS" "s3://${YETA_R2_BUCKET}/${KEY}" --endpoint-url "$EP" --content-type application/json --only-show-errors; }

# ── 1) 세션 읽기 — 미생성(404)은 빈 세션으로 시작(전화가 첫 이벤트일 수 있음) ──
if ! _gerr="$(r2get 2>&1)"; then
  if printf '%s' "$_gerr" | grep -qiE 'Not Found|NoSuchKey|404'; then
    printf '{"turns":[],"note":"","state":"idle"}' > "$SESS"
  else
    echo "::error::R2 세션 읽기 실패: ${_gerr}"; exit 1
  fi
fi

# ── 2) 재료 추출 + 발신자 선정 — BUSY(대화 중) | JSON{persona,name,switch,note_pub,note_me,hist} ──
mat="$(YETA_CALL_PERSONA="${YETA_CALL_PERSONA:-}" python3 - "$SESS" "$ROSTER" "$RECENT_TURNS" <<'PY'
import json, os, random, sys
sys.path.insert(0, ".github/scripts")
from yeta_v3 import migrate_v3
S_ROOT = migrate_v3(json.load(open(sys.argv[1], encoding="utf-8")))
_cur = S_ROOT.get("cur") or ""
s = dict((S_ROOT.get("threads") or {}).get(_cur) or {})   # 현재 방 뷰(없으면 빈 방 = 랜덤 발신)
s["persona"] = _cur
for _k in ("note_pub", "note", "notes"): s[_k] = S_ROOT.get(_k)
roster = json.load(open(sys.argv[2], encoding="utf-8"))
n = int(sys.argv[3])
turns = s.get("turns") or []
last_a = max([i for i, t in enumerate(turns) if t.get("role") == "assistant"], default=-1)
if any(t.get("role") == "user" for t in turns[last_a + 1:]):
    print("BUSY"); sys.exit(0)                       # 답장 대기 중 = 챗 우선(전화 생략)
ids = [c.get("id") for c in roster if c.get("id")]
want = os.environ.get("YETA_CALL_PERSONA", "").strip()
cur = s.get("persona") or ""
persona = want if want in ids else (cur if cur in ids else random.choice(ids))
name = next((c.get("name") or persona for c in roster if c.get("id") == persona), persona)
def line(t):
    r, x = t.get("role"), (t.get("text") or "").replace("\n", " / ")
    if r == "user": return "유저: " + x
    if r == "assistant": return "너: " + x
    return "— " + x + " —"
hist = "\n".join(line(t) for t in turns[-n:])
print(json.dumps({"persona": persona, "name": name,
                  "switch": bool(cur and cur != persona and turns),
                  "note_pub": s.get("note_pub") or s.get("note") or "",
                  "note_me": ((s.get("notes") or {}).get(persona)) or "", "hist": hist},
                 ensure_ascii=False))
PY
)"
[ "$mat" = "BUSY" ] && { echo "답장 대기 중인 유저 메시지 있음 — 전화 생략(챗 우선)"; exit 0; }
[ -n "$mat" ] || { echo "::error::세션/로스터 파싱 실패"; exit 1; }
matv() { python3 -c 'import json,sys; v=json.loads(sys.argv[1]).get(sys.argv[2]); print("" if v is None else v)' "$mat" "$1"; }
PERSONA="$(matv persona)"; CNAME="$(matv name)"; SWITCH="$(matv switch)"
NOTE_PUB="$(matv note_pub)"; NOTE_ME="$(matv note_me)"; HIST="$(matv hist)"
[[ "$PERSONA" =~ ^[a-z0-9_-]{1,24}$ ]] || { echo "::error::발신자 선정 실패"; exit 1; }

# ── 3) 첫마디 — 수동 대사(YETA_CALL_LINE·테스트) 또는 claude -p 생성(챗과 동일 폴오버 규율) ──
GEN_S=0
if [ -n "${YETA_CALL_LINE:-}" ]; then
  out="$YETA_CALL_LINE"
else
  [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || { echo "::error::OAuth 토큰 없음(수동 대사 line 도 미지정)"; exit 1; }
  CBLOCK="$(character_block "$PERSONA")" || { echo "::error::지침 주입 실패(${PERSONA})"; exit 1; }
  prompt="${CBLOCK}

[공용 기억 — 유저에 대한 사실과 이 세계의 사건. 다른 주민도 알 만한 것]
${NOTE_PUB:-"(아직 없음)"}

[너와 유저 둘만의 기억 — 관계 진도·너에게만 한 말. 다른 주민은 모른다]
${NOTE_ME:-"(아직 없음 — 첫 만남)"}

[최근 대화 — 다른 주민이 나눈 대화일 수 있다. 사실 맥락은 이어받되 둘만의 비밀은 넘겨짚지 마라]
${HIST:-"(없음)"}

[상황]
너는 지금 유저에게 먼저 전화를 걸었고, 유저가 방금 받았다. 건 이유는 네가 정한다 — 안부, 문득 생각나서, 최근 대화의 후속, 네 일상의 작은 사건 등 캐릭터답게.

[출력 계약 — 반드시 지켜라]
- 전화 첫마디 딱 한 호흡만: 2~4문장, 공백 포함 220자 이내.
- 이 텍스트는 그대로 음성(TTS)으로 재생된다. 소리 내어 말하는 대사만 — 나레이션·지문·이탤릭(*…*)·괄호 연출·이모지 금지.
- 너는 \"${CNAME}\"다. 이름표·따옴표·메타 설명 없이 대사만. 기억 블록(<<NOTE>>)·무드 태그(<<MOOD>>)도 붙이지 마라."

  echo "yeta-call: ${PERSONA}(${CNAME}) · ${MODEL}${EFF:+ · effort $EFF}${SAFE:+ · safe}"
  EFF_ARGS=(); [ -n "$EFF" ] && EFF_ARGS=(--effort "$EFF")
  T0=$SECONDS; inline_delay=15; rc=1; out=""; _eff_dropped=0
  for attempt in $(seq 1 "$INLINE_TRIES"); do
    out="$(printf '%s' "$prompt" | METER_SRC=yeta-call METER_REF="$PERSONA" METER_MODEL="$MODEL" METER_EFFORT="$EFF" claude_meter 240 \
          --model "$MODEL" $SAFE "${SYS_ARGS[@]}" "${EFF_ARGS[@]}" --tools "" \
          --disallowedTools "Write,Edit,NotebookEdit,Bash,Task,WebFetch,WebSearch,Read,Glob,Grep" \
          --max-turns 1 \
          2> /tmp/yeta_call.err)"   # --tools "" = 빌트인 스키마 0(책빼기 · yeta_chat gen_out 동형 260723 — 종전엔 통화 첫마디마다 스키마 ~18k tok 자동 탑재)
    rc=$?
    if [ $rc -eq 0 ] && [ -n "${out// }" ]; then
      if is_quota "$out"; then   # 쿼터 문구 rc=0 유출 가드(yeta_chat gen_out 동형 · 운영자 260709) — 전환 후 재시도·소진 = 실패
        echo "  ⚠️ 쿼터 한도 텍스트(rc=0) — 계정 전환 시도"
        if claude_failover "$out"; then out=""; continue; fi
        rc=1; break
      fi
      break
    fi
    if [ ${#EFF_ARGS[@]} -gt 0 ] && [ "$_eff_dropped" = 0 ] && grep -qi 'effort' /tmp/yeta_call.err 2>/dev/null; then
      echo "  ⚠️ effort 거부 추정 — effort 빼고 재시도"; EFF_ARGS=(); EFF=""; _eff_dropped=1; continue
    fi
    if claude_failover "$out$(cat /tmp/yeta_call.err 2>/dev/null)"; then continue; fi
    if [ "$attempt" -lt "$INLINE_TRIES" ] && is_transient "$out$(cat /tmp/yeta_call.err 2>/dev/null)"; then
      echo "  ⏳ 일시 과부하(${attempt}/${INLINE_TRIES}) — ${inline_delay}s 후 재시도"
      sleep "$inline_delay"; inline_delay=$((inline_delay * 2)); continue
    fi
    break
  done
  GEN_S=$((SECONDS - T0))
  if [ $rc -ne 0 ] || [ -z "${out// }" ]; then
    echo "::error::첫마디 생성 실패(rc=$rc)"; head -n 5 /tmp/yeta_call.err 2>/dev/null || true; exit 1
  fi
fi

# 새니타이즈 — TTS로 그대로 읽히므로 연출 잔여물 제거(NOTE/MOOD 블록·*지문*·백틱) + 400자 컷
LINE_TEXT="$(python3 - <<'PY' "$out"
import re, sys
t = sys.argv[1]
t = re.split(r'<<\s*NOTE(?:\s*:\s*\w+)?\s*>>', t, flags=re.I)[0]          # 계약 위반 방어(챗 파서와 동형 정신)
t = re.sub(r'<<\s*/?\s*(?:NOTE|MOOD)(?:\s*:\s*\w+)?\s*>>', '', t, flags=re.I)
t = re.sub(r'\*[^*\n]{1,120}\*', '', t)                                    # *나레이션* = 소리 아님 → 제거
t = re.sub(r'[`*_]', '', t)
t = re.sub(r'\s+', ' ', t).strip()
print(t[:400])
PY
)"
[ -n "$LINE_TEXT" ] || { echo "::error::새니타이즈 후 빈 대사"; exit 1; }
echo "yeta-call: 첫마디 ${#LINE_TEXT}자 · ${GEN_S}s"

# ── 4) TTS — SSOT = yeta_tts.py(클론 보이스 el: 우선 = 프리미엄 · OpenAI 프리셋 폴백 · ⚠️유료 = 수동 dispatch/일 상한 안에서만) — fail-soft(실패=무음 전화) ──
MP3=/tmp/yeta_call.mp3; rm -f "$MP3"
python3 .github/scripts/yeta_tts.py "$PERSONA" "$LINE_TEXT" "$MP3" || echo "TTS 실패/미설정 — 무음 전화로 진행"

# ── 5) 음성 업로드 = 비공개 세션 버킷 voice/ (⚠️ 대사=대화 내용 → 공개 버킷·git 커밋 절대 금지 · 서빙=op voice) ──
VKEY=""
if [ -s "$MP3" ]; then
  VKEY="voice/call-${PERSONA}-$(date +%s).mp3"
  if aws s3 cp "$MP3" "s3://${YETA_R2_BUCKET}/${VKEY}" --endpoint-url "$EP" --content-type audio/mpeg --only-show-errors; then
    echo "  음성 업로드 — ${VKEY}"
  else
    echo "  ⚠️ 음성 업로드 실패 — 무음 전화로 진행"; VKEY=""
  fi
fi

# ── 6) 세션 반영 — fresh 재-read 후 append(그 사이 유저 턴 생겼으면 통화 폐기 = 챗 우선·매몰 방지) ──
_g=0; for _i in 1 2 3; do if r2get; then _g=1; break; fi; [ "$_i" -lt 3 ] && sleep 2; done
if [ "$_g" = 0 ]; then
  # 첫 이벤트 레이스(세션 아직 미생성)면 빈 세션으로 생성 진행 — 그 외 실패는 반영 포기
  printf '{"turns":[],"note":"","state":"idle"}' > "$SESS"
fi
LINE_TEXT="$LINE_TEXT" PERSONA="$PERSONA" CNAME="$CNAME" SWITCH="$SWITCH" VKEY="$VKEY" MODEL="$MODEL" EFF="$EFF" GEN_S="$GEN_S" \
python3 - "$SESS" <<'PY'
import json, os, sys, time
sys.path.insert(0, ".github/scripts")
from yeta_v3 import migrate_v3
S = migrate_v3(json.load(open(sys.argv[1], encoding="utf-8")))
persona, name = os.environ["PERSONA"], os.environ.get("CNAME") or os.environ["PERSONA"]
th = (S.get("threads") or {}).setdefault(persona, {"turns": [], "state": "idle", "opening": 0, "awaiting_since": 0, "err": "",
      "room": [persona], "invite": None, "barged": 0, "declined": {}, "pin": 0, "updated": 0, "last_sp": persona, "char_ver": "", "nudge": None})
turns = th.setdefault("turns", [])
last_a = max([i for i, t in enumerate(turns) if t.get("role") == "assistant"], default=-1)
if any(t.get("role") == "user" for t in turns[last_a + 1:]):
    print("반영 직전 유저 메시지 감지 — 통화 폐기(챗 우선)"); sys.exit(2)
now = int(time.time() * 1000)
turn = {"role": "assistant", "kind": "call", "text": os.environ["LINE_TEXT"], "ts": now + 1,
        "persona": persona, "model": os.environ.get("MODEL", ""), "effort": os.environ.get("EFF", ""),
        "gen_s": int(os.environ.get("GEN_S", "0") or 0)}
if os.environ.get("VKEY"):
    turn["voice"] = os.environ["VKEY"]                 # 뷰어 재생 키(op voice 로 스트림)
turns.append(turn)
if len(turns) > 200:
    th["turns"] = turns = turns[-200:]
S["cur"] = persona                                     # 발신자의 방 = 현재 방(전화 = 등장 · v3)
S["call"] = {"ts": now + 1, "persona": persona, "text": os.environ["LINE_TEXT"][:200],
             "voice": os.environ.get("VKEY", "")}      # 수신 UI 훅 = top-level(마이그감사 스키마)
th["updated"] = S["updated"] = now + 1
json.dump(S, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
PY
_rc=$?
[ "$_rc" = 2 ] && exit 0
[ "$_rc" = 0 ] || { echo "::error::세션 반영 실패(rc=$_rc)"; exit 1; }
r2put || { echo "::error::세션 저장 실패(R2 put)"; exit 1; }
echo "yeta-call: 세션 반영 완료 — ${PERSONA} · voice=${VKEY:-없음}"

# ── 7) 웹푸시 — 구독자 없으면 조용히 no-op(비치명 · yeta_chat.sh push_reply 동형) ──
if [ -n "${VAPID_PRIVATE_KEY:-}" ]; then
  python3 .github/scripts/push_send.py --notify "yeta" "📞 ${CNAME}에게서 전화가 왔어 — 탭해서 받기" \
    --url "/?yeta=main&call=1" --tag "nomute-yeta-call" >/dev/null 2>&1 || true
fi
exit 0
