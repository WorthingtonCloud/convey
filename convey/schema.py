"""A small JSON Schema checker (the subset the skill's schemas use), standard library only.

Supports type, enum, required, properties, additionalProperties: false, items, minItems,
minLength, pattern and local $ref ("#/$defs/name"). Returns readable problems with their path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "schema"
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _is(value, t: str) -> bool:
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def check(value, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    root = root or schema
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return check(value, node, root, path)
    out = []
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} is not one of {schema['enum']}"]
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(value).__name__}"]
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{path}: missing {k!r}")
        props = schema.get("properties", {})
        for k, v in value.items():
            if k in props:
                out += check(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{path}: unknown field {k!r}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            out.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, v in enumerate(value):
                out += check(v, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            out.append(f"{path}: empty")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            out.append(f"{path}: {value!r} does not match {schema['pattern']}")
    return out


def validate(value, name: str) -> list[str]:
    """Check a document against skill/schema/<name>.schema.json."""
    return check(value, json.loads((HERE / f"{name}.schema.json").read_text()))
