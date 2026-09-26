"""Server-side array serving for the browser (3D-evidence program).

Pure functions over numbers -- no HTTP, no auth, no store access.  The
routes in :mod:`astraeus.api.routes` resolve *which* artifact a request
may see (ownership, candidate lookup, path jailing); everything here
only shapes arrays that are already authorized:

* :func:`stride_for` -- stride decimation receipt for curve overviews.
* :func:`decimate_periodogram` -- peak-preserving periodogram thinning
  (a pure stride can skip a 1-2 bin BLS spike, so the top-N peaks ride
  along as an overlay).
* :func:`fold_and_bin` -- phase fold + bin means.  Mirrors
  ``web/lib/fold.ts`` exactly (double-modulo phase, clamped bin index,
  empty bins skipped, ascending bin order) so a server-folded curve and
  a client-folded one agree point for point.
* :func:`artifact_etag` -- immutable content tag for ``If-None-Match``.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "stride_for",
    "decimate_1d",
    "decimate_periodogram",
    "fold_and_bin",
    "artifact_etag",
]


def stride_for(n: int, max_points: int, stride: int | None = None) -> int:
    """Stride that brings ``n`` points within ``max_points``.

    An explicit ``stride`` is honored verbatim (the receipt reports it);
    otherwise the smallest stride that fits the budget wins.
    """
    if stride is not None:
        if stride < 1:
            raise ValueError("stride must be >= 1")
        return stride
    if n <= 0:
        return 1
    return max(1, math.ceil(n / max_points))


def decimate_1d(
    x: np.ndarray, y: np.ndarray, stride: int
) -> tuple[np.ndarray, np.ndarray]:
    """Stride-slice two aligned arrays.  Index 0 always survives."""
    return np.asarray(x)[::stride], np.asarray(y)[::stride]


def decimate_periodogram(
    grid: np.ndarray, max_points: int, n_peaks: int = 200
) -> tuple[np.ndarray, int]:
    """Thin an ``(N, 2)`` ``[period, power]`` grid, preserving spikes.

    Returns ``(merged, stride)`` where ``merged`` is the stride
    background plus the ``n_peaks`` highest-power rows, deduplicated and
    sorted by ascending period.  The exact peak always survives, so the
    UI crosshair never points at a decimated-away maximum.
    """
    grid = np.asarray(grid, dtype=np.float64).reshape(-1, 2)
    n = grid.shape[0]
    stride = stride_for(n, max_points)
    background = grid[::stride]
    keep = min(n_peaks, n)
    top_idx = np.argpartition(grid[:, 1], -keep)[-keep:]
    merged = np.unique(np.vstack([background, grid[top_idx]]), axis=0)
    order = np.argsort(merged[:, 0], kind="stable")
    return merged[order], stride


def fold_and_bin(
    time: np.ndarray,
    flux: np.ndarray,
    period: float,
    epoch: float,
    bins: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fold ``(time, flux)`` on ``(period, epoch)`` into ``bins`` means.

    Phase convention ``[-0.5, 0.5)`` with the double-modulo form, bin
    index ``clip(floor((phase + 0.5) * bins), 0, bins - 1)``, bin centres
    ``(b + 0.5) / bins - 0.5``, empty bins skipped -- byte-for-byte the
    semantics of ``web/lib/fold.ts`` (``foldToPhase`` + ``binFolded``).

    Returns ``(centres, means, counts)`` over non-empty bins in ascending
    bin order.  ``bins == 0`` is rejected here; the route maps it to a
    decimated unbinned scatter instead.
    """
    if not np.isfinite(period) or period <= 0:
        raise ValueError("period must be a positive finite number")
    if not np.isfinite(epoch):
        raise ValueError("epoch must be finite")
    if bins < 1:
        raise ValueError("bins must be >= 1")
    t = np.asarray(time, dtype=np.float64)
    f = np.asarray(flux, dtype=np.float64)
    phase = (np.mod(np.mod(t - epoch, period) + period, period)) / period - 0.5
    idx = np.clip(np.floor((phase + 0.5) * bins).astype(np.int64), 0, bins - 1)
    sums = np.bincount(idx, weights=f, minlength=bins)
    counts = np.bincount(idx, minlength=bins)
    nonempty = np.nonzero(counts > 0)[0]
    centres = (nonempty + 0.5) / bins - 0.5
    means = sums[nonempty] / counts[nonempty]
    return centres, means, counts[nonempty]


def artifact_etag(*parts: object) -> str:
    """Opaque immutable tag from checksum + request parameters."""
    return '"' + ":".join(str(p) for p in parts) + '"'
