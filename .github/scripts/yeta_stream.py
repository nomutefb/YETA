#!/usr/bin/env python3
# yeta_stream.py — claude -p stream-json 수집 필터 + 문장 스트리밍 부분 박제(대화 속도 260714 한수2)
# 파이프: claude -p --output-format stream-json --include-partial-messages --verbose | 이 필터
#   stdout = 최종 result 이벤트 JSON 1개(= --output-format json 출력과 동형) → claude_meter 기존 파서(.result)·계측·실패판정 그대로 호환.
#   부수효과 = 텍스트 델타를 문장 경계로 모아 R2 draft(sessions/<char>.draft.json)에 발행 → 게이트웨이 watch가 감시 → 뷰어가 생성 중 문장부터 표시.
# 안전:
#   · 대사 밖 유출 0 — 첫 '<<' 이후 전부 보류(출력 계약상 <<NOTE>>/<<MOOD>>는 대사 뒤 = 기억 내용·무드 태그가 draft로 새지 않음) · 꼬리 낱개 '<'도 보류(다음 델타에서 << 가능).
#   · result 이벤트 부재(크래시·비정상) = 원문 라인 그대로 stdout(기존 is_quota/is_transient 폴오버 매칭 보존).
#   · draft 발행 실패 = 전부 무해(check=False·예외 삼킴) — 스트리밍은 가산 축, 본답장 파이프라인 무영향.
#   · 발행 게이트 = 새 문장 경계 + 최소 1.2s 간격(aws 서브프로세스 남발 방지 · R2 Class A ~2-6회/답장).
# env: YETA_DRAFT_KEY/BUCKET/EP(없으면 순수 수집만) · YETA_DRAFT_T(스레드)/YETA_DRAFT_P(페르소나) — 뷰어 스테일 가드용.
#      YETA_PTT_HEAD(선택 · PTT 턴만) = 헤드 TTS 선굽기 경로 프리픽스 — 첫 문장이 확정되는 순간 백그라운드로 yeta_tts.py 발사
#      (한수3 260714: 음성 대기 = 생성+전문TTS → 생성과 헤드TTS 병렬 · ptt_voice가 접두 일치 검증 후 나머지만 굽고 이어붙임 · 불일치 = 전문 폴백).
import hashlib, json, os, re, subprocess, sys, tempfile, time

KEY = os.environ.get("YETA_DRAFT_KEY", "")
BUCKET = os.environ.get("YETA_DRAFT_BUCKET", "")
EP = os.environ.get("YETA_DRAFT_EP", "")
TH = os.environ.get("YETA_DRAFT_T", "")
PS = os.environ.get("YETA_DRAFT_P", "")
HEAD = os.environ.get("YETA_PTT_HEAD", "")
FIRST = os.environ.get("YETA_STREAM_FIRST", "")   # 첫 발행 시각(epoch ms) 기록 파일 — 계기판 lat.f(첫문장까지) 재료(운영자 260714)
first_done = False
MIN_GAP = 1.2
last_pub = 0.0
pub_len = 0
buf = []
result = None
raw_lines = []
head_fired = False

MOODS = ("base", "warm", "tense", "blue", "joy", "love", "shy", "mad", "sulky")   # finish 화이트리스트와 짝(yeta_chat.sh 9감정 · Q.29 + 260726 삐짐 독립)
mood = ""   # 선두 <<MOOD:x>> 캡처분(출력 계약 첫 줄 · Q.81) — draft 동봉 = 뷰어가 생성 중에도 감정 글자 리졸브

def clean(t):
    global mood
    m = re.match(r'\s*<<\s*MOOD\s*:\s*([A-Za-z]+)\s*>>\s*', t, flags=re.I)   # 선두 MOOD(Q.81 출력 계약 첫 줄) — 캡처 후 대사에서 벗김(태그 유출 0 유지 · 미완성 '<<MO…'는 아래 find 보류가 그대로 잡음)
    if m:
        if not mood and m.group(1).lower() in MOODS: mood = m.group(1).lower()
        t = t[m.end():]
    i = t.find("<<")                      # 첫 마커부터 전부 보류 — NOTE 내용·꼬리 MOOD 태그 유출 원천 차단(대사는 마커 앞)
    if i >= 0: t = t[:i]
    if t.endswith("<"): t = t[:-1]        # 꼬리 낱개 '<' 보류(다음 델타에서 '<<' 완성 가능)
    return t.strip()[:4000]

# ⛔ SAFETY-LOCK[stream-guard] — 안전 가드레일(운영자 260714). 생성 중 스트리밍으로 거절 벽(영어 메타)이 뷰어에 새는 걸 막는 축. 약화·제거·임계완화 금지(LLM 세션 포함) · 변경 = check_refs SAFETY-LOCK 게이트 감지.
def frame_break(t):                       # 스트리밍 중 프레임이탈(콘텐츠 거절 영어 벽) 조기 감지(운영자 260714 스샷) — 지문 제거 후 40자↑인데 한글<15% = 영어 메타 → 발행 차단(is_frame_break(b) 미러 · 게이트웨이 draft 유출 봉합)
    x = re.sub(r"\*[^*\n]{1,400}\*", "", t)
    x = re.sub(r"[`_*]", "", x).strip()
    letters = [c for c in x if c.isalpha()]
    if len(x) <= 40 or not letters: return False
    han = sum(1 for c in letters if "가" <= c <= "힣")
    return han / len(letters) < 0.15

def publish(force=False):
    global last_pub, pub_len
    if not (KEY and BUCKET and EP): return
    t = clean("".join(buf))
    if not t or (len(t) <= pub_len and not force): return
    if frame_break(t): return             # 영어 거절 벽 = 뷰어에 안 흘림(gen_out is_frame_break가 폐기·이탈 폴백으로 갈음)
    now = time.time()
    if not force and now - last_pub < MIN_GAP: return
    if not force and not re.search(r"[.!?…~\n]", t[pub_len:]): return   # 새 문장 경계 없으면 보류(어중간한 단어 절단 노출 감소)
    try:
        d = {"t": TH, "p": PS, "ts": int(now * 1000), "text": t}
        if mood and mood != "base": d["mood"] = mood   # base = 무감정(뷰어 연출 비발동 축) — 동봉 생략 = 종전 draft와 동형
        body = json.dumps(d, ensure_ascii=False)
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        f.write(body); f.close()
        r = subprocess.run(["aws", "s3api", "put-object", "--bucket", BUCKET, "--key", KEY, "--body", f.name,
                            "--content-type", "application/json", "--endpoint-url", EP],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
        os.unlink(f.name)
        if r.returncode != 0: return               # 실패 발행 = 상태 미전진(다음 틱 재시도) · FIRST 미기록 = 거짓 f 방지(평의회 260714 계측)
        last_pub = now; pub_len = len(t)
        global first_done
        if FIRST and not first_done:
            first_done = True
            try: open(FIRST, "w").write(str(int(now * 1000)))   # 첫 문장 '성공' 발행 시각 — 계기판 f 축
            except Exception: pass
    except Exception:
        pass

def spoken_head(t):                       # ptt_voice의 spoken 정제와 동일 연산(접두 일치 계약 — 드리프트 금지: yeta_chat.sh ptt_voice 짝)
    t = re.split(r'^\s*\[[^\]\n]{1,24}\]\s', t, maxsplit=1, flags=re.M)[0]
    t = re.sub(r'\*[^*\n]{1,200}\*', '', t)
    t = re.sub(r'[`*_]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def try_head():                           # 첫 문장 확정 순간 헤드 TTS 백그라운드 발사(1회) — 실패 전부 무해(ptt_voice 전문 폴백)
    global head_fired
    if head_fired or not (HEAD and PS): return
    raw = clean("".join(buf))
    if not raw or raw.count("*") % 2: return          # 미닫힌 *지문* = 경계 미확정 — 정제 결과가 전문과 어긋날 수 있어 대기
    s2 = spoken_head(raw)
    head = ""
    for m in re.finditer(r'[.!?…~]', s2):             # 첫 '충분히 긴' 머리(≥5자)까지 — 짧은 감탄("안녕!")은 다음 문장까지 흡수
        if m.end() >= 5: head = s2[:m.end()].strip()[:200]; break
    if not head: return
    head_fired = True                                 # 성공/실패 무관 1회(재발사 소음 방지)
    try:
        # 콘텐츠 해시 결속(평의회 260714 레이스·오디오 MED) — gen_out 재시도로 attempt가 겹쳐도 txt↔mp3가 해시로 짝지어져 폐기 답장의 헤드 음성 오접합 원천 차단.
        h = hashlib.sha256(head.encode("utf-8")).hexdigest()[:8]
        open(HEAD + ".txt", "w", encoding="utf-8").write(head)
        subprocess.Popen(["bash", "-c",
            'python3 .github/scripts/yeta_tts.py "$1" "$2" "$3.part" >/dev/null 2>&1 && { mv -f "$3.part" "$3.mp3"; mv -f "$3.part.eng" "$3.eng" 2>/dev/null || true; }; echo done > "$3.done"',
            "_", PS, head, HEAD + "." + h], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

for line in sys.stdin:
    raw_lines.append(line)
    s = line.strip()
    if not s: continue
    try: ev = json.loads(s)
    except Exception: continue
    ty = ev.get("type")
    if ty == "stream_event":              # 토큰 델타(--include-partial-messages) — 부작용(발행·헤드)은 예외 격리: 본답장 stdout(result 수집)이 절대 안 죽게(평의회 260714 플랫폼 MED)
        try:
            d = (ev.get("event") or {}).get("delta") or {}
            if d.get("type") == "text_delta":
                buf.append(str(d.get("text") or "")); try_head(); publish()
        except Exception: pass
    elif ty == "assistant":               # 완결 어시스턴트 메시지 — 파셜 미지원 CLI에서도 메시지 단위 동기
        try:
            txt = "".join(c.get("text", "") for c in (ev.get("message") or {}).get("content") or [] if c.get("type") == "text")
            if len(txt) > len("".join(buf)): buf = [txt]; try_head(); publish()
        except Exception: pass
    elif ty == "result":
        result = ev

if result is not None:
    publish(force=True)                   # 마지막 조각까지 발행(확정 스왑 전 공백 최소화)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
else:
    sys.stdout.write("".join(raw_lines))  # 비정상 종료 = 원문 그대로(호출부 실패판정·폴오버 경로 보존)
