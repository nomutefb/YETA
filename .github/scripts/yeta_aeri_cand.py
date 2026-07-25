#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_aeri_cand.py — 신규 주민 '애리쌤' 이미지 일괄 생성·탑재(운영자 260721 "제미나이 말고 지피티로 얼굴 만들고 일반 사람처럼 탑재 · 지도도 · 표정 위주 8장").

Gemini 월 지출 한도 429(260721 실측)로 OpenAI(gpt-image = yeta_char_art.py 10인 초상과 동일 축)로 전환. 3종 일괄:
  ① 초상 1장(2:3) → viewer/assets/yeta_char/aeri.png(+webp 768w) + 상단 정사각 512² 크롭 av/aeri.webp + roster avatar 자동 주입(= 일반 주민 탑재 규약 · yeta_char_art 동형)
  ② 지도 워커 스프라이트 → viewer/assets/yeta_map/char_aeri.png(그린스크린 → 크로마키 → 트림 → 320px = yeta_map_char.py 동형)
  ③ 표정 갤러리 8장(평범한 사무실 배경 · 표정이 분위기 전달 · 클로즈업/상반신/전신 카메라 각도 변주) → viewer/characters/aeri/<표정>_01.webp(용량 = webp만 보존)
  ④ 지브리 얼빡 프사(운영자 260725 "애리쌤만 제미나이에서 지브리스타일로 하나 뽑아서 올드함을 강조") — `AERI_GHIBLI=1` 단독 축:
     Gemini 1:1 극단 클로즈업 → viewer/assets/yeta_char/aeri_ghibli.png(편집 베이스) + av/aeri.webp 교체 + roster 배선(값 동일·그림만 갈림).
     이 축은 ①②③을 건너뛴다(다른 산출물 불변) · 게이트 = GEMINI_API_KEY.
수동 dispatch 전용(⚠️ OpenAI·Gemini 유료 종량제 · 자동 트리거 금지 = 이미지 파이프 공통 규약).
멱등: 있으면 skip(FORCE=1 재생성). 게이트 = OPENAI_API_KEY(없으면 no-op · ④는 GEMINI_API_KEY).
"""
import base64, io, json, os, re, shutil, subprocess, sys, time, urllib.request

KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY_nomute", "")
MODEL = (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2").strip()
API = "https://api.openai.com/v1/images/generations"
FORCE = os.environ.get("FORCE", "") == "1"
# ── 지브리 얼빡 프사 축(운영자 260725 "애리쌤만 제미나이에서 지브리스타일로 하나 뽑아서 올드함을 강조") ──
GHIBLI = os.environ.get("AERI_GHIBLI", "") == "1"   # 1 = 이 축만 돌린다(①②③ 건너뜀 · 다른 산출물 불변)
GEM_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEM_MODEL = "gemini-3.1-flash-image-preview"        # 모델 ID SSOT = shared/models.json gemini_image(게이트 check_model_ids)
GEM_API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(GEM_MODEL)
CHAR_DIR = "viewer/assets/yeta_char"
AVDIR = os.path.join(CHAR_DIR, "av")
MAP_DIR = "viewer/assets/yeta_map"
EXPR_DIR = "viewer/characters/aeri"
ROSTER = "apps/yeta/characters/roster.json"
AV_URL = "assets/yeta_char/av/aeri.webp"

# 인물 스펙 고정(카드 정본 = aeri.md 수치 주석) — 미형 보정 금지가 정체성: 평범한 인상의 52세.
WHO = ("a plain ordinary-looking Korean woman in her early 50s — NOT glamorous, NOT beautified, believable everyday middle-aged face, "
       "light-brown short bob haircut, glasses, slightly dated old-fashioned styling with a knit cardigan, silk scarf and a small brooch "
       "(not nerdy, just a bit behind the trends)")

# ① 초상(주민 표준 · yeta_char_art BASE 결 계승 — 단 '미형' 가드 반전)
PORTRAIT = ("Character portrait, polished Korean manhwa / webtoon key-art illustration, painterly semi-realistic, "
            "half-body (waist-up) shot, vertical 2:3 composition, one single original fictional character, " + WHO + ", "
            "standing in her small second-floor culture classroom in Mueum-dong — a back-alley Seoul neighborhood where the night runs longer than the day — "
            "in front of a wall crowded with framed two-shot photos and autographs, "
            "a modest self-effacing smile that doesn't quite open up, warm lamplight against deep shadows, "
            "a restrained palette with a muted antique-gold (#c9a86b) accent, "
            "no text, no caption, no watermark, no logo, no border.")

# ② 지도 스프라이트(yeta_map_char.py BASE 동형 — 걷는 치비 한 컷 · 그린스크린)
SPRITE = ("tiny cute chibi full-body character sprite for a cozy village map game, 3/4 top-down view, "
          "mid-step walking pose facing slightly left, flat pastel cartoon style with soft outlines, "
          "a plain middle-aged Korean woman with a light-brown short bob and glasses, knit cardigan and scarf, "
          "clutching a folder of papers to her chest while glancing sideways curiously, muted antique-gold color accents, busybody quick walk. "
          "Single character only, centered, whole body visible with margin. "
          "Plain solid pure bright green background color #00FF00 filling the entire frame (chroma key). "
          "No text, no letters, no watermark, no shadow on the ground.")

# ③ 표정 갤러리(운영자 260721 "평범한 사무실 · 표정 위주 · 전신/상반신 · 카메라 각도 다양 · 분위기는 표정이 나타냄")
EXPR_BASE = ("Expressive character study, polished Korean manhwa / webtoon key-art illustration, painterly semi-realistic, "
             "vertical 2:3 composition, one single original fictional character, " + WHO + ", "
             "inside a plain ordinary small office-like culture classroom (beige walls, cluttered desk, bookshelf, framed photos), "
             "THE FACIAL EXPRESSION carries the entire mood of the image, "
             "no text, no caption, no watermark, no logo, no border. Shot — ")
EXPRS = [
    ("gossip_sparkle_01",   "upper-body shot leaning in across the desk toward the camera, eyes sparkling wide behind glasses, one hand half-covering a thrilled conspiratorial grin, mid-whisper of a juicy secret."),
    ("flustered_wave_01",   "upper-body three-quarter angle, flustered and shrinking, waving both hands to deflect a compliment, awkward embarrassed half-smile, shoulders pulled in, gaze slipping sideways."),
    ("proud_wall_01",       "full-body shot standing beside a photo-covered wall, chin slightly lifted, hands clasped in front, a quietly proud contained smile trying not to show."),
    ("frozen_startle_01",   "full-body side-angle shot at the doorway, frozen mid-step, eyes wide and stiff with panic behind glasses, clutching her folder, caught by someone she idolizes."),
    ("brooding_night_01",   "upper-body shot at a dim desk lit by a single lamp at night, glasses held in one hand, staring down deflated, a bitter wounded expression chewing over a slight."),
    ("lecture_confident_01","upper-body front shot mid-lecture, pointing a pen forward, animated confident teaching face, eyebrows raised, the only place she shines directly."),
    ("wistful_drawer_01",   "close-up over-the-shoulder low-angle shot, gazing down at an old manuscript bundle inside a desk drawer, wistful longing eyes, lips slightly pressed."),
    ("cold_smirk_01",       "close-up slightly high-angle shot, a cooled polite smile that doesn't reach the skeptical narrowed eyes, listening to someone else's name-dropping."),
]


def openai_image(prompt, size="1024x1536"):
    """yeta_char_art.py openai_image 동형(자립형 규약)."""
    payload = {"model": MODEL, "prompt": prompt, "size": size, "n": 1}
    req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = (json.load(r).get("data") or [{}])[0]
            b = d.get("b64_json")
            if b:
                return base64.b64decode(b)
            u = d.get("url")
            if u:
                with urllib.request.urlopen(u, timeout=120) as r2:
                    return r2.read()
            print("  ⚠️ 이미지 파트 없음", flush=True)
            return None
        except Exception as e:
            print(f"  ⚠️ 생성 실패: {e}", flush=True)
            if attempt == 0:
                time.sleep(5); continue
    return None


def webp(path, width=768, q="82"):
    """뷰어 서빙용 webp 사본 — yeta_char_art.py 동형. ffmpeg 없으면 None(png 원본 유지)."""
    if not shutil.which("ffmpeg"):
        return None
    out = path[:-4] + ".webp"
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", f"scale={width}:-2",
                        "-quality", q, out], check=True, timeout=120)
        return out
    except Exception as e:
        print(f"  ⚠️ webp 변환 실패(비치명): {e}", flush=True)
        return None


def avatar_crop(png_path):
    """상단·가로중앙 정사각 512² webp = 작은 얼굴(yeta_char_art.py 동형 · 260713 운영자 눈검증 프레이밍)."""
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — av 크롭 생략", flush=True); return None
    os.makedirs(AVDIR, exist_ok=True)
    out = os.path.join(AVDIR, "aeri.webp")
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", png_path,
                        "-vf", "crop=iw/2:iw/2:iw/4:0,scale=512:512", "-quality", "86", out],
                       check=True, timeout=120)
        return out
    except Exception as e:
        print(f"  ⚠️ av 크롭 실패(비치명): {e}", flush=True); return None


def set_avatar(text, pid, url):
    """roster.json id 블록 안 avatar 값만 치환(yeta_char_art.py 동형 · 수제 포맷 보존)."""
    m = re.search(r'"id"\s*:\s*"%s"' % re.escape(pid), text)
    if not m:
        return text, False
    nxt = re.search(r'"id"\s*:\s*"', text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    seg, n = re.subn(r'"avatar"\s*:\s*"[^"]*"', '"avatar": "%s"' % url, text[m.end():end], count=1)
    if n == 0:
        return text, False
    return text[:m.end()] + seg + text[end:], True


def chroma_cut(png_bytes, size=320):
    """그린스크린 제거 → 투명 PNG + bbox 트림 + 축소(yeta_map_char.py 동형 · fail-soft)."""
    try:
        from PIL import Image
    except Exception:
        print("  ⚠️ Pillow 없음 — 원본 저장 폴백", flush=True)
        return png_bytes
    try:
        im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        px = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if g > 120 and g > r * 1.6 and g > b * 1.6:
                    px[x, y] = (0, 0, 0, 0)
                elif g > 90 and g > r * 1.25 and g > b * 1.25:
                    m = max(r, b)
                    px[x, y] = (r, min(g, int(m * 1.15)), b, a)
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)
        im.thumbnail((size, size), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception as e:
        print(f"  ⚠️ 크로마키 실패({e}) — 원본 저장 폴백", flush=True)
        return png_bytes


# 지브리 얼빡 프사(운영자 260725) — 프레이밍 어휘 = yeta_char_art.AV_BASE 계승(얼굴이 프레임을 꽉 채움 · 새 결 창작 0), 화풍만 지브리.
# "올드함"은 두 겹으로 = ⓐ인물(50대 주름·피로·유행 지난 차림 = WHO 정본 계승) ⓑ화풍(80~90년대 손그림 셀 애니·바랜 필름색).
GHIBLI_AV = ("Extreme close-up face shot — the face fills the entire square frame edge to edge with no margin, "
             "cropped just above the eyebrows and just below the lower lip, no shoulders, no neck, no scenery, "
             "perfectly square 1:1, one single original fictional character, "
             "hand-painted Studio-Ghibli-style 1980s-90s cel animation look — soft gouache watercolor rendering, "
             "warm rounded features drawn with a thin gentle ink line, flat honest shading, "
             "NO digital gloss, NO airbrush, NO manhwa key-art sheen, "
             "age worn openly and warmly: fine wrinkles at the eyes and mouth, laugh lines, a faint tiredness under the eyes, "
             "faded vintage film color grade with gentle grain as if scanned from an old animated feature, "
             "a modest self-effacing smile, looking straight at the viewer, "
             "no text, no caption, no watermark, no logo, no border. Character — " + WHO)


def gemini_image(prompt, aspect="1:1"):
    """Gemini 이미지 1장 → PNG bytes(실패 시 None · fail-soft). yeta_bg.py gemini_image 동형(imageSize 1K)."""
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseModalities": ["IMAGE"],
                                    "imageConfig": {"aspectRatio": aspect, "imageSize": "1K"}}}
    req = urllib.request.Request(GEM_API + "?key=" + GEM_KEY, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                j = json.loads(r.read().decode())
            for cand in j.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    inl = p.get("inlineData") or p.get("inline_data")
                    if inl and inl.get("data"):
                        return base64.b64decode(inl["data"])
            print("  ⚠️ 이미지 파트 없음(inlineData 부재)", flush=True); return None
        except Exception as e:
            code = getattr(e, "code", 0)
            body = ""
            try: body = e.read().decode()[:200]
            except Exception: pass
            print(f"  ⚠️ 제미나이 실패 {code} {body or e}", flush=True)
            if attempt == 0 and code in (429, 500, 503):
                time.sleep(4); continue
            return None
    return None


def av_square(png_path):
    """1:1 원본 → **확대 크롭** 512² webp = av/aeri.webp. ffmpeg 없으면 None.
    배율 = yeta_char_art.AV_ZOOM과 같은 값(0.72 · 10인 렌더 실측 확정) — 프롬프트만으론 정수리~턱 헤드샷으로 나와
    32px 원에서 얼굴이 작았다. 애리만 다른 배율이면 목록에서 혼자 튄다 = 같은 노브·같은 기본값으로 묶는다."""
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — av 변환 생략", flush=True); return None
    os.makedirs(AVDIR, exist_ok=True)
    out = os.path.join(AVDIR, "aeri.webp")
    z = (os.environ.get("YETA_AV_ZOOM") or "0.72").strip()
    yb = (os.environ.get("YETA_AV_YBIAS") or "0.04").strip()
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", png_path,
                        "-vf", f"crop=iw*{z}:iw*{z}:(iw-iw*{z})/2:(ih-iw*{z})/2-ih*{yb},scale=512:512",
                        "-quality", "86", out], check=True, timeout=120)
        return out
    except Exception as e:
        print(f"  ⚠️ av 변환 실패(비치명): {e}", flush=True); return None


def run_ghibli():
    """애리쌤 지브리 얼빡 1장(제미나이) → aeri_ghibli.png(원본·편집 베이스) + av/aeri.webp + roster 배선.
    다른 산출물(초상·스프라이트·표정 8장)은 손대지 않는다 — 이 축만 단독 실행."""
    if not GEM_KEY:
        print("GEMINI_API_KEY 없음 — 지브리 얼빡 생략(no-op)"); return 0
    os.makedirs(CHAR_DIR, exist_ok=True)
    src = os.path.join(CHAR_DIR, "aeri_ghibli.png")
    if os.path.exists(src) and not FORCE:
        print("skip 지브리 얼빡(기존 · FORCE=1로 재생성)")
    else:
        print("생성 지브리 얼빡(제미나이) …", flush=True)
        png = gemini_image(GHIBLI_AV)
        if not png:
            print("::warning::지브리 얼빡 생성 실패 — 산출물 무변경"); return 0
        open(src, "wb").write(png)
        print(f"  ✓ {src} ({len(png)//1024}KB)", flush=True)
    if av_square(src) and os.path.exists(ROSTER):
        roster = open(ROSTER, encoding="utf-8").read()
        roster, ok = set_avatar(roster, "aeri", AV_URL)   # 값은 종전과 동일(멱등) — 그림만 갈린다
        if ok:
            open(ROSTER, "w", encoding="utf-8").write(roster)
            print("  ✓ roster avatar 배선(값 동일·그림 교체)", flush=True)
    return 1


def main():
    if GHIBLI:   # 애리쌤 지브리 얼빡 단독 축(운영자 260725) — OPENAI 키 없어도 돈다(게이트 = GEMINI_API_KEY)
        n = run_ghibli()
        print(f"완료 — 지브리 얼빡 {n}장")
        return 0
    if not KEY:
        print("OPENAI_API_KEY 없음 — 애리 이미지 생성 생략(no-op)"); return 0
    made = 0

    # ① 초상 + av 크롭 + roster 배선
    os.makedirs(CHAR_DIR, exist_ok=True)
    portrait = os.path.join(CHAR_DIR, "aeri.png")
    if os.path.exists(portrait) and not FORCE:
        print("skip 초상(기존)")
    else:
        print("생성 초상 …", flush=True)
        png = openai_image(PORTRAIT)
        if png:
            open(portrait, "wb").write(png)
            webp(portrait)
            made += 1
            print(f"  ✓ {portrait} ({len(png)//1024}KB)", flush=True)
    if os.path.exists(portrait):
        if avatar_crop(portrait) and os.path.exists(ROSTER):
            roster = open(ROSTER, encoding="utf-8").read()
            roster, ok = set_avatar(roster, "aeri", AV_URL)
            if ok:
                open(ROSTER, "w", encoding="utf-8").write(roster)
                print("  ✓ roster avatar 배선", flush=True)
            else:
                print("  ⚠️ roster 주입 실패(avatar 키 없음?)", flush=True)

    # ② 지도 워커 스프라이트
    os.makedirs(MAP_DIR, exist_ok=True)
    sprite = os.path.join(MAP_DIR, "char_aeri.png")
    if os.path.exists(sprite) and not FORCE:
        print("skip 스프라이트(기존)")
    else:
        print("생성 지도 스프라이트 …", flush=True)
        png = openai_image(SPRITE, size="1024x1024")
        if png:
            open(sprite, "wb").write(chroma_cut(png))
            made += 1
            print(f"  ✓ {sprite}", flush=True)

    # ③ 표정 갤러리 8장(webp만 보존 — 용량)
    os.makedirs(EXPR_DIR, exist_ok=True)
    for name, desc in EXPRS:
        final = os.path.join(EXPR_DIR, f"{name}.webp")
        tmp_png = os.path.join(EXPR_DIR, f"{name}.png")
        if (os.path.exists(final) or os.path.exists(tmp_png)) and not FORCE:
            print(f"skip {name}(기존)"); continue
        print(f"생성 {name} …", flush=True)
        png = openai_image(EXPR_BASE + desc)
        if not png:
            continue
        open(tmp_png, "wb").write(png)
        if webp(tmp_png):
            os.remove(tmp_png)   # webp 성공 시 png 미보존(갤러리 용량 규약 · 초상만 png 편집 베이스 유지)
        made += 1
        print(f"  ✓ {name}", flush=True)
        time.sleep(2)

    print(f"완료 — 신규 {made}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
