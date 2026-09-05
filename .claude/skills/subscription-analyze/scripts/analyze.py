#!/usr/bin/env python3
"""
청약 분석기 — collector 원천(01_*)을 리포트/웹앱용 02_analyst_summary.json 으로 가공한다.

하는 일 (subscription-analyze SKILL.md 규칙의 결정적 구현):
  1. 수도권 필터(SUBSCRPT_AREA_CODE_NM → HSSPLY_ADRES 폴백, 판별불가 보존)
  2. 유형별 날짜 정규화 + D-day/태그 (긴급≤3 · 임박≤7 · 마감<0 · 일반)
  3. 규제 플래그·국민/민영 코드 노출 (APT_일반)
  4. 01_collector_stats.json 이 있으면 주택형별(분양가·면적·특공 배정)·경쟁률·당첨가점·특공신청현황을 해석해
     각 공고에 models / result 를 붙이고, 접수 종료 공고의 결과를 competition 에 모은다
  5. 데이터 누락·이상은 notes 에 기록 (조용히 삼키지 않는다)

D-day 는 기준일(base_date) 기준 계산값이다. 리포트/웹앱은 표시 시점에 apply_end 로 재계산해야 한다
(스냅샷이 오래되면 틀어진다 — docs/ERRORS.md 2026-07-15).

사용: python analyze.py --workspace _workspace [--base-date YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

CAPITAL = ("서울", "경기", "인천")
# 규제지역(투기과열=청약과열, 2026-09-05 청약홈 지정 현황) — API 플래그 없는 유형의 주소 폴백. references/regulated-zones.md 와 함께 갱신.
ZONES_DATE = "2026-09-05"
ZONES_GG = ["과천시", "광명시", "수원시 영통구", "수원시 장안구", "수원시 팔달구", "성남시 분당구", "성남시 수정구", "성남시 중원구",
            "안양시 동안구", "용인시 수지구", "용인시 기흥구", "화성시 동탄", "의왕시", "하남시", "구리시"]


def zone_by_address(adr):
    a = re.sub(r"\s+", " ", adr or "")
    if a.startswith("서울"):
        return True
    if a.startswith("경기"):
        return any(z in a for z in ZONES_GG)
    return False


TYPES = ["APT_일반", "APT_무순위잔여", "오피스텔생활숙박", "공공지원민간임대", "임의공급"]

START_FIELDS = ("RCEPT_BGNDE", "SUBSCRPT_RCEPT_BGNDE", "GNRL_RCEPT_BGNDE", "SPSPLY_RCEPT_BGNDE",
                "GNRL_RNK1_CRSPAREA_RCPTDE")
END_FIELDS = ("RCEPT_ENDDE", "SUBSCRPT_RCEPT_ENDDE", "GNRL_RCEPT_ENDDE", "SPSPLY_RCEPT_ENDDE",
              "GNRL_RNK1_CRSPAREA_ENDDE", "GNRL_RNK1_ETC_AREA_ENDDE", "GNRL_RNK1_ETC_GG_ENDDE",
              "GNRL_RNK2_CRSPAREA_ENDDE", "GNRL_RNK2_ETC_AREA_ENDDE", "GNRL_RNK2_ETC_GG_ENDDE")

SPECIAL_MODEL_FIELDS = {  # 주택형별(Mdl) 특공 배정
    "신혼부부": "NWWDS_HSHLDCO", "생애최초": "LFE_FRST_HSHLDCO", "다자녀": "MNYCH_HSHLDCO",
    "노부모부양": "OLD_PARNTS_SUPORT_HSHLDCO", "신생아": "NWBB_HSHLDCO", "청년": "YGMN_HSHLDCO",
    "기관추천": "INSTT_RECOMEND_HSHLDCO",
}
SPECIAL_REQ_FIELDS = {  # 특공신청현황: (배정, [접수 해당지역, 기타경기, 기타지역])
    "신혼부부": ("NWWDS_NMTW_HSHLDCO", ["CRSPAREA_NWWDS_NMTW_CNT", "CTPRVN_NWWDS_NMTW_CNT", "ETC_AREA_NWWDS_NMTW_CNT"]),
    "생애최초": ("LFE_FRST_HSHLDCO", ["CRSPAREA_LFE_FRST_CNT", "CTPRVN_LFE_FRST_CNT", "ETC_AREA_LFE_FRST_CNT"]),
    "다자녀": ("MNYCH_HSHLDCO", ["CRSPAREA_MNYCH_CNT", "CTPRVN_MNYCH_CNT", "ETC_AREA_MNYCH_CNT"]),
    "노부모부양": ("OLD_PARNTS_SUPORT_HSHLDCO", ["CRSPAREA_OPS_CNT", "CTPRVN_OPS_CNT", "ETC_AREA_OPS_CNT"]),
    "신생아": ("NWBB_NWBBSHR_HSHLDCO", ["CRSPAREA_NWBB_NWBBSHR_CNT", "CTPRVN_NWBB_NWBBSHR_CNT", "ETC_AREA_NWBB_NWBBSHR_CNT"]),
    "청년": ("YGMN_HSHLDCO", ["CRSPAREA_YGMN_CNT", "CTPRVN_YGMN_CNT", "ETC_AREA_YGMN_CNT"]),
    "기관추천": ("INSTT_RECOMEND_HSHLDCO", ["INSTT_RECOMEND_DCSN_CNT"]),
}


# ── 파서 ─────────────────────────────────────────────────────────────
def norm_date(v):
    """YYYYMMDD / YYYY-MM-DD / YYYY.MM.DD / 시각 포함 → YYYY-MM-DD, 실패 None."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    m = re.match(r"(\d{4})[-./]?(\d{2})[-./]?(\d{2})", s)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def to_int(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    return int(float(s)) if re.match(r"^-?\d+(\.\d+)?$", s) else None


def parse_rate(v):
    """CMPET_RATE: '401.00'→401.0 · '(△15)'→미달 15 · null/'-'→None (미집계)."""
    if v is None:
        return None, None
    s = str(v).strip()
    if not s or s == "-":
        return None, None
    m = re.match(r"^\(?[△▲]\s*(\d+)\)?$", s)
    if m:
        return 0.0, int(m.group(1))
    try:
        return float(s.replace(",", "")), 0
    except ValueError:
        return None, None


def parse_house_ty(ty):
    """'084.9543T' → (84.95, 'T') · '76A' → (76.0, 'A') · '059.8000 ' → (59.8, '')."""
    if not ty:
        return None, ""
    s = str(ty).strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Za-z\-0-9]*)$", s)
    if not m:
        return None, s
    return round(float(m.group(1)), 2), m.group(2).upper()


def region_of(it):
    nm = (it.get("SUBSCRPT_AREA_CODE_NM") or "").strip()
    if nm in CAPITAL:
        return nm, "code"
    adr = it.get("HSSPLY_ADRES") or ""
    for r in CAPITAL:
        if adr.startswith(r) or f" {r}" in adr[:12] or adr.startswith({"서울": "서울특별시", "경기": "경기도", "인천": "인천광역시"}[r]):
            return r, "address"
    if nm:
        return nm, "code"
    return None, None


def flag(v):
    return True if v == "Y" else False if v == "N" else None


# ── 통계 해석 ─────────────────────────────────────────────────────────
def summarize_models(rec):
    rows = (rec.get("models") or {}).get("rows") or []
    out = []
    for r in rows:
        area, suffix = parse_house_ty(r.get("HOUSE_TY") or r.get("TP"))
        excl = to_int(r.get("EXCLUSE_AR")) if r.get("EXCLUSE_AR") else None
        price = to_int(r.get("LTTOT_TOP_AMOUNT")) or to_int(r.get("SUPLY_AMOUNT"))
        special = {k: to_int(r.get(f)) for k, f in SPECIAL_MODEL_FIELDS.items() if r.get(f) is not None}
        # 공공지원민간임대 특공 필드
        for k, f in (("신혼부부", "SPSPLY_NEW_MRRG_HSHLDCO"), ("청년", "SPSPLY_YGMN_HSHLDCO"), ("고령자", "SPSPLY_AGED_HSHLDCO")):
            if r.get(f) is not None:
                special[k] = to_int(r.get(f))
        m = {"ty": (r.get("HOUSE_TY") or r.get("TP") or "").strip(), "area": area if area is not None else excl,
             "suffix": suffix, "supply_general": to_int(r.get("SUPLY_HSHLDCO") if "GNSPLY_HSHLDCO" not in r else r.get("GNSPLY_HSHLDCO")),
             "supply_special": to_int(r.get("SPSPLY_HSHLDCO")), "special": {k: v for k, v in special.items() if v},
             "price_manwon": price}
        out.append(m)
    return out


def summarize_result(rec, house_type):
    """경쟁률/가점/특공신청현황 → {status, models:[...], max_rate, undersubscribed, min_lwet, special}"""
    cm_rows = (rec.get("cmpet") or {}).get("rows") or []
    if not cm_rows and house_type == "APT_무순위잔여":
        cm_rows = (rec.get("cmpet_cancel") or {}).get("rows") or []
    if not cm_rows:
        return {"status": "없음"}
    by_ty = {}
    any_counted = False
    for r in cm_rows:
        ty = (r.get("HOUSE_TY") or "").strip()
        rate, short = parse_rate(r.get("CMPET_RATE"))
        req = to_int(r.get("REQ_CNT")) or 0
        if rate is not None:
            any_counted = True
        d = by_ty.setdefault(ty, {"ty": ty, "supply": to_int(r.get("SUPLY_HSHLDCO")), "req": 0, "rate_max": None, "short": 0,
                                  "rank1_local": None})
        d["req"] += req
        if rate is not None:
            d["rate_max"] = max(d["rate_max"] or 0, rate)
            if short:
                d["short"] = max(d["short"], short)
            if r.get("SUBSCRPT_RANK_CODE") in (1, "1") and r.get("RESIDE_SECD") in ("01", None):
                d["rank1_local"] = rate if not short else f"미달 {short}"
    if not any_counted:
        return {"status": "미집계", "models": list(by_ty.values())}
    res = {"status": "집계", "models": list(by_ty.values())}
    rates = [d["rate_max"] for d in by_ty.values() if d["rate_max"]]
    res["max_rate"] = max(rates) if rates else 0.0
    res["undersubscribed"] = [{"ty": d["ty"], "short": d["short"]} for d in by_ty.values() if d["short"]]
    res["total_req"] = sum(d["req"] for d in by_ty.values())
    # 당첨가점
    sc_rows = (rec.get("score") or {}).get("rows") or []
    lw = []
    for r in sc_rows:
        v = to_int(r.get("LWET_SCORE"))
        if v:  # 0 은 추첨/미달 행이라 커트라인 아님

            lw.append({"ty": (r.get("HOUSE_TY") or "").strip(), "reside": r.get("RESIDE_SENM"), "lwet": v,
                       "avg": r.get("AVRG_SCORE"), "top": to_int(r.get("TOP_SCORE"))})
    if lw:
        res["score"] = lw
        res["min_lwet"] = min(x["lwet"] for x in lw)
    # 특공 신청현황(유형별 합산)
    sp_rows = (rec.get("spsply") or {}).get("rows") or []
    if sp_rows:
        agg = {}
        for k, (alloc_f, req_fs) in SPECIAL_REQ_FIELDS.items():
            alloc = sum(to_int(r.get(alloc_f)) or 0 for r in sp_rows)
            req = sum(sum(to_int(r.get(f)) or 0 for f in req_fs) for r in sp_rows)
            if alloc:
                agg[k] = {"alloc": alloc, "req": req, "rate": round(req / alloc, 2)}
        if agg:
            res["special"] = agg
            res["special_status"] = sp_rows[0].get("SUBSCRPT_RESULT_NM")
    return res


def strategy_signals(models, total_supply, aggressive_only=False):
    """지식베이스 §6 빈집털이 신호: 타워형(T)·뒷알파벳(C 이후)·소수세대·애매평형."""
    sig = []
    for m in models:
        s = m.get("suffix") or ""
        letters = re.sub(r"[^A-Z]", "", s)
        why = []
        if "T" in letters:
            why.append("타워형")
        if letters and letters[-1] >= "C" and "T" not in letters:
            why.append(f"뒷알파벳({letters[-1]})")
        a = m.get("area")
        if a and not (58 <= a <= 60 or 83 <= a <= 85.9) and a < 100:
            why.append("애매평형")
        sup = (m.get("supply_general") or 0) + (m.get("supply_special") or 0)
        if 0 < sup <= 10:
            why.append(f"소수세대({sup})")
        if why:
            sig.append({"ty": m["ty"], "why": why})
    return sig


# ── 메인 ─────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="_workspace")
    ap.add_argument("--base-date", default=None)
    args = ap.parse_args()
    ws = Path(args.workspace)
    notices = json.loads((ws / "01_collector_notices.json").read_text(encoding="utf-8")).get("items", [])
    meta = json.loads((ws / "01_collector_meta.json").read_text(encoding="utf-8"))
    stats_p = ws / "01_collector_stats.json"
    stats = json.loads(stats_p.read_text(encoding="utf-8")) if stats_p.exists() else None
    base = dt.date.fromisoformat(args.base_date) if args.base_date else dt.date.today()
    notes = []
    if not meta.get("auth_ok", True):
        notes.append("collector 인증 실패(auth_ok=false) — 공고 데이터가 비었거나 불완전합니다")
    for e in meta.get("endpoints", []):
        if e.get("error"):
            notes.append(f"{e['label']} 수집 오류: {e['error']}")
    if stats is None:
        notes.append("경쟁률·가점·주택형 데이터 없음 — fetch_stats.py 를 실행하면 주택형별 분양가·특공배정·경쟁률·당첨가점이 붙습니다")
    else:
        sm = stats.get("meta", {})
        if not sm.get("auth_ok", True):
            notes.append("경쟁률 서비스 인증 실패 — 통계 데이터 불완전")
        if sm.get("errors"):
            notes.append(f"통계 수집 오류 {len(sm['errors'])}건 (01_collector_stats.json meta.errors)")

    by_type = {t: [] for t in TYPES}
    counts_by_type = {t: 0 for t in TYPES}
    unclassified, non_capital, closed, new_cnt = 0, 0, 0, 0
    deadline_soon, competition, unparsed = [], [], 0

    for it in notices:
        ht = it.get("_house_type")
        counts_by_type[ht] = counts_by_type.get(ht, 0) + 1
        region, how = region_of(it)
        if region is None:
            unclassified += 1
            continue
        if region not in CAPITAL:
            non_capital += 1
            continue
        starts = [norm_date(it.get(k)) for k in START_FIELDS if it.get(k)]
        ends = [norm_date(it.get(k)) for k in END_FIELDS if it.get(k)]
        starts = [s for s in starts if s]; ends = [e for e in ends if e]
        apply_start = min(starts) if starts else None
        apply_end = max(ends) if ends else None
        dday = (dt.date.fromisoformat(apply_end) - base).days if apply_end else None
        if apply_end is None:
            unparsed += 1
        tag = ("마감" if dday < 0 else "긴급" if dday <= 3 else "임박" if dday <= 7 else "일반") if dday is not None else "일반"
        hm = str(it.get("HOUSE_MANAGE_NO"))
        item = {
            "id": hm, "name": it.get("HOUSE_NM"), "type": ht, "location": it.get("HSSPLY_ADRES"), "region": region,
            "region_source": how, "apply_start": apply_start, "apply_end": apply_end,
            "winner_date": norm_date(it.get("PRZWNER_PRESNATN_DE")),
            "contract_date": norm_date(it.get("CNTRCT_CNCLS_BGNDE")),
            "builder": it.get("CNSTRCT_ENTRPS_NM") or "정보 없음", "developer": it.get("BSNS_MBY_NM"),
            "supply_scale": to_int(it.get("TOT_SUPLY_HSHLDCO")), "url": it.get("PBLANC_URL"),
            "notice_date": norm_date(it.get("RCRIT_PBLANC_DE")), "dday": dday, "tag": tag,
            "date_unparsed": apply_end is None,
            "house_dtl": it.get("HOUSE_DTL_SECD_NM") or it.get("HOUSE_DETAIL_SECD_NM"),  # 민영/국민 등
            "house_secd": it.get("HOUSE_SECD_NM"),
        }
        if ht == "APT_일반":
            item["regulation"] = {
                "speculation_zone": flag(it.get("SPECLT_RDN_EARTH_AT")),   # 투기과열지구
                "adjusted_area": flag(it.get("MDAT_TRGET_AREA_SECD")),     # 조정대상지역
                "price_cap": flag(it.get("PARCPRC_ULS_AT")),               # 분양가상한제
                "public_housing_zone": flag(it.get("PUBLIC_HOUSE_EARTH_AT")),
                "public_housing_law": flag(it.get("PUBLIC_HOUSE_SPCLW_APPLC_AT")),
                "redevelopment": flag(it.get("IMPRMN_BSNS_AT")),
                "large_site": flag(it.get("LRSCL_BLDLND_AT")),
                "source": "api",
            }
        else:
            z = zone_by_address(it.get("HSSPLY_ADRES"))
            item["regulation"] = {"speculation_zone": z, "adjusted_area": z, "price_cap": None,
                                  "source": f"address_list_{ZONES_DATE}"}
            item["is_public"] = it.get("HOUSE_DTL_SECD") == "03" and it.get("PUBLIC_HOUSE_SPCLW_APPLC_AT") == "Y"
            item["special_apply"] = [norm_date(it.get("SPSPLY_RCEPT_BGNDE")), norm_date(it.get("SPSPLY_RCEPT_ENDDE"))]
            item["move_in"] = it.get("MVN_PREARNGE_YM")
        # 통계 결합
        rec = (stats or {}).get("by_notice", {}).get(hm)
        if rec:
            models = summarize_models(rec)
            item["models"] = models
            prices = [m["price_manwon"] for m in models if m.get("price_manwon")]
            item["price_range_manwon"] = [min(prices), max(prices)] if prices else None
            areas = sorted({m["area"] for m in models if m.get("area")})
            item["areas"] = areas
            item["strategy_signals"] = strategy_signals(models, item["supply_scale"])
            item["result"] = summarize_result(rec, ht)
        else:
            item["result"] = {"status": "없음"}

        if dday is not None and dday < 0:
            closed += 1
            if item["result"].get("status") == "집계":
                competition.append(item)
            continue
        is_new = apply_start is not None and (apply_start >= base.isoformat() or (base - dt.date.fromisoformat(apply_start)).days <= 7)
        item["is_new"] = is_new
        if is_new:
            new_cnt += 1
        by_type[ht].append(item)
        if tag in ("긴급", "임박"):
            deadline_soon.append(item)

    deadline_soon.sort(key=lambda x: (x["dday"], x["name"] or ""))
    for t in by_type:
        by_type[t].sort(key=lambda x: (x["dday"] if x["dday"] is not None else 999, x["name"] or ""))
    competition.sort(key=lambda x: x["apply_end"] or "", reverse=True)

    if unparsed:
        notes.append(f"접수 마감일 파싱 실패 {unparsed}건 (date_unparsed=true, D-day 없음)")
    if stats is not None:
        counted = len(competition)
        pending = sum(1 for t in by_type.values() for x in t if x["result"].get("status") in ("미집계", "없음"))
        notes.append(f"경쟁률 집계 완료 {counted}건(접수 종료 수도권) · 진행/예정 공고 {pending}건은 접수 종료 후 채워짐. "
                     "접수건수는 은행 전산에 따라 사후 변동될 수 있음(청약홈 최종값 우선)")
        notes.append(f"통계 수집 시각 {stats['meta'].get('collected_at')}")
    notes.append(f"collector 총 {len(notices)}건(최근 {meta.get('lookback_days')}일), 수도권 {sum(len(v) for v in by_type.values()) + closed}건")
    notes.append("D-day 는 기준일 계산값 — 리포트/웹앱은 표시 시점에 apply_end 로 재계산할 것")

    out = {
        "report_date": base.isoformat(),
        "counts": {"new": new_cnt, "deadline_soon": len(deadline_soon), "closed": closed,
                   "open_capital": sum(len(v) for v in by_type.values()), "by_type": counts_by_type},
        "deadline_soon": deadline_soon, "new_by_type": by_type, "competition": competition,
        "others": {"unclassified": unclassified, "non_capital": non_capital}, "notes": notes,
    }
    (ws / "02_analyst_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"분석 완료 (기준 {base}): 수도권 진행/예정 {out['counts']['open_capital']}건 · 신규 {new_cnt} · 임박 {len(deadline_soon)} · 마감 {closed} · 결과집계 {len(competition)}")
    for t, v in by_type.items():
        print(f"  - {t}: {len(v)}건")
    for n in notes:
        print("  ·", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
