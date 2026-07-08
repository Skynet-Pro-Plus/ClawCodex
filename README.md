# ClawCodex

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Rust](https://img.shields.io/badge/Rust-stable-orange.svg)](https://www.rust-lang.org/)
[![Status: Research](https://img.shields.io/badge/Status-Research-orange.svg)](#disclaimer)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D4.svg)](#quick-start)

> A packaged distribution of the `claw` CLI agent harness — an autonomous coding agent coordination system built in Rust, designed for machine-driven development workflows where humans set direction and agents execute the work.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Tool Capabilities](#tool-capabilities)
- [Security Boundaries](#security-boundaries)
- [Documentation](#documentation)
- [Tech Stack](#tech-stack)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)
- [Disclaimer](#disclaimer)

---

## Overview

ClawCodex is a research-grade agentic coding harness built around the idea that the **system that produces the commits** is more important than the diffs themselves. The active implementation lives in the Rust workspace under [`rust/`](./rust), with a Windows launcher and optional bundled binary.

The harness is designed to be "clawable" — deterministic to start, machine-readable in state and failure modes, recoverable without a human watching the terminal, and capable of autonomous next-step execution through hooks, plugins, sessions, and channel events.

## Key Features

- **Multi-provider authentication** — OpenRouter, Cerebras, Z.ai, DeepSeek, and Kimi with live key validation and model selection
- **Autonomous agent coordination** — parallel coding agents that plan, execute, review, and retry automatically
- **Worker lifecycle management** — create, observe, restart, and terminate agent worker processes
- **Task orchestration** — structured task tracking with packet-based creation, status updates, and output retrieval
- **MCP protocol integration** — discover and invoke tools exposed by Model Context Protocol servers
- **Plugin extensibility** — load custom tools through plugin manifests with JSON schema validation
- **Language Server Protocol support** — interact with LSP-backed code intelligence features
- **Scheduling and team coordination** — cron jobs, team groupings, and coordinated multi-agent work
- **Hooks system** — local command execution surface for custom workflow integration
- **Sandboxed execution** — platform-dependent isolation with namespace/network sandboxing on Linux

## Quick Start

### Windows (Recommended)

1. Clone the repository:
   ```powershell
   git clone https://github.com/Skynet-Pro-Plus/ClawCodex C:\clawcodex
   cd C:\clawcodex
   ```

2. Double-click [`START-CLAW.bat`](./START-CLAW.bat).

3. Choose a provider: **OpenRouter**, **Cerebras**, **Z.ai**, **DeepSeek**, or **Kimi**.

4. Paste your API key when prompted (input is hidden). Credentials are saved to repo-root `.env` and validated live.

5. The launcher runs `claw doctor`, then starts the REPL with your chosen provider and model.

### Useful Commands

```bat
START-CLAW.bat
run-claw.bat
run-claw.bat doctor
```

## Architecture

```
ClawCodex/
├── rust/                    # Rust workspace (primary implementation)
│   ├── crates/
│   │   ├── runtime/         # Core runtime and orchestration
│   │   ├── rusty-claude-cli/# CLI entry point and REPL
│   │   ├── tools/           # Built-in tool implementations
│   │   ├── plugins/         # Plugin system
│   │   ├── commands/        # Command dispatch
│   │   ├── repo-intel/      # Repository analysis
│   │   ├── api/             # API layer
│   │   ├── telemetry/       # Observability and metrics
│   │   ├── compat-harness/  # Compatibility testing
│   │   └── mock-anthropic-service/ # Test harness
│   ├── scripts/             # Build and test scripts
│   └── Cargo.toml           # Workspace manifest
├── bin/windows/             # Windows launcher and bundled binary
├── docs/                    # Documentation
├── frontend/                # Web UI components
├── Containerfile            # Container support
├── USAGE.md                 # Setup and workflow guide
├── PARITY.md                # Parity and migration status
├── ROADMAP.md               # Planned work and known gaps
└── PHILOSOPHY.md            # Project intent and framing
```

## Tool Capabilities

ClawCodex extends beyond direct file edits with a rich tool surface:

| Category | Tools |
|----------|-------|
| **Discovery** | `WebFetch`, `WebSearch`, `ToolSearch` |
| **Planning** | `TodoWrite`, `Skill`, `Config`, `EnterPlanMode`, `ExitPlanMode` |
| **Tasks** | `TaskCreate`, `RunTaskPacket`, `TaskGet`, `TaskList`, `TaskUpdate`, `TaskOutput`, `TaskStop` |
| **Workers** | `WorkerCreate`, `WorkerGet`, `WorkerObserve`, `WorkerSendPrompt`, `WorkerRestart`, `WorkerTerminate` |
| **Teams** | `TeamCreate`, `TeamDelete`, `CronCreate`, `CronList`, `CronDelete` |
| **Integration** | `LSP`, `MCP`, `ListMcpResources`, `ReadMcpResource`, `RemoteTrigger` |

Not every tool is available in every environment. Some depend on configured MCP servers, worker state, or permission mode.

### Extension Surfaces

- **Plugin tools** — Define a tool name, description, JSON schema, command, and permission in a plugin manifest.
- **MCP tools** — Configure MCP servers to expose tools and resources that ClawCodex discovers at runtime.

## Security Boundaries

Hooks are an intentional local command execution surface. Treat hook configuration from a project or shared repository as trusted code — hooks run through the host shell, can see tool payloads, and may influence permission decisions.

Sandbox strength is platform-dependent. Full namespace/network isolation is Linux-specific when user namespaces are available. Windows and macOS runs should be treated as host-shell execution with weaker environment scoping.

## Documentation

| Document | Description |
|----------|-------------|
| [USAGE.md](./USAGE.md) | Setup, auth, launch commands, and common workflows |
| [rust/README.md](./rust/README.md) | Rust workspace layout and crate responsibilities |
| [PARITY.md](./PARITY.md) | Parity and migration status |
| [ROADMAP.md](./ROADMAP.md) | Planned work and known gaps |
| [PHILOSOPHY.md](./PHILOSOPHY.md) | Project intent, framing, and credits |

## Tech Stack

- **Language:** Rust (primary), Python (auxiliary scripts and API server)
- **Frameworks:** FastAPI, Uvicorn, Pydantic (API layer)
- **Tooling:** Cargo, PyInstaller
- **Platform:** Windows (primary), Linux (container support)

## Contributing

This repository is for research and experimentation. If you find issues or have improvements, feel free to open an issue or submit a pull request. Please ensure any changes are consistent with the project's research-oriented direction.

## Credits

**Johnny Export** — This repository explicitly credits Johnny Export for his work and philosophy: treating autonomous agent coordination, not only files on disk, as the product lesson, and centering the idea that humans set direction while claws perform the labor. See [`PHILOSOPHY.md`](./PHILOSOPHY.md) for the full acknowledgment.

## License

This project is licensed under the [MIT License](LICENSE).

## Disclaimer

- This repository is for **research and experimentation only**.
- This repository does not claim ownership of the original Claude Code source material.
- This repository is not affiliated with, endorsed by, or maintained by Anthropic.
