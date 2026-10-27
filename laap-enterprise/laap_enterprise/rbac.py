"""基于角色的访问控制（RBAC，占位实现）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set


@dataclass(frozen=True)
class Role:
    name: str
    permissions: Set[str] = field(default_factory=set)


class RBAC:
    """简单的内存 RBAC，后续可替换为数据库-backed 实现。"""

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._user_roles: dict[str, set[str]] = {}
        self._define_defaults()

    def _define_defaults(self) -> None:
        self.add_role(Role("viewer", {"read:cognitive_state", "read:memory"}))
        self.add_role(Role("operator", {"read:*", "write:memory", "trigger:reflect"}))
        self.add_role(Role("admin", {"*"}))

    def add_role(self, role: Role) -> None:
        self._roles[role.name] = role

    def assign(self, user: str, role_name: str) -> None:
        if role_name not in self._roles:
            raise ValueError(f"Unknown role: {role_name}")
        self._user_roles.setdefault(user, set()).add(role_name)

    def can(self, user: str, permission: str) -> bool:
        for role_name in self._user_roles.get(user, set()):
            role = self._roles.get(role_name)
            if not role:
                continue
            if "*" in role.permissions:
                return True
            if permission in role.permissions:
                return True
            # 支持通配命名空间，如 read:* 匹配 read:cognitive_state
            namespace = permission.split(":")[0] if ":" in permission else ""
            if namespace and f"{namespace}:*" in role.permissions:
                return True
        return False
