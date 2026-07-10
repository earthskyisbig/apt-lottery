#!/usr/bin/env python3
"""
청약홈 분양정보 조회 서비스(odcloud stage 37000) 직접 수집기.

5개 상세조회 엔드포인트에서 최근 공고를 페이징 병합으로 전량 수집해
_workspace/ 에 raw JSON 으로 저장한다. 필터링/가공은 하지 않는다(analyst 담당).

인증: ODCLOUD_SERVICE_KEY (data.go.kr "일반 인증키 Decoding" 값).
  - 1차: serviceKey 쿼리 파라미터(디코딩 키 → requests 가 1회 인코딩)
  - 401 시: Authorization 헤더로 재시도(키 형태 차이 흡수)

사용:
  python fetch_subscriptions.py --out ../../../../_workspace --lookback-days 90
환경변수 ODCLOUD_SERVICE_KEY 또는 프로젝트 루트 .env 에서 키를 읽는다.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from urllib import request as urlrequest, parse as urlparse, error as urlerror

BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1"

# (label, endpoint, 날짜필터 포맷)  — RCRIT_PBLANC_DE 포맷이 엔드포인트마다 다름
ENDPOINTS = [
    ("APT_일반",          "getAPTLttotPblancDetail",           "dash"),   # YYYY-MM-DD
    ("APT_무순위잔여",     "getRemndrLttotPblancDetail",        "dash"),
    ("오피스텔생활숙박",   "getUrbtyOfctlLttotPblancDetail",     "dash"),
    ("공공지원민간임대",   "getPblPvtRentLttotPblancDetail",     "plain"),  # YYYYMMDD
    ("임의공급",          "getOPTLttotPblancDetail",           "plain"),
]


def load_service_key():
    key = os.environ.get("ODCLOUD_SERVICE_KEY", "").strip()
    if key:
        return key
    # 프로젝트 루트 .env 탐색 (스크립트 기준 상위로 올라가며)
    here = Path(__file__).resolve()
    for parent in here.parents:
        env = parent / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("ODCLOUD_SERVICE_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _http_get(url, headers=None, timeout=30):
    req = urlrequest.Request(url, headers=headers or {})
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8")


def _base_query(params):
    """serviceKey 를 제외한 나머지 파라미터를 인코딩한 쿼리 문자열."""
    return urlparse.urlencode(params)


def fetch_page(endpoint, key, params):
    """인증키 형태(Encoding/Decoding)를 몰라도 '구동되는' 방식을 자동 탐색.

    포털은 Encoding 또는 Decoding 키 중 환경에 맞는 것을 쓰라고 안내한다.
    아래 4가지를 순서대로 시도하고, 401이 아니면 그 응답을 채택한다:
      1) Decoding 키로 가정 → serviceKey 를 URL 인코딩(특수문자 +,/,= 처리)
      2) Encoding 키로 가정 → serviceKey 를 그대로(이미 %-인코딩됨) 부착
      3) Authorization 헤더에 키 그대로
      4) Authorization 헤더에 디코딩한 키
    """
    base_q = _base_query(params)
    attempts = [
        # (url, headers)
        (f"{BASE}/{endpoint}?{base_q}&serviceKey={urlparse.quote(key, safe='')}", None),
        (f"{BASE}/{endpoint}?{base_q}&serviceKey={key}", None),
        (f"{BASE}/{endpoint}?{base_q}", {"Authorization": key}),
        (f"{BASE}/{endpoint}?{base_q}", {"Authorization": urlparse.unquote(key)}),
    ]
    last = None
    for url, headers in attempts:
        try:
            _, body = _http_get(url, headers=headers)
            return json.loads(body)
        except urlerror.HTTPError as e:
            last = {"error": f"HTTP {e.code}", "message": e.read().decode("utf-8", "ignore")[:300]}
            if e.code != 401:
                return last  # 401 외 오류는 인증 문제 아님 → 즉시 반환
        except Exception as e:  # noqa
            last = {"error": "request_failed", "message": str(e)[:300]}
    return last or {"error": "unknown"}


def collect_endpoint(label, endpoint, date_fmt, key, since_str_dash, since_str_plain):
    since = since_str_dash if date_fmt == "dash" else since_str_plain
    base_params = {
        "page": 1,
        "perPage": 100,
        "returnType": "JSON",
        "cond[RCRIT_PBLANC_DE::GTE]": since,
    }
    first = fetch_page(endpoint, key, base_params)
    if "error" in first:
        return {"label": label, "endpoint": endpoint, "error": first["error"],
                "message": first.get("message", ""), "items": [], "total_count": 0}
    total = first.get("totalCount", 0)
    # matchCount 는 cond 필터가 반영된 건수. totalCount 는 종종 필터 미반영(전체) 값이라
    # 종료 기준으로 못 쓴다. 종료는 '부분/빈 페이지'로 판정한다.
    match = first.get("matchCount") or 0
    per = base_params["perPage"]
    page_data = first.get("data", [])
    items = list(page_data)
    pages = 1
    while len(page_data) == per:          # 직전 페이지가 꽉 찼을 때만 다음 페이지 시도
        pages += 1
        p = dict(base_params); p["page"] = pages
        nxt = fetch_page(endpoint, key, p)
        page_data = nxt.get("data") if isinstance(nxt, dict) else None
        if not page_data:
            break
        items.extend(page_data)
        time.sleep(0.2)                   # rate 완화
    return {"label": label, "endpoint": endpoint,
            "total_count": total, "match_count": match,
            "collected": len(items), "pages": pages, "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="_workspace 출력 디렉토리")
    ap.add_argument("--lookback-days", type=int, default=90,
                    help="RCRIT_PBLANC_DE 기준 최근 N일 공고 수집 (기본 90)")
    args = ap.parse_args()

    key = load_service_key()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    base_date = dt.date.today()
    since = base_date - dt.timedelta(days=args.lookback_days)
    since_dash = since.strftime("%Y-%m-%d")
    since_plain = since.strftime("%Y%m%d")

    meta = {"base_date": base_date.isoformat(), "lookback_days": args.lookback_days,
            "since": since_dash, "endpoints": [], "auth_ok": True}

    if not key:
        meta["auth_ok"] = False
        meta["error"] = "ODCLOUD_SERVICE_KEY 미설정 — .env 에 키를 넣으세요."
        (out / "01_collector_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("ERROR: 서비스키 없음. .env 의 ODCLOUD_SERVICE_KEY 설정 필요.", file=sys.stderr)
        return 2

    all_notices = []
    for label, endpoint, date_fmt in ENDPOINTS:
        res = collect_endpoint(label, endpoint, date_fmt, key, since_dash, since_plain)
        # 각 유형 원천 저장
        (out / f"01_collector_{label}.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        # 유형 라벨을 붙여 통합 목록에 추가
        for it in res.get("items", []):
            it["_house_type"] = label
            all_notices.append(it)
        meta["endpoints"].append({k: res.get(k) for k in
                                  ("label", "endpoint", "match_count", "collected", "pages", "error", "message")})
        if res.get("error") == "HTTP 401":
            meta["auth_ok"] = False

    (out / "01_collector_notices.json").write_text(
        json.dumps({"count": len(all_notices), "items": all_notices},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    meta["notice_count"] = len(all_notices)
    (out / "01_collector_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"수집 완료: {len(all_notices)}건 / 유형 {len(ENDPOINTS)}개 / 기준 {since_dash}~")
    for e in meta["endpoints"]:
        tail = f" [ERROR {e['error']}]" if e.get("error") else ""
        print(f"  - {e['label']}: {e.get('collected',0)}건{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
