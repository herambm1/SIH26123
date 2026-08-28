# CONTRIBUTING.md

Practical Git rules for our 6-person team, working alongside AI coding agents (Claude, Antigravity, Cursor). This is not a Git tutorial — it's our rulebook. If you need general Git help, ask your AI agent; this file only covers what's specific to *our* project.

---

## 0. Documentation Distribution Model

Two separate things exist for this project, and it matters that you don't mix them up:

```text
                    GitHub Repository
                          │
          ┌───────────────┼────────────────┐
          │               │                │
     CONTRIBUTING     Master Overview   Shared Contracts
     (this file)   (SIH_26123_Project   (docs/00_SHARED_
                    _Overview.md)        CONTRACTS.md,
                                          shared/python/
                                          models.py)
          │
          │  common Git rules
          ▼
    All 6 members
```

```text
Project Lead
    │
    ├── Member 1 → 01_PATH_PLANNING.md
    ├── Member 2 → 02_ROBOT_COMMUNICATION.md
    ├── Member 3 → 03_COORDINATION.md
    ├── Member 4 → 04_FRONTEND.md
    ├── Member 5 → 05_EDGE_ECE.md
    └── Member 6 → 06_BACKEND.md
```

**In the repository** (cloned by everyone): `README.md`, `CONTRIBUTING.md` (this file), `SIH_26123_Project_Overview.md`, `docs/00_SHARED_CONTRACTS.md`, `shared/python/models.py`. These are the shared, common references every member and every AI agent can read.

**Outside the repository**, distributed privately by the project lead: the six role specifications (`01_PATH_PLANNING.md` through `06_BACKEND.md`). Each member receives only their own file — this is deliberate, so a member's AI agent gets one clear implementation brief instead of six role specs it might mistake for permission to touch six modules.

What this means in practice:
- Your role MD is **not** in `docs/` and you will not find it by browsing the repo. Don't look for it there, and don't add it there.
- Don't commit your role MD to the repository, don't ask a teammate for theirs, and don't edit someone else's copy.
- When you start work, give your AI agent **your own role MD** (as a pasted document or local file, however your tool accepts it) alongside repository access. The AI reads the repo's master overview and shared contracts for architectural context, and your role MD for the specifics of what to build.

---

## 1. Our Branch Structure

```text
main
  ↓
develop
  ↓
individual feature branches
  ↓
Pull Request
  ↓
develop
```

- **`main`** = stable, demo-ready code only.
- **`develop`** = the integration branch where everyone's finished work meets.
- **You do not work directly on `main` or `develop`.** You work on your own feature branch and open a Pull Request into `develop` when it's ready.

| Member | Branch |
|---|---|
| 1 | `feature/astar-basic` |
| 2 | `feature/robot-communication` |
| 3 | `feature/coordination` |
| 4 | `feature/dashboard-map` |
| 5 | `feature/edge-interface` |
| 6 | `feature/backend-api` |

Don't invent new branch names for your primary work — use the one assigned to you above. (If you need a short-lived sub-branch for a specific fix, base it off your own branch, not `develop`.)

---

## 2. Module Ownership

| Member | Owns |
|---|---|
| 1 | `planner/` |
| 2 | `robot_agent/communication/` |
| 3 | `collision_engine/`, `robot_agent/agent.py`, `simulation/` |
| 4 | `dashboard/` |
| 5 | `edge/` |
| 6 | `backend/` |
| Shared | `shared/` and other explicitly shared project files (see §7) |

**Everyone can *read* the whole repository. Reading is not the same as owning or modifying.**

Your AI agent should normally only *modify* files inside your own owned folder(s), even though it's free to *read* other modules to understand their interfaces.

---

## 3. Why This Structure Minimizes Conflicts

Git branches don't magically prevent conflicts — two branches can still touch the same file and collide. What actually reduces conflicts is:

- **One owner per module.** Member 1 normally changes `planner/`. Member 6 normally changes `backend/`. Different folders, different people, near-zero overlap.
- **Separate folders.** If nobody else edits your folder, nobody else's work can collide with yours.
- **Stable shared contracts.** `shared/` doesn't change casually, so nobody's module breaks underneath them without warning.
- **Small commits and PRs.** Smaller changes are easier to review and merge cleanly.
- **Communication before touching shared files.** The one place conflicts *can* still happen — `shared/` — is exactly the place we agreed to talk before editing (§7).

If everyone stays inside their own folder, most days nobody sees a merge conflict at all.

---

## 4. Daily Workflow

```bash
# 1. See what state you're in
git status

# 2. Make sure you're on your own branch
git switch <your-branch>

# 3. Get the latest info from the remote (doesn't change your files yet)
git fetch origin

# 4. Bring develop's latest integrated changes into your branch
git merge origin/develop
```

**Now work — only inside your owned module(s) from §2.**

```bash
# 5. See what you changed
git status
git diff

# 6. Run your tests / build before committing
#    (pytest for Python modules, mvn test for backend;
#     for the dashboard, check package.json for the scripts that actually
#     exist there — npm run build is confirmed by the repo setup doc,
#     npm run dev to preview; don't assume npm test/lint exist unless
#     package.json actually defines them)

# 7. Stage only the files you actually meant to change
git add <specific files>

# 8. Commit with a clear message
git commit -m "..."

# 9. Push your branch
git push
```

**10. Open a Pull Request: your feature branch → `develop`.**

Quick command reference:
- `git status` — what's changed, what's staged.
- `git switch <branch>` — move to a different branch.
- `git fetch origin` — download the latest info from GitHub, doesn't touch your files.
- `git merge origin/develop` — merge those latest `develop` changes into your current branch.
- `git diff` — see the exact line-by-line changes before committing.
- `git add` — stage specific files for the next commit.
- `git commit -m "..."` — save a snapshot with a message.
- `git push` — upload your branch to GitHub.

---

## 5. Keep Commits Small

One commit = one logical change.

**Good:**
```
feat: implement basic A* planner
test: add planner tests
fix: handle blocked goal cell
```

**Bad:**
```
feat: implement entire project
```

Small commits make code review faster, make bugs easier to find (`git log` becomes a readable history instead of a wall of text), make it possible to roll back *one* thing without losing everything else, and make merge conflicts smaller and easier to resolve when they do happen.

---

## 6. Pull Request Rules

Every member merges finished work into `develop` through a PR — never a direct push to `develop`.

Your PR description should say:
- **What changed.**
- **What you tested.**
- **Which module it touches** (should match your ownership in §2).
- **Whether shared contracts were touched** (see §7 — this needs extra care).
- **Whether another member needs to know about an interface change** (e.g., "I changed what `plan()` returns" — tell the person who calls it).

A PR should contain only the change it claims to contain — no unrelated drive-by edits. Before opening one, run `git status` and `git diff` yourself and actually read them.

---

## 7. Shared Files

These are conflict-sensitive because more than one person's work depends on them:

```text
shared/python/models.py
docs/00_SHARED_CONTRACTS.md
(plus common configuration files, where applicable — e.g. root .gitignore, docker-compose.yml)
```

**Do not casually modify shared contracts.** If a contract genuinely needs to change:

1. Tell the team.
2. Explain why.
3. Identify which members/modules are affected.
4. Agree on the change together.
5. Make the change deliberately.
6. Update all required mirrors (Java DTOs, TypeScript interfaces — see `docs/00_SHARED_CONTRACTS.md`).
7. Test the affected modules.

**Keeping your role MD in sync.** Your role MD lives outside the repository (§0), so it can't update itself automatically when the shared architecture or contracts change. The rule is simple:

- When the shared architecture or contracts change, the project lead notifies whichever members are affected.
- If your module is affected, get the updated role MD from the project lead before continuing significant work on that part of it.
- **The repository always wins.** If anything in your local role MD ever conflicts with the current `SIH_26123_Project_Overview.md` or `docs/00_SHARED_CONTRACTS.md`, the repository is correct and your role MD is what's stale.
- Don't keep building against a role MD you know is outdated — if something in the repo has clearly moved on since your copy was written, stop and check with the project lead rather than guessing which version is current.

> **An AI coding agent must never silently change a shared contract just because it seems convenient in the moment.** If your AI suggests it, that's a "tell the team first" moment, not a "go ahead" moment.

---

## 8. AI Coding Rules

All six of us use AI coding agents — this is the section that matters most for avoiding chaos.

Give your AI:
- **your own role MD** — the implementation specification the project lead gave you privately (see §0). It is not part of the repository; provide it to your AI directly (paste it in, or point your tool at your own local copy).
- **repository access** so it can read the master overview (`SIH_26123_Project_Overview.md`) and the shared contracts (`docs/00_SHARED_CONTRACTS.md`, `shared/python/models.py`) for architectural context, and so it can inspect other modules to understand their interfaces.

Then instruct it to **work only within your ownership boundary** — reading other modules to understand an interface is fine; modifying them is not.

**GOOD prompt:**
> "You are implementing Member 1's path-planning module. I have provided you with the Member 1 role specification. Follow that specification and the repository's shared contracts. You may inspect other modules to understand their interfaces, but only modify files owned by Member 1 unless the team has explicitly coordinated a shared change."

**BAD prompts:**
> "Implement the entire project."
> "Read every role specification and improve the whole repository."
> "Fix anything you think is wrong."

If your AI notices something that looks wrong in another module or in a shared contract, it should **not** fix it automatically. It should report:
- what it thinks needs changing,
- why,
- which module is affected,

and then you bring that to the team, per §7. An AI seeing a "better" way to do something is not authorization to do it.

---

## 9. Git Command Safety With AI

Before letting an AI agent run any of these, stop and make sure you personally understand what it will do — don't auto-approve:

```text
git reset --hard
git clean -fd
git push --force
git branch -D
git rebase
```
...and anything involving large-scale file deletion or renaming.

Generally safe to let an AI run without a second thought (these only *look*, they don't change anything):

```text
git status
git log
git diff
git branch
git fetch
```

"Safe" here means read-only/inspection. You should still understand what any command does before running it — the point isn't to trust these blindly, it's that they can't hurt you if you get them wrong.

---

## 10. Merging / Syncing With `develop`

Our preferred approach, every time you sit down to work:

```bash
git fetch origin
git merge origin/develop
```

This brings the latest work everyone else has already merged into `develop` into your own branch, so you're never developing against stale code. We use **merge, not rebase** — rebasing is a sharper tool than a beginner team needs, and merge conflicts are easier to reason about when they do happen.

---

## 11. What To Do When a Merge Conflict Occurs

In plain terms: Member 1 and Member 3 both changed the same file. Git can't automatically decide whose change should win, so it stops and asks you.

**Rules:**

1. **Stop.** Don't panic-resolve.
2. **Read which file conflicted.**
3. **Figure out why both branches touched it.**
4. **If it's another member's module** — contact that owner before resolving.
5. **If it's a shared contract** — this is a §7 situation, discuss with the team.
6. **Resolve deliberately**, keeping the correct pieces of both changes.
7. **Test after resolving** — a clean merge that doesn't run is not actually resolved.
8. **Only then** commit the merge.

**Do not** blindly run `git checkout --ours` or `git checkout --theirs` to make the conflict marker disappear without understanding what you're throwing away — that's how a teammate's fix silently vanishes.

---

## 12. File Ownership + AI Boundaries (Reference Table)

| Member | Branch | Owns |
|---|---|---|
| 1 | `feature/astar-basic` | `planner/` |
| 2 | `feature/robot-communication` | `robot_agent/communication/` |
| 3 | `feature/coordination` | `collision_engine/`, `robot_agent/agent.py`, `simulation/` |
| 4 | `feature/dashboard-map` | `dashboard/` |
| 5 | `feature/edge-interface` | `edge/` |
| 6 | `feature/backend-api` | `backend/` |

**A branch is a workspace, not a permission slip.** Being on `feature/astar-basic` doesn't authorize editing `backend/` — ownership (§2) determines what you should normally touch, regardless of which branch you happen to be on.

---

## 13. Mock-First Development

Because we all work at the same time, don't wait on anyone:

- Use the documented interfaces from your role MD, not guesses.
- Use schema-correct mock data (matching `shared/python/models.py` / `docs/00_SHARED_CONTRACTS.md`), not made-up shapes.
- Swap mocks for the real thing later — this should be a small, contained change, not a rewrite.

This is also a Git-hygiene rule: mocking properly is what stops people from making emergency, out-of-ownership edits to someone else's unfinished module just to unblock themselves.

---

## 14. Before Every PR Checklist

```text
[ ] I am on my feature branch.
[ ] I only changed my module.
[ ] I did not accidentally modify another member's module.
[ ] I did not silently modify shared contracts.
[ ] I used the documented interfaces.
[ ] My tests/build pass.
[ ] I reviewed git diff.
[ ] No secrets/API keys are included.
[ ] No generated build artifacts are included.
[ ] My commit describes one logical change.
[ ] My PR targets develop.
```

---

## 15. Absolute Don'ts

**DO NOT:**
- work directly on `main`,
- work directly on `develop`,
- force-push,
- delete another member's branch,
- reset the repository blindly,
- blindly accept destructive AI Git commands,
- modify another member's module without coordination,
- silently change shared contracts,
- commit `.env` / secrets / API keys,
- commit `node_modules/`,
- commit `target/`,
- commit `__pycache__/`,
- merge unrelated work into a single PR,
- ask an AI to "fix the whole project."

---

## 16. Quick Reference

```text
START
  git status
  git switch <your-branch>

SYNC
  git fetch origin
  git merge origin/develop

WORK
  Only modify your owned module (§2).

CHECK
  git status
  git diff

COMMIT
  git add <files>
  git commit -m "..."

PUSH
  git push

INTEGRATE
  Open PR → develop
```
