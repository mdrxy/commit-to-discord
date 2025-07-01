# commit-to-discord

[![GitHub last commit](https://img.shields.io/github/last-commit/mdrxy/commit-to-discord)](https://github.com/mdrxy/commit-to-discord/commits/main)

Monitors specified GitHub repositories for new commits across all branches and sends detailed notifications to a Discord webhook. The notifications are designed to closely mirror Discord's native embed style for commit messages, providing a clean and familiar look.

## Key Features

* **Multi-Repository & Multi-Branch Monitoring:** Keep track of commits across several repositories and all their active branches.
* **Discord Embed-Style Notifications:** Delivers well-formatted messages to your Discord channel, similar to native GitHub integrations.
* **Persistent Tracking:** Remembers the last notified commit for each branch to avoid duplicates, even after restarts (uses `last_commits.json`).
* **Configurable:** Set repository list, webhook URL, polling interval, and GitHub token via environment variables.
* **Dockerized:** Easy to deploy and run using Docker, with `Makefile` support for common operations.
* **GitHub API Token Support:** Use a GitHub Personal Access Token for higher API rate limits or to access private repositories.

## Example Discord Notification

![Example Discord Notification](/img/example.png)

## Prerequisites

* Docker (or Podman) installed.
* A Discord Webhook URL.
* Repositories to monitor on GitHub.

## Setup & Configuration

1. **Clone the repository (if you haven't already):**

    ```bash
    git clone https://github.com/mdrxy/commit-to-discord.git
    cd commit-to-discord
    ```

2. **Create an environment file:**
    Copy the sample `.sample.env` to `.env` and customize it:

    ```bash
    cp .sample.env .env
    ```

3. **Edit `.env` with your settings:**

    * `GITHUB_REPOS`: A comma-separated list of GitHub repositories to monitor.
        * Format: `owner1/repo1,owner2/repo2`
        * Example: `AzuraCast/AzuraCast,mdrxy/commit-to-discord`
    * `DISCORD_WEBHOOK_URL`: Your Discord channel's webhook URL.
    * `GITHUB_TOKEN` (Optional): Your GitHub Personal Access Token. Recommended for private repositories or to avoid rate limiting on public repositories with frequent checks.
    * `POLL_INTERVAL_SECONDS` (Optional): How often (in seconds) to check for new commits.
        * Defaults to `120` (2 minutes).
        * Be mindful of GitHub API rate limits (60 requests/hour unauthenticated per IP, 5000/hour authenticated). The script makes one request per branch per repository during each poll.
    * `BRANCH_BLACKLIST` (Optional): A comma-separated list of branch patterns to ignore.
        * **Global patterns:** Apply to all repositories (e.g., `main,develop`).
        * **Repository-specific patterns:** Apply to a single repository (e.g., `owner/repo:main,owner/repo:develop`).
        * **Wildcards:** Supported for pattern matching (e.g., `release/*, feature-*`).
        * Example: `dependabot/*,mdrxy/commit-to-discord:main` will ignore all `dependabot/` branches in every repository and the `main` branch in `mdrxy/commit-to-discord`.

## Usage (Docker)

The provided `Makefile` simplifies Docker operations.

* **Build and Run (Recommended):**

    ```bash
    make
    ```

    This will clean any previous instances, build the image, run the container in detached mode, and start following logs.

* **Using Podman:**
    If you prefer Podman, you can set the `DOCKER_TOOL` environment variable:

    ```bash
    DOCKER_TOOL=podman make
    ```

### Manual Docker Commands

* **Build the Docker image:**

    ```bash
    docker build -t commit-to-discord-image .
    ```

* **Run the Docker container:**

    ```bash
    docker run -d --restart unless-stopped \
      --name commit-to-discord \
      --env-file .env \
      commit-to-discord-image
    ```

    *Note: The `Makefile` passes `LOG_LEVEL` as an environment variable (`-e LOG_LEVEL=$(LOG_LEVEL)`). If running manually and you need to adjust `LOG_LEVEL` (default 'info' in `utils/logging.py`), you can add `-e LOG_LEVEL=debug` or similar to the `docker run` command.*

### Makefile Targets

* `make` or `make default`: Cleans, builds, runs, and tails logs.
* `make q`: Quick build and run (cleans first).
* `make build`: Builds the Docker image (`commit-to-discord-image`).
* `make run`: Runs the Docker container (`commit-to-discord`) in detached mode. Stops existing container first.
* `make start`: Alias for `run`.
* `make stop`: Stops and removes the Docker container.
* `make clean`: Stops and removes the container, then removes the Docker image.
* `make logsf`: Follows the logs of the running container.
* `make exec`: Attaches a shell to the running container for debugging.

## How It Works

The `commit_watcher.py` script performs the following steps:

1. Loads configuration from environment variables.
2. Initializes by fetching the latest commit for each branch of the specified repositories if `last_commits.json` is empty or a repo/branch is new.
3. Enters a loop, polling at the defined `POLL_INTERVAL_SECONDS`:
    a.  For each repository, it fetches all branches.
    b.  For each branch, it fetches the latest commits.
    c.  It compares these commits against the last known commit ID stored for that repository and branch (from `last_commits.json`).
    d.  If new commits are found, they are formatted into an embed.
    e.  A single Discord message is sent containing all new commits for that branch, with a title indicating the number of new commits and linking to a comparison view if multiple commits are new.
    f.  The `last_commits.json` file is updated with the newest commit ID for that branch.

## Logging

Log level can be controlled via the `LOG_LEVEL` environment variable (e.g., `INFO`, `DEBUG`, `WARNING`). Logs are output in color to the console (Docker logs) with timestamps in Eastern Time.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue.
