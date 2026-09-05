---
name: subscription-analyze
description: 수집된 청약 분양공고를 수도권 기준 필터링, 물건 유형별 분류, 접수 마감 D-day 계산, 신규공고 선별, 규제 플래그·국민/민영 노출, 주택형별 분양가·특공배정·경쟁률·당첨가점·특공 신청현황 해석("(△15)"=미달)으로 가공해 리포트·웹앱용 구조화 JSON을 만든다. 청약 데이터 분석·필터링·마감임박 판정·경쟁률 정리·유형별 정리 작업 시 사용.
---

# 청약 분석 스킬

collector의 raw JSON을 사용자가 실제로 쓸 수 있는 요약으로 가공한다. 핵심은 **수도권 필터 · 유형별 분류 · 마감 D-day · 신규공고 선별 · 규제/국민·민영 노출 · 통계 해석(주택형·경쟁률·가점·특공)**이다.

## 실행 방법 — 번들 스크립트 (결정적 구현)
규칙이 유형별 필드명·표기 예외로 복잡해 매번 손으로 짜면 어긋난다. 아래 스크립트가 이 문서의 규칙 전부를 구현한다. **직접 파싱 코드를 새로 쓰지 말고 이걸 실행하라.** 규칙을 바꾸면 이 문서와 스크립트를 함께 고친다.

```bash
python .claude/skills/subscription-analyze/scripts/analyze.py --workspace _workspace
```

실행 후 analyst가 할 일: 출력 요약과 `notes`를 읽고 이상(0건·파싱 실패 다수·통계 없음)을 확인해 오케스트레이터에 보고한다. 사용자 커스텀(예: "마감 기준 D-5")은 스크립트 상수를 고쳐 재실행한다.

## 입력
- `_workspace/01_collector_notices.json` (5개 유형 통합, 각 항목에 `_house_type`)
- `_workspace/01_collector_meta.json` (기준일·유형별 건수·auth_ok)
- `_workspace/01_collector_stats.json` (공고별 주택형·경쟁률·가점·특공신청현황). **없으면** 통계 없이 진행하고 notes에 명시.

## 1. 수도권 필터링
서버에서 날짜만 걸러왔으므로 지역 선별은 여기서 한다.
- 우선순위: `SUBSCRPT_AREA_CODE_NM`(서울/경기/인천) → 없으면 `HSSPLY_ADRES` 접두(서울특별시·경기도·인천광역시).
- **판별 불가**: 버리지 말고 `others.unclassified` 카운트로 보존. 임의 단정 금지. `region_source`로 근거를 남긴다.

## 2. 물건 유형별 분류
`_house_type`으로 그룹핑: `APT_일반`, `APT_무순위잔여`, `오피스텔생활숙박`, `공공지원민간임대`, `임의공급`.

## 3. 마감 임박(D-day) 판정
접수 시작 = 시작 성격 필드 중 **가장 이른** 날짜, 접수 마감 = 마감 성격 필드 중 **가장 늦은** 날짜(필드명은 유형마다 다름 — `references/date-rules.md`).

| 조건 | 태그 |
|------|------|
| 마감일 - 기준일 ≤ 3일 (미경과) | `긴급` |
| 마감일 - 기준일 ≤ 7일 | `임박` |
| 마감일이 과거 | `마감` |
| 그 외 | `일반` |

- 파싱 실패는 `date_unparsed:true`, D-day=null, `일반`.
- `deadline_soon`에는 `긴급`+`임박`만, **D-day 오름차순**.
- **D-day는 기준일 계산값**이다. 리포트·웹앱은 표시 시점에 `apply_end`로 재계산해야 한다(스냅샷 경과 시 마감 공고가 추천되는 사고 — ERRORS 2026-07-15).

## 4. 진행/예정 공고 (`new_by_type`)
마감되지 않은 수도권 공고 **전부**를 유형별로 담는다(웹앱이 이걸 그대로 쓴다). 접수 시작이 최근 7일 이내이거나 예정이면 `is_new:true`.
각 항목: `id`(HOUSE_MANAGE_NO)·주택명·위치·지역·유형·접수시작~마감·당첨발표·계약일·시공/사업주체·공급규모·URL·D-day·태그, 그리고 아래 5~6의 확장 필드.

## 5. 규제 플래그·국민/민영 (APT_일반)
분양정보 응답에 이미 들어있는 값을 **그대로 노출**한다(추측 금지, 최신 확인 문구는 유지):
- `house_dtl`: `HOUSE_DTL_SECD_NM` → "국민"/"민영". advisor의 국민/민영 경로 판정은 **이 값을 우선** 쓴다(프로필 통장 성향은 보조).
- `regulation`: `speculation_zone`(투기과열지구 `SPECLT_RDN_EARTH_AT`) · `adjusted_area`(조정대상 `MDAT_TRGET_AREA_SECD`) · `price_cap`(분양가상한제 `PARCPRC_ULS_AT`) · `public_housing_zone`/`public_housing_law`/`redevelopment`/`large_site`. 값은 true/false/null(정보 없음).
- `is_public`: 국민(03) + 공공주택특별법 적용(Y) → 청년·신생아 특공 배정이 유효한 공공주택.
- `special_apply`: 특공 접수 시작~마감.

## 6. 통계 해석 (`01_collector_stats.json` 있을 때)
### 주택형별 → `models[]`, `price_range_manwon`, `areas`, `strategy_signals[]`
- `HOUSE_TY` `"084.9543T"` → `area` 84.95 · `suffix` "T". 오피스텔·공공임대는 `TP`("76A") + `EXCLUSE_AR`.
- 분양가 `LTTOT_TOP_AMOUNT`(APT/무순위/임의, **콤마 포함 문자열 가능** `"62,342"`) 또는 `SUPLY_AMOUNT`(오피스텔·공공임대). 단위 만원.
- 특공 배정: 신혼·생애최초·다자녀·노부모·신생아·청년·기관추천 세대수(APT). 공공임대는 신혼/청년/고령자.
- **빈집털이 신호(지식베이스 §6)**: 타워형(T) · 뒷알파벳(C 이후) · 애매평형(59·84 벗어남) · 소수세대(≤10). 신호일 뿐 판정이 아니다.

### 경쟁률 → `result`
- `status`: `없음`(통계 미수집) · `미집계`(접수 전/집계 전: `CMPET_RATE`가 `null`/`"-"`) · `집계`.
- `CMPET_RATE` 표기 규칙: 숫자 문자열 → 경쟁률 · **`"(△15)"` → 미달 15세대(경쟁률 0)** · `"-"`/`null` → 미집계. 명세에 없는 표기이므로 정규식으로 잡는다.
- 주택형별 `models[{ty, supply, req, rate_max, short, rank1_local}]`, `max_rate`, `undersubscribed[{ty, short}]`, `total_req`.
- APT 당첨가점 `score[{ty, reside, lwet, avg, top}]`, `min_lwet`(발표 전엔 `"-"`라 없음).
- APT 특공 신청현황 `special{유형:{alloc, req, rate}}` — 유형별 접수건수(해당+기타경기+기타지역 합) ÷ 배정세대. **advisor가 프로필 세대유형과 직접 대조하는 값**. `special_status`(예: "청약접수 종료").

### `competition[]`
접수 종료된 수도권 공고 중 `status=집계`인 것, 마감일 내림차순. 리포트 "지난 접수 결과" 표와 advisor의 유사단지 참고치로 쓴다. 지역 평균이 아니라 **단지별 결과**다(평균은 소수 대형 단지에 왜곡됨).

## 7. 주의사항 전달 (`notes`)
- `meta.auth_ok` false·유형별 error·통계 없음·파싱 실패 건수·통계 수집 시각·"접수건수는 은행 전산 사후 변동 가능"을 담아 리포트에 노출.
- D-day 재계산 경고를 항상 포함.

## 출력: `_workspace/02_analyst_summary.json`
```json
{
  "report_date": "2026-09-05",
  "counts": { "new": 17, "deadline_soon": 12, "closed": 182, "open_capital": 17, "by_type": {"APT_일반":84, "...":0} },
  "deadline_soon": [ { "id":"2026000400", "name":"...", "type":"APT_일반", "dday":3, "tag":"긴급", "apply_end":"...", "region":"서울",
                       "house_dtl":"민영", "regulation":{"speculation_zone":false,"adjusted_area":false,"price_cap":true},
                       "price_range_manwon":[55000,60900], "areas":[59.9,84.6], "models":[...], "strategy_signals":[{"ty":"084.7673C","why":["뒷알파벳(C)"]}],
                       "result":{"status":"미집계"} } ],
  "new_by_type": { "APT_일반": [...], "APT_무순위잔여": [...], "오피스텔생활숙박":[...], "공공지원민간임대":[...], "임의공급":[...] },
  "competition": [ { "name":"...", "type":"APT_일반", "region":"인천", "apply_end":"2026-09-02",
                     "result":{"status":"집계","max_rate":262.0,"undersubscribed":[],"total_req":3100,
                               "special":{"신혼부부":{"alloc":30,"req":380,"rate":12.66},"노부모부양":{"alloc":13,"req":10,"rate":0.77}}} } ],
  "others": { "unclassified": 0, "non_capital": 84 },
  "notes": [ "경쟁률 집계 완료 169건 …", "D-day 는 기준일 계산값 — 표시 시점 재계산" ]
}
```

## 완료 기준
- 수도권 필터 적용, 판별불가 보존
- 유형별 분류(`new_by_type`) 완성, 각 항목에 D-day·태그·정규화 날짜·`id`
- APT_일반에 `house_dtl`·`regulation`; 통계 있으면 `models`·`price_range_manwon`·`result`
- `deadline_soon` D-day 오름차순, `competition` 마감일 내림차순
- 데이터 누락(auth·유형에러·통계부재)이 `notes`에 반영
- reporter·webapp이 이 파일만으로 산출물 생성 가능
