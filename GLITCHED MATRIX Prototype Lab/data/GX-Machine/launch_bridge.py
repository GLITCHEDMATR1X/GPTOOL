from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bootstrap.panda3d_bootstrap import ensure_panda3d
from diagnostics.bridge_exit_cleanup import install_exit_cleanup
from diagnostics.env_probe import build_probe, finalize_probe


DEFAULT_BOOTSTRAP_LOG = Path("logs") / "panda3d_bootstrap.json"
DEFAULT_ENV_LOG = Path("logs") / "launch_env_probe.json"
DEFAULT_CLEANUP_LOG = Path("logs") / "bridge_exit_cleanup_auto.json"
DEFAULT_CLEANUP_IMAGE = Path("logs") / "bridge_exit_cleanup_auto.png"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch the GPT bridge with automatic Panda3D bootstrap when needed."
    )
    parser.add_argument(
        "--no-auto-install",
        action="store_true",
        help="Disable automatic Panda3D installation on launch.",
    )
    parser.add_argument(
        "--include-optional-profile-packages",
        action="store_true",
        help="Also install panda3d-gltf and panda3d-simplepbr when Panda3D is missing.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="pip install timeout in seconds.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON instead of a text summary.",
    )
    parser.add_argument(
        "--bootstrap-log",
        default=str(DEFAULT_BOOTSTRAP_LOG),
        help="Path for the bootstrap log JSON.",
    )
    parser.add_argument(
        "--env-log",
        default=str(DEFAULT_ENV_LOG),
        help="Path for the environment probe JSON.",
    )
    parser.add_argument(
        "--no-cleanup-on-exit",
        action="store_true",
        help="Disable automatic cache/temp cleanup when the launcher exits.",
    )
    parser.add_argument(
        "--wipe-test-workspace-on-exit",
        action="store_true",
        help="Also wipe the managed bridge test workspace on exit to reduce stale validation leftovers after commits.",
    )
    parser.add_argument(
        "--cleanup-log",
        default=str(DEFAULT_CLEANUP_LOG),
        help="Path for the exit cleanup JSON report.",
    )
    parser.add_argument(
        "--cleanup-image",
        default=str(DEFAULT_CLEANUP_IMAGE),
        help="Path for the exit cleanup PNG summary.",
    )
    args = parser.parse_args()

    cleanup_disabled = os.environ.get('BRIDGE_EXIT_CLEANUP_DISABLE', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    install_exit_cleanup(
        root=Path(__file__).resolve().parent,
        output_path=args.cleanup_log,
        debug_image_path=args.cleanup_image,
        wipe_test_workspace=args.wipe_test_workspace_on_exit,
        enabled=(not args.no_cleanup_on_exit) and (not cleanup_disabled),
    )

    bootstrap_report = ensure_panda3d(
        auto_install=not args.no_auto_install,
        include_optional_profile_packages=args.include_optional_profile_packages,
        timeout=args.timeout,
        log_path=args.bootstrap_log,
    )

    env_report = finalize_probe(build_probe())
    env_log_path = Path(args.env_log).resolve()
    env_log_path.parent.mkdir(parents=True, exist_ok=True)
    env_log_path.write_text(json.dumps(env_report, indent=2), encoding="utf-8")

    report = {
        "launcher": "launch_bridge",
        "bootstrap": bootstrap_report,
        "environment": env_report,
        "status": {
            "ok": env_report["capabilities"]["panda3d_profile_ready"],
            "ready": env_report["capabilities"]["panda3d_profile_ready"],
        },
        "next_steps": [
            "Run diagnostics/env_probe.py --json for a direct environment report.",
            "Run diagnostics/bridge_exit_cleanup.py --root . --output logs/bridge_exit_cleanup.json --debug-image logs/bridge_exit_cleanup.png to remove bridge cache/temp leftovers and optionally wipe the managed test workspace after commits.",
            "Run validators/syntax_validator.py <project_or_file> --json to validate code.",
            "Run validators/reference_image_validator.py --image <path> --output logs/reference_image_validation.json --debug-image logs/reference_image_debug.png before image-to-3D generation.",
            "Run validators/alpha_prep.py --image <path> --output logs/alpha_prep.json --debug-image logs/alpha_prep.png --cutout-output logs/alpha_cutout.png to inspect and preserve the subject matte.",
            "Run validators/depth_hint_generator.py --image <path> --output logs/depth_hint.json --debug-image logs/depth_hint.png --depth-output logs/depth_hint_map.png to preview front-back mass before generation.",
            "Run validators/image_to_3d_fidelity_validator.py --reference <source.png> --candidate <render.png> --output logs/image_to_3d_fidelity.json --debug-image logs/image_to_3d_fidelity.png after generation or render export.",
            "Run validators/mesh_quality_validator.py --mesh <asset.glb|asset.obj> --output logs/mesh_quality.json --debug-image logs/mesh_quality.png before export or texture work.",
            "Run scanners/reference_model_library.py --root <reference_models_root> --output logs/reference_model_library.json --debug-image logs/reference_model_library.png to preserve metadata-only dimensions, rig signals, and texture standards from 3D donor bundles without copying source meshes into the bridge.",
            "Run examples/build_examples_library.py --sources-root <donor_projects_root> --output logs/examples_library.json --debug-image logs/examples_library.png to extract ranked donor profiles.",
            "Run examples/build_editor_library.py --sources-root <editor_donor_root> --output logs/editor_library.json --debug-image logs/editor_library.png to extract editor and fabrication donors.",
            "Run examples/build_modeling_library.py --sources-root <modeling_donor_root> --output logs/modeling_library.json --debug-image logs/modeling_library.png to extract character-runtime, object-structure, rigging, and export-finalization donors.",
            "Run examples/build_animation_library.py --sources-root <animation_donor_root> --output logs/animation_library.json --debug-image logs/animation_library.png to extract runtime-validation, animated-export, and Panda animation-map donors from character/animation tool packs.",
            "Run validators/animation_asset_validator.py --asset <base.glb> --clips-dir <clip_folder> --output logs/animation_asset_validation.json --debug-image logs/animation_asset_validation.png --screenshot logs/animation_asset_validation.png.runtime.png to verify that external FBX or GLB clips bind without collapsing in Panda3D.",
            "Run examples/build_2d_library.py --sources-root <prototype_lab_root> --output logs/two_d_library.json --debug-image logs/two_d_library.png to extract ranked 2D donors for side, top, hybrid, isometric, creature-generation, and atmosphere/UI workflows.",
            "Run reviewers/two_d_project_audit.py --root <prototype_lab_root> --output logs/two_d_project_audit.json --debug-image logs/two_d_project_audit.png to perform a full static compile and warning sweep over 2D donor projects before ingestion.",
            "Run model_router.py --target game_preview --examples-library logs/examples_library.json --editor-library logs/editor_library.json --modeling-library logs/modeling_library.json --animation-library logs/animation_library.json --two-d-library logs/two_d_library.json --reference-model-library logs/reference_model_library.json --json to combine backend routing with donor guidance, including metadata-only 3D reference standards and animation I/O donors.",
            "Run reviewers/controller_diagnostics.py --examples-library logs/examples_library.json --modeling-library logs/modeling_library.json --donor gib_player_controller --output logs/controller_diagnostics.json --debug-image logs/controller_diagnostics.png to inspect movement traces, jump arc, turning, and doorway clearance.",
            "Run reviewers/panda3d_patch_planner.py --target <project_main.py> --output logs/panda3d_patch_planner.json --debug-image logs/panda3d_patch_planner.png --snippet-output logs/panda3d_patch_snippet.py to plan helper insertion points before instrumenting an existing Panda3D project.",
            "Run salvage/code_preview_analysis.py <python_file> --output logs/code_preview_analysis.json --debug-image logs/code_preview_analysis.png to extract static symbol and preview signals from a donor or target project file.",
            "Run salvage/tool_function_salvager.py --sources <tool_root_a> <tool_root_b> <tool_root_c> --output logs/tool_salvage.json --debug-image logs/tool_salvage.png to map donor-tool functions into bridge-safe salvage lanes, including 2D texture and sprite-rig donors.",
            "Run salvage/texture_forge.py --operation tileable --image <sprite_or_texture.png> --image-output logs/texture_forge.png --output logs/texture_forge.json --debug-image logs/texture_forge_panel.png to quantize, tile, knockout, and palette-lock 2D textures or sprites.",
            "Run salvage/sprite_rig_lab.py --images <part_a.png> <part_b.png> --output logs/sprite_rig_lab.json --debug-image logs/sprite_rig_lab.png to extract pivot suggestions and cutout keyframe profiles for part-based 2D animation.",
            "Import reviewers.panda3d_trace_helper.install_trace_helper(...) inside a Panda3D project to expose grounded, collision, animation, eye-height, and radius hints directly to the recorder.",
            "Run reviewers/panda3d_trace_recorder.py --script samples/v12_trace_helper_demo.py --duration 3.5 --headless --output logs/panda3d_trace_recorder.json --debug-image logs/panda3d_trace_recorder.png to capture live Panda3D movement, camera, collision, and animation traces from a helper-instrumented running project.",
            "Run reviewers/screenshot_reviewer.py --image <path> --layout-profile gameplay --output logs/screenshot_review.json for screenshot review."
        ],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        ready = report["status"]["ready"]
        print("GPT bridge launch complete.")
        print(f"Panda3D ready: {ready}")
        for note in bootstrap_report["capabilities"]["notes"]:
            print(f"- {note}")
        if bootstrap_report.get("install_result") and not bootstrap_report["install_result"].get("ok"):
            print("- Auto-install attempt did not complete successfully. Check logs/panda3d_bootstrap.json.")
    return 0 if report["status"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
