---
name: apt-subscription-report
description: 수도권 아파트 청약정보를 수집·분석·리포트하는 주간 파이프라인 오케스트레이터. 신규 모집공고 일정, 마감임박 알림, 경쟁률·가점 요약을 HTML 리포트로 낸다. 트리거 표현 — "청약 리포트 만들어줘", "이번 주 청약 정리해줘", "청약정보 업데이트", "청약 리포트 다시 실행/재실행/업데이트", "마감임박 청약 알려줘", "청약 경쟁률 정리", "수도권 청약 공고". 정기 실행(매주)의 실행 본체.
---

# 수도권 청약 주간 리포트 오케스트레이터

collector → analyst → reporter **서브 에이전트 파이프라인**을 조율해, 수도권 아파트 청약 주간 HTML 리포트를 만든다.

**실행 모드:** 서브 에이전트 파이프라인 (파일 기반 핸드오프). 각 단계는 `_workspace/`에 산출물을 남기고 다음 단계가 읽는다. 실시간 토론이 없는 순차 의존 작업이므로 팀 대신 파이프라인을 쓴다.

## Phase 0: 컨텍스트 확인 (초기/후속/부분 재실행 판별)
1. 프로젝트 루트에 `_workspace/` 존재 여부 확인.
2. 분기:
   - `_workspace/` 없음 → **초기 실행** (Phase 1부터 전체).
   - `_workspace/` 있음 + 사용자가 "새로/최신으로 다시" → **새 실행**. 기존 `_workspace/`를 `_workspace_prev/`로 이동 후 전체 재실행.
   - `_workspace/` 있음 + 사용자가 특정 부분만 요청(예: "리포트 디자인만 다시", "마감기준 D-5로") → **부분 재실행**. 해당 단계 에이전트만 재호출하고 앞 단계 산출물 재사용.

## Phase 1: 데이터 수집
`Agent` 도구로 `subscription-collector` 호출 (`model: "opus"`).
- 지시: `subscription-collect` 스킬의 번들 스크립트(`scripts/fetch_subscriptions.py --out _workspace --lookback-days 90`)로 5개 유형 분양공고를 직접 API 수집, `_workspace/01_collector_*.json` 저장.
- `run_in_background: false` (다음 단계가 결과에 의존).
- **인증 체크**: 반환된 meta의 `auth_ok`가 false면(키 미설정/401) 파이프라인을 계속 진행하되, Phase 4에서 사용자에게 `.env`의 `ODCLOUD_SERVICE_KEY` 설정을 안내한다.

## Phase 2: 분석·필터
`Agent` 도구로 `subscription-analyst` 호출 (`model: "opus"`).
- 지시: `subscription-analyze` 스킬로 `01_collector_*.json`을 읽어 수도권 필터·D-day·경쟁률 요약 → `_workspace/02_analyst_summary.json` 저장.
- 사용자가 필터/마감기준 커스텀을 줬으면 지시에 전달.

## Phase 3: 리포트 생성
`Agent` 도구로 `subscription-reporter` 호출 (`model: "opus"`).
- 지시: `subscription-report-html` 스킬로 `02_analyst_summary.json` → `reports/청약리포트_{날짜}.html` 생성.
- 반환: 저장 경로 + 핵심 요약(신규 N·임박 M).

## Phase 4: 사용자 보고
- 리포트 경로를 알려주고, 핵심 요약(신규 공고 수, 마감 임박 건, 최고 경쟁률 지역)을 3줄 이내로 브리핑.
- 데이터 누락·인증 실패가 있었으면 반드시 함께 알린다.

## 데이터 전달 프로토콜 (파일 기반)
- 중간 산출물은 `_workspace/`에 `{순번}_{에이전트}_{산출물}.json`으로.
- 최종 리포트만 `reports/`에 저장. `_workspace/`는 사후 검증·감사용으로 보존.

## 에러 핸들링
- 각 Phase 에이전트 실패 → 1회 재시도. 재실패 시 해당 단계 산출물 없이 다음으로 진행하되, 최종 리포트 `notes`에 누락을 명시.
- 인증(ODCLOUD 키) 실패 → 파이프라인을 멈추지 않고, "데이터 수집 실패" 안내 리포트를 만들어 사용자가 원인(키 미설정)을 알게 한다.
- 상충 데이터는 삭제하지 않고 출처·원본 병기.

## 정기 실행 (매주)
이 스킬 자체가 주간 실행 본체다. 자동 스케줄은 `schedule`(클라우드 크론) 또는 `loop` 스킬로 이 오케스트레이터를 매주 트리거하도록 등록한다. 사용자가 "매주 자동 실행 걸어줘"라고 하면 스케줄 등록을 안내/수행한다.

## 테스트 시나리오
- **정상 흐름**: 트리거 → 수집(공고 N건·통계) → 분석(수도권 M건·임박 K건) → HTML 리포트 생성 → 경로+요약 보고.
- **에러 흐름(인증 실패)**: collector가 error 반환 → analyst가 notes에 전파 → reporter가 "수집 실패" 안내 리포트 생성 → 사용자에게 키 설정 필요 안내.
- **부분 재실행**: "리포트 디자인만 다시" → Phase 3만 재실행, `02_analyst_summary.json` 재사용.
