#!/usr/bin/env python3
"""Offline regression tests for pin updates, patch rebases, and release gates."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import upstream

spec = importlib.util.spec_from_file_location("release_upstream", Path(__file__).with_name("release-upstream.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class VersionTests(unittest.TestCase):
    def test_rejects_preview_and_unstable_releases(self):
        for tag, draft, preview in [("v1.104.0-rc1", False, True), ("v1.103.1", False, False),
                                    ("v1.104.0", True, False), ("v1.104.0", False, True)]:
            with self.subTest(tag=tag, draft=draft, preview=preview), self.assertRaises(ValueError):
                upstream.stable_release({"tag_name": tag, "draft": draft, "prerelease": preview})

    def test_accepts_next_stable_minor(self):
        self.assertEqual(upstream.stable_release({"tag_name": "v1.104.0", "draft": False,
                                                 "prerelease": False}), "v1.104.0")

    def test_allocates_native_builds_without_reusing_failed_tags(self):
        self.assertEqual(upstream.next_native_tag("v1.102.5", ["tailscale.1.102.5-9", "tailscale.1.102.5-10",
                                                              "tailscale.1.102.6-20", "1.0.2"]),
                         "tailscale.1.102.5-11")
        self.assertEqual(upstream.next_native_tag("v1.104.0", []), "tailscale.1.104.0-1")

    def test_package_versions_sort_numerically_and_ignore_native_tags(self):
        self.assertEqual(upstream.next_package_tag(["1.0.9", "1.0.10", "2.0.0-rc1", "tailscale.1.102.5-1"]),
                         "1.0.11")
        with self.assertRaises(ValueError):
            upstream.next_package_tag([])

    def test_go_toolchain_never_downgrades_and_honors_upstream(self):
        self.assertEqual(upstream.go_version("go 1.28\ntoolchain go1.28.2\n", "1.27.1"), "1.28.2")
        self.assertEqual(upstream.go_version("go 1.25.5\n", "1.27.1"), "1.27.1")


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "wrapper"
        self.source = Path(self.temp.name) / "upstream"
        self.root.mkdir()
        self.source.mkdir()
        self.patches = self.root / "Patches/libtailscale"
        self.patches.mkdir(parents=True)
        (self.root / "Bridge").mkdir()
        (self.root / "Bridge/bridge.go").write_text("package main\n")
        upstream.run("git", "init", "--quiet", cwd=self.source)
        upstream.run("git", "config", "user.name", "test", cwd=self.source)
        upstream.run("git", "config", "user.email", "test@localhost", cwd=self.source)
        upstream.run("git", "config", "commit.gpgsign", "false", cwd=self.source)
        (self.source / "go.mod").write_text("module example.org/test\n\ngo 1.25.5\n\nrequire tailscale.com v1.94.1\n")
        (self.source / "go.sum").write_text("old dependency\n")
        (self.source / "compat.go").write_text("before\n\n")
        self.old = self.commit()
        (self.source / "compat.go").write_text("after\n\n")
        self.compat = self.patches / "0002-compat.patch"
        self.compat.write_text(upstream.run("git", "diff", "--full-index", cwd=self.source) + "\n")
        upstream.run("git", "checkout", "--", "compat.go", cwd=self.source)
        self.dependency = self.patches / upstream.DEPENDENCY_PATCH
        self.dependency.write_text("old generated dependency patch\n")
        (self.root / "libtailscale.ref").write_text(self.old + "\n")
        (self.root / "Tailscale.version").write_text("v1.102.5\n")
        (self.root / ".go-version").write_text("1.27.1\n")
        (self.source / "new-upstream-file").write_text("keep this\n")
        self.new = self.commit()
        self.commands = []

    def commit(self):
        upstream.run("git", "add", ".", cwd=self.source)
        upstream.run("git", "commit", "--quiet", "-m", "fixture", cwd=self.source)
        return upstream.run("git", "rev-parse", "HEAD", cwd=self.source)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def prepare(self, revision=None, tailscale="v1.104.0"):
        return upstream.prepare(self.root, revision or self.new, tailscale, upstream_url=str(self.source))

    def fake_go(self, *args, **kwargs):
        self.commands.append(args)
        if args[0] != "go":
            return self.real_run(*args, **kwargs)
        source = kwargs["cwd"]
        self.assertEqual((source / "compat.go").read_text(), "after\n\n")
        self.assertTrue((source / "bridge.go").exists())
        self.assertEqual(kwargs["env"]["GOTOOLCHAIN"], "go1.27.1+auto")
        if args[1:3] == ("get", "tailscale.com@v1.104.0"):
            (source / "go.mod").write_text("module example.org/test\n\ngo 1.28.1\n\nrequire tailscale.com v1.104.0\n")
            (source / "go.sum").write_text("new dependency\n")
        if args[1:3] == ("list", "-m"):
            return json.dumps({"Version": "v1.104.0"})
        return ""

    def test_no_change_does_not_run_git_or_go(self):
        before = self.snapshot()
        with patch.object(upstream, "run", side_effect=AssertionError("unexpected command")):
            self.assertFalse(self.prepare(self.old, "v1.102.5"))
        self.assertEqual(self.snapshot(), before)

    def test_either_pin_can_trigger_regeneration(self):
        self.real_run = upstream.run
        with patch.object(upstream, "run", side_effect=self.fake_go):
            self.assertTrue(self.prepare(self.old))
        self.assertEqual((self.root / "libtailscale.ref").read_text().strip(), self.old)
        self.assertEqual((self.root / "Tailscale.version").read_text().strip(), "v1.104.0")

    def test_libtailscale_only_update_regenerates_dependency_patch(self):
        self.real_run = upstream.run
        (self.root / "Tailscale.version").write_text("v1.104.0\n")
        with patch.object(upstream, "run", side_effect=self.fake_go):
            self.assertTrue(self.prepare())
        self.assertEqual((self.root / "libtailscale.ref").read_text().strip(), self.new)

    def test_regenerated_patches_apply_to_new_upstream_without_copying_bridge(self):
        self.real_run = upstream.run
        with patch.object(upstream, "run", side_effect=self.fake_go):
            self.assertTrue(self.prepare())
        self.assertEqual((self.root / ".go-version").read_text().strip(), "1.28.1")
        for item in sorted(self.patches.glob("*.patch")):
            upstream.run("git", "apply", str(item), cwd=self.source)
        self.assertIn("tailscale.com v1.104.0", (self.source / "go.mod").read_text())
        self.assertEqual((self.source / "compat.go").read_text(), "after\n\n")
        self.assertEqual((self.source / "new-upstream-file").read_text(), "keep this\n")
        self.assertNotIn("bridge.go", self.dependency.read_text())

    def test_patch_conflict_does_not_change_pins_or_patches(self):
        (self.source / "compat.go").write_text("conflicting upstream change\n")
        conflicting = self.commit()
        before = self.snapshot()
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepare(conflicting)
        self.assertEqual(self.snapshot(), before)

    def test_module_failure_does_not_change_pins_or_patches(self):
        self.real_run = upstream.run
        before = self.snapshot()

        def fail(*args, **kwargs):
            if args[0] == "go":
                raise subprocess.CalledProcessError(1, args)
            return self.real_run(*args, **kwargs)

        with patch.object(upstream, "run", side_effect=fail), self.assertRaises(subprocess.CalledProcessError):
            self.prepare()
        self.assertEqual(self.snapshot(), before)

    def test_absorbed_patch_requires_review_without_writing_an_empty_patch(self):
        (self.source / "compat.go").write_text("after\n\n")
        absorbed = self.commit()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "already upstream"):
            self.prepare(absorbed)
        self.assertEqual(self.snapshot(), before)

    def test_rejects_downgrades_and_unstable_versions_before_mutating(self):
        before = self.snapshot()
        for value in ["v1.100.9", "v1.103.0", "v1.104.0-rc1"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.prepare(tailscale=value)
        self.assertEqual(self.snapshot(), before)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "Tailscale.version").write_text("v1.104.0\n")
        self.previous = "a" * 40
        self.commands = []
        self.addCleanup(patch.stopall)
        patch.object(release, "ROOT", self.root).start()
        patch.dict(os.environ, {"GITHUB_REPOSITORY": "AkinoKaede/libtailscale-spm",
                                "PREVIOUS_MAIN": self.previous, "GITHUB_STEP_SUMMARY": ""}).start()
        patch.object(release, "run", side_effect=self.fake_run).start()
        self.dispatch = patch.object(release, "dispatch", side_effect=self.dispatched).start()

    def fake_run(self, *args):
        self.commands.append(args)
        if args == ("git", "rev-parse", "origin/main"):
            return self.previous
        if args == ("git", "tag", "--list"):
            return "1.0.9\n1.0.10\ntailscale.1.104.0-1"
        return ""

    def dispatched(self, workflow, tag):
        self.commands.append(("dispatch", workflow, tag))

    def test_main_moves_only_after_both_workflows_and_published_consumer_pass(self):
        release.main()
        go_matrix = self.commands.index(("dispatch", "test.yml", "tailscale.1.104.0-2"))
        native = self.commands.index(("dispatch", "build.yml", "tailscale.1.104.0-2"))
        consumer = self.commands.index(("bash", "Scripts/test-package.sh"))
        package_tag = self.commands.index(("git", "tag", "-a", "1.0.11", "-m", "1.0.11"))
        package = self.commands.index(("dispatch", "release.yml", "1.0.11"))
        self.assertLess(go_matrix, native)
        self.assertLess(native, consumer)
        self.assertLess(consumer, package_tag)
        self.assertLess(package_tag, package)
        self.assertEqual(self.commands[-1], ("git", "push", f"--force-with-lease=refs/heads/main:{self.previous}",
                                             "origin", "HEAD:refs/heads/main"))

    def test_failed_native_build_never_tags_package_or_promotes_main(self):
        self.dispatch.side_effect = [None, RuntimeError("native build failed")]
        with self.assertRaises(RuntimeError):
            release.main()
        self.assertFalse(any("1.0.11" in command or "HEAD:refs/heads/main" in command for command in self.commands))

    def test_failed_package_release_never_promotes_main(self):
        self.dispatch.side_effect = [None, None, RuntimeError("package failed")]
        with self.assertRaises(RuntimeError):
            release.main()
        self.assertFalse(any("HEAD:refs/heads/main" in command for command in self.commands))

    def test_failed_published_consumer_never_tags_package(self):
        def fail_consumer(*args):
            if args == ("bash", "Scripts/test-package.sh"):
                raise subprocess.CalledProcessError(1, args)
            return self.fake_run(*args)

        with patch.object(release, "run", side_effect=fail_consumer), self.assertRaises(subprocess.CalledProcessError):
            release.main()
        self.assertFalse(any("1.0.11" in command or "HEAD:refs/heads/main" in command for command in self.commands))

    def test_main_race_aborts_before_publishing_tags(self):
        real_run = self.fake_run
        with patch.object(release, "run", side_effect=lambda *args:
                          "b" * 40 if args == ("git", "rev-parse", "origin/main") else real_run(*args)):
            with self.assertRaises(RuntimeError):
                release.main()
        self.assertFalse(any(command[:2] == ("git", "push") for command in self.commands))


class DispatchTests(unittest.TestCase):
    def test_ignores_prior_runs_and_wrong_commits(self):
        calls = []
        snapshots = iter([
            [{"databaseId": 1, "headSha": "a" * 40}],
            [{"databaseId": 1, "headSha": "a" * 40}, {"databaseId": 2, "headSha": "b" * 40}],
            [{"databaseId": 3, "headSha": "a" * 40}],
        ])

        def fake_run(*args):
            calls.append(args)
            if args[:3] == ("gh", "run", "list"):
                self.assertIn("workflow_dispatch", args)
                self.assertIn("tailscale.1.104.0-1", args)
                return json.dumps(next(snapshots))
            if args[:2] == ("git", "rev-parse"):
                return "a" * 40
            return ""

        with patch.object(release, "run", side_effect=fake_run), patch.object(release.time, "sleep"), \
                patch.object(release.subprocess, "run") as watch:
            release.dispatch("build.yml", "tailscale.1.104.0-1")
        self.assertIn(("gh", "workflow", "run", "build.yml", "--ref", "tailscale.1.104.0-1",
                       "-f", "tag=tailscale.1.104.0-1"), calls)
        self.assertEqual(watch.call_args.args[0], ["gh", "run", "watch", "3", "--exit-status", "--interval", "30"])
        self.assertTrue(watch.call_args.kwargs["check"])

    def test_dispatch_timeout_stops_release(self):
        def fake_run(*args):
            return "[]" if args[:3] == ("gh", "run", "list") else "a" * 40

        with patch.object(release, "run", side_effect=fake_run), patch.object(release.time, "sleep"), \
                self.assertRaises(RuntimeError):
            release.dispatch("build.yml", "tailscale.1.104.0-1")


if __name__ == "__main__":
    unittest.main()
