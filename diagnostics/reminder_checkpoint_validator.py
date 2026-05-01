from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

ALLOWED_STATUSES = {"pass", "fail", "warn", "skipped", "unknown", "n/a", "none", "no_new_crash"}


class ReceiptValidationError(ValueError):
    pass


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_ack_text(text: str) -> Dict[str, Any]:
    receipt: Dict[str, Any] = {}
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        raise ReceiptValidationError("Acknowledgement text is empty.")

    header = lines[0]
    if header.upper().startswith("ACK "):
        receipt["step_id"] = header[4:].strip()
        lines = lines[1:]

    for line in lines:
        if "=" not in line:
            raise ReceiptValidationError(f"Receipt line is not key=value: {line}")
        key, value = line.split("=", 1)
        receipt[key.strip()] = value.strip()

    return receipt


def parse_receipt(receipt_input: Dict[str, Any] | str) -> Dict[str, Any]:
    if isinstance(receipt_input, dict):
        return dict(receipt_input)
    return parse_ack_text(receipt_input)


def _normalize_status(value: Any) -> str:
    return str(value).strip().lower()


def validate_receipt(step_id: str, card: Dict[str, Any], receipt_input: Dict[str, Any] | str) -> Dict[str, Any]:
    receipt = parse_receipt(receipt_input)
    errors: list[str] = []
    warnings: list[str] = []

    receipt_step = str(receipt.get("step_id", "")).strip()
    if receipt_step and receipt_step != step_id:
        errors.append(f"Receipt step_id mismatch: expected '{step_id}', got '{receipt_step}'.")

    for field in card.get("required_ack_fields", []):
        value = receipt.get(field)
        if value is None or str(value).strip() == "":
            errors.append(f"Missing required acknowledgement field: {field}")

    pass_if = card.get("pass_if", {})
    if pass_if.get("all_required_fields_present"):
        pass

    for field, allowed_values in pass_if.items():
        if field == "all_required_fields_present":
            continue
        if not isinstance(allowed_values, list):
            continue
        actual = _normalize_status(receipt.get(field, ""))
        allowed = {_normalize_status(v) for v in allowed_values}
        if actual not in allowed:
            errors.append(
                f"Field '{field}' did not satisfy pass rule. Got '{receipt.get(field, '')}', allowed: {sorted(allowed)}"
            )

    for key, value in receipt.items():
        if key.endswith("_status"):
            normalized = _normalize_status(value)
            if normalized and normalized not in ALLOWED_STATUSES:
                warnings.append(f"Status field '{key}' used non-standard value '{value}'.")

    return {
        "passed": not errors,
        "step_id": step_id,
        "receipt": receipt,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate a blocking reminder checkpoint acknowledgement receipt.")
    ap.add_argument("--card", required=True, help="Path to a reminder card JSON file or a JSON file containing a single card object.")
    ap.add_argument("--step-id", required=True)
    ap.add_argument("--receipt", required=True, help="Path to receipt file. JSON object or ACK text are supported.")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    card_path = Path(args.card)
    card_payload = load_json(card_path)
    if 'cards' in card_payload:
        lookup = {str(item['id']): item for item in card_payload.get('cards', [])}
        if args.step_id not in lookup:
            raise ReceiptValidationError(f"Step '{args.step_id}' not found in card set: {card_path}")
        card = lookup[args.step_id]
    else:
        card = card_payload
    receipt_path = Path(args.receipt)
    raw_receipt = receipt_path.read_text(encoding="utf-8")
    if receipt_path.suffix.lower() == ".json":
        receipt_input: Dict[str, Any] | str = json.loads(raw_receipt)
    else:
        receipt_input = raw_receipt

    result = validate_receipt(args.step_id, card, receipt_input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
