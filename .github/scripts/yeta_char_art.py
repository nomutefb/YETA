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
  `<id>_face.png`(1024² 편집 베이스) + `av/<id>.webp`(512² · **확대 크롭 0.72**) + roster 배선. 상단 정사각 크롭(avatar_crop) 축과 배타.
  `YETA_AV_REBUILD=1` = 생성 없이 기존 원본에서 크롭만 다시(무과금 · 배율 노브 `YETA_AV_ZOOM`·`YETA_AV_YBIAS`).
멱등: 이미 있는 id는 skip(FORCE=1 재생성 · 얼빡 모드 기준 = `<id>_face.png`). 게이트 = OPENAI_API_KEY(없으면 no-op).
"""
import base64, json, os, re, shutil, subprocess, sys, time, urllib.request

KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY_nomute", "")
MODEL = (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2").strip()
API = "https://api.openai.com/v1/images/generations"
FORCE = os.environ.get("FORCE", "") == "1"
ONLY = os.environ.get("YETA_CHAR_ONLY", "").strip()   # 특정 id 하나만(비용 절감 테스트)
AV_MODE = os.environ.get("YETA_AV_MODE", "") == "1"   # 얼빡 프사 전용 모드(운영자 260725) — 큰 초상 무시, av/<id>.webp만 새로 뽑는다
AV_REBUILD = os.environ.get("YETA_AV_REBUILD", "") == "1"   # 이미 뽑아둔 <id>_face.png에서 크롭만 다시(생성 0 = 무과금 · 배율 조정용)
AV_ZOOM = (os.environ.get("YETA_AV_ZOOM") or "0.72").strip()   # 얼빡 확대 배율(실측 확정 0.72 · 아래 av_write 주석)
# ⚠ 260726 실측(홍석천 4테이크): 0.72는 **260725 출력 기준**으로 잰 값이다. 프롬프트가 바뀌어 원본부터 여백 없이 꽉 찬 얼빡으로
#   나오는 계열은 여기서 더 자르면 **입·턱이 잘린다**(4테이크 전부 재현). 그런 경우 dispatch에 zoom=1.0을 넘겨 크롭을 끄고,
#   0.72는 여백이 남는 옛 계열에만 쓴다. 판정법 = 생성 직후 <id>_face.png를 그냥 봐라(여백 있으면 0.72 · 없으면 1.0).
AV_YBIAS = (os.environ.get("YETA_AV_YBIAS") or "0.04").strip()  # 크롭 창 y 편향(위로)
try:
    AV_TAKES = max(1, min(6, int(os.environ.get("YETA_AV_TAKES") or "1")))   # 한 인물 얼빡 N장(운영자 260726 "지피티로 한 4장") — 2장째부터는 av/<id>_v2.webp… 로 빠지고 roster 주입 안 함(고르는 건 운영자)
except ValueError:
    AV_TAKES = 1
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
# 얼빡 = 얼굴이 여백 없이 화면을 빡빡하게 채우는 극단 클로즈업(K팝 얼빡직캠 어원) — **정본 견본 = 루시 lucy_face.webp**(운영자가 "저런식으로"로 지목).
# ⚠ run#1 반성: 스타일 어휘를 위 BASE(판타지 반신 초상)에서 통째로 계승했더니 결이 어긋났다 —
#   반실사 글로시 + 번개·아우라·입자 범벅에 마이크·손·어깨까지 들어가 얼빡도 아니었다(운영자 "루시 얼빡 말고는 다시 만들어야 된다").
#   그래서 계승 대상을 **BASE가 아니라 견본 프사(lucy_face.webp) 실물**로 바꿔 적는다 = 납작한 애니 셀 · 파스텔 · FX 0 · 얼굴만.
AV_BASE = ("Extreme close-up face shot — the face fills the entire square frame edge to edge with no margin, "
           "cropped through the top of the head just above the eyebrows and cut just below the lower lip, "
           "NO shoulders, NO neck, NO hands, NO props or instruments, NO scenery or objects in frame — face only, "
           "perfectly square 1:1, one single original fictional character, "
           "clean flat anime illustration with crisp dark line art and soft cel shading — like a modern anime key visual, "
           "NOT semi-realistic, NOT photoreal, NOT glossy painterly rendering, NO sweaty skin, "
           "matte pastel colour palette, soft airbrushed blush across the cheeks and nose, "
           "large detailed eyes with clean eyeliner accents, calm even lighting, "
           "plain softly blurred background in one quiet tone (a faint hint of the character's own aura colour), "
           "NO lightning, NO sparks, NO glowing particles, NO magic effects, NO neon streaks, NO heavy rim light, "
           "keep the described gender and apparent age exactly — the crop hides hair length and clothing, so read the description, not the framing, "   # 260725 run#1 실측: 세라(19세 여성)가 남성 얼굴로 나왔다 — 얼빡 크롭이 성별·나이 단서(포니테일·의상)를 지워 프롬프트 표류
           "no text, no caption, no watermark, no logo, no border. Character — ")

# 10인 판타지 초상(카드 서사 각색 · 포인트색 아우라 = roster color) — grounded 인물도 '낮게 새는 판타지'로 승격
CHARS = [
    # 260726 운영자 개편("게이 + 근육질 컨셉 · 종종 동물로 변신해 대화 중 도망 · 얼굴에 임팩트 있고 선이 강하게") —
    # 종전 androgynous/serene 어휘가 얼굴을 물렁하게 만들어 10인 중 개성이 제일 옅었다. 남성 명사 + 각진 골격 + 굵은 선으로 교체.
    ("mudi",  "a striking masculine gay man in his early 40s who keeps a centuries-old 24-hour teahouse — a broad-shouldered heavily muscled build with a thick corded neck and visible collarbones, a hard angular jawline and high sharp cheekbones, a strong straight nose, one arched brow, a knowing lopsided half-smile with a slight fang, deep-set timeless eyes that have heard a thousand years of sorrows; bold heavy confident line art with strong dark linework and high-contrast shading — a face with impact, not a soft one; close-cropped dark hair, a small hoop earring, a linen apron strap over a bare muscular shoulder; a faint animal cast to the pupils (he does not stay human when he is startled); a mint-green (#7ee0a3) ethereal aura, warm amber lanterns behind."),
    ("sera",  "a fierce beautiful 19-year-old girl, the youngest 'awakener' — unmistakably a teenage young woman with soft feminine features, chic aloof guarded expression with loneliness underneath, sleek high ponytail with one earphone in, faint incandescent power-lines glowing along one arm from climbing 'the Tower', a sporty crop-and-jacket practice outfit; a hot-pink (#ff8fb3) awakened aura crackling faintly, a vast shadowy spire looming in the deep background."),
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
    """얼빡 원본(1024²) 저장 + **확대 크롭** 512² webp = av/<id>.webp(뷰어 아바타 규격).
    원본 png = 편집 베이스 관례 계승(같은 폴더 <id>_face.png · 새 디렉터리 0). ffmpeg 없으면 None(주입 생략 = avatar_crop 결).
    png_bytes=None = 기존 원본에서 크롭만 다시(재생성 0 · 무과금)."""
    os.makedirs(AVDIR, exist_ok=True)
    src = os.path.join(OUT, f"{cid}_face.png")
    if png_bytes is not None:
        open(src, "wb").write(png_bytes)
    if not os.path.exists(src):
        return None
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — av webp 변환 생략", flush=True); return None
    out = os.path.join(AVDIR, f"{cid}.webp")
    try:
        # 확대 크롭(운영자 260725 "얼빡이야 얼빡") — 생성 이미지가 프롬프트만으론 정수리~턱 다 들어간 헤드샷으로 나와
        # 32px 원에서 얼굴이 작았다. 배율 실측(0.82/0.72/0.64 × 10인 렌더 대조) = **0.72**가 견본(lucy_face) 프레이밍과 일치
        # (0.82 = 여백 잔존 · 0.64 = 입·턱 절단 다발). y −4% = 얼굴이 화면 중앙보다 살짝 위에 앉는 초상 관례.
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", src,
                        "-vf", f"crop=iw*{AV_ZOOM}:iw*{AV_ZOOM}:(iw-iw*{AV_ZOOM})/2:(ih-iw*{AV_ZOOM})/2-ih*{AV_YBIAS},scale=512:512",
                        "-quality", "86", out], check=True, timeout=120)
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
        if AV_REBUILD:   # 크롭만 다시(생성 0 · 무과금) — 배율 조정·ffmpeg 부재 런 복구용
            if av_write(None, cid):
                wired.append(cid); made += 1; print(f"  ✓ 재크롭 {av}", flush=True)
            else:
                print(f"  ⚠️ {cid} 원본 없음 — 재크롭 생략", flush=True)
            continue
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
        for n in range(2, AV_TAKES + 1):   # 여벌 테이크(운영자 260726 "한 4장") — 같은 프롬프트 재추첨분은 <id>_v2… 로만 떨어뜨리고 roster는 안 건드린다(픽 = 운영자)
            print(f"얼빡 {cid} 테이크 {n} …", flush=True)
            png2 = openai_image(AV_BASE + desc, size="1024x1024")
            if not png2:
                continue
            if av_write(png2, f"{cid}_v{n}"):
                made += 1
                print(f"  ✓ {AVDIR}/{cid}_v{n}.webp (여벌 · roster 미주입)", flush=True)
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
            # ⚠ 여벌 픽 보호(260726 실측): 운영자가 테이크 중 하나(av/<id>_v4.webp)를 골라 배선해둔 상태에서
            #   같은 인물을 재생성하면 여기서 기본 경로(av/<id>.webp)로 **말없이 되돌아간다**(홍석천 = v4 픽 → v1 회귀).
            #   yeta_face.py의 av_owned 가드와 같은 결 — 이미 여벌을 가리키고 있으면 건드리지 않는다.
            if re.search(r'"id"\s*:\s*"%s".*?"avatar"\s*:\s*"assets/yeta_char/av/%s_v\d+\.webp"'
                         % (re.escape(cid), re.escape(cid)), roster, re.S):
                print(f"  ↷ {cid}: roster가 여벌 테이크를 가리키는 중 — 주입 생략(운영자 픽 보호)", flush=True)
                hits += 1
                continue
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
