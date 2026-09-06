#!/usr/bin/env python3
"""
청약 자격진단 웹앱 빌더.
analyst의 02_analyst_summary.json을 읽어 공고를 평탄화하고,
webapp-template.html 의 __DATA__ 자리에 주입해 자기완결 HTML을 만든다.
매칭 로직은 템플릿의 JS(브라우저)에 있고, 이 스크립트는 데이터 주입만 한다.
"""
import argparse
import json
import sys
from pathlib import Path

# 웹앱 카드에 필요한 필드만 추림 (파일 크기 억제)
KEEP = ("id", "name", "type", "location", "region", "apply_start", "apply_end",
        "winner_date", "builder", "supply_scale", "url", "dday", "tag",
        "house_dtl", "house_secd", "is_public", "regulation", "price_range_manwon", "areas", "strategy_signals")
MODEL_KEEP = ("ty", "area", "suffix", "supply_general", "supply_special", "special", "price_manwon")


def slim_model(m):
    return {k: m.get(k) for k in MODEL_KEEP if m.get(k) not in (None, {}, "")}


def flatten(summary):
    """deadline_soon + new_by_type 을 한 배열로 합치고 중복 제거. 주택형은 요약만 싣는다."""
    rows, seen = [], set()
    buckets = list(summary.get("deadline_soon", []))
    for items in (summary.get("new_by_type") or {}).values():
        buckets.extend(items)
    for it in buckets:
        key = (it.get("id") or it.get("name"), it.get("apply_end"), it.get("type"))
        if key in seen:
            continue
        seen.add(key)
        row = {k: it.get(k) for k in KEEP if it.get(k) is not None}
        if it.get("models"):
            row["models"] = [slim_model(m) for m in it["models"]]
        rows.append(row)
    return rows


def reference_results(summary):
    """접수 종료 단지 결과 → 웹앱이 '같은 지역 최근 특공 경쟁률·최저가점'을 근거로 쓰도록 압축."""
    out = []
    for it in summary.get("competition", []):
        r = it.get("result") or {}
        if r.get("status") != "집계":
            continue
        out.append({
            "name": it.get("name"), "type": it.get("type"), "region": it.get("region"),
            "apply_end": it.get("apply_end"), "max_rate": r.get("max_rate"),
            "short": sum(u.get("short", 0) for u in r.get("undersubscribed", [])),
            "min_lwet": r.get("min_lwet"),
            "special": {k: v.get("rate") for k, v in (r.get("special") or {}).items()},
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="_workspace", help="analyst 산출물 디렉토리")
    ap.add_argument("--out", default="reports", help="웹앱 출력 디렉토리")
    args = ap.parse_args()

    src = Path(args.workspace) / "02_analyst_summary.json"
    if not src.exists():
        print(f"ERROR: {src} 없음. analyst 단계를 먼저 실행하세요.", file=sys.stderr)
        return 2

    summary = json.loads(src.read_text(encoding="utf-8"))
    notices = flatten(summary)
    if not notices:
        print("WARN: 공고 0건 — 빈 웹앱을 만듭니다(안내 문구 노출).", file=sys.stderr)

    tpl = Path(__file__).resolve().parents[1] / "assets" / "webapp-template.html"
    html = tpl.read_text(encoding="utf-8")

    payload = {
        "report_date": summary.get("report_date", "정보 없음"),
        "counts": summary.get("counts", {}),
        "notes": summary.get("notes", []),
        "notices": notices,
        "results": reference_results(summary),
    }
    # </script> 가 JSON 문자열에 들어가면 스크립트 블록이 조기 종료됨 → 이스케이프
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = html.replace("__DATA__", data)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "청약자격진단.html"
    out.write_text(html, encoding="utf-8")

    kb = len(html.encode("utf-8")) / 1024
    print(f"웹앱 생성: {out} ({kb:.0f}KB, 공고 {len(notices)}건, 결과 참고 {len(payload['results'])}건, 기준일 {payload['report_date']})")
    by_region = {}
    for n in notices:
        by_region[n.get("region", "?")] = by_region.get(n.get("region", "?"), 0) + 1
    for r, c in sorted(by_region.items(), key=lambda x: -x[1]):
        print(f"  - {r}: {c}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
