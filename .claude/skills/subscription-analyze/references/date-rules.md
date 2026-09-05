# 청약 일정 날짜 파싱 규칙

청약홈 공고 API는 일정 필드를 여러 형식으로 반환할 수 있다. 일관된 `YYYY-MM-DD`로 정규화하기 위한 규칙.

## 흔한 입력 형식
- `20260710` (YYYYMMDD) → `2026-07-10`
- `2026-07-10` → 그대로
- `2026.07.10` / `2026/07/10` → 구분자 통일
- 시각 포함(`2026-07-10 17:00`) → 날짜만 취함
- 빈 문자열 / `null` / `-` → 파싱 실패로 간주, `date_unparsed: true`

## D-day 계산
- `dday = (접수마감일 - 기준일)` 일수. 기준일 당일 마감이면 0 = `긴급`.
- 접수마감일이 없고 접수시작일만 있으면 D-day는 null, 태그는 `일반`(예정).
- 음수(이미 지남)면 `마감`.

## 엣지 케이스
- **당첨자 발표일/계약일**이 마감일보다 앞서는 등 순서가 뒤집힌 데이터 → 값은 보존하되 `notes`에 "일정 순서 이상: {주택명}" 기록. 임의 수정 금지.
- **다자녀/특별공급 등 복수 접수기간**이 한 공고에 섞인 경우 → 가장 늦은 마감일을 대표 마감으로 삼되, 원본을 항목에 보존.
- 연도가 없는 형식(MMDD만)은 파싱 실패 처리. 추측으로 연도를 붙이지 않는다.

## 확인된 실데이터 필드 매핑 (2026-07 검증)
청약홈 분양정보 응답의 실제 필드명:
- **주택명** `HOUSE_NM` · **위치** `HSSPLY_ADRES` · **지역명** `SUBSCRPT_AREA_CODE_NM`(서울/경기/인천)
- **접수 시작** `RCEPT_BGNDE` · **접수 마감** `RCEPT_ENDDE`(APT_일반)
- 무순위/잔여·기타 유형은 마감 필드가 `SUBSCRPT_RCEPT_ENDDE`/`GNRL_RNK*_ENDDE` 등으로 분산 → **마감 성격 날짜 중 가장 늦은 값**을 대표 마감으로.
- **당첨발표** `PRZWNER_PRESNATN_DE` · **계약** `CNTRCT_CNCLS_BGNDE`~`CNTRCT_CNCLS_ENDDE`
- **시공사** `CNSTRCT_ENTRPS_NM`(APT_일반만 존재) · **사업주체** `BSNS_MBY_NM` · **총공급세대** `TOT_SUPLY_HSHLDCO` · **공고URL** `PBLANC_URL` · **공고일** `RCRIT_PBLANC_DE`
- 시공사 없는 유형은 `builder:"정보 없음"` + `developer`(사업주체) 보존.
- 공공지원민간임대·임의공급 날짜는 원본 `YYYYMMDD` → `YYYY-MM-DD` 변환 필요.

## 유형별 접수 시작/마감 필드 (2026-09 실데이터)
| 유형 | 시작 | 마감 |
|------|------|------|
| APT_일반 | `RCEPT_BGNDE`, `SPSPLY_RCEPT_BGNDE`, `GNRL_RNK1_*_RCPTDE` | `RCEPT_ENDDE`, `SPSPLY_RCEPT_ENDDE`, `GNRL_RNK1/2_*_ENDDE` |
| APT_무순위잔여 · 임의공급 | `SUBSCRPT_RCEPT_BGNDE`, `GNRL_RCEPT_BGNDE`, `SPSPLY_RCEPT_BGNDE` | `SUBSCRPT_RCEPT_ENDDE`, `GNRL_RCEPT_ENDDE`, `SPSPLY_RCEPT_ENDDE` |
| 오피스텔생활숙박 · 공공지원민간임대 | `SUBSCRPT_RCEPT_BGNDE` | `SUBSCRPT_RCEPT_ENDDE` |
시작 = 가장 이른 값, 마감 = 가장 늦은 값. 공공지원민간임대의 상세구분 필드는 `HOUSE_DETAIL_SECD_NM`(철자 다름).

## 통계 파일 필드 (01_collector_stats.json, 2026-09 실데이터)
- **주택형별(APT/무순위/임의)**: `HOUSE_TY`("084.9543T"), `SUPLY_AR`, `SUPLY_HSHLDCO`(일반), `SPSPLY_HSHLDCO`(특공 합), `NWWDS/LFE_FRST/MNYCH/OLD_PARNTS_SUPORT/NWBB/YGMN/INSTT_RECOMEND_HSHLDCO`, `LTTOT_TOP_AMOUNT`(만원, `"62,342"`처럼 콤마 가능)
- **주택형별(오피스텔·공공임대)**: `TP`("76A"), `EXCLUSE_AR`, `SUPLY_AMOUNT`, `SUBSCRPT_REQST_AMOUNT`(청약금), 공공임대는 `GNSPLY_HSHLDCO` + `SPSPLY_NEW_MRRG/YGMN/AGED_HSHLDCO`
- **경쟁률**: `HOUSE_TY`, `SUPLY_HSHLDCO`, `REQ_CNT`, `CMPET_RATE`(숫자 · `"(△15)"`=미달15 · `"-"`/null=미집계), APT는 `SUBSCRPT_RANK_CODE`(1/2)·`RESIDE_SECD`(01 해당지역·02 기타지역·03 기타경기), 공공임대는 `SPSPLY_KND_NM`
- **당첨가점(APT)**: `LWET_SCORE`·`TOP_SCORE`·`AVRG_SCORE`(발표 전 `"-"`)
- **특공신청현황(APT)**: 배정 `*_HSHLDCO`, 접수 `CRSPAREA_*`(해당지역)·`CTPRVN_*`(기타경기)·`ETC_AREA_*`(기타지역), `SUBSCRPT_RESULT_NM`

## 원칙
데이터가 이상하면 **버리거나 조작하지 말고 보존 + notes 기록**. 리포트에서 사용자가 원본을 판단할 수 있어야 한다.
