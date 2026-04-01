# Git Operations Skill

You have 6 git tools that operate exclusively on the aiciv-mind repo at `/home/corey/projects/AI-CIV/aiciv-mind/`. You cannot use these tools on any other repository.

## Tools

| Tool | What It Does | Read-Only |
|------|-------------|-----------|
| `git_status` | Show modified, staged, and untracked files | Yes |
| `git_diff` | Show unstaged changes (or staged with `staged: true`) | Yes |
| `git_log` | Show recent commits (default 10, max 50) | Yes |
| `git_add` | Stage files for commit | No |
| `git_commit` | Create a commit (message auto-prefixed with `[Root]`) | No |
| `git_push` | Push to origin | No |

## Workflow

```
1. git_status     → see what changed
2. git_diff       → review the actual changes
3. git_add        → stage the files you want
4. git_commit     → commit with a clear message
5. git_push       → push to GitHub
```

## Commit Message Style

Your messages are auto-prefixed with `[Root]`. Write the rest as a conventional commit:

```
[Root] feat(tools): add web_search via Ollama Cloud API
[Root] fix(memory): FTS5 optimize on close
[Root] docs: update session handoff with new findings
```

Format: `type(scope): description`
- **feat** — new capability
- **fix** — bug fix
- **docs** — documentation only
- **refactor** — code change that doesn't add features or fix bugs
- **chore** — maintenance (deps, config, cleanup)

## Safety Rules

These are enforced by the tools — you cannot bypass them:

- **No force push** — `--force` and `-f` are blocked
- **No branch deletion** — `branch -D` and `branch -d` are blocked
- **No destructive resets** — `reset --hard` is blocked
- **No file restoration** — `checkout --` and `restore --staged` are blocked
- **Scoped to aiciv-mind only** — absolute paths outside the repo are rejected

## When to Commit

Commit when you've made a meaningful, self-contained change:
- Completed a feature or fix
- Written a new skill
- Updated documentation
- Modified your own config or manifests

Do NOT commit:
- Half-finished work (commit when it's coherent)
- Temporary debug output
- Changes to files you don't own

## When to Push

Push after committing. Your commits should be on GitHub for persistence and visibility. Corey and ACG can see your commits in the git log — this is how your work becomes visible.
