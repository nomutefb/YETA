# tests/ — 회귀 하니스

| 하니스 | 대상 | 실행 | 소요 |
|---|---|---|---|
| `test_yeta_v3.py` | 러너 세션 로직(방·스레드·기억) | `python3 tests/test_yeta_v3.py` | 즉시(stdlib) |
| `test_backstack.js` | 뷰어 인앱 뒤로가기(백스택) | `node tests/test_backstack.js` | ~1.5분(실브라우저) |
| `test_face_base.py` | 초상 프롬프트 SSOT(BASE 3분할 무손실 · 3컷 시트 프레이밍) | `python3 tests/test_face_base.py` | 즉시(stdlib) |

---

## 1) `test_yeta_v3.py` — yeta_v3 세션 어댑터 회귀 + 대화 품질 스냅샷

> **대상**: `.github/scripts/yeta_v3.py`(러너 세션 로직 = 마이그레이션·방·스레드 선택 SSOT).
> **왜**: 이 로직이 "대화가 **어떤 방·페르소나·기억**으로 풀리는지"를 좌우하는데 회귀 테스트가 0이었다 → 리팩터 때 대화 품질이 **조용히** 바뀌어도 안 잡혔다. 이 테스트는 그 변화를 **전/후로 눈에 보이게** 만든다.
> **의존성 0**: pytest 불요 — 파이썬 stdlib만. `python3 tests/test_yeta_v3.py`.

## "대화 품질"을 어떻게 보나
`yeta_v3.py`는 LLM 답변 텍스트가 아니라 **대화의 뼈대**(어떤 방이 열리고, 어떤 페르소나가 나오고, 대기 중 유저가 무시되지 않고, 타 방 비밀이 안 새는지)를 정한다. 이 뼈대 = '풀린 대화 상태' 스냅샷 = 대화 품질의 관측 가능한 대리지표.

## 3층 방어
1. **스펙 불변식** (박제 아님 — docstring + JS 쌍둥이 `functions/api/yeta.js:migrateV3`에서 도출)
   - `멱등` 재마이그레이션이 세션 안 망침 · `턴무손실` 대화 안 사라짐 · `cur유효` · `방≤2` · `비밀누수차단`(`_others`에 턴 텍스트 없음).
2. **골든 스냅샷** — 시나리오별 '풀린 대화 상태'(cur·threads·pick·view)를 `yeta_v3_golden.json`에 박제. 코드가 바뀌면 **읽을 수 있는 before/after diff**로 노출 (예: `pick : 'a' → 'b'` = 풀리는 대화가 바뀜).
3. **parity** — JS `migrateV3` 실물을 추출·node로 실행해 PY와 대조(동형 붕괴 자동 포착). *알려진 차이 1건*: `null` 입력 — JS는 상류 `EMPTY()`가 처리(`migrateV3(null)=null`), PY는 인라인 골격. 문서화됨.

## 실행
```
python3 tests/test_yeta_v3.py            # 체크(불변식+골든) · rc=0 통과 / rc=1 회귀
python3 tests/test_yeta_v3.py --report   # 대화 품질 상태를 사람이 읽게 출력(전/후 눈으로)
python3 tests/test_yeta_v3.py --update   # 골든 재생성(= 의도된 변경 승인 · diff 확인 후에만)
python3 tests/test_yeta_v3.py --parity   # JS↔PY 동형 대조(node 필요)
```

## 전/후 워크플로
1. 로직 바꾸기 전 = 현재 골든이 **before**.
2. 바꾼 뒤 `python3 tests/test_yeta_v3.py` → 변화가 있으면 **after diff** 출력.
3. 그 diff가 **의도한 개선**이면 `--update`로 골든 갱신(=승인), **의도 안 한 회귀**면 코드 되돌림.
4. 사람이 통째로 보려면 `--report`(전 시나리오 상태를 라벨로).

## 시나리오(픽스처)
`01` 신규(null)·`02` v2단일→v3(대화 무손실)·`03` persona 무턴 엣지·`04` v3 멱등·`05` 다중방 FIFO(기아방지)·`06` invite 분기·`07` 타방 비밀누수차단.

## CI/커밋 게이트로 물리기(옵션)
`rc=1`이라 그대로 게이트에 걸 수 있다 — `shared/check_refs.py`에 한 줄 추가(하드 or WARN)하거나 워크플로로. 자동 부착은 운영자 승인 후(기틀 변경 = `[9]`). 참고: 사망/부활 로직은 JS(`functions/api/yeta.js`)라 이 PY 테스트 범위 밖 → JS측 테스트는 후속.


---

## 2) `test_backstack.js` — 인앱 뒤로가기(백스택) 실브라우저 회귀

> **대상**: `viewer/index.html`의 `navOpen`/`navBack`/`navSwap`/`navHome`/`popstate` 골격.
> **왜(260726 사고)**: 262차가 종료 확인 팝업을 폐지하며 **"홈에서 뒤로 1회 = 앱 밖"**을 계약으로 내걸었는데, 검증이 "팝업 0 · 에러 0"만 보고 **몇 번 눌러야 나가는지를 안 셌다**. 실제로는 2회였고(연쇄 감기의 착지 칸에서 멈춤) 뒤로 1회가 통째로 씹혔다 — 267차에서야 실측으로 잡혔다. **눈으로 보는 검증은 '횟수' 같은 걸 놓친다 → 기계가 세게 만든다.**

### 지키는 계약 8개
| | 계약 | 깨지면 |
|---|---|---|
| C1 | 종료 확인 팝업(`#yexit`) DOM 부재 | 262차 폐지분 부활 |
| C2 | 레이어 회수 우선 — 레이어 있으면 뒤로 = 최상단만 닫힘 | 뒤로 1회에 앱이 통째로 나감 |
| C3 | **고아 칸 N겹이어도 사용자 뒤로 1회에 앱 밖** | 뒤로가 씹힘(267차 이전 = 2회) |
| C4 | 감기 표식 누수 0 — 고아 칸 뒤 새 레이어는 그 레이어부터 회수 | 새 레이어가 건너뛰어짐 |
| C5 | `#yconfirm` 생존(열기·닫기·백스택 등재/회수) | `.yexit*` 골격 정본을 계승한 확인 팝업 동반 사망 |
| C6 | 챗 위 명함 모달(`navOpen('yvcf')`) = 뒤로 1회에 명함만 | 뒤 챗이 동반 종료 |
| C7 | JS 실에러 0 | — |

### 실행
```
node tests/test_backstack.js             # 체크 · rc=0 통과 / rc=1 회귀
node tests/test_backstack.js --report    # 각 단계의 스택·history 상태를 사람이 읽게
node tests/test_backstack.js --strict    # 브라우저 없으면 스킵 대신 실패(CI용)
```
- **의존성**: playwright(전역 설치분 자동 탐색) + chromium(`PLAYWRIGHT_BROWSERS_PATH`/`/opt/pw-browsers`). 둘 중 하나라도 없으면 **스킵 + rc=0** — 브라우저 없는 기기에서 커밋을 막지 않는다(`--strict`로 뒤집기).
- **서버는 자체 기동**한다(임의 포트 · `http-server` 등 외부 도구 불요). `api/yeta`는 실 `roster.json`을 주입해 목킹.

### 커밋 게이트와의 분업
1.5분짜리를 매 커밋에 붙이면 UI 작업이 답답해진다 → **가벼운 정적 게이트**를 `shared/check_refs.py:check_backstack_contract()`가 매 커밋 수행한다(popstate 3분기 생존 + 폐지분 부활 감시). 그 게이트가 걸리면 **이 하니스로 실증**해라. 의도된 리팩터라면 하니스를 먼저 통과시키고 게이트 기대를 갱신(사유 기록).

> ⚠ 초록 ≠ 전면 안전. 이 하니스는 **백스택 축만** 본다(디자인·렌더·러너는 각자 게이트).
