"""Bounded everyday-English patterns; never infer missing cutoffs or approvals."""

import json
import re
from fractions import Fraction

from .contracts import Unsupported
from .language import Parser, SYMBOLS, UNITS, normalize


def field_label(name):
    return "waiting time" if name == "waiting" else name.replace("_", " ")


def destination(text):
    text = text.strip()
    if text.startswith('"'):
        try:
            route = json.loads(text)
        except ValueError:
            route = None
    else:
        text = re.sub(r"^the\s+", "", text, flags=re.I)
        aliases = {"manual review": "manual", "priority queue": "priority", "normal queue": "normal", "escalation": "escalation"}
        route = aliases.get(text.casefold(), text)
    if not isinstance(route, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", route):
        raise Unsupported('Name a destination such as manual review, priority queue, escalation or normal queue; quote an exact custom route name')
    return route


def action_route(text):
    if re.fullmatch(r"escalate(?:\s+(?:the\s+)?tickets?)?", text, re.I):
        return "escalation"
    action = re.fullmatch(r"(?:send|route)\s+(?:(?:the|a)\s+)?(?:tickets?|it|them)\s+(?:to|for)\s+(.+)", text, re.I)
    return destination(action[1] if action else text)


def split_clause(text, markers):
    quoted, escaped, depth = False, False, 0
    lowered = text.casefold()
    for i, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if quoted and char == "\\":
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
        if quoted:
            continue
        depth += (char == "(") - (char == ")")
        if depth == 0:
            for marker in markers:
                if lowered.startswith(marker, i):
                    return text[:i].strip(), text[i + len(marker):].strip()
    raise Unsupported("Separate the condition and action with a comma or 'then', for example: If category is missing, send the ticket for manual review")


class EnglishCondition(Parser):
    def __init__(self, text, fields):
        super().__init__(text)
        self.fields = fields

    def words(self, phrase):
        tokens = phrase.split()
        if [t.casefold() for t in self.tokens[self.i:self.i + len(tokens)]] == tokens:
            self.i += len(tokens)
            return True
        return False

    def field(self):
        if self.peek("THE") and self.tokens[self.i] not in self.fields:
            self.take()
        matches = []
        for name in self.fields:
            for alias in {name, name.replace("_", " "), field_label(name)}:
                parts = alias.casefold().split()
                if [t.casefold() for t in self.tokens[self.i:self.i + len(parts)]] == parts:
                    matches.append((len(parts), name))
        if not matches:
            raise Unsupported("Name a declared ticket detail, such as waiting time, category or urgent")
        longest = max(length for length, _ in matches)
        if longest == 1 and self.tokens[self.i] in self.fields:
            return self.take()
        names = {name for length, name in matches if length == longest}
        if len(names) != 1:
            raise Unsupported("This ticket-detail name is ambiguous; use its exact field name")
        self.i += longest
        return names.pop()

    def atom(self, level):
        if level > 24:
            raise Unsupported("The rule has too many nested conditions")
        if self.words("not"):
            return {"op": "not", "arg": self.atom(level + 1)}
        if self.peek("("):
            self.take()
            expr = self.expression(level + 1)
            self.take(")")
            return expr
        subject = self.words("a ticket is") or self.words("the ticket is") or self.words("ticket is")
        negated = subject and self.words("not")
        name = self.field()
        descriptor = self.fields[name]
        if descriptor["type"] == "boolean" and (self.i == len(self.tokens) or self.peek("AND") or self.peek("OR") or self.peek(")")):
            expr = {"op": "eq", "field": name, "value": True}
            return {"op": "not", "arg": expr} if negated else expr
        if negated:
            raise Unsupported("Use 'not' with an explicit condition for this ticket detail")
        self.words("is")
        if self.words("missing"):
            return {"op": "missing", "field": name}
        if self.words("not missing"):
            return {"op": "not", "arg": {"op": "missing", "field": name}}
        op = "eq"
        comparisons = (("not equal to", "ne"), ("at least", "gte"), ("at most", "lte"),
                       ("more than", "gt"), ("greater than", "gt"), ("less than", "lt"),
                       ("equal to", "eq"), ("equals", "eq"), ("exactly", "eq"), ("not", "ne"))
        compared = False
        for phrase, operator in comparisons:
            if self.words(phrase):
                op = operator
                compared = True
                break
        if self.i < len(self.tokens) and self.tokens[self.i] in SYMBOLS:
            if compared:
                raise Unsupported("Use one comparison for each ticket detail")
            op = SYMBOLS[self.take()]
        token = self.take()
        if descriptor["type"] == "number":
            if not re.fullmatch(r"-?\d+(?:\.\d+)?", token):
                raise Unsupported(f"Give a numeric cutoff for {field_label(name)}; wording such as 'too long' is not defined")
            value = Fraction(token)
        elif descriptor["type"] == "boolean":
            if token.casefold() not in ("true", "false", "yes", "no"):
                raise Unsupported(f"Say whether {field_label(name)} is true or false")
            value = token.casefold() in ("true", "yes")
        else:
            value = json.loads(token) if token.startswith('"') else token
        expr = {"op": op, "field": name, "value": value}
        if self.i < len(self.tokens):
            unit = self.tokens[self.i].casefold()
            unit = unit + "s" if unit in ("second", "minute", "hour") else unit
            if unit in UNITS:
                self.take()
                expr["unit"] = unit
        for phrase, operator in (("or more", "gte"), ("or less", "lte"), ("or fewer", "lte")):
            if self.words(phrase):
                if op != "eq" or descriptor["type"] != "number":
                    raise Unsupported("Use one numeric comparison, such as 'at least 30 minutes'")
                expr["op"] = operator
                break
        return expr


def parse_english_source(text, fields):
    text = text.strip().removesuffix(".").strip()
    default = re.fullmatch(r"for\s+all\s+(?:remaining|other)\s+tickets\s*,\s*(.+)", text, re.I)
    if default:
        return True, action_route(default[1])
    default = re.fullmatch(r"(?:send|route)\s+all\s+(?:remaining|other)\s+tickets\s+(?:to|for)\s+(.+)", text, re.I)
    if default:
        return True, destination(default[1])
    default = re.fullmatch(r"all\s+(?:remaining|other)\s+tickets\s+go\s+to\s+(.+)", text, re.I)
    if default:
        return True, destination(default[1])
    default = re.fullmatch(r"otherwise(?:\s*,\s*|\s+)(?:then\s+)?(.+)", text, re.I)
    if default:
        return True, action_route(default[1])
    conditional = re.match(r"(?:if|when)\s+(.+)", text, re.I)
    if conditional:
        condition, action = split_clause(conditional[1], (",", " then "))
        route = action_route(action)
    else:
        escalation = re.fullmatch(r"escalate\s+(?:the\s+)?tickets?\s+(.+)", text, re.I)
        if escalation:
            condition = re.sub(r"^(?:that have been|that are|which are|if|when)\s+", "", escalation[1], flags=re.I)
            route = "escalation"
        else:
            action, condition = split_clause(text, (" when ", " if "))
            route = action_route(action)
    parser = EnglishCondition(condition, fields)
    expr = parser.expression()
    if parser.i != len(parser.tokens):
        raise Unsupported("The whole condition could not be understood; clarify the extra wording or quote a multiword category")
    return normalize(expr, fields), route
