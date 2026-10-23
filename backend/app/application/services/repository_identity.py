"""Canonical repository identities used to keep delivery facts and Git evidence aligned."""

from urllib.parse import urlparse


def github_repository_slug_from_git_url(repository_url: str) -> str | None:
    """Return a case-normalized GitHub ``owner/repository`` identity for supported Git URLs."""
    parsed = urlparse(repository_url.strip())
    if parsed.scheme not in {"https", "ssh"} or (parsed.hostname or "").casefold() != "github.com":
        return None
    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) != 2:
        return None
    owner, repository = segments
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        return None
    return f"{owner}/{repository}".casefold()


def github_repository_matches(*, repository_url: str, repository_slug: str) -> bool:
    return github_repository_slug_from_git_url(repository_url) == repository_slug.strip().strip("/").casefold()
