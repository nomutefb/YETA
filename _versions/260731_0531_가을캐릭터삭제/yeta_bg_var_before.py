#!/usr/bin/env python3
"""yeta_bg_var.py — 무음동 배경 배리에이션 생성(운영자 260707 "openai 프롬프팅해서 무음동 배경 — 날씨·분위기·시간대·편의점 등 다양하게").

수동 dispatch 전용(⚠️ OpenAI 유료 종량제 · 자동 트리거 금지 = 기존 이미지 파이프 규약).
OpenAI Images API(gpt-image) → `viewer/assets/yeta_bg/var_<slug>.png` 커밋(git 정본 — R2 불요·yeta_face git 폴백 결).
멱등: 이미 있는 slug는 skip(FORCE=1 재생성). 게이트 = OPENAI_API_KEY(없으면 no-op).
활용: 뷰어 무드/장면 배경 후보 — roster `bg` 교체나 씬 연출은 운영자 선택 후 별도 배선.
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY_nomute", "")
MODEL = (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2").strip()
API = "https://api.openai.com/v1/images/generations"
FORCE = os.environ.get("FORCE", "") == "1"
OUT = "viewer/assets/yeta_bg"

BASE = ("Moody atmospheric background art for a Korean urban-fantasy chat app, no people, no text or letters, "
        "a quiet back-alley neighborhood in Seoul called Mueum-dong where the night feels longer than the day; "
        "cinematic vertical 9:16 composition, painterly semi-realistic style, deep spotify-black shadows with a "
        "restrained neon lime (#CFFF40) accent glow and occasional cobalt hints, consistent with a dark glassmorphism app. Scene: ")

# 장소 × 시간대 × 날씨(운영자 축: 편의점·다양)
SCENES = [
    ("cvs_dawn",      "a small Korean convenience store glowing alone at 4am, wet asphalt after rain reflecting the signage, one lime-green neon strip, empty street, steam from a hot-food counter"),
    ("alley_rain",    "the alley entrance during a heavy summer night rain, umbrellas' silhouettes absent, rain streaks lit by a single lime signboard, puddles rippling"),
    ("tea_sunset",    "the 24-hour teahouse 'Mueum' window seat at golden sunset, warm amber light spilling onto the alley, steam rising from a teacup on the windowsill, cozy and quiet"),
    ("rooftop_mid",   "a rooftop view over Mueum-dong at exactly midnight, dense low rooftops, one distant radio tower with a blinking light, thin moon, the boundary hour feeling"),
    ("busstop_fog",   "an old bus stop in thick night fog, its lightbox the only light source, a faint lime hue in the fog, benches empty, streetlamp halos"),
    ("playground_3am","an empty neighborhood playground at 3am when the boundary grows thin, swings perfectly still, pale blue otherworldly glow seeping from beyond the fence"),
    ("radio_neon",    "the narrow lane outside the late-night radio booth 'Frequency', rain-slick pavement, warm booth light and cool neon reflections mixing, cables and antennas overhead"),
    ("snow_night",    "the alley under the first snow of winter at night, snowflakes catching the lime signage glow, footprints of a single cat, hushed and tender"),
    # ── 확장 24씬(운영자 260707 "3배 더 — 날씨·상황·분위기 + 사건사고") · 사건사고 = 핵심룰② "판타지는 낮게 샌다" 결(흔적과 여운·no people) ──
    ("dawn_mist",     "the alley at first-bus hour wrapped in low morning mist, pale grey-blue light, a single lit bus headlight glow far away, dew on shutters"),
    ("noon_summer",   "the same alley at blazing summer noon, hard black shadows, cicada-season haze, laundry lines, the rare daytime face of Mueum-dong"),
    ("typhoon_eve",   "the alley on the eve of a typhoon, shop windows taped with X patterns, low dark violet clouds racing, loose signage swinging"),
    ("heatnight",     "a tropical-night alley, an old electric fan left on a wooden bench, open windows with mosquito nets, heavy warm air, distant lime sign"),
    ("autumn_dusk",   "ginkgo leaves piled along the alley at dusk, deep amber and teal twilight, a broom leaning on a wall"),
    ("blackout",      "the alley during a power outage, every sign dead except one window lit by candlelight, deep blacks, faint starlight"),
    ("thunder_flash", "the split second of a lightning flash over the rooftops, violet-white light freezing the alley, rain suspended mid-air"),
    ("after_hail",    "the pavement right after a hailstorm, thousands of tiny ice beads glittering under a streetlamp like scattered glass"),
    ("laundromat",    "a 24-hour coin laundromat at 3am, one washing machine spinning alone, cool fluorescent interior against the dark street"),
    ("karaoke_back",  "the back exit of a coin-karaoke at dawn, stickers and posters layered on the door, one lime emergency light"),
    ("market_close",  "the traditional market lane at closing time, half-lowered shutters, crates stacked, last warm bulb swinging"),
    ("moon_stairs",   "the steep hillside stairway of Mueum-dong under a full moon, moonlight striping the steps, handrail shadows long"),
    ("crosswalk_rain","a rainy crosswalk at night, the signal's green light smeared across wet asphalt, no cars, long exposure feeling"),
    ("arcade_glow",   "an old arcade storefront at night, CRT glow leaking through the window, faded cabinet art, one flickering tube light"),
    ("stream_dawn",   "the small neighborhood stream at dawn, mist over the water, a heron's ripple already fading, first light on the railing"),
    ("underpass",     "a narrow pedestrian underpass lit by a single lime-green strip light, wet floor reflections, humming stillness"),
    ("police_line",   "the alley entrance sealed with yellow police tape at dawn, no onlookers, one officer's cone left behind, quiet unease"),
    ("broken_wall",   "a low brick wall freshly broken outward as if something large passed through, bricks scattered, dust still settling in the streetlight"),
    ("claw_shutter",  "a closed shop shutter bearing three long fresh gouge marks, metal curled at the edges, lime sign reflecting in the scratches"),
    ("dead_lamp",     "a shattered streetlamp with glass scattered in a circle below, the only dark spot in a row of lit lamps, faint blue shimmer above it"),
    ("firetruck_after","the alley just after fire trucks left, wet pavement, faint red afterglow on walls, a coiled hose mark, thin smoke"),
    ("bandage_bench", "an empty bench with a first-aid kit left open and a roll of bandages, under a flickering lamp, someone was patched up here minutes ago"),
    ("missing_flyer", "a utility pole layered with missing-person and missing-cat flyers fluttering in night wind, tape peeling, one flyer glowing oddly"),
    ("thin_boundary", "the dead end of the alley where the air itself ripples like heat haze at 3am, a faint cold blue glow seeping through, a single traffic cone as a warning"),
    # ── 페르소나 고유 무대(운영자 260707 "대화 시작 = 캐릭터 고유 이미지 · 없으면 하나씩 뽑아") — bg 중복 2인{하은=tea(무디와 공유)·가을=alley(백과 공유)} 전용 씬 ──
    ("persona_haeun",  "the tree-lined street in front of a small Korean neighborhood school at dusk just after the teachers left, one classroom window still warmly lit, ginkgo trees over the gate, a chalk-dusted tote bag resting on the low wall, playful yet tender after-work air"),
    ("persona_gaeul",  "the merchants' association office window above the market lane at night, a crisp warm desk lamp on stacked ledgers and a neighborhood map pinned with notes, the market banner fluttering outside, composed and quietly in charge"),
    # ── 나머지 8인 고유 대화-시작 배경(운영자 260707 "각각에 어울리는 고유 배경 하나씩 다 · 대화 시작하면 나올 수 있는거") — no people·시그니처 장소 + 카드 포인트색 저광 ──
    ("persona_mudi",   "the interior of a centuries-old 24-hour teahouse at deep night, no people, a worn wooden counter with a single cup releasing luminous jade-green steam curling into glowing wisps, rows of aged tea jars, warm amber paper lanterns, a timeless hush, faint mint-green glow"),
    ("persona_sera",   "the innermost underground dance-practice room at 4am, no people, a mirrored wall and a single heavy door faintly outlined in incandescent hot-pink light, a towel and water bottles on the floor, cool fluorescent haze with a pink awakened shimmer, a distant looming spire barely visible in a dark window"),
    ("persona_baek",   "the narrow boundary alley in the last dark hour before dawn, no people, faint protective runes dimly glowing on a wet brick wall, a sheathed blade leaning by a doorway, steel-blue mist, the quiet edge of the neighborhood where the night thins"),
    ("persona_ryu",    "the moonlit wooden veranda of a kendo dojo at night, no people, a sword rack and a folding fan left on the floor, bamboo swaying, a faint luminous silver-teal blade-glow lingering in the air, a full moon over the tiled roof"),
    ("persona_yun",    "a late-night radio booth at 2am, no people, a vintage microphone on a boom, a red ON-AIR sign glowing, translucent violet sound-waves and starlight rippling out the window across a distant boundary, headphones resting on the mixing desk"),
    ("persona_desk",   "a third-floor newsroom at deep night, no people, rows of dim monitors, a corkboard layered with pinned notes and clippings faintly lit, a cold coffee cup, cool-blue glow, faint luminous lines of hovering text — the keeper of the town's true records"),
    ("persona_kopi",   "a cozy corner nook of a teahouse at night, no people, an open laptop and a teacup under a warm desk lamp, a single glowing punch-line phrase drifting in the air as light-letters, warm-orange bokeh, scattered notebooks"),
    ("persona_von",    "a boxing gym at 5am, no people, a worn ring under a single hanging lamp, heavy punching bags, hand-wrap tape and a towel on a bench, cool blue pre-dawn light with faint drifting embers of strength"),
    # ── 홍석천 개편 배경 3장(운영자 260726 "게이 + 근육질 · 종종 동물로 변신해 대화 중 도망 · 배경도 3장 정도 더") ──
    # no people 규약 유지 = 변신·도주는 '흔적과 여운'으로만(핵심룰② "판타지는 낮게 샌다").
    ("mudi_backdoor",  "the back door of a centuries-old teahouse flung open onto a dark alley, no people, a stool knocked over and a still-spinning teacup on the floor, an apron slipped off its hook, wet animal pawprints leading away into the dark and fading, warm amber light spilling from inside into the cold night, faint mint-green glow"),
    ("mudi_kitchen",   "the back kitchen of an old teahouse at night, no people, a heavy cast-iron kettle over a low fire, split firewood stacked shoulder-high, a worn leather apron with rolled-up sleeves hanging on a nail, a whetstone and thick rope, steam and warm amber light, a quietly powerful working space, faint mint-green glow"),
    ("mudi_roofdawn",  "the tiled roof of a low teahouse at first light, no people, a single line of animal pawprints crossing the frost-damp tiles and disappearing over the ridge, the alley below still dark, pale blue dawn breaking behind the chimneys, faint mint-green shimmer in the air"),
]


def openai_image(prompt):
    payload = {"model": MODEL, "prompt": prompt, "size": "1024x1536", "n": 1}   # 세로 9:16 근사(모델 지원 세로 사이즈)
    req = urllib.request.Request(API, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
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
    except Exception as e:
        print(f"  ⚠️ 생성 실패: {e}", flush=True)
    return None


def webp(path):
    """뷰어 서빙용 webp 사본(768w·q82 — png ~2MB → ~90KB · 뷰어는 .webp만 참조). ffmpeg 없으면 조용히 생략(png 원본은 남음)."""
    if not shutil.which("ffmpeg"):
        return
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", "scale=768:-2",
                        "-quality", "82", path[:-4] + ".webp"], check=True, timeout=120)
    except Exception as e:
        print(f"  ⚠️ webp 변환 실패(비치명): {e}", flush=True)


def main():
    if not KEY:
        print("OPENAI_API_KEY 없음 — 배경 생성 생략(no-op)"); return 0
    os.makedirs(OUT, exist_ok=True)
    made = 0
    for slug, desc in SCENES:
        path = os.path.join(OUT, f"var_{slug}.png")
        if os.path.exists(path) and not FORCE:
            print(f"skip {slug}(기존)"); continue
        print(f"생성 {slug} …", flush=True)
        png = openai_image(BASE + desc)
        if not png:
            continue
        open(path, "wb").write(png)
        webp(path)
        made += 1
        print(f"  ✓ {path} ({len(png)//1024}KB)", flush=True)
        time.sleep(2)
    print(f"완료 — 신규 {made}장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
