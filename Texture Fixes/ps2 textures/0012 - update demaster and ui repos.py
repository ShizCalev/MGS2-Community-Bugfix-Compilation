import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ==========================================================
# CONFIGURATION
# ==========================================================
TARGET_REPOS = [
    r"C:\Development\Git\MGS2-Demastered-Substance-Edition",
    r"C:\Development\Git\MGS2-Upscaled-UI-Textures",
]

MAX_WORKERS = max(1, min(len(TARGET_REPOS), os.cpu_count() or 2))

print_lock = Lock()


# ==========================================================
# UTILITIES
# ==========================================================
def log(message):
    with print_lock:
        print(message)


def fail(message, exit_code=1):
    log(f"[!] {message}")
    input("Press ENTER to exit...")
    sys.exit(exit_code)


def run(cmd, cwd=None, check=True):
    log(f"\n[{cwd}] $ {' '.join(cmd)}")
    try:
        subprocess.run(cmd, cwd=cwd, check=check)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Command failed in {cwd}: {' '.join(cmd)} (exit code {e.returncode})"
        ) from e


def git_output(cmd, cwd):
    result = subprocess.run(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def get_submodule_paths(repo_path):
    result = subprocess.run(
        ["git", "submodule", "status", "--recursive"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )

    submodules = []

    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue

        rel_path = parts[1]
        full_path = os.path.join(repo_path, rel_path)
        submodules.append(full_path)

    return submodules


def repo_exists_and_is_git(repo_path):
    if not os.path.isdir(repo_path):
        return False

    git_dir = os.path.join(repo_path, ".git")
    return os.path.exists(git_dir)


def pull_current_branch(repo_path):
    branch = git_output(["git", "branch", "--show-current"], cwd=repo_path)

    if not branch:
        log(f"[!] Detached HEAD, not switching branches or pulling: {repo_path}")
        return None

    log(f"[+] Staying on current branch '{branch}' in: {repo_path}")

    run(["git", "fetch", "origin"], cwd=repo_path)

    upstream = git_output(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=repo_path,
    )

    if upstream:
        run(["git", "pull", "--ff-only"], cwd=repo_path)
        return branch

    remote_branch = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=repo_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    if remote_branch.returncode != 0:
        log(f"[!] Current branch '{branch}' has no origin branch, not pulling: {repo_path}")
        return branch

    run(["git", "branch", "--set-upstream-to", f"origin/{branch}", branch], cwd=repo_path)
    run(["git", "pull", "--ff-only"], cwd=repo_path)

    return branch


def update_submodule(submodule_path):
    if not os.path.isdir(submodule_path):
        raise RuntimeError(f"Submodule directory missing: {submodule_path}")

    log(f"\n=== [ Submodule ] {submodule_path} ===")

    old_commit = git_output(["git", "rev-parse", "HEAD"], cwd=submodule_path)
    if old_commit:
        log(f"[+] Current commit: {old_commit}")

    pull_current_branch(submodule_path)

    run(
        ["git", "submodule", "update", "--recursive", "--remote", "--init"],
        cwd=submodule_path,
    )

    new_commit = git_output(["git", "rev-parse", "HEAD"], cwd=submodule_path)
    if new_commit:
        log(f"[+] New commit: {new_commit}")


# ==========================================================
# MAIN REPO PROCESSING
# ==========================================================
def process_repo(repo_path):
    log("\n=================================================")
    log(f"[REPO] {repo_path}")
    log("=================================================")

    if not repo_exists_and_is_git(repo_path):
        raise RuntimeError(f"Repo not found or not a git repo: {repo_path}")

    current_commit = git_output(["git", "rev-parse", "HEAD"], cwd=repo_path)
    if current_commit:
        log(f"[+] Repo HEAD: {current_commit}")

    run(["git", "submodule", "init"], cwd=repo_path)
    run(["git", "submodule", "update", "--recursive", "--init"], cwd=repo_path)

    submodules = get_submodule_paths(repo_path)
    log(f"[+] Found {len(submodules)} recursive submodule(s)")

    for submodule_path in submodules:
        update_submodule(submodule_path)

    log(f"\n[+] Final status for repo: {repo_path}")
    run(["git", "status"], cwd=repo_path)

    log(f"[✓] Finished: {repo_path}")


def main():
    log("=== [ Updating demaster and upscaled external repos ] ===")
    log(f"[+] Repo count: {len(TARGET_REPOS)}")

    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(process_repo, repo_path): repo_path
            for repo_path in TARGET_REPOS
        }

        for future in as_completed(future_map):
            repo_path = future_map[future]
            try:
                future.result()
            except Exception as e:
                errors.append((repo_path, str(e)))

    if errors:
        log("\n[!] One or more repos failed:")
        for repo_path, error in errors:
            log(f"    {repo_path}")
            log(f"        {error}")
        input("Press ENTER to exit...")
        sys.exit(1)

    log("\n✅ All repos updated successfully.")


if __name__ == "__main__":
    main()