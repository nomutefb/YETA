#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_face_base.py — 초상 프롬프트 SSOT 회귀 하니스 (260803 · 의존성 0 = stdlib만).

**왜 있나**: 260803에 `yeta_face.BASE`(로스터 10인 초상 프롬프트)를 세 조각으로 갈랐다 —
`STYLE_A`(화풍) + `FRAME_1X1`(정사각 얼굴 프레이밍) + `STYLE_B`(인물·조명·안전가드).
이유는 「내 캐릭터 3컷 시트」(`yeta_meface.py` KIND=sheet)가 **톤만 계승하고 프레이밍만 갈아끼워야** 해서다.
쪼개는 순간 위험이 생긴다 — 조각 하나를 손대면 **10인 초상 톤이 조용히 바뀐다**(그림은 dispatch 때나 보이니 늦게 들킨다).
이 테스트가 그 조용한 변화를 커밋 시점에 잡는다.

검사 3종:
  ① BASE = 세 조각 연결(순서·공백 무변) · 길이 983 박제 — 조각 편집 = 여기서 즉시 적색
  ② FRAME_1X1 = 정사각 얼굴 프레이밍 어휘 보유(다른 조각으로 새지 않았나)
  ③ 3컷 시트 프롬프트 = 톤 두 조각 계승 + 프레이밍 교체(1:1 어휘 잔존 0 · 전신/A-포즈 절 생존)
  ④ 얼빡 정본(`yeta_char_art.AV_BASE`) 동일 분할 + `sheet=FACE`(머리 전체 판)가 톤만 계승하는지

실행: `python3 tests/test_face_base.py`  (rc=0 통과 · rc=1 실패)
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, ".github", "scripts")
BASE_LEN = 983      # 260803 분할 시점 실측(원문 = 260712 루시 톤 통일본)
AV_BASE_LEN = 1103   # 260805 분할 시점 실측(얼빡 정본 = yeta_char_art.AV_BASE)


def load(name):
    sys.path.insert(0, SCRIPTS)
    os.environ.setdefault("OPENAI_API_KEY", "test")   # 임포트 시 키 없어도 no-op 경로만 타면 되지만, 상수 로드에는 무관
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    face = load("yeta_face")
    meface = load("yeta_meface")
    fails = []

    def ck(cond, label):
        print(("  OK  " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("① BASE 조립 무손실")
    ck(face.BASE == face.STYLE_A + face.FRAME_1X1 + face.STYLE_B, "BASE = STYLE_A + FRAME_1X1 + STYLE_B")
    ck(len(face.BASE) == BASE_LEN, "BASE 길이 {} (실측 {})".format(BASE_LEN, len(face.BASE)))
    ck(face.BASE.endswith("Character — "), "BASE 꼬리 = 'Character — '(호출부가 인물 절을 이어붙인다)")

    print("② 프레이밍 조각 격리")
    ck("perfectly square 1:1" in face.FRAME_1X1, "정사각 어휘 = FRAME_1X1 안")
    ck("perfectly square 1:1" not in face.STYLE_A + face.STYLE_B, "톤 조각엔 프레이밍 어휘 없음")

    print("③ 3컷 시트 = 톤 계승 + 프레이밍 교체")
    sheet = meface.sheet_prompt("테스트용 소개 한 줄.")
    ck(face.STYLE_A in sheet, "STYLE_A 계승")
    ck(face.STYLE_B in sheet, "STYLE_B 계승")
    ck(face.FRAME_1X1 not in sheet, "FRAME_1X1 미포함(프레이밍 교체됨)")
    for kw in ("THREE stacked", "A-pose", "head to feet"):
        ck(kw in sheet, "시트 프레이밍 절 생존 — " + kw)
    ck(meface.SHEET_SIZE == "1024x1536", "시트 size = 세로 1024x1536(칸 3개 × 512)")
    ck(meface.FACE_CROP == (512, 512), "얼굴 칸 크롭 = 512² (칸 높이와 동수)")

    print("④ 얼빡 정본(AV_BASE) 분할 무손실 + sheet=FACE 프레이밍 교체")
    art = load("yeta_char_art")
    ck(art.AV_BASE == art.AV_FRAME_TIGHT + art.AV_STYLE, "AV_BASE = AV_FRAME_TIGHT + AV_STYLE")
    ck(len(art.AV_BASE) == AV_BASE_LEN, "AV_BASE 길이 {} (실측 {})".format(AV_BASE_LEN, len(art.AV_BASE)))
    ck("just above the eyebrows" in art.AV_FRAME_TIGHT, "극단 크롭 어휘 = AV_FRAME_TIGHT 안")
    ck("just above the eyebrows" not in art.AV_STYLE, "톤 조각엔 크롭 어휘 없음")
    os.environ["YETA_BOARD_SHEET"], os.environ["YETA_BOARD_SLUG"] = "FACE", "haeun"
    board = load("yeta_char_board")
    fp = board.build_face()
    ck(art.AV_STYLE in fp, "sheet=FACE = 톤(AV_STYLE) 계승")
    ck("just above the eyebrows" not in fp, "sheet=FACE = 극단 크롭 미포함(md FACE_FRAME이 대체)")
    for kw in ("whole head fills the square frame", "bridge of the nose"):
        ck(kw in fp, "머리 전체 프레이밍 절 생존 — " + kw)
    ck(board.SIZES.get("FACE") == "1024x1024", "FACE size = 1:1 1024²")

    print("\n" + ("통과 — 실패 0" if not fails else "실패 {}건: {}".format(len(fails), " · ".join(fails))))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
