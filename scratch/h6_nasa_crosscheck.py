"""
Phase 1, H6 diagnostic protocol - NASA Exoplanet Archive cross-check.

Fetches pscomppars reference data for Kepler-90 and TRAPPIST-1 systems.
Pure reference data fetch - no Astraeus code is invoked.

Notes on hostnames
------------------
The NASA Exoplanet Archive `pscomppars` table does not always store the
canonical name as `hostname`. Investigation (during this run) showed:
  - "TRAPPIST-1" -> stored as hostname 'TRAPPIST-1' (works directly).
  - "Kepler-90"  -> stored as hostname 'KOI-351' (the canonical name is
                    attached via pl_name, e.g. 'Kepler-90 i').
To stay faithful to the original task spec, we first issue the exact
hostname query that was requested, and if it returns 0 data rows we fall
back to a `pl_name LIKE '<canonical> %'` query (also restricted to the
known canonical system) and clearly mark which path produced the rows.
"""
import csv
import io
import sys
import requests
from typing import List, Dict, Any, Optional

TAP_BASE = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
TIMEOUT_S = 30
SELECT_COLS = "pl_name,pl_orbper,pl_trandep,pl_tranmid,pl_rade,pl_eqt,pl_bmasse"


def build_query_url(where_clause: str) -> str:
    q = f"SELECT+{SELECT_COLS}+FROM+pscomppars+WHERE+{where_clause}+ORDER+BY+pl_orbper"
    return f"{TAP_BASE}?query={q}&format=csv"


def fetch(url: str, label: str) -> Optional[str]:
    print(f"\n[FETCH] {label}")
    print(f"[URL]   {url}")
    try:
        r = requests.get(url, timeout=TIMEOUT_S)
        print(f"[HTTP]  status={r.status_code}  bytes={len(r.content)}")
        if r.status_code != 200:
            print(f"[ERROR] HTTP {r.status_code}: {r.text[:300]}")
            return None
        text = r.text
        if len(text) > 500:
            print(f"[RAW]   (truncated to 500 chars):\n{text[:500]}\n[...]")
        else:
            print(f"[RAW]\n{text}")
        return text
    except requests.RequestException as e:
        print(f"[ERROR] RequestException: {e}")
        return None


def to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    s = s.strip()
    if s == "" or s.lower() in ("null", "nan", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def compute_depth_ppm(trandep_str: Optional[str]) -> Optional[float]:
    """pscomppars pl_trandep is documented as a fractional value
    (depth = (Rp/Rs)^2). The TRAPPIST-1 rows we received, however, are
    already in percent-ish scale (~0.7 for a ~0.7% transit). Per the
    task instructions: if |val| < 1, treat as fractional and scale by 1e6
    to get ppm.
    """
    v = to_float(trandep_str)
    if v is None:
        return None
    if abs(v) < 1.0:
        return v * 1e6
    return v


def infer_t0_units(values: List[Optional[float]]) -> str:
    clean = [v for v in values if v is not None]
    if not clean:
        return "UNKNOWN (no t0 values)"
    lo, hi = min(clean), max(clean)
    print(f"  [t0 range] min={lo:.4f}  max={hi:.4f}")
    if all(120.0 <= v <= 300.0 for v in clean):
        return "BKJD (BJD-2454833) - tight Kepler window"
    if 100.0 <= lo and hi <= 3000.0:
        return "BKJD (BJD-2454833)"
    if 2454000.0 <= lo and hi <= 2461000.0:
        return "BJD (full)"
    if 2400000.0 <= lo and hi <= 2500000.0:
        return "BJD-like (MJD? check - MJD ~ 50000-60000)"
    return f"UNKNOWN (range {lo:.2f}..{hi:.2f})"


def parse_rows(raw: str) -> List[Dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw))
    return list(reader)


def process_target(canonical: str) -> Dict[str, Any]:
    """Try hostname='<canonical>' first, fall back to pl_name LIKE."""
    # 1) primary query
    primary_url = build_query_url(f"hostname='{canonical}'")
    raw_primary = fetch(primary_url, f"hostname='{canonical}'")
    used_fallback = False
    raw = raw_primary
    fallback_url = None

    if raw is not None:
        rows = parse_rows(raw)
        if not rows:
            # 2) fallback: pl_name LIKE
            fallback_url = build_query_url(f"pl_name+LIKE+'{canonical} %'")
            print(f"\n[NOTE]  Primary hostname query returned 0 rows.")
            print(f"[NOTE]  Falling back to pl_name LIKE query.")
            raw = fetch(fallback_url, f"pl_name LIKE '{canonical} %'")
            used_fallback = True
            if raw is None:
                return {"canonical": canonical, "rows": [], "t0_units": "UNRESOLVED",
                        "anomalies": ["Both primary and fallback HTTP failed"]}
            rows = parse_rows(raw)
    else:
        return {"canonical": canonical, "rows": [], "t0_units": "UNRESOLVED",
                "anomalies": ["Primary HTTP failed"]}

    n = len(rows)
    print(f"\n[PARSE] {canonical}: {n} rows  (used_fallback={used_fallback})")

    t0_values: List[Optional[float]] = []
    parsed_rows: List[Dict[str, Any]] = []
    anomalies: List[str] = []

    for i, row in enumerate(rows, start=1):
        name = (row.get("pl_name") or "").strip()
        period = to_float(row.get("pl_orbper"))
        trandep = row.get("pl_trandep")
        t0 = to_float(row.get("pl_tranmid"))
        rade = to_float(row.get("pl_rade"))
        eqt = to_float(row.get("pl_eqt"))
        bmasse = to_float(row.get("pl_bmasse"))
        depth_ppm = compute_depth_ppm(trandep)

        if t0 is not None:
            t0_values.append(t0)
        if t0 is not None and t0 < 0:
            anomalies.append(f"{name}: negative t0={t0}")
        if period is None:
            anomalies.append(f"{name}: NULL period")
        if rade is None:
            anomalies.append(f"{name}: NULL radius")
        if depth_ppm is None:
            anomalies.append(f"{name}: NULL trandep (depth_ppm cannot be derived)")

        parsed_rows.append({
            "pl_name": name,
            "period_days": period,
            "depth_ppm": depth_ppm,
            "t0": t0,
            "planet_radius_earth": rade,
            "eq_temp_K": eqt,
            "mass_earth": bmasse,
        })

        print(
            f"  [{i:2d}] {name:<20s} "
            f"P={period if period is not None else 'NULL':>12} d  "
            f"depth_ppm={depth_ppm if depth_ppm is not None else 'NULL':>14}  "
            f"t0={t0 if t0 is not None else 'NULL':>16}  "
            f"R={rade if rade is not None else 'NULL':>10} Re  "
            f"Teq={eqt if eqt is not None else 'NULL':>8} K  "
            f"M={bmasse if bmasse is not None else 'NULL':>10} Me"
        )

    t0_units = infer_t0_units(t0_values)
    print(f"  [t0 units inferred] {t0_units}")
    if anomalies:
        print(f"  [ANOMALIES]")
        for a in anomalies:
            print(f"    - {a}")
    else:
        print(f"  [ANOMALIES] none")

    return {
        "canonical": canonical,
        "rows": parsed_rows,
        "t0_units": t0_units,
        "anomalies": anomalies,
        "used_fallback": used_fallback,
    }


def print_final_table(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 110)
    print("FINAL REFERENCE TABLE  (source: NASA Exoplanet Archive / pscomppars)")
    print("=" * 110)
    for res in results:
        canonical = res["canonical"]
        print(f"\n# {canonical}  (t0_units_inferred: {res['t0_units']})"
              f"  [used_fallback={res.get('used_fallback', False)}]")
        print("-" * 110)
        header = (f"{'pl_name':<22s} {'period_d':>12s} {'depth_ppm':>14s} "
                  f"{'t0':>18s} {'R_earth':>10s} {'Teq_K':>8s} {'M_earth':>10s}")
        print(header)
        print("-" * 110)
        for row in res["rows"]:
            def fmt(v, w, prec=None):
                if v is None:
                    return f"{'NULL':>{w}}"
                if prec is None:
                    return f"{v:{w}.6g}"
                return f"{v:{w}.{prec}f}"
            print(
                f"{row['pl_name']:<22s} "
                f"{fmt(row['period_days'], 12):>12s} "
                f"{fmt(row['depth_ppm'], 14, 1):>14s} "
                f"{fmt(row['t0'], 18, 4):>18s} "
                f"{fmt(row['planet_radius_earth'], 10, 3):>10s} "
                f"{fmt(row['eq_temp_K'], 8, 1):>8s} "
                f"{fmt(row['mass_earth'], 10, 3):>10s}"
            )
        if res.get("anomalies"):
            print(f"  Anomalies: {len(res['anomalies'])} -> {res['anomalies']}")
        else:
            print(f"  Anomalies: 0")


def main():
    print("=" * 110)
    print("Phase 1, H6 - NASA Exoplanet Archive pscomppars cross-check")
    print(f"TAP endpoint: {TAP_BASE}")
    print(f"Targets: Kepler-90, TRAPPIST-1")
    print("=" * 110)

    results = [process_target(c) for c in ("Kepler-90", "TRAPPIST-1")]
    print_final_table(results)

    print("\n" + "=" * 110)
    print("SUMMARY")
    print("=" * 110)
    for res in results:
        print(f"  {res['canonical']}: {len(res['rows'])} planets returned, "
              f"t0_units={res['t0_units']}, "
              f"anomalies={len(res.get('anomalies', []))}, "
              f"used_fallback={res.get('used_fallback', False)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        raise
