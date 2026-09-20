This command is intended for both humans and agents. It exposes the CLI surface in a way
that supports workflow discovery without scraping prose docs or shell help output.

```bash
# Human-readable overview
nsx commands

# Machine-readable command graph
nsx commands --json
```

`--json` is the preferred interface for LLM or agent tooling. The output includes
top-level commands, nested subcommands, argument metadata and basic workflow hints. It
describes the canonical NSX CLI surface, not editor-specific or local environment
assumptions.
