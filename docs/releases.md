# Releasing

Releases use immutable semantic-version tags such as `v1.0.0` and a moving
major-version tag such as `v1`. Workflows should generally use the major tag:

```yaml
- uses: bytecodealliance/setup-wasi-sdk-action@v1
```

Security-sensitive consumers can pin the immutable version tag or its commit.

## Creating a release

1. Confirm all required checks pass on `main`.
2. Open the **Release** workflow in GitHub Actions and select **Run workflow**.
3. Enter the next version in `vMAJOR.MINOR.PATCH` form, such as `v1.0.0`.
4. Review the generated GitHub release notes.

The workflow always releases the current `main`, reruns the doctests, refuses
to replace an existing semantic-version tag, creates the immutable version tag,
and moves the corresponding major tag to the same commit. Tag pushes are
atomic, so neither tag is updated if GitHub rejects either update.

If tag creation succeeds but GitHub release creation fails, do not rerun the
workflow because the immutable tag now exists. Instead, create the GitHub
release for that existing tag manually with generated release notes.

## GitHub Marketplace

For the first public release, a repository owner must edit the GitHub release,
select **Publish this Action to the GitHub Marketplace**, accept the Marketplace
Developer Agreement if prompted, and choose appropriate categories. This is a
one-time approval in GitHub's release interface and is not exposed by the
Releases API used by the workflow.

Later releases using the same major tag remain available to existing `@v1`
consumers automatically.
