"""LAAP Enterprise 占位测试"""

import pytest

from laap_enterprise.license_manager import LicenseManager
from laap_enterprise.audit_logger import AuditLogger
from laap_enterprise.rbac import RBAC


def test_license_validation():
    lm = LicenseManager("LAAP-ENT-DEMO-12345")
    assert lm.validate() is True
    assert lm.has_feature("audit") is True


def test_audit_logger(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    logger.log("test_event", "alice", {"x": 1})
    results = logger.query(event_type="test_event")
    assert len(results) == 1
    assert results[0]["actor"] == "alice"


def test_rbac():
    rbac = RBAC()
    rbac.assign("bob", "operator")
    assert rbac.can("bob", "read:cognitive_state") is True
    assert rbac.can("bob", "delete:system") is False
