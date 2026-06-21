from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    # TODO: validate JWT and extract claims
    token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    # TODO: validate JWT and extract real claims — using seed data IDs for dev
    return {
        "tenant_id": "11111111-0000-0000-0000-000000000001",
        "user_id":   "33333333-0000-0000-0000-000000000002",
    }
