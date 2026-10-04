#!/usr/bin/env python3
"""Release a validated upstream candidate, then fast-forward main with a lease."""

import json
import os
import re
import subprocess
import time

from upstream import ROOT, next_native_tag, next_package_tag, run


def dispatch(workflow, tag):
    # Dispatch on the immutable tag; match event, ref, and source SHA, so another
    # maintainer's manual workflow cannot be mistaken for this release's tests.
    def runs():
        return json.loads(run("gh", "run", "list", "--workflow", workflow,
                              "--branch", tag, "--event", "workflow_dispatch", "--limit", "100",
                              "--json", "databaseId,headSha"))

    previous = {item["databaseId"] for item in runs()}
    expected = run("git", "rev-parse", f"{tag}^{{commit}}")
    run("gh", "workflow", "run", workflow, "--ref", tag, "-f", f"tag={tag}")
    for _ in range(60):
        candidates = [item for item in runs()
                      if item["databaseId"] not in previous and item["headSha"] == expected]
        if len(candidates) > 1:
            raise RuntimeError(f"Multiple {workflow} runs for {tag}; refusing to guess")
        if candidates:
            run_id = str(candidates[0]["databaseId"])
            print(f"Watching {workflow} run {run_id} for {tag}", flush=True)
            try:
                subprocess.run(["gh", "run", "watch", run_id, "--exit-status", "--interval", "30"],
                               cwd=ROOT, check=True)
            except subprocess.CalledProcessError:
                subprocess.run(["gh", "run", "view", run_id, "--log-failed"], cwd=ROOT, check=False)
                raise
            return
        time.sleep(5)
    raise RuntimeError(f"No {workflow} run appeared for {tag}")


def publish_tag(tag):
    run("git", "tag", "-a", tag, "-m", tag)
    run("git", "push", "origin", f"refs/tags/{tag}")


def main():
    # GITHUB_TOKEN tag pushes do not trigger push workflows. Explicit dispatch
    # makes the same build/release validation run without a personal access token.
    if os.environ.get("GITHUB_REPOSITORY") != "AkinoKaede/libtailscale-spm":
        raise RuntimeError("Automatic publishing is restricted to AkinoKaede/libtailscale-spm")
    previous = os.environ["PREVIOUS_MAIN"]
    if not re.fullmatch(r"[0-9a-f]{40}", previous):
        raise ValueError("PREVIOUS_MAIN must be a full commit SHA")
    if run("git", "status", "--porcelain"):
        raise RuntimeError("Commit the validated candidate before publishing")
    run("git", "merge-base", "--is-ancestor", previous, "HEAD")
    run("git", "fetch", "origin", "main", "--tags")
    if run("git", "rev-parse", "origin/main") != previous:
        raise RuntimeError("main moved during validation; retry from the new main")
    tags = run("git", "tag", "--list").splitlines()
    native = next_native_tag((ROOT / "Tailscale.version").read_text().strip(), tags)
    package = next_package_tag(tags)
    publish_tag(native)
    dispatch("test.yml", native)
    dispatch("build.yml", native)

    archive_dir = ROOT / ".build/upstream-release" / native
    archive_dir.mkdir(parents=True, exist_ok=True)
    run("gh", "release", "download", native, "--pattern", "CTailscale.xcframework.zip",
        "--dir", str(archive_dir))
    url = f"https://github.com/AkinoKaede/libtailscale-spm/releases/download/{native}/CTailscale.xcframework.zip"
    run("bash", "Scripts/build-manifest.sh", str(archive_dir / "CTailscale.xcframework.zip"), url)
    run("bash", "Scripts/verify-release.sh")
    # Verify the actual published binary before creating the immutable package tag.
    run("bash", "Scripts/test-package.sh")
    run("git", "add", "Package.swift")
    run("git", "commit", "-m", f"chore(release): publish TailscaleKit {package}")
    publish_tag(package)
    dispatch("release.yml", package)
    run("git", "push", f"--force-with-lease=refs/heads/main:{previous}", "origin", "HEAD:refs/heads/main")
    summary = f"Published TailscaleKit {package} using {native}; promoted verified source to main.\n"
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a") as stream:
            stream.write(summary)


if __name__ == "__main__":
    main()
