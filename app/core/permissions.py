from fastapi import Depends, HTTPException, status

from app.api.deps import get_current_user


def require_roles(*roles: str):
    """Dependency factory — enforces that the caller's JWT role is in `roles`."""

    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(roles)}",
            )
        return current_user

    return _check
