"""Validation of the JSON Schema vocabulary used by this application's contracts."""

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1_000_000


class Unsupported(ValueError):
    """Input cannot be fully verified in the declared language."""


def parse_json(raw):
    if len(raw) > MAX_BYTES:
        raise Unsupported(f"Input exceeds {MAX_BYTES} bytes; nothing was truncated")
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
        Unsupported(f"Non-finite JSON number: {value}")))


def load_json(path):
    with Path(path).open("rb") as stream:
        return parse_json(stream.read(MAX_BYTES + 1))


def validate(value, schema, root=None, path="$", depth=0):
    root = schema if root is None else root
    if depth > 40:
        raise Unsupported(f"{path}: nesting exceeds 40 levels")
    if "$ref" in schema:
        target = root
        for key in schema["$ref"].split("/")[1:]:
            target = target[key]
        return validate(value, target, root, path, depth + 1)
    if "anyOf" in schema:
        for alternative in schema["anyOf"]:
            try:
                validate(value, alternative, root, path, depth + 1)
                return
            except Unsupported:
                pass
        raise Unsupported(f"{path}: does not match a supported contract variant")
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "integer": int, "number": (int, float), "null": type(None)}
    if "type" in schema:
        expected = schema["type"]
        expected = expected if isinstance(expected, list) else [expected]
        if not any(isinstance(value, types[t]) and
                   (t not in ("integer", "number") or type(value) is not bool) for t in expected):
            raise Unsupported(f"{path}: expected {expected}")
    if isinstance(value, float) and not math.isfinite(value):
        raise Unsupported(f"{path}: non-finite number")
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        raise Unsupported(f"{path}: unexpected value {value!r}")
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= value.keys():
            raise Unsupported(f"{path}: missing required keys {set(schema['required']) - value.keys()}")
        if not schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", 10000):
            raise Unsupported(f"{path}: unsupported object size")
        for key, child in value.items():
            rule = schema.get("properties", {}).get(key, schema.get("additionalProperties", {}))
            if rule is False:
                raise Unsupported(f"{path}.{key}: unknown property")
            validate(child, {} if rule is True else rule, root, f"{path}.{key}", depth + 1)
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10000):
            raise Unsupported(f"{path}: unsupported array size")
        for i, child in enumerate(value):
            validate(child, schema.get("items", {}), root, f"{path}[{i}]", depth + 1)
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", MAX_BYTES):
            raise Unsupported(f"{path}: unsupported string size")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise Unsupported(f"{path}: invalid identifier")
    if type(value) in (int, float):
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise Unsupported(f"{path}: number outside contract")


def validate_bundle(bundle):
    validate(bundle, load_json(ROOT / "schemas/bundle.schema.json"))
    validate(bundle["fields"], {"type": "object", "additionalProperties": {}})
    for name, field in bundle["fields"].items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", name):
            raise Unsupported(f"Invalid field name {name!r}")
        if field["type"] == "enum" and len(set(field["values"])) != len(field["values"]):
            raise Unsupported(f"Duplicate enum values: {name}")


def unique(records, key="id"):
    values = [record[key] for record in records]
    if len(set(values)) != len(values):
        raise Unsupported(f"Duplicate {key} values")
