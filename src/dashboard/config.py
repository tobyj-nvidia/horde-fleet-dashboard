import os
from dataclasses import dataclass


@dataclass
class Settings:
    dolt_host: str = ""
    dolt_port: int = 0
    dolt_db: str = ""
    dolt_user: str = ""
    dolt_password: str = ""
    dashboard_host: str = ""
    dashboard_port: int = 0
    pool_min_size: int = 0
    pool_max_size: int = 0
    query_timeout_sec: int = 0

    def __post_init__(self):
        self.dolt_host = os.environ.get("DOLT_HOST", "127.0.0.1")
        self.dolt_port = int(os.environ.get("DOLT_PORT", "3306"))
        self.dolt_db = os.environ.get("DOLT_DB", "dolt-tasks")
        self.dolt_user = os.environ.get("DOLT_USER", "root")
        self.dolt_password = os.environ.get("DOLT_PASSWORD", "")
        self.dashboard_host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
        self.dashboard_port = int(os.environ.get("DASHBOARD_PORT", "8080"))
        self.pool_min_size = int(os.environ.get("POOL_MIN_SIZE", "2"))
        self.pool_max_size = int(os.environ.get("POOL_MAX_SIZE", "10"))
        self.query_timeout_sec = int(os.environ.get("QUERY_TIMEOUT_SEC", "10"))


settings = Settings()
