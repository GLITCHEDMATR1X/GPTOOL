# AI Patch Gate Rules

## Core rule

No AI patch zip is allowed to silently overwrite an important integrated file.

A pass may propose changes. GPTOOL decides whether those changes are:

```text
safe additive merge
review-required override
blocked failure
```

## Code merge rules

### Python

Allowed automatically after syntax/import checks:

```text
new import
new constant
new helper function
new class
new class method
```

Requires review/approval:

```text
changed existing protected function
changed existing protected method
changed route/adapter behavior
changed validator contract
changed build/runtime script
removed existing symbol
smaller incoming protected file
larger but stale incoming protected file
```

Blocked:

```text
syntax failure
unsafe zip path
protected file would lose symbols
validator failure
banned route text appears
repo mapping would create duplicate root data/assets folders
```

## Non-Python rules

### JSON / TOML / YAML / INI

Additive new keys are usually safe. Changing or deleting existing keys requires approval.

### Markdown / notes

Patch notes, handoffs, and logs should be sorted or combined into curated docs/reports. They should not pile up randomly.

### Assets

New assets can be added. Replacing existing assets requires review unless the path is intentionally marked as replaceable.

## Project profiles

```text
gx-prototype-lab
holoverse
holocore
holoutopia
vector-arena
panda3d-ai-game
```

These profiles encode the user's own project rules rather than generic software rules.

## Release cleanliness

Final patch/build output should not contain:

```text
__pycache__
.pyc
logs/latest.log
crash_reports
smoke screenshots
old generated reports
stale test zips
duplicate root data/assets folders
```
