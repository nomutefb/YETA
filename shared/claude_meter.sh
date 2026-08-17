#!/usr/bin/env bash
# claude_meter.sh — claude -p 토큰 사용량 계측 래퍼(SSOT). muteno 구독 OAuth 토큰이 "어디서 얼마나"
# 쓰이는지 추적하려고, 모든 claude -p 호출을 이 래퍼로 감싸 호출당 토큰을 metrics/ 에 남긴다.
# claude_transient.sh(재시도 판정)·claude_py.py(파이썬판 계정 폴오버)와 같은 결의 공용 헬퍼 — 로직 한 곳.
#
# 동작:
#   out="$(printf '%s' "$prompt" | METER_SRC=analyze METER_REF="$base" \
#          claude_meter 900 --model "$MODEL" --effort max --allowedTools ... --disallowedTools ... --max-turns 40 \
#          2> "$errfile")"
#   rc=$?
#   → claude -p 를 --output-format json 으로 돌려 .result(=원래 plain text 출력)만 stdout 으로 흘리고,
#     .usage(input/output/cache 토큰)·total_cost_usd·num_turns·duration_ms 를 잡 단위 shard 파일에 1줄 append.
#   ∴ 호출부의 out= 는 *예전과 똑같이 마크다운 본문*을 받는다(파싱 무변경). rc·stderr 도 그대로 보존.
#
# ⚠️ 안전(파이프라인 절대 안 깨지게):
#   · jq 없거나 METER_OFF=1 이면 → plain `claude -p`(--output-format json 미부착)로 폴백 = 옛 동작 그대로(계측만 생략).
#   · --output-format json 출력이 파싱 안 되면(크래시·과부하·인증오류 등 비정상) → raw 출력을 그대로 흘려보냄
#     (호출부의 is_quota/is_transient/실패판정이 옛날과 동일하게 동작 = 폴오버·재시도 무손상).
#   · shard 기록 실패는 || true 로 삼킴(분석물 유실 0).
#
# shard 경로 = metrics/usage/<run>-<job>-<attempt>.jsonl (잡마다 고유 → 동시 잡 충돌 0; 잡 내 순차 append).
#   롤업(shared/token_report.py)이 이 shard 들을 10분 버킷으로 집계하고 오래된 건 metrics/token-usage.jsonl 로 접는다.

_meter_shard() {
  local run="${GITHUB_RUN_ID:-local}" job="${GITHUB_JOB:-job}" att="${GITHUB_RUN_ATTEMPT:-1}"
  printf 'metrics/usage/%s-%s-%s.jsonl' "$run" "$job" "$att"
}

# _meter_record <json> <rc> — JSON result 객체에서 토큰·비용을 뽑아 shard 에 1줄 append(jq).
_meter_record() {
  local raw="$1" rc="$2" shard ts
  # METER_LAST(옵트인) — 호출부 지정 파일에 이 호출의 usage 요약({in,out})을 덮어씀(yeta 답장 턴 tok 박제 = 뷰어 누적 미터 · 260709). 실패 = 무해(|| true).
  if [ -n "${METER_LAST:-}" ]; then
    printf '%s' "$raw" | jq -c '{in:((.usage.input_tokens // .usage.inputTokens) // 0), out:((.usage.output_tokens // .usage.outputTokens) // 0), cr:(.usage.cache_read_input_tokens // 0), cw:(.usage.cache_creation_input_tokens // 0)}' > "$METER_LAST" 2>/dev/null || true   # cr = 캐시 히트 토큰(260721 Q.36 — kimi 실비 환산: 히트는 1/10가라 분리 필요) · cw = 캐시 적재(260723 — 클로드 턴 실부피: input_tokens만 보면 i=2 착시)
  fi
  shard="$(_meter_shard)"
  mkdir -p metrics/usage 2>/dev/null || return 0
  ts="$(TZ='Asia/Seoul' date +%FT%T%:z 2>/dev/null)"   # KST(§📐 시각=KST)
  printf '%s' "$raw" | jq -c \
    --arg ts "$ts" --arg src "${METER_SRC:-?}" --arg ref "${METER_REF:-}" \
    --arg model "${METER_MODEL:-}" --arg effort "${METER_EFFORT:-}" \
    --arg run "${GITHUB_RUN_ID:-}" --arg job "${GITHUB_JOB:-local}" \
    --arg wf "${GITHUB_WORKFLOW:-local}" --argjson rc "${rc:-0}" '
    {
      ts:$ts, src:$src, ref:$ref,
      model:(if $model=="" then (.modelUsage|keys[0]? // "") else $model end), effort:$effort,
      in:((.usage.input_tokens // .usage.inputTokens) // 0),
      out:((.usage.output_tokens // .usage.outputTokens) // 0),
      cache_r:(.usage.cache_read_input_tokens // 0),
      cache_w:(.usage.cache_creation_input_tokens // 0),
      cost:(.total_cost_usd // .cost_usd // 0),
      turns:(.num_turns // 0), dur_ms:(.duration_ms // 0),
      run:$run, job:$job, wf:$wf, rc:$rc
    }' >> "$shard" 2>/dev/null || true
}

# is_flag_reject <errfile>: stderr 가 'CLI 가 그 **플래그**를 모른다'인지 — 플래그 드롭 폴백의 유일한 방아쇠.
#   ⚠️ 좁게 잡는 이유(260817 실측 사고): CLI 2.1.x 는 모르는 모델 이름에 대해 **정상 생성 중에도** 경고 한 줄을 stderr 로 흘린다 —
#     `[claude-code:unrecognized_model] {"model":"k3","query_source":"sdk"}` (= 컨텍스트 창 가정 안내일 뿐 · 생성은 그대로 성공).
#     종전 매칭이 맨 'unrecognized' 였던 탓에 이 경고가 모르는 모델을 쓰는 **매 턴마다** 플래그 거부로 오독됐다.
#   ∴ 'option' 을 동반한 형태만 플래그 거부로 본다(모델 경고·401·5xx 는 통과).
is_flag_reject() {
  grep -qiE 'unknown option|unrecognized option|unknown argument|unknown flag|requires --verbose' "${1:-/dev/null}" 2>/dev/null
}

# _meter_stderr_out <errfile> — CLI stderr 를 호출부로 재방류하되 **무해한 경고 줄만** 걸러낸다.
#   왜(260817 실측 사고): CLI 2.1.x 는 자기가 모르는 모델 이름(키미 k3 등)에 대해 정상 생성 중에도 경고를 흘린다 —
#     `[claude-code:unrecognized_model] {"model":"k3",...}` / `"k3" is not a model this version of Claude Code recognizes …`
#   이건 컨텍스트 창 가정 안내일 뿐 실패 사유가 아닌데, 호출부(yeta_chat·nudge·call 등)의 플래그 거부 사다리가
#   맨 'unrecognized' 로 매칭하는 바람에 **「system-prompt 플래그 거부」로 오독** → 캐릭터 시스템 카드를 떨군 채 재시도했다.
#   경고를 여기서 걷어내면 전 호출처의 사다리가 한 번에 정상화된다(매칭 SSOT 를 각 스크립트에서 고칠 필요 없음).
#   ⚠️ 걸러도 로그에서 사라지지 않게 접두를 달아 1줄 요약만 남긴다(관측 유지 · 오탐만 제거).
_meter_stderr_out() {
  local f="${1:-}" n=0
  [ -s "$f" ] || return 0
  n="$(grep -ciE 'unrecognized_model|is not a model this version of Claude Code recognizes' "$f" 2>/dev/null | head -n 1)"
  case "$n" in ''|*[!0-9]*) n=0 ;; esac   # grep -c 는 미발견 시 rc=1 이라 `|| echo 0` 을 붙이면 "0\n0" 이 되어 산술 비교가 깨진다(실측)
  grep -viE 'unrecognized_model|is not a model this version of Claude Code recognizes' "$f" >&2 2>/dev/null || true
  [ "$n" -gt 0 ] 2>/dev/null && echo "claude_meter: 모델명 미인식 경고 ${n}줄 무시(생성 무관 · 컨텍스트 창 가정 안내)" >&2
  return 0
}

# _meter_fail_note <출력> <rc> — 실패한 호출의 **진짜 사유**를 로그에 한 줄 남긴다.
#   왜: CLI 는 API 실패(401·404·5xx·타임아웃)를 stderr 가 아니라 stdout 의 result 문자열로 준다. 호출부 실패 경로가 stderr 만 찍던 탓에
#     러너 로그엔 원인이 한 줄도 안 남고 무관한 경고만 남아 진단이 매번 추측으로 갔다(260817 — 3분씩 두 번 죽은 런의 로그가 그랬다).
#   D2(대화 = 공개 로그 박제 금지): 오류 '형태'일 때만 앞 300자, 대사 형태면 길이만.
_meter_fail_note() {
  local flat hit
  flat="$(printf '%s' "${1:-}" | tr '\n\r\t' '   ')"
  if [ -z "${flat// }" ]; then
    echo "claude_meter: 생성 실패(빈 출력 · rc=${2:-?} · 모델 ${METER_MODEL:-?}) — 타임아웃(rc=124)·조기 종료 의심" >&2; return 0
  fi
  # 오류 표지 **첫 등장 지점 주변**만 창으로 뜬다 — 실패 출력이 원시 stream-json 1만여 자일 때 앞 300자에는 사유가 없다(진단 무의미).
  # api_retry = CLI 가 API 실패를 stream-json 으로 흘리는 정본 이벤트({"subtype":"api_retry","error_status":401,"error":"authentication_failed",…}).
  #   CLI 는 여기서 **max_retries 10회**를 조용히 소진하므로(호출당 수십 초~수 분) 이 표지를 못 잡으면 「왜 3분씩 걸리다 죽는지」가 로그에 안 남는다.
  hit="$(printf '%s' "$flat" | grep -aoiE '.{0,60}(api_retry|error_status|API Error|"type": ?"error"|"error": ?"|"is_error": ?true|terminal_reason|error_type|authentication|invalid_request|permission_error|not_found_error|overloaded|rate_?limit|unauthorized|forbidden|"status": ?[45][0-9][0-9]).{0,200}' 2>/dev/null | head -n 1)"
  if [ -n "$hit" ]; then
    echo "claude_meter: 생성 실패(rc=${2:-?} · 모델 ${METER_MODEL:-?}) 사유 — ${hit}" >&2
  else
    echo "claude_meter: 생성 실패(rc=${2:-?} · 모델 ${METER_MODEL:-?}) 출력 ${#1}자 · 오류 표지 없음 = 대사 가능성 → 내용 미기록(D2)" >&2
  fi
  return 0
}

# claude_meter <timeout_s> [claude args after 'claude -p' ...]   (프롬프트는 stdin)
claude_meter() {
  local to="$1"; shift
  local raw rc bare=""
  # --bare 게이트 (생성경로 CLAUDE.md auto-discovery 스킵 = 안 읽는 라우터 ~37k 토큰 컨텍스트 누수 차단 · 260701).
  # 기본 ON · 품질 규칙은 stdin(inject_guidelines 주입)이 결정하므로 무영향 · 롤백 = env CLAUDE_BARE=0. judge(GATE_BARE·py)와 동형.
  case "${CLAUDE_BARE:-0}" in 0|false|no|off|"") ;; *) bare="--bare" ;; esac
  # 폴백 1 — 계측 끄기(METER_OFF) 또는 jq 부재: 옛 동작 그대로(--output-format json 미부착 = 마크다운 stdout).
  if [ "${METER_OFF:-0}" = "1" ] || ! command -v jq >/dev/null 2>&1; then
    timeout "$to" claude -p $bare "$@"
    return $?
  fi
  # 스트리밍 모드(옵트인 · METER_STREAM=필터 경로 — yeta 챗 전용 260714): stream-json 델타를 필터가 R2 draft로 흘리고
  #   최종 result 이벤트(JSON 1개 = json 모드와 동형)만 stdout에 남김 → 아래 기존 파서(.result)·계측·실패판정 전부 그대로 호환.
  #   구 CLI가 stream 플래그를 거부하면 json 모드 1회 폴백(stdin은 버퍼해 재공급).
  #   미설정(기본) = 이 분기 자체가 없던 일 — 타 호출처 무영향.
  if [ -n "${METER_STREAM:-}" ] && [ -f "${METER_STREAM}" ]; then
    local _pin _serr=/tmp/claude_meter_stream.err _rcf=/tmp/claude_meter_stream.rc; _pin="$(cat)"; rm -f "$_rcf"
    # ⚠️ 플래그 거부는 stderr로 나온다 — stdout($raw) grep은 미발화 + --verbose 진단 라인 오탐(평의회 260714 플랫폼 HIGH) → stderr 파일 포집으로 판정.
    # ⚠️ rc = **claude 의 것**을 파일로 건져 쓴다(260817). 종전 `rc=$?` 는 파이프 끝단(필터)의 rc 라 필터가 늘 0으로 끝나면
    #   API 실패(401·5xx·타임아웃)도 rc=0 이 됐고, 필터의 「result 이벤트 부재 = 원문 라인 그대로」 폴백과 겹쳐
    #   **생성 실패가 rc=0 + 원시 stream-json 1만여 자**로 호출부에 넘어갔다(= 그게 대사로 박제될 뻔한 걸 프레임이탈 그물이 겨우 막던 상태 ·
    #   쿼터·과부하 판정도 그 경로에선 못 돌았다). 주석의 「호출처가 pipefail」 전제는 실제로 성립하지 않는다(yeta_chat 미설정 — 실측).
    raw="$( { printf '%s' "$_pin" | timeout "$to" claude -p $bare --output-format stream-json --include-partial-messages --verbose "$@" 2>"$_serr"; echo $? > "$_rcf"; } | python3 "$METER_STREAM")"
    rc=$?
    local _crc; _crc="$(head -n 1 "$_rcf" 2>/dev/null)"; case "$_crc" in ''|*[!0-9]*) _crc=0 ;; esac
    # 채택 규칙(회귀 0 우선): **쓸 만한 답이 나왔으면 종전대로 성공**으로 둔다 — 답을 다 받은 뒤 늦게 죽는 케이스에서
    #   멀쩡한 답장을 버리고 재생성하는 회귀를 만들지 않으려는 것. claude 의 rc 는 「유효 result 가 없다」 또는 「is_error=true」일 때만 채택한다.
    if ! printf '%s' "$raw" | jq -e '.result | type == "string"' >/dev/null 2>&1 \
       || printf '%s' "$raw" | jq -e '.is_error == true' >/dev/null 2>&1; then
      rc="$_crc"; [ "$rc" = "0" ] && rc=1   # 실패인데 종료코드가 0이면 1로 승격(호출부 실패판정·폴오버가 돌 수 있게)
    fi
    # ⚠️ 매칭 = 위 is_flag_reject(이 파일) — 종전 맨 'unrecognized' 는 CLI 의 unrecognized_model **경고**(정상 동작)까지 물어
    #   모르는 모델 이름(kimi k3 등)을 쓰는 턴마다 json 모드 재호출이 얹혀 생성이 2배로 돌았다(260817 실측).
    if ! printf '%s' "$raw" | jq -e '.result | type == "string"' >/dev/null 2>&1 \
       && is_flag_reject "$_serr"; then
      raw="$(printf '%s' "$_pin" | timeout "$to" claude -p $bare --output-format json "$@")"
      rc=$?
    fi
    _meter_stderr_out "$_serr"   # stderr 재방류(무해 경고만 걸러서) — 호출부 effort/system-prompt 거부·폴오버 매칭 계약 보존
  else
    local _serr2=/tmp/claude_meter.err
    raw="$(timeout "$to" claude -p $bare --output-format json "$@" 2>"$_serr2")"
    rc=$?
    _meter_stderr_out "$_serr2"   # 종전엔 stderr 가 호출부로 직행했다 — 같은 무해 경고 필터를 태우려고 여기서도 1홉 경유(내용·순서 무변경)
  fi
  # 정상 JSON(.result 가 문자열) → 계측 + .result 만 흘림(호출부 파싱 무변경).
  if printf '%s' "$raw" | jq -e '.result | type == "string"' >/dev/null 2>&1; then
    _meter_record "$raw" "$rc"
    printf '%s' "$raw" | jq -r '.result' 2>/dev/null
    [ "${rc:-0}" -ne 0 ] && _meter_fail_note "$(printf '%s' "$raw" | jq -r '.result' 2>/dev/null)" "$rc"
  else
    # 비정상(크래시·과부하·인증오류 등) → raw 그대로(호출부 실패판정·폴오버가 옛날처럼 작동).
    printf '%s' "$raw"
    _meter_fail_note "$raw" "$rc"
  fi
  return $rc
}
