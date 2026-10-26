"""Merge verified Dependabot patch/minor PRs after the exact head passed CI.

This script runs from the default branch under workflow_run; PR code is never
checked out with the write token. Major or unrecognized metadata fails closed.
"""
import json
import os
import re
import subprocess
from pathlib import Path


def api(endpoint, method="GET", **fields):
    args = ["gh", "api", endpoint, "--method", method]
    for key, value in fields.items():
        args.extend(["-f", f"{key}={value}"])
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def eligible_commits(commits):
    if not commits:
        return False
    for commit in commits:
        if (commit.get("author") or {}).get("login") != "dependabot[bot]":
            return False
        data = commit["commit"]
        if not data.get("verification", {}).get("verified"):
            return False
        metadata = re.search(r"(?m)^---\nupdated-dependencies:\n(.*?)^\.\.\.$",
                             data["message"], re.S)
        if not metadata:
            return False
        types = re.findall(r"(?m)^  update-type: (\S+)\s*$", metadata[1])
        dependencies = re.findall(r"(?m)^- dependency-name: ", metadata[1])

        # Requirement-only bumps omit update-type; trust only the signed,
        # single-dependency subject with an unambiguous same-major increase.
        if not types and len(dependencies) == 1 and "update-type:" not in metadata[1]:
            subject = data["message"].splitlines()[0]
            bump = re.fullmatch(
                r"(?:[\w()/-]+: )?update (\S+) requirement from "
                r">=(\d+\.\d+\.\d+) to >=(\d+\.\d+\.\d+)", subject,
                re.IGNORECASE)
            name = re.search(r"(?m)^- dependency-name: (\S+)\s*$", metadata[1])
            if bump and name and bump[1] == name[1]:
                before = tuple(map(int, bump[2].split(".")))
                after = tuple(map(int, bump[3].split(".")))
                if after > before and after[0] == before[0]:
                    types = ["version-update:semver-minor"]
        if not types or len(types) != len(dependencies):
            return False
        if any(t not in {"version-update:semver-patch",
                         "version-update:semver-minor"} for t in types):
            return False
    return True



def required_workflows(files):
    required = set()
    for file in files:
        path = file["filename"]
        if path.startswith(".github/"):
            required.update({"rust-ci.yml", "webui-ci.yml", "docs-ci.yml"})
        elif (path.endswith(".rs") or path.endswith("Cargo.toml")
              or path == "Cargo.lock" or path.startswith(("tests/", "benches/"))):
            required.add("rust-ci.yml")
        elif path.startswith("webui/"):
            required.add("webui-ci.yml")
        elif path.startswith("docs/"):
            required.add("docs-ci.yml")
        else:
            # Docker runtime and unknown scopes need a human review.
            return set()
    return required


def workflows_passed(runs, required):
    latest = {}
    for run in runs:
        if run["event"] not in {"pull_request", "workflow_dispatch"}:
            continue
        name = run["path"].removeprefix(".github/workflows/")
        if name not in latest or run["id"] > latest[name]["id"]:
            latest[name] = run
    return bool(required) and all(
        name in latest and latest[name]["status"] == "completed"
        and latest[name]["conclusion"] == "success" for name in required)

def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    run = event["workflow_run"]
    repo = os.environ["GITHUB_REPOSITORY"]
    if (run["conclusion"] != "success"
            or run["event"] not in {"pull_request", "workflow_dispatch"}
            or run["head_repository"]["full_name"] != repo):
        return
    sha = run["head_sha"]
    prs = api(f"repos/{repo}/commits/{sha}/pulls?per_page=100")
    for candidate in prs:
        number = candidate["number"]
        pr = api(f"repos/{repo}/pulls/{number}")
        if (pr["state"] != "open" or pr["draft"]
                or pr["user"]["login"] != "dependabot[bot]"
                or pr["head"]["repo"]["full_name"] != repo
                or pr["head"]["sha"] != sha
                or pr["base"]["ref"] != event["repository"]["default_branch"]):
            continue
        commits = api(f"repos/{repo}/pulls/{number}/commits?per_page=100")
        if len(commits) >= 100 or not eligible_commits(commits):
            print(f"PR #{number}: major/unrecognized/unverified update; review required")
            continue
        files = api(f"repos/{repo}/pulls/{number}/files?per_page=100")
        required = required_workflows(files)
        runs = api(f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100")
        if (len(files) >= 100 or runs["total_count"] > 100
                or not workflows_passed(runs["workflow_runs"], required)):
            print(f"PR #{number}: affected CI missing/failed or scope needs review")
            continue
        checks = api(f"repos/{repo}/commits/{sha}/check-runs?per_page=100")
        if (not checks["check_runs"] or checks["total_count"] > 100
                or any(c["status"] != "completed"
                       or c["conclusion"] not in {"success", "skipped", "neutral"}
                       for c in checks["check_runs"])):
            print(f"PR #{number}: checks incomplete or failed")
            continue
        status = api(f"repos/{repo}/commits/{sha}/status")
        if status["total_count"] and status["state"] != "success":
            print(f"PR #{number}: commit status incomplete or failed")
            continue
        subprocess.run(["gh", "pr", "merge", str(number), "--repo", repo,
                        "--squash", "--match-head-commit", sha], check=True)
        print(f"Merged PR #{number} after successful validation of {sha}")
        # GITHUB_TOKEN merges do not trigger push workflows. Dispatch the build
        # explicitly so the upgrade reaches the published output.
        for workflow in sorted(required):
            subprocess.run(["gh", "workflow", "run", workflow,
                            "--repo", repo, "--ref", pr["base"]["ref"]], check=True)


if __name__ == "__main__":
    main()
