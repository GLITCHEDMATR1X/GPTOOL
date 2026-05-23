from __future__ import annotations
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_capsules.app_scanner import scan_app
from app_capsules.framework_migration import build_migration_plan
from app_capsules.adapter_audit import audit_adapters
from app_capsules.validate_capsule import validate_capsule
from app_capsules.install_bridge_app_capsules import plan_bridge_patch


def make_pygame_fixture(root: Path) -> Path:
    p = root / "pygame_game"; p.mkdir()
    (p / "main.py").write_text('''import pygame, sys\npygame.init()\nscreen = pygame.display.set_mode((800,600))\nrunning=True\nwhile running:\n    for event in pygame.event.get():\n        if event.type == pygame.QUIT:\n            sys.exit()\n''', encoding="utf-8")
    return p


def make_adapter_fixture(root: Path) -> Path:
    p = root / "HoloVerse"; p.mkdir()
    (p / "native_adapter.py").write_text('''import subprocess\nfrom direct.showbase.ShowBase import ShowBase\nclass BadAdapter:\n    def run(self):\n        base.destroy()\n        taskMgr.remove("update-task")\n''', encoding="utf-8")
    return p


def make_capsule_fixture(root: Path) -> Path:
    p = root / "capsule"; p.mkdir()
    (p / "app_manifest.json").write_text(json.dumps({"id":"ok","title":"OK","kind":"panda3d_same_window","entry":"capsule.py","contract":"app_capsule.v1","owns":{"window":False},"exit_keys":["escape"],"return_mode":"host_hub","validators":[]}), encoding="utf-8")
    (p / "capsule.py").write_text('''class Capsule:\n    def prepare(self, host): pass\n    def enter(self, context=None): pass\n    def update(self, dt): pass\n    def exit(self, reason="return_to_host"): pass\n    def cleanup(self): pass\n    def get_result(self): return {}\n''', encoding="utf-8")
    return p


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pg = make_pygame_fixture(tmp)
        scan = scan_app(pg)
        assert "pygame" in scan["detected_frameworks"], scan
        assert scan["recommended_kind"] == "pygame_legacy", scan
        plan = build_migration_plan(pg, target="panda3d_same_window")
        assert plan["migration_kind"] == "extract_logic_rebuild_panda3d_view", plan
        assert plan["blockers"], plan
        hv = make_adapter_fixture(tmp)
        audit = audit_adapters(hv)
        assert audit["candidate_count"] >= 1, audit
        assert audit["medium_risk_count"] + audit["high_risk_count"] >= 1, audit
        cap = make_capsule_fixture(tmp)
        val = validate_capsule(cap)
        assert val["ok"], val
        bridge = tmp / "bridge.py"
        bridge.write_text('''from __future__ import annotations\nfrom maintenance.package_cleaner import analyze_package, clean_package_tree, create_lean_package_zip, render_package_audit_text\ndef build_parser():\n    sub = object()\n    return parser\n''', encoding="utf-8")
        patch = plan_bridge_patch(bridge)
        assert patch["changed"], patch
        assert "add_app_capsule_commands" in patch["new_text"], patch["new_text"]
    print("selftest_app_capsules.py passed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
