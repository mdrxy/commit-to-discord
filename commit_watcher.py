"""
Monitors GitHub repositories for new commits and sends Discord webhook
notifications.

Periodically checks specified GitHub repositories and their branches for
new commits. When new commits are detected, it formats them into a
message that mimics Discord's native embed style for commits and sends
it to a configured Discord webhook. Tracks the last seen commit for
each branch to prevent duplicate notifications.

Author: Mason Daugherty <@mdrxy>
Version: 2.0.0
Last Modified: 2025-04-14

Changelog:
    - 1.0.0 (2025-03-29): Initial release.
    - 2.0.0 (2025-04-14): Added support for multiple repositories.
"""

import hashlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

from utils.logging import configure_logging

logging.root.handlers = []
logger = configure_logging()

load_dotenv()

GITHUB_REPOS = os.getenv("GITHUB_REPOS", "").strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_REPOS or not DISCORD_WEBHOOK_URL:
    logger.critical("Error: GITHUB_REPOS and DISCORD_WEBHOOK_URL must be set!")
    sys.exit(1)


@dataclass
class Repository:
    """
    Represents a GitHub repository.

    Attributes:
    - owner (str): The owner of the repository.
    - name (str): The name of the repository.
    - api_url (str): The API URL for fetching commits.
    """

    owner: str
    name: str
    api_url: str

    @classmethod
    def from_repo_string(cls, repo_string: str) -> "Repository":
        """
        Create a Repository instance from owner/repo string.

        Parameters:
        - repo_string (str): The repository string in the format
            "owner/repo".
        """
        owner, name = repo_string.split("/")
        api_url = f"https://api.github.com/repos/{owner}/{name}/commits"
        return cls(owner=owner, name=name, api_url=api_url)


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

LAST_COMMITS_FILE = "last_commits.json"


def get_avatar_url(commit: dict) -> Optional[str]:
    """
    Fetch avatar URL. Fallback to Gravatar based on email if needed.

    Parameters:
    - commit (dict): The commit data dictionary.

    Returns:
    - str: The avatar URL or Gravatar URL.
    """
    if commit.get("author") and commit["author"].get("avatar_url"):
        return commit["author"]["avatar_url"]
    email = commit["commit"]["author"].get("email")
    if email:
        email = email.strip().lower()
        email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
        logger.debug("Using Gravatar for email `%s`: hash=`%s`", email, email_hash)
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"
    return None


def get_author_url(commit: dict) -> Optional[str]:
    """
    Fetch author URL from commit data.

    Parameters:
    - commit (dict): The commit data dictionary.

    Returns:
    - str: The author URL or None if not found.
    """
    if commit.get("author_username"):
        return "https://github.com/" + commit["author_username"]
    logger.warning(
        "No author username found for commit `%s`, no URL returned", commit["id"]
    )
    return None


def get_branches(repo: Repository) -> List[dict]:
    """
    Fetch list of branches for a repository.

    Parameters:
    - repo (Repository): The repository object.

    Returns:
    - List[dict]: A list of branches in the repository.
    """
    branches_url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/branches"
    try:
        response = requests.get(branches_url, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error(
            "Error fetching branches for %s/%s: `%s`", repo.owner, repo.name, e
        )
        return []
    if response.status_code != 200:
        logger.error(
            "Error fetching branches for %s/%s: `%s`",
            repo.owner,
            repo.name,
            response.text,
        )
        return []
    return response.json()


def get_commits_for_branch(repo: Repository, branch_name: str) -> List[dict]:
    """
    Fetch commits for a given branch in a repository.

    Parameters:
    - repo (Repository): The repository object.
    - branch_name (str): The name of the branch.

    Returns:
    - List[dict]: A list of commits in the branch.
    """
    url = f"https://api.github.com/repos/{repo.owner}/{repo.name}/commits?sha={branch_name}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error(
            "Error fetching commits for %s/%s branch %s: `%s`",
            repo.owner,
            repo.name,
            branch_name,
            e,
        )
        return []
    if response.status_code != 200:
        logger.error(
            "Error fetching commits for %s/%s branch %s: `%s`",
            repo.owner,
            repo.name,
            branch_name,
            response.text,
        )
        return []
    commits = response.json()
    commit_list = []
    for commit in commits:
        commit_list.append(
            {
                "id": commit["sha"],
                "message": commit["commit"]["message"],
                "author_username": (
                    commit["author"]["login"] if commit.get("author") else "unknown"
                ),
                "avatar_url": get_avatar_url(commit),
                "url": commit["html_url"],
                "repository": f"{repo.owner}/{repo.name}",
                "branch": branch_name,
            }
        )
    return commit_list


def load_last_commits() -> Dict[str, Dict[str, str]]:
    """
    Load last processed commit IDs per repository and branch.

    Returns:
    - Dict[str, Dict[str, str]]: A dictionary mapping repository/branch
        pairs to their last processed commit IDs.
    """
    try:
        with open(LAST_COMMITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_last_commits(last_commits: Dict[str, Dict[str, str]]) -> None:
    """
    Save last processed commit IDs per repository and branch.

    Parameters:
    - last_commits (Dict[str, Dict[str, str]]): A dictionary mapping
        repository/branch pairs to their last processed commit IDs.
    """
    with open(LAST_COMMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(last_commits, f, indent=2)


def initialize_last_commits() -> None:
    """
    Initialize last commits for all repositories and their branches.

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
    commits: List[dict], repo: str, branch_name: str
) -> None:
    """
    Send a single Discord message containing all new commits for a
    branch.

    Parameters:
    - commits (List[dict]): A list of commit dictionaries.
    - repo (str): The repository name.
    - branch_name (str): The name of the branch.
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
            f"https://github.com/{repo}/compare/"
            f"{last_commit['id']}...{first_commit['id']}"
        )

    title = (
        f"[{repo}:{branch_name}] {count} new {'commit' if count == 1 else 'commits'}"
    )

    # Use the first commit's info for the embed author
    embed_author = {
        "name": first_commit["author_username"],
        "url": get_author_url(first_commit) or "",
        "icon_url": first_commit["avatar_url"] or "",
    }

    # Each line: commit hash (as a clickable link), then the commit
    # message and author username
    lines = []
    for commit in commits:
        commit_link = f"[`{commit['id'][:7]}`]({commit['url']})"
        message = (
            commit["message"]
            if len(commit["message"]) <= 55
            else commit["message"][:52] + "..."
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
    }

    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    if not DISCORD_WEBHOOK_URL:
        logger.error("DISCORD_WEBHOOK_URL is not set. Cannot send message to Discord.")
        return
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=10
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error posting aggregated message to Discord: `%s`", e)
        return
    if response.status_code == 204:
        logger.info(
            "Aggregated commit message posted to Discord for %s branch %s",
            repo,
            branch_name,
        )
    else:
        logger.error(
            "Failed to post aggregated message to Discord: `%s`", response.text
        )


def monitor_feed() -> None:
    """
    Monitor commits across all repositories and branches.
    """
    logger.info("Starting commit monitoring...")
    last_commits = load_last_commits()

    while True:  # pylint: disable=too-many-nested-blocks
        logger.debug("Checking for new commits")
        for repo in REPOSITORIES:
            repo_key = f"{repo.owner}/{repo.name}"
            if repo_key not in last_commits:
                last_commits[repo_key] = {}

            branches = get_branches(repo)
            for branch in branches:
                branch_name = branch["name"]
                commits = get_commits_for_branch(repo, branch_name)
                if not commits:
                    logger.warning(
                        "No commits returned for %s branch %s.", repo_key, branch_name
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
                    send_aggregated_to_discord(new_commits, repo_key, branch_name)
                    # Update the branch tracking with the newest commit
                    last_commits[repo_key][branch_name] = new_commits[-1]["id"]
                    save_last_commits(last_commits)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    initialize_last_commits()
    monitor_feed()
