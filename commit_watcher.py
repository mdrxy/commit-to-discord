"""
Commit Watcher: watches for commits in a GitHub repository and sends
notifications to Discord.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-28

Changelog:
    - 1.0.0 (2025-03-29): Initial release.
"""

import hashlib
import json
import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv

from utils.logging import configure_logging

logging.root.handlers = []
logger = configure_logging()

load_dotenv()

GITHUB_API_URL = os.getenv("GITHUB_API_URL")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_API_URL or not DISCORD_WEBHOOK_URL:
    logger.critical("Error: GITHUB_API_URL and DISCORD_WEBHOOK_URL must be set!")
    sys.exit(1)


def parse_repo_info(api_url):
    """
    Parse repository owner and name from the API URL.
    """
    # Expecting a URL like https://api.github.com/repos/<owner>/<repo>/commits
    parts = api_url.rstrip("/").split("/")
    if len(parts) >= 5:
        owner = parts[-3]
        repo = parts[-2]
        logger.debug("Parsed repository info: owner=`%s`, repo=`%s`", owner, repo)
        return owner, repo
    return None, None


OWNER, REPO = parse_repo_info(GITHUB_API_URL)

POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "120") or "120")
# Defaults to 2 minutes
# Note the API's rate limit is 60 requests per hour for unauthenticated requests

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

LAST_COMMITS_FILE = "last_commits.json"


def get_avatar_url(commit):
    """
    Fetch avatar URL. Fallback to Gravatar based on email if needed.
    """
    if commit.get("author") and commit["author"].get("avatar_url"):
        logger.debug(
            "Using GitHub avatar for author `%s`: avatar_url=`%s`",
            commit["author"]["login"],
            commit["author"]["avatar_url"],
        )
        return commit["author"]["avatar_url"]
    email = commit["commit"]["author"].get("email")
    if email:
        email = email.strip().lower()
        email_hash = hashlib.md5(email.encode("utf-8")).hexdigest()
        logger.debug("Using Gravatar for email `%s`: hash=`%s`", email, email_hash)
        return f"https://www.gravatar.com/avatar/{email_hash}?d=identicon"
    return None


def get_author_url(commit):
    """
    Fetch author URL from commit data.
    """
    if commit.get("author") and commit["author"].get("html_url"):
        logger.debug(
            "Using GitHub author URL for author `%s`: html_url=`%s`",
            commit["author"]["login"],
            commit["author"]["html_url"],
        )
        return commit["author"]["html_url"]


def get_branches():
    """
    Fetch list of branches.
    """
    branches_url = f"https://api.github.com/repos/{OWNER}/{REPO}/branches"
    try:
        response = requests.get(branches_url, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching branches: `%s`", e)
        return []
    if response.status_code != 200:
        logger.error("Error fetching branches: `%s`", response.text)
        return []
    return response.json()


def get_commits_for_branch(branch_name):
    """
    Fetch commits for a given branch.
    """
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/commits?sha={branch_name}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching commits for branch %s: `%s`", branch_name, e)
        return []
    if response.status_code != 200:
        logger.error(
            "Error fetching commits for branch %s: `%s`", branch_name, response.text
        )
        return []
    commits = response.json()
    commit_list = []
    for commit in commits:
        commit_list.append(
            {
                "id": commit["sha"],
                "message": commit["commit"]["message"],
                "author_username": commit["author"]["login"],
                "avatar_url": get_avatar_url(commit),
                "url": commit["html_url"],
                "repository": REPO,
                "branch": branch_name,
            }
        )
    return commit_list


def load_last_commits():
    """
    Load last processed commit IDs per branch.
    """
    if os.path.exists(LAST_COMMITS_FILE):
        with open(LAST_COMMITS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_last_commits(last_commits):
    """
    Save last processed commit IDs per branch.
    """
    with open(LAST_COMMITS_FILE, "w", encoding="utf-8") as f:
        json.dump(last_commits, f)


def initialize_last_commits():
    """
    Initialize last commits for all branches.
    """
    last_commits = load_last_commits()
    branches = get_branches()
    updated = False
    for branch in branches:
        branch_name = branch.get("name")
        if branch_name not in last_commits:
            commits = get_commits_for_branch(branch_name)
            if commits:
                last_commits[branch_name] = commits[0]["id"]
                updated = True
            else:
                logger.error(
                    "Error: Unable to fetch commits for branch %s during initialization.",
                    branch_name,
                )
    if updated:
        save_last_commits(last_commits)


def send_aggregated_to_discord(commits, branch_name):
    """
    Send a single Discord message containing all new commits for a
    branch.
    """
    count = len(commits)
    first_commit = commits[0]
    last_commit = commits[-1]
    compare_url = (
        f"https://github.com/{OWNER}/{REPO}/compare/"
        f"{first_commit['id']}...{last_commit['id']}"
    )

    title = (
        f"[{REPO}:{branch_name}] {count} new {'commit' if count == 1 else 'commits'}"
    )

    # Use the first commit's info for the embed author
    embed_author = {
        "name": first_commit["author_username"],
        "url": get_author_url(first_commit) or "",
        "icon_url": first_commit["avatar_url"] or "",
    }

    # Each line: commit hash (as a clickable link), then the commit message and author username
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

    embed = {
        "title": title,
        "url": compare_url,
        "description": description,
        "author": embed_author,
    }

    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=10
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error posting aggregated message to Discord: `%s`", e)
        return
    if response.status_code == 204:
        logger.info(
            "Aggregated commit message posted to Discord for branch %s", branch_name
        )
    else:
        logger.error(
            "Failed to post aggregated message to Discord: `%s`", response.text
        )


def monitor_feed():
    """
    Monitor commits across all branches and send one aggregated message
    per branch.
    """
    logger.info("Starting commit monitoring...")
    last_commits = load_last_commits()
    while True:
        branches = get_branches()
        for branch in branches:
            branch_name = branch.get("name")
            commits = get_commits_for_branch(branch_name)
            if not commits:
                logger.warning("No commits returned for branch %s.", branch_name)
                continue

            # If this branch is new, consider all commits as new.
            if branch_name not in last_commits:
                new_commits = commits[::-1]
            else:
                last_commit_id = last_commits[branch_name]
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
                send_aggregated_to_discord(new_commits, branch_name)
                # Update the branch tracking with the newest commit.
                last_commits[branch_name] = new_commits[-1]["id"]
                save_last_commits(last_commits)
            else:
                logger.debug("No new commits on branch %s.", branch_name)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    initialize_last_commits()
    monitor_feed()
