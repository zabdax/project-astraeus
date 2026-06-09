import sys
import os
import threading
import faulthandler
import numpy as np

# Enable faulthandler for traceback dumping
faulthandler.enable()

def force_traceback():
    print("\n--- TIMEOUT REACHED (15.0s) - DUMPING THREAD STACKS ---\n", file=sys.stderr)
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    os._exit(1)

timer = threading.Timer(15.0, force_traceback)
timer.start()

try:
    import lightkurve as lk
    from astraeus.core.ingestion import RemoteDiscoveryEngine

    metadata = {'pl_name': 'WASP-12 b', 'st_rad': 1.69, 'pl_orbper': 1.091418901}
    canonical = RemoteDiscoveryEngine._normalize_target_name(metadata['pl_name'])
    
    print(f"Starting Lightkurve search for {canonical}...")
    
    search_tess = lk.search_lightcurve(canonical, author="SPOC")
    search_kepler = lk.search_lightcurve(canonical, author="Kepler")
    print(f"Found {len(search_tess)} TESS and {len(search_kepler)} Kepler results.")

    lc_list = []
    
    print("Entering download loops...")
    
    for row in search_tess:
        for attempt in range(3):
            try:
                lc = row.download()
                if lc is not None:
                    lc_list.append(lc)
                break
            except Exception as e:
                if RemoteDiscoveryEngine._is_fits_corruption(e):
                    RemoteDiscoveryEngine._wipe_lightkurve_cache()
                if attempt == 2:
                    print(f"Skipping a problematic sector due to network cut: {e}")

    for row in search_kepler:
        for attempt in range(3):
            try:
                lc = row.download()
                if lc is not None:
                    lc_list.append(lc)
                break
            except Exception as e:
                if RemoteDiscoveryEngine._is_fits_corruption(e):
                    RemoteDiscoveryEngine._wipe_lightkurve_cache()
                if attempt == 2:
                    print(f"Skipping a problematic sector due to network cut: {e}")

    print("DOWNLOAD COMPLETE: Processing data arrays...")
    if lc_list:
        lc_collection = lk.LightCurveCollection(lc_list)
        print("Collection created.")
    
    print("Success. Download finished.")

finally:
    timer.cancel()
