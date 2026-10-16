"""Utility and inspection functions for Storix E2E opaque-box test suite."""

import ast
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml  # type: ignore[import-untyped]


class CfnYamlLoader(yaml.SafeLoader):
    """Custom YAML loader supporting CloudFormation intrinsic functions."""
    pass


def _cfn_tag_constructor(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {f"!{suffix}": loader.construct_scalar(node)}
    elif isinstance(node, yaml.SequenceNode):
        return {f"!{suffix}": loader.construct_sequence(node)}
    elif isinstance(node, yaml.MappingNode):
        return {f"!{suffix}": loader.construct_mapping(node)}
    return None


CfnYamlLoader.add_multi_constructor("!", _cfn_tag_constructor)


def read_file(path: Path | str) -> str:
    """Read full text of a file in UTF-8."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def count_file_lines(path: Path | str) -> int:
    """Count total physical lines in a file."""
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def parse_ini_file(path: Path | str) -> Dict[str, str]:
    """Parse a PHP ini file format into a key-value dictionary."""
    content = read_file(path)
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            result[key.strip()] = val.strip()
    return result


def load_cfn_yaml(path: Path | str) -> Dict[str, Any]:
    """Load and parse a CloudFormation YAML template."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=CfnYamlLoader) or {}


def get_ast_tree(path: Path | str) -> ast.AST:
    """Parse a python file into an AST tree."""
    content = read_file(path)
    return ast.parse(content, filename=str(path))


def check_for_infinite_recursion(py_path: Path | str, func_name: str) -> bool:
    """Check if func_name contains an unconditional recursive call to itself."""
    tree = get_ast_tree(py_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name) and child.func.id == func_name:
                        return True
    return False


def find_files_by_pattern(root_dir: Path | str, pattern: str) -> List[Path]:
    """Find all paths matching pattern recursively, excluding node_modules/git."""
    root = Path(root_dir)
    results = []
    for p in root.rglob(pattern):
        parts = p.parts
        if "node_modules" in parts or ".git" in parts or "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        results.append(p)
    return results
