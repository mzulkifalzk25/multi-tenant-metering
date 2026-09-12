"""Minimal header-based tenant/user identification.

This is intentionally simple: it establishes *who is calling* so use cases
can enforce tenant scoping, but it is not a substitute for a real identity
provider (JWT/OIDC) in production -- swapping the header extraction below
for token verification would not require touching any other layer.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from src.shared.types import TenantId, UserId


async def get_authenticated_tenant(
    x_tenant_id: str = Header(..., alias="X-Tenant-Id"),
) -> TenantId:
    if not x_tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Tenant-Id header"
        )
    return TenantId(x_tenant_id)


async def get_authenticated_user(
    x_user_id: str = Header(..., alias="X-User-Id"),
) -> UserId:
    if not x_user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-User-Id header"
        )
    return UserId(x_user_id)


def ensure_path_tenant_matches(path_tenant_id: str, authenticated_tenant_id: TenantId) -> None:
    if path_tenant_id != authenticated_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path tenant_id does not match the authenticated tenant",
        )
