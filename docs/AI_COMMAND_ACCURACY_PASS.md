# AI Command Accuracy Pass

The GPT Tool is now aimed more directly at AI-assisted game development.

Instead of only validating code after an edit, the bridge can first translate the user's natural-language command into a strict AI work order.

## Main flow

```bash
python bridge.py plan-command . --profile holoverse --command "remove the fps counter and show points only small in the top-right"
```

This writes:

```text
reports/work_order.json
reports/work_order.md
```

Then the AI edits the game while following the work order.

After the edit:

```bash
python bridge.py full-pass . --profile holoverse --work-order reports/work_order.json --changed-files HoloVerse/world.py --runtime auto --smoke --require-screenshot
```

Or verify only the command scope:

```bash
python bridge.py verify-command . --work-order reports/work_order.json --changed-files HoloVerse/world.py
```

## Work order sections

The work order contains:

- `must_do`: required changes.
- `must_not_do`: forbidden mistakes.
- `do_not_touch`: areas the AI should avoid unless necessary.
- `affected_areas`: likely project areas touched by the request.
- `scope_hints`: file/path keywords that should usually match changed files.
- `acceptance_tests`: validation checks needed for delivery.
- `visual_tests`: screenshot/visual proof expectations.
- `runtime_tests`: smoke/route checks.
- `static_checks`: source-level terms to review.
- `regression_risks`: likely ways the AI could accidentally break the project.

## Example

User command:

```text
remove the fps counter and its ui box entirely. it should just display the current points we gathered from all modes in total and no ui background box for it. small and in the right corner.
```

The bridge generates rules such as:

- remove player-visible FPS counter,
- remove FPS UI background box,
- display points clearly,
- place points in the top-right/right corner,
- keep UI compact,
- forbid visible FPS text,
- require points display proof,
- warn if remaining FPS references need review.

## Strict mode

By default, static source hits for terms like `fps` are warnings because debug variables may remain legitimately gated off. To make them blockers:

```bash
python bridge.py verify-command . --work-order reports/work_order.json --strict-static
```

## Important limitation

This pass does not use an external LLM. It is deterministic and rule-based. That makes it safe and predictable, but it still needs project-specific vocabulary expansions over time.
