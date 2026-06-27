import sys
import os
import json

# Setup sys.path to ensure astraeus is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from astraeus.core.ingestion import RemoteDiscoveryEngine
from astraeus.analysis.detection import detect_transit_candidate
from astraeus.core.orchestrator import run_multi_planet_search

TEST_CASES = [
    {"target": "TRAPPIST-1", "source": "TESS", "depth": 5, "snr": 5.0},
    {"target": "Kepler-11", "source": "Kepler", "depth": 6, "snr": 6.0},
    {"target": "WASP-12 b", "source": "Kepler", "depth": 1, "snr": 10.0},
    {"target": "K2-138", "source": "Kepler", "depth": 5, "snr": 5.5},
    {"target": "Kepler-20", "source": "Kepler", "depth": 5, "snr": 4.5},
    {"target": "AU Mic", "source": "TESS", "depth": 2, "snr": 6.0},
    {"target": "HD 80606 b", "source": "TESS", "depth": 1, "snr": 7.0},
    {"target": "TOI-700", "source": "TESS", "depth": 3, "snr": 4.8},
    {"target": "Kepler-4 d", "source": "Kepler", "depth": 1, "snr": 6.5},
    {"target": "Kepler-90", "source": "Kepler", "depth": 7, "snr": 5.0},
]

def main():
    results = []
    for idx, case in enumerate(TEST_CASES):
        print(f"Running Case {idx+1}: {case['target']}")
        res = RemoteDiscoveryEngine.fetch_data(case['target'], case['source'])
        status = res.get('status')
        if status != 'success':
            print(f"  Fetch failed: {res.get('reason', status)}")
            results.append({"case": case, "error": f"Fetch failed: {res.get('reason', status)}"})
            continue
            
        time_arr = res['time']
        flux_arr = res['flux']
        metadata = res.get('metadata', {})
        
        try:
            if case['depth'] > 1:
                raw_lc = {
                    'time': time_arr, 'flux': flux_arr,
                    'target_name': case['target'], 'data_source': case['source'],
                    'metadata': metadata
                }
                cands = run_multi_planet_search(raw_lc, max_signals=case['depth'], snr_floor=case['snr'])
                planets = len(cands)
                if planets > 0:
                    best_snr = cands[0].get('snr', 0)
                    lowest_snr = min(c.get('snr', 0) for c in cands)
                    periods = [c.get('period', 0) for c in cands]
                    print(f"  Found {planets} planets. Periods: {periods}")
                    results.append({"case": case, "planets": planets, "lowest_snr": lowest_snr, "periods": periods, "cands": cands})
                else:
                    print(f"  Found 0 planets.")
                    results.append({"case": case, "planets": 0, "lowest_snr": 0, "periods": [], "cands": []})
            else:
                cands = detect_transit_candidate(time_arr, flux_arr, target_name=case['target'], data_source=case['source'], metadata=metadata)
                if isinstance(cands, list) and len(cands) > 0:
                    best = cands[0].get('candidate_1', {})
                else:
                    best = cands if isinstance(cands, dict) else {}
                
                if best:
                    print(f"  Found 1 planet. Period: {best.get('period')}")
                    results.append({"case": case, "planets": 1, "lowest_snr": best.get('snr', 0), "periods": [best.get('period', 0)], "cands": [best]})
                else:
                    print(f"  Found 0 planets.")
                    results.append({"case": case, "planets": 0, "lowest_snr": 0, "periods": [], "cands": []})
        except Exception as e:
            print(f"  Exception: {e}")
            results.append({"case": case, "error": str(e)})

    with open("tests/backend_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
