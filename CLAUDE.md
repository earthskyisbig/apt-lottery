# apt_lottery — 수도권 아파트 청약정보 자동화

## 하네스: 수도권 청약 주간 리포트

**목표:** 수도권 아파트 청약(신규 모집공고·마감임박·경쟁률/가점)을 매주 수집·분석해 HTML 리포트로 받아본다.

**트리거:** 청약 리포트·청약정보 업데이트·마감임박·경쟁률 정리 등 청약 관련 작업 요청 시 `apt-subscription-report` 스킬(오케스트레이터)을 사용하라. 단순 질문("이번 달 공고 몇 건?")은 직접 응답 가능.

**실행 방식:** 현재 **수동 트리거**("청약 리포트 업데이트"). 자동 스케줄러 미설정. **향후: 텔레그램 연동 검토 중**(리포트 요약을 텔레그램으로 발송 → 알림 봇/웹훅 추가 시 reporter 뒤에 발송 에이전트 붙이는 방향).

**구성:** 서브 에이전트 파이프라인 — collector → analyst → (advisor, profile.yaml 있을 때) → reporter (`.claude/agents/`, `.claude/skills/`). 매주 정기 실행은 `schedule`/`loop`로 오케스트레이터를 트리거.

**산출물 2종:** ①**주간 리포트**(`reports/청약리포트_날짜.html`) — 이번 주 전체를 훑는 용도, reporter 담당. ②**자격진단 웹앱**(`reports/청약자격진단.html`) — 자격요건을 폼에 입력하면 브라우저에서 즉시 맞춤 결과, `subscription-webapp` 스킬 담당(`scripts/build_webapp.py`로 데이터 주입). 웹앱은 서버 없이 파일 하나로 동작하고 입력값이 브라우저 밖으로 나가지 않는다. **주의: 매칭 규칙이 `subscription-match`(문서)와 웹앱 JS 두 곳에 있다 — 규칙 변경 시 반드시 양쪽을 함께 고칠 것.** D-day 등 기준일 파생값은 데이터에 박제하지 말고 표시 시점에 계산한다(마감 공고 추천 사고 재발방지).

**개인 맞춤:** `profile.yaml`(개인 조건: 주택수·세대유형·청약통장·소득·목적·배우자통장·비아파트보유)을 세팅하면 advisor가 자격·전략·수익 관점으로 "내 조건 맞춤 청약"을 압축 추천(리포트 최상단). 파일을 만들기 싫으면 **자격진단 웹앱**에 같은 조건을 폼으로 입력하면 된다. 지식베이스는 `subscription-match/references/청약-지식베이스.md`(강의 2024 + **2025~2026 개정 §8 반영**: 25만원 인정한도·비아파트 무주택 완화·통장전환 기한·부부 중복청약·실거주의무 충돌). 규제는 최신 확인 전제. profile.yaml은 개인정보라 커밋 제외(`profile.example.yaml`만 공유).

**데이터 소스:** 청약홈 **분양정보 조회 서비스**(api.odcloud.kr, stage 37000: 공고 상세 + 주택형별 분양가·특공배정) + **청약접수 경쟁률·특별공급 신청현황 조회 서비스**(stage 36148: 주택형별 경쟁률·당첨가점·특공 유형별 신청현황). 인증키는 프로젝트 루트 `.env`의 `ODCLOUD_SERVICE_KEY` **하나로 두 서비스 모두 호출**(2026-09-05 확인). 수집 유형: APT 일반·무순위/잔여·오피스텔/생활숙박·공공지원임대·임의공급. 경쟁률 서비스는 날짜 필터가 없어 공고별 EQ 조회(`fetch_stats.py`, 공고당 2~4회). 미달 표기 `"(△N)"`은 analyst가 해석. 규제 플래그(투기과열·조정대상·상한제)·국민/민영은 API 값을 그대로 노출하되 "최신 확인" 문구 유지. 분석은 `subscription-analyze/scripts/analyze.py`로 결정적 실행.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-10 | 초기 구성 (3-에이전트 파이프라인 + 오케스트레이터) | 전체 | - |
| 2026-07-10 | MCP→공식 API 직접 연동 전환, 5개 물건유형 확장, 번들 수집 스크립트 추가 | collect 스킬·collector·analyst·reporter·orchestrator | 사용자가 공식 청약홈 분양정보 API 스펙+서비스키 제공, MCP 401 |
| 2026-07-10 | 라이브 검증 완료(318건 수집→수도권 27건 리포트), 필드매핑 확정, 인증 4방식 폴백 | 전체 | 실데이터 end-to-end 검증 |
| 2026-07-10 | 개인 맞춤 매칭 추가: advisor 에이전트 + subscription-match 스킬(지식베이스·프로필 스키마) + profile.example.yaml, 리포트 최상단 맞춤 섹션 | agents/subscription-advisor·skills/subscription-match·reporter·orchestrator·gitignore | 강의 4강(청약 자격·가점·전략·안전마진) 반영, 개인 조건 세팅 요청 |
| 2026-07-10 | 규제 면책 문구를 모든 추천 카드에 일괄 적용(전매·실거주·투기과열지구·소득기준 시점변동 → 원문 최신확인) | skills/subscription-match·subscription-report-html | 규제는 시점마다 바뀌므로 추천 건마다 최신확인 명시 요청 |
| 2026-07-15 | workspace-init 표준 적용(WORKLOG·ERRORS·LECTURE·db/DuckDB·design), `.gitignore`에 `data/*.duckdb` 추가 | docs·db·design·gitignore | 프로젝트 표준 부트스트랩 |
| 2026-07-15 | **자격진단 웹앱 추가** — `subscription-webapp` 스킬(정적 HTML+브라우저 계산, 폼 입력→맞춤 결과). 매칭 규칙(§3·§5·§8)을 JS로 이식 | skills/subscription-webapp·CLAUDE | 강의가 "자격요건 입력→결과" 웹앱을 요구했으나 프로젝트에 폼·서버가 전무했음 |
| 2026-07-15 | 웹앱 D-day 재계산 수정 — 마감 공고 17/27건(63%)이 TOP 추천에 노출되던 버그 | skills/subscription-webapp·ERRORS | dday가 분석 시점에 박제돼 스냅샷 경과 시 전부 틀어짐 |
| 2026-07-15 | 따라하기 강의 덱 15장 발행(`docs/slides/`) | docs/slides·LECTURE | 세션을 수강생 재현용 강의로 전환 |
| 2026-09-06 | **청약제도안내 전 메뉴 원문 반영** — 특공 소득 단계표(우선/일반/추첨, 맞벌이·2023 이후 자녀 완화), 노부모·생초·신생아 1순위 전제·규제 5년내 당첨 불가, 공공 신혼 6세↓ 자녀·한부모, 생초 저축 600만, 가점제/추첨제 비율표, 공공주택 일반공급 신생아 우선 50%, 잔여세대 3종 자격(무순위 유주택 불가·임의공급만 허용), 오피스텔 제도 분리. 원문 스냅샷 3종 보관. 프로필 필드 추가(monthly_income_manwon·household_size·dual_income·child_after_2023) | skills/subscription-match(지식베이스·SKILL·스키마·원문3종)·subscription-webapp(폼·JS·SKILL)·profile.example·ERRORS | 사용자가 특별공급 8탭 반영 여부 질문 + 하위탭 전부 읽어 반영 요청 |
| 2026-09-05 | **청약홈 원문 검증·정정** — 다자녀 2명↑·노부모 세대주·생애최초 소득세 5년·배우자 통장 2년↑3점 정정, 1순위 요건(가입기간·납입횟수·민영 예치금표·규제지역 강등) 판정 신설, 규제지역 주소 폴백(`regulated-zones.md`), 용어설명 40개 원문 스냅샷 보관. 프로필 필드 추가(account_type·account_payment_count·income_tax_years·won_within_5y·residence_area) | skills/subscription-match(지식베이스·스키마·SKILL·원문)·subscription-analyze(zones·analyze.py)·subscription-webapp(폼·JS·SKILL)·profile.example·ERRORS | 사용자가 청약홈 청약자격·용어설명·규제지역 페이지 제시 → 대조 결과 오류 4건과 1순위 검사 부재 확인 |
| 2026-09-05 | **경쟁률·특공신청현황 서비스(36148) + 주택형별(Mdl) 연동** — `fetch_stats.py` 신설(공고별 주택형·경쟁률·당첨가점·특공 신청현황), `analyze.py` 신설(analyst 규칙 결정적 구현: 수도권·D-day·규제플래그·국민/민영·통계 해석·`competition` 단지별 결과), advisor/웹앱에 특공 유형별 경쟁률·최저당첨가점·미달·빈집털이 신호·분양가·면적 필터 반영, reporter "지난 접수 결과" 표 + `build_report.py` 번들(실행일 기준 D-day 재계산), 오케스트레이터 Phase 3.5 웹앱 빌드 추가. 끊겨 있던 `01_collector_stats.json` 링크 복구 | skills/subscription-collect·analyze·match·webapp·report-html·apt-subscription-report, agents/collector·analyst·advisor, .env.example | 사용자가 두 서비스 기술문서 제공 → 검토 결과 같은 키로 호출 가능 확인, 미연동이던 경쟁률·가점·주택형 데이터 연결 |
| 2026-07-11 | 지식베이스 2025~2026 개정 반영(§8): 월납입 25만원·비아파트 무주택 완화(85㎡·공시 수도권5억)·예부금 전환기한(~26.9)·부부 중복청약/통장합산·실거주의무 충돌 현실화. 프로필 필드 추가(배우자통장·비아파트) | skills/subscription-match(지식베이스·스키마·매칭)·profile.example·CLAUDE | 2026 현재 최신 법개정·시장상황 반영 요청 |


## 워크스페이스 표준 (workspace-init)

**프로젝트:** apt_lottery — 수도권 아파트 청약정보를 매주 수집·분석해 개인 맞춤 추천이 포함된 HTML 리포트로 받아본다

작업 중 지킬 규율:
- 시작 시 `docs/ERRORS.md`를 읽고, 에러 해결 시마다 한 줄 추가(재발방지).
- 의미 있는 진전마다 `docs/WORKLOG.md` 갱신(강의용).
- 비밀은 오직 `.env`(커밋 금지). 새 키는 `.env.example`에 자리표시자 추가.
- 데이터는 `db/db.py`의 DuckDB로 적재·질의.
- **산출물(보고서·강의자료)은 웹앱(HTML)으로 만든다** — 보고서는 `design/report-template.html` 복사·작성, 강의자료는 `docs/LECTURE.md`→`class_slide_apple`. 디자인은 `design/DESIGN.md` 토큰 재사용.
- 마무리 시 `docs/LECTURE.md` 7단(목적·결과물·동작원리·프롬프트·Do·Don't·자주에러) 작성.
