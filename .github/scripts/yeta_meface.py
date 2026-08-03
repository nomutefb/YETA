#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_meface.py — 유저 「내 캐릭터」 이미지 생성 (운영자 260710 · 3컷 시트 260803 · ⚠️ OpenAI 유료 — 트리거 = op meface 일 상한 / 수동 dispatch).

비공개 R2 세션(sess.me)에서 소개(about)·호칭(call)만 읽어 → 로스터 초상과 동일 스타일(STYLE_A/STYLE_B = yeta_face.py SSOT 임포트 = "캐릭터들 톤" 정합)
**한 장**을 생성한다. MEFACE_KIND:
  sheet(기본 · 운영자 260803 "캐릭보드는 필요없고 그냥 한장만 얼굴 상반신 전신 3d용 전신")
      = 세로 1024×1536 한 장에 3칸(위→아래) ① 얼굴 ② 상반신 ③ 3D 참조용 전신 A-포즈 정면.
        · 시트 전체 → 공개 R2 `yeta_face/me_sheet.png` → `sess.me.sheet`
        · **① 얼굴 칸을 잘라** `yeta_face/me.png` → `sess.me.avatar`(우상단 프사·버블 아바타 계약 그대로 = 회귀 0)
  face  = 종전 1:1 초상 1장(폴백·롤백 경로 — 프레이밍만 다르고 나머지 배관 동일).
MEFACE_MODE:
  apply(기본) = sess.me 에 URL CAS 주입(+ meface.pending 해제) — 뷰어 폴이 집어감.
  sample      = 세션 무기록 · `SAMPLE_URL=` 로그만(개발 검증용).

⚠️ public 레포 = 공개 Actions 로그 → 소개·호칭 원문 print 절대 금지(길이만) · 대화 turns 무접촉.
⚠️ git 폴백 없음(yeta_face와 다름) — 유저 개인화 이미지를 공개 레포에 커밋하지 않는다(공개 R2 미설정 = 명시 에러).
CAS = 러너 r2put 결(ETag if-match · 4회 루프).
"""
import os, sys, json, time, shutil, hashlib, subprocess, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from yeta_face import BASE, STYLE_A, STYLE_B, openai_image, r2_upload, R2_ON   # 스타일·이미지 호출·공개 R2 업로드 SSOT(복제 금지 = 드리프트 차단)

MODE = (os.environ.get("MEFACE_MODE") or "apply").strip() or "apply"
KIND = (os.environ.get("MEFACE_KIND") or "sheet").strip() or "sheet"   # sheet(기본 · 3컷) | face(구 1:1 초상)
SHEET_SIZE = "1024x1536"   # gpt-image 허용 3종 중 세로 — 3칸(각 1024×512)이 위→아래로 쌓인다
FACE_CROP = (512, 512)     # ① 얼굴 칸에서 잘라낼 정사각(칸 중앙) — 아바타는 원형 마스크라 정사각이 정답
ACC = os.environ.get("R2_ACCOUNT_ID", "").strip()
PRIV = os.environ.get("YETA_R2_BUCKET", "").strip()
EP = "https://{}.r2.cloudflarestorage.com".format(ACC)
KEY = "sessions/main.json"
SESS = "/tmp/yeta_meface_sess.json"


def aws(*args):
    env = dict(os.environ, AWS_ACCESS_KEY_ID=os.environ.get("R2_ACCESS_KEY_ID", ""),
               AWS_SECRET_ACCESS_KEY=os.environ.get("R2_SECRET_ACCESS_KEY", ""), AWS_DEFAULT_REGION="auto")
    return subprocess.run(["aws", *args, "--endpoint-url", EP], env=env, capture_output=True, text=True, timeout=90)


def sess_get():
    """비공개 세션 read + ETag(CAS 짝). 실패 = (None, None)."""
    r = aws("s3api", "get-object", "--bucket", PRIV, "--key", KEY, SESS)
    if r.returncode != 0:
        print("::error::세션 로드 실패"); print((r.stderr or "")[-300:], file=sys.stderr)
        return None, None
    etag = ""
    try:
        etag = (json.loads(r.stdout).get("ETag") or "").strip('"')
    except Exception:
        pass
    try:
        with open(SESS, encoding="utf-8") as f:
            return json.load(f), etag
    except Exception:
        print("::error::세션 파싱 실패"); return None, None


def sess_put(sess, etag):
    """조건부 put(ETag) — 경합 = False(호출부 fresh 재시도 · yeta_chat.sh r2put 동형)."""
    with open(SESS, "w", encoding="utf-8") as f:
        json.dump(sess, f, ensure_ascii=False)
    args = ["s3api", "put-object", "--bucket", PRIV, "--key", KEY, "--body", SESS, "--content-type", "application/json"]
    if etag:
        args += ["--if-match", etag]
    r = aws(*args)
    if r.returncode != 0:
        print("  ⚠️ 세션 put 실패(경합/기타) — 재시도", flush=True)
    return r.returncode == 0


def sheet_prompt(about):
    """3컷 시트 프롬프트 — 톤은 로스터 초상(STYLE_A/STYLE_B) 그대로, **프레이밍만** 갈아끼운다(FRAME_1X1 자리).
    칸 순서·비율을 못 박는 이유 = ① 얼굴 칸을 좌표로 잘라 아바타에 쓰기 때문(크롭이 규격에 의존)."""
    frame = ("ONE single vertical character sheet image of ONE single character, divided into exactly THREE stacked "
             "equal-height panels separated by thin clean gaps, all three panels showing THE SAME person with the "
             "IDENTICAL face, hairstyle and outfit: "
             "TOP panel — a head-and-shoulders close-up portrait, the face centered and filling the panel; "
             "MIDDLE panel — a waist-up half-body shot, front facing, hands visible; "
             "BOTTOM panel — a FULL-BODY reference for 3D modelling: the whole body from head to feet inside the panel, "
             "standing straight and symmetrical in a relaxed A-pose facing the camera, arms slightly away from the body, "
             "feet fully visible, even flat lighting on a plain neutral backdrop, no cropping, no dynamic angle, no props. "
             "No panel labels, no numbers, no frames, no text anywhere. ")
    return (STYLE_A + frame + STYLE_B + persona_line(about))


def persona_line(about):
    """소개 원문 = 이미지 프롬프트 재료(텍스트 명령이어도 그림 취향 반영 이상의 권한 없음 · 상한 op가 가드)."""
    return ("the player themselves — a regular late-night visitor of this alley who belongs in its world, "
            "an ordinary yet quietly charismatic person. Derive their look, styling, expression and mood from this "
            "self-introduction (personality first, tasteful, any gender that fits it): “" + about + "”. "
            "Warm approachable presence, a subtle lime-green accent glow in the background.")


def crop_face(png, w=1024, h=1536):
    """시트 ① 얼굴 칸(상단 1/3) 중앙에서 정사각을 잘라 아바타용 PNG로. ffmpeg = 러너 기본 설치(webp 파이프 선례).
    실패 = None(fail-soft) → 호출부가 시트 원본을 아바타로 폴백(프사가 아예 안 뜨는 것보다 낫다)."""
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — 얼굴 칸 크롭 생략", flush=True); return None
    cw, ch = FACE_CROP
    x, y = (w - cw) // 2, max(0, (h // 3 - ch) // 2)   # 칸 높이 512 = 크롭 512 → y=0(칸이 커지면 중앙)
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "sheet.png"), os.path.join(d, "face.png")
        with open(src, "wb") as f:
            f.write(png)
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                            "-vf", "crop={}:{}:{}:{}".format(cw, ch, x, y), dst],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not os.path.exists(dst):
            print("  ⚠️ 크롭 실패 — " + (r.stderr or "")[-200:], flush=True); return None
        with open(dst, "rb") as f:
            return f.read()


def main():
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY 없음 — 생성 생략(no-op 스캐폴드)"); return 0
    if not (ACC and PRIV):
        print("::error::비공개 R2 미설정(R2_ACCOUNT_ID/YETA_R2_BUCKET)"); return 1
    if not R2_ON:
        print("::error::공개 R2 미설정(R2_BUCKET·R2_PUBLIC_BASE 등 5종) — 유저 아바타는 git 폴백 없음(개인화 이미지 공개 레포 커밋 회피)"); return 1

    sess, etag = sess_get()
    if sess is None:
        return 1
    me = sess.get("me") or {}
    about = str(me.get("about") or "").strip()[:300]
    if not about:
        print("소개(me.about) 비어 있음 — 생성 생략(뷰어가 소개부터 유도)"); return 0
    sheet_mode = KIND != "face"
    print("· 소개 {}자 기반 생성(원문 비출력 · 종류 {} · 모드 {})".format(len(about), KIND, MODE), flush=True)

    # 로스터 톤 정합 — sheet = STYLE_A + 3컷 프레이밍 + STYLE_B / face = 종전 BASE(1:1 프레이밍) 그대로
    prompt = sheet_prompt(about) if sheet_mode else (BASE + persona_line(about))
    png = openai_image(prompt, SHEET_SIZE if sheet_mode else "1024x1024")
    if not png:
        print("::error::이미지 생성 실패"); return 1

    def put(bytes_, key):
        u = r2_upload(bytes_, key)
        return (u + "?v=" + hashlib.sha256(bytes_).hexdigest()[:8]) if u else None   # 고정 키 + 내용 해시 캐시버스트(재생성 = 파일 교체·URL 갱신)

    sheet_url = ""
    if sheet_mode:
        sheet_url = put(png, "yeta_face/me_sheet.png")
        if not sheet_url:
            print("::error::공개 R2 업로드 실패(시트)"); return 1
        print("시트 URL: " + sheet_url)
        face = crop_face(png)
        url = put(face, "yeta_face/me.png") if face else sheet_url   # 크롭 실패 = 시트를 프사로 폴백(빈 프사보다 낫다)
        if not url:
            print("::error::공개 R2 업로드 실패(얼굴 칸)"); return 1
    else:
        url = put(png, "yeta_face/me.png")
        if not url:
            print("::error::공개 R2 업로드 실패"); return 1
    print("이미지 URL: " + url)

    if MODE == "sample":
        print("SAMPLE_URL=" + url)   # 세션 무기록 — 개발 세션이 이 줄 파싱
        if sheet_url:
            print("SAMPLE_SHEET_URL=" + sheet_url)
        return 0

    for _ in range(4):   # apply — CAS 루프(러너 결)
        me2 = sess.setdefault("me", {})
        me2["avatar"] = url
        if sheet_url:
            me2["sheet"] = sheet_url   # 3컷 원본(프로필에서 열람 · 3D 참조용 전신 포함)
        mf = sess.setdefault("meface", {})
        mf["pending"] = 0; mf["url"] = url; mf["done"] = int(time.time() * 1000)
        if sheet_url:
            mf["sheet"] = sheet_url
        if sess_put(sess, etag):
            print("세션 주입 완료 — me.avatar{} 갱신".format(" · me.sheet" if sheet_url else "")); return 0
        time.sleep(1)
        sess, etag = sess_get()
        if sess is None:
            return 1
    print("::error::세션 CAS 4회 경합 — 주입 실패(이미지는 업로드됨 · 재실행으로 주입만 재시도 가능)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
