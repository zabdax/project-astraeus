"""Authentication for the ASTRAEUS API layer (P1-H).

PRD v4.1 §13.1: authentication is **required for public v1** -- today the
desktop tool speaks plain HTTP with no auth and no sessions -- and §13.1
also names the modelling rule that makes a later multi-user rollout a
migration rather than a redesign:

> Model ``users`` + ``owner_id`` on Job/Dataset **from day one** even with
> one row.

``astraeus/jobs/store.py`` already carries that column
(``owner_id`` defaulting to ``DEFAULT_OWNER``), so this module's job is to
turn a presented credential into an ``owner_id`` the store can filter on.

Two modes, selected by environment, not by code paths:

* **Single-user** (``ASTRAEUS_SINGLE_USER=1``, the default): one shared
  API key in ``ASTRAEUS_API_KEY`` authenticates the single owner.  This is
  the honest model for a desktop tool exposing a local port, and it is
  still a *user* with an ``owner_id`` -- never an unauthenticated route.
* **Multi-user** (``ASTRAEUS_SINGLE_USER=0``): ``ASTRAEUS_API_KEYS`` is a
  JSON object ``{username: key}``; the username becomes the ``owner_id``
  and job scoping is enforced by the store query, not by the route.

JWTs are issued by ``POST /auth/token`` and validated by the
:func:`require_user` dependency.  ``PyJWT`` is used directly rather than a
framework integration: the token is a capability over the job store, and
keeping the codec in one small module means the engine boundary never
imports the web stack.

Security notes carried from the PRD: keys are never logged, a missing key
means *every* protected route 401s (fail-closed, mirroring the §4.2 science
gate), and tokens carry an expiry so a leaked bearer does not live forever.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

__all__ = [
    "CurrentUser",
    "AuthConfig",
    "AuthState",
    "create_access_token",
    "decode_token",
    "require_user",
    "single_user_mode",
]

#: Default owner when the deployment is single-user; matches the store's
#: column default so a job created by either path lands in the same scope.
DEFAULT_OWNER = "single-user"

#: Bearer scheme used by the ``require_user`` dependency.
_scheme = HTTPBearer(auto_error=False)

#: Token lifetime.  Long enough for a long TLS run, short enough that a
#: leaked bearer is not a permanent capability.
DEFAULT_TTL_HOURS = 24.0

_ALGORITHM = "HS256"


@dataclass(frozen=True)
class AuthConfig:
    """Authentication settings resolved from the environment.

    ``keys`` maps ``owner_id -> api_key``.  In single-user mode it has one
    entry; the owner is :data:`DEFAULT_OWNER`.
    """

    keys: dict[str, str]
    single_user: bool = True
    ttl_hours: float = DEFAULT_TTL_HOURS
    issuer: str = "astraeus"

    @property
    def enabled(self) -> bool:
        return bool(self.keys)


def _read_keys(single_user: bool) -> dict[str, str]:
    """Resolve the owner->key map from the environment.

    Never raises: an unresolvable configuration yields *no* keys, and
    :func:`require_user` then rejects every request (fail-closed).
    """
    raw: str | None
    if single_user:
        raw = os.environ.get("ASTRAEUS_API_KEY")
        if not raw:
            return {}
        return {DEFAULT_OWNER: raw}

    raw = os.environ.get("ASTRAEUS_API_KEYS")
    if not raw:
        return {}
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    keys = {str(user): str(value) for user, value in parsed.items() if value}
    return keys


def single_user_mode() -> bool:
    return os.environ.get("ASTRAEUS_SINGLE_USER", "1").strip() in ("1", "true", "yes", "on")


class AuthState:
    """Holds the resolved configuration so routes do not re-read the env
    per request.  Constructed once at app startup (see ``main.create_app``)
    and injected via FastAPI's dependency system."""

    def __init__(self, config: AuthConfig | None = None, *, secret: str | None = None):
        if config is None:
            config = AuthConfig(keys=_read_keys(single_user_mode()), single_user=single_user_mode())
        self.config = config
        # The JWT signing secret.  An explicit secret wins (lets a test or a
        # deployment pin it); otherwise derive one from the configured keys
        # so a restart keeps validating existing tokens only if the keys are
        # stable -- and so a keyless deployment still has *a* secret rather
        # than an empty HMAC key, which PyJWT rejects anyway.
        self.secret = _normalize_secret(
            secret or os.environ.get("ASTRAEUS_JWT_SECRET") or _derive_secret(config)
        )

    @classmethod
    def for_testing(cls, keys: dict[str, str], *, secret: str = "astraeus-test-key") -> "AuthState":
        """Build an isolated state for tests: no environment consulted."""
        return cls(
            AuthConfig(keys=dict(keys), single_user=len(keys) == 1),
            secret=secret,
        )

    def owner_for_key(self, api_key: str | None) -> str | None:
        """Resolve the owner a raw API key authenticates, or None."""
        if not api_key:
            return None
        for owner, configured in self.config.keys.items():
            if _constant_time_eq(configured, api_key):
                return owner
        return None


def _derive_secret(config: AuthConfig) -> str:
    import hashlib

    digest = hashlib.sha256(
        json.dumps({"issuer": config.issuer, "keys": sorted(config.keys)}, sort_keys=True).encode()
    ).hexdigest()
    return f"astraeus-{digest}"


def _normalize_secret(material: str) -> str:
    """Guarantee an HMAC key of at least 32 bytes.

    PyJWT warns (and RFC 7518 forbids by recommendation) short HS256 keys.
    Hashing short material is deterministic, so a secret pinned via
    ``ASTRAEUS_JWT_SECRET`` still validates on both sides; it simply cannot
    be *too short* to be sound.  A secret already long enough is used as-is.
    """
    if len(material) >= 32:
        return material
    import hashlib

    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _constant_time_eq(a: str, b: str) -> bool:
    """Compare secrets without short-circuiting on the first mismatch."""
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def create_access_token(
    state: AuthState,
    owner_id: str,
    *,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a JWT for ``owner_id``."""
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": owner_id,
        "iss": state.config.issuer,
        "iat": now,
        "exp": now + int(state.config.ttl_hours * 3600),
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, state.secret, algorithm=_ALGORITHM)


def decode_token(state: AuthState, token: str) -> dict[str, Any]:
    """Verify and decode a JWT.  Raises ``HTTPException`` on any failure."""
    try:
        payload: Any = jwt.decode(
            token,
            state.secret,
            algorithms=[_ALGORITHM],
            issuer=state.config.issuer,
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not isinstance(payload, dict) or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed token"
        )
    owner = str(payload["sub"])
    # A token for an owner whose key was revoked must not remain valid.
    if owner not in state.config.keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="owner no longer authorized"
        )
    return payload


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated principal, attached to a request."""

    owner_id: str
    claims: dict[str, Any]


def require_user(
    state: AuthState,
    credentials: HTTPAuthorizationCredentials | None = Depends(_scheme),
) -> CurrentUser:
    """FastAPI dependency: reject any request without a valid token.

    Fail-closed by design (PRD §4.2's discipline applied to auth): an
    unconfigured deployment has no keys, so this raises 401 for every
    protected route rather than serving anonymous traffic.
    """
    if not state.config.enabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="no API key configured: set ASTRAEUS_API_KEY (single-user) "
            "or ASTRAEUS_API_KEYS (multi-user) to enable the API",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(state, credentials.credentials)
    return CurrentUser(owner_id=str(payload["sub"]), claims=dict(payload))
