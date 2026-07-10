---
name: subscription-analyze
description: 수집된 청약 분양공고를 수도권 기준 필터링, 물건 유형별 분류, 접수 마감 D-day 계산, 신규공고 선별로 가공해 리포트용 구조화 JSON을 만든다. 청약 데이터 분석·필터링·마감임박 판정·유형별 정리 작업 시 사용.
---

# 청약 분석 스킬

collector의 raw JSON을 사용자가 실제로 쓸 수 있는 요약으로 가공한다. 핵심은 **수도권 필터 · 유형별 분류 · 마감 D-day · 신규공고 선별**이다.

## 입력
- `_workspace/01_collector_notices.json` (5개 유형 통합, 각 항목에 `_house_type`)
- `_workspace/01_collector_meta.json` (기준일·유형별 건수·auth_ok)
- (선택) `_workspace/01_collector_stats.json` — 경쟁률/가점. **별도 서비스**라 없을 수 있음(아래 참조).

## 1. 수도권 필터링
서버에서 날짜만 걸러왔으므로 지역 선별은 여기서 한다.
- 우선순위: 응답의 `SUBSCRPT_AREA_CODE_NM`(예: "서울"/"경기"/"인천") → 없으면 `HSSPLY_ADRES`(공급위치) 문자열에 서울·경기·인천 포함 여부.
- **판별 불가**(둘 다 비었거나 애매): 버리지 말고 `others.unclassified` 카운트로 보존. 임의 단정 금지.
- 필터 후에도 원본 위치·지역명을 항목에 보존.

## 2. 물건 유형별 분류
각 항목의 `_house_type`으로 그룹핑한다:
`APT_일반`, `APT_무순위잔여`, `오피스텔생활숙박`, `공공지원민간임대`, `임의공급`.
리포트는 유형별 섹션으로 나뉘므로, 유형 라벨과 건수를 유지한다.

## 3. 마감 임박(D-day) 판정
기준일(`base_date`)과 각 공고의 **접수 마감일**을 비교한다. 필드명은 유형마다 다를 수 있으니(예: `RCEPT_ENDDE`, `SUBSCRPT_RCEPT_ENDDE` 등) 마감 성격의 날짜를 식별해 쓴다.

| 조건 | 태그 |
|------|------|
| 마감일 - 기준일 ≤ 3일 (미경과) | `긴급` |
| 마감일 - 기준일 ≤ 7일 | `임박` |
| 마감일이 과거 | `마감` |
| 그 외 | `일반` |

- 날짜 파싱 실패는 버리지 말고 `date_unparsed:true`, D-day=null.
- `deadline_soon`에는 `긴급`+`임박`만, **D-day 오름차순**(급한 게 위), 유형 라벨 포함.

## 4. 신규 공고 선별
- `new_notices`: 접수 시작일이 최근 7일 이내이거나 접수 예정인 수도권 공고. 유형별로 묶는다.
- 각 항목: 주택명, 위치, 유형, 접수시작~마감, 당첨발표, 계약일, 시공/사업주체, 공급규모(있으면), D-day, 태그.
- 날짜는 모두 `YYYY-MM-DD` 정규화.

## 5. 경쟁률·가점 (별도 서비스 — 있을 때만)
경쟁률·가점 통계는 분양정보 서비스가 아니라 **별도 청약경쟁률 서비스**에서 온다. `01_collector_stats.json`이 있으면 수도권 지역별 평균/최고 경쟁률·가점을 요약한다. **없으면** `competition`을 빈 배열로 두고 `notes`에 "경쟁률·가점은 별도 서비스(청약경쟁률) 연동 필요"를 명시한다. 없는 데이터를 지어내지 않는다.

## 6. 주의사항 전달
- `meta.auth_ok`가 false이거나 유형별 error가 있으면 그 사실을 `notes`에 담아 리포트에 노출.
- 일정 순서 이상 등은 `notes`에 기록(세부 규칙 `references/date-rules.md`).

## 출력: `_workspace/02_analyst_summary.json`
```json
{
  "report_date": "2026-07-10",
  "counts": { "new": 5, "deadline_soon": 2, "closed": 3, "by_type": {"APT_일반":3,"APT_무순위잔여":1,"오피스텔생활숙박":1} },
  "deadline_soon": [ { "name":"...", "type":"APT_일반", "dday":3, "tag":"긴급", "apply_end":"...", "location":"서울 강동구" } ],
  "new_by_type": {
    "APT_일반": [ { "name":"...", "location":"...", "apply_start":"...", "apply_end":"...", "winner_date":"...", "contract_date":"...", "builder":"...", "supply_scale":"...", "dday":12, "tag":"일반" } ],
    "APT_무순위잔여": [ ... ], "오피스텔생활숙박":[...], "공공지원민간임대":[...], "임의공급":[...]
  },
  "competition": [],
  "others": { "unclassified": 2, "non_capital": 14 },
  "notes": [ "경쟁률·가점은 별도 서비스 연동 필요", "APT_무순위잔여 수집 0건" ]
}
```

## 완료 기준
- 수도권 필터 적용, 판별불가 보존
- 유형별 분류(`new_by_type`) 완성
- 모든 신규 공고에 D-day·태그·정규화 날짜
- `deadline_soon` D-day 오름차순
- 데이터 누락(auth·유형에러·경쟁률부재)이 `notes`에 반영
- reporter가 이 파일만으로 리포트 생성 가능
