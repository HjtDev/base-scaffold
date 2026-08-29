# `vendor/` — temporary, flagged workaround

`appkit-1.0.0.tgz` is `appkit`'s frontend half, packed with `npm pack` from a clean
checkout of `HjtDev/appkit` at tag `v1.0.0` (commit `9bd889388960679a4a3d84ab84016c28c0883ed3`,
`sha256:7ffda0fcefc97fe6bb45d72345d8458a168098446780c283ed08f3019d260cba`). It is **not** the
documented install path — `INTEGRATION-GUIDE.md` §2 step 3 installs a git dependency directly.
It's here because that path is confirmed broken; see the appkit-integration report for the full
writeup, summarized below.

## Why this exists

Verified across four separate real installs (not just spec-parsing) in this environment
(npm 11.16.0, Node 26.2.0), against both the README's literal command and the syntactically
correct npm git-subdirectory form:

```bash
npm install "github:HjtDev/appkit#v1.0.0:frontend"          # README's literal command
npm install "github:HjtDev/appkit#v1.0.0::path:frontend"    # npm's actual ::path: syntax
```

Neither produces a working `appkit` import. The first silently drops both the tag and the
subdirectory (`npm-package-arg` parses it with `gitCommittish: undefined`,
`gitSubdir: undefined`), installing the **repo root** (`appkit-repo`, private, no entrypoints)
under the dependency name `appkit-repo`. The second parses correctly (confirmed against
`npm-package-arg`'s source directly) and pacote's own `git.js` does pass the subdirectory
through to its `DirFetcher` packing step — but the package that actually lands in
`node_modules/appkit` is still the **full monorepo tree** (`backend/`, `docs/`, `playground/`,
`tests/`, `.github/`, …), with the top-level `package.json` being the private workspace-root
manifest (`name: "appkit-repo"`), not `frontend/package.json`. `require.resolve("appkit")` /
`import("appkit")` fail outright — `ERR_PACKAGE_PATH_NOT_EXPORTED`, no `main`/`exports` on that
manifest.

Compounding this: `appkit/frontend/dist` is not committed to the appkit repo (confirmed via
`git ls-files frontend/dist` → 0 files), so a correct git install still depends on the
`prepare` script (`tsc -p tsconfig.build.json`) running post-clone. This environment's npm 11
has a native script-approval gate (`allow-scripts`, configured default-deny in this sandbox's
`/etc/npmrc`) that blocks that script; `npm approve-scripts --allow-scripts-pending` reported
success but did not persist across a fresh install of the same dependency, and no combination
tried (`--foreground-scripts`, re-approving, reinstalling) produced a working result. Whether
the _monorepo-tree_ bug reproduces on an unrestricted machine (no script-gating) is untested —
that half may be sandbox-specific. The _missing-`dist/`-plus-script-gating_ half is real,
current npm 11 behavior that any security-hardened environment (a locked-down CI runner, a
supply-chain-conscious team's dev machines) can hit.

## Removing this workaround

Once appkit ships a fix (committing `dist/`, or publishing to a real registry, or confirming
the git-subdirectory install works cleanly on an unrestricted machine and documenting the
correct command) — re-pin via the documented `INTEGRATION-GUIDE.md` §2 protocol, delete this
directory, and change `frontend/package.json`'s `appkit` entry back to a `github:` spec.
