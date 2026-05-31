"""Doctrine guard (CONSTITUTION.md, ARCHITECTURE.md).

The verify/ package must import NO LLM client and NO network code. The grader
cannot be the thing it grades. This test fails the build if anyone ever wires a
model or a socket into a verifier.
"""

from __future__ import annotations

import ast
import pathlib

import myAIstory.verify as verify_pkg

FORBIDDEN_ROOTS = {
    "ollama", "openai", "anthropic", "transformers", "torch", "llama_cpp",
    "requests", "httpx", "aiohttp", "urllib", "urllib3", "http", "socket",
}


def _verify_package_files() -> list[pathlib.Path]:
    pkg_dir = pathlib.Path(verify_pkg.__file__).parent
    return sorted(pkg_dir.glob("*.py"))


def _imported_roots(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute imports only
                roots.add(node.module.split(".")[0])
    return roots


def test_verify_package_imports_no_llm_or_network():
    offenders: dict[str, set[str]] = {}
    for path in _verify_package_files():
        bad = _imported_roots(path) & FORBIDDEN_ROOTS
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"verify/ imported forbidden modules: {offenders}"


def test_verify_package_has_expected_gates():
    # Sanity: the five v1 gates are exported.
    for name in (
        "verify_seed", "verify_bible",
        "verify_continuity", "verify_structure", "verify_speaker",
    ):
        assert hasattr(verify_pkg, name), f"missing gate: {name}"
