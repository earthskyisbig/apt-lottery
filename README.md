# apt-lottery — 수도권 아파트 청약 주간 리포트 하네스

한국부동산원 **청약홈 분양정보 조회 서비스**(공공데이터포털 odcloud)를 활용해
수도권 아파트 청약 정보를 수집·분석하고 주간 HTML 리포트로 정리하는 에이전트 하네스입니다.

## 무엇을 하나

- **수집**: APT 일반분양 · APT 무순위/잔여세대 · 오피스텔/도시형/생활숙박 · 공공지원 민간임대 · 임의공급 (5개 유형)
- **분석**: 수도권(서울·경기·인천) 필터 · 접수 마감 D-day · 유형별 분류 · 신규공고 선별
- **리포트**: 마감임박 강조 + 유형별 신규공고 카드 + 참고사항의 자기완결 HTML

## 구조 (서브 에이전트 파이프라인)

```
apt-subscription-report (오케스트레이터)
   ├─ subscription-collector  → 청약홈 분양정보 직접 API 수집
   ├─ subscription-analyst    → 수도권 필터·D-day·유형별 정리
   └─ subscription-reporter   → 주간 HTML 리포트 생성
```

- `.claude/agents/` — 에이전트 정의 3종
- `.claude/skills/` — 오케스트레이터 + 수집/분석/리포트 스킬 (+ 번들 수집 스크립트)
- `CLAUDE.md` — 하네스 포인터·트리거·변경 이력

## 사용법

1. 공공데이터포털(data.go.kr)에서 **청약홈 분양정보 조회 서비스** 활용신청 후 인증키 발급
2. `.env.example`을 `.env`로 복사하고 `ODCLOUD_SERVICE_KEY`에 키 입력
3. 수집 실행:
   ```bash
   python .claude/skills/subscription-collect/scripts/fetch_subscriptions.py --out _workspace --lookback-days 90
   ```
4. Claude Code 세션에서 `"청약 리포트 업데이트해줘"` → 전체 파이프라인 실행 → `reports/청약리포트_{날짜}.html` 생성

## 데이터 출처

- 한국부동산원 청약홈 분양정보 조회 서비스 (`api.odcloud.kr`, odcloud stage 37000)
- 경쟁률·가점 통계는 별도 서비스(청약경쟁률)로, 현재 미연동

## 주의

- `.env`(서비스 키), `_workspace/`(원천 데이터), `reports/`(생성 리포트)는 `.gitignore`로 제외됩니다.
- 리포트는 참고용이며, 정확한 청약 일정·자격은 각 공고 원문을 확인하세요.
