# yeta 무음동 지도 배경 생성 — 수동 dispatch 전용(⚠️ Gemini 유료 = 자동 트리거 금지 · 이미지 파이프 공통 규약 · 260707)
# 산출 = viewer/assets/yeta_map/map_night.png · map_day.png (git 정본 커밋 — bg-var 결).
# 배치 정본 = apps/yeta/places.json(분신술 10인 수렴 좌표) — 프롬프트의 방위 서술이 그 좌표를 따름.
#   이미지는 지형·건물 "분위기"용이고 노드·핀·라벨은 지도 UI의 SVG 오버레이가 정본 좌표로 찍는다(글자 생성 금지).
# 멱등: 이미 있으면 skip · FORCE=1 재생성. 게이트 = GEMINI_API_KEY(없으면 no-op 종료).
import base64
import json
import os
import time
import urllib.error
import urllib.request

KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = "gemini-3.1-flash-image-preview"   # yeta_bg.py와 동일 모델 · 실제 ID 바뀌면 함께 교체
API = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(MODEL)
OUT_DIR = "viewer/assets/yeta_map"
FORCE = os.environ.get("FORCE", "").strip() == "1"
ONLY = os.environ.get("ONLY", "").strip()          # 'map_day' 등 — 지정 시 그 변형만 생성(다른 톤 보존 · 운영자 260716 낮 재생성)
REF_NIGHT = os.environ.get("REF_NIGHT", "").strip() == "1"   # 1 = 밤 그림을 참조 이미지로 동봉 — "같은 도시의 낮" 강제(낮밤 도로·건물 1:1 정합 · 운영자 260716 한 수)
REF_SELF = os.environ.get("REF_SELF", "").strip() == "1"     # 1 = 자기 자신(기존 같은 톤 그림)을 참조로 동봉 — 배치 유지 + LAYOUT 신규 요소(성당 등)만 추가(운영자 260717 "기존 이미지 보고 다시 뽑아")

# 동네 골격(places.json 좌표·look 특색의 언어화 · 골목 50,50 중심 — places.json look 필드와 수동 동기)
# v2(운영자 260707 "산 아님 — 중소도시·힙한 도시") · v3(운영자 260707 "상가 밀집 전경 · 출입금지 지대 · 건물마다 특색 · 도로에 차").
LAYOUT = (
    "Neighborhood layout (top of image = north): "
    "at the very center, a small crossroads plaza with street lamps and benches (the Alley - the neighborhood hotspot). "
    "Just southwest of the plaza, a small warm traditional tea house with low tiled roof, lantern-lit windows and a steaming chimney, tucked between modern shops. "
    "Northeast of the plaza, a narrow 3-story brick editorial office building with an empty signboard frame on its rooftop, only the top floor lit. "
    "Further north on a low rise, a small radio station with a tall steel antenna tower and a blinking red light. "
    "East of the plaza, a stairway entrance going down to a basement practice studio, marked by a small neon arrow. "
    "South zone (daily-life belt): a 24h convenience store with a lime-green neon sign, "
    "a little playground with swings and a slide, "
    "a traditional swordsmanship dojo with tiled roof, wooden porch and walled courtyard squeezed between buildings to the southwest, "
    "a lively open-air market street with rows of colorful awning stalls, and a boxy gym building with a boxing-glove sign. "
    "DENSE shopping streets: rows of small shops packed side by side with layered signboards, cafes, snack bars, "
    "multi-family houses with rooftop terraces and water tanks filling every block. "
    "Northeast near the stream, one fenced-off abandoned construction zone with barricades and yellow-black warning tape, unnaturally dark inside. "
    "A narrow urban stream crosses the corner with a small footbridge. "
    "On the northeast riverbank clearing right beside the footbridge, a small sacred cathedral: white-cream stone walls, "
    "one tall pointed bell tower with a tiny cross, arched stained-glass windows, warm wooden double doors facing southwest with a small forecourt. "
    "The neighborhood edges show more city: bigger buildings, distant mid-rise skyline blocks, street trees - NOT forest, NOT mountains. "
    "Clear paved roads with lane markings and crosswalks connect everything through the central plaza; a few tiny parked cars along the curbs."
)
STYLE = (
    "Cozy hand-drawn cartoon city-neighborhood map, top-down bird's-eye view with a slight isometric tilt, "
    "a trendy hip small-city district (like a cool urban neighborhood), cute tiny detailed buildings, "
    "storybook mobile life-sim game style, soft rounded shapes, clean composition, "
    "square 1:1 full-bleed map. Absolutely no text, no letters, no labels, no UI, no watermark, no characters or people."
)
VARIANTS = {
    "map_night": ("Night scene: deep dark charcoal-navy ambience, quiet late-night city mood, "
                  "warm lamplight pools, glowing windows, neon signs with lime-green accent glow on shopfronts, "
                  "distant city lights at the edges. Dark enough to sit behind a dark-themed app UI. "),
    "map_day":   ("Warm late-afternoon scene: bright pastel palette, soft golden light, gentle shadows, "
                  "lively hip-neighborhood vibe, inviting and peaceful. "),
}

_USAGE = []


def gemini_image(prompt, aspect="1:1", ref_png=None):
    """Gemini 이미지 1장 → PNG bytes(실패 None · fail-soft). ref_png = 참조 이미지 bytes(구도 고정용 · 선택)."""
    parts = []
    if ref_png:
        parts.append({"inlineData": {"mimeType": "image/png", "data": base64.b64encode(ref_png).decode()}})
    parts.append({"text": prompt})
    payload = {
        "contents": [{"parts": parts}],
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
            print("  ⚠️ 이미지 파트 없음(inlineData 부재)", flush=True)
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


def main():
    if not KEY:
        print("GEMINI_API_KEY 없음 — no-op 종료(게이트)")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    made = 0
    for name, mood in VARIANTS.items():
        if ONLY and name != ONLY:
            print("skip(ONLY={}): {}".format(ONLY, name), flush=True)
            continue
        path = os.path.join(OUT_DIR, name + ".png")
        if os.path.exists(path) and not FORCE:
            print("skip(존재): {}".format(path), flush=True)
            continue
        ref, refmode = None, ""
        if REF_SELF:   # 자기 참조 — 배치 그대로 + LAYOUT 추가 요소만 반영
            sp = os.path.join(OUT_DIR, name + ".png")
            if os.path.exists(sp):
                ref = open(sp, "rb").read(); refmode = "self"
        if ref is None and REF_NIGHT and name != "map_night":   # 밤 정본을 구도 참조로 — 도로·건물 배치 1:1(재실측 자산 낮밤 공유 가능)
            np_ = os.path.join(OUT_DIR, "map_night.png")
            if os.path.exists(np_):
                ref = open(np_, "rb").read(); refmode = "night"
        prompt = ((("Redraw this exact same city map with the IDENTICAL layout - every building, road, "
                    "crosswalk, stream and bridge in the exact same position and shape - keeping the same "
                    "time of day and lighting - only ADD the newly described elements that are missing. ") if refmode == "self" else
                   ("Redraw this exact same city map with the IDENTICAL layout - every building, road, "
                    "crosswalk, stream and bridge in the exact same position and shape - only change the "
                    "time of day and lighting. ")) if ref else "") + mood + STYLE + " " + LAYOUT
        print("생성: {}{} …".format(name, " (밤 참조)" if ref else ""), flush=True)
        png = gemini_image(prompt, ref_png=ref)
        if not png:
            print("  ⚠️ {} 생성 실패 — 계속(fail-soft)".format(name), flush=True)
            continue
        with open(path, "wb") as f:
            f.write(png)
        made += 1
        print("  ✅ {} ({:.0f}KB)".format(path, len(png) / 1024), flush=True)
    print("완료 — 신규 {}장 · Gemini 토큰 합 {}".format(made, sum(_USAGE)), flush=True)


if __name__ == "__main__":
    main()
