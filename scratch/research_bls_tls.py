import numpy as np
from astropy.timeseries import BoxLeastSquares

time = np.linspace(0, 100, 1000)
flux = np.random.normal(1, 0.001, 1000)
bls = BoxLeastSquares(time, flux)
periods = bls.autoperiod(0.1)
print(f"Astropy BLS autoperiod returns {len(periods)} periods. Min: {periods.min()}, Max: {periods.max()}")

try:
    import transitleastsquares as tls
    model = tls.transitleastsquares(time, flux)
    results = model.power()
    print(f"TLS results: period={results.period}")
except ImportError as e:
    print(f"TLS import failed: {e}")
except Exception as e:
    print(f"TLS execution failed: {e}")
