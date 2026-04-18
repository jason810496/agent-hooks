# Release Process

This directory keeps the release mechanics close to the code that uses them:

- `python -m scripts.release.manage_version show` prints the current package version.
- `python -m scripts.release.manage_version set --version <version>` updates `pyproject.toml`.
- `python -m scripts.release.manage_version validate ...` enforces the version, tag, and release-channel rules used by CI.

The project uses a static version in `pyproject.toml`, so every release starts by updating that file intentionally.
The docs site follows the same version model, with a moving `latest` version from `main` and immutable published versions from release tags.

## Supported Version Formats

- Stable release: `X.Y.Z`
- Release candidate: `X.Y.ZrcN`

The workflows also require the Git tag to be `v<version>`.

Examples:

- `0.2.0` -> tag `v0.2.0`
- `0.2.0rc1` -> tag `v0.2.0rc1`

## Required GitHub Configuration

The workflows use [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/). No API token is required if the publishers are configured correctly.
All third-party GitHub Actions in the release workflows are pinned to full commit SHAs, and the trailing comments record the human-readable release version that each SHA came from. GitHub releases themselves are created with the built-in `gh release create` CLI so immutable releases follow GitHub's draft-upload-publish sequence when assets are attached.

Create these GitHub environments:

- `testpypi` for release candidates
- `pypi` for stable releases

Register these trusted publishers:

1. TestPyPI
   Workflow: `.github/workflows/release-candidate.yml`
   Environment: `testpypi`
   Repository: this repository
2. PyPI
   Workflow: `.github/workflows/release-pypi.yml`
   Environment: `pypi`
   Repository: this repository

GitHub Pages stays on the `GitHub Actions` source. The docs workflow keeps a `gh-pages` branch as mike's backing store, then deploys that branch content through Pages so older doc versions remain available in the version selector.

## Docs Versioning Model

The docs site is versioned with [mike](https://github.com/jimporter/mike), and Material for MkDocs renders the version selector in the header.

- Pushes to `main` publish the current docs as `latest`, titled `latest (<pyproject version>)`.
- Release candidate tags like `v0.2.0rc1` publish a docs version `0.2.0rc1` and move the `rc` alias to it.
- Stable tags like `v0.2.0` publish a docs version `0.2.0` without replacing the moving `latest` docs.

That means users can switch between `latest`, stable releases, and any published release candidates directly in the docs header.

## Local Docs Commands

Use these commands when you need to inspect or rehearse the docs release state locally:

```bash
uv run --group docs mkdocs build --strict
uv run --group docs mike list
uv run --group docs mike serve
```

To stage a local docs deployment for the current branch without pushing anything:

```bash
uv run --group docs mike deploy --update-aliases --title "latest ($(uv run python -m scripts.release.manage_version show))" latest
```

To stage a tagged stable or release-candidate docs version locally:

```bash
uv run --group docs mike deploy --update-aliases --title 0.2.0 0.2.0
uv run --group docs mike deploy --update-aliases --title 0.2.0rc1 0.2.0rc1 rc
```

After a local `mike deploy`, run `uv run --group docs mike serve` if you want to browse the full multi-version site before pushing anything.

## Release Candidate Flow

1. Pick the next candidate version, for example `0.2.0rc1`.
2. Update `pyproject.toml`:

   ```bash
   uv run python -m scripts.release.manage_version set --version 0.2.0rc1
   ```

3. Run local verification:

   ```bash
   uvx ruff check .
   uv run --group dev pytest
   uv build
   uvx twine check dist/*
   ```

4. Commit the version bump.
5. Create and push the candidate tag:

   ```bash
   git tag -a v0.2.0rc1 -m "Release candidate 0.2.0rc1"
   git push origin main --follow-tags
   ```

6. GitHub Actions publishes the distributions to TestPyPI and creates a GitHub prerelease with the built artifacts and publish attestations attached.
   The docs workflow also publishes versioned docs for `0.2.0rc1` and moves the `rc` docs alias.

Use the TestPyPI install flow to validate the candidate in a clean environment before promoting it.

## Stable Release Flow

1. Pick the final version, for example `0.2.0`.
2. Update `pyproject.toml`:

   ```bash
   uv run python -m scripts.release.manage_version set --version 0.2.0
   ```

3. Run the same local verification steps:

   ```bash
   uvx ruff check .
   uv run --group dev pytest
   uv build
   uvx twine check dist/*
   ```

4. Commit the version bump.
5. Create and push the release tag:

   ```bash
   git tag -a v0.2.0 -m "Release 0.2.0"
   git push origin main --follow-tags
   ```

6. GitHub Actions publishes the package to PyPI and creates the GitHub release with release notes, distribution artifacts, and publish attestations attached.
   The docs workflow also publishes immutable versioned docs for `0.2.0` while keeping `latest` reserved for the moving docs built from `main`.

## CI Validation Rules

The workflows fail fast when any of these are true:

- the tag does not start with `v`
- the tag and the package version differ
- a release candidate workflow receives a stable version
- a stable workflow receives a release-candidate version

That validation comes from `python -m scripts.release.manage_version validate`, so the same rules are available locally before you push a tag.
