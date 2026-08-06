"""企业级授权与 License Key 管理（占位实现）"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LicenseManager:
    """验证 LAAP Enterprise 授权许可证。

    占位实现：后续接入在线授权服务器或硬件指纹绑定。
    """

    def __init__(self, license_key: str | None = None) -> None:
        self.license_key = license_key or self._load_key_from_env()
        self._validated = False
        self._features: set[str] = set()

    def _load_key_from_env(self) -> str | None:
        import os

        return os.environ.get("LAAP_ENTERPRISE_LICENSE")

    def validate(self) -> bool:
        """校验 License Key 是否有效。"""
        if not self.license_key:
            return False
        # 占位：仅做格式校验
        self._validated = self.license_key.startswith("LAAP-ENT-")
        if self._validated:
            self._features = {"audit", "rbac", "console", "federation"}
        return self._validated

    def is_valid(self) -> bool:
        return self._validated

    def has_feature(self, feature: str) -> bool:
        return self._validated and feature in self._features

    def generate_trial_key(self, seed: str | None = None) -> str:
        """生成临时试用 Key（内部使用）。"""
        base = seed or secrets.token_hex(8)
        digest = hmac.new(b"laap-enterprise-trial", base.encode(), hashlib.sha256).hexdigest()[:16]
        return f"LAAP-ENT-TRIAL-{digest.upper()}"
