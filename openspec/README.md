# OpenSpec

This repository uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) to keep
proposed changes and living specifications alongside the code.

- `changes/` contains active proposals, designs, requirement deltas, and tasks.
- `changes/archive/` contains completed changes and their decision history.
- `specs/` describes current behavior after completed changes are archived.

## Quickstart

Install the OpenSpec CLI:

```sh
npm install -g @fission-ai/openspec@latest
```

Configure OpenSpec for your coding agent:

```sh
openspec init
```

Restart the agent after setup so it discovers the generated workflows.

Useful commands:

```sh
openspec list
openspec show <change>
openspec validate <change> --strict
```

With an agent integration installed, use `/opsx:propose` to prepare a change,
`/opsx:apply` to implement one, and `/opsx:archive` after implementation and
verification. See the [OpenSpec
quickstart](https://github.com/Fission-AI/OpenSpec#quick-start) for the complete
workflow.
