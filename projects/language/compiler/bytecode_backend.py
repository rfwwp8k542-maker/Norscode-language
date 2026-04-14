import argparse
import json
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .ast_nodes import (
    BinOpNode,
    BlockNode,
    BoolNode,
    BreakNode,
    CallNode,
    ContinueNode,
    ExprStmtNode,
    ForNode,
    ForEachNode,
    FunctionNode,
    IfNode,
    IfExprNode,
    IndexNode,
    IndexSetNode,
    ListLiteralNode,
    ModuleCallNode,
    NumberNode,
    PrintNode,
    ProgramNode,
    ReturnNode,
    StringNode,
    UnaryOpNode,
    VarAccessNode,
    VarDeclareNode,
    VarSetNode,
    WhileNode,
)
from .ast_bridge import load_source_as_program, read_ast


class BytecodeCompileError(RuntimeError):
    pass


class BytecodeRuntimeError(RuntimeError):
    pass


BYTECODE_FORMAT = "norscode-bytecode-v1"
BYTECODE_NOARG_OPS = {
    "BINARY_ADD",
    "BINARY_SUB",
    "BINARY_AND",
    "BINARY_OR",
    "BINARY_DIV",
    "BINARY_MUL",
    "COMPARE_EQ",
    "COMPARE_GE",
    "COMPARE_GT",
    "COMPARE_LE",
    "COMPARE_LT",
    "COMPARE_NE",
    "INDEX_GET",
    "INDEX_SET",
    "POP",
    "UNARY_NEG",
    "UNARY_NOT",
    "RETURN",
}
BYTECODE_ONEARG_OPS = {
    "BUILD_LIST",
    "JUMP",
    "JUMP_IF_FALSE",
    "LABEL",
    "LOAD_NAME",
    "PUSH_CONST",
    "STORE_NAME",
}
BYTECODE_TWOARG_OPS = {"CALL"}
BYTECODE_ALL_OPS = BYTECODE_NOARG_OPS | BYTECODE_ONEARG_OPS | BYTECODE_TWOARG_OPS


@dataclass
class LoopLabels:
    start: str
    end: str


class BytecodeCompiler:
    def __init__(self, alias_map: dict[str, str] | None = None):
        self.alias_map = alias_map or {}
        self.label_counter = 0
        self.temp_counter = 0
        self.loop_stack: list[LoopLabels] = []
        self.current_module = "__main__"

    def new_label(self, prefix: str) -> str:
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def new_temp_name(self, prefix: str) -> str:
        self.temp_counter += 1
        return f"__{prefix}_{self.temp_counter}"

    def compile_program(self, program: ProgramNode) -> dict[str, Any]:
        functions = {}
        imports = []
        for imp in getattr(program, "imports", []):
            imports.append({"module": imp.module_name, "alias": imp.alias})
        for fn in getattr(program, "functions", []):
            key = self.function_key(fn)
            functions[key] = self.compile_function(fn)
        return {
            "format": BYTECODE_FORMAT,
            "entry": "__main__.start",
            "imports": imports,
            "functions": functions,
        }

    def function_key(self, fn: FunctionNode) -> str:
        module_name = getattr(fn, "module_name", None) or "__main__"
        return f"{module_name}.{fn.name}"

    def compile_function(self, fn: FunctionNode) -> dict[str, Any]:
        code: list[list[Any]] = []
        previous_module = self.current_module
        self.current_module = getattr(fn, "module_name", None) or "__main__"
        self.emit_block(fn.body, code)
        self.current_module = previous_module
        if not code or code[-1][0] != "RETURN":
            code.append(["PUSH_CONST", None])
            code.append(["RETURN"])
        return {
            "name": fn.name,
            "module": getattr(fn, "module_name", None) or "__main__",
            "params": [p.name for p in getattr(fn, "params", [])],
            "code": code,
        }

    def emit_block(self, block: BlockNode, code: list[list[Any]]):
        for stmt in getattr(block, "statements", []):
            self.emit_stmt(stmt, code)

    def emit_stmt(self, node: Any, code: list[list[Any]]):
        if isinstance(node, VarDeclareNode):
            self.emit_expr(node.expr, code)
            code.append(["STORE_NAME", node.name])
            return
        if isinstance(node, VarSetNode):
            self.emit_expr(node.expr, code)
            code.append(["STORE_NAME", node.name])
            return
        if isinstance(node, IndexSetNode):
            code.append(["LOAD_NAME", node.target_name])
            self.emit_expr(node.index_expr, code)
            self.emit_expr(node.value_expr, code)
            code.append(["INDEX_SET"])
            return
        if isinstance(node, ExprStmtNode):
            self.emit_expr(node.expr, code)
            code.append(["POP"])
            return
        if isinstance(node, PrintNode):
            self.emit_expr(node.expr, code)
            code.append(["CALL", "builtin.skriv", 1])
            code.append(["POP"])
            return
        if isinstance(node, ReturnNode):
            self.emit_expr(node.expr, code)
            code.append(["RETURN"])
            return
        if isinstance(node, IfNode):
            end_label = self.new_label("ifend")
            else_label = self.new_label("ifelse") if (node.else_block or node.elif_blocks) else end_label
            self.emit_expr(node.condition, code)
            code.append(["JUMP_IF_FALSE", else_label])
            self.emit_block(node.then_block, code)
            code.append(["JUMP", end_label])
            current_else = else_label
            if node.elif_blocks:
                for idx, (cond, block) in enumerate(node.elif_blocks):
                    code.append(["LABEL", current_else])
                    next_else = self.new_label(f"elifelse_{idx}") if (idx < len(node.elif_blocks)-1 or node.else_block) else end_label
                    self.emit_expr(cond, code)
                    code.append(["JUMP_IF_FALSE", next_else])
                    self.emit_block(block, code)
                    code.append(["JUMP", end_label])
                    current_else = next_else
            if node.else_block:
                code.append(["LABEL", current_else])
                self.emit_block(node.else_block, code)
            code.append(["LABEL", end_label])
            return
        if isinstance(node, WhileNode):
            start = self.new_label("while_start")
            end = self.new_label("while_end")
            self.loop_stack.append(LoopLabels(start, end))
            code.append(["LABEL", start])
            self.emit_expr(node.condition, code)
            code.append(["JUMP_IF_FALSE", end])
            self.emit_block(node.body, code)
            code.append(["JUMP", start])
            code.append(["LABEL", end])
            self.loop_stack.pop()
            return
        if isinstance(node, ForNode):
            start = self.new_label("for_start")
            end = self.new_label("for_end")
            self.emit_expr(node.start_expr, code)
            code.append(["STORE_NAME", node.name])
            self.loop_stack.append(LoopLabels(start, end))
            code.append(["LABEL", start])
            code.append(["LOAD_NAME", node.name])
            self.emit_expr(node.end_expr, code)
            code.append(["COMPARE_LE"])
            code.append(["JUMP_IF_FALSE", end])
            self.emit_block(node.body, code)
            code.append(["LOAD_NAME", node.name])
            self.emit_expr(node.step_expr, code)
            code.append(["BINARY_ADD"])
            code.append(["STORE_NAME", node.name])
            code.append(["JUMP", start])
            code.append(["LABEL", end])
            self.loop_stack.pop()
            return
        if isinstance(node, ForEachNode):
            list_name = self.new_temp_name("foreach_list")
            index_name = self.new_temp_name("foreach_index")
            start = self.new_label("foreach_start")
            step = self.new_label("foreach_step")
            end = self.new_label("foreach_end")
            self.emit_expr(node.list_expr, code)
            code.append(["STORE_NAME", list_name])
            code.append(["PUSH_CONST", 0])
            code.append(["STORE_NAME", index_name])
            self.loop_stack.append(LoopLabels(step, end))
            code.append(["LABEL", start])
            code.append(["LOAD_NAME", index_name])
            code.append(["LOAD_NAME", list_name])
            code.append(["CALL", "lengde", 1])
            code.append(["COMPARE_LT"])
            code.append(["JUMP_IF_FALSE", end])
            code.append(["LOAD_NAME", list_name])
            code.append(["LOAD_NAME", index_name])
            code.append(["INDEX_GET"])
            code.append(["STORE_NAME", node.item_name])
            self.emit_block(node.body, code)
            code.append(["LABEL", step])
            code.append(["LOAD_NAME", index_name])
            code.append(["PUSH_CONST", 1])
            code.append(["BINARY_ADD"])
            code.append(["STORE_NAME", index_name])
            code.append(["JUMP", start])
            code.append(["LABEL", end])
            self.loop_stack.pop()
            return
        if isinstance(node, BreakNode):
            if not self.loop_stack:
                raise BytecodeCompileError("'bryt' utenfor løkke")
            code.append(["JUMP", self.loop_stack[-1].end])
            return
        if isinstance(node, ContinueNode):
            if not self.loop_stack:
                raise BytecodeCompileError("'fortsett' utenfor løkke")
            code.append(["JUMP", self.loop_stack[-1].start])
            return
        raise BytecodeCompileError(f"Bytecode-backend støtter ikke statement: {type(node).__name__}")

    def emit_expr(self, node: Any, code: list[list[Any]]):
        if isinstance(node, NumberNode):
            code.append(["PUSH_CONST", node.value])
            return
        if isinstance(node, StringNode):
            code.append(["PUSH_CONST", node.value])
            return
        if isinstance(node, BoolNode):
            code.append(["PUSH_CONST", node.value])
            return
        if isinstance(node, VarAccessNode):
            code.append(["LOAD_NAME", node.name])
            return
        if isinstance(node, ListLiteralNode):
            for item in node.items:
                self.emit_expr(item, code)
            code.append(["BUILD_LIST", len(node.items)])
            return
        if isinstance(node, IndexNode):
            target_expr = getattr(node, "list_expr", getattr(node, "target", None))
            self.emit_expr(target_expr, code)
            self.emit_expr(node.index_expr, code)
            code.append(["INDEX_GET"])
            return
        if isinstance(node, UnaryOpNode):
            self.emit_expr(node.node, code)
            if node.op.typ == "MINUS":
                code.append(["UNARY_NEG"])
                return
            if node.op.typ == "IKKE":
                code.append(["UNARY_NOT"])
                return
            if node.op.typ == "PLUS":
                return
            raise BytecodeCompileError(f"Ukjent unary-op: {node.op.typ}")
        if isinstance(node, BinOpNode):
            if node.op.typ == "OG":
                end_label = self.new_label("and_end")
                false_label = self.new_label("and_false")
                self.emit_expr(node.left, code)
                code.append(["JUMP_IF_FALSE", false_label])
                self.emit_expr(node.right, code)
                code.append(["JUMP_IF_FALSE", false_label])
                code.append(["PUSH_CONST", True])
                code.append(["JUMP", end_label])
                code.append(["LABEL", false_label])
                code.append(["PUSH_CONST", False])
                code.append(["LABEL", end_label])
                return
            if node.op.typ == "ELLER":
                end_label = self.new_label("or_end")
                true_label = self.new_label("or_true")
                self.emit_expr(node.left, code)
                code.append(["JUMP_IF_FALSE", true_label + "_rhs"])
                code.append(["PUSH_CONST", True])
                code.append(["JUMP", end_label])
                code.append(["LABEL", true_label + "_rhs"])
                self.emit_expr(node.right, code)
                code.append(["JUMP_IF_FALSE", true_label + "_false"])
                code.append(["PUSH_CONST", True])
                code.append(["JUMP", end_label])
                code.append(["LABEL", true_label + "_false"])
                code.append(["PUSH_CONST", False])
                code.append(["LABEL", end_label])
                return
            self.emit_expr(node.left, code)
            self.emit_expr(node.right, code)
            mapping = {
                "PLUS": "BINARY_ADD",
                "MINUS": "BINARY_SUB",
                "MUL": "BINARY_MUL",
                "DIV": "BINARY_DIV",
                "EQ": "COMPARE_EQ",
                "NE": "COMPARE_NE",
                "GT": "COMPARE_GT",
                "LT": "COMPARE_LT",
                "GTE": "COMPARE_GE",
                "LTE": "COMPARE_LE",
            }
            opcode = mapping.get(node.op.typ)
            if opcode is None:
                raise BytecodeCompileError(f"Ukjent binæroperator: {node.op.typ}")
            code.append([opcode])
            return
        if isinstance(node, CallNode):
            for arg in node.args:
                self.emit_expr(arg, code)
            code.append(["CALL", self.resolve_call_name(node.name), len(node.args)])
            return
        if isinstance(node, ModuleCallNode):
            for arg in node.args:
                self.emit_expr(arg, code)
            module_name = self.alias_map.get(node.module_name, node.module_name)
            code.append(["CALL", f"{module_name}.{node.func_name}", len(node.args)])
            return
        if isinstance(node, IfExprNode):
            else_label = self.new_label("ifexpr_else")
            end_label = self.new_label("ifexpr_end")
            self.emit_expr(node.condition, code)
            code.append(["JUMP_IF_FALSE", else_label])
            self.emit_expr(node.then_expr, code)
            code.append(["JUMP", end_label])
            code.append(["LABEL", else_label])
            self.emit_expr(node.else_expr, code)
            code.append(["LABEL", end_label])
            return
        raise BytecodeCompileError(f"Bytecode-backend støtter ikke uttrykk: {type(node).__name__}")

    def resolve_call_name(self, name: str) -> str:
        builtins = {
            "assert", "assert_eq", "assert_ne", "skriv", "lengde",
            "legg_til", "pop_siste", "fjern_indeks", "sett_inn",
            "tekst_fra_heltall", "tekst_fra_bool", "tekst_til_små", "tekst_til_store", "tekst_til_tittel", "tekst_omvendt", "tekst_del_på", "del_på", "tekst_trim", "tekst_slice", "tekst_lengde", "tekst_slutter_med",
            "tekst_starter_med", "tekst_inneholder", "tekst_erstatt", "del_linjer", "tekst_er_ordtegn",
            "sass_til_css",
            "web_server_start",
            "gui_vindu", "gui_panel", "gui_rad", "gui_tekst", "gui_tekstboks", "gui_liste",
            "gui_liste_legg_til", "gui_liste_tom", "gui_liste_antall", "gui_liste_hent", "gui_liste_fjern", "gui_liste_filer_tre",
            "gui_liste_valgt", "gui_liste_velg",
                "gui_på_klikk", "gui_på_endring", "gui_på_tast", "gui_trykk", "gui_trykk_tast",
            "gui_foresatt", "gui_barn",
            "gui_knapp", "gui_etikett", "gui_tekstfelt", "gui_editor", "gui_editor_hopp_til", "gui_editor_cursor", "gui_editor_erstatt_fra_til",
            "gui_sett_tekst", "gui_hent_tekst", "gui_vis", "gui_lukk",
            "les_fil", "skriv_fil", "fil_eksisterer", "db_open", "db_close", "db_begin", "db_commit", "db_rollback", "db_exec", "db_query",
            "les_miljo", "argv", "kjør_kommando", "liste_filer", "liste_filer_tre", "gui_liste_filer_tre", "kjor_kilde",
        }
        if name in builtins:
            return f"builtin.{name}"
        return f"{self.current_module}.{name}"


class BytecodeVM:
    def __init__(
        self,
        program: dict[str, Any],
        trace: bool = False,
        max_steps: int = 200000,
        trace_focus: str | None = None,
        repeat_limit: int = 0,
        expr_probe: str | None = None,
        expr_probe_log: str | None = None,
    ):
        self.program = program
        self.functions = program.get("functions", {})
        self.alias_map = {
            item["alias"]: item["module"]
            for item in program.get("imports", [])
            if isinstance(item, dict) and isinstance(item.get("alias"), str) and isinstance(item.get("module"), str)
        }
        self.output: list[str] = []
        self.trace = trace
        self.max_steps = max_steps
        self.trace_focus = trace_focus.strip() if isinstance(trace_focus, str) and trace_focus.strip() else None
        self.repeat_limit = max(0, int(repeat_limit))
        self.expr_probe = expr_probe.strip() if isinstance(expr_probe, str) and expr_probe.strip() else None
        self.expr_probe_log = expr_probe_log.strip() if isinstance(expr_probe_log, str) and expr_probe_log.strip() else None
        self.expr_probe_events: list[str] = []
        self.steps = 0
        self.trace_log: list[str] = []
        self._repeat_state_key: tuple[Any, ...] | None = None
        self._repeat_state_count = 0
        self._selfhost_token_map = self._load_selfhost_token_map()
        self._memo_cache: dict[tuple[str, str], Any] = {}
        self._memoizable_functions = {
            "selfhost.compiler.normaliser_norsk_token",
            "selfhost.compiler.stack_behov",
            "selfhost.compiler.stack_endring",
            "selfhost.compiler.op_krever_arg",
            "selfhost.compiler.op_kjent",
            "selfhost.compiler.er_heltall_token",
            "selfhost.compiler.operator_til_opcode",
            "selfhost.compiler.uttrykk_til_ops_og_verdier_med_miljo",
            "selfhost.compiler.instruksjon_til_tekst",
            "selfhost.compiler.append_linje",
            "selfhost.compiler.disasm_program",
        }
        self.gui_objects: dict[int, dict[str, Any]] = {}
        self.gui_next_id = 1

    def _should_trace_function(self, name: str) -> bool:
        if not self.trace:
            return False
        if self.trace_focus is None:
            return True
        return self.trace_focus in name

    def _log(self, message: str) -> None:
        if not self.trace:
            return
        self.trace_log.append(message)
        if len(self.trace_log) > 400:
            del self.trace_log[:200]

    def get_trace_tail(self, limit: int = 60) -> list[str]:
        return self.trace_log[-limit:]

    def _record_expr_probe(self, lines: list[str]) -> None:
        payload = [str(line) for line in lines]
        self.expr_probe_events.extend(payload)
        if self.trace:
            for line in payload:
                self._log(line)

    def dump_expr_probe(self) -> str:
        text = "\n".join(self.expr_probe_events)
        if text and not text.endswith("\n"):
            text += "\n"
        if self.expr_probe_log and text:
            Path(self.expr_probe_log).expanduser().write_text(text, encoding="utf-8")
        return text


    def _load_selfhost_token_map(self) -> dict[str, str]:
        source_path = Path(__file__).resolve().parent.parent / "selfhost" / "compiler.no"
        if not source_path.exists():
            return {}
        lines = source_path.read_text(encoding="utf-8").splitlines()
        mapping: dict[str, str] = {}
        inside = False
        pending: list[str] = []
        for raw in lines:
            line = raw.strip()
            if line.startswith("funksjon normaliser_norsk_token"):
                inside = True
                continue
            if inside and line.startswith("funksjon "):
                break
            if not inside:
                continue
            if line.startswith("hvis (") and "tok ==" in line:
                pending = re.findall(r'"([^"]+)"', line)
                continue
            if pending and line.startswith("returner "):
                values = re.findall(r'"([^"]+)"', line)
                if values:
                    for key in pending:
                        mapping[key] = values[0]
                pending = []
        return mapping

    def _selfhost_emit_operator(self, ops: list[Any], verdier: list[Any], op: str) -> bool:
        if op in {"u!", "uikke"}:
            ops.append("NOT")
            verdier.append(0)
            return True
        if op == "u-":
            ops.extend(["PUSH", "SWAP", "SUB"])
            verdier.extend([0, 0, 0])
            return True
        if op in {"!=", "ikke_er"}:
            # Equality should be evaluated before negation so phrases like
            # "ikke er" and "ikke lik" produce EQ followed by NOT.
            ops.extend(["EQ", "NOT"])
            verdier.extend([0, 0])
            return True
        if op in {"xor", "^^"}:
            ops.extend(["EQ", "NOT"])
            verdier.extend([0, 0])
            return True
        if op == "xnor":
            ops.append("EQ")
            verdier.append(0)
            return True
        if op == "nand":
            ops.extend(["AND", "NOT"])
            verdier.extend([0, 0])
            return True
        if op == "nor":
            ops.extend(["OR", "NOT"])
            verdier.extend([0, 0])
            return True
        if op == "impliserer":
            ops.extend(["SWAP", "NOT", "SWAP", "OR"])
            verdier.extend([0, 0, 0, 0])
            return True
        if op == "impliseres_av":
            ops.extend(["NOT", "OR"])
            verdier.extend([0, 0])
            return True
        if op in {"<=", "mindre_eller_lik"}:
            ops.extend(["GT", "NOT"])
            verdier.extend([0, 0])
            return True
        if op in {">=", "storre_eller_lik"}:
            ops.extend(["LT", "NOT"])
            verdier.extend([0, 0])
            return True
        opcode = self._call_hot_selfhost_helper("selfhost.compiler.operator_til_opcode", [op])
        if opcode:
            ops.append(opcode)
            verdier.append(0)
            return True
        return False

    def _selfhost_operator_precedence(self, tok: str) -> int:
        if tok in {"u!", "u-", "uikke"}:
            return 7
        if tok in {"*", "/", "%"}:
            return 6
        if tok in {"+", "-"}:
            return 5
        if tok in {"<", ">", "<=", ">=", "mindre_enn", "storre_enn", "mindre_eller_lik", "storre_eller_lik"}:
            return 4
        if tok in {"==", "!=", "er", "ikke_er"}:
            return 3
        if tok in {"&&", "og", "samt", "nand"}:
            return 2
        if tok in {"||", "eller", "enten", "xor", "^^", "xnor", "nor", "impliserer", "impliseres_av"}:
            return 1
        return 0

    def _selfhost_is_operator_token(self, tok: str) -> bool:
        return tok in {
            "+", "-", "*", "/", "%", "==", "!=", "<", ">", "<=", ">=",
            "&&", "||", "!", "og", "eller", "samt", "ikke", "nand", "nor",
            "xor", "^^", "xnor", "impliserer", "impliseres_av", "er", "ikke_er",
            "mindre_enn", "storre_enn", "mindre_eller_lik", "storre_eller_lik", "enten"
        }

    def _hot_selfhost_expr_to_ops(self, tokens: list[Any], navn: list[Any], miljo_verdier: list[Any], ops: list[Any], verdier: list[Any]) -> str:
        toks = [str(t) for t in tokens]
        names = [str(n) for n in navn]
        vals = list(miljo_verdier)
        if len(names) != len(vals):
            return "/* feil: navn/miljø-verdier må ha samme lengde */"
        env = {n: vals[i] for i, n in enumerate(names)}
        operatorer: list[str] = []
        operator_pos: list[int] = []
        i = 0
        siste_token = -1
        forventer_verdi = True

        if self.expr_probe:
            probe = self.expr_probe.lower()
            raw_join = " ".join(toks).lower()
            if probe in raw_join or any(probe in str(t).lower() for t in toks):
                self._record_expr_probe([
                    f"[expr-probe] helper=selfhost.compiler.uttrykk_til_ops_og_verdier_med_miljo",
                    f"[expr-probe] raw_tokens={toks!r}",
                    f"[expr-probe] env_names={names!r}",
                    f"[expr-probe] env_values={vals!r}",
                ])

        def token_pos(pos: int) -> str:
            return f"token {pos}"

        while i < len(toks):
            tok_raw = toks[i]
            tok = str(self._call_hot_selfhost_helper("selfhost.compiler.normaliser_norsk_token", [tok_raw]))
            tok_step = 1
            n1 = str(self._call_hot_selfhost_helper("selfhost.compiler.normaliser_norsk_token", [toks[i + 1]])) if i + 1 < len(toks) else ""
            n2 = str(self._call_hot_selfhost_helper("selfhost.compiler.normaliser_norsk_token", [toks[i + 2]])) if i + 2 < len(toks) else ""
            n3 = str(self._call_hot_selfhost_helper("selfhost.compiler.normaliser_norsk_token", [toks[i + 3]])) if i + 3 < len(toks) else ""
            # compact normalizations for common multi-token forms
            if i + 1 < len(toks) and tok_raw == "-" and n1 == ">":
                tok = "impliserer"; tok_step = 2
            elif i + 1 < len(toks) and tok_raw == "=" and n1 == ">":
                tok = "impliserer"; tok_step = 2
            elif tok_raw in {"->", "=>"}:
                tok = "impliserer"; tok_step = 1
            elif tok_raw == "<-":
                tok = "impliseres_av"; tok_step = 1
            elif tok_raw in {"<->", "<=>"}:
                tok = "xnor"; tok_step = 1
            elif i + 2 < len(toks) and tok == "er" and n1 == "mindre" and n2 == "enn":
                tok = "mindre_enn"; tok_step = 3
            elif i + 3 < len(toks) and tok == "er" and n1 == "mindre" and n2 == "eller" and n3 == "lik":
                tok = "mindre_eller_lik"; tok_step = 4
            elif i + 3 < len(toks) and tok == "er" and n1 == "storre" and n2 == "eller" and n3 == "lik":
                tok = "storre_eller_lik"; tok_step = 4
            elif i + 2 < len(toks) and tok == "er" and n1 == "storre" and n2 == "enn":
                tok = "storre_enn"; tok_step = 3
            elif i + 3 < len(toks) and tok == "er" and n1 == "ikke" and n2 == "lik" and n3 == "med":
                tok = "ikke_er"; tok_step = 4
            elif i + 2 < len(toks) and tok == "er" and n1 == "ikke" and n2 == "lik":
                tok = "ikke_er"; tok_step = 3
            elif i + 2 < len(toks) and tok == "ikke" and n1 == "lik" and n2 == "med":
                tok = "ikke_er"; tok_step = 3
            elif i + 2 < len(toks) and tok == "er" and n1 == "lik" and n2 == "med":
                tok = "er"; tok_step = 3
            elif i + 2 < len(toks) and tok == "ikke" and n1 == "er" and n2 == "to":
                tok = "ikke_er"; tok_step = 3
            elif i + 2 < len(toks) and tok == "er" and n1 == "ikke" and n2 == "er":
                tok = "ikke_er"; tok_step = 3
            elif i + 1 < len(toks) and tok == "er" and n1 == "ulik":
                tok = "ikke_er"; tok_step = 2
            elif i + 1 < len(toks) and tok == "ikke" and n1 == "lik":
                tok = "ikke_er"; tok_step = 2
            elif i + 1 < len(toks) and tok == "er" and n1 == "ikke":
                tok = "ikke_er"; tok_step = 2
            elif i + 1 < len(toks) and tok == "ikke" and n1 == "er":
                tok = "ikke_er"; tok_step = 2
            elif i + 1 < len(toks) and tok == "er" and n1 == "lik":
                tok = "er"; tok_step = 2
            elif i + 2 < len(toks) and tok == "mindre" and n1 == "eller" and n2 == "lik":
                tok = "mindre_eller_lik"; tok_step = 3
            elif i + 2 < len(toks) and tok == "storre" and n1 == "eller" and n2 == "lik":
                tok = "storre_eller_lik"; tok_step = 3
            elif i + 1 < len(toks) and tok == "mindre" and n1 == "enn":
                tok = "mindre_enn"; tok_step = 2
            elif i + 1 < len(toks) and tok == "storre" and n1 == "enn":
                tok = "storre_enn"; tok_step = 2
            elif i + 1 < len(toks) and tok in {"pluss", "plus", "legg", "legge", "legges", "plusser", "pluses", "plusses", "plusse", "adder", "addere", "adderer", "adderes", "summer", "summerer", "summeres"} and n1 in {"med", "til", "sammen"}:
                tok = "+"; tok_step = 2
            elif i + 1 < len(toks) and tok in {"minus", "trekk", "trekke", "trekkes", "minuseres", "subtraher", "subtraherer", "subtraheres", "subtrahert"} and n1 in {"med", "fra"}:
                tok = "-"; tok_step = 2
            elif i + 1 < len(toks) and tok in {"gang", "gange", "ganget", "ganger", "ganges", "multipliser", "multiplisere", "multipliserer", "multiplisert", "multipliseres"} and n1 == "med":
                tok = "*"; tok_step = 2
            elif i + 2 < len(toks) and tok in {"dele", "deler", "divider", "dividere", "dividerer"} and n1 == "seg" and n2 in {"med", "pa", "paa"}:
                tok = "/"; tok_step = 3
            elif i + 1 < len(toks) and tok in {"delt", "dele", "deler", "deles", "del", "dividere", "divider", "dividerer", "dividert", "divideres"} and n1 in {"med", "pa", "paa"}:
                tok = "/"; tok_step = 2
            elif i + 1 < len(toks) and tok in {"mod", "modulo", "modul", "modulus", "rest", "resten"} and n1 == "av":
                tok = "%"; tok_step = 2
            elif tok in {"pluss", "plus", "legg", "legge", "legges", "plusser", "pluses", "plusses", "plusse", "adder", "addere", "adderer", "adderes", "summer", "summerer", "summeres", "pluss_med", "plus_med", "plusser_med", "plusses_med", "pluses_med", "plusse_med", "adder_med", "addere_med", "adderer_med", "adderes_med", "summer_med", "summerer_med", "summeres_med", "legg_til", "legge_til", "legges_til", "legg_sammen", "legge_sammen", "legges_sammen"}:
                tok = "+"; tok_step = 1
            elif tok in {"minus", "trekk", "trekke", "trekkes", "minuseres", "subtraher", "subtraherer", "subtraheres", "subtrahert", "trekk_fra", "trekke_fra", "trekkes_fra", "minus_fra", "minuseres_fra", "subtraher_fra", "subtraherer_fra", "subtraheres_fra", "subtrahert_fra", "minus_med", "minuseres_med", "trekk_med", "trekke_med", "trekkes_med", "subtraher_med", "subtraherer_med", "subtraheres_med", "subtrahert_med"}:
                tok = "-"; tok_step = 1
            elif tok in {"gang", "gange", "ganget", "ganger", "ganges", "multipliser", "multiplisere", "multipliserer", "multiplisert", "multipliseres", "gang_med", "ganget_med", "gange_med", "ganger_med", "ganges_med", "multipliser_med", "multiplisere_med", "multipliserer_med", "multiplisert_med", "multipliseres_med"}:
                tok = "*"; tok_step = 1
            elif tok in {"delt", "dele", "deler", "deles", "del", "dividere", "divider", "dividerer", "dividert", "divideres", "delt_pa", "deler_pa", "dele_pa", "deles_pa", "del_pa", "delt_med", "dele_med", "deler_med", "deles_med", "del_med", "dividere_pa", "divider_pa", "dividerer_pa", "dividert_pa", "divideres_pa", "dividere_med", "divider_med", "dividerer_med", "dividert_med", "divideres_med"}:
                tok = "/"; tok_step = 1
            elif tok in {"mod", "modulo", "modul", "modulus", "rest", "resten", "mod_av", "modulo_av", "modul_av", "modulus_av", "rest_av", "resten_av"}:
                tok = "%"; tok_step = 1
            elif tok.startswith(("minus", "trekk", "subtraher")) and tok.endswith(("med", "fra")):
                tok = "-"; tok_step = 1
            elif tok.startswith(("pluss", "plus", "legg", "adder", "summer")) and tok.endswith(("med", "til", "sammen")):
                tok = "+"; tok_step = 1
            elif tok.startswith(("gang", "multipliser")) and tok.endswith("med"):
                tok = "*"; tok_step = 1
            elif tok.startswith(("delt", "del", "dele", "deler", "deles", "divider", "dividere", "dividerer", "dividert", "divideres")) and tok.endswith(("med", "pa", "paa")):
                tok = "/"; tok_step = 1
            elif tok.startswith(("mod", "modulo", "modul", "modulus", "rest", "resten")) and tok.endswith("av"):
                tok = "%"; tok_step = 1
            elif tok in {"lik"}:
                tok = "er"; tok_step = 1
            elif tok in {"ulik", "ikke_lik"}:
                tok = "ikke_er"; tok_step = 1

            if tok == "":
                i += 1
                continue

            is_int = self._call_hot_selfhost_helper("selfhost.compiler.er_heltall_token", [tok])
            if is_int:
                if not forventer_verdi:
                    return f"/* feil: mangler operator før verdi {tok} ved {token_pos(i)} */"
                ops.append("PUSH"); verdier.append(int(tok))
                forventer_verdi = False
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            if tok in {"sann", "usann"}:
                if not forventer_verdi:
                    return f"/* feil: mangler operator før verdi {tok} ved {token_pos(i)} */"
                ops.append("PUSH"); verdier.append(1 if tok == "sann" else 0)
                forventer_verdi = False
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            if forventer_verdi and tok in env:
                ops.append("PUSH"); verdier.append(int(env[tok]))
                forventer_verdi = False
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            if tok == "(":
                if not forventer_verdi:
                    return f"/* feil: mangler operator før ( ved {token_pos(i)} */"
                operatorer.append(tok); operator_pos.append(i)
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            if tok == ")":
                if forventer_verdi:
                    return f"/* feil: mangler verdi før ) ved {token_pos(i)} */"
                fant = False
                while operatorer:
                    top = operatorer.pop(); top_pos = operator_pos.pop()
                    if top == "(":
                        fant = True
                        break
                    if not self._selfhost_emit_operator(ops, verdier, top):
                        return f"/* feil: ukjent operator {top} ved {token_pos(top_pos)} */"
                if not fant:
                    return f"/* feil: ) uten matchende ( ved {token_pos(i)} */"
                forventer_verdi = False
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            if self._selfhost_is_operator_token(tok):
                if forventer_verdi:
                    if tok == "!":
                        operatorer.append("u!"); operator_pos.append(i); siste_token = i; i += tok_step; continue
                    if tok == "ikke":
                        operatorer.append("uikke"); operator_pos.append(i); siste_token = i; i += tok_step; continue
                    if tok == "-":
                        operatorer.append("u-"); operator_pos.append(i); siste_token = i; i += tok_step; continue
                    if tok == "+":
                        siste_token = i; i += tok_step; continue
                    return f"/* feil: mangler verdi før operator {tok} ved {token_pos(i)} */"
                while operatorer:
                    top = operatorer[-1]; top_pos = operator_pos[-1]
                    if top == "(":
                        break
                    if self._selfhost_operator_precedence(top) < self._selfhost_operator_precedence(tok):
                        break
                    operatorer.pop(); operator_pos.pop()
                    if not self._selfhost_emit_operator(ops, verdier, top):
                        return f"/* feil: ukjent operator {top} ved {token_pos(top_pos)} */"
                operatorer.append(tok); operator_pos.append(i)
                forventer_verdi = True
                siste_token = i + tok_step - 1
                i += tok_step
                continue

            return f"/* feil: ukjent token/navn i uttrykk {tok} ved {token_pos(i)} */"

        if forventer_verdi:
            if siste_token >= 0:
                return f"/* feil: uttrykket avsluttes med operator ved {token_pos(siste_token)} */"
            return "/* feil: uttrykket avsluttes med operator */"

        while operatorer:
            top = operatorer.pop(); top_pos = operator_pos.pop()
            if top == "(":
                return f"/* feil: mangler ) i uttrykk ved {token_pos(top_pos)} */"
            if not self._selfhost_emit_operator(ops, verdier, top):
                return f"/* feil: ukjent operator {top} ved {token_pos(top_pos)} */"
        return ""

    def _call_hot_selfhost_helper(self, name: str, args: list[Any]) -> Any:
        if name == "selfhost.compiler.normaliser_norsk_token":
            tok = str(args[0]) if args else ""
            return self._selfhost_token_map.get(tok, tok)
        if name == "selfhost.compiler.op_krever_arg":
            op = str(args[0]) if args else ""
            return op in {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD"}
        if name == "selfhost.compiler.op_kjent":
            op = str(args[0]) if args else ""
            return op in {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD", "ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "GT", "LT", "AND", "OR", "NOT", "DUP", "POP", "SWAP", "OVER", "PRINT", "HALT", "RET"}
        if name == "selfhost.compiler.er_heltall_token":
            tok = str(args[0]) if args else ""
            try:
                return str(int(tok)) == tok
            except Exception:
                return False
        if name == "selfhost.compiler.operator_til_opcode":
            tok = str(args[0]) if args else ""
            mapping = {
                "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "%": "MOD",
                "==": "EQ", "er": "EQ", "<": "LT", "mindre_enn": "LT",
                ">": "GT", "storre_enn": "GT", "&&": "AND", "og": "AND",
                "samt": "AND", "||": "OR", "eller": "OR", "enten": "OR",
            }
            return mapping.get(tok, "")
        if name == "selfhost.compiler.stack_behov":
            op = str(args[0]) if args else ""
            if op in {"ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "GT", "LT", "AND", "OR", "OVER", "SWAP"}:
                return 2
            if op in {"NOT", "POP", "DUP", "STORE", "PRINT", "JZ"}:
                return 1
            return 0
        if name == "selfhost.compiler.stack_endring":
            op = str(args[0]) if args else ""
            if op in {"PUSH", "LOAD", "DUP", "OVER"}:
                return 1
            if op in {"ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "GT", "LT", "AND", "OR", "POP", "STORE"}:
                return -1
            return 0
        if name == "selfhost.compiler.uttrykk_til_ops_og_verdier_med_miljo":
            tokens = args[0] if len(args) > 0 else []
            navn = args[1] if len(args) > 1 else []
            miljo_verdier = args[2] if len(args) > 2 else []
            ops = args[3] if len(args) > 3 else []
            verdier = args[4] if len(args) > 4 else []
            return self._hot_selfhost_expr_to_ops(tokens, navn, miljo_verdier, ops, verdier)
        if name == "selfhost.compiler.instruksjon_til_tekst":
            op = str(args[0]) if len(args) > 0 else ""
            verdi = int(args[1]) if len(args) > 1 else 0
            if op in {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD"}:
                return op + " " + str(verdi)
            return op
        if name == "selfhost.compiler.append_linje":
            kilde = str(args[0]) if len(args) > 0 else ""
            linje = str(args[1]) if len(args) > 1 else ""
            return kilde + linje + "\n"
        if name == "selfhost.compiler.disasm_program":
            ops = list(args[0]) if len(args) > 0 else []
            verdier = list(args[1]) if len(args) > 1 else []
            if len(ops) != len(verdier):
                return "/* feil: ops og verdier må ha samme lengde */"
            out = []
            for i, op in enumerate(ops):
                if op in {"PUSH", "LABEL", "JMP", "JZ", "CALL", "STORE", "LOAD"}:
                    instr = f"{op} {verdier[i]}"
                else:
                    instr = str(op)
                out.append(f"{i}: {instr}")
            return "\n".join(out) + ("\n" if out else "")
        raise BytecodeRuntimeError(f"Ukjent hot selfhost helper: {name}")

    def _sass_replace_variables(self, text: str, variables: dict[str, str]) -> str:
        result = text
        for name, value in variables.items():
            result = result.replace(f"${name}", value)
        return result

    def _sass_to_css(self, source: str) -> str:
        variables: dict[str, str] = {}
        selector_stack: list[str] = []
        output: list[str] = []
        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("/*") or line.startswith("*"):
                continue
            if line.startswith("$") and ":" in line and line.endswith(";"):
                name, value = line[1:].split(":", 1)
                variables[name.strip()] = self._sass_replace_variables(value.strip().rstrip(";"), variables)
                continue
            line = self._sass_replace_variables(line, variables)
            if line.endswith("{"):
                selector = line[:-1].strip()
                if selector.startswith("&") and selector_stack:
                    selector = selector.replace("&", selector_stack[-1], 1)
                elif selector_stack:
                    selector = f"{selector_stack[-1]} {selector}"
                selector_stack.append(selector)
                continue
            if line == "}":
                if selector_stack:
                    selector_stack.pop()
                continue
            if ":" in line and line.endswith(";"):
                current_selector = selector_stack[-1] if selector_stack else ""
                if current_selector:
                    output.append(f"{current_selector} {{ {line} }}")
                else:
                    output.append(line)
                continue
        return "\n".join(output) + ("\n" if output else "")

    def run(self, entry: str | None = None) -> Any:
        target = entry or self.program.get("entry") or "__main__.start"
        return self.call_function(target, [])

    def call_function(self, name: str, args: list[Any]) -> Any:
        if name.startswith("selfhost.compiler.") and name.rsplit(".", 1)[-1] in {
            "normaliser_norsk_token", "op_krever_arg", "op_kjent", "er_heltall_token", "operator_til_opcode", "stack_behov", "stack_endring", "uttrykk_til_ops_og_verdier_med_miljo", "instruksjon_til_tekst", "append_linje", "disasm_program"
        }:
            return self._call_hot_selfhost_helper(name, args)
        if name in self._memoizable_functions:
            memo_key = (name, repr(args))
            if memo_key in self._memo_cache:
                return self._memo_cache[memo_key]
        else:
            memo_key = None
        if name.startswith("builtin."):
            return self.call_builtin(name.removeprefix("builtin."), args)
        if name == "std.math.pluss":
            return args[0] + args[1]
        if name == "std.math.minus":
            return args[0] - args[1]
        fn = self.functions.get(name)
        if fn is None:
            resolved_name = self._resolve_function_name(name)
            if resolved_name is not None and resolved_name != name:
                name = resolved_name
                fn = self.functions.get(name)
        if fn is None:
            short_name = name.rsplit('.', 1)[-1]
            builtin_like = {
                "assert", "assert_eq", "assert_ne", "skriv", "lengde",
                "tekst_fra_heltall", "tekst_fra_bool", "tekst_til_små", "tekst_til_store", "tekst_til_tittel", "tekst_omvendt", "tekst_del_på", "del_på", "heltall_fra_tekst", "tekst_trim", "tekst_slice", "tekst_lengde", "tekst_slutter_med", "tekst_starter_med", "tekst_inneholder", "tekst_erstatt", "del_linjer",
            "sass_til_css", "del_ord", "tokeniser_enkel", "tokeniser_uttrykk", "les_input",
            "web_server_start",
                "legg_til", "pop_siste", "fjern_indeks", "sett_inn",
                "gui_vindu", "gui_panel", "gui_tekst", "gui_tekstboks", "gui_liste",
                "gui_liste_legg_til", "gui_liste_tom",
                "gui_på_klikk", "gui_på_endring", "gui_på_tast", "gui_trykk", "gui_trykk_tast",
                "gui_foresatt", "gui_barn",
                "gui_knapp", "gui_etikett", "gui_tekstfelt", "gui_editor", "gui_editor_hopp_til", "gui_editor_cursor", "gui_editor_erstatt_fra_til",
                "gui_sett_tekst", "gui_hent_tekst", "gui_vis", "gui_lukk",
                "les_fil", "skriv_fil", "fil_eksisterer", "db_open", "db_close", "db_begin", "db_commit", "db_rollback", "db_exec", "db_query",
                "argv", "kjør_kommando", "kjor_kilde",
            }
            if short_name in builtin_like:
                return self.call_builtin(short_name, args)
            raise BytecodeRuntimeError(f"Ukjent funksjon: {name}")
        params = fn.get("params", [])
        if len(args) != len(params):
            raise BytecodeRuntimeError(
                f"Funksjonen {name} forventer {len(params)} argument(er), fikk {len(args)}"
            )
        locals_: dict[str, Any] = {param: value for param, value in zip(params, args)}
        code = fn.get("code", [])
        labels = {instr[1]: idx for idx, instr in enumerate(code) if instr[0] == "LABEL"}
        stack: list[Any] = []
        ip = 0
        while ip < len(code):
            self.steps += 1
            if self.steps > self.max_steps:
                raise BytecodeRuntimeError(f"Maks steg overskredet ({self.max_steps}) i {name} ved ip={ip}")
            instr = code[ip]
            op = instr[0]
            local_preview = {key: locals_[key] for key in list(locals_.keys())[:6]}
            if self._should_trace_function(name):
                self._log(f"step={self.steps} fn={name} ip={ip} op={instr!r} stack={stack[-4:]} locals={local_preview}")
            if self.repeat_limit > 0:
                state_key = (name, ip, tuple(instr), repr(stack[-4:]), repr(local_preview))
                if state_key == self._repeat_state_key:
                    self._repeat_state_count += 1
                else:
                    self._repeat_state_key = state_key
                    self._repeat_state_count = 1
                if self._repeat_state_count > self.repeat_limit:
                    raise BytecodeRuntimeError(
                        f"Mulig fastlås/løkke oppdaget i {name} ved ip={ip} op={instr!r} "
                        f"(samme tilstand > {self.repeat_limit} ganger)"
                    )
            if op == "LABEL":
                ip += 1
                continue
            if op == "PUSH_CONST":
                stack.append(instr[1])
            elif op == "LOAD_NAME":
                name2 = instr[1]
                if name2 not in locals_:
                    raise BytecodeRuntimeError(f"Ukjent variabel: {name2}")
                stack.append(locals_[name2])
            elif op == "STORE_NAME":
                locals_[instr[1]] = stack.pop()
            elif op == "POP":
                if stack:
                    stack.pop()
            elif op == "BUILD_LIST":
                n = instr[1]
                items = stack[-n:] if n else []
                if n:
                    del stack[-n:]
                stack.append(items)
            elif op == "INDEX_GET":
                idx = stack.pop(); lst = stack.pop(); stack.append(lst[idx])
            elif op == "INDEX_SET":
                value = stack.pop(); idx = stack.pop(); lst = stack.pop(); lst[idx] = value
            elif op == "UNARY_NEG":
                stack.append(-stack.pop())
            elif op == "UNARY_NOT":
                stack.append(not stack.pop())
            elif op == "BINARY_ADD":
                b = stack.pop(); a = stack.pop(); stack.append(a + b)
            elif op == "BINARY_SUB":
                b = stack.pop(); a = stack.pop(); stack.append(a - b)
            elif op == "BINARY_MUL":
                b = stack.pop(); a = stack.pop(); stack.append(a * b)
            elif op == "BINARY_DIV":
                b = stack.pop(); a = stack.pop(); stack.append(a / b)
            elif op == "COMPARE_EQ":
                b = stack.pop(); a = stack.pop(); stack.append(a == b)
            elif op == "COMPARE_NE":
                b = stack.pop(); a = stack.pop(); stack.append(a != b)
            elif op == "COMPARE_GT":
                b = stack.pop(); a = stack.pop(); stack.append(a > b)
            elif op == "COMPARE_LT":
                b = stack.pop(); a = stack.pop(); stack.append(a < b)
            elif op == "COMPARE_GE":
                b = stack.pop(); a = stack.pop(); stack.append(a >= b)
            elif op == "COMPARE_LE":
                b = stack.pop(); a = stack.pop(); stack.append(a <= b)
            elif op == "BINARY_AND":
                b = stack.pop(); a = stack.pop(); stack.append(bool(a) and bool(b))
            elif op == "BINARY_OR":
                b = stack.pop(); a = stack.pop(); stack.append(bool(a) or bool(b))
            elif op == "CALL":
                target, argc = instr[1], instr[2]
                call_args = stack[-argc:] if argc else []
                if argc:
                    del stack[-argc:]
                stack.append(self.call_function(target, call_args))
            elif op == "JUMP":
                ip = labels[instr[1]]
                continue
            elif op == "JUMP_IF_FALSE":
                value = stack.pop()
                if not value:
                    ip = labels[instr[1]]
                    continue
            elif op == "RETURN":
                result = stack.pop() if stack else None
                if memo_key is not None:
                    self._memo_cache[memo_key] = result
                return result
            else:
                raise BytecodeRuntimeError(f"Ukjent opcode: {op}")
            ip += 1
        if memo_key is not None:
            self._memo_cache[memo_key] = None
        return None

    def call_builtin(self, name: str, args: list[Any]) -> Any:
        if name == "skriv":
            text = " ".join(str(x) for x in args)
            print(text)
            self.output.append(text)
            return None
        if name == "assert":
            if not args[0]:
                raise AssertionError("Assert feilet")
            return None
        if name == "assert_eq":
            if args[0] != args[1]:
                raise AssertionError(f"assert_eq feilet: {args[0]!r} != {args[1]!r}")
            return None
        if name == "assert_ne":
            if args[0] == args[1]:
                raise AssertionError(f"assert_ne feilet: {args[0]!r} == {args[1]!r}")
            return None
        if name == "lengde":
            return len(args[0])
        if name == "tekst_fra_heltall":
            return str(args[0])
        if name == "tekst_fra_bool":
            return "sann" if args[0] else "usann"
        if name == "tekst_til_små":
            return str(args[0]).lower()
        if name == "tekst_til_store":
            return str(args[0]).upper()
        if name == "tekst_til_tittel":
            text = str(args[0])
            out = []
            new_word = True
            for ch in text:
                if ch.isalpha() or ch.isdigit() or ch == "_" or ch in "æøåÆØÅ":
                    out.append(ch.upper() if new_word else ch.lower())
                    new_word = False
                else:
                    out.append(ch)
                    new_word = True
            return "".join(out)
        if name == "tekst_omvendt":
            return str(args[0])[::-1]
        if name == "tekst_del_på":
            text = str(args[0])
            separator = str(args[1] if len(args) > 1 else "")
            if separator == "":
                return [text]
            return text.split(separator)
        if name == "del_på":
            text = str(args[0]) if args else ""
            separator = str(args[1]) if len(args) > 1 else ""
            if separator == "":
                return [text]
            return text.split(separator)
        if name == "tekst_trim":
            return str(args[0]).strip()
        if name == "tekst_slice":
            text = str(args[0]) if args else ""
            start = int(args[1]) if len(args) > 1 else 0
            end = int(args[2]) if len(args) > 2 else len(text)
            if start < 0:
                start = 0
            if end < start:
                end = start
            if start > len(text):
                start = len(text)
            if end > len(text):
                end = len(text)
            return text[start:end]
        if name == "tekst_lengde":
            return len(str(args[0]))
        if name == "heltall_fra_tekst":
            try:
                return int(str(args[0]).strip())
            except Exception:
                return 0
        if name == "tekst_slutter_med":
            return str(args[0]).endswith(str(args[1] if len(args) > 1 else ""))
        if name == "tekst_starter_med":
            return str(args[0]).startswith(str(args[1] if len(args) > 1 else ""))
        if name == "tekst_inneholder":
            return str(args[1] if len(args) > 1 else "") in str(args[0])
        if name == "tekst_erstatt":
            return str(args[0]).replace(str(args[1] if len(args) > 1 else ""), str(args[2] if len(args) > 2 else ""))
        if name == "del_linjer":
            return str(args[0]).split("\n")
        if name == "del_ord":
            return str(args[0]).split()
        if name == "tekst_er_ordtegn":
            text = str(args[0])
            return len(text) == 1 and (text[0].isalnum() or text in "_æøåÆØÅ")
        if name == "tokeniser_enkel":
            text = str(args[0])
            tokens = []
            current = []
            in_comment = False
            for ch in text:
                if in_comment:
                    if ch == "\n":
                        in_comment = False
                    continue
                if ch == '#':
                    if current:
                        tokens.append(''.join(current))
                        current = []
                    in_comment = True
                    continue
                if ch.isalnum() or ch in '_-':
                    current.append(ch)
                else:
                    if current:
                        tokens.append(''.join(current))
                        current = []
            if current:
                tokens.append(''.join(current))
            return tokens
        if name == "tokeniser_uttrykk":
            text = str(args[0])
            token_re = re.compile(r'<=>|<->|=>|->|<-|&&|\|\||\+=|-=|\*=|/=|%=|==|!=|<=|>=|<>|[=!(){}\[\],.:;+\-*/%<>]|"[^"\\]*(?:\\.[^"\\]*)*"|[A-Za-zÆØÅæøå_][A-Za-zÆØÅæøå0-9_]*|\d+|\S')
            return [m.group(0) for m in token_re.finditer(text) if m.group(0).strip()]
        if name == "les_input":
            return ""
        if name == "legg_til":
            args[0].append(args[1])
            return None
        if name == "pop_siste":
            if not args[0]:
                return "" if isinstance(args[0], list) and any(isinstance(x, str) for x in args[0]) else 0
            return args[0].pop()
        if name == "fjern_indeks":
            if args[1] < 0 or args[1] >= len(args[0]):
                return len(args[0])
            args[0].pop(args[1])
            return len(args[0])
        if name == "sett_inn":
            lst = args[0]
            idx = int(args[1])
            value = args[2]
            if idx < 0:
                idx = 0
            if idx < len(lst):
                lst[idx] = value
            elif idx == len(lst):
                lst.append(value)
            else:
                while len(lst) < idx:
                    lst.append(0 if not lst or not isinstance(lst[0], str) else "")
                lst.append(value)
            return None
        if name == "gui_vindu":
            return self._gui_create("window", None, args[0] if args else "")
        if name == "gui_panel":
            return self._gui_create("panel", self._gui_parent_id(args[0] if args else None), "")
        if name == "gui_rad":
            return self._gui_create("row", self._gui_parent_id(args[0] if args else None), "")
        if name == "gui_tekst":
            return self._gui_create("text", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_tekstboks":
            return self._gui_create("text_field", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_editor":
            return self._gui_create("editor", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_editor_hopp_til":
            return self._gui_editor_jump_to_line(int(args[0]), int(args[1]) if len(args) > 1 else 1)
        if name == "gui_editor_cursor":
            return self._gui_editor_cursor(int(args[0]))
        if name == "gui_editor_erstatt_fra_til":
            return self._gui_editor_replace_range(
                int(args[0]),
                int(args[1]) if len(args) > 1 else 1,
                int(args[2]) if len(args) > 2 else 1,
                int(args[3]) if len(args) > 3 else int(args[1]) if len(args) > 1 else 1,
                int(args[4]) if len(args) > 4 else int(args[2]) if len(args) > 2 else 1,
                args[5] if len(args) > 5 else "",
            )
        if name == "gui_liste":
            return self._gui_create("list", self._gui_parent_id(args[0] if args else None), "")
        if name == "gui_liste_legg_til":
            return self._gui_list_add(int(args[0]), args[1] if len(args) > 1 else "")
        if name == "gui_liste_tom":
            return self._gui_list_clear(int(args[0]))
        if name == "gui_liste_antall":
            return self._gui_list_len(int(args[0]))
        if name == "gui_liste_hent":
            return self._gui_list_get(int(args[0]), int(args[1]) if len(args) > 1 else 0)
        if name == "gui_liste_fjern":
            return self._gui_list_remove(int(args[0]), int(args[1]) if len(args) > 1 else 0)
        if name == "gui_liste_valgt":
            return self._gui_list_selected_text(int(args[0]))
        if name == "gui_liste_velg":
            return self._gui_list_select(int(args[0]), int(args[1]) if len(args) > 1 else 0)
        if name == "gui_liste_filer_tre":
            from pathlib import Path

            root = Path(str(args[0] if args else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []

            def walk(path: Path, prefix: str = "") -> None:
                entries = sorted(
                    [child for child in path.iterdir() if not child.name.startswith(".") and child.name not in {"build", "dist", "__pycache__", ".venv"}],
                    key=lambda child: (not child.is_dir(), child.name.lower()),
                )
                for child in entries:
                    if child.is_dir():
                        result.append(f"{prefix}{child.name}/")
                        walk(child, prefix + "  ")
                    elif child.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            rel = child.relative_to(root)
                            result.append(f"{prefix}{rel.as_posix()}")
                        except Exception:
                            result.append(f"{prefix}{child.name}")

            walk(root)
            return result
        if name == "gui_på_klikk":
            return self._gui_register_click(int(args[0]), args[1] if len(args) > 1 else "")
        if name == "gui_på_endring":
            return self._gui_register_change(int(args[0]), args[1] if len(args) > 1 else "")
        if name == "gui_på_tast":
            return self._gui_register_key(int(args[0]), args[1] if len(args) > 1 else "", args[2] if len(args) > 2 else "")
        if name == "gui_trykk":
            return self._gui_trigger_click(int(args[0]))
        if name == "gui_trykk_tast":
            return self._gui_trigger_key(int(args[0]), args[1] if len(args) > 1 else "")
        if name == "gui_foresatt":
            return self._gui_parent_of(int(args[0]))
        if name == "gui_barn":
            return self._gui_child_at(int(args[0]), int(args[1]) if len(args) > 1 else 0)
        if name == "fil_eksisterer":
            from pathlib import Path

            return Path(str(args[0])).expanduser().exists()
        if name == "les_miljo":
            import os

            return os.environ.get(str(args[0]), "")
        if name == "argv":
            import os

            raw_args = os.environ.get("NORSCODE_ARGS", "")
            return [line for line in raw_args.splitlines() if line != ""]
        if name == "sass_til_css":
            return self._sass_to_css(str(args[0]))
        if name == "web_server_start":
            routes = self._parse_web_routes(args[0] if args else [])
            host = str(args[1]) if len(args) > 1 else "127.0.0.1"
            port = int(args[2]) if len(args) > 2 else 8000
            return self._serve_web_app(routes, host, port)
        if name == "kjør_kommando":
            command = [str(item) for item in (args[0] if args else [])]
            if not command:
                return 1
            completed = subprocess.run(command, check=False)
            return int(completed.returncode)
        if name == "liste_filer":
            from pathlib import Path

            root = Path(str(args[0] if args else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []
            for path in sorted(root.rglob("*")):
                if path.is_file() and not any(part.startswith(".") for part in path.parts):
                    if path.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            result.append(str(path.relative_to(root)))
                        except Exception:
                            result.append(str(path))
            return result
        if name == "liste_filer_tre" or name == "gui_liste_filer_tre":
            from pathlib import Path

            root = Path(str(args[0] if args else ".")).expanduser()
            if not root.exists():
                return []
            result: list[str] = []

            def walk(path: Path, prefix: str = "") -> None:
                entries = sorted(
                    [child for child in path.iterdir() if not child.name.startswith(".") and child.name not in {"build", "dist", "__pycache__", ".venv"}],
                    key=lambda child: (not child.is_dir(), child.name.lower()),
                )
                for child in entries:
                    if child.is_dir():
                        result.append(f"{prefix}{child.name}/")
                        walk(child, prefix + "  ")
                    elif child.suffix.lower() in {".no", ".md", ".toml", ".py", ".sh", ".ps1"}:
                        try:
                            rel = child.relative_to(root)
                            result.append(f"{prefix}{rel.as_posix()}")
                        except Exception:
                            result.append(f"{prefix}{child.name}")

            walk(root)
            return result
        if name == "les_fil":
            from pathlib import Path

            try:
                return Path(str(args[0])).expanduser().read_text(encoding="utf-8")
            except Exception:
                return ""
        if name == "skriv_fil":
            from pathlib import Path

            path = Path(str(args[0])).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("" if len(args) < 2 or args[1] is None else str(args[1]), encoding="utf-8")
            return 1
        if name == "kjor_kilde":
            from io import StringIO
            from contextlib import redirect_stdout, redirect_stderr
            from .lexer import Lexer
            from .parser import Parser
            from .semantic import SemanticAnalyzer
            from .interpreter import Interpreter

            source = "" if not args else str(args[0])
            buf = StringIO()
            try:
                program = Parser(Lexer(source)).parse()
                SemanticAnalyzer(alias_map=self.alias_map).analyze(program)
                runner = Interpreter(gui_backend="headless", alias_map=self.alias_map)
                with redirect_stdout(buf), redirect_stderr(buf):
                    runner.run(program)
            except Exception as exc:
                return f"Feil: {exc}"
            return buf.getvalue()
        if name == "gui_knapp":
            return self._gui_create("button", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_etikett":
            return self._gui_create("label", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_tekstfelt":
            return self._gui_create("text_field", self._gui_parent_id(args[0] if args else None), args[1] if len(args) > 1 else "")
        if name == "gui_sett_tekst":
            gui_obj = self._gui_get(int(args[0]))
            gui_obj["text"] = "" if len(args) < 2 or args[1] is None else str(args[1])
            if gui_obj.get("kind") == "text_field":
                self._gui_trigger_change(int(args[0]))
            return int(args[0])
        if name == "gui_hent_tekst":
            gui_obj = self._gui_get(int(args[0]))
            return gui_obj.get("text", "")
        if name == "gui_vis":
            gui_obj = self._gui_get(int(args[0]))
            gui_obj["visible"] = True
            return int(args[0])
        if name == "gui_lukk":
            gui_obj = self._gui_get(int(args[0]))
            gui_obj["visible"] = False
            return int(args[0])
        raise BytecodeRuntimeError(f"Ukjent builtin: {name}")

    def _parse_web_routes(self, routes_value: Any) -> list[dict[str, str]]:
        routes: list[dict[str, str]] = []
        if not isinstance(routes_value, list):
            return routes
        for entry in routes_value:
            if not isinstance(entry, str):
                continue
            parts = entry.split("\t")
            if len(parts) >= 3:
                routes.append({"method": parts[0], "pattern": parts[1], "handler": parts[2]})
        return routes

    def _serve_web_app(self, routes: list[dict[str, str]], host: str, port: int) -> int:
        vm = self

        class Handler(BaseHTTPRequestHandler):
            def _dispatch(self, method: str) -> None:
                try:
                    parsed = urlparse(self.path)
                    target_path = parsed.path or "/"
                    query = parsed.query or ""
                    body = ""
                    length = int(self.headers.get("Content-Length", "0") or 0)
                    if length > 0:
                        body = self.rfile.read(length).decode("utf-8")
                    response = vm._dispatch_web_request(routes, method, target_path, query, body)
                    if not response.startswith("HTTP/1.1 "):
                        response = vm._plain_http_response(200, "OK", response)
                except Exception as exc:
                    response = vm._plain_http_response(500, "Internal Server Error", f"Feil: {exc}")
                self.connection.sendall(response.encode("utf-8"))
                self.close_connection = True

            def do_GET(self):  # noqa: N802
                self._dispatch("GET")

            def do_POST(self):  # noqa: N802
                self._dispatch("POST")

            def do_PATCH(self):  # noqa: N802
                self._dispatch("PATCH")

            def log_message(self, *_args):  # noqa: D401
                return None

        server = HTTPServer((host, port), Handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    def _dispatch_web_request(self, routes: list[dict[str, str]], method: str, path: str, query: str, body: str) -> str:
        for route in routes:
            if route["method"] == method and self._path_matches(route["pattern"], path):
                response = self.call_function(
                    route["handler"],
                    [method, path, query, body],
                )
                return response if isinstance(response, str) else str(response)
        return self._plain_http_response(404, "Not Found", "Not Found")

    def _path_matches(self, pattern: str, path: str) -> bool:
        pattern_segments = [segment for segment in pattern.split("/") if segment]
        path_segments = [segment for segment in path.split("/") if segment]
        if len(pattern_segments) != len(path_segments):
            return False
        for left, right in zip(pattern_segments, path_segments):
            if left.startswith("{") and left.endswith("}"):
                continue
            if left != right:
                return False
        return True

    def _plain_http_response(self, status: int, reason: str, body: str) -> str:
        body_bytes = body.encode("utf-8")
        return (
            f"HTTP/1.1 {status} {reason}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            "\r\n"
            f"{body}"
        )

    def _gui_create(self, kind: str, parent_id: int | None, text: str | None) -> int:
        object_id = self.gui_next_id
        self.gui_next_id += 1
        self.gui_objects[object_id] = {
            "kind": kind,
            "parent": parent_id,
            "text": "" if text is None else str(text),
            "visible": False,
            "items": [] if kind == "list" else None,
            "click_callback": None,
            "change_callback": None,
            "key_callbacks": {},
            "selected_index": -1,
            "cursor_line": 1,
            "cursor_col": 1,
        }
        return object_id

    def _gui_get(self, object_id: int) -> dict[str, Any]:
        if object_id not in self.gui_objects:
            raise BytecodeRuntimeError(f"Ukjent GUI-element: {object_id}")
        return self.gui_objects[object_id]

    def _gui_parent_id(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception as exc:
            raise BytecodeRuntimeError("GUI-forelder må være et heltall") from exc

    def _gui_parent_of(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        parent = obj.get("parent")
        return 0 if parent is None else int(parent)

    def _gui_parent_of(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        parent = obj.get("parent")
        return 0 if parent is None else int(parent)

    def _normalize_key_name(self, key_name: Any) -> str:
        key = "" if key_name is None else str(key_name).strip()
        lowered = key.lower()
        if lowered in {"return", "kp_enter"}:
            return "enter"
        if lowered in {"tab"}:
            return "tab"
        if lowered in {"ctrl+space", "ctrl-space", "control+space", "control-space"}:
            return "ctrl+space"
        return lowered

    def _gui_editor_jump_to_line(self, object_id: int, line_number: int) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "editor":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        line = int(line_number)
        if line < 1:
            line = 1
        obj["cursor_line"] = line
        obj["cursor_col"] = 1
        return object_id

    def _gui_editor_cursor(self, object_id: int) -> list[str]:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "editor":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        return [str(int(obj.get("cursor_line", 1))), str(int(obj.get("cursor_col", 1)))]

    def _gui_register_key(self, object_id: int, key_name: Any, callback_name: Any) -> int:
        obj = self._gui_get(object_id)
        obj.setdefault("key_callbacks", {})[self._normalize_key_name(key_name)] = "" if callback_name is None else str(callback_name)
        return object_id

    def _gui_trigger_key(self, object_id: int, key_name: Any) -> Any:
        obj = self._gui_get(object_id)
        callback_name = obj.setdefault("key_callbacks", {}).get(self._normalize_key_name(key_name))
        if not callback_name or self.callback_runner is None:
            return 0
        return self._call_callback(callback_name, object_id)

    def _replace_text_range(
        self,
        text: str,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
        replacement: str,
    ) -> tuple[str, int, int]:
        lines = str(text).split("\n")
        if not lines:
            lines = [""]
        start_line = max(1, int(start_line))
        start_col = max(1, int(start_col))
        end_line = max(start_line, int(end_line))
        end_col = max(1, int(end_col))
        if start_line > len(lines):
            lines.extend([""] * (start_line - len(lines)))
        if end_line > len(lines):
            lines.extend([""] * (end_line - len(lines)))
        start_idx = start_line - 1
        end_idx = end_line - 1
        prefix = lines[start_idx][: max(0, start_col - 1)]
        suffix = lines[end_idx][max(0, end_col - 1) :]
        if start_idx == end_idx:
            lines[start_idx] = prefix + replacement + suffix
        else:
            lines[start_idx : end_idx + 1] = [prefix + replacement + suffix]
        updated = "\n".join(lines)
        if "\n" in replacement:
            repl_lines = replacement.split("\n")
            return updated, start_line + len(repl_lines) - 1, len(repl_lines[-1]) + 1
        return updated, start_line, start_col + len(replacement)

    def _gui_editor_replace_range(
        self,
        object_id: int,
        start_line: int,
        start_col: int,
        end_line: int,
        end_col: int,
        replacement: str,
    ) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "editor":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en editor")
        updated, cursor_line, cursor_col = self._replace_text_range(
            str(obj.get("text", "")),
            start_line,
            start_col,
            end_line,
            end_col,
            "" if replacement is None else str(replacement),
        )
        obj["text"] = updated
        obj["cursor_line"] = cursor_line
        obj["cursor_col"] = cursor_col
        self._gui_trigger_change(object_id)
        return object_id

    def _gui_child_at(self, parent_id: int, index: int) -> int:
        children = [object_id for object_id, obj in self.gui_objects.items() if obj.get("parent") == parent_id]
        if index < 0 or index >= len(children):
            return 0
        return children[index]

    def _gui_list_add(self, object_id: int, text: Any) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        obj.setdefault("items", []).append("" if text is None else str(text))
        return object_id

    def _gui_list_clear(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        obj["items"] = []
        obj["selected_index"] = -1
        return object_id

    def _gui_list_select(self, object_id: int, index: int) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        previous = int(obj.get("selected_index", -1))
        obj["selected_index"] = index if 0 <= index < len(items) else -1
        if obj["selected_index"] != previous:
            self._gui_trigger_change(object_id)
        return object_id

    def _gui_list_selected_text(self, object_id: int) -> str:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        index = int(obj.get("selected_index", -1))
        if 0 <= index < len(items):
            return str(items[index])
        return ""

    def _gui_list_len(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        return len(obj.setdefault("items", []))

    def _gui_list_get(self, object_id: int, index: int) -> str:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        if 0 <= index < len(items):
            return str(items[index])
        return ""

    def _gui_list_remove(self, object_id: int, index: int) -> int:
        obj = self._gui_get(object_id)
        if obj.get("kind") != "list":
            raise BytecodeRuntimeError(f"GUI-elementet {object_id} er ikke en liste")
        items = obj.setdefault("items", [])
        if 0 <= index < len(items):
            items.pop(index)
            selected = int(obj.get("selected_index", -1))
            if selected == index:
                obj["selected_index"] = -1
                self._gui_trigger_change(object_id)
            elif selected > index:
                obj["selected_index"] = selected - 1
        return object_id

    def _gui_register_click(self, object_id: int, callback_name: Any) -> int:
        obj = self._gui_get(object_id)
        obj["click_callback"] = "" if callback_name is None else str(callback_name)
        return object_id

    def _gui_register_change(self, object_id: int, callback_name: Any) -> int:
        obj = self._gui_get(object_id)
        obj["change_callback"] = "" if callback_name is None else str(callback_name)
        return object_id

    def _resolve_callback_name(self, name: str) -> str | None:
        if name in self.functions:
            return name
        short_name = name.rsplit(".", 1)[-1]
        for candidate in self.functions:
            if candidate.rsplit(".", 1)[-1] == short_name:
                return candidate
        return None

    def _gui_trigger_click(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        callback_name = obj.get("click_callback")
        if callback_name:
            resolved = self._resolve_callback_name(str(callback_name))
            if resolved is not None:
                self.call_function(resolved, [object_id])
        return object_id

    def _gui_trigger_change(self, object_id: int) -> int:
        obj = self._gui_get(object_id)
        callback_name = obj.get("change_callback")
        if callback_name:
            resolved = self._resolve_callback_name(str(callback_name))
            if resolved is not None:
                self.call_function(resolved, [object_id])
        return object_id

    def _resolve_function_name(self, name: str) -> str | None:
        if name in self.functions:
            return name
        short_name = name.rsplit(".", 1)[-1]
        for candidate in self.functions:
            if candidate == name or candidate.rsplit(".", 1)[-1] == short_name:
                return candidate
        return None


def compile_program_to_bytecode(program, alias_map: dict[str, str] | None = None) -> dict[str, Any]:
    compiler = BytecodeCompiler(alias_map=alias_map or {})
    payload = compiler.compile_program(program)
    validate_bytecode_payload(payload)
    return payload


def validate_bytecode_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise BytecodeRuntimeError("Bytecode payload må være et objekt")
    if payload.get("format") != BYTECODE_FORMAT:
        raise BytecodeRuntimeError(f"Ugyldig bytecode-format: {payload.get('format')!r}")

    entry = payload.get("entry")
    if not isinstance(entry, str) or not entry.strip():
        raise BytecodeRuntimeError("Bytecode mangler gyldig entry")

    imports = payload.get("imports")
    if not isinstance(imports, list):
        raise BytecodeRuntimeError("Bytecode imports må være en liste")
    for item in imports:
        if not isinstance(item, dict):
            raise BytecodeRuntimeError("Bytecode import må være et objekt")
        if not isinstance(item.get("module"), str) or not isinstance(item.get("alias"), str):
            raise BytecodeRuntimeError("Bytecode import må ha module og alias")

    functions = payload.get("functions")
    if not isinstance(functions, dict):
        raise BytecodeRuntimeError("Bytecode functions må være et objekt")
    if entry not in functions:
        raise BytecodeRuntimeError(f"Bytecode entry finnes ikke: {entry}")

    for fn_key, fn in functions.items():
        if not isinstance(fn_key, str) or not fn_key.strip():
            raise BytecodeRuntimeError("Bytecode funksjonsnøkkel må være tekst")
        if not isinstance(fn, dict):
            raise BytecodeRuntimeError(f"Bytecode-funksjon {fn_key} må være et objekt")

        for field in ("name", "module"):
            if not isinstance(fn.get(field), str) or not fn[field].strip():
                raise BytecodeRuntimeError(f"Bytecode-funksjon {fn_key} mangler gyldig {field}")

        params = fn.get("params")
        if not isinstance(params, list) or any(not isinstance(param, str) for param in params):
            raise BytecodeRuntimeError(f"Bytecode-funksjon {fn_key} har ugyldige params")

        code = fn.get("code")
        if not isinstance(code, list):
            raise BytecodeRuntimeError(f"Bytecode-funksjon {fn_key} mangler code")
        for index, instr in enumerate(code):
            if not isinstance(instr, list) or not instr:
                raise BytecodeRuntimeError(f"Ugyldig bytecode-instruksjon i {fn_key} ved {index}")
            op = instr[0]
            if not isinstance(op, str) or not op:
                raise BytecodeRuntimeError(f"Ugyldig opcode i {fn_key} ved {index}")
            if op not in BYTECODE_ALL_OPS:
                raise BytecodeRuntimeError(f"Ukjent bytecode-opcode {op} i {fn_key} ved {index}")

            if op in BYTECODE_NOARG_OPS and len(instr) != 1:
                raise BytecodeRuntimeError(f"Opcode {op} i {fn_key} skal ikke ha argument")
            if op in BYTECODE_ONEARG_OPS and len(instr) != 2:
                raise BytecodeRuntimeError(f"Opcode {op} i {fn_key} må ha ett argument")
            if op in BYTECODE_TWOARG_OPS and len(instr) != 3:
                raise BytecodeRuntimeError(f"Opcode {op} i {fn_key} må ha to argumenter")

            if op in {"JUMP", "JUMP_IF_FALSE", "LABEL", "LOAD_NAME", "STORE_NAME"}:
                if not isinstance(instr[1], str) or not instr[1].strip():
                    raise BytecodeRuntimeError(f"Opcode {op} i {fn_key} må ha tekst-argument")
            if op == "CALL":
                if not isinstance(instr[1], str) or not instr[1].strip():
                    raise BytecodeRuntimeError(f"Opcode CALL i {fn_key} må ha funksjonsnavn")
                if not isinstance(instr[2], int):
                    raise BytecodeRuntimeError(f"Opcode CALL i {fn_key} må ha heltall for arity")
            if op == "BUILD_LIST" and not isinstance(instr[1], int):
                raise BytecodeRuntimeError(f"Opcode BUILD_LIST i {fn_key} må ha heltall")
            if op == "PUSH_CONST" and len(instr) != 2:
                raise BytecodeRuntimeError(f"Opcode PUSH_CONST i {fn_key} må ha ett argument")


def compile_source_to_bytecode(source_file: str) -> tuple[Path, dict[str, Any]]:
    source_path, program, alias_map = load_source_as_program(source_file)
    payload = compile_program_to_bytecode(program, alias_map=alias_map)
    return source_path, payload


def compile_ast_file_to_bytecode(ast_file: str) -> tuple[Path, dict[str, Any]]:
    ast_path = Path(ast_file).expanduser().resolve()
    program, alias_map = read_ast(str(ast_path))
    payload = compile_program_to_bytecode(program, alias_map=alias_map)
    return ast_path, payload


def default_output_path(source_path: Path) -> Path:
    return source_path.with_suffix('.ncb.json')


def build_command(source_file: str | None = None, output: str | None = None, ast_file: str | None = None) -> Path:
    if source_file:
        source_path, payload = compile_source_to_bytecode(source_file)
    elif ast_file:
        source_path, payload = compile_ast_file_to_bytecode(ast_file)
    else:
        raise RuntimeError("Mangler kildefil eller AST-fil")
    out_path = Path(output).expanduser().resolve() if output else default_output_path(source_path)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    return out_path


def run_command(source_file: str | None = None, bytecode_file: str | None = None, ast_file: str | None = None) -> Any:
    if source_file:
        _source_path, payload = compile_source_to_bytecode(source_file)
    elif ast_file:
        _ast_path, payload = compile_ast_file_to_bytecode(ast_file)
    elif bytecode_file:
        payload = json.loads(Path(bytecode_file).expanduser().read_text(encoding='utf-8'))
    else:
        raise RuntimeError("Mangler kildefil, AST-fil eller bytecode-fil")
    validate_bytecode_payload(payload)
    vm = BytecodeVM(payload)
    return vm.run()


def main():
    parser = argparse.ArgumentParser(prog='python -m compiler.bytecode_backend', description='AST -> bytecode backend (v17)')
    sub = parser.add_subparsers(dest='cmd')

    build = sub.add_parser('build', help='Bygg .no eller .nast.json til .ncb.json')
    build.add_argument('file')
    build.add_argument('--output')
    build.add_argument('--ast', action='store_true', help='Tolker input som .nast.json i stedet for .no')

    run = sub.add_parser('run', help='Kjør fra .no, .nast.json eller .ncb.json')
    run.add_argument('file')
    run.add_argument('--bytecode', action='store_true', help='Tolker input som .ncb.json i stedet for .no')
    run.add_argument('--ast', action='store_true', help='Tolker input som .nast.json i stedet for .no')

    args = parser.parse_args()
    if args.cmd == 'build':
        if args.ast:
            path = build_command(ast_file=args.file, output=args.output)
        else:
            path = build_command(source_file=args.file, output=args.output)
        print(path)
    elif args.cmd == 'run':
        if args.bytecode:
            result = run_command(bytecode_file=args.file)
        elif args.ast:
            result = run_command(ast_file=args.file)
        else:
            result = run_command(source_file=args.file)
        if result is not None:
            print(result)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
