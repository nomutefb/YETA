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

_WHERE = ("Moody atmospheric background art for a Korean urban-fantasy chat app, no people, no text or letters, "
          "a quiet back-alley neighborhood in Seoul called Mueum-dong where the night feels longer than the day; ")
_STYLE = ("painterly semi-realistic style, deep spotify-black shadows with a "
          "restrained neon lime (#CFFF40) accent glow and occasional cobalt hints, consistent with a dark glassmorphism app. ")
BASE = _WHERE + "cinematic vertical 9:16 composition, " + _STYLE + "Scene: "   # ⚠️ 기존 45씬 프롬프트와 **글자 단위 동일**(쪼갠 건 아래 시트가 톤 문구를 2벌로 베끼지 않게 하려는 것뿐 · FORCE 재생성 시에도 그림이 안 바뀐다)

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
    # ── 페르소나 고유 무대(운영자 260707 "대화 시작 = 캐릭터 고유 이미지 · 없으면 하나씩 뽑아") — bg 중복 1인{하은=tea(무디와 공유)} 전용 씬 ──
    ("persona_haeun",  "the tree-lined street in front of a small Korean neighborhood school at dusk just after the teachers left, one classroom window still warmly lit, ginkgo trees over the gate, a chalk-dusted tote bag resting on the low wall, playful yet tender after-work air"),
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


# ── 장소 씬 「한 도화지」(운영자 260811 "한 컷에 여러 분할로 소스 뽑아서 잘라서 넣어줘 · 프롬프트 1개로 1개 도화지 안에 여러 장소 컷") ──
#   왜 시트인가: 지도 12곳을 낱장으로 뽑으면 **호출 12회 = 12배 과금**인데다, 12장이 서로 다른 붓·다른 밤이 된다(장소를 옮겨다니면 동네가 아니라 딴 도시가 된다).
#   한 도화지에 12칸을 한 번에 그리면 팔레트·광원·붓이 한 벌로 묶인다 — 캐릭터 보드가 감정 20칸을 한 장에 뽑는 것과 **같은 처방**(운영자 260801·260803).
#   자르기 = `shared/cut_board_sheet.py` 그대로 계승(새 커터 0). 그 커터는 「종이색 거터」를 실측해 칸을 찾으므로,
#   프롬프트도 정본 시트 규약(`docs/캐릭터보드_프롬프트_정본.md` §2 SHEET LAYOUT)의 '따뜻한 오프화이트 종이 + 얇은 구분선 + 고른 거터'를 그대로 쓴다.
#   칸 순서(좌→우·위→아래)가 곧 아래 목록 순서 = 커터에 넘길 라벨 순서(그림 안에 글자를 넣지 않고도 어느 칸이 어디인지 확정된다).
SHEET = os.path.join(OUT, "_sheet_places.png")          # 시트 원본(자르기 베이스 · 뷰어 미참조 · 운영자 재단용으로 커밋)
SHEET_COLS, SHEET_ROWS = 2, 6                            # 2×6 = 12칸 · 각 칸 가로 약 2:1 = 뷰어 `.yin-bg`(폭 100% × 130px 띠)에 세로를 거의 안 버리고 들어간다
TRIM = 0.015                                             # 칸 가장자리 안쪽으로 깎는 비율 — 커터는 '종이가 아닌 구간'을 칸으로 보므로 얇은 구분선이 칸 테두리에 묻어 온다(어두운 씬 위 밝은 실선 = 눈에 띈다)

# 12칸 = 지도에서 탭되는 장소 전부(apps/yeta/places.json 의 공개 장소 · private/offlimits 제외). 묘사는 그 파일 `look` 필드(위치 SSOT)를 옮긴 것 — 지도 그림과 같은 동네가 되게.
PLACE_CUTS = [
    ("tea",       "the traditional teahouse 'Mueum' — a low tiled roof, a lantern glowing in every window, steam curling from the chimney, warm amber light spilling onto the dark lane"),
    ("alley",     "the small plaza crossroads that is the heart of the neighbourhood — one streetlamp, an empty bench, damp pavement, dark alley mouths running off in each direction"),
    ("store",     "the 24-hour convenience store, its lime-green neon sign burning all night, cold white interior light washing onto the pavement, stacked crates by the door"),
    ("market",    "the traditional market lane, rows of colourful canvas awnings over shuttered stalls, bare bulbs strung overhead, crates and folded tarpaulins"),
    ("park",      "the neighbourhood playground — swings, a slide and a sandpit under one tall lamp, the swings perfectly still"),
    ("school",    "the three-storey school seen from its yard — a running ground, a low reviewing platform and a flagpole, a single corridor window still lit"),
    ("dojo",      "the kendo dojo 'Wolgwang' inside its tiled-wall courtyard — a wooden veranda and polished floor, moonlight striping the boards, a sword rack in the shadow"),
    ("gym",       "the boxing gym 'Gangcheol' — a boxy building with a wide roller shutter half lowered, a painted boxing-glove signboard, one bare lamp over the door"),
    ("studio",    "the basement practice-room entrance — a neon arrow above a narrow stairwell going down, a handrail, light rising from below the steps"),
    ("office",    "the three-storey brick newsroom — a bare rooftop signboard frame against the sky, only the third-floor windows still warmly lit"),
    ("radio",     "the small radio station — a steel antenna mast on the roof with a red beacon blinking, a low block building, cables sagging down to the street"),
    ("cathedral", "the old cathedral on the north-east hill — weathered stone, a tall arched window faintly lit from within, a long stone stairway climbing to its doors under the moon"),
]


def sheet_prompt():
    """한 도화지 프롬프트 = 톤(_WHERE+_STYLE · 낱장 45씬과 같은 문구) + 정본 시트 규약 + 칸 목록. 문구 2벌 금지 = 톤은 위 상수를 그대로 쓴다."""
    panels = "\n".join(f"{i + 1}. {desc}" for i, (_, desc) in enumerate(PLACE_CUTS))
    return (
        f"A reference sheet of {len(PLACE_CUTS)} background paintings for one story. " + _WHERE + _STYLE +
        "\n\nSHEET LAYOUT\n"
        "- ONE page, portrait 2:3, on a warm off-white paper background.\n"
        f"- A clean {SHEET_COLS} columns x {SHEET_ROWS} rows grid of {len(PLACE_CUTS)} equal LANDSCAPE panels (each panel about 2:1 wide), "
        "thin hairline dividers, a small even gutter between panels, a generous outer margin.\n"
        "- Every panel is a wide establishing shot of a DIFFERENT place in the same neighbourhood, at night, with NO people.\n"
        "- Each panel is painted edge to edge inside its own frame (no inner border, no vignette, no white padding inside a panel).\n"
        "- NO text anywhere: no labels, no numbers, no captions, no signage lettering, no watermark, no signature.\n\n"
        "CONSISTENCY IS THE #1 REQUIREMENT\n"
        "All panels share ONE palette, ONE light logic, ONE brush and ONE weather — they are one night in one town, "
        "seen from twelve places. Only the place changes.\n\n"
        "PANELS (left to right, top to bottom)\n" + panels
    )


def cut_sheet():
    """시트를 칸으로 잘라 `var_place_<id>.png|webp` 로 부린다. 커터는 shared/cut_board_sheet.py 계승(격자 좌표를 지어내지 않는다 = 종이색 거터 실측)."""
    sys.path.insert(0, "shared")
    try:
        import cut_board_sheet as CBS
        from PIL import Image
    except Exception as e:
        print(f"::warning::자르기 생략 — Pillow/커터 로드 실패: {e}"); return 0
    im = Image.open(SHEET).convert("RGB")
    paper = CBS.paper_colour(im)
    cols, rows = CBS.bands(im, paper, 0), CBS.bands(im, paper, 1)
    print(f"시트 {im.size[0]}×{im.size[1]} · 종이색 {paper} · 열 {len(cols)} × 행 {len(rows)} = 칸 {len(cols) * len(rows)}", flush=True)
    if len(cols) * len(rows) != len(PLACE_CUTS):
        # 격자가 어긋난 채 자르면 **엉뚱한 장소 그림이 엉뚱한 장소에 박힌다**(찻집 자리에 체육관). 잘못 부리느니 시트만 남기고 멈춘다 — 운영자가 보고 재발사.
        print(f"::warning::격자 {len(cols)}×{len(rows)} ≠ {SHEET_COLS}×{SHEET_ROWS} — 칸/장소 대응이 깨졌다. 자르지 않고 시트만 커밋(재발사 or 수동 재단)."); return 0
    n = 0
    for r, (y0, y1) in enumerate(rows):
        for c, (x0, x1) in enumerate(cols):
            slug = PLACE_CUTS[n][0]; n += 1
            dx, dy = int((x1 - x0) * TRIM), int((y1 - y0) * TRIM)
            cell = im.crop((x0 + dx, y0 + dy, x1 - dx, y1 - dy))
            base = os.path.join(OUT, f"var_place_{slug}")
            cell.save(base + ".png")
            cell.save(base + ".webp", quality=82)   # 뷰어는 .webp만 참조 · 칸은 이미 작아 ffmpeg 768w 리스케일(=업스케일) 불요
            print(f"  {slug:<10} ({x0},{y0})-({x1},{y1}) → {cell.size[0]}×{cell.size[1]}", flush=True)
    return n


def openai_image(prompt, size="1024x1536"):
    payload = {"model": MODEL, "prompt": prompt, "size": size, "n": 1}   # 세로 9:16 근사(모델 지원 세로 사이즈)
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


def place_sheet():
    """장소 씬 12칸 = **호출 1회**. 이미 다 잘려 있으면 무과금 skip · 시트만 있고 칸이 없으면 자르기만(재발사 아님)."""
    have = all(os.path.exists(os.path.join(OUT, f"var_place_{s}.webp")) for s, _ in PLACE_CUTS)
    if have and not FORCE:
        print(f"skip 장소 시트(칸 {len(PLACE_CUTS)}개 기존)"); return 0
    if not os.path.exists(SHEET) or FORCE:
        if not KEY:
            print("OPENAI_API_KEY 없음 — 장소 시트 생략(no-op)"); return 0
        print(f"생성 장소 시트 {SHEET_COLS}×{SHEET_ROWS}={len(PLACE_CUTS)}칸 (호출 1회) …", flush=True)
        png = openai_image(sheet_prompt())
        if not png:
            print("::warning::장소 시트 생성 실패 — 칸 없음(뷰어는 씬 없는 종전 모습으로 정상 동작)"); return 0
        open(SHEET, "wb").write(png)
        print(f"  ✓ {SHEET} ({len(png) // 1024}KB)", flush=True)
    else:
        print("시트 기존 — 재생성 없이 자르기만(무과금)", flush=True)
    return cut_sheet()


def main():
    os.makedirs(OUT, exist_ok=True)
    cuts = place_sheet()   # 장소 씬(시트 1장 → 12칸) — 낱장 45씬보다 먼저(운영자가 이번에 요청한 축)
    if not KEY:
        print(f"OPENAI_API_KEY 없음 — 낱장 배경 생성 생략(no-op) · 장소 칸 {cuts}개"); return 0
    made = 0
    for slug, desc in SCENES:
        path = os.path.join(OUT, f"var_{slug}.png")
        if os.path.exists(path) and not FORCE:
            # ⚠️ 260812 평의회 — 종전엔 png 존재만 보고 건너뛰었다. 그런데 **뷰어는 .webp 만 참조**하므로
            #    png는 있고 webp가 없는 상태(260726 mudi 3씬 실측 · ffmpeg 미설치)가 영구 고착됐다 —
            #    돈 주고 뽑은 그림이 디스크에 있는데도 앱에서 안 보이고, 고치는 길은 FORCE=1(재과금)뿐이었다.
            #    이제 그 경우엔 **재생성 없이 변환만** 다시 한다(무과금 자가치유 · yeta_char_board.py 재수리 결 계승).
            if not os.path.exists(path[:-4] + ".webp"):
                print(f"repair {slug}(png만 있음 — 무과금 webp 재변환)", flush=True); webp(path)
            else:
                print(f"skip {slug}(기존)")
            continue
        print(f"생성 {slug} …", flush=True)
        png = openai_image(BASE + desc)
        if not png:
            continue
        open(path, "wb").write(png)
        webp(path)
        made += 1
        print(f"  ✓ {path} ({len(png)//1024}KB)", flush=True)
        time.sleep(2)
    print(f"완료 — 낱장 신규 {made}장 · 장소 칸 {cuts}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
