# 강의 자료 — apt_lottery

> 완성되면 **웹앱으로 낸다**: `mk-slide-content`로 내용 설계 → `class_slide_apple`로 슬라이드 덱 HTML. 보고서는 `design/report-template.html` 사용.
> 최초 생성: 2026-07-15 · 7단 작성: 2026-07-15
> 상세 따라하기 문서: `docs/강의-청약하네스-따라만들기.md` (복붙용 전체 코드 포함) · 웹 버전: `docs/청약하네스-강의.html`

## 1. 목적 (Purpose)

수도권 아파트 청약정보를 매주 수집·분석해 개인 맞춤 추천이 포함된 HTML 리포트로 받아본다.

청약은 정보가 청약홈에 흩어져 있고, 마감일을 놓치면 그걸로 끝이다. 매주 수백 건의 공고를 손으로 훑어 "내가 넣을 수 있고 수도권이고 아직 안 닫힌 것"만 골라내는 일은 반복적이지만 빠뜨리면 손해가 크다. 이 프로젝트는 그 작업을 채팅 한 줄로 대체한다.

동시에 이 프로젝트는 **하네스(harness) 패턴의 교보재**다. 여러 AI 에이전트와 스킬을 파일 기반 파이프라인으로 엮어 한 마디 명령으로 전체를 굴리는 구조를, 실제로 돈이 걸린 도메인에서 end-to-end로 검증했다.

## 2. 결과물 (Deliverables)

- **`reports/청약리포트_{YYYY-MM-DD}.html`** — 최종 산출물. 자기완결 HTML(외부 의존 0), 마감임박 배지·신규공고 카드·유형별 정리·개인 맞춤 TOP 추천
- **오케스트레이터 스킬 1개** — `.claude/skills/apt-subscription-report/` (파이프라인 지휘)
- **서브에이전트 4명** — `.claude/agents/`: collector(수집) → analyst(분석) → advisor(맞춤, 선택) → reporter(HTML)
- **작업 스킬 4개** — `.claude/skills/`: subscription-collect / analyze / match / report-html
- **파이썬 수집기** — `subscription-collect/scripts/fetch_subscriptions.py` (청약홈 5개 엔드포인트 페이징 전량 수집, 4방식 자동 인증)
- **청약 지식베이스** — `subscription-match/references/청약-지식베이스.md` (자격·가점·전략 + 2025~2026 개정 §8)
- **개인 프로필 스키마** — `profile.example.yaml` (실제 `profile.yaml`은 개인정보라 커밋 제외)

라이브 검증 결과(2026-07-10): 318건 수집 → 수도권 27건 리포트.

## 3. 동작 원리 (How it works)

사용자가 "청약 리포트 만들어줘"라고 치면 오케스트레이터가 서브에이전트를 순서대로 호출한다. 에이전트끼리 대화하지 않고 **`_workspace/`의 JSON 파일로 배턴을 넘긴다** — 이게 이 구조의 핵심이다. 앞 단계가 파일을 남기면 뒷 단계가 그 파일만 읽고 이어서 일한다.

```
"청약 리포트 만들어줘"
        │
        ▼
  오케스트레이터 (apt-subscription-report 스킬) ── 순서 지휘
        │
        ▼
 [청약홈 공식 API]  api.odcloud.kr — 5개 엔드포인트
        │  APT일반 · 무순위/잔여 · 오피스텔/생숙 · 공공지원임대 · 임의공급
        ▼
 collector ──▶ 01_collector_*.json     (원본 그대로 저장, 판단 없음)
        │
        ▼
 analyst  ──▶ 02_analyst_summary.json  (수도권 필터 · 마감 D-day · 유형별 분류)
        │
        ▼
 advisor  ──▶ 03_match_personal.json   (profile.yaml 있을 때만 — 자격·전략 매칭)
        │
        ▼
 reporter ──▶ reports/청약리포트_날짜.html   ← 최종 결과물
```

책임 분리가 설계의 전부다. collector는 **수집만**(원본 보존, `_house_type` 라벨만 부가), analyst는 **해석만**(필드 매핑·필터·D-day), reporter는 **전달만**(새 판단 금지). 유형이 늘어도 collector는 안 깨지고, 디자인을 바꿔도 데이터 로직은 그대로다.

D-day 판정: 마감일−기준일 ≤3일 `긴급`, ≤7일 `임박`, 과거면 `마감`, 그 외 `일반`.

## 4. 작업 프롬프트 (Prompts)

**① 하네스를 통째로 만들게 하는 프롬프트** (헤맨 구간의 정답이 이미 박혀 있음 — 이게 최단 경로):

```
수도권 아파트 청약 주간 리포트 하네스를 만들어줘.

[데이터 소스] 청약홈 분양정보 조회 서비스를 MCP 말고 공식 API로 직접 호출해.
  Base: https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1
  엔드포인트 5개: getAPTLttotPblancDetail(APT일반), getRemndrLttotPblancDetail(무순위/잔여),
  getUrbtyOfctlLttotPblancDetail(오피스텔/생숙), getPblPvtRentLttotPblancDetail(공공지원임대),
  getOPTLttotPblancDetail(임의공급).
  인증키는 .env의 ODCLOUD_SERVICE_KEY. 키 형태(Encoding/Decoding)를 몰라도 되게
  serviceKey 쿼리→401이면 Authorization 헤더로 자동 재시도하게 해.
  cond[RCRIT_PBLANC_DE::GTE]로 최근 90일만, 페이징으로 전량 수집.

[구조] 오케스트레이터 스킬 1개 + 서브에이전트 4개(collector→analyst→reporter, 파일 기반 핸드오프).
  collector는 원본 그대로 저장만, 수도권 필터·마감 D-day 계산은 analyst가, HTML은 reporter가.
  결과는 reports/청약리포트_날짜.html 자기완결 HTML.

harness 스킬 써서 에이전트·스킬 파일들을 만들어줘.
```

**② 매주 실행** — 이 한 마디가 전부:

```
청약 리포트 만들어줘
```

**③ 부분 재실행** — 오케스트레이터가 어느 단계만 다시 돌릴지 판단한다:

```
청약정보 업데이트
리포트 디자인만 다시 만들어줘
마감기준 D-5로 바꿔줘
```

**④ 개인 맞춤 켜기** — `profile.yaml`을 만들면 리포트 최상단에 "🎯 내 조건 맞춤" 섹션이 붙는다:

```
profile.example.yaml 보고 내 조건으로 profile.yaml 만들어줘.
무주택세대주, 신혼부부, 청약통장 5년, 관심지역 서울·경기, 목적은 실거주.
```

## 5. 해야 할 것 (Do ✅)

- **공식 API를 직접 호출한다.** MCP 래퍼를 거치지 않는다 (401 + 필터 사용 불가).
- **인증은 폴백 체인으로 짠다.** 키 형태를 추측하는 대신 4방식을 순서대로 시도 → 아무 키나 넣어도 동작.
- **수집과 해석의 책임을 분리한다.** collector는 원본 보존, 해석은 analyst. 유형 추가에 강해진다.
- **에이전트 핸드오프는 파일로 한다.** `_workspace/{순번}_{에이전트}_{산출물}.json`. 각 파일이 다음 단계에 완결적이어야 한다.
- **실패를 리포트에 노출한다.** 인증 실패·데이터 누락은 `notes`로 끝까지 전달해 화면에 띄운다.
- **규제 면책을 추천 카드마다 붙인다.** 전매제한·실거주의무·투기과열지구·특공 소득기준은 시점마다 바뀐다 → "청약홈/뉴홈 원문에서 최신 확인".
- **비밀은 `.env`에만.** `profile.yaml`은 개인정보라 `.gitignore`. 공유는 `profile.example.yaml`로.
- **작업 시작 전 `docs/ERRORS.md`를 읽는다.** 해결한 에러를 다시 겪지 않기 위함.

## 6. 하지 말아야 할 것 (Don't ❌)

- **성공한 척하지 않기.** 키가 없거나 401이면 `auth_ok:false`를 남긴다. 빈 리포트를 정상인 양 내지 않는다.
- **없는 값을 지어내지 않기.** 원천에 없으면 "정보 없음". 경쟁률·가점은 별도 서비스라 미연동 → 빈 표 대신 안내 문구.
- **첫 페이지만 보고 멈추지 않기.** 페이징으로 전량 수집해야 한다.
- **판별 불가를 버리지 않기.** 수도권 여부가 애매하면 `unclassified`로 보존. 날짜 파싱 실패는 `date_unparsed` 플래그로 남긴다.
- **자격을 단정하지 않기.** advisor는 1차 선별이지 판정이 아니다. "지원 가능 후보 + 원문 확인"으로 표현.
- **reporter가 데이터를 새로 판단하지 않기.** 전달이 책임이지 해석이 아니다.
- **수집 단계에서 필드를 정규화하지 않기.** 유형이 늘 때마다 수집기가 깨진다.

## 7. 자주 발생하는 에러 (Common Errors)

> 출처: `docs/ERRORS.md` (재발방지 가치가 큰 항목 요약)

| 증상 | 원인 | 해결 |
|------|------|------|
| 요청이 계속 HTTP 401 | MCP 래퍼로 붙이려 함 — 인증 실패 + 날짜·유형 필터 사용 불가 | 공식 API(`api.odcloud.kr`)를 파이썬으로 직접 호출. MCP 안 씀 |
| 키를 넣어도 401 (Encoding? Decoding?) | 포털이 키를 2종 발급하는데 엔드포인트가 뭘 기대하는지 문서에 없음 | 수집기가 4방식(쿼리 quote/raw → 헤더 raw/unquote)을 자동 시도 → 아무 키나 OK |
| 주택명·마감일 파싱이 깨짐 | 유형마다 필드명이 다름(`RCEPT_ENDDE` vs `SUBSCRPT_RCEPT_ENDDE`…), 날짜 포맷도 dash/plain 혼재 | collector는 원본 저장만, 해석은 analyst. 마감은 "마감 성격 날짜 중 가장 늦은 값" |
| `서비스키 없음` | `.env`의 `ODCLOUD_SERVICE_KEY=` 뒤가 비어 있음 | 키를 붙여넣기 |
| 수집은 되는데 리포트가 비었다 | 최근 90일 수도권 신규 공고가 실제로 없을 수 있음 | `--lookback-days 180`으로 확대 |
| 경쟁률·가점 표가 비어 있다 | 정상 — 경쟁률은 분양정보와 **별도 서비스**라 미연동 | 리포트 안내 문구로 노출 중. 연동하려면 별도 엔드포인트 추가 |
| Claude가 스킬을 못 찾는다 | 경로·파일명 불일치 | `.claude/agents/`, `.claude/skills/` 위치와 파일명 대소문자 확인 |
