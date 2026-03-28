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
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level configuration (read from env vars — never hardcoded)
# ---------------------------------------------------------------------------
OBSIDIAN_BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")
OBSIDIAN_API_KEY = os.environ.get("OBSIDIAN_API_KEY", "")
OBSIDIAN_TIMEOUT = 10.0     # seconds — applied to every API call
VAULT_INGEST_MAX_BYTES = int(os.environ.get("VAULT_INGEST_MAX_BYTES", "50000"))

# ---------------------------------------------------------------------------
# Vault QA (Sprint 11) — RAG context assembly constants
# ---------------------------------------------------------------------------
VAULT_QA_NOTE_MAX_CHARS = 3000    # per-note excerpt cap
VAULT_QA_TOTAL_MAX_CHARS = 12000  # Context Guard ceiling (standalone CLI)
VAULT_QA_PROMPT_MAX_CHARS = 6000  # Context Guard ceiling when called from run_agent()


class VaultQASource(TypedDict):
    """A single vault note retrieved as part of a Vault QA context bundle."""
    path: str       # vault-relative path, e.g. '20 - AREAS/23 - AI/note.md'
    wikilink: str   # Obsidian wikilink, e.g. '[[note]]'
    excerpt: str    # Note content truncated to VAULT_QA_NOTE_MAX_CHARS


class VaultQAResult(TypedDict):
    """Result of a vault_qa() RAG retrieval loop."""
    query: str
    sources: list          # list[VaultQASource]
    context_text: str      # Formatted, Context-Guard-capped text for prompt injection
    total_chars: int       # len(context_text)


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

    def search_vault(self, query: str, limit: int = 5) -> list:
        """Search the vault using the Obsidian Local REST API simple search endpoint.

        Calls GET /search/simple/?query=<encoded>&contextLength=100 and returns
        the top `limit` vault-relative paths ordered by descending score.

        Args:
            query: Plain-text search query. Must not be empty.
            limit: Maximum number of results to return. Clamped to [1, 10].

        Returns:
            list[str] of vault-relative paths (highest score first).
            Returns [] if no results found.

        Raises:
            ValueError:   If query is empty or whitespace.
            RuntimeError: If the Obsidian API returns an HTTP error.
            urllib.error.URLError: On connection-level failures.
        """
        if not query or not query.strip():
            raise ValueError("search_vault: query must not be empty.")
        limit = min(max(1, limit), 10)  # clamp to [1, 10]
        encoded_query = urllib.parse.quote(query.strip(), safe="")
        path = f"/search/simple/?query={encoded_query}&contextLength=100"
        _, body = self._make_request("GET", path)
        results = json.loads(body)
        paths = [
            r["filename"]
            for r in results
            if isinstance(r, dict) and "filename" in r
        ]
        logger.debug("search_vault: query=%r returned %d results", query, len(paths))
        return paths[:limit]


# ---------------------------------------------------------------------------
# vault_qa() — Standalone RAG retrieval function (Sprint 11)
# ---------------------------------------------------------------------------

def vault_qa(
    query: str,
    db_path: str = None,
    limit: int = 5,
    is_sensitive: bool = False,
    _max_chars: int = None,
) -> dict:
    """Perform a full RAG retrieval loop against the Obsidian vault.

    Sequence:
      1. Ping Obsidian — raise RuntimeError if not running.
      2. search_vault(query, limit) → ranked list of vault-relative paths.
      3. read_note(path) for each path; unreadable notes are skipped (WARNING).
      4. Truncate each note to VAULT_QA_NOTE_MAX_CHARS.
      5. Assemble context_text with '--- Source: [[X]] ---' headers.
      6. Apply Context Guard ceiling (VAULT_QA_TOTAL_MAX_CHARS or _max_chars).
      7. Audit log: action='VAULT_QA', rationale=query[:200] ONLY.

    SECURITY: Never log or store context_text externally.
              Use only in local LLM prompt context.
              audit_logs.rationale contains the query only — never note content.

    Args:
        query:        Search query (must not be empty).
        db_path:      Optional factory.db path for audit logging (Airlock NOT applied
                      to vault_root — this db_path IS workspace-scoped however).
        limit:        Max notes to retrieve (default 5, clamped to [1, 10]).
        is_sensitive: If True, callers must route synthesis through local Ollama only.
        _max_chars:   Internal override for Context Guard ceiling (for run_agent use).

    Returns:
        VaultQAResult dict with keys: query, sources, context_text, total_chars.

    Raises:
        ValueError:   If query is empty.
        RuntimeError: If Obsidian is not running.
    """
    max_chars = _max_chars if _max_chars is not None else VAULT_QA_TOTAL_MAX_CHARS

    bridge = ObsidianBridge()
    if not bridge.ping():
        raise RuntimeError(
            "vault_qa: Obsidian Local REST API is not running. "
            "Start Obsidian and enable the Local REST API plugin."
        )

    paths = bridge.search_vault(query, limit=limit)

    sources = []
    for path in paths:
        try:
            content = bridge.read_note(path)
        except Exception as exc:
            logger.warning("vault_qa: skipping unreadable note %r: %s", path, exc)
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        wikilink = f"[[{stem}]]"
        excerpt = content[:VAULT_QA_NOTE_MAX_CHARS]
        sources.append({"path": path, "wikilink": wikilink, "excerpt": excerpt})

    # Assemble context_text with Obsidian-style source headers
    sections = []
    for s in sources:
        sections.append(f"--- Source: {s['wikilink']} ---\n{s['excerpt']}")
    raw_context = "\n\n".join(sections)

    # Apply Context Guard ceiling
    context_text = raw_context[:max_chars]

    # Audit log — query only, NEVER note content
    if db_path:
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (action, rationale) VALUES (?, ?)",
                    (
                        "VAULT_QA",
                        f"Query: {query[:200]!r} | results={len(sources)}, chars={len(context_text)}",
                    ),
                )
                conn.commit()
        except Exception as audit_err:
            logger.warning("vault_qa: audit log failed (non-fatal): %s", audit_err)

    logger.info(
        "vault_qa: query=%r sources=%d context_chars=%d is_sensitive=%s",
        query, len(sources), len(context_text), is_sensitive,
    )

    return {
        "query": query,
        "sources": sources,
        "context_text": context_text,
        "total_chars": len(context_text),
    }
