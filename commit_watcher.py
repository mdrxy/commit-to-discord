"""
Primary script to monitor a GitHub repository for new commits and send them to
Discord.

This script uses the GitHub API to fetch the latest commits from a specified
repository.

It periodically checks for new commits using the specified intervanl (s). If
multiple commits have occurred since the last check, it sends all new commits in
chronological order to a Discord webhook.

It requires the following environment variables:
- GITHUB_API_URL: The URL to fetch the latest commits from the GitHub API.
- DISCORD_WEBHOOK_URL: The URL to send the commit details to a Discord webhook.
- GITHUB_TOKEN: Optional GitHub token to authenticate API requests.
- REPOSITORY_NAME: The name of the repository being monitored.
"""

import time
import logging
import sys
import os
import requests
from dotenv import load_dotenv
from utils.logging import configure_logging

logging.root.handlers = []
logger = configure_logging()

load_dotenv()

GITHUB_API_URL = os.getenv("GITHUB_API_URL")
REPOSITORY_NAME = os.getenv("REPOSITORY_NAME")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_API_URL or not DISCORD_WEBHOOK_URL or not REPOSITORY_NAME:
    logger.critical(
        "Error: GITHUB_API_URL, DISCORD_WEBHOOK_URL, and REPOSITORY_NAME must be set!"
    )
    sys.exit(1)

# File to track the latest commit ID processed
LAST_COMMIT_FILE = "last_commit.txt"

POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "120") or "120")
# Defaults to 2 minutes
# Note the API's rate limit is 60 requests per hour for unauthenticated requests!

HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"


def get_commits():
    """
    Fetch a list of commits for the specified repo from the GitHub API.

    Note: the `/commits` endpoint returns commits in descending order (newest
    first).

    Only the first 30 commits are returned by default. This should be sufficient
    for our use case since it is unlikely that more than 30 commits will be made
    in a 5-minute period.
    """
    try:
        response = requests.get(GITHUB_API_URL, headers=HEADERS, timeout=10)
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching commits: `%s`", e)
        return []
    if response.status_code != 200:
        logger.error("Error fetching commits: `%s`", response.text)
        return []
    commits = response.json()
    commit_list = []
    for commit in commits:
        commit_list.append(
            {
                "id": commit["sha"],
                "message": commit["commit"]["message"],
                "author": commit["commit"]["author"]["name"],
                "url": commit["html_url"],
                "repository": REPOSITORY_NAME,
            }
        )
    return commit_list


def load_last_commit():
    """Load the last processed commit ID."""
    if os.path.exists(LAST_COMMIT_FILE):
        with open(LAST_COMMIT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def save_last_commit(commit_id):
    """Save the last processed commit ID."""
    with open(LAST_COMMIT_FILE, "w", encoding="utf-8") as f:
        logger.debug("Saved last commit ID to file: `%s`", commit_id)
        f.write(commit_id)


def initialize_last_commit():
    """
    If no last commit is stored, initialize the file with the latest commit ID.
    This prevents sending all past commits on the first run.
    """
    if load_last_commit() is None:
        logger.debug("Initializing last commit file...")
        commits = get_commits()
        if commits:
            initial_commit_id = commits[0]["id"]
            save_last_commit(initial_commit_id)
            logger.debug(
                "Initialized last commit file with latest commit: `%s`",
                initial_commit_id,
            )
        else:
            logger.error("Error: Unable to fetch commits during initialization.")
            sys.exit(1)


def send_to_discord(commit):
    """
    Send the commit details to Discord.

    The commit details are sent as an embed to the Discord webhook URL. The
    docs on Discord webhooks can be found here:
    https://discord.com/developers/docs/resources/webhook#execute-webhook
    """
    embed = {
        "title": f"{REPOSITORY_NAME} - {commit["message"]}",
        "url": commit["url"],
        "author": {"name": commit["author"]},
        "description": f"Commit: `{commit['id'][:7]}`",
    }
    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=10
        )
    except requests.exceptions.RequestException as e:
        logger.error("Error posting to Discord: `%s`", e)
        return
    if response.status_code == 204:
        logger.info("Commit posted to Discord successfully!")
        logger.info("Details: %s", commit)
    else:
        logger.error("Failed to post to Discord: `%s`", response.text)


def monitor_feed():
    """
    Monitor the GitHub API for new commits and send them to Discord.

    Polls the API every 5 minutes to check for new commits.
    If new commits are found, they are sent to Discord.

    The last processed commit ID is stored in a file to track the latest commit.

    If the script is restarted, it will pick up from the last processed commit.

    Note: if more than 30 commits are made in a 5-minute period, only the first
    30 will be sent (due to the default limit of the `/commits` endpoint). A
    future TODO would be to handle pagination to fetch all commits.
    """
    last_commit_id = load_last_commit()

    while True:
        logger.info("Starting commit monitoring...")
        commits = get_commits()
        if not commits:
            logger.warning("No commits returned from API. Exiting...")
            sys.exit(1)

        # The API returns commits in descending order (newest first).
        new_commits = []
        if last_commit_id is None:
            # Should not happen because initialize_last_commit() ensures a value exists.
            new_commits = commits[::-1]
        else:
            # Look for the last processed commit in the fetched list.
            index = None
            for i, commit in enumerate(commits):
                if commit["id"] == last_commit_id:
                    index = i
                    break
            if index is None:
                # If the last commit isn't found, assume all commits are new.
                # This can happen if the last commit was deleted or modified.
                new_commits = commits[::-1]
            else:
                # All commits *before* the last processed one are new.
                new_commits = commits[:index][::-1]

        if new_commits:
            for commit in new_commits:
                logger.debug("New commit detected: `%s`", commit["message"])
                send_to_discord(commit)
                # Update the last commit ID after processing each new commit.
                # Note: if the script breaks during processing, the last commit
                # ID will be updated and the script will pick up from the last
                # processed, which may result in duplicate commits being sent.
                last_commit_id = commit["id"]
                save_last_commit(last_commit_id)
        else:
            logger.debug(
                "No new commits. Checking again in %s seconds...", POLL_INTERVAL_SECONDS
            )

        time.sleep(float(POLL_INTERVAL_SECONDS))  # Wait before checking again


if __name__ == "__main__":
    initialize_last_commit()
    monitor_feed()
