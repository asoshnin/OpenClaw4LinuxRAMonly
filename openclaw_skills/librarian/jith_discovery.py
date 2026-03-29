"""
jith_discovery.py — LIB-01: Just-in-Time Help (JITH) Discovery
================================================================
Implements the JITH protocol: agents discover CLI flags and subcommands
at runtime via `--help` probing rather than relying on hardcoded flags
that may drift as OpenClaw evolves.

Security model:
  • shell=False on every subprocess.run() call — no shell injection.
  • Input sanitized against a hardcoded VERB_ALLOWLIST of root verbs.
  • Injection characters (`;`, `|`, `&`, etc.) always rejected.
  • Only OpenClaw-managed scripts can be targeted.

Caching model:
  • Results cached in JITH_CACHE_PATH (from config.py).
  • Atomic write: write .tmp → os.replace() — safe on W540.
  • Invalidated when `--version` output changes.
  • 24-hour TTL per cache entry.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap import path so this works both installed and run directly
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.config import WORKSPACE_ROOT  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache path
# ---------------------------------------------------------------------------
JITH_CACHE_PATH: Path = WORKSPACE_ROOT / "jith_cache.json"
JITH_CACHE_TTL_SECONDS: int = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Known OpenClaw CLI entry-points (script path → list of root verbs)
# This is the SECURITY ALLOWLIST — only these scripts may be targeted.
# ---------------------------------------------------------------------------
_SCRIPT_MAP: dict[str, Path] = {
    "architect": _REPO_ROOT / "openclaw_skills" / "architect" / "architect_tools.py",
    "librarian": _REPO_ROOT / "openclaw_skills" / "librarian" / "librarian_ctl.py",
    "sync-backlog": _REPO_ROOT / "openclaw_skills" / "librarian" / "sync_backlog.py",
    "mermaid": _REPO_ROOT / "openclaw_skills" / "mermaid_pipeline.py",
}

# Allowlisted top-level OpenClaw verbs (the first element of a capability path)
VERB_ALLOWLIST: frozenset[str] = frozenset(_SCRIPT_MAP.keys())

# ---------------------------------------------------------------------------
# Characters that are never allowed in any argument (injection guard)
# ---------------------------------------------------------------------------
_FORBIDDEN_CHARS_RE = re.compile(r"[;&|><`$\\\n\r\t]")


# ---------------------------------------------------------------------------
# Parsed capability structure
# ---------------------------------------------------------------------------
# {
#   "subcommands": {"run": "Run a task attributed to a registered agent", ...},
#   "options":     {"--help": {"short": "-h", "description": "...", "takes_value": False}, ...},
#   "positionals": ["db_path", "agent_id", "task"],
# }
CapabilityMap = dict[str, Any]


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

def _sanitize_args(args: list[str]) -> list[str]:
    """
    Validate every element of *args* against injection guards.

    Rules:
      1. The first arg must appear in VERB_ALLOWLIST.
      2. No arg may contain characters from _FORBIDDEN_CHARS_RE.
      3. No arg may attempt path traversal (../).

    Returns sanitized list or raises ValueError.
    """
    if not args:
        raise ValueError("JITH: args list must not be empty.")

    verb = args[0]
    if verb not in VERB_ALLOWLIST:
        raise ValueError(
            f"JITH Security: '{verb}' is not in the allowlist {sorted(VERB_ALLOWLIST)}. "
            "Possible [EPISTEMIC_GAP]: this verb does not exist in OpenClaw yet."
        )

    for a in args:
        if _FORBIDDEN_CHARS_RE.search(a):
            raise ValueError(
                f"JITH Security: Injection character detected in argument '{a}'. "
                "Command rejected."
            )
        if ".." in a:
            raise ValueError(
                f"JITH Security: Path traversal detected in argument '{a}'. "
                "Command rejected."
            )

    return args


# ---------------------------------------------------------------------------
# Help text parser
# ---------------------------------------------------------------------------

def _parse_help_output(help_text: str) -> CapabilityMap:
    """
    Parse the output of `python3 <script> [subcommand] --help` into a
    structured CapabilityMap using regex tokenization.

    Handles argparse's standard formatting, including multi-line
    descriptions and nested subcommand listings.
    """
    result: CapabilityMap = {
        "subcommands": {},
        "options": {},
        "positionals": [],
    }

    lines = help_text.splitlines()

    # --- Subcommand pattern: `  verb    Description text`
    # argparse renders these in a positional arguments block with
    # either curly-brace listing or indented sub-names.
    subcommand_block = False
    option_block = False
    current_flag: str | None = None

    # Regex patterns
    _sub_in_braces = re.compile(r"\{([^}]+)\}")           # {a,b,c} listing
    _option_line = re.compile(
        r"^\s{1,4}(-\w),?\s+(--[\w-]+)(?:\s+\S+)?\s*(.*)?$"
    )  # -h, --help [VALUE]  description
    _long_only = re.compile(
        r"^\s{1,4}(--[\w-]+)(?:\s+\S+)?\s*(.*)?$"
    )  # --flag [VALUE]   description
    _positional_line = re.compile(r"^\s{2,6}([a-z_][a-z_0-9]*)\s*(.*)?$")
    _takes_value = re.compile(r"--[\w-]+\s+[A-Z_]{2,}")   # --flag VALUE

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect section headers
        if re.match(r"^positional arguments:", stripped, re.IGNORECASE):
            subcommand_block = True
            option_block = False
            i += 1
            continue
        if re.match(r"^options?:", stripped, re.IGNORECASE):
            option_block = True
            subcommand_block = False
            i += 1
            continue
        if re.match(r"^usage:", stripped, re.IGNORECASE):
            subcommand_block = False
            option_block = False
            # Extract {subcommands} from usage line if present
            m = _sub_in_braces.search(line)
            if m:
                for sub in m.group(1).split(","):
                    sub = sub.strip()
                    if sub and not sub.startswith("-"):
                        result["subcommands"].setdefault(sub, "")
            i += 1
            continue

        # Blank lines reset context
        if not stripped:
            current_flag = None
            i += 1
            continue

        # --- Options block ---
        if option_block:
            # Short + long: `  -h, --help   description`
            m = _option_line.match(line)
            if m:
                short_flag, long_flag, desc = m.group(1), m.group(2), (m.group(3) or "").strip()
                takes_val = bool(_takes_value.search(line))
                result["options"][long_flag] = {
                    "short": short_flag,
                    "description": desc,
                    "takes_value": takes_val,
                }
                current_flag = long_flag
            else:
                # Long only: `  --flag VALUE  description`
                m2 = _long_only.match(line)
                if m2:
                    long_flag, desc = m2.group(1), (m2.group(2) or "").strip()
                    takes_val = bool(_takes_value.search(line))
                    result["options"][long_flag] = {
                        "short": None,
                        "description": desc,
                        "takes_value": takes_val,
                    }
                    current_flag = long_flag
                elif current_flag and line.startswith("  ") and stripped:
                    # Continuation line — append to last flag's description
                    result["options"][current_flag]["description"] += " " + stripped

        # --- Positional/subcommand block ---
        elif subcommand_block:
            # Named subcommand: `  {a,b,c}` or `  verb   description`
            m = _sub_in_braces.search(line)
            if m:
                for sub in m.group(1).split(","):
                    sub = sub.strip()
                    if sub:
                        result["subcommands"].setdefault(sub, "")
            else:
                # Individual `  verb   description` entry
                pm = _positional_line.match(line)
                if pm:
                    name, desc = pm.group(1).strip(), (pm.group(2) or "").strip()
                    if name in result["subcommands"]:
                        result["subcommands"][name] = desc
                    elif not name.startswith("{"):
                        # Could be a positional arg (not a subcommand name)
                        # Distinguish: subcommand if it was already seeded from usage
                        if name in result.get("subcommands", {}):
                            result["subcommands"][name] = desc
                        else:
                            # Treat as positional
                            if name not in result["positionals"]:
                                result["positionals"].append(name)

        i += 1

    return result


# ---------------------------------------------------------------------------
# Core discovery function
# ---------------------------------------------------------------------------

def get_cli_capabilities(args: list[str]) -> CapabilityMap:
    """
    Discover the CLI capabilities for the given *args* path.

    Args:
        args: A list specifying the tool path, e.g.
              ['architect']          → architect_tools.py --help
              ['architect', 'run']   → architect_tools.py run --help
              ['librarian', 'init']  → librarian_ctl.py init --help

    Returns:
        A CapabilityMap dict with keys 'subcommands', 'options', 'positionals'.

    Raises:
        ValueError: If args fail security validation.
        RuntimeError: If the CLI invocation fails.
    """
    _sanitize_args(args)

    # Check cache first
    cached = _cache_get(args)
    if cached is not None:
        log.debug("JITH cache hit for %s", args)
        return cached

    # Resolve script
    verb = args[0]
    script_path = _SCRIPT_MAP[verb]
    cmd = [sys.executable, str(script_path)] + args[1:] + ["--help"]

    log.info("JITH probing: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,       # SECURITY: never use shell=True
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"JITH: CLI probe timed out for {args}")
    except FileNotFoundError as e:
        raise RuntimeError(f"JITH: Python interpreter not found: {e}") from e

    # argparse prints help to stdout for --help (exit code 0)
    # Some versions print to stderr; accept either.
    help_text = proc.stdout or proc.stderr
    if not help_text.strip():
        raise RuntimeError(
            f"JITH: No help output received for {args}. "
            f"Exit code: {proc.returncode}. "
            "[EPISTEMIC_GAP]: This CLI path may not exist or may not support --help."
        )

    capabilities = _parse_help_output(help_text)
    _cache_set(args, capabilities)
    return capabilities


def validate_invocation(args: list[str], flags: list[str]) -> None:
    """
    Validate that all *flags* are present in the discovered capabilities
    for *args*. Raises RuntimeError with an [EPISTEMIC_GAP] report if any
    flag is missing.

    Args:
        args:  Tool path, e.g. ['architect', 'vault-qa']
        flags: List of flags to verify, e.g. ['--query', '--limit']

    Raises:
        ValueError: On security violation.
        RuntimeError: With [EPISTEMIC_GAP] if any flag is undiscovered.
    """
    caps = get_cli_capabilities(args)
    known_flags = set(caps["options"].keys())
    known_subs = set(caps["subcommands"].keys())
    missing = []

    for flag in flags:
        if flag.startswith("--"):
            if flag not in known_flags:
                missing.append(flag)
        else:
            if flag not in known_subs:
                missing.append(flag)

    if missing:
        raise RuntimeError(
            f"[EPISTEMIC_GAP] validate_invocation: The following flags/subcommands "
            f"were NOT found in '{' '.join(args)}' capabilities: {missing}. "
            "The Librarian cannot safely execute this command. "
            "Reported to epistemic_backlog for future resolution."
        )


# ---------------------------------------------------------------------------
# Cache helpers — atomic write pattern
# ---------------------------------------------------------------------------

def _cache_key(args: list[str]) -> str:
    return "|".join(args)


def _load_cache() -> dict:
    """Load the cache file; return {} on any error."""
    if not JITH_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(JITH_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("JITH: cache file corrupt or unreadable, starting fresh.")
        return {}


def _save_cache(data: dict) -> None:
    """Atomically write *data* to JITH_CACHE_PATH."""
    JITH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=JITH_CACHE_PATH.parent, suffix=".tmp", prefix=".jith_cache_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp_path, JITH_CACHE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _get_version_fingerprint() -> str:
    """Run each known script with --version (or --help fallback) to build a fingerprint."""
    parts = []
    for verb, script in _SCRIPT_MAP.items():
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--version"],
                capture_output=True, text=True, timeout=5, shell=False,
            )
            parts.append(f"{verb}:{(proc.stdout or proc.stderr).strip()[:80]}")
        except Exception:
            parts.append(f"{verb}:unavailable")
    return "|".join(parts)


def _cache_get(args: list[str]) -> CapabilityMap | None:
    """Return cached capabilities or None if missing/stale/version-mismatch."""
    data = _load_cache()
    current_version = _get_version_fingerprint()

    if data.get("_version") != current_version:
        log.debug("JITH: version fingerprint changed — cache invalidated.")
        return None

    key = _cache_key(args)
    entry = data.get("entries", {}).get(key)
    if entry is None:
        return None

    age = time.time() - entry.get("timestamp", 0)
    if age > JITH_CACHE_TTL_SECONDS:
        log.debug("JITH: cache entry for %s expired (age=%.0fs).", args, age)
        return None

    return entry["capabilities"]


def _cache_set(args: list[str], capabilities: CapabilityMap) -> None:
    """Write capabilities to cache atomically."""
    data = _load_cache()
    current_version = _get_version_fingerprint()

    # Reset entries if version changed
    if data.get("_version") != current_version:
        data = {"_version": current_version, "entries": {}}

    data.setdefault("entries", {})[_cache_key(args)] = {
        "timestamp": time.time(),
        "capabilities": capabilities,
    }
    _save_cache(data)
    log.debug("JITH: cached capabilities for %s.", args)
