"""
obsidian_bridge.py — OpenClaw Obsidian Local REST API Client

Wraps the coddingtonbear/obsidian-local-rest-api community plugin
served at http://127.0.0.1:27123 (default).

Security invariants (SKILL.md — Obsidian Bridge Policy):
  - base_url MUST resolve to loopback — enforced at construction.
  - api_key is REQUIRED — empty string raises ValueError at construction.
  - append_to_note uses PATCH, NOT POST ?append=true.
  - list_notes parses a FLAT JSON ARRAY, not {"files": [...]} dict.
  - ping() uses GET /vault/, NOT GET /.
  - write_note validates vault_path for both ../ traversal AND absolute paths.
  - No requests/httpx — stdlib urllib.request only.
"""

import os
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level configuration (read from env vars — never hardcoded)
# ---------------------------------------------------------------------------
OBSIDIAN_BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")
OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
OBSIDIAN_TIMEOUT = 10.0     # seconds — applied to every API call
VAULT_INGEST_MAX_BYTES = int(os.environ.get("VAULT_INGEST_MAX_BYTES", "50000"))


def _validate_vault_path(vault_path: str) -> None:
    """Validate a vault-relative path for traversal and absolute-path attacks.

    Both checks are required (SKILL.md rule 13):
      - Relative traversal: ../evil.md passes startswith("..") check after normpath
      - Absolute path:     /etc/passwd does NOT start with ".." but must also be rejected
    """
    normed = os.path.normpath(vault_path)
    if normed.startswith(".."):
        raise ValueError(
            f"vault_path traversal detected (contains '..'): {vault_path!r}"
        )
    if os.path.isabs(normed):
        raise ValueError(
            f"vault_path must be relative (got absolute path): {vault_path!r}"
        )


class ObsidianBridge:
    """HTTP client for the Obsidian Local REST API plugin.

    All calls use urllib.request (stdlib only — no requests/httpx).
    API key is sent as 'Authorization: Bearer {api_key}' on every request.
    Spaces in vault paths are encoded as %20 (RFC 3986 path encoding, not +).
    """

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or OBSIDIAN_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else OBSIDIAN_API_KEY

        # Enforce localhost — SKILL.md rule 1
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError(
                f"ObsidianBridge: base_url must resolve to loopback. "
                f"Got hostname: {parsed.hostname!r}. "
                "This prevents OBSIDIAN_BASE_URL from bypassing the router.py security model."
            )

        # Enforce API key — SKILL.md rule 2
        if not self.api_key:
            raise ValueError(
                "OBSIDIAN_API_KEY is required. "
                "Set the env var or pass api_key= to ObsidianBridge(). "
                "An empty key causes 401 on all calls, silently masking as VAULT_WRITE_SKIPPED."
            )

    def _make_request(
        self,
        method: str,
        path: str,
        body: bytes = None,
        content_type: str = "application/json",
    ) -> tuple[int, str]:
        """Execute an HTTP request against the Local REST API.

        Args:
            method:       HTTP method (GET, PUT, PATCH, POST)
            path:         URL path (already encoded by caller)
            body:         Optional request body bytes
            content_type: Content-Type header value

        Returns:
            (status_code: int, response_body: str)

        Raises:
            RuntimeError: On non-2xx HTTP responses.
            urllib.error.URLError: On connection-level failures (re-raised by callers).
        """
        url = f"{self.base_url}{path}"
        headers = {
            # NOTE: %20 for spaces in path, NOT + (RFC 3986 path encoding — deliberate)
            "Authorization": f"Bearer {self.api_key}",
        }
        if body is not None:
            headers["Content-Type"] = content_type

        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=OBSIDIAN_TIMEOUT) as resp:
                status = resp.status
                response_body = resp.read().decode("utf-8", errors="replace")
                return status, response_body
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(
                f"Obsidian API {e.code} on {method} {path}: {body_text}"
            ) from e

    def ping(self) -> bool:
        """Check whether the Obsidian Local REST API plugin is reachable.

        Uses GET /vault/ — NOT GET / (root endpoint reliability varies by plugin version).
        Returns True on ANY HTTP response (including 401 — plugin running, key wrong).
        Returns False only on connection-level failure (urllib.error.URLError, timeout).
        Never propagates exceptions.
        """
        try:
            self._make_request("GET", "/vault/")
            return True
        except RuntimeError:
            # HTTP error (including 401) — plugin IS running
            return True
        except Exception:
            # Connection refused, timeout, etc. — plugin NOT running
            return False

    def read_note(self, vault_path: str) -> str:
        """Read a note's raw markdown content from the vault.

        Args:
            vault_path: Relative path within vault (e.g. '30 - RESOURCES/note.md')

        Returns:
            Raw markdown string.

        Raises:
            FileNotFoundError: If the note does not exist (404).
            RuntimeError: On other HTTP errors.
        """
        # URL-encode path: spaces → %20 (NOT +), safe="/" preserves separators
        encoded = urllib.parse.quote(vault_path, safe="/")
        try:
            _, body = self._make_request("GET", f"/vault/{encoded}")
            return body
        except RuntimeError as e:
            if "404" in str(e):
                raise FileNotFoundError(f"Note not found in vault: {vault_path!r}") from e
            raise

    def write_note(self, vault_path: str, content: str) -> None:
        """Create or overwrite a note in the vault (atomic via PUT).

        Args:
            vault_path: Relative path within vault.
            content:    Full markdown text to write.

        Raises:
            ValueError:     On path traversal or absolute path.
            RuntimeError:   On HTTP errors.
        """
        _validate_vault_path(vault_path)
        encoded = urllib.parse.quote(vault_path, safe="/")
        self._make_request(
            "PUT",
            f"/vault/{encoded}",
            body=content.encode("utf-8"),
            content_type="text/markdown",
        )
        logger.debug("write_note: wrote %d bytes to %s", len(content), vault_path)

    def append_to_note(self, vault_path: str, content: str) -> None:
        """Append content to an existing note, creating it if absent.

        Uses PATCH /vault/{path} — NOT POST ?append=true (that endpoint does not exist).
        Sends '\\n\\n{content}' as body; plugin appends to end of file.
        Falls back to write_note if note does not exist (PATCH returns 404).

        Args:
            vault_path: Relative path within vault.
            content:    Text to append.

        Raises:
            ValueError:   On path traversal or absolute path.
            RuntimeError: On HTTP errors other than 404.
        """
        _validate_vault_path(vault_path)
        encoded = urllib.parse.quote(vault_path, safe="/")
        append_body = f"\n\n{content}".encode("utf-8")
        try:
            self._make_request(
                "PATCH",
                f"/vault/{encoded}",
                body=append_body,
                content_type="text/markdown",
            )
        except RuntimeError as e:
            if "404" in str(e):
                # Note does not exist — create it instead
                logger.debug("append_to_note: note not found, creating: %s", vault_path)
                self.write_note(vault_path, content)
            else:
                raise

    def list_notes(self, folder: str = "") -> list:
        """List all notes under a vault folder.

        Args:
            folder: Relative folder path ('' for vault root).

        Returns:
            Flat list of path strings ['path/a.md', 'path/b.md', ...].
            NOTE: The plugin returns a flat JSON array, NOT {"files": [...], "folders": [...]}.
            Returns [] if folder does not exist (404).

        Raises:
            RuntimeError: On non-404 HTTP errors.
        """
        encoded = urllib.parse.quote(folder, safe="/")
        path = f"/vault/{encoded}/" if encoded else "/vault/"
        try:
            _, body = self._make_request("GET", path)
            data = json.loads(body)
            # Real plugin response: flat array of path strings
            if isinstance(data, list):
                return data
            # Defensive: if unexpected dict shape, extract any list values
            if isinstance(data, dict):
                for key in ("files", "notes", "paths"):
                    if isinstance(data.get(key), list):
                        return data[key]
            return []
        except RuntimeError as e:
            if "404" in str(e):
                return []
            raise

    def check_obsidian_health(self) -> dict:
        """Check Obsidian Local REST API health with latency measurement.

        Returns:
            {"status": "ok"|"down", "url": str, "latency_ms": int}
        """
        t0 = time.time()
        reachable = self.ping()
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "status": "ok" if reachable else "down",
            "url": self.base_url,
            "latency_ms": latency_ms if reachable else 0,
        }
