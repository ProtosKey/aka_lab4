"""Code generator: Lisp AST → RISC instructions. Results always in a0."""

from __future__ import annotations

from .assembler import (
    A0,
    ARG_REGS,
    FP,
    GP,
    RA,
    SP,
    T0,
    T1,
    X0,
    Assembler,
    _hi_lo,
)
from .ast import (
    Call,
    DefFun,
    Expr,
    If,
    IntLit,
    Loop,
    Progn,
    Setq,
    StrLit,
    VarRef,
)

DATA_MEM_SIZE = 64 * 1024  # 64 KiB
STACK_TOP = DATA_MEM_SIZE  # sp points just past the top byte

# Built-in names that the translator inlines (never emit a JAL for these)
_BUILTINS = {
    "+",
    "-",
    "*",
    "<",
    ">",
    "=",
    "<=",
    ">=",
    "getc",
    "putc",
    "halt",
    "load",
    "store",
    "load-byte",
    "store-byte",
}


class DataSection:
    """Manages the data memory layout (strings + globals)."""

    def __init__(self) -> None:
        self._bytes: bytearray = bytearray()
        self._strings: dict[str, int] = {}  # content → byte offset
        self._globals: dict[str, int] = {}  # name → byte offset from GP_BASE
        self.gp_base: int = 0  # set by freeze()

    def add_string(self, s: str) -> int:
        """Return byte offset of the string in the data section."""
        if s in self._strings:
            return self._strings[s]
        offset = len(self._bytes)
        self._strings[s] = offset
        self._bytes.extend(s.encode("latin-1", errors="replace"))
        self._bytes.append(0)  # NUL terminator
        return offset

    def freeze(self) -> None:
        """Called after all strings are added.  Aligns to 4 bytes; GP starts here."""
        while len(self._bytes) % 4:
            self._bytes.append(0)
        self.gp_base = len(self._bytes)

    def global_offset(self, name: str) -> int:
        """Return byte offset of global variable from GP_BASE (allocates if new)."""
        if name not in self._globals:
            off = len(self._globals) * 4
            self._globals[name] = off
            self._bytes.extend(b"\x00\x00\x00\x00")
        return self._globals[name]

    def to_bytes(self) -> bytes:
        return bytes(self._bytes)


# pre-scan


def _collect_strings(exprs: list[Expr], ds: DataSection) -> None:
    """Walk the AST and pre-register all StrLit values."""
    for e in exprs:
        _collect_strings_expr(e, ds)


def _collect_strings_expr(e: Expr, ds: DataSection) -> None:
    if isinstance(e, StrLit):
        offset = ds.add_string(e.value)
        e.label = offset
    elif isinstance(e, (Setq, If)):
        if isinstance(e, Setq):
            _collect_strings_expr(e.value, ds)
        else:
            _collect_strings_expr(e.cond, ds)
            _collect_strings_expr(e.then, ds)
            _collect_strings_expr(e.else_, ds)
    elif isinstance(e, (Loop, Progn, DefFun)):
        if isinstance(e, Loop):
            _collect_strings_expr(e.cond, ds)
            _collect_strings(e.body, ds)
        elif isinstance(e, Progn):
            _collect_strings(e.body, ds)
        else:
            _collect_strings(e.body, ds)
    elif isinstance(e, Call):
        _collect_strings(e.args, ds)


def _collect_funs(exprs: list[Expr]) -> dict[str, DefFun]:
    """Return all DefFun nodes keyed by name (in order of definition)."""
    funs: dict[str, DefFun] = {}
    for e in exprs:
        if isinstance(e, DefFun):
            funs[e.name] = e
    return funs


# code generator


class CodeGen:
    def __init__(self, asm: Assembler, ds: DataSection) -> None:
        self.asm = asm
        self.ds = ds
        self._params: list[str] = []  # params of current function (empty = main)


    def compile(self, exprs: list[Expr]) -> None:
        """Compile a complete program."""
        funs = _collect_funs(exprs)

        # Emit boot stub
        self._emit_boot()

        # Emit user-defined functions first (so JALs can reach them)
        for fun in funs.values():
            self._emit_defun(fun)

        # Emit main body
        self.asm.place_label("main")
        main_exprs = [e for e in exprs if not isinstance(e, DefFun)]
        for e in main_exprs:
            self._expr(e)
        self.asm.halt()

    def _emit_boot(self) -> None:
        """5-instruction boot stub: load gp/sp, then JAL main."""
        gp_val = self.ds.gp_base

        gp_hi, gp_lo = _hi_lo(gp_val)
        if gp_hi:
            self.asm.lui(GP, gp_hi)
            self.asm.addi(GP, GP, gp_lo & 0xFFF)
        else:
            self.asm.addi(GP, X0, gp_lo & 0xFFF)
            self.asm.addi(GP, GP, 0)  # pad to keep 5-instr boot (nop)

        # LUI sp + ADDI sp
        sp_hi, sp_lo = _hi_lo(STACK_TOP)
        if sp_hi:
            self.asm.lui(SP, sp_hi)
            self.asm.addi(SP, SP, sp_lo & 0xFFF)
        else:
            self.asm.addi(SP, X0, sp_lo & 0xFFF)
            self.asm.addi(SP, SP, 0)

        self.asm.jal(X0, "main")


    def _expr(self, e: Expr) -> None:
        """Lower expression e; result lands in a0."""
        if isinstance(e, IntLit):
            self._int_lit(e)
        elif isinstance(e, StrLit):
            self._str_lit(e)
        elif isinstance(e, VarRef):
            self._var_ref(e)
        elif isinstance(e, Setq):
            self._setq(e)
        elif isinstance(e, If):
            self._if(e)
        elif isinstance(e, Loop):
            self._loop(e)
        elif isinstance(e, Progn):
            self._progn(e)
        elif isinstance(e, DefFun):
            pass  # already emitted separately
        elif isinstance(e, Call):
            self._call(e)
        else:
            raise NotImplementedError(type(e))

    def _int_lit(self, e: IntLit) -> None:
        self.asm.load_const(A0, e.value)

    def _str_lit(self, e: StrLit) -> None:
        # Load absolute address of the string literal
        addr = e.label  # byte offset in data memory
        self.asm.load_const(A0, addr)

    def _var_ref(self, e: VarRef) -> None:
        idx = self._param_idx(e.name)
        if idx >= 0:
            self.asm.lw(A0, FP, 8 + 4 * idx)
        else:
            off = self.ds.global_offset(e.name)
            self.asm.lw(A0, GP, off)

    def _setq(self, e: Setq) -> None:
        self._expr(e.value)  # a0 = value
        idx = self._param_idx(e.name)
        if idx >= 0:
            self.asm.sw(FP, A0, 8 + 4 * idx)
        else:
            off = self.ds.global_offset(e.name)
            self.asm.sw(GP, A0, off)
        # a0 still holds the assigned value (Setq is an expression)

    def _if(self, e: If) -> None:
        l_else = self.asm.new_label("else")
        l_end = self.asm.new_label("end")
        self._expr(e.cond)
        self.asm.beq(A0, X0, l_else)
        self._expr(e.then)
        self.asm.jal(X0, l_end)
        self.asm.place_label(l_else)
        self._expr(e.else_)
        self.asm.place_label(l_end)

    def _loop(self, e: Loop) -> None:
        l_head = self.asm.new_label("Lhead")
        l_end = self.asm.new_label("Lend")
        # Push default result = 0
        self.asm.addi(SP, SP, -4)
        self.asm.sw(SP, X0, 0)
        self.asm.place_label(l_head)
        self._expr(e.cond)
        self.asm.beq(A0, X0, l_end)
        for stmt in e.body:
            self._expr(stmt)
        self.asm.sw(SP, A0, 0)  # save last body value
        self.asm.jal(X0, l_head)
        self.asm.place_label(l_end)
        self.asm.lw(A0, SP, 0)
        self.asm.addi(SP, SP, 4)

    def _progn(self, e: Progn) -> None:
        for stmt in e.body:
            self._expr(stmt)

    def _call(self, e: Call) -> None:
        if e.callee in _BUILTINS:
            self._builtin(e)
        else:
            self._user_call(e)


    def _builtin(self, e: Call) -> None:
        name = e.callee

        if name == "halt":
            self.asm.halt()
            return

        if name == "getc":
            self.asm.in_port(A0, 0)
            return

        if name == "putc":
            self._expr(e.args[0])
            self.asm.out_port(A0, 1)
            return

        if name == "load":
            self._expr(e.args[0])  # a0 = addr
            self.asm.lw(A0, A0, 0)
            return

        if name == "load-byte":
            self._expr(e.args[0])
            self.asm.lb(A0, A0, 0)
            return

        if name == "store":
            self._expr(e.args[0])  # a0 = addr
            self.asm.addi(SP, SP, -4)
            self.asm.sw(SP, A0, 0)  # push addr
            self._expr(e.args[1])  # a0 = val
            self.asm.lw(T0, SP, 0)  # t0 = addr
            self.asm.addi(SP, SP, 4)
            self.asm.sw(T0, A0, 0)  # M4[addr] = val
            return

        if name == "store-byte":
            self._expr(e.args[0])
            self.asm.addi(SP, SP, -4)
            self.asm.sw(SP, A0, 0)
            self._expr(e.args[1])
            self.asm.lw(T0, SP, 0)
            self.asm.addi(SP, SP, 4)
            self.asm.sb(T0, A0, 0)
            return

        # Binary arithmetic/comparison: eval A, push; eval B; pop t0 = A
        a, b = e.args[0], e.args[1]
        self._expr(a)
        self.asm.addi(SP, SP, -4)
        self.asm.sw(SP, A0, 0)
        self._expr(b)
        self.asm.lw(T0, SP, 0)  # t0 = A
        self.asm.addi(SP, SP, 4)
        # Now: t0 = A, a0 = B

        if name == "+":
            self.asm.add(A0, T0, A0)
        elif name == "-":
            self.asm.sub(A0, T0, A0)
        elif name == "*":
            self.asm.mul(A0, T0, A0)

        elif name == "=":
            # t1 = t0 - a0; a0 = 1; BEQ t1,x0,+8; a0 = 0
            l_eq = self.asm.new_label("eq")
            self.asm.sub(T1, T0, A0)
            self.asm.addi(A0, X0, 1)
            self.asm.beq(T1, X0, l_eq)
            self.asm.addi(A0, X0, 0)
            self.asm.place_label(l_eq)

        elif name == "<":
            # t1 = B; a0 = 1; BLT t0,t1,+8; a0 = 0
            l_lt = self.asm.new_label("lt")
            self.asm.addi(T1, A0, 0)
            self.asm.addi(A0, X0, 1)
            self.asm.blt(T0, T1, l_lt)
            self.asm.addi(A0, X0, 0)
            self.asm.place_label(l_lt)

        elif name == ">":
            # (A > B) ⟺ (B < A): BLT t1(=B=a0), t0(=A)
            l_gt = self.asm.new_label("gt")
            self.asm.addi(T1, A0, 0)
            self.asm.addi(A0, X0, 1)
            self.asm.blt(T1, T0, l_gt)
            self.asm.addi(A0, X0, 0)
            self.asm.place_label(l_gt)

        elif name == "<=":
            # (A <= B) = !(B < A)
            l_le = self.asm.new_label("le")
            self.asm.addi(T1, A0, 0)
            self.asm.addi(A0, X0, 0)
            self.asm.blt(T1, T0, l_le)
            self.asm.addi(A0, X0, 1)
            self.asm.place_label(l_le)

        elif name == ">=":
            # (A >= B) = !(A < B)
            l_ge = self.asm.new_label("ge")
            self.asm.addi(T1, A0, 0)
            self.asm.addi(A0, X0, 0)
            self.asm.blt(T0, T1, l_ge)
            self.asm.addi(A0, X0, 1)
            self.asm.place_label(l_ge)

        else:
            raise NotImplementedError(f"Built-in: {name!r}")

    def _user_call(self, e: Call) -> None:
        """Push args in order, pop into a(n-1)..a0 in reverse, JAL."""
        n = len(e.args)
        for arg in e.args:
            self._expr(arg)
            self.asm.addi(SP, SP, -4)
            self.asm.sw(SP, A0, 0)
        for i in range(n - 1, -1, -1):
            self.asm.lw(ARG_REGS[i], SP, 0)
            self.asm.addi(SP, SP, 4)
        self.asm.jal(RA, e.callee)

    def _emit_defun(self, fun: DefFun) -> None:
        """Emit prologue + body + epilogue for a user function."""
        n = len(fun.params)
        frame_size = 8 + 4 * n  # ra(4) + fp(4) + n params(4 each)

        self.asm.place_label(fun.name)

        # Prologue
        self.asm.addi(SP, SP, -frame_size)
        self.asm.sw(SP, RA, 0)  # save ra
        self.asm.sw(SP, FP, 4)  # save caller's fp
        self.asm.addi(FP, SP, 0)  # new fp = sp

        # Store parameters
        for i, _ in enumerate(fun.params):
            self.asm.sw(FP, ARG_REGS[i], 8 + 4 * i)

        # Compile body (with params in scope)
        old_params = self._params
        self._params = fun.params
        for stmt in fun.body:
            self._expr(stmt)
        self._params = old_params

        # Epilogue
        self.asm.addi(SP, FP, 0)  # restore sp to frame base
        self.asm.lw(RA, SP, 0)  # restore ra
        self.asm.lw(FP, SP, 4)  # restore caller's fp
        self.asm.addi(SP, SP, frame_size)
        self.asm.jalr(X0, RA)  # return


    def _param_idx(self, name: str) -> int:
        """Return 0-based parameter index, or -1 if not a parameter."""
        try:
            return self._params.index(name)
        except ValueError:
            return -1


# public API


def compile_program(src: str) -> tuple[bytes, bytes, str]:
    """
    Compile Lisp source to binary.

    Returns:
        inst_bytes  — instruction memory binary (little-endian 32-bit words)
        data_bytes  — data memory initial image
        listing_txt — human-readable disassembly listing
    """
    from .ast import parse

    exprs = parse(src)

    ds = DataSection()
    _collect_strings(exprs, ds)
    ds.freeze()

    asm = Assembler()
    cg = CodeGen(asm, ds)
    cg.compile(exprs)

    return asm.to_bytes(), ds.to_bytes(), asm.listing_text()
