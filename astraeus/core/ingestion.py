import sys
import re

from astraeus.data.adapter import DataAdapter
from astraeus.core.nasa_archive import NASAExoplanetArchive
from astraeus.core.lightkurve_client import LightkurveClient

# Missions that yield high-cadence time-series photometry. The NASA Archive
# itself is metadata-only, so when a user picks "NASA Exoplanet Archive" we
# transparently bridge into one of these via the resolved target name.
_TIME_SERIES_MISSIONS = ("TESS", "Kepler")

# Recognises host-star designations resolvable by MAST (Kepler-N, K2-N, TIC,
# TOI, WASP-N, HAT-P-N, ...). Prefix set mirrors NASAExoplanetArchive._PREFIX_CASE
# so anything the normalizer accepts is also accepted as a searchable target.
_MISSION_TARGET_RE = re.compile(
    r"^(kepler-\d+|k2-\d+|tic\s?\d+|toi\s?\d+|kic\s?\d+|wd\s?\d+|"
    r"wasp-\d+|hat-?p-\d+|tres-\d+|xo-\d+|kelt-\d+|"
    r"gj\s?\d+|hd\s?\d+|hip\s?\d+|tyc\s?\d+)",
    re.IGNORECASE,
)


class RemoteDiscoveryEngine:
    """
    Connects to NASA Exoplanet Archive (TAP/pscomppars table) and MAST via
    Lightkurve. Acts as a facade coordinating NASAExoplanetArchive and LightkurveClient.
    """

    @staticmethod
    def _resolve_mission_target(meta: dict, canonical: str, target_name: str) -> tuple[str | None, str]:
        """Resolve a NASA Archive pl_name to a MAST-searchable target string.

        Strategy (first match wins):
          1. If the canonical name (or pl_name) already looks like a Kepler/K2/TESS
             designation, use it verbatim.
          2. Strip the planet letter off pl_name to get the host star
             (e.g. "Kepler-13 b" -> "Kepler-13").
          3. Fall back to the raw user-supplied target_name.

        Returns:
            (resolved_target_or_None, reason). When the resolver cannot produce a
            plausibly searchable target, returns (None, "Metadata mismatch").
        """
        pl_name = (meta or {}).get("pl_name") or canonical

        candidates = []
        for name in (pl_name, canonical, target_name):
            if name and _MISSION_TARGET_RE.match(name.strip()):
                candidates.append(name.strip())

        if candidates:
            return candidates[0], "OK"

        # Strip trailing planet letter (" b"/" c"/...) to reach the host star.
        host = re.sub(r"\s+[a-zA-Z]$", "", pl_name.strip())
        if host and host.lower() != pl_name.strip().lower():
            return host, "OK"
        if host:
            return host, "OK"

        print(
            f"[RemoteDiscoveryEngine] Metadata mismatch: pl_name='{pl_name}' "
            f"canonical='{canonical}' could not be resolved to a Kepler/TESS ID.",
            file=sys.stderr,
        )
        return None, "Metadata mismatch"

    @staticmethod
    def _bridge_to_time_series(meta: dict, canonical: str, target_name: str, archive_error: str | None) -> dict:
        """NASA Archive metadata bridge: attempt a fallback mission download.

        Triggered when `mission == 'NASA Exoplanet Archive'`. Resolves the target
        name, then tries TESS first (broader sky coverage post-2018) followed by
        Kepler. On success returns a standard `success` payload; on failure
        returns `no_time_series` with a specific `reason` tag for the UI.
        """
        resolved_target, resolve_reason = RemoteDiscoveryEngine._resolve_mission_target(
            meta, canonical, target_name,
        )

        if resolved_target is None:
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
                "reason": resolve_reason,
            }

        print(
            f"[RemoteDiscoveryEngine] NASA Archive bridge: resolved "
            f"'{target_name}' -> '{resolved_target}'; attempting TESS then Kepler.",
            file=sys.stderr,
        )

        data = None
        mast_error = None
        chosen_mission = None
        for mission_type in _TIME_SERIES_MISSIONS:
            try:
                data, mast_error = LightkurveClient.download_pipeline(resolved_target, mission_type)
            except Exception as exc:
                mast_error = str(exc)
                data = None
                print(
                    f"[RemoteDiscoveryEngine] NASA bridge: {mission_type} download "
                    f"raised for '{resolved_target}': {exc}",
                    file=sys.stderr,
                )
            if data is not None:
                chosen_mission = mission_type
                break

        if data is None:
            # Classify the reason for the UI's custom warning.
            err_lower = (mast_error or "").lower()
            if "timeout" in err_lower or "timed out" in err_lower:
                reason = "Network Timeout"
            elif "not observed" in err_lower or "no data" in err_lower or not mast_error:
                reason = "Target not observed"
            else:
                reason = "Target not observed"
            print(
                f"[RemoteDiscoveryEngine] NASA Archive bridge: no time-series "
                f"coverage for '{resolved_target}' (reason={reason}; mast_error={mast_error!r}).",
                file=sys.stderr,
            )
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
                "mast_error": mast_error,
                "reason": reason,
                "resolved_target": resolved_target,
            }

        print(
            f"[RemoteDiscoveryEngine] NASA Archive bridge: {chosen_mission} "
            f"yielded {len(data.get('time', []))} cadences for '{resolved_target}'.",
            file=sys.stderr,
        )
        meta = dict(meta)
        meta["bridged_mission"] = chosen_mission
        meta["resolved_target"] = resolved_target

        return {
            "status": "success",
            "metadata": meta,
            "time": data["time"],
            "flux": data["flux"],
            "flux_err": data["flux_err"],
            "archive_error": archive_error,
            "mast_error": None,
            "bridged_mission": chosen_mission,
        }

    @staticmethod
    def _fetch_data_impl(target_name: str, mission: str) -> dict:
        canonical = NASAExoplanetArchive.normalize_target_name(target_name)
        meta, archive_error = NASAExoplanetArchive.fetch_metadata(canonical)

        if mission == "NASA Exoplanet Archive":
            # FIX 1: the Archive is metadata-only. Bridge into a real time-series
            # mission (TESS/Kepler) via the resolved target, instead of halting.
            return RemoteDiscoveryEngine._bridge_to_time_series(
                meta, canonical, target_name, archive_error,
            )

        mast_error = None
        data = None

        if mission in ("TESS", "TESS Only", "TESS (via Lightkurve)"):
            data, mast_error = LightkurveClient.download_pipeline(target_name, "TESS")
        elif mission in ("Kepler", "Kepler Only", "Kepler (via Lightkurve)"):
            data, mast_error = LightkurveClient.download_pipeline(target_name, "Kepler")
        elif mission == "Combined Baseline (Kepler + TESS)":
            data, mast_error = LightkurveClient.download_combined_fusion(meta.get("pl_name", canonical))
        else:
            return {
                "status": "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
                "reason": "Unknown mission route",
            }

        if data is None:
            err_lower = (mast_error or "").lower()
            if "timeout" in err_lower or "timed out" in err_lower:
                reason = "Network Timeout"
            elif mast_error:
                reason = "Download failed"
            else:
                reason = "Target not observed"
            return {
                "status": "error" if mast_error else "no_time_series",
                "metadata": meta,
                "archive_error": archive_error,
                "mast_error": mast_error,
                "reason": reason,
            }

        if "baseline" in data:
            meta["time_baseline"] = data["baseline"]
            meta["kepler_segments"] = data.get("kepler_segments", 0)
            meta["tess_segments"] = data.get("tess_segments", 0)

        return {
            "status": "success",
            "metadata": meta,
            "time": data["time"],
            "flux": data["flux"],
            "flux_err": data["flux_err"],
            "archive_error": archive_error,
            "mast_error": mast_error,
        }

def _cached_fetch_data(target_name: str, mission: str = "Kepler") -> dict:
    import streamlit as st
    @st.cache_data(ttl=3600, show_spinner=False)
    def _inner_fetch(t_name, m_name):
        return RemoteDiscoveryEngine._fetch_data_impl(t_name, m_name)
    return _inner_fetch(target_name, mission)

RemoteDiscoveryEngine.fetch_data = staticmethod(_cached_fetch_data)

# Export DataAdapter for backwards compatibility
__all__ = ["RemoteDiscoveryEngine", "DataAdapter"]
