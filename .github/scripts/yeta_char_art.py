#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_char_art.py — 무음동 10인 판타지 캐릭터 초상(운영자 260707 "이거 기틀로 캐릭터 이미지 하나씩 뽑아줘 · 판타지컬하게 · 완성형 만들고 편집").

기존 얼굴 파이프(yeta_face.py = grounded 웹툰 프사)와 별개 축 = **판타지컬 반신 초상**(2:3 · 각 카드 판타지 서사 + roster 포인트색 아우라 반영).
수동 dispatch 전용(⚠️ OpenAI 유료 종량제 · 자동 트리거 금지 = 이미지 파이프 공통 규약).
OpenAI Images API(gpt-image) → `viewer/assets/yeta_char/<id>.png`(+webp 768w) 커밋 = git 정본(큰 그림 = 운영자 편집 베이스).
+ 작은 얼굴 자동화(운영자 260713 "완전 자동 ㄱㄱ"): 큰 그림 상단·가로중앙 정사각을 512² webp `av/<id>.webp`로 떼고 roster avatar 슬롯에 자동 주입.
  = 〔큰 그림 → 작은 얼굴 크롭 → roster 배선〕 한 dispatch로 hands-off. 큰 그림 편집 베이스 성격은 유지(원하면 운영자가 png 손보고 재크롭).
+ 얼빡 프사 축(운영자 260725 "프로필 영역이 작아서 가슴 위를 쓰면 실제로는 안 보인다 · 몸은 더더욱 필요 없다"):
  `YETA_AV_MODE=1` → 큰 초상은 건드리지 않고 **얼굴이 프레임을 꽉 채우는 1:1 극단 클로즈업**만 새로 뽑아
  `<id>_face.png`(1024² 편집 베이스) + `av/<id>.webp`(512²) + roster 배선. 크롭 축(avatar_crop)과 배타 — 이 모드에선 크롭 안 씀.
멱등: 이미 있는 id는 skip(FORCE=1 재생성 · 얼빡 모드 기준 = `<id>_face.png`). 게이트 = OPENAI_API_KEY(없으면 no-op).
"""
import base64, json, os, re, shutil, subprocess, sys, time, urllib.request

KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY_nomute", "")
MODEL = (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2").strip()
API = "https://api.openai.com/v1/images/generations"
FORCE = os.environ.get("FORCE", "") == "1"
ONLY = os.environ.get("YETA_CHAR_ONLY", "").strip()   # 특정 id 하나만(비용 절감 테스트)
AV_MODE = os.environ.get("YETA_AV_MODE", "") == "1"   # 얼빡 프사 전용 모드(운영자 260725) — 큰 초상 무시, av/<id>.webp만 새로 뽑는다
OUT = "viewer/assets/yeta_char"
AVDIR = os.path.join(OUT, "av")                       # 작은 얼굴(아바타) 512²
ROSTER = "apps/yeta/characters/roster.json"
AV_URL = "assets/yeta_char/av/%s.webp"                # 뷰어 상대경로(roster avatar 슬롯)

# 판타지 초상 공통 결 — 무음동 판타지 개편(각 카드 = 판타지·무협 주인공 서사) · 반신·아우라 허용(얼굴 파이프의 'not costume fantasy' 가드 해제).
BASE = ("Fantasy character portrait, polished Korean manhwa / webtoon key-art illustration, painterly semi-realistic, "
        "half-body (waist-up) hero shot, vertical 2:3 composition, one single original fictional character, "
        "very good-looking and striking with an elegant commanding presence, refined proportions, flawless skin, fully clothed and tasteful, "
        "set in Mueum-dong — a back-alley Seoul neighborhood where the night runs longer than the day and a low urban fantasy seeps in; "
        "cinematic rim light against deep spotify-black shadows, a restrained neon-lime and cobalt palette with the character's own aura color, "
        "delicate floating light particles and a dreamlike magical atmosphere, dynamic yet grounded, "
        "no text, no caption, no watermark, no logo, no border. Character — ")

# 얼빡 프사(운영자 260725 "프로필 영역이 작아서 가슴 위를 쓰면 실제로는 안 보인다 · 몸은 더더욱 필요 없다").
# 얼빡 = 얼굴이 여백 없이 화면을 빡빡하게 채우는 극단 클로즈업(K팝 얼빡직캠 어원) — 정본 견본 = 루시 lucy_face.webp.
# 스타일 어휘는 위 BASE 그대로 계승(붓결·아우라·입자 = 같은 축), 바뀐 건 프레이밍 하나뿐(새 결 창작 0).
AV_BASE = ("Extreme close-up face shot — the face fills the entire square frame edge to edge with no margin, "
           "cropped just above the eyebrows and just below the lower lip, no shoulders, no neck, no scenery, "
           "perfectly square 1:1, one single original fictional character, "
           "polished Korean manhwa / webtoon key-art illustration, painterly semi-realistic, glossy rendering with soft painterly shading, "
           "looking straight at the viewer, large expressive highly-detailed eyes, flawless luminous skin, "
           "shallow depth of field, cinematic rim light against deep spotify-black shadows, "
           "a restrained neon-lime and cobalt palette with the character's own aura color, delicate floating light particles, "
           "no text, no caption, no watermark, no logo, no border. Character — ")

# 10인 판타지 초상(카드 서사 각색 · 포인트색 아우라 = roster color) — grounded 인물도 '낮게 새는 판타지'로 승격
CHARS = [
    ("mudi",  "an ageless serene androgynous keeper of a centuries-old 24-hour teahouse, early-40s appearance but timeless eyes that have heard a thousand years of sorrows, a soft knowing half-smile, tidy linen apron over a fitted robe, holding a warm cup from which luminous jade-green steam curls into drifting glowing wisps; a mint-green (#7ee0a3) ethereal aura, warm amber lanterns behind."),
    ("sera",  "a fierce beautiful 19-year-old youngest 'awakener', chic aloof guarded expression with loneliness underneath, sleek high ponytail with one earphone in, faint incandescent power-lines glowing along one arm from climbing 'the Tower', a sporty crop-and-jacket practice outfit; a hot-pink (#ff8fb3) awakened aura crackling faintly, a vast shadowy spire looming in the deep background."),
    ("haeun", "an elegant playful 32-year-old literature teacher touched by quiet word-magic, a warm teasing smile, soft wavy shoulder-length hair, refined features, a stylish blouse with a chalk-dusted satchel, faint glowing hangul letters and golden ink drifting off an open book beside her like fireflies; a soft gold (#ffd36b) aura, dusk school-gate glow behind."),
    ("baek",  "an extremely handsome tall broad-shouldered 43-year-old warden — the last surviving hunter of the guild that turns back the 'night-things' from beyond the boundary, chiseled jaw, intense weary watchful eyes, a faint old scar on the arm, a sharp dark warding-coat with a sheathed blade, faint protective runes dimly lit; a steel-blue (#9db2bf) mist aura, pre-dawn alley shadow behind."),
    ("ryu",   "a charismatic handsome 45-year-old kendo master who was a legendary sword-saint of the martial world five centuries ago and woke here, light stubble, an alluring half-lidded lazy gaze that turns razor-sharp, dark hair loosely tied back, elegant traditional-modern attire, a folding fan in one hand and a faintly luminous spectral blade resting at his side; a silver-teal (#6bd6e8) moonlit aura, dojo veranda haze behind."),
    ("yun",   "a mellow handsome 34-year-old late-night radio DJ whose frequency reaches across the boundary to both the living and those who crossed over, soft introspective half-lit eyes, tousled hair, headphones around his neck, faint translucent sound-waves and starlight rippling out from a vintage mic like a spell; a soft-violet (#b8a7ff) aura, dim red ON-AIR booth glow behind."),
    ("desk",  "a distinguished strikingly handsome 48-year-old veteran editor-in-chief, keeper of the neighborhood's true records, sharp intelligent eyes behind thin steel-rimmed glasses, cool composed almost-unreadable expression, dark hair greying at the temples, faint stubble, crisp muted grey shirt sleeves rolled once, faint luminous lines of text and pinned notes hovering around him; a cool-blue (#8fb7ff) aura, late-night newsroom glow behind."),
    ("kopi",  "a charming handsome 34-year-old freelance copywriter and wordsmith, a witty half-smile that's half a mask, stylishly tousled hair, warm eyes quietly hungry for praise, a cozy oversized knit, a laptop and teacup, a single glowing punch-line phrase materializing in the air as drifting light-letters; a warm-orange (#ffb46b) aura, teahouse-corner lamplight bokeh behind."),
    ("gaeul", "a gorgeous commanding 33-year-old merchants'-association leader, the real power of the alley, a poised proud almost-regal gaze, glamorous polished look, sleek pulled-back dark hair, an impeccably tailored elegant coat, spine perfectly straight, a folder under one arm, faint threads of light radiating to the shopfronts she commands; an amethyst-violet (#c9a2ff) aura, market banner and neon reflection behind."),
    ("von",   "a powerfully athletic handsome 42-year-old former champion fighter turned boxing-gym master, short cropped hair, strong composed weathered features, a fit muscular build under a clean fitted jacket, a towel around the neck, hands wrapped, a faint ember-like strength aura rising from clenched fists; a warm-ember (#ff9d6b) aura, cool 5am gym light with drifting sparks behind."),
]


def webp(path):
    """뷰어 서빙용 webp 사본(768w·q82). ffmpeg 없으면 조용히 생략(png 원본 유지)."""
    if not shutil.which("ffmpeg"):
        return
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", "scale=768:-2",
                        "-quality", "82", path[:-4] + ".webp"], check=True, timeout=120)
    except Exception as e:
        print(f"  ⚠️ webp 변환 실패(비치명): {e}", flush=True)


def avatar_crop(png_path, cid):
    """큰 반신(1024×1536)에서 상단·가로중앙 정사각(iw/2)만 떼 512² webp = 작은 얼굴.
    프레이밍 = 운영자 수동 av/ 크롭 10인 역산·눈검증분(260713: crop 512²@x256,y0 ≈ 수동과 동일).
    해상도 무관식(iw/2·iw/4)이라 size 바뀌어도 안전. ffmpeg 없으면 None(주입 생략)."""
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — av 크롭 생략", flush=True); return None
    os.makedirs(AVDIR, exist_ok=True)
    out = os.path.join(AVDIR, f"{cid}.webp")
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", png_path,
                        "-vf", "crop=iw/2:iw/2:iw/4:0,scale=512:512", "-quality", "86", out],
                       check=True, timeout=120)
        return out
    except Exception as e:
        print(f"  ⚠️ av 크롭 실패(비치명): {e}", flush=True); return None


def set_avatar(text, pid, url):
    """roster.json — "id":"<pid>" 객체 블록 안 "avatar" 값 교체(멀티라인 pretty JSON 대응 · yeta_face.py 260712 픽스 계승).
    id 블록 = 그 "id" 매치부터 다음 "id" 전까지 → 그 안 avatar 1개만 치환(수제 포맷·타 캐릭터 불변)."""
    m = re.search(r'"id"\s*:\s*"%s"' % re.escape(pid), text)
    if not m:
        return text, False
    nxt = re.search(r'"id"\s*:\s*"', text[m.end():])
    end = m.end() + nxt.start() if nxt else len(text)
    seg, n = re.subn(r'"avatar"\s*:\s*"[^"]*"', '"avatar": "%s"' % url, text[m.end():end], count=1)
    if n == 0:
        return text, False
    return text[:m.end()] + seg + text[end:], True


def av_write(png_bytes, cid):
    """얼빡 원본(1024²) 저장 + 512² webp = av/<id>.webp(뷰어 아바타 규격 · 크롭 없이 그대로 축소).
    원본 png = 편집 베이스 관례 계승(같은 폴더 <id>_face.png · 새 디렉터리 0). ffmpeg 없으면 None(주입 생략 = avatar_crop 결)."""
    os.makedirs(AVDIR, exist_ok=True)
    src = os.path.join(OUT, f"{cid}_face.png")
    open(src, "wb").write(png_bytes)
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — av webp 변환 생략", flush=True); return None
    out = os.path.join(AVDIR, f"{cid}.webp")
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src,
                        "-vf", "scale=512:512", "-quality", "86", out], check=True, timeout=120)
        return out
    except Exception as e:
        print(f"  ⚠️ av webp 실패(비치명): {e}", flush=True); return None


def openai_image(prompt, size="1024x1536"):
    payload = {"model": MODEL, "prompt": prompt, "size": size, "n": 1}   # 기본 = 세로 2:3(반신 초상) · 얼빡 모드 = 1024x1024
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


def main():
    if not KEY:
        print("OPENAI_API_KEY 없음 — 캐릭터 초상 생성 생략(no-op)"); return 0
    os.makedirs(OUT, exist_ok=True)
    chars = [c for c in CHARS if not ONLY or c[0] == ONLY]
    made = 0
    wired = []                        # av 크롭까지 있는 id = roster 주입 대상
    for cid, desc in (chars if AV_MODE else []):   # 얼빡 축(운영자 260725) — 큰 초상은 손대지 않는다(편집 베이스 보존) · 아래 초상 루프와 배타
        av = os.path.join(AVDIR, f"{cid}.webp")
        src = os.path.join(OUT, f"{cid}_face.png")
        if os.path.exists(src) and not FORCE:
            print(f"skip {cid}(기존 얼빡)")
            if os.path.exists(av):
                wired.append(cid)     # 기존분도 roster 정합만 보장(값 동일=멱등)
            elif av_write(open(src, "rb").read(), cid):
                wired.append(cid)     # 원본은 있는데 webp만 없다(그 런에 ffmpeg 부재) = API 재호출 없이 변환·배선만 복구
            continue
        print(f"얼빡 {cid} …", flush=True)
        png = openai_image(AV_BASE + desc, size="1024x1024")
        if not png:
            continue
        if av_write(png, cid):
            wired.append(cid)
        made += 1
        print(f"  ✓ {av} ({len(png)//1024}KB 원본)", flush=True)
        time.sleep(2)
    for cid, desc in ([] if AV_MODE else chars):
        path = os.path.join(OUT, f"{cid}.png")
        if os.path.exists(path) and not FORCE:
            print(f"skip {cid}(기존)")
            if os.path.exists(os.path.join(AVDIR, f"{cid}.webp")):
                wired.append(cid)     # 기존분도 roster 정합만 보장(값 동일=멱등)
            continue
        print(f"생성 {cid} …", flush=True)
        png = openai_image(BASE + desc)
        if not png:
            continue
        open(path, "wb").write(png)
        webp(path)
        if avatar_crop(path, cid):
            wired.append(cid)
        made += 1
        print(f"  ✓ {path} ({len(png)//1024}KB)", flush=True)
        time.sleep(2)
    # roster 자동 주입 — 큰 그림=편집 베이스 유지, 작은 얼굴만 avatar 슬롯 배선(lucy/winter=CHARS 밖 = 불가침)
    if wired and os.path.exists(ROSTER):
        roster = open(ROSTER, encoding="utf-8").read()
        hits = 0
        for cid in wired:
            roster, ok = set_avatar(roster, cid, AV_URL % cid)
            if ok:
                hits += 1
            else:
                print(f"  ⚠️ roster 주입 실패 {cid}(avatar 키 없음?)", flush=True)
        open(ROSTER, "w", encoding="utf-8").write(roster)
        print(f"roster avatar 주입 — {hits}/{len(wired)}")
    print(f"완료 — 신규 {made}장 · 배선 {len(wired)}인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
