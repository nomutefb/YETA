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
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
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
    "gojo": {
        # 변신 모드 없음 = 단일 폴더(main) · mode_dir 미지정 → viewer 모드 게이트 비활성(불변 캐릭터 경로)
        "modes": {"main": ["base"]},
        "comment": ("시즌 감정 미디어 manifest(고죠) — 기계 산출물(shared/build_season_media.py · 손편집 금지 · check_refs 게이트). "
                    "yStage 답장수 n 결정적 로테이션 pool[n%len]. 버킷 = 감정 8종(base/warm/joy/love/shy/blue/tense/mad · Q.29) — "
                    "사진 = main/<감정>/에 붓기만 · 미분류(main 루트) = base 흡수. 변신 모드 없음(mode_dir 없음 = 시간대 필터 비활성). "
                    "정본=viewer/characters/season/gojo/main/<감정>/."),
    },
}


def rel(p: Path) -> str:
    return p.relative_to(ROOT / "viewer").as_posix()  # viewer 서빙 루트 기준(로스터 bg 경로 규약과 동일)


def build_one(cid: str, cfg: dict) -> dict:
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
        for b in root_to:  # 모드 루트 미분류 = 지정 버킷 흡수(신규 수집 안전망)
            buckets[b].extend(sorted(p for p in mdir.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT))
        for sub in sorted(d for d in mdir.iterdir() if d.is_dir()):
            if sub.name not in EMOS:
                print(f"⚠️ {cid}: 규약 밖 폴더 무시 — {mode}/{sub.name}/ (허용 = {'/'.join(EMOS)})")
                continue
            buckets[sub.name].extend(sorted(p for p in sub.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT))
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
        mpath = SEASON_DIR / cid / "media.json"
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
