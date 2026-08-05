#!/usr/bin/env python3
"""시즌 감정 미디어 manifest 생성기 — viewer/characters/season/<id>/media.json 재생성 (260717 Q.25 · Q.29 8감정 확장)

운영 흐름(운영자 260717 "수집은 많이 해줄 수 있는데 감정 명시가 비효율" → "다채롭게 나눠봐"):
  사진을 모드 폴더의 **감정 하위폴더**(android/joy/ · dokkaebi/tense/ 등)에 아무 이름으로 던져넣고
  이 스크립트를 돌리면 끝. 하위폴더 없이 모드 루트에 부으면 그 모드의 기본 버킷으로 흡수(미분류 안전망).

규약:
  · 감정 버킷 = EMOS 9종(base/warm/joy/love/shy/blue/tense/mad/sulky) — viewer Y_MOODS·러너 <<MOOD>> 화이트리스트와 짝(불변 계약)
    ⚠ sulky(삐짐) = 260726 운영자 「삐짐은 mad도 shy도 아니다」로 mad에서 독립. 구분선 = mad는 화가 밖으로 나가는 쪽
      (angry/furious/annoyed + **익살스러운 화남** = 신나게 총 쏘는 도발·이빨 드러낸 웃음 · 운영자 260726 "진짜 화난 게 아니라
      익살스러운 화남이 그거인 거야 화남이 맞음"), sulky는 상대에게 **서운해서** 안으로 토라진 것(sulky/pouty/offended/grumpy/
      cold_shoulder/귀엽게 째려봄) — 풀어주면 풀리는 쪽. ⚠ 호전적 도발을 tense(긴장·서늘)로 보내지 마라 — 260726에 5장이
      거기 묶여 있었다(dokkaebi 02·08·18·41 · android 15). tense = 표정 없는 서늘·압박이고, 웃으며 쏘는 건 mad다.
  · mode_dir = 변신 모드 전용 폴더명 — viewer yStage 모드 게이트(yModeOn)가 경로(/dokkaebi/)로 필터(하위폴더 깊이 무관)
  · 클립(mp4/webm · 캐릭터 루트) = base 선두(대화 시작 배경 계약)
  · 산출물 media.json = 기계 산출물(CLAUDE.md [0] ⚙ · check_refs 하드 게이트) — 손편집 금지, 값 변경 = 이 스크립트 수정.

사용: python3 shared/build_season_media.py            # 전 시즌 캐릭터 재생성
      python3 shared/build_season_media.py --check    # 재생성 없이 드리프트 검사(rc=1)
"""
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON_DIR = ROOT / "viewer" / "characters" / "season"
IMG_EXT = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".avif"}   # .jfif(260726) = 브라우저 저장 JPEG 변종 — 운영자 업로드에 그대로 섞여 들어온다. ⚠ 서빙 MIME이 호스트에 따라 octet-stream이 될 수 있어 **가능하면 .jpg로 개명해 두는 게 안전**(바이트 동일 = 무손실). 여기 등재는 누락 방지용 안전망.
CLIP_EXT = {".mp4", ".webm"}
# ⚠ 260726: 종전엔 감정 폴더에서 IMG_EXT만 읽어 **감정 폴더에 넣은 영상이 통째로 무시**됐다(운영자 "고죠 기분좋을때 나오는 영상").
#   클립은 캐릭터 루트(=base 선두)에만 놓을 수 있었던 셈 — 감정 지정이 불가능했다. IMG_EXT|CLIP_EXT로 확장해
#   **아무 감정 버킷에나 영상을 넣을 수 있게** 한다(뷰어 yStage는 이미 확장자로 클립을 판별하므로 무수정).
MEDIA_EXT = IMG_EXT | CLIP_EXT
EMOS = ["base", "warm", "joy", "love", "shy", "blue", "tense", "mad", "sulky"]  # viewer Y_MOODS(+base)·러너 화이트리스트와 짝 · sulky = 뒤에 추가(기존 버킷 순서 불변 = manifest diff 최소)

# ── 얼빡(프사) 배경 차단 — 운영자 260726 「얼빡은 배경에 깔지마」 ────────────────────────
# 왜 필요한가: 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘린다.
#   두 번 샜다 — ① 5인 `_face01`(파일명으로 잡음) ② 세라 `sera_k01`(이름이 평범해 그물 통과).
# 판별 축 2개(운영자 260726 "프로필사진은 내가 프로필 사진이라고 따로 명명해서 줄건데,
#   사실 정확히 구분하긴 어렵고 내가 명명해서 줄거임"):
#   ① **파일명 = 정본**(하드) — 운영자가 명명한다. 아래 패턴이면 배경 풀에서 자동 제외.
#   ② 종횡비 = **보조 경고**(자동 제외 안 함) — 정사각이어도 전신 풍경이면 배경으로 멀쩡하다
#      (실측: gojo_n09 736×736 헬스장 전신 · dokkaebi_11 1600×1600 여백 큰 일러스트).
#      기계가 못 가리므로 **사람이 보라고 띄우기만** 한다. 차단은 check_refs 게이트가 baseline으로.
FACE_PAT = re.compile(r"프로필|프사|profile|face", re.I)
FACE_RATIO = 0.85   # w/h > 이 값 = 정사각~가로형 = 세로 무대 부적합 의심(경고선)


def is_face(p: Path) -> bool:
    """운영자가 명명한 프사인가 — 파일명 하나로 판정(정본 축)."""
    return bool(FACE_PAT.search(p.stem))


def img_size(p: Path):
    """이미지 헤더만 읽어 (w, h). 실패·미지원이면 None (외부 의존 0 = 게이트가 환경 타지 않게)."""
    try:
        with p.open("rb") as f:
            head = f.read(32)
            if head[:2] == b"\xff\xd8":                      # JPEG(.jpg/.jpeg/.jfif)
                f.seek(2)
                while True:
                    b = f.read(1)
                    if not b:
                        return None
                    if b != b"\xff":
                        continue
                    m = f.read(1)
                    while m == b"\xff":
                        m = f.read(1)
                    if not m:
                        return None
                    if m[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                        f.read(3)
                        h, w = struct.unpack(">HH", f.read(4))
                        return w, h
                    ln = struct.unpack(">H", f.read(2))[0]
                    f.read(ln - 2)
            if head[:8] == b"\x89PNG\r\n\x1a\n":             # PNG
                return struct.unpack(">II", head[16:24])
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP":  # WebP 3변종
                f.seek(0)
                d = f.read(40)
                tag = d[12:16]
                if tag == b"VP8X":
                    return int.from_bytes(d[24:27], "little") + 1, int.from_bytes(d[27:30], "little") + 1
                if tag == b"VP8 ":
                    return int.from_bytes(d[26:28], "little") & 0x3FFF, int.from_bytes(d[28:30], "little") & 0x3FFF
                if tag == b"VP8L":
                    bits = int.from_bytes(d[21:25], "little")
                    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    except Exception:
        return None
    return None

# ── 평면(flat) 축 파일명 규칙 — 아이돌 등급 `characters/idol/<id>/` 계보(윈터 260726 · 최산 260730) ──────────
# ⚠⚠ 캐릭터마다 **자기 표**를 갖는다(운영자 260730 「여튼 윈터랑 최산은 절대 겹치면안됨」 → 「규칙표도 분리」).
#   종전 잠깐 IDOL_FLAT_RULES 하나를 둘이 참조했는데(같은 날 오전), 운영자 지시로 되돌렸다 —
#   두 실존 아이돌이 어떤 축에서도 공유물을 갖지 않게 한다. 대가 = 표 2벌 = 한쪽만 고쳐지는 드리프트 여지
#   (그래서 아래 두 표는 **같은 순서·같은 뜻**을 유지하고, 한쪽을 고치면 다른 쪽도 볼 것 —
#    합치는 건 금지 = 운영자 지시).
# ⚠ 위에서부터 첫 일치 승 — 좁은 토큰을 먼저.
#   (예: glaring_cut → sulky 가 glaring → mad 보다 위 · faux_furious → sulky 가 furious → mad 보다 위 · playful_cute → shy 가 playful → joy 보다 위)
WINTER_FLAT_RULES = [
    ("shy",   ["tsundere", "hesitant_to_speak", "flustered", "giggle_bashfully", "act_cute", "play_cute", "playful_cute"]),
    ("love",  ["seduce", "flirty", "love_u", "how_do_i_look", "miss_someone", "fond_look"]),
    # bored/listless(260729 운영자 「soso · 따분 · 심심 이런느낌으로 기존에 있는거에」) = 각성 낮은 무기력 결로 blue 편입.
    #   새 버킷을 안 만든 이유 = EMOS 9종은 러너 <<MOOD>> 화이트리스트와 짝인 불변 계약(신설 = 양쪽 동시 개정).
    ("blue",  ["sob", "crying", "heartbroken", "worried", "brooding", "sleepy", "asleep", "dozing", "heavy_eyes", "gotosleep", "go_sleep", "helpless", "at_a_loss", "let_down", "overwhelmed", "sad", "bored", "listless"]),
    # 삐짐(260726 독립) — 서운해서 토라진 결. mad보다 **위**여야 좁은 토큰이 먼저 잡힌다.
    #   glaring_cut* = "귀엽게 째려봄" = 삐짐 표정 그 자체(종전 shy에 있었으나 볼 붉힘 축과 다르다 · tsundere만 shy 잔류)
    #   faux_furious·feigning_mad·low_key_mad = 화난 '척'·은근한 화 = 대놓고 화난 mad와 반대쪽 결
    ("sulky", ["sulky", "pouty", "offend", "grumpy", "upset", "low_key_mad", "feigning_mad", "faux_furious", "cold_shoulder", "curt", "glaring_cut", "glaring_cuty"]),
    ("mad",   ["angry", "furious", "annoy", "irritat", "disgusting", "glaring"]),
    ("tense", ["suspicious", "taken_aback", "confused", "clueless", "dumbfounded", "panick", "freaking", "is_this_happening", "no_way", "for_real", "oh_really", "are_u_kidding", "what_now", "speechless", "so_cold", "poker_face", "fake_smile", "i_told_you_so", "smirk", "distracted"]),
    ("joy",   ["happy", "excited", "eureka", "goofy", "proud", "full_of_oneself", "playful", "hopeful"]),
    ("warm",  ["smile", "chuckle", "cheerup", "hi_", "its_you", "love"]),
    # 나머지(무대·연습·일상·배경·모델컷 등) = base 폴백
]

# 최산 전용 표(260730) — 윈터 표와 **별개 객체**. 같은 뜻·같은 순서를 쓰되 공유하지 않는다(운영자 「절대 겹치면안됨」).
#   최산 파일은 전부 `san_` 접두라 토큰은 접두 뒤 단어로 잡힌다(부분일치 = 접두 무해 · 실측).
SAN_FLAT_RULES = [
    ("shy",   ["tsundere", "hesitant_to_speak", "flustered", "giggle_bashfully", "act_cute", "play_cute", "playful_cute"]),
    ("love",  ["seduce", "flirty", "love_u", "how_do_i_look", "miss_someone", "fond_look"]),
    ("blue",  ["sob", "crying", "heartbroken", "worried", "brooding", "sleepy", "asleep", "dozing", "heavy_eyes", "gotosleep", "go_sleep", "helpless", "at_a_loss", "let_down", "overwhelmed", "sad", "bored", "listless"]),
    ("sulky", ["sulky", "pouty", "offend", "grumpy", "upset", "low_key_mad", "feigning_mad", "faux_furious", "cold_shoulder", "curt", "glaring_cut", "glaring_cuty"]),
    ("mad",   ["angry", "furious", "annoy", "irritat", "disgusting", "glaring"]),
    ("tense", ["suspicious", "taken_aback", "confused", "clueless", "dumbfounded", "panick", "freaking", "is_this_happening", "no_way", "for_real", "oh_really", "are_u_kidding", "what_now", "speechless", "so_cold", "poker_face", "fake_smile", "i_told_you_so", "smirk", "distracted"]),
    ("joy",   ["happy", "excited", "eureka", "goofy", "proud", "full_of_oneself", "playful", "hopeful"]),
    ("warm",  ["smile", "chuckle", "cheerup", "hi_", "its_you", "love"]),
    # 나머지(무대·행사·거리·해변 등 상황어) = base 폴백
]

# 캐릭터별 구성 — modes: {모드폴더: 루트(미분류) 파일이 흡수될 버킷들} · mode_dir: 변신 모드 폴더(viewer 게이트 축)
SEASONS = {
    "lucy": {
        "modes": {"android": ["base"], "dokkaebi": ["warm", "tense"]},
        "mode_dir": "dokkaebi",
        # 클립 = 파일 자체를 감정 폴더에 뒀다(260727) — android/joy/lucy_clip_02(루시·우주) · dokkaebi/joy/lucy_clip_01(레베카·미소).
        #   ⚠ 왜 갈랐나: 모드 필터가 경로로 자르므로 **캐릭터 루트에 두면 도깨비 창(21~03시)엔 절대 안 걸린다**(260727 실측).
        #   모드별로 얼굴이 다른 캐릭터라 각 모드 폴더에 그 얼굴의 클립을 둔다 = 낮·밤 양쪽에서 재생.
        "clip_w": 3,
        "comment": ("시즌 감정 미디어 manifest(루시) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 클립(muted 비디오) = joy 버킷 · clip_w=3 = 다른 사진 대비 3배 빈도(등간격). "
                    "버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — 사진 = 모드 폴더의 감정 하위폴더에 붓기만(예 android/joy/) · "
                    "모드 루트 미분류 = android→base · dokkaebi→warm·tense 흡수. "
                    "mode_dir=도깨비 폴더 — viewer 모드 게이트(yModeOn)가 활성 시 이 폴더만, 평시 제외로 필터(무드보다 우선). "
                    "정본=viewer/characters/season/lucy/{android,dokkaebi}/<감정>/."),
    },
    "desk": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → 시간대 필터 비활성
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(조지 로이스) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "정본=viewer/characters/season/desk/main/<감정>/."),
    },
    "sera": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → 시간대 필터 비활성
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(세라) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 얼빡 제외: base에 있던 sera_k01.jpg(640×640 정사각 프사 크롭)를 캐릭터 루트 sera_face01.jpg로 옮겼다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(sera_face.webp 선례 계승). "
                    "왜 뺐나 = 얼빡은 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 배경으로 부적합(운영자 260726 「얼빡은 배경에 깔지마」). "
                    "base는 잔여 3장(k02·k03·v06 = 전부 세로형)으로 로테이션 유지. "
                    "정본=viewer/characters/season/sera/main/<감정>/."),
    },
    "gojo": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(고죠) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/gojo/main/<감정>/."),
    },
    "reze": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(레제) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/reze/main/<감정>/."),
    },
    "seyeun": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(서예은) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/seyeun/main/<감정>/."),
    },
    "mudi": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(홍석천) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = 사람 없는 찻집 장소 씬 3장(yeta_bg_var 산출 var_mudi_* 사본 — 원본은 생성기 소관이라 여긴 사본이 정본). "
                    "배치 = 주방(불·주전자)→base · 뒷문(넘어진 스툴+발자국 = 도주 직후)→tense · 새벽 지붕(발자국이 넘어감)→blue. "
                    "정본=viewer/characters/season/mudi/main/<감정>/."),
    },
    "san": {
        # 평면 축(flat) — 운영자 260730 「최산도 윈터랑 같은급. 아이돌로 취급해지고 리포지토리 위치랑 그 트리 구조 계승도 맞춰줘」.
        #   종전(260730 오전)엔 season/san/main/<감정>/ 하위폴더 축이었다 → 같은 날 오후 지시로 윈터와 **같은 경로·같은 트리**로 이관.
        #   등급(roster grade "idol")과 에셋 경로를 한 축으로 정렬 = 아이돌은 `characters/idol/<id>/` 평면 + 감정 파일명.
        "flat": "characters/idol/san",
        # 클립 노브 = 윈터와 같은 계약(파일명 토큰이 먼저 · 미매치면 clip_to 폴백 · clip_w배 등간격).
        #   현 클립 seduce_vest_clip_01 은 파일명에 seduce 가 있어 love로 확정 = clip_to는 다음 클립용 폴백.
        "clip_to": ["love", "shy"],
        "clip_w": 3,
        "clip_cap": True,   # 260730 — 풀이 작아 3배를 그대로 먹이면 클립이 과반(love 6칸 중 3칸 = 두 턴에 한 번 영상)이 된다.
                            #   사진이 늘면 캡이 저절로 풀려 clip_w 3배로 복귀(운영자 「나중에 이미지를 더 넣을 것」).
                            #   윈터·루시는 운영자 명시 지정 축이라 캡을 안 건다(apply_clip_weight 독스트링 ⚠⚠).
        "rules": SAN_FLAT_RULES,   # 최산 전용 표(윈터와 별개 객체 · 운영자 260730 「절대 겹치면안됨」)
        "comment": ("감정 미디어 manifest(최산) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립). "
                    "⚠ 축 = **평면(flat) 폴더**(윈터와 동일 · 운영자 260730 「윈터랑 같은급 · 트리 구조 계승」) — 사진이 감정 하위폴더가 아니라 "
                    "`characters/idol/san/`에 **`san_` 접두 + 감정 단어** 파일명(san_happy_thumbs_up_01 · san_so_cold_02 · san_pouty_headphones_01 …)으로 모여 있고, "
                    "SAN_FLAT_RULES 토큰 규칙이 그걸 읽어 버킷에 넣는다(부분일치라 접두는 무해). ⚠ `san_` 접두 = **윈터와 파일명이 절대 안 겹치게** 하는 구조 장치(운영자 260730) — 새 사진도 접두를 붙일 것 · "
                    "어디에도 안 걸리면 base 폴백. 클립 = 파일명 토큰 우선(seduce_vest_clip_01 → love) · 미매치 시 clip_to(love·shy) · clip_w=3(등간격 3배). "
                    "얼빡 프사 `san_face.webp`는 같은 폴더에 두지만 `<id>_face*` 규약으로 배경 풀에서 자동 제외된다. "
                    "정본=viewer/characters/idol/san/."),
    },
    "winter": {
        # 평면 축(flat) — 감정 하위폴더 없이 파일명 토큰으로 분류. 파일을 안 옮기는 이유 = build_flat 독스트링.
        "flat": "characters/idol/winter",
        # 클립 노브(운영자 260727 "애정, 설렘 감정이 들때 나오게" + "다른것에 3배") — 평면 축이라 파일을 못 옮긴다(경로 불변이 이 캐릭터의 계약)
        #   → clip_to로 버킷을 지정한다. 종전 = base 66장 선두 = 66턴에 1번(사실상 안 보임).
        "clip_to": ["love", "shy"],
        "clip_w": 3,
        # ⚠ 위에서부터 첫 일치 승 — 표는 WINTER_FLAT_RULES(모듈 상단 · 윈터 전용 · 최산 표와 공유 금지).
        "rules": WINTER_FLAT_RULES,
        "comment": ("시즌 감정 미디어 manifest(윈터) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립). "
                    "클립 = 파일명에 감정 토큰이 있으면 그 버킷(bored_photoshoot_01 → blue · 260729), 없으면 clip_to 폴백(love·shy) · "
                    "clip_w=3 = 다른 사진 대비 3배 빈도(등간격 · 260727). "
                    "⚠ 다른 인물과 축이 다르다 = **평면(flat) 폴더** — 사진이 감정 하위폴더가 아니라 `characters/idol/winter/`에 "
                    "감정이 적힌 파일명(happy_01 · are_u_kidding_02 · glaring_cutely_03 …)으로 모여 있고, SEASONS['winter']['rules']의 "
                    "토큰 규칙이 그걸 읽어 버킷에 넣는다(파일 이동 0 = roster avatar·bg·카드 폴백 경로 불변). "
                    "새 사진 = 같은 폴더에 감정 단어가 들어간 이름으로 넣기만 · 어디에도 안 걸리면 base 폴백. "
                    "정본=viewer/characters/idol/winter/."),
    },
    "haeun": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 신규 편입(종전 0장 = 무대가 빈 채로 대화가 돌던 자리)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(하서연) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md)를 shared/cut_board_sheet.py로 자른 9:16 칸. "
                    "정본=viewer/characters/season/haeun/main/<감정>/."),
    },
    "yun": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 신규 편입(종전 0장 = 무대가 빈 채로 대화가 돌던 자리)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(윤) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md)를 shared/cut_board_sheet.py로 자른 9:16 칸. "
                    "정본=viewer/characters/season/yun/main/<감정>/."),
    },
    "baek": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 신규 편입(종전 0장 = 무대가 빈 채로 대화가 돌던 자리)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(백) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md)를 shared/cut_board_sheet.py로 자른 9:16 칸. "
                    "정본=viewer/characters/season/baek/main/<감정>/."),
    },
    "kopi": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 신규 편입(종전 0장 = 무대가 빈 채로 대화가 돌던 자리)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(카피) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md)를 shared/cut_board_sheet.py로 자른 9:16 칸. "
                    "정본=viewer/characters/season/kopi/main/<감정>/."),
    },
    "ryu": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 2차 보강(종전 1장)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(류) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md §6)를 shared/cut_board_sheet.py로 자른 9:16 칸(버킷당 2장). "
                    "정본=viewer/characters/season/ryu/main/<감정>/."),
    },
    "von": {
        # 변신 모드 없음 = 단일 폴더(main) · 260803 2차 보강(종전 2장)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(본) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종 — 사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "⚠ 출처 = 시트 F(캐릭터별 락 · docs/캐릭터보드_캐릭터별_보강.md §6)를 shared/cut_board_sheet.py로 자른 9:16 칸(버킷당 2장). "
                    "정본=viewer/characters/season/von/main/<감정>/."),
    },
    "hanna": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → 시간대 필터 비활성
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(도한나) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 출처 = 시트 E(9:16 상황 24칸 · docs/캐릭터보드_프롬프트_정본.md §2-E)를 shared/cut_board_sheet.py로 자른 것 — "
                    "칸당 ~318×566 = 무대(420×900) 규격. 얼빡 hanna_face.webp는 캐릭터 루트라 배경 풀에서 자동 제외. "
                    "정본=viewer/characters/season/hanna/main/<감정>/."),
    },
    "drusilla": {
        # 고죠 흉내 = 변신 모드(gojo 폴더) · mode_dir 지정 → viewer 모드 게이트가 경로로 필터.
        # ⚠ 루시(도깨비)의 시간대 게이트와 축이 다르다 — 프리실라 mode는 roster mode.with=["gojo"](동석 게이트)라
        #    "고죠와 같은 방일 때만" gojo/ 폴더가 열린다(yModeOn 동석축 · 260726).
        "modes": {"main": ["base"], "gojo": ["base"]},
        "mode_dir": "gojo",
        "comment": ("시즌 감정 미디어 manifest(프리실라) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 9종(base/warm/joy/love/shy/blue/tense/mad/sulky · Q.29 + 260726 삐짐 독립) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "mode_dir=고죠 흉내 폴더 — viewer 모드 게이트(yModeOn 동석축 roster mode.with=[\"gojo\"])가 활성 시 이 폴더만, 평시 제외로 필터. "
                    "정본=viewer/characters/season/drusilla/{main,gojo}/<감정>/."),
    },
}


def rel(p: Path) -> str:
    return p.relative_to(ROOT / "viewer").as_posix()  # viewer 서빙 루트 기준(로스터 bg 경로 규약과 동일)


# ── 클립 노브 2종(운영자 260727) — 「영상이 너무 안 나온다」 ────────────────────────────
# 배경 로테이션은 viewer yStage의 `pool[n % len]`(답장수 결정적 순회)이라, 풀에 1번 실린 클립은
# **한 바퀴에 딱 한 번**만 걸린다(윈터 base 66장 = 66턴에 1번). 노브는 그 확률을 푸는 두 축이다.
#   · clip_to = 클립이 실릴 버킷들(미지정 = base = 종전 계약) — 감정 폴더로 파일을 못 옮기는
#     평면(flat) 캐릭터에서 「이 감정일 때 영상」을 지정하는 유일한 수단(윈터 = love·shy).
#     감정 폴더 축(build_one)은 파일을 그 폴더에 두면 되므로 보통 불요.
#   · clip_w  = 클립 1개가 한 바퀴에 실리는 횟수 = **다른 사진 대비 배수**(3 = 3배).
# ⚠ 반복분을 뒤에 몰아 붙이면 같은 영상이 연속 턴에 연타된다 → weave가 **등간격 슬롯**에 꽂는다.
def weave(items: list, extra: list) -> list:
    """extra(클립 반복분)를 items 사이 등간격에 끼운다 — 연타 방지 · 총 길이 = len(items)+len(extra).

    ⚠ 260730 슬롯 반칸 밀기 — 종전 `int(i*step)`은 i=0에서 **항상 슬롯 0**이라 클립이 풀 맨 앞에 섰다.
      뷰어 yStage는 답장수 n의 `pool[n%len]`을 집는데, **방을 처음 열면 n≡0** = 늘 클립이 걸린다.
      그런데 시즌 첫 페인트는 암전 방지를 위해 **클립을 건너뛰고 시그니처 스틸로 착지**하는 계약이라
      (yStage `_yStageCold`), 결과가 「설렘 국면인데 base 시그니처가 뜬다」였다(운영자 260730 실측 지적).
      `(i+0.5)*step`으로 반칸 밀면 extra는 **구간 한가운데**에 꽂힌다 → 슬롯 0은 항상 사진 =
      첫 진입이 그 감정의 진짜 사진으로 착지한다. 등간격·연타 방지 성질은 그대로.
    """
    if not extra:
        return list(items)
    total = len(items) + len(extra)
    step = total / len(extra)                       # total ≥ len(extra) → step ≥ 1 → 슬롯 충돌 없음
    slots = {int((i + 0.5) * step) for i in range(len(extra))}   # 반칸 밀기(위 ⚠) · 최대 (len-0.5)*step < total = 범위 안전
    out, ii, ei = [], 0, 0
    for i in range(total):
        if i in slots and ei < len(extra):
            out.append(extra[ei]); ei += 1
        else:
            out.append(items[ii]); ii += 1
    return out


def clip_buckets(cfg: dict) -> list:
    """클립이 실릴 버킷 — 미지정 = base(종전 계약 · 대화 시작 배경)."""
    return [b for b in (cfg.get("clip_to") or ["base"]) if b in EMOS]


def apply_clip_weight(buckets: dict, cfg: dict) -> None:
    """버킷 안의 클립을 clip_w배로 늘려 등간격 재배치(제자리 수정). 감정 폴더 축·평면 축 공용.

    ⚠ 260730 사진 수 비례 상한 — clip_w는 윈터(버킷당 사진 11~62장) 기준으로 정한 3배다.
      사진이 적은 버킷에 그대로 3배를 먹이면 **클립이 과반**이 된다(실측: 최산 love = 사진 2 + 클립 3
      = 6칸 중 3칸이 영상 = 두 턴 중 한 번이 영상). 「일단 자연스럽게」가 우선이므로
      **클립 반복분이 사진 수의 절반을 넘지 않게** 캡을 건다 — 사진이 늘면 캡이 풀려 자동으로
      원래 clip_w로 복귀한다(운영자 260730 「최산거는 나중에 이미지를 더 넣을 것」 = 스스로 자라는 규칙).
      캡 계산은 **클립 종류 수**가 아니라 반복 배수에만 건다(클립이 여러 개인 버킷도 각자 1배는 보장).
      ⚠⚠ 기본은 **끔**(`clip_cap` 미지정 = 종전 동작 그대로). 켜면 칸 수가 줄어드는데, 윈터·루시는
        운영자가 260727에 「영상이 너무 안 나온다 · 애정/설렘 때 나오게 · 다른 것에 3배」로 **명시 지정**한
        축이라 그 결정을 자동으로 뒤집으면 안 된다. 새로 붓는 인물처럼 풀이 작아 클립이 과반이 되는
        경우에만 켠다(현재 = 최산).
    """
    w = int(cfg.get("clip_w") or 1)
    if w <= 1:
        return
    cap = bool(cfg.get("clip_cap"))
    for e, lst in buckets.items():
        clips = [p for p in lst if p.suffix.lower() in CLIP_EXT]
        if not clips:
            continue
        imgs = [p for p in lst if p.suffix.lower() not in CLIP_EXT]
        w_eff = min(w, max(1, len(imgs) // (2 * len(clips)))) if cap else w   # 캡 ON = 클립 총 칸수 ≤ 사진 수의 절반
        buckets[e] = weave(imgs, clips * w_eff)


def build_flat(cid: str, cfg: dict) -> dict:
    """평면 폴더 축(260726 윈터) — 감정 하위폴더 없이 **파일명에 감정이 적혀 있는** 수집분을 규칙으로 분류.

    왜 별도 축인가: 윈터 189장은 `characters/idol/<id>/` 규약(아이돌 등급 · inject_character.sh 폴백 경로)으로 먼저 모였고,
    파일명 자체가 감정 라벨이다(happy_01 · are_u_kidding_02 · glaring_cutely_03 …). 이걸 감정 폴더로 옮기면
    roster avatar·bg와 카드 폴백 경로가 전부 깨진다 → **파일을 옮기는 대신 규칙으로 읽는다**(경로 불변).
    규칙 = (버킷, [토큰…]) 리스트 · **위에서부터 첫 일치 승**(specific → general 순서로 적을 것 · 오타 수집분도 토큰으로 흡수).
    어디에도 안 걸리면 base(안전망) — 새 파일을 부어도 최소 base로는 잡힌다.
    """
    fdir = ROOT / "viewer" / cfg["flat"]
    if not fdir.is_dir():
        raise SystemExit(f"평면 폴더 없음: {fdir}")
    buckets = {e: [] for e in EMOS}
    rules = cfg["rules"]
    # 클립(mp4/webm) — 260726엔 clip_to 버킷 일괄이었다(그 처리가 아예 빠져 운영자가 넣은 영상 3개가 통째로 무시됐던 자리).
    # ⚠ 260729 보강: 클립도 **사진과 같은 파일명 규칙**을 먼저 탄다. 종전엔 clip_to가 폴더 안 모든 클립을 강제 흡수해서
    #   「이 영상은 다른 감정」을 파일명으로 지정할 방법이 없었다(운영자 260729 = 따분·심심 클립을 blue로).
    #   토큰 미매치 = 종전 clip_to 폴백 → 기존 3종(go_for_a_walk_date_*)은 어느 토큰에도 안 걸려 love·shy 그대로(회귀 0 · 실측).
    _named_clips, _fallback_clips = [], []
    for _c in sorted(p for p in fdir.iterdir() if p.is_file() and p.suffix.lower() in CLIP_EXT):
        _nm = _c.stem.lower()
        for _emo, _toks in rules:
            if any(t in _nm for t in _toks):
                buckets[_emo].append(_c)
                _named_clips.append((_c.name, _emo))
                break
        else:
            _fallback_clips.append(_c)
    for _b in clip_buckets(cfg):
        buckets[_b].extend(_fallback_clips)
    for _n, _e in _named_clips:
        print(f"🎬 {cid}: 클립 파일명 분류 — {_n} → {_e} (clip_to 폴백 미적용)")
    for p in sorted(fdir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in IMG_EXT:
            continue
        nm = p.stem.lower()
        # 얼빡 프사 제외(260730) — 평면 축엔 이 제외가 없어서 프사가 배경 풀에 섞여 있었다(윈터 winter_face.webp = base 62번째 · 실측).
        #   운영자 260726 「얼빡은 배경에 깔지마」가 감정 폴더 축(build_one의 is_face)에만 걸려 있던 자리다.
        #   ⚠ 판정은 넓은 FACE_PAT(is_face)이 아니라 **`<id>_face…` 규약 이름만** — 평면 축 어휘엔 poker_face·fake_smile처럼
        #     'face'가 든 **정상 배경**이 있어서 넓게 잡으면 그걸 같이 떨어뜨린다(윈터 poker_face_01 = tense · 실측).
        if nm.startswith(f"{cid}_face"):
            continue
        for emo, toks in rules:
            if any(t in nm for t in toks):
                buckets[emo].append(p)
                break
        else:
            buckets["base"].append(p)
    apply_clip_weight(buckets, cfg)   # 클립 가중치(clip_w) = 등간격 반복
    out = {"_comment": cfg["comment"]}
    for e in EMOS:
        if buckets[e]:
            out[e] = [rel(p) for p in buckets[e]]
    return out


def build_one(cid: str, cfg: dict) -> dict:
    if cfg.get("flat"):
        return build_flat(cid, cfg)
    cdir = SEASON_DIR / cid
    if not cdir.is_dir():
        raise SystemExit(f"캐릭터 폴더 없음: {cdir}")
    buckets = {e: [] for e in EMOS}
    rootb = {e: [] for e in EMOS}
    clips = sorted(p for p in cdir.iterdir() if p.suffix.lower() in CLIP_EXT)
    for b in clip_buckets(cfg):
        rootb[b].extend(clips)  # 캐릭터 루트 클립 = clip_to 버킷 선두(미지정 = base 선두 계약)
    apply_clip_weight(rootb, cfg)

    def collect(d: Path) -> list:
        """배경 풀 수집 — 프사는 파일명으로 제외하고 **로그로 알린다**(조용한 누락 = 다음 사고).
        정사각~가로형은 제외하지 않고 경고만 — 전신 풍경도 정사각일 수 있어 기계가 못 가린다."""
        out = []
        for p in sorted(d.iterdir()):
            if not (p.is_file() and p.suffix.lower() in MEDIA_EXT):
                continue
            if is_face(p):
                print(f"⏭️  {cid}: 프사 제외 — {p.relative_to(cdir)} (파일명 규약 · 배경 풀 미편입)")
                continue
            wh = img_size(p)
            if wh and wh[1] and wh[0] / wh[1] > FACE_RATIO:
                print(f"⚠️  {cid}: 정사각~가로형 {wh[0]}×{wh[1]} — {p.relative_to(cdir)} "
                      f"(세로 무대 cover 시 좌우 잘림 · 얼빡이면 파일명에 'face'를 넣어 제외 "
                      f"· 배경으로 쓸 거면 check_refs _FACE_RATIO_OK에 등재)")
            out.append(p)
        return out

    # ⚠ 가중치는 **모드 단위로** 건다(260727 실측). viewer 모드 필터는 완성된 풀을 경로로 잘라내므로,
    #   섞인 풀에 등간격을 잡아두면 잘린 뒤 간격이 무너져 클립이 연타로 붙는다(평시 joy ▶····▶▶).
    #   모드별로 짠 뒤 이어 붙이면 어느 쪽으로 잘려도 그 안의 등간격이 그대로 남는다.
    for e in EMOS:
        buckets[e].extend(rootb[e])
    for mode, root_to in cfg["modes"].items():
        mdir = cdir / mode
        if not mdir.is_dir():
            continue
        mb = {e: [] for e in EMOS}
        for b in root_to:  # 모드 루트 미분류 = 지정 버킷 흡수(신규 수집 안전망)
            mb[b].extend(collect(mdir))
        for sub in sorted(d for d in mdir.iterdir() if d.is_dir()):
            if sub.name not in EMOS:
                print(f"⚠️ {cid}: 규약 밖 폴더 무시 — {mode}/{sub.name}/ (허용 = {'/'.join(EMOS)})")
                continue
            mb[sub.name].extend(collect(sub))
        apply_clip_weight(mb, cfg)   # 클립 가중치(clip_w) = 그 모드 안에서 등간격 반복
        for e in EMOS:
            buckets[e].extend(mb[e])
    out = {"_comment": cfg["comment"]}
    for e in EMOS:
        if buckets[e]:
            out[e] = [rel(p) for p in buckets[e]]  # 빈 버킷 = 생략(viewer 그룹 폴백 Y_GRP가 흡수)
    if cfg.get("mode_dir"):
        out["mode_dir"] = cfg["mode_dir"]
    return out


def _assert_no_dup_keys() -> None:
    """SEASONS 중복키 금지(260804 평의회 #16) — dict 리터럴은 **뒤 정의가 조용히 이긴다**.

    355차에 4인(haeun·yun·baek·kopi)이 두 번 정의돼 앞 4블록이 사문이 됐다. 산출물은 같아 아무도 못 알아채는데,
    앞 블록을 고치면 「고쳤는데 안 바뀐다」가 된다 = 편집 함정. 소스를 직접 세어 재발을 그 자리에서 막는다.
    """
    import collections
    src = open(__file__, encoding="utf-8").read()
    keys = re.findall(r'^    "([a-z0-9_-]+)": \{', src, flags=re.M)
    dup = [k for k, n in collections.Counter(keys).items() if n > 1]
    if dup:
        raise SystemExit(f"SEASONS 중복키: {', '.join(dup)} — 한 캐릭터는 한 번만 정의한다(뒤 정의가 이겨 앞이 사문이 된다)")


def main() -> int:
    _assert_no_dup_keys()
    check = "--check" in sys.argv
    rc = 0
    for cid, cfg in SEASONS.items():
        mpath = (ROOT / "viewer" / cfg["flat"] / "media.json") if cfg.get("flat") else (SEASON_DIR / cid / "media.json")
        fresh = build_one(cid, cfg)
        cur = None
        if mpath.exists():
            try:
                cur = json.loads(mpath.read_text(encoding="utf-8"))
            except Exception:
                cur = None
        stat = " · ".join(f"{e} {len(fresh.get(e, []))}" for e in EMOS if fresh.get(e))
        if cur == fresh:
            print(f"OK {cid}: media.json 최신 ({stat})")
            continue
        if check:
            print(f"DRIFT {cid}: media.json ≠ 폴더 실측 — python3 shared/build_season_media.py 로 재생성")
            rc = 1
            continue
        mpath.write_text(json.dumps(fresh, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"WROTE {cid}: media.json 재생성 ({stat} · mode_dir {fresh.get('mode_dir', '-')})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
