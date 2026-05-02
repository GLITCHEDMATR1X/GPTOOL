from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import BuilderScene, run_vr_editing_proof, validate_export_bundle


def command_panda_xr_proof(args: Any) -> int:
    output_dir = Path(args.output).resolve()
    proof = run_vr_editing_proof(output_dir)
    if args.json:
        print(json.dumps(proof, indent=2, sort_keys=True))
    else:
        print(f"Panda XR proof ok: {proof['ok']}")
        print(f"Objects: {proof['object_count']}")
        print(f"Operations: {proof['operation_count']}")
        print(f"Proof: {proof['outputs']['proof_result']}")
    return 0 if proof.get("ok") else 1


def command_panda_xr_export(args: Any) -> int:
    manifest = Path(args.manifest).resolve()
    output_dir = Path(args.output).resolve()
    scene = BuilderScene.load_manifest(manifest)
    exports = scene.export_game_ready(output_dir)
    scene_quality = scene.validate_scene()
    export_quality = validate_export_bundle(exports)
    result = {
        "ok": scene_quality["ok"] and export_quality["ok"],
        "schema": scene.to_dict()["schema"],
        "object_count": len(scene.objects),
        "connection_count": len(scene.connections),
        "path_node_count": len(scene.path_nodes),
        "behavior_count": len(scene.behaviors),
        "operation_count": len(scene.operation_history),
        "performance": scene.performance_summary(),
        "scene_quality": scene_quality,
        "export_quality": export_quality,
        "outputs": {key: str(value) for key, value in exports.items()},
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Panda XR export ok: {result['ok']}")
        for key, value in result["outputs"].items():
            print(f"{key}: {value}")
    return 0 if result["ok"] else 1


def command_panda_xr_quality(args: Any) -> int:
    manifest = Path(args.manifest).resolve()
    scene = BuilderScene.load_manifest(manifest)
    report = scene.validate_scene()
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Panda XR quality ok: {report['ok']}")
        print(f"Errors: {report['error_count']}")
        print(f"Warnings: {report['warning_count']}")
    return 0 if report["ok"] else 1


def command_panda_xr_visual_proof(args: Any) -> int:
    from .visual_proof import run_vr_visual_proof

    output_dir = Path(args.output).resolve()
    report = run_vr_visual_proof(
        output_dir,
        width=int(args.width),
        height=int(args.height),
        seconds=float(args.seconds),
        backend=str(args.backend),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Panda XR visual proof ok: {report['ok']}")
        print(f"Backend: {report['backend']}")
        print(f"Screenshot: {report['outputs']['screenshot']}")
        print(f"Report: {report['outputs']['visual_report']}")
    return 0 if report.get("ok") else 1
