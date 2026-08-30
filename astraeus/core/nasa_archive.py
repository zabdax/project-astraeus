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
            # Audit fix 5 (2026-08-21, verified live against the TAP
            # service): pscomppars stores HD/HIP/GJ designations
            # SPACE-separated ("HD 209458 b"); the hyphenated form matches
            # zero rows. Catalog-style prefixes keep the hyphen.
            separator = " " if prefix_raw in ("hd", "hip", "gj") else "-"
            if letter:
                return f"{canonical_prefix}{separator}{number} {letter}"
            return f"{canonical_prefix}{separator}{number}"

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
                resp = requests.get(url, params=params, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[NASAExoplanetArchive] ps-table fallback query timed out for '{safe_canonical}': {e}", file=sys.stderr)
                return None

            if data and len(data) > 0:
                row = data[0]
                # Audit fix 7: the dead 'pl_period' / 'pl_orbpererr1'
                # fallbacks were removed here too — the query already
                # filters `pl_orbper is not null`, so anything else is
                # garbage, not a period.
                period = row.get('pl_orbper')
                if period is not None:
                    return float(period)
        except Exception as exc:
            print(f"[NASAExoplanetArchive] ps-table fallback query failed for '{safe_canonical}': {exc}", file=sys.stderr)
        return None

    @staticmethod
    def _metadata_name_candidates(canonical_name: str) -> list[str]:
        """Return an ordered list of candidate target names to try in the
        NASA Exoplanet Archive pscomppars TAP query.

        Many KOI-catalogued Kepler targets are stored in pscomppars
        under the KOI hostname rather than the canonical Kepler-N
        name. The round-2 H6 evidence (see
        logs/diagnostic_run_2026-07-06T053656Z.json) confirmed this for
        Kepler-90 → KOI-351 and the round-1 test suite pins
        "Kepler-13 b" → "KOI-13 b". This is a structural pattern, not a
        one-off: pscomppars uses the catalog-discovery name (KOI-N for
        Kepler, K2-N for K2) as the hostname for most Kepler / K2
        multi-planet systems.

        I3 fix (round-2 diagnostic 2026-07-06, see
        logs/diagnostic_run_round2_*.json): add a generic Kepler-N →
        KOI-N (and K2-N) alias so the same pattern is handled for any
        catalogued target, not just the three hardcoded ones previously
        listed. The aliases are appended after the canonical name and
        after the existing Kepler-13 b / Kepler-90 special-cases, so
        the canonical name is still tried first.

        Note: Kepler-90 is a special case in pscomppars — its KOI
        number is 351, not 90. The generic Kepler-N → KOI-N alias is
        therefore wrong for Kepler-90; the explicit KOI-351 alias is
        kept, and the generic alias is added for the OTHER N.
        """
        names = [canonical_name]

        _KNOWN_ARCHIVE_ALIASES = {
            "Kepler-13 b": "KOI-13 b",
        }
        alias = _KNOWN_ARCHIVE_ALIASES.get(canonical_name)
        if alias:
            names.append(alias)

        # Audit fix 5 (2026-08-21): HD/HIP/GJ designations are stored
        # SPACE-separated in pscomppars (hyphen form matches zero rows).
        # The normalizer emits the space form; also offer the opposite
        # separator as a fallback candidate so either historical spelling
        # of the same designation resolves.
        m_catalog = re.match(
            r"^(HD|HIP|GJ)([-\s])(\d+)(\s+[a-z])?$",
            canonical_name,
            re.IGNORECASE,
        )
        if m_catalog:
            pfx, sep, num, letter = m_catalog.groups()
            other_sep = " " if sep == "-" else "-"
            names.append(
                f"{pfx.upper()}{other_sep}{num}{letter.lower() if letter else ''}"
            )

        kepler_component_match = re.match(r"^(Kepler-\d+)\s+([a-z])$", canonical_name, re.IGNORECASE)
        if kepler_component_match:
            host, planet_letter = kepler_component_match.groups()
            names.append(f"{host} A {planet_letter.lower()}")

        if canonical_name.lower() == "kepler-90":
            # Kepler-90 is KOI-351 in pscomppars. The generic alias
            # below would map Kepler-90 → KOI-90 (wrong) so the
            # explicit KOI-351 form is the only correct fallback.
            names.extend(["KOI-351", "Kepler-90 i", "KOI-351 b"])
        else:
            # Generic Kepler-N (or K2-N) host → KOI-N (or K2-N) alias.
            # This handles every catalogued multi-planet system whose
            # KOI number is the hostname in pscomppars, not just the
            # special-cases above. The canonical name is tried first;
            # the alias is a fallback.
            m_kepler_host = re.match(r"^Kepler-(\d+)$", canonical_name, re.IGNORECASE)
            if m_kepler_host:
                koi_n = m_kepler_host.group(1)
                names.append(f"KOI-{koi_n}")
            m_k2_host = re.match(r"^K2-(\d+)$", canonical_name, re.IGNORECASE)
            if m_k2_host:
                k2_n = m_k2_host.group(1)
                names.append(f"K2-{k2_n}")
            if not re.search(r"\s+[a-z]$", canonical_name, re.IGNORECASE):
                # If it's just a host star name, try appending ' b' as a fallback
                names.append(f"{canonical_name} b")

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
                # Audit fix 6 (2026-08-21, verified live: a hostname query
                # for Kepler-11 returned "Kepler-11 d" first): without an
                # ORDER BY the row order is arbitrary, so a hostname match
                # bound a RANDOM planet's period/depth to system-level
                # metadata. The innermost planet (smallest pl_orbper) is a
                # deterministic choice.
                query = f"select pl_name, pl_orbper, pl_orbpererr1, st_rad, st_raderr1, st_lum, st_teff, st_mass, sy_jmag, pl_trandep, pl_ratror from pscomppars where pl_name='{candidate_name}' or hostname='{candidate_name}' order by pl_orbper asc"
                params = {"query": query, "format": "json"}

                for attempt in range(3):
                    try:
                        resp = requests.get(url, params=params, timeout=30.0)
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

                # Audit fix 6: when the query matched on hostname, the row's
                # pl_name is the planet the metadata actually belongs to —
                # record it instead of the queried candidate so consumers
                # know which planet's period/depth they received.
                row_pl_name = row.get('pl_name')
                if (
                    isinstance(row_pl_name, str)
                    and row_pl_name
                    and row_pl_name != matched_canonical
                ):
                    matched_canonical = row_pl_name

                # Audit fix 7 (2026-08-21): the previous fallback chain read
                # the nonexistent 'pl_period' column and then adopted the
                # ERROR column 'pl_orbpererr1' as a period — garbage values
                # were silently accepted. A null pl_orbper now goes straight
                # to the ps-table fallback (which filters nulls properly).
                pl_orbper = row.get('pl_orbper')
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

                # ── Transit-depth normalisation ──────────────────────────
                # Contract: `transit_depth` is ALWAYS stored as a raw
                # decimal fraction (e.g. 0.00459 for Kepler-13 b).
                # The ppm conversion (× 1,000,000) happens ONCE, at the
                # display layer in the UI.
                #
                # NASA archive `pl_trandep` semantics:
                #   >= 1.0  → value is in percent   → divide by 100
                #   <  1.0  → value is a fraction    → use as-is
                # Fallback `pl_ratror` → (Rp/R★)²  → already a fraction
                # Fallback `pl_rade`/stellar radius → (Rp/R★)² geometric.
                #
                # I3 fix (round-2 diagnostic 2026-07-06, see
                # logs/diagnostic_run_round2_*.json): previously, when
                # `pl_trandep` was NULL and the secondary fallbacks
                # (`pl_ratror`, geometric) also failed, the depth was
                # silently returned as 0.0 with no audit trail. Round 1
                # evidence shows Kepler-90 i has NULL `pl_trandep` in
                # pscomppars — under the old code, that planet's depth
                # was lost with zero indication. Now we fall back
                # through `pl_ratror` → geometric (pl_rade / st_rad)
                # → explicit "unavailable" marker, and we record the
                # exact source so consumers can distinguish "no data"
                # from "we didn't check" (which is the same class of
                # bug as the original ingestion bug).
                pl_trandep_raw = row.get('pl_trandep')
                depth_fraction = None   # fraction of normalized flux (consumer contract)
                depth_percent = None    # pscomppars percent value (consumer contract)
                depth_source = None
                if pl_trandep_raw is not None and not (
                    isinstance(pl_trandep_raw, float) and np.isnan(pl_trandep_raw)
                ):
                    # pscomppars stores pl_trandep in PERCENT, unconditionally.
                    # Verified live 2026-08-21 against the TAP service:
                    # TRAPPIST-1 b -> 0.7378 (= 7378 ppm), HD 209458 b -> 1.5.
                    # The previous `>= 1.0` value-sniffing heuristic left every
                    # planet shallower than 1% (most known planets) unconverted,
                    # so transit_depth came out 100x too large as a fraction.
                    depth_percent = float(pl_trandep_raw)
                    depth_fraction = depth_percent / 100.0
                    depth_source = "pl_trandep"
                else:
                    pl_ratror = row.get('pl_ratror')
                    if pl_ratror is not None and not (
                        isinstance(pl_ratror, float) and np.isnan(pl_ratror)
                    ):
                        depth_fraction = float(pl_ratror) ** 2  # already a fraction
                        depth_percent = depth_fraction * 100.0
                        depth_source = "pl_ratror_squared"
                    else:
                        # Geometric fallback: depth = (Rp / R★)^2 derived
                        # from pl_rade and st_rad, in earth and solar
                        # radii respectively.
                        pl_rade = row.get('pl_rade')
                        _st_rad_for_depth = st_rad
                        if (
                            pl_rade is not None
                            and _st_rad_for_depth is not None
                            and float(pl_rade) > 0
                            and float(_st_rad_for_depth) > 0
                        ):
                            _R_SUN_TO_R_EARTH = 109.2  # nominal
                            rp_over_rstar = (
                                float(pl_rade) / (_R_SUN_TO_R_EARTH * float(_st_rad_for_depth))
                            )
                            depth_fraction = rp_over_rstar ** 2
                            depth_percent = depth_fraction * 100.0
                            depth_source = "pl_rade_over_st_rad_geometric"
                        else:
                            # No archive-derived depth available. Surface
                            # "unavailable" explicitly (depth = 0.0 is
                            # not the same as "we didn't check").
                            depth_fraction = 0.0
                            depth_percent = 0.0
                            depth_source = "unavailable_no_archive_input"

                meta = {
                    "pl_name": matched_canonical,
                    "orbital_period": pl_orbper,
                    "stellar_radius": st_rad if st_rad is not None else 1.0,
                    # Fraction of normalized flux — UI renders this * 1e6 as ppm.
                    "transit_depth": depth_fraction if depth_fraction is not None else 0.0,
                    "transit_depth_source": depth_source,  # I3 fix
                    "pl_orbper": pl_orbper,
                    "st_rad": st_rad if st_rad is not None else 1.0,
                    # Kept in pscomppars PERCENT so consumers that divide by
                    # 100 (analysis/detection.py archive-depth cross-check)
                    # stay correct. Distinct from transit_depth (fraction).
                    "pl_trandep": depth_percent if depth_percent is not None else 0.0,
                    "st_teff": st_teff,
                    "st_mass": st_mass,
                    "sy_jmag": sy_jmag,
                    "raw_row_dump": row,
                }

                meta = NASAExoplanetArchive.sanitize_meta(meta)

        except Exception as exc:
            archive_error = str(exc)

        return meta, archive_error
