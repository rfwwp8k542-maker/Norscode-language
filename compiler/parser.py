from .lexer import Lexer
from .ast_nodes import *


class Parser:
    IMPORT_NAME_TOKENS = {
        "IDENT",
        "I",
        "TYPE_INT",
        "TYPE_BOOL",
        "TYPE_TEXT",
        "TYPE_LIST_INT",
        "TYPE_LIST_TEXT",
    }

    def __init__(self, lexer: Lexer):
        self.lexer = lexer
        self.current = self.lexer.next_token()
        self.next = self.lexer.next_token()
        self.next2 = self.lexer.next_token()

    def advance(self):
        self.current = self.next
        self.next = self.next2
        self.next2 = self.lexer.next_token()

    def error(self, message):
        raise SyntaxError(f"{message} ved linje {self.current.line}, kolonne {self.current.column}")

    def eat(self, token_type):
        if self.current.typ == token_type:
            self.advance()
        else:
            self.error(f"Forventet {token_type}, fikk {self.current.typ}")

    def eat_name(self):
        if self.current.typ in ("IDENT", "I"):
            value = self.current.value
            self.eat(self.current.typ)
            return value
        self.error(f"Forventet IDENT, fikk {self.current.typ}")

    def eat_import_name(self):
        if self.current.typ in self.IMPORT_NAME_TOKENS:
            value = self.current.value
            self.eat(self.current.typ)
            return value
        self.error(f"Forventet modul- eller aliasnavn, fikk {self.current.typ}")

    def parse(self):
        imports = []
        functions = []
        tests = []
        while self.current.typ == "BRUK":
            imports.append(self.import_stmt())
        while self.current.typ != "EOF":
            if self.current.typ == "TEST":
                tests.append(self.test_block())
            else:
                functions.append(self.function_def())
        try:
            return ProgramNode(imports, functions, tests)
        except TypeError:
            program = ProgramNode(imports, functions)
            setattr(program, "tests", tests)
            return program

    def import_stmt(self):
        self.eat("BRUK")
        if self.current.typ not in self.IMPORT_NAME_TOKENS:
            self.error("Forventet modulnavn etter 'bruk'")

        parts = [self.eat_import_name()]

        while self.current.typ == "DOT":
            self.eat("DOT")
            if self.current.typ not in self.IMPORT_NAME_TOKENS:
                self.error("Forventet modulnavn etter punktum i import")
            parts.append(self.eat_import_name())

        module_name = ".".join(parts)

        alias = None
        if self.current.typ == "SOM":
            self.eat("SOM")
            if self.current.typ not in self.IMPORT_NAME_TOKENS:
                self.error("Forventet aliasnavn etter 'som'")
            alias = self.eat_import_name()

        return ImportNode(module_name, alias)

    def parse_type(self):
        mapping = {
            "TYPE_INT": TYPE_INT,
            "TYPE_BOOL": TYPE_BOOL,
            "TYPE_TEXT": TYPE_TEXT,
            "TYPE_LIST_INT": TYPE_LIST_INT,
            "TYPE_LIST_TEXT": TYPE_LIST_TEXT,
        }
        if self.current.typ in mapping:
            t = mapping[self.current.typ]
            self.eat(self.current.typ)
            return t
        self.error(f"Forventet type, fikk {self.current.typ}")

    def function_def(self):
        self.eat("FUNKSJON")
        name = self.eat_name()
        self.eat("LPAREN")
        params = []
        if self.current.typ != "RPAREN":
            while True:
                pname = self.eat_name()
                self.eat("COLON")
                ptype = self.parse_type()
                params.append(Param(pname, ptype))
                if self.current.typ == "COMMA":
                    self.eat("COMMA")
                    continue
                break
        self.eat("RPAREN")
        self.eat("ARROW")
        return_type = self.parse_type()
        body = self.block()
        return FunctionNode(name, params, return_type, body)

    def block(self):
        self.eat("LBRACE")
        statements = []
        while self.current.typ != "RBRACE":
            statements.append(self.statement())
        self.eat("RBRACE")
        return BlockNode(statements)

    def statement(self):
        if self.current.typ == "LA":
            return self.var_decl()
        if self.current.typ == "SKRIV":
            return self.print_stmt()
        if self.current.typ == "HVIS":
            return self.if_stmt()
        if self.current.typ == "MENS":
            return self.while_stmt()
        if self.current.typ == "FOR":
            return self.for_stmt()
        if self.current.typ == "RETURNER":
            return self.return_stmt()
        if self.current.typ == "BRYT":
            self.eat("BRYT")
            return BreakNode()
        if self.current.typ == "FORTSETT":
            self.eat("FORTSETT")
            return ContinueNode()
        if self.current.typ == "ASSERT":
            return self.assert_stmt()
        if self.current.typ == "ASSERT_EQ":
            return self.assert_eq_stmt()
        if self.current.typ == "ASSERT_NE":
            return self.assert_ne_stmt()

        if self.current.typ in ("IDENT", "I") and self.next.typ == "ASSIGN":
            return self.var_set_stmt()

        if (
            self.current.typ in ("IDENT", "I")
            and self.next.typ == "LBRACKET"
            and self._looks_like_index_assignment()
        ):
            return self.index_set_stmt()

        expr = self.expr()
        return ExprStmtNode(expr)

    def _looks_like_index_assignment(self):
        depth = 0
        tokens = [self.current, self.next, self.next2]
        idx = 1

        while idx < len(tokens):
            tok = tokens[idx]
            if tok.typ == "LBRACKET":
                depth += 1
            elif tok.typ == "RBRACKET":
                depth -= 1
                if depth == 0:
                    if idx + 1 < len(tokens) and tokens[idx + 1].typ == "ASSIGN":
                        return True
                    return False
            idx += 1

        return False

    def index_set_stmt(self):
        name = self.eat_name()
        self.eat("LBRACKET")
        index_expr = self.expr()
        self.eat("RBRACKET")
        self.eat("ASSIGN")
        value_expr = self.expr()
        return IndexSetNode(name, index_expr, value_expr)

    def var_decl(self):
        self.eat("LA")
        name = self.eat_name()
        self.eat("COLON")
        var_type = self.parse_type()
        self.eat("ASSIGN")
        expr = self.expr()
        return VarDeclareNode(name, var_type, expr)

    def var_set_stmt(self):
        name = self.eat_name()
        self.eat("ASSIGN")
        expr = self.expr()
        return VarSetNode(name, expr)

    def print_stmt(self):
        self.eat("SKRIV")
        self.eat("LPAREN")
        expr = self.expr()
        self.eat("RPAREN")
        return PrintNode(expr)

    def test_block(self):
        self.eat("TEST")
        if self.current.typ != "STRING":
            self.error("Forventet testnavn (tekst)")
        name = self.current.value
        self.eat("STRING")
        body = self.block()
        return TestNode(name, body)

    def assert_stmt(self):
        self.eat("ASSERT")
        self.eat("LPAREN")
        expr = self.expr()
        self.eat("RPAREN")
        return ExprStmtNode(CallNode("assert", [expr]))

    def assert_eq_stmt(self):
        self.eat("ASSERT_EQ")
        self.eat("LPAREN")
        left = self.expr()
        self.eat("COMMA")
        right = self.expr()
        if self.current.typ == "COMMA":
            self.eat("COMMA")
            _message = self.expr()
        self.eat("RPAREN")
        return ExprStmtNode(CallNode("assert_eq", [left, right]))

    def assert_ne_stmt(self):
        self.eat("ASSERT_NE")
        self.eat("LPAREN")
        left = self.expr()
        self.eat("COMMA")
        right = self.expr()
        if self.current.typ == "COMMA":
            self.eat("COMMA")
            _message = self.expr()
        self.eat("RPAREN")
        return ExprStmtNode(CallNode("assert_ne", [left, right]))

    def if_stmt(self):
        self.eat("HVIS")
        self.eat("LPAREN")
        cond = self.expr()
        self.eat("RPAREN")
        then_block = self.block()

        elif_blocks = []
        else_block = None

        while self.current.typ == "ELLERS":
            self.eat("ELLERS")

            if self.current.typ == "HVIS":
                self.eat("HVIS")
                self.eat("LPAREN")
                elif_cond = self.expr()
                self.eat("RPAREN")
                elif_block = self.block()
                elif_blocks.append((elif_cond, elif_block))
                continue

            else_block = self.block()
            break

        return IfNode(cond, then_block, elif_blocks, else_block)

    def while_stmt(self):
        self.eat("MENS")
        self.eat("LPAREN")
        cond = self.expr()
        self.eat("RPAREN")
        body = self.block()
        return WhileNode(cond, body)

    def for_stmt(self):
        self.eat("FOR")
        item_name = self.eat_name()
        if self.current.typ == "I":
            self.eat("I")
            list_expr = self.expr()
            body = self.block()
            return ForEachNode(item_name, list_expr, body)
        self.eat("ASSIGN")
        start_expr = self.expr()
        self.eat("TIL")
        end_expr = self.expr()
        if self.current.typ == "STEG":
            self.eat("STEG")
            step_expr = self.expr()
        else:
            step_expr = NumberNode(1)
        body = self.block()
        return ForNode(item_name, start_expr, end_expr, step_expr, body)

    def return_stmt(self):
        self.eat("RETURNER")
        expr = self.expr()
        return ReturnNode(expr)

    def expr(self):
        return self.logic_or()

    def logic_or(self):
        node = self.logic_and()
        while self.current.typ == "ELLER":
            op = self.current
            self.eat("ELLER")
            node = BinOpNode(node, op, self.logic_and())
        return node

    def logic_and(self):
        node = self.equality()
        while self.current.typ == "OG":
            op = self.current
            self.eat("OG")
            node = BinOpNode(node, op, self.equality())
        return node

    def equality(self):
        node = self.comparison()
        while self.current.typ in ("EQ", "NE"):
            op = self.current
            self.eat(self.current.typ)
            node = BinOpNode(node, op, self.comparison())
        return node

    def comparison(self):
        node = self.term()
        comparison_tokens = {
            "GT": "GT",
            "LT": "LT",
            "GTE": "GTE",
            "LTE": "LTE",
            "GREATER": "GT",
            "LESS": "LT",
            "GREATER_EQUAL": "GTE",
            "LESS_EQUAL": "LTE",
        }

        while self.current.typ in comparison_tokens:
            op = self.current
            normalized_typ = comparison_tokens[op.typ]
            if op.typ != normalized_typ:
                op = type(op)(normalized_typ, op.value, op.line, op.column)
            self.eat(self.current.typ)
            node = BinOpNode(node, op, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.current.typ in ("PLUS", "MINUS"):
            op = self.current
            self.eat(self.current.typ)
            node = BinOpNode(node, op, self.factor())
        return node

    def factor(self):
        node = self.unary()
        while self.current.typ in ("MUL", "DIV"):
            op = self.current
            self.eat(self.current.typ)
            node = BinOpNode(node, op, self.unary())
        return node

    def unary(self):
        if self.current.typ in ("PLUS", "MINUS", "IKKE"):
            op = self.current
            self.eat(self.current.typ)
            return UnaryOpNode(op, self.unary())
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while True:
            if self.current.typ == "DOT":
                if not isinstance(node, VarAccessNode):
                    self.error("Kan bare bruke punktum på navn i denne versjonen")
                module_name = node.name
                self.eat("DOT")
                if self.current.typ != "IDENT":
                    self.error("Forventet funksjonsnavn etter punktum")
                func_name = self.current.value
                self.eat("IDENT")
                self.eat("LPAREN")
                args = []
                if self.current.typ != "RPAREN":
                    args.append(self.expr())
                    while self.current.typ == "COMMA":
                        self.eat("COMMA")
                        args.append(self.expr())
                self.eat("RPAREN")
                node = ModuleCallNode(module_name, func_name, args)
                continue

            if self.current.typ == "LPAREN":
                if not isinstance(node, VarAccessNode):
                    self.error("Kan bare kalle funksjoner med navn")
                name = node.name
                self.eat("LPAREN")
                args = []
                if self.current.typ != "RPAREN":
                    args.append(self.expr())
                    while self.current.typ == "COMMA":
                        self.eat("COMMA")
                        args.append(self.expr())
                self.eat("RPAREN")
                node = CallNode(name, args)
                continue

            if self.current.typ == "LBRACKET":
                self.eat("LBRACKET")
                idx = self.expr()
                self.eat("RBRACKET")
                node = IndexNode(node, idx)
                continue

            break
        return node

    def primary(self):
        token = self.current
        if token.typ == "NUMBER":
            self.eat("NUMBER")
            return NumberNode(token.value)
        if token.typ == "STRING":
            self.eat("STRING")
            return StringNode(token.value)
        if token.typ == "SANN":
            self.eat("SANN")
            return BoolNode(True)
        if token.typ == "USANN":
            self.eat("USANN")
            return BoolNode(False)
        if token.typ in ("IDENT", "I"):
            self.eat(token.typ)
            return VarAccessNode(token.value)
        if token.typ == "LPAREN":
            self.eat("LPAREN")
            node = self.expr()
            self.eat("RPAREN")
            return node
        if token.typ == "LBRACKET":
            return self.list_literal()
        self.error(f"Uventet token: {token.typ}")

    def list_literal(self):
        self.eat("LBRACKET")
        items = []
        if self.current.typ != "RBRACKET":
            items.append(self.expr())
            while self.current.typ == "COMMA":
                self.eat("COMMA")
                items.append(self.expr())
        self.eat("RBRACKET")
        return ListLiteralNode(items)
