"""Bounded model calls and evidence validation, separate from deterministic truth."""

import hashlib
import copy
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Protocol

from .contracts import ROOT, Unsupported, validate

PROMPT = (ROOT / "reviewer/prompt.txt").read_text()
MODEL_SCHEMA = json.loads((ROOT / "schemas/model-report.schema.json").read_text())
MAX_RESPONSE = 65536


def response_schema(request):
    schema = copy.deepcopy(MODEL_SCHEMA)
    ids = [rule["id"] for rule in request["effective_rules"]]
    schema["properties"]["coverage"]["enum"] = [ids]
    schema["properties"]["claims"]["items"]["properties"]["rule_ref"]["enum"] = ids
    return schema


@dataclass(frozen=True)
class Config:
    model: str = "offline-fake"
    temperature: int = 0
    timeout_seconds: int = 5
    max_attempts: int = 2
    max_output_tokens: int = 2048
    max_request_bytes: int = 200000
    context_window: int = 32768
    thinking: bool | None = None


class ModelClient(Protocol):
    provenance: str

    def complete(self, request: dict, config: Config) -> str: ...


class FakeClient:
    provenance = "synthetic-fake; not evidence of real-model performance"

    def __init__(self, modes="ok"):
        self.modes = modes.split(",")
        self.calls = 0

    def complete(self, request, config):
        mode = self.modes[min(self.calls, len(self.modes) - 1)]
        self.calls += 1
        if mode == "timeout":
            raise TimeoutError("Injected fake-client timeout; no real waiting")
        if mode in ("malformed", "truncated"):
            return "not JSON" if mode == "malformed" else '{"coverage": ['
        if mode == "oversized":
            return " " * (MAX_RESPONSE + 1)
        claims = []
        for rule in request["effective_rules"]:
            evidence = rule["evidence"][-1]
            claims.append({"rule_ref": rule["id"], "judgment": "no_additional_issue",
                           **evidence, "explanation": "Synthetic response for contract tests only."})
        response = {"coverage": [r["id"] for r in request["effective_rules"]], "claims": claims}
        if mode == "invented" and claims:
            claims[0]["location"] = "invented/location"
        elif mode == "conflict":
            for claim in claims:
                claim["judgment"] = "equivalent"
        elif mode == "omit":
            response["coverage"] = []
        elif mode == "ambiguous" and claims:
            claims[0]["judgment"] = "ambiguous"
        elif mode != "ok":
            if mode not in ("invented", "conflict", "omit", "ambiguous"):
                raise Unsupported(f"Unknown fake mode {mode}")
        return json.dumps(response)


class OllamaClient:
    provenance = "live-local-ollama"

    def complete(self, request, config):
        payload = {"model": config.model, "stream": False, "format": response_schema(request),
                   "messages": [{"role": "system", "content": PROMPT},
                                {"role": "user", "content": json.dumps(request)}],
                   "options": {"temperature": config.temperature, "num_predict": config.max_output_tokens,
                               "num_ctx": config.context_window}}
        if config.thinking is not None:
            payload["think"] = config.thinking
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=config.timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise Unsupported("Model transport response exceeds byte limit")
        body = json.loads(raw)
        if type(body) is not dict or body.get("done") is not True or body.get("done_reason") not in (None, "stop"):
            raise Unsupported("Model response is incomplete")
        if type(body.get("message")) is not dict or type(body["message"].get("content")) is not str:
            raise Unsupported("Model transport has no message content")
        self.last_metadata = {k: body[k] for k in ("model", "created_at", "done_reason", "prompt_eval_count", "eval_count") if k in body}
        return body["message"]["content"]


def review_model(client, config, rules, evidence, findings, fields, bindings):
    request = {"effective_rules": rules, "evidence_inventory": evidence,
               "deterministic_findings": [],
               "field_contract": fields,
               "citation_scope": {ref: [{"artifact": a, "version": v, "location": loc} for a, v, loc in sorted(keys)]
                                  for ref, keys in bindings.items()}}
    schema = response_schema(request)
    encoded = json.dumps({"system": PROMPT, "request": request}, sort_keys=True).encode()
    info = {"client": client.provenance, "configuration": asdict(config),
            "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
            "response_schema_sha256": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
            "request_sha256": hashlib.sha256(encoded).hexdigest(), "request_bytes": len(encoded),
            "attempts": [], "calls": 0, "retries": 0}
    if not (1 <= config.max_attempts <= 3 and 1 <= config.timeout_seconds <= 120
            and 1 <= config.max_output_tokens <= 4096 and 1 <= config.max_request_bytes <= 500000
            and 4096 <= config.context_window <= 65536 and config.thinking in (None, False, True)):
        return info, ["Invalid model resource limits"], []
    if len(encoded) > config.max_request_bytes:
        return info, ["Model input exceeds byte limit; no input was truncated or sent"], []
    # Byte-fallback tokenizers use at most one token per UTF-8 byte; reserve framing and output.
    if len(encoded) > config.context_window - config.max_output_tokens - 1024:
        return info, ["Model input exceeds conservative context bound; no input was truncated or sent"], []
    expected = {r["id"] for r in rules}
    by_rule = {r["id"]: r for r in rules}
    allowed = {(e["artifact"], e["version"], e["location"]): e["quote"] for e in evidence}
    for attempt in range(config.max_attempts):
        attempt_request = request
        if info["attempts"]:
            attempt_request = {**request, "validation_feedback": info["attempts"][-1]["error"]}
        attempt_encoded = json.dumps({"system": PROMPT, "request": attempt_request}, sort_keys=True).encode()
        if len(attempt_encoded) > min(config.max_request_bytes, config.context_window - config.max_output_tokens - 1024):
            return info, ["Retry input exceeds resource bound; no input was truncated or sent"], []
        start = time.perf_counter()
        record = {"attempt": attempt + 1, "request_sha256": hashlib.sha256(attempt_encoded).hexdigest()}
        if "validation_feedback" in attempt_request:
            record["validation_feedback"] = attempt_request["validation_feedback"]
        info["calls"] += 1
        info["retries"] = attempt
        try:
            raw = client.complete(attempt_request, config)
            if hasattr(client, "last_metadata"):
                record["transport"] = client.last_metadata
            if type(raw) is not str or len(raw.encode()) > MAX_RESPONSE:
                raise Unsupported("Model output exceeds byte limit or is not text")
            record["response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
            record["response"] = raw
            result = json.loads(raw)
            validate(result, schema)
            if set(result["coverage"]) != expected or len(result["coverage"]) != len(expected):
                raise Unsupported("Model coverage does not exactly match effective requirements")
            if any(c["rule_ref"] not in expected for c in result["claims"]):
                raise Unsupported("Model claims invent rule references")
            ambiguities = []
            judgments = {}
            for claim in result["claims"]:
                key = (claim["artifact"], claim["version"], claim["location"])
                if key not in allowed or claim["quote"] not in allowed[key]:
                    raise Unsupported("Model cited invented evidence or an invalid quote")
                if key not in bindings[claim["rule_ref"]]:
                    raise Unsupported("Model attributed evidence to an unrelated or unbound rule")
                prior = judgments.setdefault(claim["rule_ref"], claim["judgment"])
                if prior != claim["judgment"]:
                    raise Unsupported("Model made conflicting claims for one rule")
                if claim["judgment"] == "equivalent" and any(
                        f.get("rule_ref") == claim["rule_ref"] and f["severity"] == "blocker" for f in findings):
                    raise Unsupported("Model equivalence claim conflicts with deterministic evidence")
                if claim["judgment"] == "ambiguous":
                    if by_rule[claim["rule_ref"]].get("interpretation") is not None:
                        raise Unsupported("Ambiguity claim contradicts a complete declared-language interpretation. Boolean grouping, comparisons, units and missing values are already defined. Recheck the supplied interpretation; return no ambiguity claim for settled syntax.")
                    ambiguities.append(claim)
            record["result"] = "validated"
            record["seconds"] = time.perf_counter() - start
            info["attempts"].append(record)
            return info, [], ambiguities
        except (ValueError, TimeoutError, OSError, KeyError, TypeError) as exc:
            record.update(result="rejected", error=f"{type(exc).__name__}: {exc}", seconds=time.perf_counter() - start)
            info["attempts"].append(record)
    return info, [info["attempts"][-1]["error"]], []
