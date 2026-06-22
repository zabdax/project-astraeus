import json
import warnings

warnings.filterwarnings('ignore')

from astraeus.data.loader import universal_load_lightcurve
from astraeus.core.orchestrator import run_multi_planet_search

def main():
    target = 'KIC 11442793'
    print(f"Fetching data for {target}...")
    # Fetch data (NASAArchiveLoader)
    t, f, e = universal_load_lightcurve('api', target, mission='Kepler')
    
    raw_lightcurve = {
        'time': t,
        'flux': f,
        'target_name': target,
        'data_source': 'NASA Exoplanet Archive',
        'metadata': {}
    }
    
    print(f"Starting multi-planet search with max_signals=5, snr_floor=5.0")
    results = run_multi_planet_search(raw_lightcurve, max_signals=5, snr_floor=5.0)
    
    # The output requirement: Print the final consolidated discovery payload in JSON format,
    # detailing every verified candidate found, their respective periods, and the total number 
    # of iterations executed before safe shutdown.
    
    payload = {
        "target": target,
        "total_iterations_executed": len(results) + 1,  # +1 because the last one broke or we hit max
        "candidates": []
    }
    
    for idx, r in enumerate(results):
        payload["candidates"].append({
            "iteration": idx + 1,
            "period": r.get("period"),
            "snr": r.get("snr"),
            "vetting_status": r.get("vetting_status"),
            "depth": r.get("depth"),
            "duration": r.get("duration"),
            "t0": r.get("t0")
        })
        
    print("\nFINAL CONSOLIDATED DISCOVERY PAYLOAD:")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
