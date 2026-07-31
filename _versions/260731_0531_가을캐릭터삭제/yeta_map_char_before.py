# yeta 지도 미니 캐릭터 스프라이트 생성 — 수동 dispatch 전용(⚠️ Gemini 유료 · 260707 운영자 "쪼만한 게 걸어다니게 · 캐릭터별 특성 살아있게")
# 산출 = viewer/assets/yeta_map/char_<id>.png (투명 배경 · 지도 워커 스프라이트 — 걷기 모션은 지도 UI의 CSS 몫).
# 방식 = 그린스크린(#00FF00) 프롬프트 생성 → PIL 크로마키 제거 → bbox 트림 → 320px 축소(용량).
# 개성 정본 = 캐릭터 카드(apps/yeta/characters/*.md)의 시각 요소 요약 — 카드 개정 시 여기 desc도 손봐야 함.
# 멱등: 있으면 skip · FORCE=1 재생성 · 게이트 = GEMINI_API_KEY(없으면 no-op).
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = "gemini-3.1-flash-image-preview"
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(MODEL)
OUT_DIR = "viewer/assets/yeta_map"
FORCE = os.environ.get("FORCE", "").strip() == "1"

# 캐릭터별 시각 개성(카드 요약 · 걷는 포즈 한 컷) — 색 포인트 = roster color 근사
CHARS = {
    "mudi":  "calm young tea master in a dark apron, carrying a small wooden tea tray with a steaming cup, gentle smile, soft mint-green color accents, unhurried walk",
    "sera":  "sulky teen girl in an oversized hoodie and training pants, one earphone in, messy short hair, hands in pockets, pink color accents, slouchy walk",
    "haeun": "cheerful young woman teacher in a cardigan, swinging a tote bag, playful grin, warm yellow color accents, bouncy walk",
    "baek":  "stoic middle-aged watchman in a long dark coat, holding a flashlight, expressionless, blue-grey color accents, steady patrol walk",
    "ryu":   "lazy long-haired swordsman in a loose traditional dojo robe, folding fan in one hand and a liquor bottle hanging from the other, sky-blue color accents, slow strolling walk",
    "yun":   "sleepy late-night radio DJ with headphones around the neck, long dark coat, half-lidded eyes, purple color accents, quiet drifting walk",
    "desk":  "sharp editor in a shirt with loosened tie, stack of papers under one arm and a coffee cup, tired but focused, cobalt-blue color accents, brisk walk",
    "kopi":  "scruffy freelance copywriter in a worn hoodie, laptop bag across the shoulder and a tumbler, orange color accents, hurried shuffle walk",
    "gaeul": "dignified middle-aged market association president in a neat modern-hanbok jacket, holding a ledger book, composed expression, lavender color accents, confident walk",
    "von":   "muscular gym master in a tracksuit with a towel around the neck, energetic, red-orange color accents, powerful stride",
    "lucy":  "aloof doll-like girl with long pale hair, holding a small paper coffee cup at her fingertips, expressionless half-lidded eyes, deep crimson color accents, slow detached walk",   # 에픽 1호 루시(카드 260707) — 스프라이트 부재로 지도 폴백 노출(운영자 260716 "특정 인물 검정") · 소품 = 담배→커피(카드 '커피도 사랑' 결 유지 — 담배 묘사는 Gemini가 이미지 미반환)
    "winter": "graceful young woman idol in casual off-stage wear, short neat hair, calm cool expression with a faint warm smile, ice-blue color accents, poised light walk",   # 아이돌 윈터(카드) — 동상
}
BASE = ("tiny cute chibi full-body character sprite for a cozy village map game, 3/4 top-down view, "
        "mid-step walking pose facing slightly left, flat pastel cartoon style with soft outlines, {desc}. "
        "Single character only, centered, whole body visible with margin. "
        "Plain solid pure bright green background color #00FF00 filling the entire frame (chroma key). "
        "No text, no letters, no watermark, no shadow on the ground.")

# 지도 합성용 건물 스프라이트(운영자 260717 "성당이 지하성당 같음 — 그림 새로 뽑아 레이어를 새로 따면 될듯") — 산출 = bld_<이름>.png(투명 · 뷰어가 배경 위 레이어로 합성 · 지도 원본 무수정 = 기계산출물 규약)
BLDG_BASE = ("small charming sacred neighborhood cathedral building for a cozy hand-drawn cartoon city map game, "
             "top-down bird's-eye view with a slight isometric tilt matching a storybook life-sim map, "
             "white-cream stone walls, one tall pointed bell tower with a small cross, arched stained-glass windows, "
             "warm wooden double doors with tiny front steps, soft rounded shapes, cute tiny detailed. "
             "Single building only, centered, whole building visible with margin. "
             "Plain solid pure bright green background color #00FF00 filling the entire frame (chroma key). "
             "No text, no letters, no watermark, no people, no shadow on the ground. ")
BLDGS = {
    "cathedral_night": BLDG_BASE + "Night version: deep dark charcoal-navy ambience, stained-glass windows glowing warmly from inside, a small lantern by the door.",
    "cathedral_day":   BLDG_BASE + "Warm late-afternoon version: bright pastel palette, soft golden light, gentle and peaceful.",
}

_USAGE = []


def gemini_image(prompt, aspect="1:1"):
    """yeta_map_bg.py gemini_image 동형(자립형 규약)."""
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
                _USAGE.append(int(um.get("totalTokenCount") or 0))
            for cand in j.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    inl = p.get("inlineData") or p.get("inline_data")
                    if inl and inl.get("data"):
                        return base64.b64decode(inl["data"])
            print("  ⚠️ 이미지 파트 없음", flush=True)
            return None
        except urllib.error.HTTPError as e:
            print("  ⚠️ HTTP {} — {}".format(e.code, e.read().decode()[:200]), flush=True)
            if e.code in (429, 500, 503) and attempt == 0:
                time.sleep(4); continue
            return None
        except Exception as e:
            print("  ⚠️ 호출 실패: {}".format(e), flush=True)
            if attempt == 0:
                time.sleep(4); continue
            return None
    return None


def chroma_cut(png_bytes, size=320):
    """그린스크린 제거 → 투명 PNG + bbox 트림 + 축소. Pillow 필요(러너 pip 설치) — 실패 시 None(fail-soft)."""
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
                if g > 120 and g > r * 1.6 and g > b * 1.6:      # 순수 초록 계열 = 배경
                    px[x, y] = (0, 0, 0, 0)
                elif g > 90 and g > r * 1.25 and g > b * 1.25:   # 가장자리 초록 번짐 = 반투명 완화(그린 스필 축소)
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
        print("  ⚠️ 크로마키 실패({}) — 원본 저장 폴백".format(e), flush=True)
        return png_bytes


def main():
    if not KEY:
        print("GEMINI_API_KEY 없음 — no-op 종료(게이트)")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    made = 0
    for cid, desc in CHARS.items():
        path = os.path.join(OUT_DIR, "char_{}.png".format(cid))
        if os.path.exists(path) and not FORCE:
            print("skip(존재): {}".format(path), flush=True)
            continue
        print("생성: {} …".format(cid), flush=True)
        png = gemini_image(BASE.format(desc=desc))
        if not png:
            print("  ⚠️ {} 실패 — 계속(fail-soft)".format(cid), flush=True)
            continue
        cut = chroma_cut(png)
        with open(path, "wb") as f:
            f.write(cut)
        made += 1
        print("  ✅ {} ({:.0f}KB)".format(path, len(cut) / 1024), flush=True)
    for bid, prompt in BLDGS.items():   # 건물 스프라이트(성당 등) — 캐릭터와 동일 멱등·크로마키 파이프 · 크기만 520(건물 디테일)
        path = os.path.join(OUT_DIR, "bld_{}.png".format(bid))
        if os.path.exists(path) and not FORCE:
            print("skip(존재): {}".format(path), flush=True)
            continue
        print("생성: {} …".format(bid), flush=True)
        png = gemini_image(prompt)
        if not png:
            print("  ⚠️ {} 실패 — 계속(fail-soft)".format(bid), flush=True)
            continue
        cut = chroma_cut(png, size=520)
        with open(path, "wb") as f:
            f.write(cut)
        made += 1
        print("  ✅ {} ({:.0f}KB)".format(path, len(cut) / 1024), flush=True)
    print("완료 — 신규 {}장 · Gemini 토큰 합 {}".format(made, sum(_USAGE)), flush=True)


if __name__ == "__main__":
    main()
