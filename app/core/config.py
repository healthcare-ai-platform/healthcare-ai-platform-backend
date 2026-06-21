import os

JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM: str = "HS256"
JWT_ACCESS_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "60"))
JWT_REFRESH_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

INVITE_EXPIRE_HOURS: int = 48

SES_FROM_EMAIL: str = os.getenv("SES_FROM_EMAIL", "noreply@healthcare-platform.com")
APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:3000")
