"""RBAC — granular roles, workspaces, and permissions for Pro teams.

Goes beyond typical antidetect team features (a few fixed roles) with:
  * fine-grained capability flags (compose exactly what a role can do),
  * per-workspace role assignment (Admin in one workspace, Viewer in another),
  * custom roles (define your own permission bundles),
  * deny-by-default with explicit grants.
Pure, unit-testable logic; persistence handled by the host/backend.
"""
from __future__ import annotations
from dataclasses import dataclass

CAPS = [
    "workspace.view", "workspace.edit", "workspace.delete",
    "profile.view", "profile.launch", "profile.edit", "profile.export", "profile.share",
    "proxy.assign", "proxy.rotate", "member.invite", "member.manage",
    "billing.view", "billing.manage", "api.key.manage", "audit.view",
]

BUILTIN_ROLES = {
    "owner":    set(CAPS),
    "admin":    set(CAPS) - {"billing.manage", "workspace.delete"},
    "manager":  {"workspace.view", "profile.view", "profile.launch", "profile.edit",
                 "proxy.assign", "proxy.rotate", "member.invite", "audit.view"},
    "operator": {"workspace.view", "profile.view", "profile.launch"},
    "viewer":   {"workspace.view", "profile.view"},
}


@dataclass
class Assignment:
    user_id: str
    workspace_id: str
    role: str


class RBAC:
    def __init__(self):
        self.custom_roles = {}     # name -> set(caps)
        self.assignments = {}      # (user, ws) -> role

    def define_role(self, name, caps):
        bad = [c for c in caps if c not in CAPS]
        if bad:
            raise ValueError("unknown caps: %s" % bad)
        self.custom_roles[name] = set(caps)

    def assign(self, user_id, workspace_id, role):
        if role not in BUILTIN_ROLES and role not in self.custom_roles:
            raise ValueError("unknown role: %s" % role)
        self.assignments[(user_id, workspace_id)] = role

    def _caps(self, role):
        return BUILTIN_ROLES.get(role) or self.custom_roles.get(role, set())

    def can(self, user_id, workspace_id, cap):
        role = self.assignments.get((user_id, workspace_id))
        if not role:
            return False           # deny by default
        return cap in self._caps(role)
