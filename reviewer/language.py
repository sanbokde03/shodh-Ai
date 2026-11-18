"""Controlled English and a finite, exact routing language (integer ticket fields)."""

import ast
import itertools
import math
import operator
import re
from fractions import Fraction

from .contracts import Unsupported

UNITS = {"seconds": 1, "minutes": 60, "hours": 3600, "count": 1}
OPS = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt,
       "lte": operator.le, "gt": operator.gt, "gte": operator.ge}
SYMBOLS = {"=": "eq", "!=": "ne", "<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}
TOKEN = re.compile(r'\s*(>=|<=|!=|[=><()]|"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_-]*)')


def normalize(expr, fields):
    if type(expr) is bool:
        return expr
    op = expr["op"]
    if op in ("and", "or"):
        return {"op": op, "args": [normalize(e, fields) for e in expr["args"]]}
    if op == "not":
        return {"op": op, "arg": normalize(expr["arg"], fields)}
    name = expr["field"]
    if name not in fields:
        raise Unsupported(f"Unknown ticket field {name!r}")
    field = fields[name]
    if op == "missing":
        return dict(expr)
    value = expr["value"]
    result = dict(expr)
    if field["type"] == "number":
        if type(value) not in (int, float, Fraction):
            raise Unsupported(f"{name}: numeric comparison requires a number")
        unit = expr.get("unit", field["unit"])
        if (unit == "count") != (field["unit"] == "count"):
            raise Unsupported(f"{name}: incompatible units")
        result["value"] = Fraction(str(value)) * UNITS[unit] / UNITS[field["unit"]]
    else:
        if "unit" in expr or op not in ("eq", "ne"):
            raise Unsupported(f"{name}: unsupported comparison or unit")
        if field["type"] == "boolean" and type(value) is not bool:
            raise Unsupported(f"{name}: expected a boolean")
        if field["type"] == "enum" and (type(value) is not str or value not in field["values"]):
            raise Unsupported(f"{name}: value outside declared enum")
    result.pop("unit", None)
    return result


class Parser:
    def __init__(self, text):
        self.tokens = []
        pos = 0
        text = text.strip()
        while pos < len(text):
            match = TOKEN.match(text, pos)
            if not match:
                raise Unsupported(f"Unsupported source text at {text[pos:pos + 40]!r}")
            self.tokens.append(match[1])
            pos = match.end()
        self.i = 0

    def take(self, value=None):
        if self.i >= len(self.tokens):
            raise Unsupported("Unexpected end of source requirement")
        token = self.tokens[self.i]
        if value is not None and token.upper() != value:
            raise Unsupported(f"Expected {value}, found {token}")
        self.i += 1
        return token

    def peek(self, value):
        return self.i < len(self.tokens) and self.tokens[self.i].upper() == value

    def expression(self, level=0):
        if level > 24:
            raise Unsupported("Source expression too deeply nested")
        parts = [self.conjunction(level)]
        while self.peek("OR"):
            self.take()
            parts.append(self.conjunction(level))
        return parts[0] if len(parts) == 1 else {"op": "or", "args": parts}

    def conjunction(self, level):
        parts = [self.atom(level)]
        while self.peek("AND"):
            self.take()
            parts.append(self.atom(level))
        return parts[0] if len(parts) == 1 else {"op": "and", "args": parts}

    def atom(self, level):
        if self.peek("NOT"):
            self.take()
            return {"op": "not", "arg": self.atom(level + 1)}
        if self.peek("("):
            self.take()
            expr = self.expression(level + 1)
            self.take(")")
            return expr
        name = self.take()
        if self.peek("IS"):
            self.take()
            self.take("MISSING")
            return {"op": "missing", "field": name}
        symbol = self.take()
        if symbol not in SYMBOLS:
            raise Unsupported(f"Unsupported comparison {symbol}")
        token = self.take()
        try:
            import json
            value = json.loads(token, parse_float=Fraction)
        except ValueError as exc:
            raise Unsupported("Values must be numbers, true/false, or double-quoted strings") from exc
        expr = {"op": SYMBOLS[symbol], "field": name, "value": value}
        if self.i < len(self.tokens) and self.tokens[self.i] in UNITS:
            expr["unit"] = self.take()
        return expr


def _parse_formal_source(text, fields):
    p = Parser(text)
    if p.peek("OTHERWISE"):
        p.take()
        p.take("THEN")
        expr = True
    else:
        keyword = p.take().upper()
        if keyword not in ("IF", "WHEN"):
            raise Unsupported("Source must use IF/WHEN ... THEN ... or OTHERWISE THEN ...")
        expr = p.expression()
        p.take("THEN")
    route = p.take()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", route) or p.i != len(p.tokens):
        raise Unsupported("Unsupported route or trailing source text")
    return normalize(expr, fields), route


def parse_source(text, fields):
    try:
        return _parse_formal_source(text, fields)
    except Unsupported:
        from .english import parse_english_source
        return parse_english_source(text, fields)


def evaluate(expr, ticket):
    if type(expr) is bool:
        return expr
    op = expr["op"]
    if op == "and":
        return all(evaluate(e, ticket) for e in expr["args"])
    if op == "or":
        return any(evaluate(e, ticket) for e in expr["args"])
    if op == "not":
        return not evaluate(expr["arg"], ticket)
    value = ticket.get(expr["field"])
    if op == "missing":
        return value is None
    if value is None:
        return op == "ne"
    return OPS[op](value, expr["value"])


def representatives(expressions, fields, max_tickets=100000):
    thresholds = {name: set() for name, f in fields.items() if f["type"] == "number"}

    def visit(e):
        if type(e) is bool:
            return
        if e["op"] in ("and", "or"):
            for child in e["args"]:
                visit(child)
        elif e["op"] == "not":
            visit(e["arg"])
        elif e["op"] != "missing" and e["field"] in thresholds:
            thresholds[e["field"]].add(e["value"])

    for expression in expressions:
        visit(expression)
    domains = []
    for name, field in fields.items():
        if field["type"] == "number":
            values = {0}
            for threshold in thresholds[name]:
                values.update((math.floor(threshold) - 1, math.floor(threshold),
                               math.ceil(threshold), math.ceil(threshold) + 1))
            domain = sorted(values)
        elif field["type"] == "boolean":
            domain = [False, True]
        else:
            domain = sorted(field["values"])
        domains.append([ABSENT, None] + domain)
    size = math.prod(map(len, domains))
    if size > max_tickets:
        raise Unsupported(f"Exhaustive partition needs {size} tickets; limit is {max_tickets}; no sampling used")
    return ({name: value for name, value in zip(fields, row) if value is not ABSENT}
            for row in itertools.product(*domains)), size


ABSENT = object()


class Code:
    """Inspect and interpret a restricted AST. Never compile, eval, or exec snippets."""

    def __init__(self, source, fields):
        self.fields = fields
        self.expressions = []
        self.tree = ast.parse(source)
        if sum(1 for _ in ast.walk(self.tree)) > 1500:
            raise Unsupported("Snippet AST exceeds 1500 nodes")
        if len(self.tree.body) != 1 or not isinstance(self.tree.body[0], ast.FunctionDef):
            raise Unsupported("Snippet must contain exactly def route(ticket)")
        fn = self.tree.body[0]
        if (fn.name != "route" or len(fn.args.args) != 1 or fn.args.args[0].arg != "ticket"
                or fn.args.posonlyargs or fn.args.kwonlyargs or fn.args.defaults
                or fn.args.kwarg or fn.args.vararg or fn.decorator_list or fn.returns
                or fn.args.args[0].annotation or fn.type_params):
            raise Unsupported("Only plain def route(ticket) is supported")
        self.body = fn.body
        self.decision_lines = {n.lineno for n in ast.walk(fn) if isinstance(n, ast.If)}
        self._statements(self.body)

    def field(self, node):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "ticket" and isinstance(node.slice, ast.Constant)):
            name = node.slice.value
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and isinstance(node.func.value, ast.Name) and node.func.value.id == "ticket"
              and node.func.attr == "get" and len(node.args) == 1 and not node.keywords
              and isinstance(node.args[0], ast.Constant)):
            name = node.args[0].value
        else:
            raise Unsupported("Code conditions must compare ticket['field'] or ticket.get('field') with constants")
        if name not in self.fields:
            raise Unsupported(f"Unknown code field {name!r}")
        return name

    @staticmethod
    def literal(node):
        if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) in (int, float):
            return -node.operand.value
        raise Unsupported("Code comparison requires a literal")

    def condition(self, node):
        if isinstance(node, ast.Constant) and type(node.value) is bool:
            return node.value
        if isinstance(node, ast.BoolOp):
            return {"op": "and" if isinstance(node.op, ast.And) else "or", "args": [self.condition(v) for v in node.values]}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return {"op": "not", "arg": self.condition(node.operand)}
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            field = self.field(node.left)
            value = self.literal(node.comparators[0])
            op = node.ops[0]
            if isinstance(op, (ast.Is, ast.IsNot)) and value is None:
                expr = {"op": "missing", "field": field}
                return {"op": "not", "arg": expr} if isinstance(op, ast.IsNot) else expr
            mapping = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "lte", ast.Gt: "gt", ast.GtE: "gte"}
            if type(op) in mapping:
                expr = normalize({"op": mapping[type(op)], "field": field, "value": value}, self.fields)
                if type(value) is float:
                    expr["value"] = Fraction.from_float(value)
                return expr
        raise Unsupported(f"Unsupported Python condition at line {getattr(node, 'lineno', '?')}")

    def _statements(self, statements):
        for node in statements:
            if isinstance(node, ast.If):
                self.expressions.append(self.condition(node.test))
                self._statements(node.body)
                self._statements(node.orelse)
            elif isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and type(node.value.value) is str:
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", node.value.value):
                    raise Unsupported("Code returns an invalid route")
            else:
                raise Unsupported(f"Unsupported Python statement at line {getattr(node, 'lineno', '?')}")

    def _condition(self, node, ticket):
        # Python subscripting missing keys and ordering None raise, unlike policy predicates.
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._condition(v, ticket) for v in node.values)
            return any(self._condition(v, ticket) for v in node.values)
        if isinstance(node, ast.UnaryOp):
            return not self._condition(node.operand, ticket)
        if isinstance(node, ast.Constant):
            return node.value
        name = self.field(node.left)
        if isinstance(node.left, ast.Subscript) and name not in ticket:
            raise KeyError(name)
        left, right = ticket.get(name), self.literal(node.comparators[0])
        op = node.ops[0]
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        mapping = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
                   ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
        return mapping[type(op)](left, right)

    def route(self, ticket):
        trace = []

        def block(statements):
            for node in statements:
                trace.append(node.lineno)
                if isinstance(node, ast.Return):
                    return node.value.value
                branch = node.body if self._condition(node.test, ticket) else node.orelse
                result = block(branch)
                if result is not None:
                    return result
            return None

        try:
            return block(self.body), trace
        except (TypeError, KeyError) as exc:
            return f"ERROR:{type(exc).__name__}", trace
