IMAGE_NAME = commit-to-discord-image
CONTAINER_NAME = commit-to-discord
LOG_LEVEL= info

# Default to Docker, allows for override to DOCKER_TOOL=podman
DOCKER_TOOL ?= docker

default: clean build run logsf

q: clean build run

exec:
	$(DOCKER_TOOL) exec -it $(CONTAINER_NAME) /bin/bash

logsf:
	$(DOCKER_TOOL) logs -f $(CONTAINER_NAME)

build:
	@echo "Building $(IMAGE_NAME)..."
	$(DOCKER_TOOL) build --quiet -t $(IMAGE_NAME) .

start: run

run: stop
	$(DOCKER_TOOL) run -d --restart unless-stopped \
		--name $(CONTAINER_NAME) \
		-e LOG_LEVEL=$(LOG_LEVEL) \
		$(IMAGE_NAME)

stop:
	@echo "Checking if container $(CONTAINER_NAME) is running..."
	@if [ "$$($(DOCKER_TOOL) ps -a -q -f name=$(CONTAINER_NAME))" != "" ]; then \
		echo "Stopping $(CONTAINER_NAME)..."; \
		$(DOCKER_TOOL) stop $(CONTAINER_NAME) > /dev/null; \
		echo "Removing the container $(CONTAINER_NAME)..."; \
		$(DOCKER_TOOL) rm -f $(CONTAINER_NAME) > /dev/null; \
	else \
		echo "No running container with name $(CONTAINER_NAME) found."; \
	fi

clean: stop
	@IMAGE_ID=$$($(DOCKER_TOOL) images -q $(IMAGE_NAME)); \
	if [ "$$IMAGE_ID" ]; then \
		echo "Removing image $(IMAGE_NAME) with ID $$IMAGE_ID..."; \
		$(DOCKER_TOOL) rmi $$IMAGE_ID > /dev/null; \
	else \
		echo "No image found with name $(IMAGE_NAME)."; \
	fi
