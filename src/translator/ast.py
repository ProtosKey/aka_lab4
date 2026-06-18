"""
Lexer, parser, and AST node definitions for the minimal Lisp dialect.
(language.md §2–§4)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union


# ── AST nodes ────────────────────────────────────────────────────────────────

@dataclass
class IntLit:
    value: int

@dataclass
class StrLit:
    value: str          # the string content (without quotes)
    label: int = 0      # assigned by codegen: byte offset in data section

@dataclass
class VarRef:
    name: str

@dataclass
class Setq:
    name:  str
    value: "Expr"

@dataclass
class If:
    cond:  "Expr"
    then:  "Expr"
    else_: "Expr"

@dataclass
class Loop:
    cond: "Expr"
    body: list["Expr"]

@dataclass
class Progn:
    body: list["Expr"]

@dataclass
class DefFun:
    name:   str
    params: list[str]
    body:   list["Expr"]

@dataclass
class Call:
    callee: str
    args:   list["Expr"]

Expr = Union[IntLit, StrLit, VarRef, Setq, If, Loop, Progn, DefFun, Call]


# ── Lexer ─────────────────────────────────────────────────────────────────────

def tokenize(src: str) -> list[str]:
    """
    Return a flat list of tokens: '(', ')', integer strings, string literals,
    and identifiers.  Comments (';' to end of line) are stripped.
    """
    tokens: list[str] = []
    i, n = 0, len(src)

    while i < n:
        c = src[i]

        # Skip whitespace
        if c in " \t\r\n":
            i += 1
            continue

        # Skip comment
        if c == ";":
            while i < n and src[i] != "\n":
                i += 1
            continue

        if c == "(":
            tokens.append("(")
            i += 1
            continue

        if c == ")":
            tokens.append(")")
            i += 1
            continue

        # String literal
        if c == '"':
            i += 1
            buf = []
            while i < n and src[i] != '"':
                if src[i] == "\\" and i + 1 < n:
                    esc = src[i + 1]
                    if esc == "n":
                        buf.append("\n")
                    elif esc == "0":
                        buf.append("\0")
                    elif esc == '"':
                        buf.append('"')
                    elif esc == "\\":
                        buf.append("\\")
                    else:
                        buf.append(src[i])
                        buf.append(esc)
                    i += 2
                else:
                    buf.append(src[i])
                    i += 1
            if i >= n:
                raise SyntaxError("Unterminated string literal")
            i += 1  # skip closing "
            tokens.append('"' + "".join(buf) + '"')
            continue

        # Number or identifier/symbol
        j = i
        while j < n and src[j] not in " \t\r\n();\"":
            j += 1
        token = src[i:j]
        if not token:
            raise SyntaxError(f"Unexpected character: {c!r}")
        tokens.append(token)
        i = j

    return tokens


# ── Parser ───────────────────────────────────────────────────────────────────

class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos    = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _consume(self, expected: str | None = None) -> str:
        tok = self._peek()
        if tok is None:
            raise SyntaxError("Unexpected end of input")
        if expected is not None and tok != expected:
            raise SyntaxError(f"Expected {expected!r}, got {tok!r}")
        self._pos += 1
        return tok

    def parse_program(self) -> list[Expr]:
        exprs: list[Expr] = []
        while self._peek() is not None:
            exprs.append(self._parse_expr())
        return exprs

    def _parse_expr(self) -> Expr:
        tok = self._peek()
        if tok is None:
            raise SyntaxError("Unexpected end of input")

        if tok == "(":
            return self._parse_compound()

        self._consume()

        # String literal
        if tok.startswith('"'):
            return StrLit(tok[1:-1])  # strip leading and trailing "

        # Integer literal
        try:
            return IntLit(int(tok))
        except ValueError:
            pass

        # Identifier
        return VarRef(tok)

    def _parse_compound(self) -> Expr:
        self._consume("(")
        head = self._consume()

        if head == "defun":
            name   = self._consume()
            self._consume("(")
            params: list[str] = []
            while self._peek() != ")":
                params.append(self._consume())
            self._consume(")")
            body = self._parse_body()
            self._consume(")")
            return DefFun(name, params, body)

        if head == "setq":
            name  = self._consume()
            value = self._parse_expr()
            self._consume(")")
            return Setq(name, value)

        if head == "if":
            cond  = self._parse_expr()
            then  = self._parse_expr()
            else_ = self._parse_expr()
            self._consume(")")
            return If(cond, then, else_)

        if head == "loop":
            cond = self._parse_expr()
            body = self._parse_body()
            self._consume(")")
            return Loop(cond, body)

        if head == "progn":
            body = self._parse_body()
            self._consume(")")
            return Progn(body)

        # Function / built-in call
        args: list[Expr] = []
        while self._peek() != ")":
            args.append(self._parse_expr())
        self._consume(")")
        return Call(head, args)

    def _parse_body(self) -> list[Expr]:
        exprs: list[Expr] = []
        while self._peek() != ")":
            exprs.append(self._parse_expr())
        return exprs


def parse(src: str) -> list[Expr]:
    """Parse Lisp source and return list of top-level expressions."""
    tokens = tokenize(src)
    return _Parser(tokens).parse_program()
