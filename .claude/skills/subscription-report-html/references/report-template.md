# 청약 주간 리포트 HTML 템플릿

복붙 후 `02_analyst_summary.json` 값으로 채운다. 자기완결(외부 의존 없음).

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>수도권 청약 주간 리포트 — {report_date}</title>
<style>
  :root{
    --bg:#f8fafc;--card:#fff;--ink:#1e293b;--muted:#64748b;
    --urgent:#dc2626;--soon:#ea580c;--accent:#2563eb;--ok:#16a34a;--line:#e2e8f0;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif;line-height:1.55}
  .wrap{max-width:900px;margin:0 auto;padding:24px 16px 48px}
  header{margin-bottom:24px}
  header h1{font-size:1.5rem;margin:0 0 6px}
  .sub{color:var(--muted);font-size:.95rem}
  .kpi{display:flex;gap:12px;margin-top:14px;flex-wrap:wrap}
  .kpi div{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:12px 18px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .kpi b{font-size:1.4rem;display:block}
  section{margin-top:28px}
  section h2{font-size:1.15rem;border-left:4px solid var(--accent);padding-left:10px;margin:0 0 14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:16px 18px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .card h3{margin:0 0 8px;font-size:1.05rem}
  .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:6px 18px;
    font-size:.9rem;color:var(--muted)}
  .meta span b{color:var(--ink);font-weight:600}
  .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.8rem;
    font-weight:700;color:#fff}
  .b-urgent{background:var(--urgent)} .b-soon{background:var(--soon)}
  .b-normal{background:var(--muted)} .b-ok{background:var(--ok)}
  .table-wrap{overflow-x:auto}
  table{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}
  th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:.9rem}
  th{background:#f1f5f9}
  .empty{color:var(--muted);font-style:italic;padding:12px}
  .notes{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 16px}
  .notes li{margin:4px 0}
  footer{margin-top:36px;color:var(--muted);font-size:.85rem;text-align:center;
    border-top:1px solid var(--line);padding-top:16px}
  @media(max-width:600px){.meta{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🏠 수도권 청약 주간 리포트</h1>
    <div class="sub">기준일 {report_date}</div>
    <div class="kpi">
      <div><b>{counts.new}</b>신규 공고</div>
      <div><b>{counts.deadline_soon}</b>마감 임박</div>
      <div><b>{counts.closed}</b>이번 주 마감</div>
    </div>
  </header>

  <!-- 1. 마감 임박 (최상단) -->
  <section>
    <h2>⏰ 마감 임박</h2>
    <!-- deadline_soon 각 항목: 긴급=b-urgent, 임박=b-soon -->
    <div class="card">
      <h3>{name} <span class="badge b-urgent">D-{dday}</span></h3>
      <div class="meta"><span>접수마감 <b>{apply_end}</b></span><span>위치 <b>{location}</b></span></div>
    </div>
    <!-- 비었으면 --> <div class="empty">이번 주 마감 임박 공고 없음</div>
  </section>

  <!-- 2. 신규 모집공고 -->
  <section>
    <h2>📋 신규 모집공고</h2>
    <div class="card">
      <h3>{name} <span class="badge b-normal">D-{dday}</span></h3>
      <div class="meta">
        <span>위치 <b>{location}</b></span>
        <span>접수 <b>{apply_start} ~ {apply_end}</b></span>
        <span>당첨발표 <b>{winner_date}</b></span>
        <span>계약 <b>{contract_date}</b></span>
        <span>시공/사업주체 <b>{builder}</b></span>
      </div>
    </div>
    <!-- 비었으면 --> <div class="empty">이번 주 신규 공고 없음</div>
  </section>

  <!-- 3. 지난 접수 결과 (competition[]: 접수 종료·집계 완료, 최근 30일) -->
  <section>
    <h2>📊 지난 접수 결과 — 경쟁률 · 특공 · 가점</h2>
    <div class="sub">접수건수는 은행 전산에 따라 사후 변동 가능 · 집계 {stats_collected_at}</div>
    <div class="table-wrap">
    <table>
      <thead><tr><th>단지</th><th>유형 · 지역</th><th>마감</th><th>최고 경쟁률</th><th>미달 주택형</th><th>최저 당첨가점</th><th>특공 (최저 · 최고)</th></tr></thead>
      <tbody>
        <tr><td>{name}</td><td>{type_label} · {region}</td><td>{apply_end}</td><td>{result.max_rate or "미달"}</td><td>{len(undersubscribed)}개 · {sum short}세대</td><td>{result.min_lwet or "발표 전"}</td><td>{min special: 노부모 0.8} · {max special: 신혼 12.7}</td></tr>
      </tbody>
    </table>
    </div>
    <!-- 30일 내 없음 --> <div class="empty">최근 30일 내 접수 종료 결과 없음</div>
    <!-- competition 자체가 비면 --> <div class="notes">통계 미수집 — fetch_stats.py 실행 필요</div>
  </section>

  <!-- 신규 카드에 붙는 배지/라인 예시 -->
  <!--
    <span class="badge b-normal">민영</span> <span class="badge b-normal">투기과열</span> <span class="badge b-normal">상한제</span>
    <div class="meta"><span>분양가 <b>5.5억 ~ 6.1억</b></span><span>전용 <b>59 · 84㎡</b></span></div>
    <div class="sub">신호(판정 아님): 084C 뒷알파벳·6세대 · 056T 타워형</div>
  -->


  <!-- 4. 참고·주의 -->
  <section>
    <h2>ℹ️ 참고 · 주의</h2>
    <div class="notes">
      <ul>
        <li>{note}</li>
        <li>수도권 외 공고 {others.non_capital}건 · 지역 판별불가 {others.unclassified}건은 제외</li>
      </ul>
    </div>
  </section>

  <footer>데이터 출처: 청약홈(Applyhome) · 생성 {generated_at}</footer>
</div>
</body>
</html>
```

## 채우기 규칙
- 반복 블록(마감임박 카드, 신규 카드, 표 행)은 배열 길이만큼 복제.
- 값이 없는 필드는 `정보 없음`으로 채움(빈 태그 방치 금지).
- D-day 배지 색: `긴급`→`b-urgent`, `임박`→`b-soon`, `일반`→`b-normal`, `마감`→회색 텍스트.
- 데이터 전체가 비면 본문 대신 "이번 주 데이터 수집 실패/공고 없음" 카드 하나로 대체.
