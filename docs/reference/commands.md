# `nsx commands`

Shows the NSX command tree, arguments, and workflow hints.

This command is intended for both humans and agents. It exposes the CLI surface
in a way that supports workflow discovery without scraping prose docs or shell
help output.

## Syntax

```text
nsx commands [--json]
```

## Examples

Human-readable overview:

```bash
nsx commands
```

Machine-readable command graph:

```bash
nsx commands --json
```

## Notes

- `--json` is the preferred interface for LLM or agent tooling
- the output includes top-level commands, nested subcommands, argument metadata, and basic workflow hints
- this is intended to describe the canonical NSX CLI surface, not editor-specific or local environment assumptions
