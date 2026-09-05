#!/usr/bin/env python3
"""
청약홈 주택형별·경쟁률·당첨가점·특공신청현황 수집기 (분양정보 37000 Mdl + 경쟁률 36148).

fetch_subscriptions.py 가 만든 01_collector_notices.json 의 공고(HOUSE_MANAGE_NO·PBLANC_NO)를 순회하며
공고별로 아래를 EQ 조회해 원본 그대로 01_collector_stats.json 에 저장한다. 해석은 analyst 몫이다.

  유형              주택형별(37000)                 경쟁률(36148)                      가점 / 특공신청현황(36148, APT만)
  APT_일반          getAPTLttotPblancMdl            getAPTLttotPblancCmpet             getAptLttotPblancScore / getAPTSpsplyReqstStus
  APT_무순위잔여     getRemndrLttotPblancMdl         getRemndrLttotPblancCmpet(→취소후재공급 폴백)
  오피스텔생활숙박   getUrbtyOfctlLttotPblancMdl     getUrbtyOfctlLttotPblancCmpet
  공공지원민간임대   getPblPvtRentLttotPblancMdl     getPblPvtRentLttotPblancCmpet
  임의공급          getOPTLttotPblancMdl            getOPTLttotPblancCmpet

경쟁률 서비스에는 날짜 필터가 없다(주택관리번호·공고번호 EQ 만 가능) → 공고 수만큼 호출한다.
같은 ODCLOUD_SERVICE_KEY 로 두 서비스 모두 호출된다(2026-09-05 라이브 확인).

사용:
  python fetch_stats.py --workspace _workspace [--max-notices 5] [--skip-not-started]
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from urllib import request as urlrequest, parse as urlparse, error as urlerror

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_subscriptions import load_service_key  # noqa: E402

DETAIL = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"
CMPET = "https://api.odcloud.kr/api/ApplyhomeInfoCmpetRtSvc/v1"

# 유형별 엔드포인트 계획. (키, base, endpoint)
PLAN = {
    "APT_일반": [
        ("models", DETAIL, "getAPTLttotPblancMdl"),
        ("cmpet", CMPET, "getAPTLttotPblancCmpet"),
        ("score", CMPET, "getAptLttotPblancScore"),
        ("spsply", CMPET, "getAPTSpsplyReqstStus"),
    ],
    "APT_무순위잔여": [
        ("models", DETAIL, "getRemndrLttotPblancMdl"),
        ("cmpet", CMPET, "getRemndrLttotPblancCmpet"),
        ("cmpet_cancel", CMPET, "getCancResplLttotPblancCmpet"),  # 취소후재공급은 별도 엔드포인트
    ],
    "오피스텔생활숙박": [
        ("models", DETAIL, "getUrbtyOfctlLttotPblancMdl"),
        ("cmpet", CMPET, "getUrbtyOfctlLttotPblancCmpet"),
    ],
    "공공지원민간임대": [
        ("models", DETAIL, "getPblPvtRentLttotPblancMdl"),
        ("cmpet", CMPET, "getPblPvtRentLttotPblancCmpet"),
    ],
    "임의공급": [
        ("models", DETAIL, "getOPTLttotPblancMdl"),
        ("cmpet", CMPET, "getOPTLttotPblancCmpet"),
    ],
}


def _get(url, headers=None, timeout=30):
    req = urlrequest.Request(url, headers=headers or {})
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch(base, endpoint, key, params):
    """fetch_subscriptions 와 동일한 인증 폴백(쿼리 quote/raw → 헤더 raw/unquote)."""
    q = urlparse.urlencode(params)
    attempts = [
        (f"{base}/{endpoint}?{q}&serviceKey={urlparse.quote(key, safe='')}", None),
        (f"{base}/{endpoint}?{q}&serviceKey={key}", None),
        (f"{base}/{endpoint}?{q}", {"Authorization": key}),
        (f"{base}/{endpoint}?{q}", {"Authorization": urlparse.unquote(key)}),
    ]
    last = None
    for url, headers in attempts:
        try:
            return _get(url, headers)
        except urlerror.HTTPError as e:
            last = {"error": f"HTTP {e.code}", "message": e.read().decode("utf-8", "ignore")[:200]}
            if e.code != 401:
                return last
        except Exception as e:  # noqa
            last = {"error": "request_failed", "message": str(e)[:200]}
    return last or {"error": "unknown"}


def fetch_all_pages(base, endpoint, key, hm, pb):
    rows, page, per = [], 1, 100
    while True:
        params = {"page": page, "perPage": per, "returnType": "JSON",
                  "cond[HOUSE_MANAGE_NO::EQ]": hm, "cond[PBLANC_NO::EQ]": pb}
        r = fetch(base, endpoint, key, params)
        if "error" in r:
            return rows, r
        data = r.get("data") or []
        rows.extend(data)
        if len(data) < per:
            return rows, None
        page += 1
        time.sleep(0.1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="_workspace")
    ap.add_argument("--max-notices", type=int, default=0, help="테스트용: 유형별 최대 N건만")
    ap.add_argument("--skip-not-started", action="store_true",
                    help="접수 시작 전 공고는 경쟁률 계열(cmpet/score/spsply) 호출 생략(주택형별은 항상 수집)")
    args = ap.parse_args()

    ws = Path(args.workspace)
    src = ws / "01_collector_notices.json"
    if not src.exists():
        print(f"ERROR: {src} 없음 — fetch_subscriptions.py 를 먼저 실행하세요.", file=sys.stderr)
        return 2
    key = load_service_key()
    meta = {"base_date": dt.date.today().isoformat(), "collected_at": dt.datetime.now().isoformat(timespec="seconds"),
            "auth_ok": True, "calls": 0, "by_type": {}, "errors": []}
    if not key:
        meta["auth_ok"] = False; meta["error"] = "ODCLOUD_SERVICE_KEY 미설정"
        (ws / "01_collector_stats.json").write_text(json.dumps({"meta": meta, "by_notice": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ERROR: 서비스키 없음", file=sys.stderr); return 2

    notices = json.loads(src.read_text(encoding="utf-8")).get("items", [])
    today = dt.date.today().isoformat()
    by_notice, per_type_count = {}, {}
    for it in notices:
        ht = it.get("_house_type")
        hm, pb = str(it.get("HOUSE_MANAGE_NO", "")), str(it.get("PBLANC_NO", ""))
        if ht not in PLAN or not hm or not pb:
            continue
        if args.max_notices and per_type_count.get(ht, 0) >= args.max_notices:
            continue
        per_type_count[ht] = per_type_count.get(ht, 0) + 1
        # 접수 시작일(유형별 필드 상이) — 없으면 '시작됨'으로 간주
        start = None
        for k in ("RCEPT_BGNDE", "SUBSCRPT_RCEPT_BGNDE", "GNRL_RNK1_CRSPAREA_RCPTDE"):
            v = it.get(k)
            if v:
                start = str(v); break
        if start and len(start) == 8 and start.isdigit():
            start = f"{start[:4]}-{start[4:6]}-{start[6:]}"
        not_started = bool(start) and start > today

        rec = {"house_type": ht, "house_nm": it.get("HOUSE_NM"), "pblanc_no": pb,
               "rcept_bgnde": start, "region": it.get("SUBSCRPT_AREA_CODE_NM")}
        for section, base, ep in PLAN[ht]:
            if args.skip_not_started and not_started and section != "models":
                rec[section] = {"skipped": "not_started"}
                continue
            rows, err = fetch_all_pages(base, ep, key, hm, pb)
            meta["calls"] += 1
            if err:
                rec[section] = {"error": err["error"], "message": err.get("message", ""), "rows": rows}
                meta["errors"].append({"hm": hm, "section": section, "endpoint": ep, "error": err["error"]})
                if err["error"] == "HTTP 401":
                    meta["auth_ok"] = False
            else:
                rec[section] = {"endpoint": ep, "count": len(rows), "rows": rows}
            time.sleep(0.1)
        by_notice[hm] = rec
        t = meta["by_type"].setdefault(ht, {"notices": 0, "with_models": 0, "with_cmpet": 0})
        t["notices"] += 1
        if rec.get("models", {}).get("count"):
            t["with_models"] += 1
        if rec.get("cmpet", {}).get("count") or rec.get("cmpet_cancel", {}).get("count"):
            t["with_cmpet"] += 1
        print(f"  {ht} {hm} {rec['house_nm']}: " + ", ".join(
            f"{s}={rec[s].get('count', rec[s].get('error', rec[s].get('skipped')))}" for s, _, _ in PLAN[ht]))

    out = {"meta": meta, "by_notice": by_notice}
    (ws / "01_collector_stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"통계 수집 완료: 공고 {len(by_notice)}건 / 호출 {meta['calls']}회 / 에러 {len(meta['errors'])}건 → {ws/'01_collector_stats.json'}")
    for ht, t in meta["by_type"].items():
        print(f"  - {ht}: {t['notices']}건 (주택형 {t['with_models']} · 경쟁률 {t['with_cmpet']})")
    return 0 if meta["auth_ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
