import batman
import numpy as np
import json

def test_batman(period, t0, duration, depth):
    time = np.linspace(t0 - duration*2, t0 + duration*2, 100)
    
    rp = np.sqrt(depth)
    a = (period / np.pi) * (1.0 + rp) / duration
    
    params = batman.TransitParams()
    params.t0 = t0
    params.per = period
    params.rp = rp
    params.a = a
    params.inc = 90.
    params.ecc = 0.
    params.w = 90.
    params.u = [0.1, 0.3]
    params.limb_dark = "quadratic"
    
    m = batman.TransitModel(params, time)
    flux = m.light_curve(params)
    return flux

f = test_batman(10.0, 0.0, 0.1, 0.01)
print(f"min flux: {np.min(f)}")
