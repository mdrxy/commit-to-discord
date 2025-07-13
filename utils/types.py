"""Type definitions for the commit watcher."""

from __future__ import annotations

from typing import TypedDict


class CommitAuthor(TypedDict):
    """Represents the author of a commit."""

    email: str


class CommitDetails(TypedDict):
    """Represents the details of a commit."""

    author: CommitAuthor
    message: str


class AuthorDetails(TypedDict):
    """Represents the author details of a commit."""

    avatar_url: str
    login: str
    html_url: str


class Commit(TypedDict):
    """Represents a commit."""

    sha: str
    commit: CommitDetails
    author: AuthorDetails
    html_url: str
    author_username: str
    avatar_url: str | None
    repository: str
    branch: str
    id: str
    message: str
    url: str


class Branch(TypedDict):
    """Represents a branch."""

    name: str
