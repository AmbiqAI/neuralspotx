# Agent Guidance

The repository's canonical instructions for AI agents and automated
contributors live in [`AGENTS.md`](https://github.com/AmbiqAI/neuralspotx/blob/main/AGENTS.md).
Read that file before making changes; it contains the current architectural
rules, workflow expectations, environment-variable policy, schema-versioning
policy, and validation commands.

At a high level, contributions should preserve NSX's app-first,
app-locally-vendored, registry-driven design. Shared behavior belongs in the
operations layer, the Python API and CLI should delegate to it, and generated
content should use the repository's Jinja templating path. The public
`pipx`-installed workflow must remain functional.

This page intentionally does not duplicate the full guide. Update
`AGENTS.md` when those rules change so repository automation has one source of
truth.
