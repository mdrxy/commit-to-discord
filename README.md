# commit-to-discord

Monitors specified GitHub repositories for new commits and sends detailed notifications to a Discord webhook. The notifications are designed to mirror Discord's first-party GitHub embed style (achieved by appending `/github` to a Discord webhook from within GitHub).

## Key Features

* **Multi-Repository & Multi-Branch Monitoring:** Keep track of commits across several repositories and selected branches.
* **Persistent Tracking:** Remembers the last notified commit for each branch to avoid duplicates, even after restarts (using `last_commits.json`).
* **Configurable:** Set repository list, webhook URL, polling interval, and GitHub token via environment variables.
* **Containerized:** Easy to deploy and run using Docker or Podman, with `Makefile` targets for building, running, and management.
* **GitHub API Token Support:** Use a [GitHub Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens) for higher API rate limits or to access private repositories.

## Example Discord Notification

![Screenshot of an example Discord Notification using commit-to-discord](/img/example.png)

## Prerequisites

* [Docker](https://www.docker.com/) (or [Podman](https://podman.io/)) installed.
* A [Discord Webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) URL.
* Repositories to monitor on GitHub.

## Setup & Configuration

1. **Clone the repository**

    ```bash
    git clone https://github.com/mdrxy/commit-to-discord.git
    cd commit-to-discord
    ```

2. **Create an environment file:**
    Copy `.sample.env` to `.env`:

    ```bash
    cp .sample.env .env
    ```

3. **Fill in `.env` with your settings:**

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
      * Example: `dependabot/*,mdrxy/commit-to-discord:main` will ignore all `dependabot` branches in every repository and the `main` branch in `mdrxy/commit-to-discord`.
    * `LOG_LEVEL` (Optional): Set the logging level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`). Defaults to `INFO`.
    * `LOG_TZ` (Optional): Set the timezone for log timestamps. Defaults to UTC.

## Usage

The provided `Makefile` simplifies deployment operations. [(Install `make`)](https://www.gnu.org/software/make/)

* **Build and Run (Recommended):**

    ```bash
    make
    ```

    This will clean any previous instances, build the image, run the container in detached mode, and start following logs.

* **Using Podman:**
    It's assumed you're using Docker, but if you prefer Podman, you can set the `DOCKER_TOOL` environment variable to `podman` to seamlessly switch containerization tools:

    ```bash
    DOCKER_TOOL=podman make
    ```

### Manual Build Commands

* **Build the image:**

    ```bash
    docker build -t commit-to-discord-image .
    ```

* **Run the container:**

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

## Logging

Log level can be controlled via the `LOG_LEVEL` environment variable (e.g., `INFO`, `DEBUG`, `WARNING`). Logs are output in color to the console (Docker logs) with timestamps in Eastern Time.

## Development

### Local Development Setup

For local development without Docker:

1. **Install dependencies:**

   ```bash
   make setup-dev
   ```

   This installs all development dependencies and sets up pre-commit hooks.

2. **Run quality checks:**

   ```bash
   make check-all    # Run linting, type checking, and format checking
   make lint         # Run linting only
   make typecheck    # Run type checking only
   make format       # Format code
   ```

3. **Run the application locally:**

   ```bash
   # Copy and configure environment
   cp .sample.env .env
   # Edit .env with your settings
   
   # Run the application
   uv run python commit_watcher.py
   ```

### Available Make Targets

**Development:**

* `make setup-dev`: Install dev dependencies and set up pre-commit
* `make install-dev`: Install development dependencies only
* `make check-all`: Run all quality checks

**Code Quality:**

* `make lint`: Check code with ruff
* `make lint-fix`: Fix linting issues automatically
* `make format`: Format code with ruff
* `make format-check`: Check if code is properly formatted
* `make typecheck`: Run mypy type checking

**Pre-commit:**

* `make pre-commit-install`: Install pre-commit hooks
* `make pre-commit-run`: Run pre-commit on all files

**Docker (existing):**

* `make`: Full build and run workflow
* `make build`: Build Docker image
* `make run`: Run container
* `make stop`: Stop container
* `make clean`: Remove container and image

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue for any bugs or feature requests. I'll do my best to address them promptly.

### Development Workflow

1. Fork the repository
2. Run `make setup-dev` to set up your development environment
3. Make your changes
4. Run `make check-all` to ensure code quality
5. Commit your changes (pre-commit hooks will run automatically)
6. Push and create a pull request

The CI pipeline will automatically run linting, type checking, security checks, and Docker build tests on all pull requests.
