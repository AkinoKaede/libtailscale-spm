#!/usr/bin/env python3
"""Discover upstream pins and regenerate only the owned Go dependency patch."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
LIBTAILSCALE_URL = "https://github.com/tailscale/libtailscale.git"
DEPENDENCY_PATCH = "0001-official-tailscale-version.patch"


def run(*args, cwd=ROOT, env=None):
    # Keep complete stderr in CI, including patch conflicts and Go diagnostics.
    try:
        # Preserve whitespace on diff context lines (a blank line is " \n").
        return subprocess.check_output(args, cwd=cwd, env=env, text=True).rstrip("\n")
    except subprocess.CalledProcessError as error:
        print(error.output, flush=True)
        raise


def version(value, prefix=""):
    match = re.fullmatch(re.escape(prefix) + r"(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise ValueError(f"Invalid version: {value}")
    return tuple(map(int, match.groups()))


def stable_release(release):
    tag = release["tag_name"]
    numbers = version(tag, "v")
    if release["draft"] or release["prerelease"] or numbers[1] % 2:
        raise ValueError(f"Expected an official stable Tailscale release, got {tag}")
    return tag


def next_native_tag(tailscale, tags):
    version(tailscale, "v")
    prefix = f"tailscale.{tailscale[1:]}-"
    builds = [int(tag[len(prefix):]) for tag in tags if re.fullmatch(re.escape(prefix) + r"\d+", tag)]
    return f"{prefix}{max(builds, default=0) + 1}"


def next_package_tag(tags):
    versions = [version(tag) for tag in tags if re.fullmatch(r"\d+\.\d+\.\d+", tag)]
    if not versions:
        raise ValueError("An initial package release is required before automatic updates")
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch + 1}"


def go_version(module, minimum):
    versions = [minimum]
    for line in module.splitlines():
        match = re.fullmatch(r"(?:go |toolchain go)(\d+\.\d+(?:\.\d+)?)", line)
        if match:
            value = match[1]
            versions.append(value if value.count(".") == 2 else value + ".0")
    return max(versions, key=version)


def prepare(root, revision, tailscale, refresh=False, upstream_url=LIBTAILSCALE_URL):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("libtailscale revision must be a full commit SHA")
    selected = version(tailscale, "v")
    current = (root / "Tailscale.version").read_text().strip()
    if selected[1] % 2 or selected < version(current, "v"):
        raise ValueError("Tailscale updates must be stable and must not downgrade the current pin")
    old_revision = (root / "libtailscale.ref").read_text().strip()
    if not refresh and (revision, tailscale) == (old_revision, current):
        return False

    toolchain = (root / ".go-version").read_text().strip()
    version(toolchain)
    env = dict(os.environ, GOTOOLCHAIN=f"go{toolchain}+auto", GOWORK="off")
    patches = root / "Patches/libtailscale"
    # Generate everything in a disposable checkout. Failed rebases/resolution must
    # leave the wrapper pins and all checked-in patches untouched.
    with tempfile.TemporaryDirectory(prefix="libtailscale-upstream-") as directory:
        source = Path(directory)
        run("git", "init", "--quiet", cwd=source)
        for ref in dict.fromkeys([old_revision, revision]):
            run("git", "fetch", "--quiet", "--depth=1", upstream_url, ref, cwd=source)
        run("git", "checkout", "--quiet", "--detach", revision, cwd=source)
        rebased = {}
        for patch in sorted(patches.glob("*.patch")):
            if patch.name == DEPENDENCY_PATCH:
                continue
            # --3way can preserve upstream context changes, but never resolves
            # conflicting source edits on its own. Re-emit against the new base.
            run("git", "apply", "--3way", "--index", str(patch), cwd=source)
            contents = run("git", "diff", "--cached", "--binary", "--full-index", cwd=source)
            if not contents:
                raise ValueError(f"Patch {patch.name} is already upstream; review and remove it")
            rebased[patch] = contents + "\n"
            run("git", "-c", "commit.gpgsign=false", "-c", "user.name=upstream-sync", "-c", "user.email=sync@localhost",
                "commit", "--quiet", "--allow-empty", "-m", patch.name, cwd=source)

        for entry in (root / "Bridge").iterdir():
            if entry.is_file():
                if (source / entry.name).exists():
                    raise ValueError(f"Bridge overlay would overwrite upstream file: {entry.name}")
                shutil.copy2(entry, source / entry.name)

        required = go_version((source / "go.mod").read_text(), toolchain)
        run("go", "mod", "edit", f"-go={required}", cwd=source, env=env)
        run("go", "get", f"tailscale.com@{tailscale}", cwd=source, env=env)
        run("go", "mod", "tidy", cwd=source, env=env)
        actual = json.loads(run("go", "list", "-m", "-json", "tailscale.com", cwd=source, env=env))
        if actual["Version"] != tailscale or actual.get("Replace"):
            raise ValueError("Resolved Tailscale module does not match the official release")
        toolchain = go_version((source / "go.mod").read_text(), required)
        dependency = run("git", "diff", "--binary", "--full-index", "--", "go.mod", "go.sum", cwd=source)
        if not dependency:
            raise ValueError("Empty dependency patch: upstream dependency layout needs review")

    for patch, contents in rebased.items():
        patch.write_text(contents)
    (patches / DEPENDENCY_PATCH).write_text(dependency + "\n")
    (root / "libtailscale.ref").write_text(revision + "\n")
    (root / "Tailscale.version").write_text(tailscale + "\n")
    (root / ".go-version").write_text(toolchain + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libtailscale-ref", help="Override upstream default-branch HEAD")
    parser.add_argument("--tailscale-version", help="Override the latest official stable release")
    parser.add_argument("--refresh", action="store_true", help="Regenerate even when pins are unchanged")
    args = parser.parse_args()
    revision = args.libtailscale_ref or run("gh", "api", "repos/tailscale/libtailscale/commits/HEAD", "--jq", ".sha")
    tailscale = args.tailscale_version or stable_release(json.loads(
        run("gh", "api", "repos/tailscale/tailscale/releases/latest")))
    changed = prepare(ROOT, revision, tailscale, args.refresh)
    print(f"{'Prepared' if changed else 'Already pinned to'} libtailscale {revision}, Tailscale {tailscale}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            stream.write(f"changed={str(changed).lower()}\n")


if __name__ == "__main__":
    main()
