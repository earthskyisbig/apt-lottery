# -*- coding: utf-8 -*-
"""주간 청약 HTML 리포트 생성 (subscription-report-html 스킬 표준)."""
import json, os, sys, html
from datetime import date, datetime

from datetime import timedelta
# 스크립트 위치: .claude/skills/subscription-report-html/scripts/ → 프로젝트 루트는 4단계 위
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
WS = os.path.join(ROOT, "_workspace")
# 기준일 = 실행일 (인자로 YYYY-MM-DD 지정 가능). D-day 는 이 날짜로 재계산된다.
BASE = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
REPORT_DATE = BASE.isoformat()
RECENT_FROM = BASE - timedelta(days=30)

E = lambda s: html.escape(str(s)) if s is not None else ""

TYPE_LABEL = {
    "APT_일반": "APT 일반분양",
    "APT_무순위잔여": "APT 무순위·잔여세대",
    "오피스텔생활숙박": "오피스텔/도시형/생활숙박",
    "공공지원민간임대": "공공지원 민간임대",
    "임의공급": "임의공급",
}
TYPE_ORDER = ["APT_일반", "APT_무순위잔여", "오피스텔생활숙박", "공공지원민간임대", "임의공급"]
REG_LABEL = [("speculation_zone", "투기과열"), ("adjusted_area", "조정대상"), ("price_cap", "상한제")]
CONFIRM = ("전매제한 · 실거주의무 · 투기과열지구 지정 · 특공 소득/자산기준은 시점마다 바뀝니다 "
           "— 청약홈/뉴홈 공고 원문에서 최신 확인.")


def pdate(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def dday_of(item):
    d = pdate(item.get("apply_end"))
    return None if d is None else (d - BASE).days


def dbadge(dd):
    if dd is None:
        return '<span class="badge b-normal">일정 미상</span>'
    if dd < 0:
        return '<span class="badge b-normal">마감</span>'
    if dd == 0:
        return '<span class="badge b-urgent">오늘 마감</span>'
    if dd <= 3:
        return '<span class="badge b-urgent">D-%d</span>' % dd
    if dd <= 7:
        return '<span class="badge b-soon">D-%d</span>' % dd
    return '<span class="badge b-normal">D-%d</span>' % dd


def eok(manwon):
    return ("%.1f억" % (manwon / 10000.0))


def price_line(item):
    pr = item.get("price_range_manwon")
    if not pr:
        return None
    lo, hi = pr[0], pr[-1]
    return eok(lo) if lo == hi else "%s ~ %s" % (eok(lo), eok(hi))


def area_line(item):
    ar = item.get("areas")
    if not ar:
        return None
    return " · ".join("%g" % a for a in ar) + "㎡"


def signal_line(item):
    sig = item.get("strategy_signals") or []
    if not sig:
        return None
    parts = []
    for s in sig[:4]:
        ty = str(s.get("ty", "")).replace(".0000", "").lstrip("0")
        parts.append("%s %s" % (ty, "·".join(s.get("why", []))))
    more = " 외 %d개" % (len(sig) - 4) if len(sig) > 4 else ""
    return "신호(판정 아님): " + " · ".join(parts) + more


def badges_for(item):
    out = []
    hd = item.get("house_dtl")
    if hd:
        out.append('<span class="pill pill-blue">%s</span>' % E(hd))
    reg = item.get("regulation") or {}
    for k, lab in REG_LABEL:
        if reg.get(k):
            out.append('<span class="pill">%s</span>' % lab)
    if item.get("is_new"):
        out.append('<span class="pill pill-new">NEW</span>')
    return " ".join(out)


def meta_rows(pairs):
    return "".join('<span>%s <b>%s</b></span>' % (E(k), E(v)) for k, v in pairs if v not in (None, "", []))


def notice_card(item, dd):
    name = E(item.get("name"))
    url = item.get("url")
    title = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(url), name) if url else name
    pairs = [
        ("위치", item.get("location")),
        ("접수", "%s ~ %s" % (item.get("apply_start") or "?", item.get("apply_end") or "?")),
        ("당첨발표", item.get("winner_date")),
        ("계약", item.get("contract_date")),
        ("시공사", item.get("builder")),
        ("사업주체", item.get("developer")),
        ("공급규모", ("%s세대" % item.get("supply_scale")) if item.get("supply_scale") else None),
    ]
    p = price_line(item)
    if p:
        pairs.append(("분양가", p))
    a = area_line(item)
    if a:
        pairs.append(("전용면적", a))
    sig = signal_line(item)
    sig_html = '<div class="sig">%s</div>' % E(sig) if sig else ""
    return ("""<div class="card">
      <h3>%s %s</h3>
      <div class="pills">%s</div>
      <div class="meta">%s</div>
      %s
    </div>""" % (title, dbadge(dd), badges_for(item), meta_rows(pairs), sig_html))


# ---------------------------------------------------------------- load
try:
    S = json.load(open(os.path.join(WS, "02_analyst_summary.json"), encoding="utf-8"))
except Exception as e:
    S = None
    ERR = str(e)

M = None
mp = os.path.join(WS, "03_match_personal.json")
if os.path.exists(mp):
    try:
        M = json.load(open(mp, encoding="utf-8"))
    except Exception:
        M = None

parts = []
A = parts.append

# ---------------------------------------------------------------- header
counts = (S or {}).get("counts", {}) or {}
notes = (S or {}).get("notes", []) or []
collected_at = ""
for n in notes:
    if "통계 수집 시각" in n:
        collected_at = n.split("통계 수집 시각")[-1].strip()

new_by_type = (S or {}).get("new_by_type", {}) or {}
# D-day 재계산 → 마감된 공고 제외
open_items = {}
n_open = 0
for t in TYPE_ORDER:
    lst = []
    for it in new_by_type.get(t, []) or []:
        dd = dday_of(it)
        if dd is not None and dd < 0:
            continue
        lst.append((it, dd))
    lst.sort(key=lambda x: (999 if x[1] is None else x[1]))
    open_items[t] = lst
    n_open += len(lst)

# 마감임박 = 재계산 D-day 0~7
soon = []
seen = set()
for it in (S or {}).get("deadline_soon", []) or []:
    dd = dday_of(it)
    if dd is not None and 0 <= dd <= 7 and it.get("id") not in seen:
        seen.add(it.get("id"))
        soon.append((it, dd))
soon.sort(key=lambda x: x[1])

if S is None:
    body = ('<div class="card"><h3>이번 주 데이터 수집 실패</h3>'
            '<p>analyst 요약 파일을 읽지 못했습니다: %s</p></div>' % E(ERR))
else:
    body = None

A("""<div class="wrap">
  <header>
    <h1>🏠 수도권 청약 주간 리포트</h1>
    <div class="sub">기준일 %s · 데이터 수집 %s</div>
    <div class="sub">한 줄 요약 — 진행·예정 <b>%d건</b> · 마감 임박(7일 내) <b>%d건</b> · 이번 회차 신규 <b>%d건</b></div>
    <div class="kpi">
      <div><b>%d</b>진행·예정</div>
      <div><b>%d</b>마감 임박</div>
      <div><b>%d</b>신규 공고</div>
      <div><b>%d</b>집계 완료 결과</div>
    </div>
    <div class="kpi small">%s</div>
  </header>""" % (
    E(REPORT_DATE), E(collected_at or "정보 없음"), n_open, len(soon), counts.get("new", 0),
    n_open, len(soon), counts.get("new", 0), len((S or {}).get("competition", []) or []),
    "".join('<div><b>%d</b>%s</div>' % (v, E(TYPE_LABEL.get(k, k)))
            for k, v in (counts.get("by_type") or {}).items())))

# ---------------------------------------------------------------- 0. 맞춤
A('<section id="match"><h2>🎯 내 조건 맞춤</h2>')
if M and M.get("profile_present"):
    ps = M.get("profile_summary", {}) or {}
    acc = ps.get("account", {}) or {}
    A('<div class="card profile"><h3>프로필 요약</h3><div class="meta">%s</div>%s</div>' % (
        meta_rows([
            ("세대유형", ps.get("household_status")),
            ("해당 유형", " · ".join(ps.get("types") or [])),
            ("예상 가점", "%s점" % ps.get("est_score") if ps.get("est_score") is not None else None),
            ("성향", ps.get("orientation")),
            ("청약통장", "가입 %s년 · 총 %s만원 · 월 %s만원" % (
                acc.get("join_years"), acc.get("total_manwon"), acc.get("monthly_manwon"))
             if acc else None),
            ("소득", ps.get("income_level")),
            ("목적", ps.get("purpose")),
            ("희망지역", " · ".join(ps.get("regions") or [])),
        ]),
        ('<div class="sig">%s</div>' % E(" · ".join(ps.get("flags") or []))) if ps.get("flags") else ""))
    A('<div class="warn"><b>이 섹션은 1차 선별이며 자격 판정이 아닙니다.</b> '
      '전매제한 · 실거주의무 · 투기과열지구 지정 · 특공 소득/자산기준은 시점마다 바뀝니다 — '
      '청약홈/뉴홈 공고 원문에서 최신 확인하세요.</div>')

    tm = sorted(M.get("top_matches", []) or [], key=lambda x: -(x.get("fit_score") or 0))
    live = [t for t in tm if (dday_of(t) is None or dday_of(t) >= 0)]
    if not live:
        A('<div class="empty">추천 가능한 진행 중 공고 없음</div>')
    for i, t in enumerate(live, 1):
        dd = dday_of(t)
        url = t.get("url")
        nm = E(t.get("name"))
        title = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(url), nm) if url else nm
        routes = " ".join('<span class="pill pill-blue">%s</span>' % E(r) for r in (t.get("route") or []))
        tags = " ".join('<span class="pill">%s</span>' % E(x) for x in (t.get("tags") or []))
        regs = " ".join('<span class="pill pill-red">%s</span>' % E(x) for x in (t.get("regulation_flags") or []))
        pairs = [("지역", "%s · %s" % (t.get("region") or "", t.get("location") or "")),
                 ("접수마감", t.get("apply_end")),
                 ("당첨발표", t.get("winner_date")),
                 ("공급규모", ("%s세대" % t.get("supply_scale")) if t.get("supply_scale") else None)]
        p = price_line(t)
        if p:
            pairs.append(("분양가", p))
        a = area_line(t)
        if a:
            pairs.append(("전용면적", a))
        ev = t.get("evidence") or []
        ev_html = ('<div class="evidence"><b>근거 데이터</b><ul>%s</ul></div>'
                   % "".join("<li>%s</li>" % E(x) for x in ev)) if ev else \
                  '<div class="evidence"><b>근거 데이터</b> 없음 (해당 지역 최근 집계 결과 미확보)</div>'
        A("""<div class="card match">
      <div class="rank">#%d <span class="fit">적합도 %s</span></div>
      <h3>%s %s</h3>
      <div class="pills">%s %s %s</div>
      <div class="meta">%s</div>
      <div class="why"><b>왜 추천</b> %s</div>
      %s
      <div class="confirm"><b>확인 필요</b> %s</div>
    </div>""" % (i, E(t.get("fit_score")), title, dbadge(dd), routes, tags, regs,
                 meta_rows(pairs), E(t.get("why")), ev_html,
                 E(t.get("confirm") or CONFIRM)))

    sg = M.get("simultaneous_groups") or []
    if sg:
        A('<div class="notes"><b>⚠️ 동시분양 — 당첨자 발표일이 같으면 택1</b><ul>')
        for g in sg:
            names = ", ".join("%s(%s)" % (n.get("name"), n.get("region")) for n in g.get("notices", []))
            A("<li><b>%s 발표</b> — %s<br><span class='sub'>%s</span></li>"
              % (E(g.get("announce_date")), E(names), E(g.get("hint"))))
        A("</ul></div>")
else:
    A('<div class="notes">profile.yaml을 세팅하면 내 조건에 맞는 청약만 골라 드립니다. '
      '(또는 <b>청약자격진단 웹앱</b>에 같은 조건을 폼으로 입력하세요)</div>')
A("</section>")

# ---------------------------------------------------------------- 2. 마감임박
A('<section><h2>⏰ 마감 임박</h2>')
if soon:
    for it, dd in soon:
        A('<div class="card urgent-card"><h3>%s %s</h3><div class="pills">%s %s</div>'
          '<div class="meta">%s</div></div>' % (
              ('<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(it.get("url")), E(it.get("name"))))
              if it.get("url") else E(it.get("name")),
              dbadge(dd),
              '<span class="pill pill-blue">%s</span>' % E(TYPE_LABEL.get(it.get("type"), it.get("type"))),
              badges_for(it),
              meta_rows([("접수마감", it.get("apply_end")), ("위치", it.get("location")),
                         ("당첨발표", it.get("winner_date")),
                         ("공급규모", ("%s세대" % it.get("supply_scale")) if it.get("supply_scale") else None),
                         ("분양가", price_line(it)), ("전용면적", area_line(it))])))
else:
    A('<div class="empty">이번 주 마감 임박 공고 없음</div>')
A("</section>")

# ---------------------------------------------------------------- 3. 진행/예정
A('<section><h2>📋 진행 · 예정 모집공고 (유형별)</h2>')
sec_counts = {}
for t in TYPE_ORDER:
    lst = open_items.get(t, [])
    sec_counts[t] = len(lst)
    A('<h3 class="typeh">%s <span class="cnt">%d건</span></h3>' % (E(TYPE_LABEL[t]), len(lst)))
    if not lst:
        A('<div class="empty">해당 없음</div>')
        continue
    for it, dd in lst:
        A(notice_card(it, dd))
A("</section>")

# ---------------------------------------------------------------- 4. 지난 결과
comp = (S or {}).get("competition", []) or []
recent = []
for c in comp:
    d = pdate(c.get("apply_end"))
    if d and d >= RECENT_FROM and d <= BASE:
        recent.append((d, c))
recent.sort(key=lambda x: -x[0].toordinal())

A('<section><h2>📊 지난 접수 결과 — 경쟁률 · 특공 · 가점</h2>')
if not comp:
    A('<div class="notes">통계 미수집 — <code>fetch_stats.py</code> 실행 필요</div>')
elif not recent:
    A('<div class="empty">최근 30일 내 접수 종료 결과 없음</div>')
else:
    A('<div class="sub cap">접수건수는 은행 전산에 따라 사후 변동 가능 · 집계 %s</div>' % E(collected_at or "정보 없음"))
    rows = []
    for d, c in recent:
        r = c.get("result") or {}
        mr = r.get("max_rate")
        rate = "미달" if not mr else "%s : 1" % ("%g" % mr)
        rate_cls = "bad" if not mr else ("hot" if mr >= 50 else "")
        und = r.get("undersubscribed") or []
        if und:
            short = sum(int(u.get("short") or 0) for u in und)
            undtxt = '<span class="bad">%d개 · %d세대</span>' % (len(und), short)
        else:
            undtxt = "없음"
        lwet = r.get("min_lwet")
        lwet = "%s점" % lwet if lwet is not None else "발표 전"
        sp = r.get("special") or {}
        if sp:
            items = [(k, v.get("rate")) for k, v in sp.items() if v.get("rate") is not None]
            if items:
                lo = min(items, key=lambda x: x[1])
                hi = max(items, key=lambda x: x[1])
                sptxt = "%s %g · %s %g" % (lo[0], lo[1], hi[0], hi[1])
            else:
                sptxt = "—"
        else:
            sptxt = "—"
        nm = E(c.get("name"))
        if c.get("url"):
            nm = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (E(c.get("url")), nm)
        rows.append("<tr><td>%s</td><td>%s · %s</td><td>%s</td><td class='%s'>%s</td>"
                    "<td>%s</td><td>%s</td><td>%s</td></tr>" % (
                        nm, E(TYPE_LABEL.get(c.get("type"), c.get("type"))), E(c.get("region")),
                        E(c.get("apply_end")), rate_cls, E(rate), undtxt, E(lwet), E(sptxt)))
    A('<div class="table-wrap"><table><thead><tr>'
      '<th>단지</th><th>유형 · 지역</th><th>마감</th><th>최고 경쟁률</th>'
      '<th>미달 주택형</th><th>최저 당첨가점</th><th>특공 (최저 · 최고)</th>'
      '</tr></thead><tbody>%s</tbody></table></div>' % "".join(rows))
    A('<div class="sub">최근 30일(%s ~ %s) 접수 종료 %d건 · 전체 집계 완료 %d건'
      % (RECENT_FROM.isoformat(), BASE.isoformat(), len(recent), len(comp)))
    A("</div>")
A("</section>")

# ---------------------------------------------------------------- 5. 참고
A('<section><h2>ℹ️ 참고 · 주의</h2><div class="notes"><b>데이터 수집 메모</b><ul>')
for n in notes:
    A("<li>%s</li>" % E(n))
oth = (S or {}).get("others", {}) or {}
A("<li>수도권 외 공고 %d건 · 지역 판별불가 %d건은 제외</li>"
  % (oth.get("non_capital", 0), oth.get("unclassified", 0)))
A("</ul></div>")
if M and (M.get("notes") or []):
    A('<div class="notes" style="margin-top:12px"><b>맞춤 분석 메모</b><ul>')
    for n in M["notes"]:
        A("<li>%s</li>" % E(n))
    A("</ul></div>")
A("</section>")

A('<footer>데이터 출처: 청약홈 분양정보 조회 서비스 · 청약접수 경쟁률 · 특별공급 신청현황 조회 서비스'
  '<br>생성 %s · 이 리포트는 정보 제공용이며 청약 자격 판정이 아닙니다.</footer>' % E(REPORT_DATE))
A("</div>")

CSS = """
  :root{--bg:#f8fafc;--card:#fff;--ink:#1e293b;--muted:#64748b;
    --urgent:#dc2626;--soon:#ea580c;--accent:#2563eb;--ok:#16a34a;--line:#e2e8f0;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:'Segoe UI','Malgun Gothic',system-ui,sans-serif;line-height:1.55}
  a{color:inherit}
  .wrap{max-width:900px;margin:0 auto;padding:24px 16px 48px}
  header h1{font-size:1.5rem;margin:0 0 6px}
  .sub{color:var(--muted);font-size:.92rem}
  .sub.cap{margin-bottom:8px}
  .kpi{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
  .kpi div{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:10px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:.88rem;color:var(--muted)}
  .kpi b{font-size:1.35rem;display:block;color:var(--ink)}
  .kpi.small div{padding:8px 12px;font-size:.8rem}
  .kpi.small b{font-size:1.05rem}
  section{margin-top:32px}
  section h2{font-size:1.15rem;border-left:4px solid var(--accent);padding-left:10px;margin:0 0 14px}
  h3.typeh{font-size:1rem;margin:22px 0 10px;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:6px}
  h3.typeh .cnt{color:var(--accent);font-weight:700}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:16px 18px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
  .card h3{margin:0 0 8px;font-size:1.05rem;line-height:1.4}
  .card.urgent-card{border-left:4px solid var(--urgent)}
  .card.match{border-left:4px solid var(--accent)}
  .card.profile{background:#f1f5f9}
  .rank{font-size:.85rem;color:var(--muted);font-weight:700;margin-bottom:4px}
  .fit{background:var(--accent);color:#fff;border-radius:999px;padding:2px 10px;margin-left:6px;font-size:.78rem}
  .meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:6px 18px;
    font-size:.88rem;color:var(--muted)}
  .meta span b{color:var(--ink);font-weight:600}
  .pills{margin:0 0 10px;display:flex;gap:6px;flex-wrap:wrap}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.75rem;
    font-weight:600;background:#e2e8f0;color:#475569}
  .pill-blue{background:#dbeafe;color:#1d4ed8}
  .pill-red{background:#fee2e2;color:#b91c1c}
  .pill-new{background:var(--ok);color:#fff}
  .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.78rem;
    font-weight:700;color:#fff;vertical-align:middle}
  .b-urgent{background:var(--urgent)} .b-soon{background:var(--soon)} .b-normal{background:var(--muted)}
  .why{margin-top:10px;font-size:.9rem;background:#f8fafc;border-radius:8px;padding:10px 12px}
  .why b{color:var(--accent)}
  .evidence{margin-top:8px;font-size:.85rem;color:var(--muted)}
  .evidence b{color:var(--ink)}
  .evidence ul{margin:4px 0 0;padding-left:18px}
  .confirm{margin-top:8px;font-size:.82rem;background:#fffbeb;border:1px solid #fde68a;
    border-radius:8px;padding:9px 12px;color:#92400e}
  .confirm b{color:#b45309}
  .warn{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:12px;
    padding:12px 16px;margin-bottom:14px;font-size:.88rem}
  .sig{margin-top:8px;font-size:.82rem;color:var(--muted);font-style:italic}
  .table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
  table{width:100%;border-collapse:collapse;background:var(--card);min-width:760px}
  th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:.85rem;white-space:nowrap}
  td:first-child{white-space:normal;min-width:200px}
  th{background:#f1f5f9;position:sticky;top:0}
  td.hot{color:var(--urgent);font-weight:700}
  td.bad,.bad{color:var(--soon);font-weight:700}
  .empty{color:var(--muted);font-style:italic;padding:12px 0}
  .notes{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 16px;font-size:.88rem}
  .notes ul{margin:6px 0 0;padding-left:18px}
  .notes li{margin:5px 0}
  footer{margin-top:40px;color:var(--muted);font-size:.82rem;text-align:center;
    border-top:1px solid var(--line);padding-top:16px}
  @media(max-width:600px){.meta{grid-template-columns:1fr}}
  @media print{body{background:#fff}.card{break-inside:avoid}}
"""

doc = ("""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>수도권 청약 주간 리포트 — %s</title>
<style>%s</style>
</head>
<body>
%s
</body>
</html>
""" % (REPORT_DATE, CSS, ("\n".join(parts) if body is None else
       '<div class="wrap"><header><h1>🏠 수도권 청약 주간 리포트</h1>'
       '<div class="sub">기준일 %s</div></header>%s</div>' % (REPORT_DATE, body))))

outdir = os.path.join(ROOT, "reports")
os.makedirs(outdir, exist_ok=True)
out = os.path.join(outdir, "청약리포트_%s.html" % REPORT_DATE)
with open(out, "w", encoding="utf-8") as f:
    f.write(doc)

sys.stdout.reconfigure(encoding="utf-8")
print("OUT", out, os.path.getsize(out), "bytes")
print("맞춤 추천", len([t for t in (M.get("top_matches") or []) if (dday_of(t) or 0) >= 0]) if M else 0)
print("마감임박", len(soon))
print("진행·예정 합계", n_open, {TYPE_LABEL[k]: v for k, v in sec_counts.items()})
print("지난결과 행", len(recent), "/ 전체", len(comp))
print("notes", len(notes), "match notes", len(M.get("notes", [])) if M else 0)
