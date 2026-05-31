import os
import tempfile
import numpy as np
import pandas as pd
from astraeus.data.loader import universal_load_lightcurve

def test_stress_data_handling():
    """Create a Stress Data file and verify the loader cleans it or raises AssertionError."""
    # 1. Create a "Stress Data" file (CSV) containing: negative flux values, 
    # missing timestamps (NaNs), and out-of-order time indices.
    df = pd.DataFrame({
        "time": [3.0, np.nan, 1.0, 2.0, 4.0],
        "flux": [1.0, 1.0, 1.0, -0.5, 1.0],  # negative flux
        "flux_err": [0.01, 0.01, 0.01, 0.01, 0.01]
    })
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        df.to_csv(f.name, index=False)
        stress_file = f.name
        
    try:
        t, f, e = universal_load_lightcurve('csv', stress_file)
    except AssertionError:
        # The loader raised a clean AssertionError instead of crashing -> PASS
        return
    finally:
        os.remove(stress_file)
        
    # If the loader didn't raise, it MUST have cleaned the data automatically
    assert not np.isnan(t).any(), "NaNs were not cleaned from time array."
    assert not np.isnan(f).any(), "NaNs were not cleaned from flux array."
    assert (f >= 0).all(), "Negative fluxes were not cleaned."
    
    # Check sorting
    assert np.all(np.diff(t) > 0), "Time indices are out of order."


def test_format_mapping():
    """Verify that the loader maps both NASA Exoplanet Archive and Standard CSV formats correctly."""
    
    # NASA Exoplanet Archive Format mock
    nasa_df = pd.DataFrame({
        "BJD": [1.0, 2.0, 3.0],
        "PDCSAP_FLUX": [1.0, 0.99, 1.0],
        "PDCSAP_FLUX_ERR": [0.01, 0.01, 0.01]
    })
    
    # Standard CSV Format mock
    std_df = pd.DataFrame({
        "time": [1.0, 2.0, 3.0],
        "flux": [1.0, 0.99, 1.0],
        "flux_err": [0.01, 0.01, 0.01]
    })
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as fnasa, \
         tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as fstd:
        
        nasa_df.to_csv(fnasa.name, index=False)
        std_df.to_csv(fstd.name, index=False)
        
        nasa_file = fnasa.name
        std_file = fstd.name
        
    try:
        t_nasa, f_nasa, e_nasa = universal_load_lightcurve('csv', nasa_file)
        assert len(t_nasa) == 3
        assert np.array_equal(t_nasa, [1.0, 2.0, 3.0])
        assert np.array_equal(f_nasa, [1.0, 0.99, 1.0])
        
        t_std, f_std, e_std = universal_load_lightcurve('csv', std_file)
        assert len(t_std) == 3
        assert np.array_equal(t_std, [1.0, 2.0, 3.0])
        assert np.array_equal(f_std, [1.0, 0.99, 1.0])
    finally:
        os.remove(nasa_file)
        os.remove(std_file)
