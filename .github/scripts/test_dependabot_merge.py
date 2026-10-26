import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dependabot_merge import eligible_commits, main, required_workflows, workflows_passed


class MetadataGateTests(unittest.TestCase):
    def setUp(self):
        self.commit = {
            "author": {"login": "dependabot[bot]"},
            "commit": {
                "verification": {"verified": True},
                "message": ("Update dependencies\n\n---\nupdated-dependencies:\n"
                            "- dependency-name: example\n"
                            "  update-type: version-update:semver-minor\n"
                            "...\n\nSigned-off-by: dependabot[bot]"),
            },
        }

    def test_minor_and_patch(self):
        self.assertTrue(eligible_commits([self.commit]))
        self.commit["commit"]["message"] = self.commit["commit"]["message"].replace(
            "semver-minor", "semver-patch")
        self.assertTrue(eligible_commits([self.commit]))

    def test_major_in_group(self):
        self.commit["commit"]["message"] = self.commit["commit"]["message"].replace(
            "...\n", "- dependency-name: second\n"
            "  update-type: version-update:semver-major\n...\n")
        self.assertFalse(eligible_commits([self.commit]))

    def test_missing_metadata(self):
        self.commit["commit"]["message"] = "Update dependencies"
        self.assertFalse(eligible_commits([self.commit]))

    def test_missing_type_in_group(self):
        self.commit["commit"]["message"] = self.commit["commit"]["message"].replace(
            "...\n", "- dependency-name: second\n...\n")
        self.assertFalse(eligible_commits([self.commit]))

    def test_unverified_commit(self):
        self.commit["commit"]["verification"]["verified"] = False
        self.assertFalse(eligible_commits([self.commit]))

    def test_non_bot_commit(self):
        second = copy.deepcopy(self.commit)
        second["author"]["login"] = "someone-else"
        self.assertFalse(eligible_commits([self.commit, second]))

    def test_unknown_update_type(self):
        self.commit["commit"]["message"] = self.commit["commit"]["message"].replace(
            "version-update:semver-minor", "unknown")
        self.assertFalse(eligible_commits([self.commit]))


    def test_signed_requirement_bump_without_update_type(self):
        self.commit["commit"]["message"] = (
            "chore: update example requirement from >=7.6.0 to >=7.7.0\n\n"
            "---\nupdated-dependencies:\n- dependency-name: example\n"
            "  dependency-type: direct:production\n...\n")
        self.assertTrue(eligible_commits([self.commit]))
        original = self.commit["commit"]["message"]
        for old, new in [("7.7.0", "8.0.0"), ("7.7.0", "7.5.0"),
                         ("7.7.0", "7.7.0rc1"), ("update example", "update other"),
                         (">=7.7.0", "<8"),
                         ("...\n", "  update-type: unknown\n...\n")]:
            self.commit["commit"]["message"] = original.replace(old, new)
            self.assertFalse(eligible_commits([self.commit]), new)
        self.commit["commit"]["message"] = original
        self.commit["commit"]["verification"]["verified"] = False
        self.assertFalse(eligible_commits([self.commit]))

    def test_empty_commits(self):
        self.assertFalse(eligible_commits([]))


class WorkflowGateTests(unittest.TestCase):
    def test_affected_scopes(self):
        for path, expected in [
            ("Cargo.lock", {"rust-ci.yml"}),
            ("crates/proto/Cargo.toml", {"rust-ci.yml"}),
            ("webui/pnpm-lock.yaml", {"webui-ci.yml"}),
            ("docs/package-lock.json", {"docs-ci.yml"}),
            (".github/workflows/release.yml",
             {"rust-ci.yml", "webui-ci.yml", "docs-ci.yml"}),
            ("packaging/docker/Dockerfile.runtime", set()),
        ]:
            self.assertEqual(required_workflows([{"filename": path}]), expected)
        self.assertEqual(required_workflows([]), set())

    def test_wait_for_every_workflow_and_latest_attempt(self):
        run = {
            "id": 1, "path": ".github/workflows/rust-ci.yml",
            "event": "pull_request", "status": "completed", "conclusion": "success",
        }
        self.assertTrue(workflows_passed([run], {"rust-ci.yml"}))
        self.assertFalse(workflows_passed([run], {"rust-ci.yml", "webui-ci.yml"}))
        self.assertFalse(workflows_passed([run], set()))
        for override in [{"status": "in_progress"}, {"conclusion": "failure"},
                         {"event": "schedule"}]:
            self.assertFalse(workflows_passed([{**run, **override}], {"rust-ci.yml"}))
        self.assertFalse(workflows_passed(
            [run, {**run, "id": 2, "conclusion": "failure"}], {"rust-ci.yml"}))


class MergeGateTests(unittest.TestCase):
    def setUp(self):
        MetadataGateTests.setUp(self)
        self.repo = "owner/repo"
        self.pr = {
            "number": 1, "state": "open", "draft": False,
            "user": {"login": "dependabot[bot]"},
            "head": {"repo": {"full_name": self.repo}, "sha": "tested"},
            "base": {"ref": "main"},
        }
        self.event = {
            "repository": {"default_branch": "main"},
            "workflow_run": {
                "conclusion": "success", "event": "pull_request",
                "head_repository": {"full_name": self.repo}, "head_sha": "tested",
            },
        }
        self.checks = {
            "total_count": 1,
            "check_runs": [{"status": "completed", "conclusion": "success"}],
        }

    def run_gate(self):
        def fake_api(endpoint):
            if endpoint.endswith("/pulls?per_page=100"):
                return [self.pr]
            if "/pulls/1/files" in endpoint:
                return [{"filename": "Cargo.lock"}]
            if "/actions/runs?" in endpoint:
                return {"total_count": 1, "workflow_runs": [{
                    "id": 1, "path": ".github/workflows/rust-ci.yml",
                    "event": "pull_request", "status": "completed",
                    "conclusion": "success"}]}
            if "/pulls/1/commits" in endpoint:
                return [self.commit]
            if endpoint.endswith("/pulls/1"):
                return self.pr
            if "/check-runs?" in endpoint:
                return self.checks
            if endpoint.endswith("/status"):
                return {"total_count": 0, "state": "pending"}
            raise AssertionError(endpoint)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(self.event))
            with patch.dict(os.environ, {
                "GITHUB_EVENT_PATH": str(path), "GITHUB_REPOSITORY": self.repo,
                "POST_MERGE_WORKFLOW": "build.yml",
            }), patch("dependabot_merge.api", side_effect=fake_api), \
                    patch("dependabot_merge.subprocess.run") as command:
                main()
                return [call.args[0] for call in command.call_args_list]

    def test_validated_head_merges_and_dispatches(self):
        commands = self.run_gate()
        self.assertEqual(len(commands), 2)
        self.assertIn("--match-head-commit", commands[0])
        self.assertIn("tested", commands[0])
        self.assertEqual(commands[1][1:4], ["workflow", "run", "rust-ci.yml"])

    def test_stale_head_never_merges(self):
        self.pr["head"]["sha"] = "new-untested"
        self.assertEqual(self.run_gate(), [])

    def test_failed_run_never_merges(self):
        self.event["workflow_run"]["conclusion"] = "failure"
        self.assertEqual(self.run_gate(), [])

    def test_fork_never_merges(self):
        self.event["workflow_run"]["head_repository"]["full_name"] = "other/repo"
        self.assertEqual(self.run_gate(), [])

    def test_failed_or_pending_checks_never_merge(self):
        for state, conclusion in [("completed", "failure"), ("in_progress", None)]:
            self.checks["check_runs"][0].update(status=state, conclusion=conclusion)
            self.assertEqual(self.run_gate(), [])

    def test_empty_checks_never_merge(self):
        self.checks = {"total_count": 0, "check_runs": []}
        self.assertEqual(self.run_gate(), [])

    def test_major_never_merges(self):
        self.commit["commit"]["message"] = self.commit["commit"]["message"].replace(
            "semver-minor", "semver-major")
        self.assertEqual(self.run_gate(), [])


if __name__ == "__main__":
    unittest.main()
