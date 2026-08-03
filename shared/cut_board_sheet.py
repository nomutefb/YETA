#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cut_board_sheet.py — 캐릭터 보드 시트를 칸 단위로 자른다 (운영자 260803 "n장에 여러 개 뽑아서 **잘라서 쓰자**").

왜 필요한가: `yeta-char-board` dispatch가 뽑는 건 **한 장짜리 시트**(칸 6~20개)다. 앱에 꽂으려면 칸을 잘라
`viewer/characters/season/<id>/main/<감정>/`에 부어야 하는데(정본 §5), 손으로 자르면 24칸이 24번의 눈대중이 된다.

어떻게 자르나 — **격자 좌표를 지어내지 않는다**. 시트는 「따뜻한 오프화이트 종이 + 얇은 칸 구분선」 규약이라
(정본 `docs/캐릭터보드_프롬프트_정본.md` §2 SHEET LAYOUT) 페이지 여백 색을 실측해 **종이색 띠(거터)를 찾아** 그 사이를 칸으로 본다.
행·열 수를 인자로 못 박지 않으므로 시트 A(3×3)·D(3×3)·E(3×2)·B(5×4) 모두 같은 코드로 잘린다.

9:16 마감: `--ratio 9:16`이면 잘라낸 칸을 그 비율로 **중앙 크롭**한다(무대 `yStage` 세로 규격 계승 · 좌우/상하만 깎는다).

사용:
  python3 shared/cut_board_sheet.py viewer/assets/yeta_char/board/ilzin_sheetE_p1.png \
      --labels GUM,NOPE,CASUAL,KISS,SCRATCH,KICK --out /tmp/cut --ratio 9:16
  python3 shared/cut_board_sheet.py <시트> --dry-run     # 자르지 않고 검출된 칸 좌표만 출력
"""
import argparse
import os
import sys

try:
    from PIL import Image
except ImportError:                                    # 게이트가 아니라 도구다 — 없으면 안내하고 조용히 빠진다
    sys.exit("Pillow가 필요하다: pip install pillow")

PAPER_TOL = 26          # 종이색으로 볼 채널 오차(±) — 실측: 시트 여백은 균일한 오프화이트 한 톤
PAPER_FRAC = 0.92       # 한 줄(행·열)이 거터로 인정되는 종이색 비율
MIN_PANEL = 0.06        # 칸으로 인정할 최소 폭·높이(페이지 대비) — 구분선 노이즈를 칸으로 오인하지 않게


def paper_colour(im):
    """페이지 여백 색 = 네 모서리 8×8의 중앙값(가장 안전한 실측 지점 = 바깥 여백)."""
    w, h = im.size
    px = []
    for x0, y0 in ((0, 0), (w - 8, 0), (0, h - 8), (w - 8, h - 8)):
        px += list(im.crop((x0, y0, x0 + 8, y0 + 8)).getdata())
    px.sort(key=lambda c: sum(c))
    return px[len(px) // 2]


def bands(im, paper, axis):
    """axis=0 → 열별, 1 → 행별로 '종이색 줄'을 판정해 (시작, 끝) 칸 구간 목록을 돌려준다."""
    w, h = im.size
    n, m = (w, h) if axis == 0 else (h, w)
    step = max(1, m // 240)                            # 세로(가로) 방향은 성기게 훑어도 판정이 안 흔들린다
    is_gutter = []
    for i in range(n):
        line = (im.crop((i, 0, i + 1, h)) if axis == 0 else im.crop((0, i, w, i + 1)))
        data = list(line.getdata())[::step]
        ok = sum(1 for c in data if all(abs(c[k] - paper[k]) <= PAPER_TOL for k in range(3)))
        is_gutter.append(ok >= PAPER_FRAC * len(data))
    out, start = [], None
    for i, g in enumerate(is_gutter):
        if not g and start is None:
            start = i
        elif g and start is not None:
            out.append((start, i)); start = None
    if start is not None:
        out.append((start, n))
    return [(a, b) for a, b in out if (b - a) >= MIN_PANEL * n]


def centre_crop(im, ratio):
    """비율 문자열('9:16')로 중앙 크롭 — 넘치는 축만 깎는다(늘리지 않는다 = 인물 왜곡 0)."""
    rw, rh = (int(v) for v in ratio.split(":"))
    w, h = im.size
    if w * rh > h * rw:                                # 가로가 넘침 → 좌우를 깎는다
        nw = int(round(h * rw / rh)); x = (w - nw) // 2
        return im.crop((x, 0, x + nw, h))
    nh = int(round(w * rh / rw)); y = (h - nh) // 2    # 세로가 넘침 → 위아래를 깎는다
    return im.crop((0, y, 0 + w, y + nh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--out", default="cut")
    ap.add_argument("--labels", default="", help="칸 라벨 쉼표 목록(좌→우·위→아래 순서). 없으면 01,02…")
    ap.add_argument("--prefix", default="", help="파일명 앞머리(기본 = 시트 파일명)")
    ap.add_argument("--ratio", default="", help="예: 9:16 — 잘라낸 칸을 이 비율로 중앙 크롭")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    im = Image.open(a.sheet).convert("RGB")
    paper = paper_colour(im)
    cols, rows = bands(im, paper, 0), bands(im, paper, 1)
    print(f"{os.path.basename(a.sheet)} {im.size[0]}×{im.size[1]} · 종이색 {paper} · 열 {len(cols)} × 행 {len(rows)} = 칸 {len(cols)*len(rows)}")
    labels = [s.strip() for s in a.labels.split(",") if s.strip()]
    prefix = a.prefix or os.path.splitext(os.path.basename(a.sheet))[0]
    if not a.dry_run:
        os.makedirs(a.out, exist_ok=True)
    n = 0
    for r, (y0, y1) in enumerate(rows):
        for c, (x0, x1) in enumerate(cols):
            lab = labels[n] if n < len(labels) else f"{n + 1:02d}"
            n += 1
            cell = im.crop((x0, y0, x1, y1))
            if a.ratio:
                cell = centre_crop(cell, a.ratio)
            print(f"  {lab:<8} ({x0},{y0})-({x1},{y1}) → {cell.size[0]}×{cell.size[1]}")
            if not a.dry_run:
                cell.save(os.path.join(a.out, f"{prefix}_{lab.lower()}.png"))
    if labels and n != len(labels):
        print(f"⚠️ 칸 {n}개인데 라벨 {len(labels)}개 — 격자 검출이 어긋났을 수 있다(--dry-run으로 좌표 확인)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
