"""V4 identity — resolves the logged-in tier into one user record used for write
attribution and scope filtering.

V4 uses TIER-CODE identity (the existing store / DM / admin login) plus an optional
typed display name captured at write time; no per-user accounts yet (that's deferred
to the security-hardening item). Pure module, no Streamlit import, so it's testable.
"""
from config import CITY, DISTRICTS, STORE_CODES, REGIONS


def resolve(role, code):
    """(role, code) -> {role, code, label, stores}. `stores` is the write/read scope."""
    if role == "store":
        return {"role": "store", "code": code,
                "label": f"{CITY.get(code, code)} #{code}", "stores": [code]}
    if role == "district":
        name, ids = DISTRICTS.get(code, (code, []))
        return {"role": "district", "code": code, "label": name, "stores": list(ids)}
    return {"role": "admin", "code": None, "label": "Admin", "stores": list(STORE_CODES)}


def attribution(user, typed_name=""):
    """String stored in completed_by / updated_by / from_user — typed name + tier label."""
    typed_name = (typed_name or "").strip()
    base = (user or {}).get("label", "?")
    return f"{typed_name} ({base})" if typed_name else base


# ---------------- V4 Phase 1 (A): scope deep-links ----------------
# Pure functions so app.py's Streamlit widgets stay a thin shell over testable logic.
# A `scope` string is what rides in the ?scope= query param:
#   ''/'all'           -> the tier's default view
#   'region:<Region>'  -> admin only: admin view scoped to one region's stores
#   'store:<id>'       -> the full single-store dashboard (must be in the user's scope)

def _store_label(s):
    return f"{CITY.get(s, s)} #{s}"


def resolve_scope(role, user, scope):
    """(role, user, scope-string) -> (render_tier, allowed_stores, scope_label).
    Falls back to the tier default for any unknown/uninted scope."""
    scope = (scope or "").strip()
    allowed = list(user.get("stores", []))

    if role == "store":
        s = user["code"]
        return "store", [s], _store_label(s)

    # store: drill-in is valid for DM (own stores) and admin (any store)
    if scope.startswith("store:"):
        s = scope.split(":", 1)[1]
        if (role == "admin" and s in STORE_CODES) or (role == "district" and s in allowed):
            return "store", [s], _store_label(s)

    if role == "district":
        return "district", allowed, f"{user['label']} · {len(allowed)} stores"

    # admin
    if scope.startswith("region:"):
        r = scope.split(":", 1)[1]
        if r in REGIONS:
            ids = list(REGIONS[r])
            return "admin", ids, f"{r} · {len(ids)} stores"
    return "admin", list(STORE_CODES), f"All Stores · {len(STORE_CODES)}"


def scope_region_of(scope):
    """The region a scope belongs to, for restoring the 2-level admin picker from a deep link.
    A 'store:<id>' scope resolves to that store's region so the region tab reopens on it."""
    scope = (scope or "").strip()
    if scope.startswith("region:"):
        r = scope.split(":", 1)[1]
        return r if r in REGIONS else None
    if scope.startswith("store:"):
        s = scope.split(":", 1)[1]
        for r, ids in REGIONS.items():
            if s in ids:
                return r
    return None
