#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_bg.py — 무음동(yeta) 무대 배경 '직영' 생성 (9:16 · Gemini · 수동 dispatch 전용 · 자립형).

무대(찻집·편집국·연습실…) 8장면을 Gemini로 생성 → R2 공개 버킷 `yeta_bg/<key>.png` 업로드 →
roster.json 의 해당 페르소나 bg 슬롯에 공개 URL 주입(라인 정규식 = 수제 포맷 보존).
뷰어(yApply)는 bg 위에 어두운 그라데를 얹고 cover+center 로 그림 = "늘리지 말고 중앙 크롭"(운영자 260703).

⚠️ 과금: Gemini 이미지 8콜(+무드 배리언트) = 유료. **자동경로 금지 — workflow_dispatch(yeta-bg.yml) 수동 1회성만**
   (챗 구독 OAuth와 완전 별개 축 · 운영자 직접 지시 260703 "몇개 제미나이로 뽑아 저장").
게이트 = GEMINI_API_KEY(없으면 no-op). 공개 R2 5시크릿 없으면 git 폴백(viewer/assets/yeta_bg/ 커밋).
멱등: roster bg 가 이미 차 있으면 그 무대는 skip(FORCE=1 이면 재생성·덮어쓰기). R2에 이미 있으면 재생성 0(URL만 주입).
⚠️ 독립 레포(muteno/yeta) 자립형 — nomute thumb_gen 의존 제거·Gemini 호출·R2 업로드 인라인(260704 이식·yeta_face.py 패턴).
"""
import os, re, sys, time, json, base64, hashlib, tempfile, subprocess, urllib.request, urllib.error

ROSTER = "apps/yeta/characters/roster.json"
LOCAL_DIR = "viewer/assets/yeta_bg"   # R2 미설정 git 폴백(뷰어 상대경로 서빙)
KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = "gemini-3.1-flash-image-preview"   # 카드/썸네일과 동일 모델(nomute thumb_gen 정합) · 실제 ID 바뀌면 여기 교체
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(MODEL)

# ── 공개 R2(배경 호스팅) — 챗 세션(YETA_R2_BUCKET·비공개)과 별도 버킷. 계정 키는 공용 재사용(§🔑 인프라). ──
R2_ACCOUNT = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()                    # 공개 버킷(≠ YETA_R2_BUCKET)
R2_PUBLIC = os.environ.get("R2_PUBLIC_BASE", "").strip().rstrip("/")   # 예: https://pub-xxxx.r2.dev
R2_KEY = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_ON = all([R2_ACCOUNT, R2_BUCKET, R2_PUBLIC, R2_KEY, R2_SECRET])

# 공통 스타일 — 채팅 배경용(무인·야간·저대비·텍스트 프리·full-bleed). 뷰어가 위에 어두운 그라데를 얹으므로 무드 중심.
BASE = ("서울 변두리, 밤이 긴 골목 '무음동'의 한 장면. 세로 9:16 모바일 채팅 배경. "
        "사람 없음(무인 공간). 반실사 애니 일러스트 배경 아트(semi-realistic anime-style illustrated background, glossy painterly rendering — 캐릭터 초상과 같은 톤·NOT 실사 사진), "
        "어둡고 차분한 여름밤 톤, 은은한 인공조명, 낮은 대비, 몽환적이고 은은한 판타지 분위기. "
        "글자·간판 텍스트·자막·워터마크·로고 없음. 화면 가장자리까지 장면으로 꽉 채움(여백·레터박스 금지). ")

# 무대 8장면 → 페르소나 매핑(10인 전원 커버 · 찻집=무디·하은 / 골목=가을·백 공유)
STAGES = [
    ("tea",       ["mudi", "haeun"], "24시 찻집 '무음' 내부. 원목 카운터 위 찻주전자와 김이 오르는 찻잔, 따뜻한 전구색 펜던트 조명, 창밖은 어두운 골목."),
    ("teacorner", ["kopi"],          "심야 찻집의 구석 자리. 열린 노트북과 흩어진 원고 뭉치, 작은 스탠드 조명 하나, 반쯤 남은 찻잔."),
    ("office",    ["desk"],          "공유오피스 3층 편집국의 밤. 켜진 모니터 불빛, 벽의 코르크보드와 붙은 메모들, 창밖 도시 야경."),
    ("studio",    ["sera"],          "지하 아이돌 연습실의 심야. 거울 벽, 형광등은 일부만 켜짐, 바닥의 물병과 수건, 문틈으로 새는 복도 불빛."),
    ("alley",     ["gaeul", "baek"], "여름밤 골목 상점가. 비 갠 뒤 젖은 아스팔트에 비친 상점 불빛, 처마 밑 전구 줄, 인적 없는 골목길."),
    ("dojo",      ["ryu"],           "검도장 '월광'의 밤. 마룻바닥에 길게 든 달빛, 벽의 죽도 걸이, 반쯤 열린 미닫이문 너머 마당."),
    ("gym",       ["von"],           "체육관 '강철'의 새벽. 샌드백과 바벨, 높은 창으로 드는 푸른 새벽빛, 거친 콘크리트 벽."),
    ("radio",     ["yun"],           "심야 라디오 부스 '주파수'. 붉은 ON AIR 무드의 콘솔 페이더와 마이크, 어두운 방음벽, 작은 조명."),
]

# 감정(무드) 배리언트(운영자 260703 "배경으로 감정·분위기") — 같은 무대가 공기만 바뀜(무대 유지 = 몰입 유지).
# 답장 <<MOOD:x>> 태그(yeta_chat.sh 파싱) → 뷰어가 yeta_bg/<stage>_<mood>.png 로 크로스페이드(URL 규약 파생 — roster 는 base 만).
MOODS = [
    ("warm",  "따뜻하고 아늑한 공기 — 전구색 조명이 더 풍성하고 부드러운 빛번짐, 온기 도는 색감, 편안한 분위기."),
    ("tense", "긴장감 도는 공기 — 차갑고 푸른 색조, 그늘이 깊고 조명 일부가 꺼짐, 대비가 살짝 올라간 서늘한 분위기."),
    ("blue",  "쓸쓸하고 조용한 공기 — 비가 막 그친 듯한 습기, 유리에 맺힌 물기·푸른 새벽빛, 채도를 낮춘 가라앉은 분위기."),
]

_USAGE = []   # Gemini 호출 토큰 누적(로그용)


def gemini_image(prompt, aspect="9:16"):
    """Gemini 이미지 1장 → PNG bytes(실패 시 None · fail-soft). imageSize 1K 고정(토큰 절감). nomute thumb_gen.gemini_image 인라인."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"aspectRatio": aspect, "imageSize": "1K"}},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(API + "?key=" + KEY, data=data, headers={"Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.loads(r.read().decode())
            um = j.get("usageMetadata") or {}
            if isinstance(um, dict):
                _USAGE.append(int(um.get("totalTokenCount") or 0))   # 실제 호출 과금 반영(이미지 파트 유무 무관)
            for cand in j.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    inl = p.get("inlineData") or p.get("inline_data")
                    if inl and inl.get("data"):
                        return base64.b64decode(inl["data"])
            print("  ⚠️ 이미지 파트 없음(응답에 inlineData 부재)", flush=True)
            return None
        except urllib.error.HTTPError as e:
            print("  ⚠️ HTTP {} — {}".format(e.code, e.read().decode()[:250]), flush=True)
            if e.code in (429, 500, 503) and attempt == 0:
                time.sleep(4); continue
            return None
        except Exception as e:
            print("  ⚠️ 호출 실패: {}".format(e), flush=True)
            if attempt == 0:
                time.sleep(4); continue
            return None
    return None


def r2_upload(png_bytes, key, content_type="image/png"):
    """바이트 → 공개 R2 업로드(aws cli S3호환·러너 기본설치) → 공개 URL. 실패 시 None(fail-soft → git 폴백). yeta_face.py 동형."""
    endpoint = "https://{}.r2.cloudflarestorage.com".format(R2_ACCOUNT)
    env = dict(os.environ, AWS_ACCESS_KEY_ID=R2_KEY, AWS_SECRET_ACCESS_KEY=R2_SECRET,
               AWS_DEFAULT_REGION="auto")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(png_bytes); tmp = f.name
        subprocess.run(["aws", "s3", "cp", tmp, "s3://{}/{}".format(R2_BUCKET, key),
                        "--endpoint-url", endpoint, "--content-type", content_type,
                        "--only-show-errors"], check=True, env=env, timeout=90)
        return "{}/{}".format(R2_PUBLIC, key)
    except Exception as e:
        print("  ⚠️ R2 업로드 실패: {}".format(e), flush=True)
        return None
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def r2_head(key):
    """R2 객체 존재 확인 + ETag(단순 업로드=md5) → (존재, etag 12자). 재과금 0 재사용용 —
    이전 런이 업로드 성공 후 커밋(roster 주입)만 유실됐을 때 Gemini 재호출 없이 URL만 주입."""
    if not R2_ON:
        return False, ""
    endpoint = "https://{}.r2.cloudflarestorage.com".format(R2_ACCOUNT)
    env = dict(os.environ, AWS_ACCESS_KEY_ID=R2_KEY, AWS_SECRET_ACCESS_KEY=R2_SECRET,
               AWS_DEFAULT_REGION="auto")
    try:
        out = subprocess.run(["aws", "s3api", "head-object", "--bucket", R2_BUCKET, "--key", key,
                              "--endpoint-url", endpoint, "--query", "ETag", "--output", "text"],
                             capture_output=True, text=True, env=env, timeout=30)
        if out.returncode != 0:
            return False, ""
        return True, out.stdout.strip().strip('"')[:12]
    except Exception:
        return False, ""


def set_bg(text, pid, url):
    """roster.json — "id":"<pid>" 객체 블록 안의 "bg" 값 교체(멀티라인 pretty JSON 대응 · 260712 픽스).
    이전 '1줄=1명' 가정은 pretty JSON(id·bg 다른 줄)에서 '라인 못 찾음'으로 주입 실패했다."""
    m = re.search(r'"id"\s*:\s*"%s"' % re.escape(pid), text)
    if not m:
        return text, False
    nxt = re.search(r'"id"\s*:\s*"', text[m.end():])   # 다음 캐릭터 객체 시작 = 이 블록 끝
    end = m.end() + nxt.start() if nxt else len(text)
    seg, n = re.subn(r'"bg"\s*:\s*"[^"]*"', '"bg": "%s"' % url, text[m.end():end], count=1)
    if n == 0:
        return text, False
    return text[:m.end()] + seg + text[end:], True


def main():
    if not KEY:
        print("GEMINI_API_KEY 없음 — 배경 생성 생략(no-op)"); return 0
    force = os.environ.get("FORCE", "") == "1"
    only = os.environ.get("YETA_BG_ONLY", "").strip()   # 특정 무대 하나만(연결·키 테스트 · 비용 절감)
    try:
        roster = open(ROSTER, encoding="utf-8").read()
    except OSError:
        print("::error::roster.json 없음"); return 1

    stages = [s for s in STAGES if not only or s[0] == only]
    if only and not stages:
        print("::warning::YETA_BG_ONLY={} 가 STAGES에 없음".format(only)); return 0
    made, skipped, failed = 0, 0, 0
    for key, pids, scene in stages:
        # 멱등 — 대상 전원 bg 채워져 있으면 skip(FORCE=1 예외)
        if not force and all(re.search(r'"id"\s*:\s*"%s"[^\n]*"bg"\s*:\s*"[^"]+"' % re.escape(p), roster) for p in pids):
            print("· {} — bg 이미 있음, skip".format(key)); skipped += 1; continue
        r2key = "yeta_bg/{}.png".format(key)
        if not force:   # 재과금 0 — R2에 이미 객체 있으면(이전 런이 업로드 후 roster 주입만 유실) 생성 없이 URL만 주입
            exists, etag = r2_head(r2key)
            if exists:
                url = "{}/{}?v={}".format(R2_PUBLIC, r2key, etag)
                print("· {} — R2 기존 객체 재사용(생성 0): {}".format(key, url))
                for p in pids:
                    roster, hit = set_bg(roster, p, url)
                    print("  {} bg ← 재사용".format(p) if hit else "  ⚠️ {} 라인 못 찾음".format(p))
                made += 1; continue
        print("· {} 생성 — {}".format(key, scene[:38]), flush=True)
        png = gemini_image(BASE + scene, aspect="9:16")
        if not png:
            print("  ⚠️ 생성 실패 — {} 건너뜀(비치명)".format(key)); failed += 1; continue
        v = hashlib.sha256(png).hexdigest()[:8]   # 캐시버스트(재생성 시 URL 갱신 — R2 raw 5분 캐시 무관 즉시 반영)
        url = None
        if R2_ON:
            url = r2_upload(png, r2key)
            if url:
                url += "?v=" + v
        if not url:   # git 폴백 — 뷰어 상대경로(레포 비대 주의라 R2 권장)
            os.makedirs(LOCAL_DIR, exist_ok=True)
            open(os.path.join(LOCAL_DIR, key + ".png"), "wb").write(png)
            url = "assets/yeta_bg/{}.png?v={}".format(key, v)
            print("  ⚠️ R2 미설정/실패 → git 폴백: {}".format(url))
        for p in pids:
            roster, hit = set_bg(roster, p, url)
            print("  {} bg ← {}".format(p, url) if hit else "  ⚠️ {} 라인 못 찾음".format(p))
        made += 1

    # 무드 배리언트 — roster 무관(뷰어가 base URL에서 규약 파생)이라 멱등 키 = R2 존재(git 폴백은 로컬 파일 존재)
    for key, _pids, scene in stages:
        for mood, mod in MOODS:
            r2key = "yeta_bg/{}_{}.png".format(key, mood)
            local = os.path.join(LOCAL_DIR, "{}_{}.png".format(key, mood))
            if not force and (r2_head(r2key)[0] or os.path.exists(local)):
                skipped += 1; continue
            print("· {}_{} 생성".format(key, mood), flush=True)
            png = gemini_image(BASE + scene + " " + mod, aspect="9:16")
            if not png:
                print("  ⚠️ 생성 실패 — 건너뜀(비치명·재실행으로 채움)"); failed += 1; continue
            if not (R2_ON and r2_upload(png, r2key)):
                os.makedirs(LOCAL_DIR, exist_ok=True)
                open(local, "wb").write(png)
                print("  ⚠️ R2 미설정/실패 → git 폴백: {}".format(local))
            made += 1

    if made:
        open(ROSTER, "w", encoding="utf-8").write(roster)
    print("완료 — 생성 {} · skip {} · 실패 {}".format(made, skipped, failed))
    if _USAGE:
        print("Gemini 사용량: {}콜 · 총 {}tok".format(len(_USAGE), sum(_USAGE)))
    return 0   # 부분 실패 = 비치명(성공분만 반영 · 멱등이라 재실행으로 빈 무대만 채움)


if __name__ == "__main__":
    sys.exit(main())
