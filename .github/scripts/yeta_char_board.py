#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_char_board.py — 캐릭터 「감정 + 배경」 한 장 시트(캐릭터 보드) 생성 (운영자 260801 "감정 + 배경 한 페이지에 최대한 많이 · gpt로 · 캐릭터랑 느낌이 똑같아야 해").

기존 얼굴·초상 파이프(yeta_face.py / yeta_char_art.py)와 **별개 축** = 한 장에 여러 칸이 든 감정 시트(모델시트).
수동 dispatch 전용(⚠️ OpenAI 유료 종량제 · 자동 트리거 금지 = 이미지 파이프 공통 규약 · yeta-char-board.yml).

⚠ 프롬프트를 여기 적지 않는다 — 정본 = `docs/캐릭터보드_프롬프트_정본.md`의 `<!-- BOARD:* -->` 앵커 코드펜스.
  이 스크립트는 그걸 **읽어 조립**만 한다(문구 2벌 = 드리프트 씨앗 · 문구를 바꾸려면 md를 고친다).

레퍼런스 이미지가 있으면 `/v1/images/edits`(첨부 = 동일성 앵커), 없으면 `/v1/images/generations`(글 락만 — 「비슷」이지 「똑같이」가 아니다).
산출 = `viewer/assets/yeta_char/board/<slug>_sheet<A|B|C|D>[_v<n>].png`(+webp 768w) = git 정본(운영자 편집·칸 자르기 베이스).
멱등: 이미 있으면 skip(FORCE=1 재생성). 게이트 = OPENAI_API_KEY(없으면 no-op).
"""
import base64, json, mimetypes, os, re, shutil, subprocess, sys, time, urllib.request, uuid

KEY = os.environ.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY_nomute", "")
MODEL = (os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-2").strip()
API_GEN = "https://api.openai.com/v1/images/generations"
API_EDIT = "https://api.openai.com/v1/images/edits"
FORCE = os.environ.get("FORCE", "") == "1"
SHEET = (os.environ.get("YETA_BOARD_SHEET") or "A").strip().upper()      # A = 감정 9칸(3×3 · 앱 정합) · B = 감정 20칸(5×4) · C = 포즈 12칸(4×3 · 표정 고정) · D = 일진 상황 9칸(3×3) · E = 9:16 상황 6칸(3×2 · 칸 목록에서 6칸씩 · n장) · CELL = 개별 칸 1장씩(9:16 크롭)
SLUG = re.sub(r"[^0-9A-Za-z_-]", "", (os.environ.get("YETA_BOARD_SLUG") or "board")) or "board"
REF = (os.environ.get("YETA_BOARD_REF") or "").strip()                   # 레퍼런스 이미지 경로(있으면 edits 경로 = 동일성 앵커)
SPEC = os.environ.get("YETA_BOARD_SPEC") or "docs/캐릭터보드_프롬프트_정본.md"
try:
    TAKES = max(1, min(4, int(os.environ.get("YETA_BOARD_TAKES") or "1")))   # 여벌 테이크(고르는 건 운영자 · 2장째부터 _v2…)
except ValueError:
    TAKES = 1
OUT = "viewer/assets/yeta_char/board"
# 시트 비례 = 칸 3:4 기준 — A·D(3열×3행)·E(3열×2행 · 칸 9:16) → 세로 3:4 / B(5열×4행)·C(4열×3행) → 정사각.
# gpt-image 허용 size 3종뿐이라 **칸이 9:16이어도 페이지는 1024x1536**이다(칸 비례는 프롬프트가, 최종 9:16은 자를 때 성립).
SIZES = {"A": "1024x1536", "B": "1024x1024", "C": "1024x1024", "D": "1024x1536",
         "E": "1024x1536", "CELL": "1024x1536"}
PER_SHEET = 6          # 시트 E 한 장에 들어가는 칸 수(정본 §2-E · 9:16 칸 상한)
CROP_916 = "crop=trunc(ih*9/16/2)*2:ih"   # 개별 칸 전용 — 1024×1536 → 864×1536 = 정확히 9:16(좌우만 깎는다)


def spec_block(anchor):
    """정본 md에서 `<!-- BOARD:<anchor> ... -->` 다음 첫 코드펜스 본문을 뽑는다(문구 SSOT = md 1벌)."""
    if not os.path.exists(SPEC):
        raise SystemExit(f"프롬프트 정본 없음: {SPEC}")
    txt = open(SPEC, encoding="utf-8").read()
    m = re.search(r"<!--\s*BOARD:%s\b.*?-->\s*\n```[^\n]*\n(.*?)\n```" % re.escape(anchor), txt, re.S)
    if not m:
        raise SystemExit(f"{SPEC}에 BOARD:{anchor} 앵커+코드펜스가 없다(앵커를 지웠나?)")
    return m.group(1).strip("\n")


def cells():
    """§3-1 `CELLS_<SLUG>` 목록 파싱 — 한 줄 = 한 칸 · `라벨 :: 액션 :: 배경 :: 예외(선택)`."""
    out = []
    for ln in spec_block("CELLS_%s" % SLUG.upper()).split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        f = [p.strip() for p in ln.split("::")]
        if len(f) < 3 or not f[0]:
            raise SystemExit(f"칸 목록 형식 오류(' :: ' 3~4칸이어야 한다): {ln[:60]}…")
        out.append({"label": f[0], "act": f[1], "bg": f[2], "over": (f[3] if len(f) > 3 else "")})
    if not out:
        raise SystemExit(f"BOARD:CELLS_{SLUG.upper()} 목록이 비어 있다")
    return out


def build_prompt(sheet):
    lock = spec_block("LOCK")
    body = spec_block("SHEET_%s" % sheet)
    if "{LOCK}" not in body:
        raise SystemExit(f"BOARD:SHEET_{sheet} 블록에 {{LOCK}} 자리표시자가 없다")
    return body.replace("{LOCK}", lock)


def build_sheet_e(group):
    """시트 E = 템플릿 1벌 + 칸 목록 6개(§3-1)를 조립. 예외는 칸을 지목해 따로 문단으로 붙인다."""
    body = build_prompt("E")
    panels = "\n".join('%d. "%s" — %s. BG: %s.' % (i, c["label"], c["act"], c["bg"])
                       for i, c in enumerate(group, 1))
    ov = [f'Panel {i} ("{c["label"]}"): {c["over"]}' for i, c in enumerate(group, 1) if c["over"]]
    over = ("\nPER-PANEL EXCEPTIONS — each applies ONLY to the panel it names, never to the others\n"
            + "\n".join(ov) + "\n") if ov else ""
    return body.replace("{PANELS}", panels).replace("{OVERRIDES}", over)


def build_cell(c):
    """개별 칸 = §3 CELL 정본에 액션·배경·예외를 꽂는다(9:16 크롭은 생성 뒤 ffmpeg)."""
    body = spec_block("CELL").replace("{LOCK}", spec_block("LOCK"))
    over = ("\nEXCEPTION FOR THIS IMAGE\n" + c["over"] + "\n") if c["over"] else ""
    return body.replace("{OVERRIDE}", over).replace("{EXPRESSION}", c["act"]).replace("{BACKGROUND}", c["bg"])


def multipart(fields, files):
    """stdlib만으로 multipart/form-data 조립(requests 의존 0 · 레포 인라인 관례 계승)."""
    b = ("----yetaboard" + uuid.uuid4().hex).encode()
    out = bytearray()
    for k, v in fields.items():
        out += b"--" + b + b"\r\n"
        out += ('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode()
        out += str(v).encode() + b"\r\n"
    for k, path in files:
        name = os.path.basename(path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        out += b"--" + b + b"\r\n"
        out += ('Content-Disposition: form-data; name="%s"; filename="%s"\r\n' % (k, name)).encode()
        out += ("Content-Type: %s\r\n\r\n" % ctype).encode()
        out += open(path, "rb").read() + b"\r\n"
    out += b"--" + b + b"--\r\n"
    return bytes(out), "multipart/form-data; boundary=" + b.decode()


def _pick(d):
    b = d.get("b64_json")
    if b:
        return base64.b64decode(b)
    u = d.get("url")
    if u:
        with urllib.request.urlopen(u, timeout=120) as r2:
            return r2.read()
    return None


def openai_image(prompt, size, ref=""):
    """ref 있으면 edits(첨부 이미지 = 동일성 앵커) · 없으면 generations. 실패 1회 재시도 후 None(fail-soft = 파이프 관례)."""
    if ref and os.path.exists(ref):
        data, ctype = multipart({"model": MODEL, "prompt": prompt, "size": size, "n": 1}, [("image[]", ref)])
        req = urllib.request.Request(API_EDIT, data=data,
                                     headers={"Authorization": f"Bearer {KEY}", "Content-Type": ctype})
    else:
        req = urllib.request.Request(API_GEN,
                                     data=json.dumps({"model": MODEL, "prompt": prompt, "size": size, "n": 1}).encode(),
                                     headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                png = _pick((json.load(r).get("data") or [{}])[0])
            if png:
                return png
            print("  ⚠️ 이미지 파트 없음", flush=True)
            return None
        except Exception as e:
            print(f"  ⚠️ 생성 실패: {e}", flush=True)
            if attempt == 0:
                time.sleep(5); continue
    return None


def webp(path):
    """뷰어·채팅 전달용 webp 사본(768w·q82). ffmpeg 없으면 조용히 생략(png 원본 유지 · yeta_char_art.webp 계승)."""
    if not shutil.which("ffmpeg"):
        return
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", "scale=768:-2",
                        "-quality", "82", path[:-4] + ".webp"], check=True, timeout=180)
    except Exception as e:
        print(f"  ⚠️ webp 변환 실패(비치명): {e}", flush=True)


def crop916(path):
    """개별 칸 전용 — 좌우만 깎아 정확히 9:16으로. ffmpeg 없으면 원본(2:3) 유지(비치명)."""
    if not shutil.which("ffmpeg"):
        print("  ⚠️ ffmpeg 없음 — 9:16 크롭 생략(1024×1536 원본 유지)", flush=True); return
    tmp = path[:-4] + "_crop.png"
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vf", CROP_916, tmp],
                       check=True, timeout=180)
        os.replace(tmp, path)
    except Exception as e:
        print(f"  ⚠️ 9:16 크롭 실패(비치명): {e}", flush=True)


def jobs():
    """(파일경로, 프롬프트, 9:16크롭여부) 목록. 시트 E·CELL은 §3-1 칸 목록에서 자동 전개."""
    out = []
    for n in range(1, TAKES + 1):
        tag = "" if n == 1 else f"_v{n}"
        if SHEET == "E":
            cs = cells()
            pages = [cs[i:i + PER_SHEET] for i in range(0, len(cs), PER_SHEET)]
            for k, g in enumerate(pages, 1):
                out.append((os.path.join(OUT, f"{SLUG}_sheetE_p{k}{tag}.png"), build_sheet_e(g), False))
        elif SHEET == "CELL":
            for c in cells():
                out.append((os.path.join(OUT, f"{SLUG}_cell_{c['label'].lower()}{tag}.png"), build_cell(c), True))
        else:
            out.append((os.path.join(OUT, f"{SLUG}_sheet{SHEET}{tag}.png"), build_prompt(SHEET), False))
    return out


def main():
    if not KEY:
        print("OPENAI_API_KEY 없음 — 캐릭터 보드 생성 생략(no-op)"); return 0
    if SHEET not in SIZES:
        print(f"⚠️ 알 수 없는 시트 '{SHEET}' — A · B · C · D · E · CELL 중 하나"); return 1
    size = SIZES[SHEET]
    if REF and not os.path.exists(REF):
        print(f"⚠️ 레퍼런스 경로 없음: {REF} — 글 락만으로 생성한다(동일성 보장 약함)", flush=True)
    todo = jobs()
    print(f"시트 {SHEET} · size {size} · slug {SLUG} · 레퍼런스 {'있음 ' + REF if REF and os.path.exists(REF) else '없음(generations)'} · 테이크 {TAKES} · 생성 대상 {len(todo)}장", flush=True)
    os.makedirs(OUT, exist_ok=True)
    made = 0
    for path, prompt, crop in todo:
        if os.path.exists(path) and not FORCE:
            print(f"skip {path}(기존)"); continue
        print(f"생성 {path} …", flush=True)
        png = openai_image(prompt, size, REF)
        if not png:
            continue
        open(path, "wb").write(png)
        if crop:
            crop916(path)
        webp(path)
        made += 1
        print(f"  ✓ {path} ({len(png)//1024}KB)", flush=True)
        time.sleep(2)
    print(f"완료 — 신규 {made}장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
