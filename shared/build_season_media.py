#!/usr/bin/env python3
"""시즌 감정 미디어 manifest 생성기 — viewer/characters/season/<id>/media.json 재생성 (260717 Q.25 · Q.29 8감정 확장)

운영 흐름(운영자 260717 "수집은 많이 해줄 수 있는데 감정 명시가 비효율" → "다채롭게 나눠봐"):
  사진을 모드 폴더의 **감정 하위폴더**(android/joy/ · dokkaebi/tense/ 등)에 아무 이름으로 던져넣고
  이 스크립트를 돌리면 끝. 하위폴더 없이 모드 루트에 부으면 그 모드의 기본 버킷으로 흡수(미분류 안전망).

규약:
  · 감정 버킷 = EMOS 8종(base/warm/joy/love/shy/blue/tense/mad) — viewer Y_MOODS·러너 <<MOOD>> 화이트리스트와 짝(불변 계약)
  · mode_dir = 변신 모드 전용 폴더명 — viewer yStage 모드 게이트(yModeOn)가 경로(/dokkaebi/)로 필터(하위폴더 깊이 무관)
  · 클립(mp4/webm · 캐릭터 루트) = base 선두(대화 시작 배경 계약)
  · 산출물 media.json = 기계 산출물(CLAUDE.md [0] ⚙ · check_refs 하드 게이트) — 손편집 금지, 값 변경 = 이 스크립트 수정.

사용: python3 shared/build_season_media.py            # 전 시즌 캐릭터 재생성
      python3 shared/build_season_media.py --check    # 재생성 없이 드리프트 검사(rc=1)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON_DIR = ROOT / "viewer" / "characters" / "season"
IMG_EXT = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".gif", ".avif"}   # .jfif(260726) = 브라우저 저장 JPEG 변종 — 운영자 업로드에 그대로 섞여 들어온다. ⚠ 서빙 MIME이 호스트에 따라 octet-stream이 될 수 있어 **가능하면 .jpg로 개명해 두는 게 안전**(바이트 동일 = 무손실). 여기 등재는 누락 방지용 안전망.
CLIP_EXT = {".mp4", ".webm"}
EMOS = ["base", "warm", "joy", "love", "shy", "blue", "tense", "mad"]  # viewer Y_MOODS(+base)·러너 화이트리스트와 짝

# 캐릭터별 구성 — modes: {모드폴더: 루트(미분류) 파일이 흡수될 버킷들} · mode_dir: 변신 모드 폴더(viewer 게이트 축)
SEASONS = {
    "lucy": {
        "modes": {"android": ["base"], "dokkaebi": ["warm", "tense"]},
        "mode_dir": "dokkaebi",
        "comment": ("시즌 감정 미디어 manifest(루시) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. base 선두 클립=대화 시작배경(muted 비디오). "
                    "버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — 사진 = 모드 폴더의 감정 하위폴더에 붓기만(예 android/joy/) · "
                    "모드 루트 미분류 = android→base · dokkaebi→warm·tense 흡수. "
                    "mode_dir=도깨비 폴더 — viewer 모드 게이트(yModeOn)가 활성 시 이 폴더만, 평시 제외로 필터(무드보다 우선). "
                    "정본=viewer/characters/season/lucy/{android,dokkaebi}/<감정>/."),
    },
    "desk": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → 시간대 필터 비활성
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(조지 로이스) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "정본=viewer/characters/season/desk/main/<감정>/."),
    },
    "sera": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → 시간대 필터 비활성
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(세라) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
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
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/gojo/main/<감정>/."),
    },
    "reze": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(레제) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/reze/main/<감정>/."),
    },
    "seyeun": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(서예은) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/seyeun/main/<감정>/."),
    },
    "mudi": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(홍석천) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = 사람 없는 찻집 장소 씬 3장(yeta_bg_var 산출 var_mudi_* 사본 — 원본은 생성기 소관이라 여긴 사본이 정본). "
                    "배치 = 주방(불·주전자)→base · 뒷문(넘어진 스툴+발자국 = 도주 직후)→tense · 새벽 지붕(발자국이 넘어감)→blue. "
                    "정본=viewer/characters/season/mudi/main/<감정>/."),
    },
    "von": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(본) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = 사람 없는 체육관 장소 씬만(운영자 '페르소나 구축 안 된 애들은 익명으로 넣고 나중에 보강') — 인물 초상은 미수집. "
                    "정본=viewer/characters/season/von/main/<감정>/."),
    },
    "ryu": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(류) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = 얼굴 없는 검도 실루엣 1장뿐(운영자 '익명으로 넣고 나중에 보강') — 인물 확정 아님 · tense 국면 전용. "
                    "정본=viewer/characters/season/ryu/main/<감정>/."),
    },
    "haeun": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(하서연) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = **배경 풀 0장**(manifest 빈 껍데기 = 뷰어 시그니처 폴백 유지). 얼빡 프사 1장은 캐릭터 루트 `<id>_face01.webp`에 둔다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(세라 sera_face.webp 선례 계승). "
                    "⚠ 왜 뺐나(260726 게이트 개방 실측): 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 "
                    "기존 전용 배경 var_persona_<id>.webp보다 나빴다. 수집분 들어오면 main/<감정>/에 부어 확장. "
                    "정본=viewer/characters/season/haeun/main/<감정>/."),
    },
    "baek": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(백) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = **배경 풀 0장**(manifest 빈 껍데기 = 뷰어 시그니처 폴백 유지). 얼빡 프사 1장은 캐릭터 루트 `<id>_face01.webp`에 둔다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(세라 sera_face.webp 선례 계승). "
                    "⚠ 왜 뺐나(260726 게이트 개방 실측): 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 "
                    "기존 전용 배경 var_persona_<id>.webp보다 나빴다. 수집분 들어오면 main/<감정>/에 부어 확장. "
                    "정본=viewer/characters/season/baek/main/<감정>/."),
    },
    "yun": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(윤) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = **배경 풀 0장**(manifest 빈 껍데기 = 뷰어 시그니처 폴백 유지). 얼빡 프사 1장은 캐릭터 루트 `<id>_face01.webp`에 둔다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(세라 sera_face.webp 선례 계승). "
                    "⚠ 왜 뺐나(260726 게이트 개방 실측): 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 "
                    "기존 전용 배경 var_persona_<id>.webp보다 나빴다. 수집분 들어오면 main/<감정>/에 부어 확장. "
                    "정본=viewer/characters/season/yun/main/<감정>/."),
    },
    "kopi": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(카피) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = **배경 풀 0장**(manifest 빈 껍데기 = 뷰어 시그니처 폴백 유지). 얼빡 프사 1장은 캐릭터 루트 `<id>_face01.webp`에 둔다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(세라 sera_face.webp 선례 계승). "
                    "⚠ 왜 뺐나(260726 게이트 개방 실측): 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 "
                    "기존 전용 배경 var_persona_<id>.webp보다 나빴다. 수집분 들어오면 main/<감정>/에 부어 확장. "
                    "정본=viewer/characters/season/kopi/main/<감정>/."),
    },
    "aeri": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(애리) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음. "
                    "⚠ 260726 현재 = **배경 풀 0장**(manifest 빈 껍데기 = 뷰어 시그니처 폴백 유지). 얼빡 프사 1장은 캐릭터 루트 `<id>_face01.webp`에 둔다 "
                    "— 루트 이미지는 build_one이 안 읽으므로(클립만 읽음) 배경 풀에서 자동 제외되는 자리다(세라 sera_face.webp 선례 계승). "
                    "⚠ 왜 뺐나(260726 게이트 개방 실측): 얼빡 = 정사각 프사 크롭이라 420×900 세로 무대에 cover로 깔면 얼굴만 확대·잘려 "
                    "기존 전용 배경 var_persona_<id>.webp보다 나빴다. 수집분 들어오면 main/<감정>/에 부어 확장. "
                    "정본=viewer/characters/season/aeri/main/<감정>/."),
    },
    "winter": {
        # 평면 축(flat) — 감정 하위폴더 없이 파일명 토큰으로 분류. 파일을 안 옮기는 이유 = build_flat 독스트링.
        "flat": "characters/idol/winter",
        # ⚠ 위에서부터 첫 일치 승 — 좁은 토큰을 먼저. (예: glaring_cut → shy 가 glaring → mad 보다 위)
        "rules": [
            ("shy",   ["glaring_cut", "glaring_cuty", "tsundere", "hesitant_to_speak", "flustered", "giggle_bashfully", "act_cute", "play_cute", "playful_cute"]),
            ("love",  ["seduce", "flirty", "love_u", "how_do_i_look", "miss_someone", "fond_look"]),
            ("blue",  ["sob", "crying", "heartbroken", "worried", "brooding", "sleepy", "asleep", "dozing", "heavy_eyes", "gotosleep", "go_sleep", "helpless", "at_a_loss", "let_down", "overwhelmed", "sad"]),
            ("mad",   ["angry", "furious", "annoy", "irritat", "offend", "pouty", "sulky", "grumpy", "upset", "low_key_mad", "feigning_mad", "disgusting", "cold_shoulder", "glaring", "curt"]),
            ("tense", ["suspicious", "taken_aback", "confused", "clueless", "dumbfounded", "panick", "freaking", "is_this_happening", "no_way", "for_real", "oh_really", "are_u_kidding", "what_now", "speechless", "so_cold", "poker_face", "fake_smile", "i_told_you_so", "smirk", "distracted"]),
            ("joy",   ["happy", "excited", "eureka", "goofy", "proud", "full_of_oneself", "playful", "hopeful"]),
            ("warm",  ["smile", "chuckle", "cheerup", "hi_", "its_you", "love"]),
            # 나머지(무대·연습·일상·배경·모델컷 등) = base 폴백
        ],
        "comment": ("시즌 감정 미디어 manifest(윈터) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29). "
                    "⚠ 다른 인물과 축이 다르다 = **평면(flat) 폴더** — 사진이 감정 하위폴더가 아니라 `characters/idol/winter/`에 "
                    "감정이 적힌 파일명(happy_01 · are_u_kidding_02 · glaring_cutely_03 …)으로 모여 있고, SEASONS['winter']['rules']의 "
                    "토큰 규칙이 그걸 읽어 버킷에 넣는다(파일 이동 0 = roster avatar·bg·카드 폴백 경로 불변). "
                    "새 사진 = 같은 폴더에 감정 단어가 들어간 이름으로 넣기만 · 어디에도 안 걸리면 base 폴백. "
                    "정본=viewer/characters/idol/winter/."),
    },
    "drusilla": {
        # 고죠 흉내 = 변신 모드(gojo 폴더) · mode_dir 지정 → viewer 모드 게이트가 경로로 필터.
        # ⚠ 루시(도깨비)의 시간대 게이트와 축이 다르다 — 드루실라 mode는 roster mode.with=["gojo"](동석 게이트)라
        #    "고죠와 같은 방일 때만" gojo/ 폴더가 열린다(yModeOn 동석축 · 260726).
        "modes": {"main": ["base"], "gojo": ["base"]},
        "mode_dir": "gojo",
        "comment": ("시즌 감정 미디어 manifest(드루실라) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. "
                    "mode_dir=고죠 흉내 폴더 — viewer 모드 게이트(yModeOn 동석축 roster mode.with=[\"gojo\"])가 활성 시 이 폴더만, 평시 제외로 필터. "
                    "정본=viewer/characters/season/drusilla/{main,gojo}/<감정>/."),
    },
}


def rel(p: Path) -> str:
    return p.relative_to(ROOT / "viewer").as_posix()  # viewer 서빙 루트 기준(로스터 bg 경로 규약과 동일)


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
    # 클립(mp4/webm) = base 선두 계약 — build_one과 동형(260726 실측: 이 처리가 빠져 있어 운영자가 넣은 영상 3개가 통째로 무시됐다).
    buckets["base"].extend(sorted(p for p in fdir.iterdir() if p.is_file() and p.suffix.lower() in CLIP_EXT))
    for p in sorted(fdir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in IMG_EXT:
            continue
        nm = p.stem.lower()
        for emo, toks in rules:
            if any(t in nm for t in toks):
                buckets[emo].append(p)
                break
        else:
            buckets["base"].append(p)
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
    clips = sorted(p for p in cdir.iterdir() if p.suffix.lower() in CLIP_EXT)
    buckets["base"].extend(clips)  # 클립 = base 선두 계약
    for mode, root_to in cfg["modes"].items():
        mdir = cdir / mode
        if not mdir.is_dir():
            continue
        # ⚠ 260726: 종전엔 여기서 IMG_EXT만 읽어 **감정 폴더에 넣은 영상이 통째로 무시**됐다(운영자 "고죠 기분좋을때 나오는 영상").
        #   클립은 캐릭터 루트(=base 선두)에만 놓을 수 있었던 셈 — 감정 지정이 불가능했다. IMG_EXT|CLIP_EXT로 확장해
        #   **아무 감정 버킷에나 영상을 넣을 수 있게** 한다(뷰어 yStage는 이미 확장자로 클립을 판별하므로 무수정).
        MEDIA_EXT = IMG_EXT | CLIP_EXT
        for b in root_to:  # 모드 루트 미분류 = 지정 버킷 흡수(신규 수집 안전망)
            buckets[b].extend(sorted(p for p in mdir.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXT))
        for sub in sorted(d for d in mdir.iterdir() if d.is_dir()):
            if sub.name not in EMOS:
                print(f"⚠️ {cid}: 규약 밖 폴더 무시 — {mode}/{sub.name}/ (허용 = {'/'.join(EMOS)})")
                continue
            buckets[sub.name].extend(sorted(p for p in sub.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXT))
    out = {"_comment": cfg["comment"]}
    for e in EMOS:
        if buckets[e]:
            out[e] = [rel(p) for p in buckets[e]]  # 빈 버킷 = 생략(viewer 그룹 폴백 Y_GRP가 흡수)
    if cfg.get("mode_dir"):
        out["mode_dir"] = cfg["mode_dir"]
    return out


def main() -> int:
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
