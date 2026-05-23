from __future__ import annotations

class Capsule:
    def __init__(self):
        self.host = None
        self.active = False
        self.result = {"app_id": "sample_capsule", "exit_reason": "not_started", "score_delta": 0, "discoveries": []}

    def prepare(self, host):
        self.host = host

    def enter(self, context=None):
        self.active = True
        self.result["exit_reason"] = "active"

    def update(self, dt: float):
        if not self.active:
            return

    def exit(self, reason: str = "return_to_host"):
        self.active = False
        self.result["exit_reason"] = reason

    def cleanup(self):
        self.active = False

    def get_result(self):
        return dict(self.result)
