import numpy as np
from scipy.optimize import curve_fit

from astraeus.core.constants import VETTING_U_VS_V_CHI2_DELTA_THRESHOLD

class VettingEngine:
    @staticmethod
    def vet_transit_shape(time: np.ndarray, flux: np.ndarray, period: float, t0: float, duration: float, depth: float, threshold: float = VETTING_U_VS_V_CHI2_DELTA_THRESHOLD) -> dict:
        """
        Statistical Transit Model Fitting engine for vetting planet candidates.
        Performs Bayesian Model Likelihood comparison to differentiate between a planetary transit (U-shape)
        and a grazing/eclipsing binary (V-shape).

        ``threshold`` (default ``VETTING_U_VS_V_CHI2_DELTA_THRESHOLD``) is the minimum
        ``(delta_chi2_u - delta_chi2_v)`` required to label the fit as
        ``"Likely Planet"`` rather than ``"Ambiguous/False Positive"``. See
        ``astraeus/core/constants.py`` and ``reports/bucket10_threshold_audit.md``
        §3 for the empirical derivation. The previous default of 0.0 was a
        category-(c) magic-number flagged in bucket 2 — it required only an
        infinitesimal U-shape advantage over V-shape, with no significance
        floor on the fit itself.
        """
        time = np.asarray(time)
        flux = np.asarray(flux)
        
        # Phase-fold the data
        phase = (time - t0 + 0.5 * period) % period - 0.5 * period
        
        # Local median normalization window = 3x duration
        window_mask = np.abs(phase) < 1.5 * duration
        local_phase = phase[window_mask]
        local_flux = flux[window_mask]
        
        # Data Integrity Guard
        if len(local_flux) < 3:
            return {
                'vetting_status': 'Insufficient Data',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        in_transit_mask = np.abs(local_phase) < 0.5 * duration
        if np.sum(in_transit_mask) < 3:
            return {
                'vetting_status': 'Insufficient Data',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        # Normalization Guard
        local_median = float(np.median(local_flux))
        if local_median == 0 or np.isnan(local_median):
            return {
                'vetting_status': 'Inconclusive',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0
            }
            
        normalized_flux = local_flux / local_median
        
        # Sort for proper fitting
        sort_idx = np.argsort(local_phase)
        p_sorted = local_phase[sort_idx]
        f_sorted = normalized_flux[sort_idx]
        
        try:
            # Model A: U-Shape (Planet) using analytical trapezoid template
            def u_model_template(t):
                dur = duration
                ingress = dur * 0.1
                flux_model = np.ones_like(t)
                phase = np.abs(t)
                
                flat_mask = phase <= (dur / 2.0 - ingress)
                flux_model[flat_mask] = 0.0
                
                slope_mask = (phase > (dur / 2.0 - ingress)) & (phase < dur / 2.0)
                if ingress > 0:
                    flux_model[slope_mask] = 1.0 - (dur / 2.0 - phase[slope_mask]) / ingress
                    
                return 1.0 - flux_model # 1 at max depth, 0 out of transit
                
            u_template = u_model_template(p_sorted)
            
            def u_model_fit(t, d):
                return 1.0 - d * u_template
                
            popt_u, _ = curve_fit(u_model_fit, p_sorted, f_sorted, p0=[depth], bounds=([0.0], [1.0]), maxfev=100)
            f_u_fit = u_model_fit(p_sorted, *popt_u)
            
            # Model B: V-Shape (Grazing/Eclipsing Binary) template
            def v_model_template(t):
                dur = duration
                flux_model = np.ones_like(t)
                in_trans = np.abs(t) < dur / 2.0
                if np.any(in_trans):
                    flux_model[in_trans] = 1.0 - (1.0 - 2.0 * np.abs(t[in_trans]) / dur)
                return 1.0 - flux_model
                
            v_template = v_model_template(p_sorted)
            
            def v_model_fit(t, d):
                return 1.0 - d * v_template
                
            popt_v, _ = curve_fit(v_model_fit, p_sorted, f_sorted, p0=[depth], bounds=([0.0], [1.0]), maxfev=100)
            f_v_fit = v_model_fit(p_sorted, *popt_v)
            
            # Null hypothesis (flat line)
            f_flat = np.ones_like(p_sorted)
            
            # Chi-Squared Minimization
            chi2_flat = np.sum((f_sorted - f_flat)**2)
            chi2_u = np.sum((f_sorted - f_u_fit)**2)
            chi2_v = np.sum((f_sorted - f_v_fit)**2)
            
            delta_chi2_u = chi2_flat - chi2_u
            delta_chi2_v = chi2_flat - chi2_v
            
            # Verdict Logic
            if delta_chi2_u > delta_chi2_v + threshold:
                status = "Likely Planet"
                confidence = 1.0 - (chi2_u / chi2_v) if chi2_v > 0 else 1.0
            else:
                status = "Ambiguous/False Positive"
                confidence = chi2_u / chi2_v if chi2_v > 0 else 0.0
                
            confidence = max(0.0, min(1.0, confidence))
                
            return {
                'vetting_status': status,
                'vetting_confidence': float(confidence),
                'u_shape_chi2': float(chi2_u),
                'v_shape_chi2': float(chi2_v),
                'delta_chi2_u': float(delta_chi2_u),
                'delta_chi2_v': float(delta_chi2_v)
            }
            
        except Exception:
            return {
                'vetting_status': 'Indeterminate',
                'vetting_confidence': 0.0,
                'u_shape_chi2': 0.0,
                'v_shape_chi2': 0.0,
                'delta_chi2_u': 0.0,
                'delta_chi2_v': 0.0
            }
