---
name: subscription-collect
description: 청약홈 분양정보 조회 서비스(odcloud stage 37000)와 청약접수 경쟁률·특별공급 신청현황 서비스(stage 36148)에서 APT·무순위/잔여·오피스텔/생활숙박·공공지원임대·임의공급 분양공고 + 주택형별 분양가·특공배정 + 경쟁률·당첨가점·특공신청현황을 직접 API로 수집한다. 번들 스크립트 2개(공고 목록 → 공고별 통계). 청약 데이터 수집·크롤링·긁어오기·경쟁률 가져오기 작업 시 사용.
---

# 청약 분양정보 수집 스킬 (직접 API)

한국부동산원 청약홈 **분양정보 조회 서비스**를 `api.odcloud.kr`로 직접 호출해 원천 데이터를 전량 수집한다. 수집만 하고 가공하지 않는다(필터·D-day·요약은 analyst).

## 왜 MCP 대신 직접 호출인가
- 공식 API는 서버측 필터(`cond[...::GTE]` 날짜, `SUBSCRPT_AREA_CODE` 지역)와 **5개 물건 유형 엔드포인트**를 모두 노출한다. MCP 래퍼는 이를 못 쓰고 401을 반환했다.
- 직접 호출로 인증·필터·유형을 우리가 제어한다.

## 수집 대상 (5개 엔드포인트)
Base: `https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1`

| 라벨 | 엔드포인트 | 내용 | 날짜포맷 |
|------|-----------|------|---------|
| APT_일반 | `getAPTLttotPblancDetail` | APT·민간사전청약·신혼희망타운 | YYYY-MM-DD |
| APT_무순위잔여 | `getRemndrLttotPblancDetail` | 무순위·잔여세대 | YYYY-MM-DD |
| 오피스텔생활숙박 | `getUrbtyOfctlLttotPblancDetail` | 오피스텔·도시형·민간임대·생활숙박 | YYYY-MM-DD |
| 공공지원민간임대 | `getPblPvtRentLttotPblancDetail` | 공공지원 민간임대 | YYYYMMDD |
| 임의공급 | `getOPTLttotPblancDetail` | 임의공급 | YYYYMMDD |

## 실행 방법 — 번들 스크립트
반복적·결정적 수집이므로 스크립트로 번들링되어 있다. 직접 도구를 하나씩 호출하지 말고 이걸 실행하라:

```bash
python .claude/skills/subscription-collect/scripts/fetch_subscriptions.py \
  --out _workspace --lookback-days 90
```

스크립트가 하는 일:
1. `ODCLOUD_SERVICE_KEY`를 환경변수 또는 프로젝트 루트 `.env`에서 읽는다.
2. 5개 엔드포인트를 `cond[RCRIT_PBLANC_DE::GTE]=(오늘-90일)`로 필터해 최근 공고만, **페이징으로 전량**(totalCount까지) 수집.
3. 인증은 serviceKey 쿼리 → 401이면 Authorization 헤더로 자동 재시도(키 형태 차이 흡수).
4. 각 유형 항목에 `_house_type` 라벨을 붙여 통합.

## 2단계 — 주택형별·경쟁률·당첨가점·특공신청현황 (`fetch_stats.py`)
공고 목록을 만든 뒤 **반드시 이어서** 실행한다. 분양가·면적·특공 배정(37000의 주택형별 Mdl)과 경쟁률·당첨가점·특공 신청현황(**경쟁률 서비스 36148**, `ApplyhomeInfoCmpetRtSvc`)을 공고별로 긁는다.

```bash
python .claude/skills/subscription-collect/scripts/fetch_stats.py --workspace _workspace --skip-not-started
```

- **같은 `ODCLOUD_SERVICE_KEY`로 두 서비스가 모두 호출된다**(2026-09-05 라이브 확인, 추가 활용신청 불필요).
- 경쟁률 서비스는 **날짜 필터가 없다** — `HOUSE_MANAGE_NO`+`PBLANC_NO` EQ 조회만 되므로 `01_collector_notices.json`의 공고를 순회하며 공고당 2~4회 호출한다(90일분 ≈ 300건 × ≤4 = 1,200회, 일 한도 4만의 3%).
- `--skip-not-started`: 접수 시작 전 공고는 경쟁률 계열 호출을 생략(값이 있을 리 없음). 주택형별은 항상 수집.
- 유형별 엔드포인트: APT_일반 = Mdl+Cmpet+Score+Spsply / 무순위잔여 = Mdl+Cmpet(+취소후재공급 폴백) / 오피스텔·공공임대·임의공급 = Mdl+Cmpet.
- **원본 그대로 저장**. `CMPET_RATE`가 `"(△15)"`(미달 15세대)·`"-"`·`null`(미집계)로 오는 표기 해석은 analyst 몫이다.
- 산출물 `01_collector_stats.json` — `{meta:{calls, by_type, errors, auth_ok, collected_at}, by_notice:{HOUSE_MANAGE_NO:{house_type, models, cmpet, score, spsply}}}`
- 경쟁률·가점은 **접수 종료 후**(가점은 당첨자 발표 후) 채워진다. 이번 주 신규 공고엔 없는 게 정상이며 `status`로 구분된다.

## 인증 키
- data.go.kr → 마이페이지 → 활용신청 현황의 인증키(Encoding 또는 Decoding)를 `.env`의 `ODCLOUD_SERVICE_KEY`에 넣는다.
- 포털 안내: "Encoding/Decoding 중 **구동되는** 키를 사용". 스크립트가 4가지 방식(쿼리 인코딩/원본, 헤더 원본/디코딩)을 자동 시도하므로 어느 형태를 넣어도 된다.
- 일 호출 제한 40000 — 주간 수집(수십~수백 건)에 충분.
- 키 미설정 시 스크립트는 `01_collector_meta.json`에 `auth_ok:false, error`를 남기고 종료(exit 2). 조용히 성공한 척하지 않는다.

## 산출물 (`_workspace/`)
- `01_collector_notices.json` — 5개 유형 통합 공고 `{count, items:[{..., _house_type}]}`
- `01_collector_{라벨}.json` — 유형별 원천(엔드포인트·totalCount·collected·pages)
- `01_collector_meta.json` — 기준일·lookback·유형별 건수·`auth_ok`·에러

## 지역 코드 참고
`SUBSCRPT_AREA_CODE`(청약 지역코드)는 `references/area-codes.md` 참조. 단, 본 스킬은 **날짜 필터만 서버측**에 걸고 수도권 선별은 analyst가 응답의 `SUBSCRPT_AREA_CODE_NM`/`HSSPLY_ADRES`로 하도록 위임한다(코드 오류 위험 회피). 대량이면 지역 필터를 서버측에 추가할 수 있다.

## 완료 기준
- 5개 유형 각각 `collected == totalCount`(페이징 누락 없음) 또는 에러가 meta에 기록됨
- `01_collector_notices.json` + 유형별 파일 + meta 생성
- `01_collector_stats.json` 생성(`fetch_stats.py`), meta.errors 가 비었거나 사유가 기록됨
- `auth_ok`가 true (키 정상)
