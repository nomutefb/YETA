#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yeta_tts.py — 페르소나 음성 합성 SSOT (전화 yeta_call.sh + 무전기 yeta_chat.sh 공용 · 260704).

사용: python3 yeta_tts.py <persona> <text> <out.mp3>   (rc 0=성공 · 1=실패 — 호출부 fail-soft)

보이스 결정(프리미엄 우선):
  ① roster.json 해당 캐릭터 "voice" 필드
     - "el:<voice_id>"  = ElevenLabs 클론 보이스(⚠️유료 · 운영자 1분 샘플 → yeta-voice.yml 로 생성 = **프리미엄 캐릭터**)
     - "oa:<voice>"     = OpenAI 프리셋 고정
  ② 필드 없음 → OpenAI 프리셋 매핑(아래 VOICES · 페르소나별 보이스+톤 지시)
  ③ ELEVENLABS_API_KEY/OPENAI_API_KEY 둘 다 없음 → rc 1(무음)

env: ELEVENLABS_API_KEY · ELEVENLABS_TTS_MODEL(기본 eleven_multilingual_v2 — 한국어 클론 음색 보존이 1순위,
     저지연이 필요하면 vars 로 eleven_flash_v2_5) · OPENAI_API_KEY · OPENAI_TTS_MODEL(기본 gpt-4o-mini-tts) ·
     YETA_CALL_VOICE(OpenAI 보이스 강제 — 테스트용)
비용 축(운영자 260704 리서치): ElevenLabs = $5/월 30k자(≈월 100통) · OpenAI = 분당 ~$0.015 · 대안 = Fish($15/M자)/MiniMax($1.5/클론).
"""
import io, json, os, sys, time, urllib.request, urllib.error

ROSTER = "apps/yeta/characters/roster.json"

# 페르소나 → (OpenAI 보이스, 톤 지시) 폴백 매핑 — 클론 보이스(el:) 없을 때의 기본 음색(캐릭터 목소리 SSOT).
VOICES = {
    "desk":  ("onyx",    "낮고 단단한 40대 후반 남성, 냉철한 편집장. 건조하지만 말끝에 옅은 온기."),
    "kopi":  ("verse",   "장난기 있는 30대 남성 카피라이터. 리듬감 있게, 경쾌하고 시니컬하게."),
    "mudi":  ("sage",    "성별이 모호한 40대 찻집 주인. 낮고 아주 따뜻하게, 서두르지 않고."),
    "sera":  ("coral",   "열아홉 여자 아이돌 연습생. 퉁명스럽고 빠른데 말끝이 살짝 여려짐."),
    "haeun": ("shimmer", "30대 여자 국어교사. 능글맞고 장난스럽게, 웃음기 섞인 말끝."),
    "gaeul": ("nova",    "당당한 30대 여자 상인회장. 명령조인데 밉지 않게, 또렷하고 시원시원하게."),
    "baek":  ("ash",     "과묵한 저음의 40대 남성 경호원. 짧고 묵직하게, 감정 절제."),
    "ryu":   ("echo",    "나른한 40대 남성 검도 사범. 느긋하게 끄는 말투, 반쯤 웃는 톤."),
    "von":   ("onyx",    "절도 있는 40대 남성 체육관 관장. 군더더기 없이 힘 있고 간결하게."),
    "yun":   ("ballad",  "심야 라디오 DJ, 30대 남성. 낮고 느리게, 속삭이듯 부드럽게."),
}


def roster_voice(persona):
    try:
        for c in json.load(open(ROSTER, encoding="utf-8")):
            if c.get("id") == persona:
                return (c.get("voice") or "").strip()
    except Exception:
        pass
    return ""


def http(req, tries=2, timeout=120):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            print("  ⚠️ TTS HTTP {} — {}".format(e.code, e.read().decode()[:200]), flush=True)
            if e.code in (429, 500, 503) and attempt == 0:
                time.sleep(5); continue
            return None
        except Exception as e:
            print("  ⚠️ TTS 호출 실패: {}".format(e), flush=True)
            if attempt == 0:
                time.sleep(5); continue
            return None
    return None


def tts_elevenlabs(voice_id, text):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("  ⚠️ ELEVENLABS_API_KEY 없음 — 클론 보이스 스킵(OpenAI 폴백)"); return None
    model = os.environ.get("ELEVENLABS_TTS_MODEL", "").strip() or "eleven_multilingual_v2"
    payload = {"text": text, "model_id": model}
    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/text-to-speech/{}?output_format=mp3_44100_128".format(voice_id),
        data=json.dumps(payload).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    b = http(req)
    if b:
        print("  TTS ok — elevenlabs {} · voice {}".format(model, voice_id))
    return b


def tts_openai(persona, text, force_voice=""):
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("  ⚠️ OPENAI_API_KEY 없음 — TTS 스킵"); return None
    voice, instr = VOICES.get(persona, ("alloy", "차분한 대화 톤."))
    if force_voice:
        voice = force_voice
    model = os.environ.get("OPENAI_TTS_MODEL", "").strip() or "gpt-4o-mini-tts"
    payload = {"model": model, "voice": voice, "input": text, "response_format": "mp3",
               "instructions": "캐릭터 대사. 한국어로 자연스럽게. " + instr}
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech",
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    b = http(req)
    if b:
        print("  TTS ok — {} · voice {}".format(model, voice))
    return b


def main():
    if len(sys.argv) < 4:
        print("사용: yeta_tts.py <persona> <text> <out.mp3>"); return 1
    persona, text, out = sys.argv[1], sys.argv[2], sys.argv[3]
    if not text.strip():
        return 1
    v = roster_voice(persona)
    b = None; eng = ""
    if v.startswith("el:"):                      # 프리미엄 = 클론 보이스 우선
        b = tts_elevenlabs(v[3:], text)
        if b: eng = "el"                         # el = 44.1kHz mp3 · oa = 24kHz — 엔진 갈리면 raw 접합 불가(평의회 260714 오디오 HIGH)
    if not b and v.startswith("oa:"):
        b = tts_openai(persona, text, force_voice=v[3:])
        if b: eng = "oa"
    if not b:
        b = tts_openai(persona, text, force_voice=os.environ.get("YETA_CALL_VOICE", "").strip())
        if b: eng = "oa"
    if not b:
        return 1
    open(out, "wb").write(b)
    try: open(out + ".eng", "w").write(eng)      # 엔진 사이드카 — ptt_voice 헤드 접합 전 동일성 대조(불일치 = 전문 폴백) · 타 호출처엔 무해한 잉여 tmp
    except Exception: pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
