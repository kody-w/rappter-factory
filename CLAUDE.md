# CLAUDE.md — rappter-factory

## What This Is

**rappter-factory** is the foundation repo — the base scaffold from which all Rappter projects are generated. It contains the core tooling, configurations, and conventions that every project inherits. Changes here propagate downstream, so treat this repo with care.

## Repository Structure

```
rappter-factory/
├── CLAUDE.md              # This file — AI assistant guide and project documentation
└── (scaffolding TBD)      # Templates, configs, and tooling to be added
```

> Update this tree as the repo grows. Keep it current.

## Purpose & Philosophy

This repo exists to solve one problem: **every new project should start with a working foundation** — linting, formatting, testing, CI/CD, Docker, and sensible defaults — so teams never waste time on boilerplate setup.

Principles:
- **Opinionated defaults, easy overrides** — ship strong conventions but don't lock projects in
- **Nothing unused** — every file in this repo should serve a purpose in generated projects
- **Keep it minimal** — add what's needed, nothing speculative

## Development Setup

### Prerequisites

- Git

### Getting Started

```bash
git clone <repository-url>
cd rappter-factory
```

## Development Workflow

### Branch Naming

- Feature branches: `feature/<description>`
- Bug fixes: `fix/<description>`
- Documentation: `docs/<description>`

### Commit Messages

Conventional commit format:

```
type(scope): short description
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Making Changes

1. Create a branch from `main`
2. Make focused, minimal changes
3. Test that generated/scaffolded projects still work
4. Open a PR with a clear description

## Code Conventions

- Write clear, self-documenting code
- Keep functions focused and small
- Add tests for new functionality
- No dead code, no commented-out blocks
- Config files should include brief inline comments explaining non-obvious settings

## Testing

```bash
# Run tests (update once test framework is chosen)
```

## CI/CD

> Update with pipeline details once configured.

## AI Assistant Guidelines

When working in this repository:

1. **Read before writing** — always read existing files before modifying them
2. **Minimal changes** — only change what's necessary to accomplish the task
3. **Don't over-engineer** — keep solutions simple and focused
4. **Preserve existing patterns** — follow conventions already established in the codebase
5. **Test your changes** — run the test suite after making changes
6. **No secrets** — never commit `.env` files, API keys, or credentials
7. **This is a foundation repo** — changes here affect every project generated from it, so be deliberate
8. **Update this file** — when you add tooling, configs, or conventions, update this CLAUDE.md to reflect them
