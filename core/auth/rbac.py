from __future__ import annotations
from fastapi import Header, HTTPException

_ROLE_RANK = {"viewer": 1, "analyst": 2, "admin": 3}


def require_role(minimum: str):
    async def dep(x_argus_role: str | None = Header(default=None)) -> str:
        role = (x_argus_role or "viewer").lower()
        if _ROLE_RANK.get(role, 0) < _ROLE_RANK.get(minimum, 99):
            raise HTTPException(status_code=403, detail=f"Role '{role}' insufficient; need '{minimum}'")
        return role
    return dep
