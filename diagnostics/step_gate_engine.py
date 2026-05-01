from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from diagnostics.reminder_checkpoint_validator import validate_receipt
except ModuleNotFoundError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from diagnostics.reminder_checkpoint_validator import validate_receipt


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_cards(cards_path: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(cards_path)
    cards = payload.get("cards", [])
    return {str(card["id"]): card for card in cards}


def load_workflow(workflow_path: Path) -> Dict[str, Any]:
    return load_json(workflow_path)


def build_session(
    project_name: str,
    workflow: Dict[str, Any],
    cards: Dict[str, Dict[str, Any]],
    profile: str = "panda3d",
    authoritative_root: str | None = None,
    candidate_root: str | None = None,
) -> Dict[str, Any]:
    steps = workflow.get("steps", [])
    if not steps:
        raise ValueError("Workflow has no steps.")
    missing_cards = [step_id for step_id in steps if step_id not in cards]
    if missing_cards:
        raise ValueError(f"Workflow references steps without cards: {missing_cards}")

    first_step = steps[0]
    return {
        "bridge_version": "0.5.0",
        "project_name": project_name,
        "profile": profile,
        "workflow_id": workflow.get("workflow_id", "default"),
        "workflow_steps": steps,
        "completed_steps": [],
        "pending_step": first_step,
        "allowed_actions": ["acknowledge_step"],
        "blocked_actions": cards[first_step].get("forbidden_actions", []),
        "authoritative_root": authoritative_root,
        "candidate_root": candidate_root,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "step_receipts": [],
        "status": "blocked_pending_ack",
    }


def get_step_index(session: Dict[str, Any], step_id: str) -> int:
    return session.get("workflow_steps", []).index(step_id)


def get_card(session: Dict[str, Any], cards: Dict[str, Dict[str, Any]], step_id: str | None = None) -> Dict[str, Any]:
    target = step_id or session.get("pending_step")
    if not target:
        raise ValueError("No pending step remains.")
    return cards[target]


def render_card_text(step_id: str, card: Dict[str, Any], session: Dict[str, Any] | None = None) -> str:
    lines = [
        f"STEP {step_id}",
        f"TITLE: {card.get('title', step_id)}",
    ]
    if session:
        lines.append(f"PROJECT: {session.get('project_name', 'unknown')}")
        lines.append(f"PROFILE: {session.get('profile', 'unknown')}")
        if session.get("authoritative_root"):
            lines.append(f"AUTHORITATIVE_ROOT: {session['authoritative_root']}")
        if session.get("candidate_root"):
            lines.append(f"CANDIDATE_ROOT: {session['candidate_root']}")
    if card.get("why"):
        lines.append(f"WHY: {card['why']}")
    lines.append("HARD REMINDERS:")
    lines.extend(f"- {item}" for item in card.get("hard_reminders", []))
    lines.append("FORBIDDEN ACTIONS:")
    lines.extend(f"- {item}" for item in card.get("forbidden_actions", []))
    lines.append("REQUIRED ACK FIELDS:")
    lines.extend(f"- {item}" for item in card.get("required_ack_fields", []))
    lines.append("REPLY FORMAT:")
    lines.append(f"ACK {step_id}")
    for field in card.get("required_ack_fields", []):
        lines.append(f"{field}=<value>")
    return "\n".join(lines)


def _next_step(session: Dict[str, Any]) -> str | None:
    steps = session.get("workflow_steps", [])
    completed = set(session.get("completed_steps", []))
    for step_id in steps:
        if step_id not in completed:
            return step_id
    return None


def acknowledge_step(
    session: Dict[str, Any],
    cards: Dict[str, Dict[str, Any]],
    receipt_input: Dict[str, Any] | str,
    step_id: str | None = None,
) -> Dict[str, Any]:
    target = step_id or session.get("pending_step")
    if not target:
        raise ValueError("Workflow already completed.")

    card = get_card(session, cards, target)
    result = validate_receipt(target, card, receipt_input)
    session["updated_at"] = utc_now_iso()
    session.setdefault("step_receipts", []).append(
        {
            "step_id": target,
            "timestamp": session["updated_at"],
            "passed": result["passed"],
            "errors": result["errors"],
            "warnings": result["warnings"],
            "receipt": result["receipt"],
        }
    )

    if not result["passed"]:
        session["status"] = "blocked_receipt_failed"
        session["allowed_actions"] = ["acknowledge_step"]
        session["blocked_actions"] = card.get("forbidden_actions", [])
        session["pending_step"] = target
        return {"session": session, "validation": result}

    if target not in session.setdefault("completed_steps", []):
        session["completed_steps"].append(target)
    next_step = _next_step(session)
    session["pending_step"] = next_step
    if next_step is None:
        session["status"] = "workflow_complete"
        session["allowed_actions"] = ["export_report", "promote_candidate", "deliver"]
        session["blocked_actions"] = []
    else:
        session["status"] = "blocked_pending_ack"
        session["allowed_actions"] = ["acknowledge_step"]
        session["blocked_actions"] = cards[next_step].get("forbidden_actions", [])
    return {"session": session, "validation": result}


def guarded_action(session: Dict[str, Any], action_name: str) -> Dict[str, Any]:
    allowed = set(session.get("allowed_actions", []))
    if action_name not in allowed:
        return {
            "passed": False,
            "blocked": True,
            "pending_step": session.get("pending_step"),
            "status": session.get("status"),
            "message": f"Action '{action_name}' blocked until step '{session.get('pending_step')}' is acknowledged.",
        }
    return {
        "passed": True,
        "blocked": False,
        "pending_step": session.get("pending_step"),
        "status": session.get("status"),
    }


def update_memory(memory_path: Path, session: Dict[str, Any]) -> Dict[str, Any]:
    memory = load_json(memory_path) if memory_path.exists() else {"projects": {}}
    projects = memory.setdefault("projects", {})
    entry = projects.setdefault(session["project_name"], {})
    entry.update(
        {
            "profile": session.get("profile"),
            "authoritative_root": session.get("authoritative_root"),
            "candidate_root": session.get("candidate_root"),
            "workflow_id": session.get("workflow_id"),
            "last_step_gate_status": session.get("status"),
            "last_pending_step": session.get("pending_step"),
            "last_updated_at": session.get("updated_at"),
            "step_receipts": session.get("step_receipts", []),
        }
    )
    memory["bridge_version"] = "0.5.0"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps(memory, indent=2), encoding="utf-8")
    return memory


def main() -> int:
    ap = argparse.ArgumentParser(description="Blocking reminder step gate engine for GPT Game Generation Bridge.")
    sub = ap.add_subparsers(dest="command", required=True)

    init_ap = sub.add_parser("init")
    init_ap.add_argument("--project-name", required=True)
    init_ap.add_argument("--workflow", default="rules/workflow_sequence.json")
    init_ap.add_argument("--cards", default="rules/reminder_cards.json")
    init_ap.add_argument("--profile", default="panda3d")
    init_ap.add_argument("--authoritative-root")
    init_ap.add_argument("--candidate-root")
    init_ap.add_argument("--output", required=True)
    init_ap.add_argument("--memory")

    card_ap = sub.add_parser("show-card")
    card_ap.add_argument("--session", required=True)
    card_ap.add_argument("--cards", default="rules/reminder_cards.json")
    card_ap.add_argument("--step-id")
    card_ap.add_argument("--output")

    ack_ap = sub.add_parser("ack")
    ack_ap.add_argument("--session", required=True)
    ack_ap.add_argument("--cards", default="rules/reminder_cards.json")
    ack_ap.add_argument("--receipt", required=True)
    ack_ap.add_argument("--step-id")
    ack_ap.add_argument("--output", required=True)
    ack_ap.add_argument("--memory")

    guard_ap = sub.add_parser("guard")
    guard_ap.add_argument("--session", required=True)
    guard_ap.add_argument("--action", required=True)
    guard_ap.add_argument("--output", required=True)

    args = ap.parse_args()

    if args.command == "init":
        workflow = load_workflow(Path(args.workflow))
        cards = load_cards(Path(args.cards))
        session = build_session(
            project_name=args.project_name,
            workflow=workflow,
            cards=cards,
            profile=args.profile,
            authoritative_root=args.authoritative_root,
            candidate_root=args.candidate_root,
        )
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(session, indent=2), encoding="utf-8")
        if args.memory:
            update_memory(Path(args.memory), session)
        return 0

    if args.command == "show-card":
        session = load_json(Path(args.session))
        cards = load_cards(Path(args.cards))
        step_id = args.step_id or session.get("pending_step")
        text = render_card_text(step_id, get_card(session, cards, step_id), session)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0

    if args.command == "ack":
        session = load_json(Path(args.session))
        cards = load_cards(Path(args.cards))
        receipt_path = Path(args.receipt)
        raw = receipt_path.read_text(encoding="utf-8")
        receipt_input: Dict[str, Any] | str = json.loads(raw) if receipt_path.suffix.lower() == ".json" else raw
        result = acknowledge_step(session, cards, receipt_input=receipt_input, step_id=args.step_id)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        Path(args.session).write_text(json.dumps(result["session"], indent=2), encoding="utf-8")
        if args.memory:
            update_memory(Path(args.memory), result["session"])
        return 0 if result["validation"]["passed"] else 2

    if args.command == "guard":
        session = load_json(Path(args.session))
        result = guarded_action(session, args.action)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0 if result["passed"] else 2

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
