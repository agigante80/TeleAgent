# Supply-Chain Security Hardening (`detect-secrets`, dependency pinning)

> Status: **Planned** | Priority: Medium | Last reviewed: 2026-03-16

Harden the CI pipeline and dependency management against supply-chain attacks by adding
pre-commit secret detection, tightening Python dependency pins, and complementing the
Trivy/CodeQL/pip-audit work planned in `improved-security-scanning.md`.

---

## Team Review

> Managed automatically by the team review process — see `docs/guides/feature-review-process.md`.
> To start a review, ask any team member: `dev Please start a feature review of docs/features/supply-chain-hardening.md`

| Reviewer | Round | Score | Date | Notes |
|----------|-------|-------|------|-------|
| GateCode | 1 | -/10 | - | Pending |
| GateSec  | 1 | -/10 | - | Pending |
| GateDocs | 1 | -/10 | - | Pending |

**Status**: ⏳ Pending review
**Approved**: No — requires all scores ≥ 9/10 in the same round

---

## ⚠️ Prerequisite Questions

> Answer these before writing a single line of code. A wrong assumption at the start
> costs 10× more to fix than a clarification takes.

1. **Scope** — CI/CD pipeline + `requirements.txt` + `requirements-dev.txt` only. No
   runtime code, no bot commands, no platform changes.
2. **Backend** — N/A — this feature does not touch AI backends.
3. **Stateful vs stateless** — N/A.
4. **Breaking change?** — No. Tighter pins may require `pip install --upgrade` on dev
   machines after pulling, but no env var, command, or Docker volume changes. PATCH bump.
5. **New dependency?** — `detect-secrets` added to `requirements-dev.txt` for local
   baseline regeneration. CI installs it inline (`pip install detect-secrets`).
6. **Persistence** — `.secrets.baseline` JSON file committed to repo root. No DB changes.
7. **Auth** — No new secrets. `GITHUB_TOKEN` (automatic) suffices.
8. **Overlap with `improved-security-scanning.md`** — That spec (Approved, roadmap 2.1)
   covers Trivy noise reduction, CodeQL SAST, and `pip-audit`. This spec covers the two
   medium-priority gaps *not* addressed there: secret detection and dependency pinning.
   The two specs are complementary and can be implemented independently.

---

## Problem Statement

1. **No secret detection in CI** — A developer can accidentally commit an API key, Slack
   token, or GitHub PAT to the repository, and no CI check will catch it. The runtime
   `SecretRedactor` (`src/redact.py`) only scrubs *bot output* — it does not scan source
   code. There is no `.pre-commit-config.yaml` or baseline file. This is a direct path
   to credential leaks in a public (or shared-private) repository.

2. **Loose dependency pinning** — 8 of 9 production dependencies in `requirements.txt`
   use open-ended `>=X.Y` ranges with no upper bound (e.g., `openai>=1.0`,
   `anthropic>=0.28`). All 5 dev dependencies follow the same pattern. A malicious or
   buggy upstream release can silently compromise or break builds. The single wildcard
   pin (`python-telegram-bot[job-queue]==22.*`) is better but still allows ~100 patch
   versions.

3. **No hash verification** — `pip install --no-cache-dir -r requirements.txt` in the
   Dockerfile (line 39) does not use `--require-hashes`. A compromised PyPI mirror or
   man-in-the-middle attack could substitute a tampered package without detection.

4. **Trivy and pip-audit gaps** — Trivy container scanning exists but uses an unpinned
   action ref (`@master`) and runs non-blocking (`exit-code: '0'`). No `pip-audit` step
   exists. *Both gaps are addressed by `improved-security-scanning.md` (roadmap 2.1)
   and are listed here for completeness only — no duplicate implementation needed.*

**Affected users**: all maintainers and contributors. Self-hosters who fork the repo
inherit the same weak pinning.

---

## Current Behaviour (as of v`0.20.x`)

| Layer | Location | Current behaviour |
|-------|----------|-------------------|
| CI — secret scan | `.github/workflows/ci-cd.yml` | No secret detection step exists |
| Pre-commit | `.pre-commit-config.yaml` | File does not exist |
| Baseline | `.secrets.baseline` | File does not exist |
| Prod deps | `requirements.txt:1` | `python-telegram-bot[job-queue]==22.*` — wildcard pin |
| Prod deps | `requirements.txt:2-9` | All use `>=X.Y` — no upper bound (`pydantic-settings>=2.0`, `openai>=1.0`, etc.) |
| Dev deps | `requirements-dev.txt:1-5` | All use `>=X.Y` — no upper bound |
| Docker build | `Dockerfile:39` | `pip install --no-cache-dir` — no `--require-hashes` |
| CI — Trivy | `ci-cd.yml:347-354` | `aquasecurity/trivy-action@master`, `exit-code: '0'` — *addressed by roadmap 2.1* |
| CI — pip-audit | N/A | Does not exist — *addressed by roadmap 2.1* |
| Runtime redactor | `src/redact.py` | Scrubs bot output only; does not scan source commits |

> **Key gap**: The repository has *zero* pre-merge defences against committed secrets,
> and the dependency supply chain is unverified — any upstream release within the
> open-ended ranges is trusted implicitly.

---

## Design Space

### Axis 1 — Secret detection approach

#### Option A — CI-only `detect-secrets` step

Run `detect-secrets scan` in CI and diff against a committed baseline. No local hooks.

**Pros:**
- Zero local setup for contributors
- Catches secrets on every push/PR

**Cons:**
- Secrets reach the remote before being flagged (already in git history)
- Developer must manually rewrite history to remove them

---

#### Option B — `detect-secrets` as pre-commit hook + CI gate *(recommended)*

Commit a `.pre-commit-config.yaml` with `detect-secrets` and add a CI step that runs
the same scan. Developers who install pre-commit catch secrets locally; CI is the safety
net for those who don't.

**Pros:**
- Secrets caught *before* they leave the developer's machine (if hooks installed)
- CI gate ensures no bypass
- `.secrets.baseline` tracks known false positives — prevents alert fatigue

**Cons:**
- Developers must run `pre-commit install` once (documented, not enforced)

**Recommendation: Option B** — defence in depth: local hook + CI gate.

---

#### Option C — GitHub push protection (native)

Rely on GitHub's built-in secret scanning and push protection.

**Pros:**
- Zero repo config
- Covers GitHub-partnered token patterns natively

**Cons:**
- Only available on public repos or GitHub Advanced Security (paid for private repos)
- Does not cover custom secret patterns (e.g., Slack bot tokens in env vars)
- No `.secrets.baseline` for false-positive management

---

### Axis 2 — Dependency pinning strategy

#### Option A — Status quo (`>=X.Y`)

Keep open-ended lower bounds.

**Pros:**
- Always gets latest features and patches automatically

**Cons:**
- No reproducibility — builds vary between machines and over time
- Supply-chain risk: a compromised release is pulled automatically
- Version conflicts are discovered at runtime, not at pin-update time

---

#### Option B — Compatible-release pins (`~=X.Y.Z`) *(recommended)*

Pin to a known-good version with the compatible-release operator. E.g.,
`openai~=1.82.0` allows `>=1.82.0, <2.0.0`.

**Pros:**
- Reproducible builds within a MAJOR version
- Still gets patches and minor features automatically
- Breakage from MAJOR version bumps is blocked until explicit update

**Cons:**
- Requires periodic manual updates (mitigated by Dependabot)

**Recommendation: Option B** — balances reproducibility with automatic patch ingestion.

---

#### Option C — Exact pins + hash verification (`==X.Y.Z --hash=sha256:…`)

Pin exact versions and require hash verification in the Dockerfile.

**Pros:**
- Fully reproducible and tamper-proof builds

**Cons:**
- Extremely high maintenance burden (every transitive dep must be listed)
- Breaks multi-platform builds (different wheels per arch have different hashes)
- Overkill for a single-container bot project

---

### Axis 3 — CI step placement

#### Option A — Separate workflow file

Create `.github/workflows/secret-scan.yml`.

**Pros:**
- Clean separation of concerns

**Cons:**
- More files to maintain
- Cannot share job dependencies with existing pipeline

---

#### Option B — New step in existing `security-scan` job *(recommended)*

Add the `detect-secrets` step to the existing `security-scan` job in `ci-cd.yml`.

**Pros:**
- Centralised security checks
- Shares checkout and permissions
- Consistent with the Trivy/CodeQL additions in `improved-security-scanning.md`

**Cons:**
- Job grows larger (acceptable — still under 15-min timeout)

**Recommendation: Option B** — add to the existing `security-scan` job.

---

## Recommended Solution

- **Axis 1**: Option B — `detect-secrets` pre-commit hook + CI gate
- **Axis 2**: Option B — compatible-release pins (`~=X.Y.Z`)
- **Axis 3**: Option B — new step in existing `security-scan` job

End-to-end flow:

```
Developer commits code
  └─ (if pre-commit installed) detect-secrets hook blocks committed secrets locally
  └─ pushes to GitHub
      └─ CI security-scan job:
           1. Trivy image scan (existing — improved by roadmap 2.1)
           2. CodeQL SAST (added by roadmap 2.1)
           3. pip-audit (added by roadmap 2.1)
           4. detect-secrets scan ← NEW (this spec)
               - runs `detect-secrets scan --baseline .secrets.baseline`
               - fails if new secrets detected outside baseline
               - uploads results to step summary
      └─ pip resolves dependencies within ~= bounds (reproducible)
```

---

## Architecture Notes

> **Read before touching code.** These are non-obvious constraints or conventions.

- **No runtime changes** — this feature is purely CI/CD + config files. No `src/` code
  is modified. The runtime `SecretRedactor` is unrelated and unchanged.
- **Baseline management** — `.secrets.baseline` must be regenerated when new false
  positives are found: `detect-secrets scan --update .secrets.baseline`. Document this
  in the PR template or `CONTRIBUTING.md`.
- **`improved-security-scanning.md` coordination** — Steps 1–3 in this spec can be
  implemented before or after roadmap 2.1. Step 4 (CI secret scan) should be added
  alongside or after the Trivy/CodeQL steps for clean job ordering.
- **Dependabot** — after tightening pins, enable Dependabot for `pip` in
  `.github/dependabot.yml` to automate version-bump PRs.
- **Multi-platform builds** — `~=X.Y.Z` pins are compatible with the existing
  `linux/amd64` + `linux/arm64` Docker builds. Exact pins with `--require-hashes`
  would break ARM builds (different wheel hashes) — deliberately avoided.

---

## Config Variables

No new env vars are introduced. All changes are in CI configuration and `requirements*.txt`.

| Env var | Type | Default | Description |
|---------|------|---------|-------------|
| *(none)* | — | — | This feature adds no runtime configuration. |

> **Note**: `detect-secrets` configuration is stored in `.secrets.baseline` (JSON),
> not in env vars.

---

## Implementation Steps

### Step 1 — `requirements.txt`: tighten production pins

Replace open-ended `>=` ranges with compatible-release `~=` pins using the currently
resolved versions as the baseline. Determine current versions:

```bash
pip install -r requirements.txt
pip freeze | grep -i "python-telegram-bot\|pydantic-settings\|gitpython\|openai\|anthropic\|aiosqlite\|pexpect\|slack-bolt\|aiohttp"
```

Then update `requirements.txt`:

```
python-telegram-bot[job-queue]~=22.0
pydantic-settings~=2.9.1
gitpython~=3.1.44
openai~=1.82.0
anthropic~=0.52.0
aiosqlite~=0.21.0
pexpect~=4.9.0
slack-bolt[async]~=1.22.0
aiohttp~=3.12.6
```

*(Exact patch versions to be determined at implementation time via `pip freeze`.)*

---

### Step 2 — `requirements-dev.txt`: tighten dev pins

Same approach for dev dependencies:

```
pytest~=8.3.5
pytest-asyncio~=0.26.0
pytest-mock~=3.14.0
pytest-cov~=6.1.1
ruff~=0.11.0
detect-secrets~=1.5.0
```

*(Adds `detect-secrets` as a new dev dependency.)*

---

### Step 3 — `.secrets.baseline`: generate initial baseline

```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline
# Review the baseline — audit each finding:
detect-secrets audit .secrets.baseline
```

Commit the clean baseline. Any finding that is a genuine false positive (e.g., a
high-entropy test fixture) should be marked as such during audit.

---

### Step 4 — `.pre-commit-config.yaml`: add detect-secrets hook

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

---

### Step 5 — `.github/workflows/ci-cd.yml`: add secret scan step

Add a new step to the `security-scan` job, after the Trivy scan and before the summary:

```yaml
      - name: 🔑 Scan for leaked secrets
        run: |
          pip install detect-secrets~=1.5.0
          detect-secrets scan --baseline .secrets.baseline
          # Returns exit-code 1 if new secrets found outside baseline
          echo "### 🔑 Secret Scan" >> $GITHUB_STEP_SUMMARY
          echo "- **Status**: ✅ No new secrets detected" >> $GITHUB_STEP_SUMMARY

      - name: 🔑 Secret scan failed
        if: failure()
        run: |
          echo "### 🔑 Secret Scan" >> $GITHUB_STEP_SUMMARY
          echo "- **Status**: ❌ New secrets detected — review and update baseline" >> $GITHUB_STEP_SUMMARY
```

---

### Step 6 — `.github/dependabot.yml`: enable pip dependency updates

Create or update `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
    open-pull-requests-limit: 5
    labels:
      - dependencies
      - security
```

---

## Files to Create / Change

| File | Action | Summary of change |
|------|--------|-------------------|
| `requirements.txt` | **Edit** | Replace `>=` with `~=X.Y.Z` compatible-release pins |
| `requirements-dev.txt` | **Edit** | Replace `>=` with `~=X.Y.Z` pins; add `detect-secrets` |
| `.secrets.baseline` | **Create** | Initial `detect-secrets` baseline (JSON) |
| `.pre-commit-config.yaml` | **Create** | `detect-secrets` pre-commit hook |
| `.github/workflows/ci-cd.yml` | **Edit** | Add secret scan step to `security-scan` job |
| `.github/dependabot.yml` | **Create** | Enable weekly pip dependency update PRs |
| `docs/features/supply-chain-hardening.md` | **Edit** | Mark status as `Implemented` after merge |
| `docs/roadmap.md` | **Edit** | Mark item as done (✅) after merge |

---

## Dependencies

| Package | Status | Notes |
|---------|--------|-------|
| `detect-secrets~=1.5.0` | ❌ Needs adding | Add to `requirements-dev.txt`. CI installs inline. |
| `pre-commit` | ℹ️ Developer tool | Not added to requirements — installed globally by developers who opt in. |

> **Rule**: `detect-secrets` is a dev/CI tool only. It must NOT be added to
> `requirements.txt` (production).

---

## Test Plan

### No new `tests/` files needed

This feature changes CI configuration and dependency pins — not runtime source code.
Validation is done via CI pipeline execution, not pytest.

### Validation matrix

| Check | What it validates |
|-------|-------------------|
| `pip install -r requirements.txt` succeeds | Pins resolve without conflicts |
| `pip install -r requirements-dev.txt` succeeds | Dev pins resolve without conflicts |
| `pytest tests/ -v --tb=short` passes | No regressions from version changes |
| `ruff check src/` passes | No lint regressions |
| `detect-secrets scan --baseline .secrets.baseline` exits 0 | Baseline is current and clean |
| CI `security-scan` job passes | Secret scan step works in CI |
| Docker build succeeds | Pinned deps install correctly on both amd64 and arm64 |

### Regression check

After tightening pins, run the full test suite to confirm no package behaviour changed:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v --tb=short
```

---

## Documentation Updates

### `README.md`

No README changes needed — this feature adds no user-facing commands, env vars, or
runtime behaviour.

### `.env.example` and `docker-compose.yml.example`

No changes — no new env vars.

### `.github/copilot-instructions.md`

Add one bullet under "Key Conventions":

```markdown
- **Dependency pinning**: use compatible-release pins (`~=X.Y.Z`) in `requirements.txt`
  and `requirements-dev.txt`. Open-ended `>=` ranges are not allowed. Run
  `detect-secrets scan --update .secrets.baseline` when adding new test fixtures with
  high-entropy strings.
```

### `docs/roadmap.md`

Add this feature as a new roadmap entry and mark done (✅) on merge to `main`.

### `docs/features/supply-chain-hardening.md`

Change `Status: **Planned**` → `Status: **Implemented**` on merge to `main`.

---

## Version Bump

| This feature… | Bump |
|---------------|------|
| Tightens dependency pins and adds CI secret scanning — no user-facing API change | **PATCH** |

**Expected bump for this feature**: `PATCH` → `0.20.1`

> Rationale: no new env vars, no new commands, no behavioural change for users.
> Dependency pin tightening is an internal hardening measure.

---

## Roadmap Update

When this feature is complete, update `docs/roadmap.md`:

```markdown
| 2.16 | ✅ Supply-chain hardening — detect-secrets CI gate + dependency pinning | [→ features/supply-chain-hardening.md](features/supply-chain-hardening.md) |
```

---

## Edge Cases and Open Questions

1. **False positives in baseline** — High-entropy test fixtures (e.g., mock tokens in
   `tests/`) may trigger `detect-secrets`. These must be audited and marked as false
   positives in `.secrets.baseline` during Step 3. Proposed answer: run
   `detect-secrets audit .secrets.baseline` interactively and mark each finding.

2. **Pin freshness** — Compatible-release pins (`~=X.Y.Z`) will drift as upstream
   releases accumulate. Dependabot (Step 6) mitigates this by opening weekly PRs.
   Proposed answer: review and merge Dependabot PRs weekly.

3. **Transitive dependency conflicts** — Tightening a direct pin (e.g.,
   `openai~=1.82.0`) could conflict with a transitive requirement from another package.
   Proposed answer: test with `pip install --dry-run` before committing; loosen the
   upper bound if a conflict is found (e.g., `openai~=1.82`).

4. **`detect-secrets` version drift in CI vs dev** — CI installs `detect-secrets`
   inline (`pip install detect-secrets~=1.5.0`) while dev machines use the version in
   `requirements-dev.txt`. Proposed answer: keep both pinned to the same `~=1.5.0`
   range; CI and dev will converge within the same minor version.

5. **Pre-commit adoption** — Pre-commit hooks are opt-in. Developers who don't run
   `pre-commit install` rely entirely on the CI gate. Proposed answer: document the
   setup in `CONTRIBUTING.md` but don't enforce it — CI is the safety net.

6. **Existing secrets in git history** — This spec prevents *new* secrets from being
   committed. It does not scan or remediate existing history. Proposed answer: out of
   scope for this spec. If a historical leak is discovered, handle via GitHub's
   secret revocation and `git filter-repo`.

---

## Acceptance Criteria

> The feature is **done** when ALL of the following are true.

- [ ] `requirements.txt` uses `~=X.Y.Z` compatible-release pins for all dependencies.
- [ ] `requirements-dev.txt` uses `~=X.Y.Z` pins and includes `detect-secrets`.
- [ ] `.secrets.baseline` exists, is audited, and contains zero unresolved findings.
- [ ] `.pre-commit-config.yaml` exists with the `detect-secrets` hook.
- [ ] CI `security-scan` job includes a `detect-secrets` scan step.
- [ ] `detect-secrets scan --baseline .secrets.baseline` exits 0 on a clean checkout.
- [ ] `pip install -r requirements.txt` resolves without conflicts.
- [ ] `pip install -r requirements-dev.txt` resolves without conflicts.
- [ ] `pytest tests/ -v --tb=short` passes with no failures or errors.
- [ ] `ruff check src/` reports no new linting issues.
- [ ] Docker build succeeds on both amd64 and arm64.
- [ ] `.github/copilot-instructions.md` updated with pinning convention.
- [ ] `.github/dependabot.yml` enables weekly pip updates.
- [ ] `docs/roadmap.md` entry added for this feature.
- [ ] PR is merged to `develop` first; CI is green; then merged to `main`.
