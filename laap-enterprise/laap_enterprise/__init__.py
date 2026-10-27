"""LAAP Enterprise — 企业级增强包（闭源商业授权）

本包依赖 laap-AGI 社区版，提供企业级授权、审计、RBAC 与高级编排能力。
"""

__version__ = "0.1.0"
__license__ = "Proprietary"

from laap_enterprise.license_manager import LicenseManager
from laap_enterprise.audit_logger import AuditLogger
from laap_enterprise.rbac import RBAC

__all__ = ["LicenseManager", "AuditLogger", "RBAC", "__version__"]
