"""Monitors GitHub repositories for new commits, sends Discord webhooks.

Periodically checks specified GitHub repositories and their branches for new commits.

When new commits are detected, it formats them into a message that mimics Discord's
native embed style for commits and sends it to a configured Discord webhook. Tracks the
last seen commit for each branch to prevent duplicate notifications.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, cast

import requests
from dotenv import load_dotenv

from utils.logging import configure_logging

if TYPE_CHECKING:
    from types import FrameType

    from utils.types import Branch, Commit

shutdown_event = threading.Event()

STATUS_OK = 200
STATUS_NO_CONTENT = 204
MAX_MESSAGE_LENGTH = 55
TRUNCATE_LENGTH = 52


def handle_shutdown(_signum: int, _frame: Optional[FrameType]) -> None:
    """Gracefully handle shutdown signals (`SIGTERM`, `SIGINT`).

    Args:
        _signum: The signal number.
        _frame: The current stack frame.

    """
    shutdown_event.set()
    logger.info("Shutdown signal received, stopping monitor...")


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

logging.root.handlers = []
logger = configure_logging()

load_dotenv()

GITHUB_REPOS = os.getenv("GITHUB_REPOS", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_REPOS or not DISCORD_WEBHOOK_URL:
    logger.critical("Error: GITHUB_REPOS and DISCORD_WEBHOOK_URL must be set!")
    sys.exit(1)

BRANCH_BLACKLIST = os.getenv("BRANCH_BLACKLIST", "").strip()


@dataclass
class Repository:
    """Represents a GitHub repository.

    Attributes:
        owner: The owner of the repository.
        name: The name of the repository.
        api_url: The API URL for fetching commits.

    """

    owner: str
    name: str
    api_url: str

    @classmethod
    def from_repo_string(cls, repo_string: str) -> Repository:
        """Create a Repository instance from owner/repo string.

        Args:
            repo_string: The repository string in the format `'owner/repo'`.

        """
        owner, name = repo_string.split("/")
        api_url = f"https://api.github.com/repos/{owner}/{name}/commits"
        return cls(owner=owner, name=name, api_url=api_url)


def parse_blacklist_patterns(blacklist_string: str) -> dict[str, list[str]]:
    """Parse the branch blacklist string into a dictionary.

    The blacklist string can contain global patterns or patterns specific
    to a repository, in the format `'owner/repo:pattern'`.

    Args:
        blacklist_string: The comma-separated blacklist string.

    Returns:
        A dictionary mapping repositories to their blacklist patterns.

    """
    blacklist_patterns: dict[str, list[str]] = {"global": []}
    if not blacklist_string:
        return blacklist_patterns

    patterns = [p.strip() for p in blacklist_string.split(",")]
    for pattern in patterns:
        if ":" in pattern:
            repo_key, branch_pattern = pattern.split(":", 1)
            if repo_key not in blacklist_patterns:
                blacklist_patterns[repo_key] = []
            blacklist_patterns[repo_key].append(branch_pattern)
        else:
            blacklist_patterns["global"].append(pattern)

    return blacklist_patterns


def is_branch_blacklisted(
    repo_key: str,
    branch_name: str,
    blacklist_patterns: dict[str, list[str]],
) -> bool:
    """Check if a branch is blacklisted.

    Args:
        repo_key: The repository key (e.g., `'owner/repo'`).
        branch_name: The name of the branch.
        blacklist_patterns: The blacklist patterns.

    Returns:
        `True` if the branch is blacklisted, `False` otherwise.

    """
    # Check for global blacklists
    for pattern in blacklist_patterns.get("global", []):
        if fnmatch.fnmatch(branch_name, pattern):
            return True

    # Check for repo-specific blacklists
    for pattern in blacklist_patterns.get(repo_key, []):
        if fnmatch.fnmatch(branch_name, pattern):
            return True

    return False


# Parse repository configurations
REPOSITORIES = [
    Repository.from_repo_string(repo.strip()) for repo in GITHUB_REPOS.split(",")
]

POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "120") or "120")
# Defaults to 2 minutes
# Note the API's rate limit is 60 requests per hour for unauthenticated
# requests

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

LAST_COMMITS_FILE = Path("last_commits.json")

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0


def request_with_retry(
    method: Literal["get", "post", "put", "patch", "delete", "head", "options"],
    url: str,
    **kwargs: Any,  # noqa: ANN401
) -> Optional[requests.Response]:
    """Make an HTTP request with exponential backoff retry.

    Args:
        method: The HTTP method (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`, head,
            options).
        url: The URL to request.
        **kwargs: Additional arguments to pass to requests.

    Returns:
        The response object, or `None` if all retries failed.

    """
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(MAX_RETRIES):
        try:
            return requests.request(method, url, timeout=10, **kwargs)
        except (  # noqa: PERF203
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(
                    "Request to %s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    url,
                    attempt + 1,
                    MAX_RETRIES,
                    type(e).__name__,
                    backoff,
                )
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            else:
                logger.exception(
                    "Request to %s failed after %d attempts",
                    url,
                    MAX_RETRIES,
                )
        except requests.exceptions.RequestException:
            logger.exception("Request to %s failed with non-retryable error", url)
            return None

    return None


def get_avatar_url(commit: Commit) -> Optional[str]:
    """Fetch avatar URL.

    Fallback to Gravatar based on email if needed.

    Args:
        commit: The commit data dictionary.

    Returns:
        The avatar URL or Gravatar URL.

    """
    if commit.get("author") and commit["author"].get("avatar_url"):
        return str(commit["author"]["avatar_url"])
    email = commit["commit"]["author"].get("email")
    if email:
        email = email.strip().lower()
        email_hash = hashlib.md5(
            email.encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        logger.debug("Using Gravatar for email `%s`: hash=`%s`", email, email_hash)
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"
    return None


def get_branches(repo: Repository) -> list[Branch]:
    """Fetch list of branches for a repository.

    Args:
        repo: The repository object.

    Returns:
        A list of branches in the repository.

    """
    branches_url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/branches"
    response = request_with_retry("get", branches_url, headers=HEADERS)
    if response is None:
        logger.error(
            "Failed to fetch branches for %s/%s after retries",
            repo.owner,
            repo.name,
        )
        return []
    if response.status_code != STATUS_OK:
        logger.error(
            "Error fetching branches for %s/%s: `%s`",
            repo.owner,
            repo.name,
            response.text,
        )
        return []
    branches: list[Branch] = response.json()
    return branches


def get_commits_for_branch(
    repo: Repository,
    branch_name: str,
) -> list[Commit]:
    """Fetch commits for a given branch in a repository.

    Args:
        repo: The repository object.
        branch_name: The name of the branch.

    Returns:
        A list of commits in the branch, or empty list on failure.

    """
    url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/commits?sha={branch_name}"
    response = request_with_retry("get", url, headers=HEADERS)
    if response is None:
        logger.error(
            "Failed to fetch commits for %s/%s branch %s after retries",
            repo.owner,
            repo.name,
            branch_name,
        )
        return []
    if response.status_code != STATUS_OK:
        logger.error(
            "Error fetching commits for %s/%s branch %s: %s",
            repo.owner,
            repo.name,
            branch_name,
            response.text,
        )
        return []
    commits: list[Commit] = response.json()
    for commit in commits:
        commit["id"] = commit["sha"]
        commit["message"] = commit["commit"]["message"]
        commit["author_username"] = (
            commit["author"]["login"] if commit.get("author") else "unknown"
        )
        commit["avatar_url"] = get_avatar_url(commit)
        commit["url"] = commit["html_url"]
        commit["repository"] = f"{repo.owner}/{repo.name}"
        commit["branch"] = branch_name
    return commits


def load_last_commits() -> dict[str, dict[str, str]]:
    """Load last processed commit IDs per repository and branch.

    Returns:
        A dictionary mapping repository/branch pairs to their last
        processed commit IDs.

    """
    try:
        with LAST_COMMITS_FILE.open(encoding="utf-8") as f:
            return cast("dict[str, dict[str, str]]", json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_last_commits(last_commits: dict[str, dict[str, str]]) -> None:
    """Save last processed commit IDs per repository and branch.

    Args:
        last_commits: A dictionary mapping repository/branch pairs to their
            last processed commit IDs.

    """
    with LAST_COMMITS_FILE.open("w", encoding="utf-8") as f:
        json.dump(last_commits, f, indent=2)


def initialize_last_commits() -> None:
    """Initialize last commits for all repositories and their branches.

    This function checks if the last commits file exists. If it doesn't,
    it creates a new file and populates it with the latest commit IDs
    for each branch in the specified repositories.
    """
    last_commits = load_last_commits()
    updated = False

    for repo in REPOSITORIES:
        repo_key = f"{repo.owner}/{repo.name}"
        if repo_key not in last_commits:
            last_commits[repo_key] = {}
            branches = get_branches(repo)
            for branch in branches:
                branch_name = branch["name"]
                commits = get_commits_for_branch(repo, branch_name)
                if commits:
                    last_commits[repo_key][branch_name] = commits[0]["id"]
                    updated = True

    if updated:
        save_last_commits(last_commits)


def send_aggregated_to_discord(  # pylint: disable=too-many-locals
    commits: list[Commit],
    repo: str,
    branch_name: str,
    old_commit_id: str,
) -> None:
    """Send a Discord message containing all new commits for a branch.

    Args:
        commits: A list of commit dictionaries.
        repo: The repository name.
        branch_name: The name of the branch.
        old_commit_id: The commit ID before the new commits.

    """
    count = len(commits)
    first_commit = commits[0]
    logger.debug(
        "Sending aggregated message to Discord for %s branch %s: %d new commits",
        repo,
        branch_name,
        count,
    )

    if count == 1:
        # For a single commit, use its direct URL
        commit_url = first_commit["url"]
    else:
        last_commit = commits[-1]
        commit_url = (
            f"https://github.com/{repo}/compare/{old_commit_id}...{last_commit['id']}"
        )

    title = (
        f"[{repo}:{branch_name}] {count} new {'commit' if count == 1 else 'commits'}"
    )

    # Use the first commit's info for the embed author
    author_url = ""
    if first_commit.get("author") and first_commit["author"].get("html_url"):
        author_url = first_commit["author"]["html_url"]
    embed_author = {
        "name": first_commit["author_username"],
        "url": author_url,
        "icon_url": first_commit["avatar_url"] or "",
    }

    # Each line: commit hash (as a clickable link), then the commit
    # message and author username
    lines = []
    for commit in commits:
        commit_link = f"[`{commit['id'][:7]}`]({commit['url']})"
        message = (
            commit["message"]
            if len(commit["message"]) <= MAX_MESSAGE_LENGTH
            else f"{commit['message'][:TRUNCATE_LENGTH]}..."
        )
        line = f"{commit_link} {message} - {commit['author_username']}"
        lines.append(line)
    description = "\n".join(lines)

    footer = {
        "text": "Powered by mdrxy/commit-to-discord",
    }

    embed = {
        "title": title,
        "url": commit_url,
        "description": description,
        "author": embed_author,
        "footer": footer,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    if not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL is not set. Cannot send message to Discord.")
        return
    response = request_with_retry(
        "post",
        DISCORD_WEBHOOK_URL,
        json=payload,
        headers=headers,
    )
    if response is None:
        logger.error(
            "Failed to post to Discord after retries for %s branch %s. Payload: %s",
            repo,
            branch_name,
            json.dumps(payload, indent=2),
        )
        return
    if response.status_code == STATUS_NO_CONTENT:
        logger.info(
            "Aggregated commit message posted to Discord for %s branch %s",
            repo,
            branch_name,
        )
    else:
        logger.error(
            "Failed to post to Discord (status %d): `%s`. Payload: %s",
            response.status_code,
            response.text,
            json.dumps(payload, indent=2),
        )


def monitor_feed() -> None:  # noqa: C901, PLR0912
    """Monitor commits across all repositories and branches."""
    logger.info("Starting commit monitoring...")
    last_commits = load_last_commits()
    blacklist_patterns = parse_blacklist_patterns(BRANCH_BLACKLIST)

    while not shutdown_event.is_set():  # pylint: disable=too-many-nested-blocks
        logger.debug("Checking for new commits")
        for repo in REPOSITORIES:
            repo_key = f"{repo.owner}/{repo.name}"
            if repo_key not in last_commits:
                last_commits[repo_key] = {}

            branches = get_branches(repo)
            for branch in branches:
                branch_name = branch["name"]
                if is_branch_blacklisted(repo_key, branch_name, blacklist_patterns):
                    logger.debug(
                        "Branch %s in repo %s is blacklisted, skipping.",
                        branch_name,
                        repo_key,
                    )
                    continue

                commits = get_commits_for_branch(repo, branch_name)
                if not commits:
                    logger.warning(
                        "No commits returned for %s branch %s.",
                        repo_key,
                        branch_name,
                    )
                    continue

                # If this branch is new, consider all commits as new
                if branch_name not in last_commits[repo_key]:
                    new_commits = commits[::-1]
                else:
                    last_commit_id = last_commits[repo_key][branch_name]
                    index = None
                    for i, commit in enumerate(commits):
                        if commit["id"] == last_commit_id:
                            index = i
                            break
                    if index is None:
                        new_commits = commits[::-1]
                    else:
                        new_commits = commits[:index][::-1]

                if new_commits:
                    send_aggregated_to_discord(
                        new_commits,
                        repo_key,
                        branch_name,
                        last_commits.get(repo_key, {}).get(branch_name, ""),
                    )
                    # Update the branch tracking with the newest commit
                    last_commits[repo_key][branch_name] = new_commits[-1]["id"]
                    save_last_commits(last_commits)

        time.sleep(POLL_INTERVAL_SECONDS)

    # Clean shutdown: save state and exit
    save_last_commits(last_commits)
    logger.info("Commit watcher exited cleanly")


if __name__ == "__main__":
    initialize_last_commits()
    monitor_feed()
