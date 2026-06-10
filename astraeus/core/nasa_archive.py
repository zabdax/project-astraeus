import sys
import re
import requests
import time
import numpy as np

class NASAExoplanetArchive:
    """Handles interactions with the NASA Exoplanet Archive."""

    @staticmethod
    def normalize_target_name(raw: str) -> str:
        name = raw.strip()
        name = re.sub(r"\s+", " ", name)
        name = re.sub(r"\s*-\s*", "-", name)

        _PREFIX_PATTERN = re.compile(
            r"^(wasp|hat-?p|kepler|k2|toi|tres|xo|gj|kelt|hd|hip|tyc)"
            r"[-\s]?(\d+)"
            r"(?:[-\s]?([a-zA-Z]))$",
            re.IGNORECASE,
        )

        _PREFIX_CASE: dict = {
            "wasp": "WASP", "hatp": "HAT-P", "hat-p": "HAT-P",
            "kepler": "Kepler", "k2": "K2", "toi": "TOI",
            "tres": "TrES", "xo": "XO", "gj": "GJ",
            "kelt": "KELT", "hd": "HD", "hip": "HIP", "tyc": "TYC",
        }

        m = _PREFIX_PATTERN.match(name)
        if m:
            prefix_raw = m.group(1).lower().replace(" ", "")
            number = m.group(2)
            letter = m.group(3).lower() if m.group(3) else ""
            canonical_prefix = _PREFIX_CASE.get(prefix_raw, prefix_raw.upper())
            if letter:
                return f"{canonical_prefix}-{number} {letter}"
            return f"{canonical_prefix}-{number}"

        return name

    @staticmethod
    def sanitize_meta(meta: dict) -> dict:
        _FLOAT_DEFAULTS: dict[str, float] = {
            "orbital_period": 0.0, "pl_orbper": 0.0,
            "transit_depth": 0.0, "pl_trandep": 0.0,
            "stellar_radius": 1.0, "st_rad": 1.0,
            "st_teff": 5778.0, "st_mass": 1.0, "sy_jmag": 10.0,
        }

        for key, default in _FLOAT_DEFAULTS.items():
            raw = meta.get(key)
            if raw is None:
                meta[key] = default
                continue
            try:
                if np.ma.is_masked(raw):
                    meta[key] = default
                    continue
                fval = float(raw)
                meta[key] = default if (np.isnan(fval) or np.isinf(fval)) else fval
            except (TypeError, ValueError):
                meta[key] = default

        return meta

    @staticmethod
    def _fetch_ps_orbital_period(safe_canonical: str) -> float | None:
        try:
            url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
            query = f"select pl_name, pl_orbper, pl_orbpererr1 from ps where pl_name='{safe_canonical}' and pl_orbper is not null order by pl_orbper desc"
            params = {"query": query, "format": "json"}

            try:
                resp = requests.get(url, params=params, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[NASAExoplanetArchive] ps-table fallback query timed out for '{safe_canonical}': {e}", file=sys.stderr)
                return None

            if data and len(data) > 0:
                row = data[0]
                period = row.get('pl_orbper')
                if period is None:
                    period = row.get('pl_orbpererr1')
                if period is not None:
                    return float(period)
        except Exception as exc:
            print(f"[NASAExoplanetArchive] ps-table fallback query failed for '{safe_canonical}': {exc}", file=sys.stderr)
        return None

    @staticmethod
    def _metadata_name_candidates(canonical_name: str) -> list[str]:
        names = [canonical_name]

        _KNOWN_ARCHIVE_ALIASES = {
            "Kepler-13 b": "KOI-13 b",
        }
        alias = _KNOWN_ARCHIVE_ALIASES.get(canonical_name)
        if alias:
            names.append(alias)

        kepler_component_match = re.match(r"^(Kepler-\d+)\s+([a-z])$", canonical_name, re.IGNORECASE)
        if kepler_component_match:
            host, planet_letter = kepler_component_match.groups()
            names.append(f"{host} A {planet_letter.lower()}")

        return list(dict.fromkeys(names))

    @staticmethod
    def fetch_metadata(canonical_name: str) -> tuple[dict, str | None]:
        meta: dict = {}
        archive_error: str | None = None
        safe_canonical = canonical_name.strip()

        try:
            url = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
            data = []
            matched_canonical = safe_canonical
            for candidate_name in NASAExoplanetArchive._metadata_name_candidates(safe_canonical):
                query = f"select pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror from pscomppars where pl_name='{candidate_name}'"
                params = {"query": query, "format": "json"}

                for attempt in range(3):
                    try:
                        resp = requests.get(url, params=params, timeout=5.0)
                        resp.raise_for_status()
                        data = resp.json()
                        if data:
                            matched_canonical = candidate_name
                        break
                    except Exception as e:
                        if attempt == 2:
                            print(f"[NASAExoplanetArchive] Archive query failed or timed out after 3 attempts: {e}", file=sys.stderr)
                        else:
                            time.sleep(2.0)
                if data:
                    break

            if data and len(data) > 0:
                row = data[0]

                pl_orbper = row.get('pl_orbper')
                if pl_orbper is None:
                    pl_orbper = row.get('pl_period')
                if pl_orbper is None:
                    pl_orbper = row.get('pl_orbpererr1')

                if pl_orbper is not None:
                    pl_orbper = float(pl_orbper)
                else:
                    pl_orbper = NASAExoplanetArchive._fetch_ps_orbital_period(safe_canonical)
                    if pl_orbper is None:
                        pl_orbper = 0.0

                st_rad = row.get('st_rad')
                if st_rad is not None:
                    st_rad = abs(float(st_rad))
                else:
                    st_lum = row.get('st_lum')
                    st_teff = row.get('st_teff')
                    if st_lum is not None and st_teff is not None and float(st_teff) > 0:
                        st_lum = float(st_lum)
                        st_teff = float(st_teff)
                        st_rad = abs(np.sqrt(10.0 ** st_lum) * (5778.0 / st_teff) ** 2)

                st_teff = float(row.get('st_teff')) if row.get('st_teff') is not None else 5778.0
                st_mass = float(row.get('st_mass')) if row.get('st_mass') is not None else 1.0
                sy_jmag = float(row.get('sy_jmag')) if row.get('sy_jmag') is not None else 10.0

                pl_trandep = row.get('pl_trandep')
                if pl_trandep is not None:
                    pl_trandep = float(pl_trandep)
                    if pl_trandep < 1.0:
                        pl_trandep = pl_trandep * 1_000_000
                else:
                    pl_ratror = row.get('pl_ratror')
                    if pl_ratror is not None:
                        pl_ratror = float(pl_ratror)
                        pl_trandep = (pl_ratror ** 2) * 1_000_000

                meta = {
                    "pl_name": matched_canonical,
                    "orbital_period": pl_orbper,
                    "stellar_radius": st_rad if st_rad is not None else 1.0,
                    "transit_depth": pl_trandep if pl_trandep is not None else 0.0,
                    "pl_orbper": pl_orbper,
                    "st_rad": st_rad if st_rad is not None else 1.0,
                    "pl_trandep": pl_trandep if pl_trandep is not None else 0.0,
                    "st_teff": st_teff,
                    "st_mass": st_mass,
                    "sy_jmag": sy_jmag,
                    "raw_row_dump": row,
                }

                meta = NASAExoplanetArchive.sanitize_meta(meta)

        except Exception as exc:
            archive_error = str(exc)

        return meta, archive_error
