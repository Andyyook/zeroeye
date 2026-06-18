# Contributing to Tent of Trials / zeroeye

Thank you for your interest! This project uses a bounty-based contribution model.
Pick an open issue with a `bounty` label, claim it, and submit a PR to earn.

## Quick Start

### Prerequisites

- **Python 3.10+** — core build tooling and diagnostics
- **Git** — version control
- **One or more of:** Rust / Go / Node.js 22+ / Java 21+ / Ruby / Lua / GHC / C++17+ (depending on which module you target)

### Clone

```bash
git clone https://github.com/lobster-trap/TentOfTrials
cd TentOfTrials
```

### Build Everything

```bash
python3 build.py
```

This generates diagnostic output in `diagnostic/` that must be committed with your PR.

### Build Specific Modules

```bash
python3 build.py --target backend,frontend
python3 build.py --target market --skip-diagnostics
```

### Run Tests

```bash
# Backend (Rust)
cd backend && cargo test

# Frontend (TypeScript)
cd frontend && npm test

# Market (Go)
cd market && go test ./...

# Python tools
python3 -m pytest tools/
```

## Bounty Workflow

1. **Find an open bounty** — look for issues with the `bounty` label and no `/claim` comment
2. **Claim it** — comment `/claim` on the issue (opire bot will assign it to you, or start the review process)
3. **Fork + branch** — create a feature branch from `main`
4. **Implement** — follow the acceptance criteria in the issue
5. **Run build** — `python3 build.py` must succeed locally
6. **Commit diagnostics** — the `diagnostic/` folder output must be committed with your PR
7. **Submit PR** — open a pull request against `lobster-trap/zeroeye:main`
8. **Submit claim** — comment `/submit` on the original issue with your PR link

The maintainers will review within a few days. Once merged, the bounty is paid.

## Code Standards

- **Python**: PEP 8, 4-space indentation, type hints encouraged
- **Rust**: `rustfmt` default style
- **TypeScript/JS**: Prettier with 2-space indent
- **Go**: `gofmt` (tab indentation)
- **All languages**: LF line endings, UTF-8 encoding, trailing newline

See `.editorconfig` for per-language formatting rules.

## PR Checklist

Before submitting:

- [ ] `python3 build.py` runs without errors
- [ ] Diagnostic output is committed in the `diagnostic/` directory
- [ ] Code follows the project's formatting conventions
- [ ] Tests pass for affected modules
- [ ] PR description explains what was changed and why
- [ ] The original bounty issue number is referenced in the PR description

## Questions?

Open a discussion or comment on the relevant issue. The maintainers monitor the repo regularly.

*This project uses [opire](https://opire.dev) for bounty management.*
