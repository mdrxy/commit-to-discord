# commit-to-discord

See the module docstring for info.

## Environment Variables

Ensure these are set in `.env` before running!

- **GITHUB_API_URL**: The URL to fetch the latest commits from the GitHub API.  
  _Example_: `https://api.github.com/repos/AzuraCast/AzuraCast/commits`

- **DISCORD_WEBHOOK_URL**: The Discord webhook URL where commit notifications will be sent.

- **GITHUB_TOKEN** (optional): A GitHub Personal Access Token can optionally be used for higher rate limits.

- **POLL_INTERVAL_SECONDS** (optional, default is 2 minutes): The number of seconds to wait between each fetch.

## Usage

You can use the provided Makefile (by running `make`) or the following commands:

```bash
# Build the container
docker build -t commit-watcher-image .

# Run
docker run -d --restart unless-stopped --name commit-watcher commit-watcher-image
```

If using `make`, you can run the container with podman by setting `DOCKER_TOOL=podman` before running.
