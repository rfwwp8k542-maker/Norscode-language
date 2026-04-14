import re

from .ast_nodes import *


class CGenerator:
    def __init__(self, function_symbols, alias_map=None):
        self.function_symbols = function_symbols
        self.alias_map = alias_map or {}
        self.lines = []
        self.indent = 0
        self.var_types = {}
        self.current_module = "__main__"
        self.current_return_type = None
        self.temp_counter = 0
        self.function_name_map = {}
        self.needs_gui_runtime = False
        self._build_function_name_map()

    def _build_function_name_map(self):
        for key, symbol in self.function_symbols.items():
            if getattr(symbol, "builtin", False):
                continue
            module_name = getattr(symbol, "module_name", None)
            short_name = key.split(".")[-1]
            self.function_name_map[key] = self.mangle_function_name(module_name, short_name)
            if module_name and module_name != "__main__":
                self.function_name_map[f"{module_name}.{short_name}"] = self.mangle_function_name(module_name, short_name)
            else:
                self.function_name_map[short_name] = self.mangle_function_name(module_name, short_name)

    def emit(self, line=""):
        self.lines.append("    " * self.indent + line)

    def c_type(self, t):
        return {
            TYPE_INT: "int",
            TYPE_BOOL: "int",
            TYPE_TEXT: "char *",
            TYPE_LIST_INT: "nl_list_int*",
            TYPE_LIST_TEXT: "nl_list_text*",
        }[t]

    def c_string(self, value):
        escaped = (
            value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'

    def mangle_function_name(self, module_name, name):
        def sanitize(identifier):
            safe = re.sub(r"[^0-9A-Za-z_]", "_", identifier)
            if safe and safe[0].isdigit():
                safe = "_" + safe
            return safe

        if not module_name or module_name == "__main__":
            return sanitize(name)
        return f"{sanitize(module_name).replace('.', '__')}__{sanitize(name)}"

    def format_condition(self, expr_code):
        trimmed = expr_code.strip()
        if trimmed.startswith("(") and trimmed.endswith(")"):
            return trimmed
        return f"({trimmed})"

    def resolve_symbol(self, name, module_name=None):
        if module_name:
            real_module = self.alias_map.get(module_name, module_name)
            full = f"{real_module}.{name}"
            return self.function_symbols.get(full), full

        current_full = f"{self.current_module}.{name}" if self.current_module and self.current_module != "__main__" else name
        if current_full in self.function_symbols:
            return self.function_symbols[current_full], current_full
        if name in self.function_symbols:
            return self.function_symbols[name], name
        return None, name

    def resolve_c_function_name(self, name, module_name=None):
        _symbol, full = self.resolve_symbol(name, module_name=module_name)
        if full in self.function_name_map:
            return self.function_name_map[full]
        if name in self.function_name_map:
            return self.function_name_map[name]
        if module_name:
            real_module = self.alias_map.get(module_name, module_name)
            return self.mangle_function_name(real_module, name)
        return name

    def generate(self, tree):
        self.needs_gui_runtime = self._tree_uses_gui_runtime(tree)
        self.emit("#include <stdio.h>")
        self.emit("#include <stdlib.h>")
        self.emit("#include <string.h>")
        self.emit("#include <ctype.h>")
        self.emit("#include <dirent.h>")
        self.emit("#include <sys/stat.h>")
        self.emit("#ifdef _WIN32")
        self.emit("#include <process.h>")
        self.emit("#else")
        self.emit("#include <unistd.h>")
        self.emit("#include <sys/wait.h>")
        self.emit("#endif")
        self.emit()
        self.emit_runtime_helpers()
        if self.needs_gui_runtime:
            self.emit_gui_runtime_helpers()

        for fn in tree.functions:
            self.visit_function(fn)
            self.emit()

        if self.needs_gui_runtime:
            self.emit_callback_dispatcher(tree)

        self.emit("int main(void) {")
        self.indent += 1
        self.emit("return start();")
        self.indent -= 1
        self.emit("}")

        return "\n".join(self.lines)

    def emit_runtime_helpers(self):
        self.emit("typedef struct { int *data; int len; int cap; } nl_list_int;")
        self.emit("typedef struct { char **data; int len; int cap; } nl_list_text;")
        self.emit()
        self.emit("static int nl_call_callback(const char *name, int widget_id);")
        self.emit()

        self.emit("static nl_list_int *nl_list_int_new(void) {")
        self.indent += 1
        self.emit("nl_list_int *l = (nl_list_int *)malloc(sizeof(nl_list_int));")
        self.emit("if (!l) { perror(\"malloc\"); exit(1); }")
        self.emit("l->len = 0;")
        self.emit("l->cap = 8;")
        self.emit("l->data = (int *)malloc(sizeof(int) * l->cap);")
        self.emit("if (!l->data) { perror(\"malloc\"); exit(1); }")
        self.emit("return l;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_list_text_new(void) {")
        self.indent += 1
        self.emit("nl_list_text *l = (nl_list_text *)malloc(sizeof(nl_list_text));")
        self.emit("if (!l) { perror(\"malloc\"); exit(1); }")
        self.emit("l->len = 0;")
        self.emit("l->cap = 8;")
        self.emit("l->data = (char **)malloc(sizeof(char *) * l->cap);")
        self.emit("if (!l->data) { perror(\"malloc\"); exit(1); }")
        self.emit("return l;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static void nl_list_int_ensure(nl_list_int *l, int need) {")
        self.indent += 1
        self.emit("if (need <= l->cap) { return; }")
        self.emit("while (l->cap < need) { l->cap *= 2; }")
        self.emit("l->data = (int *)realloc(l->data, sizeof(int) * l->cap);")
        self.emit("if (!l->data) { perror(\"realloc\"); exit(1); }")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static void nl_list_text_ensure(nl_list_text *l, int need) {")
        self.indent += 1
        self.emit("if (need <= l->cap) { return; }")
        self.emit("while (l->cap < need) { l->cap *= 2; }")
        self.emit("l->data = (char **)realloc(l->data, sizeof(char *) * l->cap);")
        self.emit("if (!l->data) { perror(\"realloc\"); exit(1); }")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_int_len(nl_list_int *l) { return l ? l->len : 0; }")
        self.emit("static int nl_list_text_len(nl_list_text *l) { return l ? l->len : 0; }")
        self.emit()

        self.emit("static int nl_list_int_push(nl_list_int *l, int v) {")
        self.indent += 1
        self.emit("nl_list_int_ensure(l, l->len + 1);")
        self.emit("l->data[l->len++] = v;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_text_push(nl_list_text *l, char *v) {")
        self.indent += 1
        self.emit("nl_list_text_ensure(l, l->len + 1);")
        self.emit("l->data[l->len++] = v;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_int_pop(nl_list_int *l) {")
        self.indent += 1
        self.emit("if (!l || l->len == 0) { return 0; }")
        self.emit("int v = l->data[l->len - 1];")
        self.emit("l->len -= 1;")
        self.emit("return v;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_list_text_pop(nl_list_text *l) {")
        self.indent += 1
        self.emit('if (!l || l->len == 0) { return ""; }')
        self.emit("char *v = l->data[l->len - 1];")
        self.emit("l->len -= 1;")
        self.emit("return v;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_int_remove(nl_list_int *l, int idx) {")
        self.indent += 1
        self.emit("if (!l || idx < 0 || idx >= l->len) { return nl_list_int_len(l); }")
        self.emit("for (int i = idx; i < l->len - 1; i++) { l->data[i] = l->data[i + 1]; }")
        self.emit("l->len -= 1;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_text_remove(nl_list_text *l, int idx) {")
        self.indent += 1
        self.emit("if (!l || idx < 0 || idx >= l->len) { return nl_list_text_len(l); }")
        self.emit("for (int i = idx; i < l->len - 1; i++) { l->data[i] = l->data[i + 1]; }")
        self.emit("l->len -= 1;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_int_set(nl_list_int *l, int idx, int v) {")
        self.indent += 1
        self.emit("if (!l || idx < 0 || idx >= l->len) { return nl_list_int_len(l); }")
        self.emit("l->data[idx] = v;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_text_set(nl_list_text *l, int idx, char *v) {")
        self.indent += 1
        self.emit("if (!l || idx < 0 || idx >= l->len) { return nl_list_text_len(l); }")
        self.emit("l->data[idx] = v;")
        self.emit("return l->len;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_strdup(const char *s) {")
        self.indent += 1
        self.emit("if (!s) { s = \"\"; }")
        self.emit("size_t n = strlen(s) + 1;")
        self.emit("char *out = (char *)malloc(n);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, s, n);")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_streq(const char *a, const char *b) {")
        self.indent += 1
        self.emit("if (!a) { a = \"\"; }")
        self.emit("if (!b) { b = \"\"; }")
        self.emit("return strcmp(a, b) == 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_concat(const char *a, const char *b) {")
        self.indent += 1
        self.emit("if (!a) { a = \"\"; }")
        self.emit("if (!b) { b = \"\"; }")
        self.emit("size_t al = strlen(a);")
        self.emit("size_t bl = strlen(b);")
        self.emit("char *out = (char *)malloc(al + bl + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, a, al);")
        self.emit("memcpy(out + al, b, bl);")
        self.emit("out[al + bl] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_run_command(nl_list_text *parts) {")
        self.indent += 1
        self.emit("if (!parts || !parts->data || parts->len <= 0) { return 1; }")
        self.emit("char **argv = (char **)calloc((size_t)parts->len + 1, sizeof(char *));")
        self.emit("if (!argv) { perror(\"calloc\"); exit(1); }")
        self.emit("for (int i = 0; i < parts->len; i++) {")
        self.indent += 1
        self.emit("argv[i] = nl_strdup(parts->data[i] ? parts->data[i] : \"\");")
        self.indent -= 1
        self.emit("}")
        self.emit("argv[parts->len] = NULL;")
        self.emit("#ifdef _WIN32")
        self.emit("int status = _spawnvp(_P_WAIT, argv[0], (const char * const *)argv);")
        self.emit("for (int i = 0; i < parts->len; i++) { free(argv[i]); }")
        self.emit("free(argv);")
        self.emit("if (status == -1) { return 1; }")
        self.emit("return status == 0 ? 0 : 1;")
        self.emit("#else")
        self.emit("pid_t pid = fork();")
        self.emit("if (pid == -1) {")
        self.indent += 1
        self.emit("for (int i = 0; i < parts->len; i++) { free(argv[i]); }")
        self.emit("free(argv);")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (pid == 0) {")
        self.indent += 1
        self.emit("execvp(argv[0], argv);")
        self.emit("_exit(127);")
        self.indent -= 1
        self.emit("}")
        self.emit("int status = 1;")
        self.emit("if (waitpid(pid, &status, 0) == -1) {")
        self.indent += 1
        self.emit("for (int i = 0; i < parts->len; i++) { free(argv[i]); }")
        self.emit("free(argv);")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit("for (int i = 0; i < parts->len; i++) { free(argv[i]); }")
        self.emit("free(argv);")
        self.emit("if (WIFEXITED(status)) { return WEXITSTATUS(status) == 0 ? 0 : WEXITSTATUS(status); }")
        self.emit("if (WIFSIGNALED(status)) { return 128 + WTERMSIG(status); }")
        self.emit("return 1;")
        self.emit("#endif")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_read_input(const char *prompt) {")
        self.indent += 1
        self.emit("(void)prompt;")
        self.emit('return nl_strdup("");')
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_int_to_text(int value) {")
        self.indent += 1
        self.emit("char buffer[32];")
        self.emit("snprintf(buffer, sizeof(buffer), \"%d\", value);")
        self.emit("return nl_strdup(buffer);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_er_ordtegn(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return 0; }")
        self.emit("const unsigned char *s = (const unsigned char *)text;")
        self.emit("unsigned char lead = s[0];")
        self.emit("int width = 1;")
        self.emit("int cp = 0;")
        self.emit("if ((lead & 0x80) == 0) { cp = lead; }")
        self.emit("else if ((lead & 0xE0) == 0xC0) { width = 2; cp = ((lead & 0x1F) << 6) | (s[1] & 0x3F); }")
        self.emit("else if ((lead & 0xF0) == 0xE0) { width = 3; cp = ((lead & 0x0F) << 12) | ((s[1] & 0x3F) << 6) | (s[2] & 0x3F); }")
        self.emit("else if ((lead & 0xF8) == 0xF0) { width = 4; cp = ((lead & 0x07) << 18) | ((s[1] & 0x3F) << 12) | ((s[2] & 0x3F) << 6) | (s[3] & 0x3F); }")
        self.emit("else { return 0; }")
        self.emit("if (s[width] != '\\0') { return 0; }")
        self.emit("if ((cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') || cp == '_') { return 1; }")
        self.emit("return cp == 0x00C5 || cp == 0x00E5 || cp == 0x00C6 || cp == 0x00E6 || cp == 0x00D8 || cp == 0x00F8;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_split_words(const char *s) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("char *copy = nl_strdup(s ? s : \"\");")
        self.emit("char *tok = strtok(copy, \" \\t\\r\\n\");")
        self.emit("while (tok) {")
        self.indent += 1
        self.emit("nl_list_text_push(out, nl_strdup(tok));")
        self.emit("tok = strtok(NULL, \" \\t\\r\\n\");")
        self.indent -= 1
        self.emit("}")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_tokenize_simple(const char *s) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!s) { return out; }")
        self.emit("char token[256];")
        self.emit("int tlen = 0;")
        self.emit("int in_comment = 0;")
        self.emit("for (const char *p = s; ; ++p) {")
        self.indent += 1
        self.emit("char c = *p;")
        self.emit("if (c == '\\0') {")
        self.indent += 1
        self.emit("if (tlen > 0) { token[tlen] = '\\0'; nl_list_text_push(out, nl_strdup(token)); }")
        self.emit("break;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (in_comment) {")
        self.indent += 1
        self.emit("if (c == '\\n') { in_comment = 0; }")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (c == '#') {")
        self.indent += 1
        self.emit("if (tlen > 0) { token[tlen] = '\\0'; nl_list_text_push(out, nl_strdup(token)); tlen = 0; }")
        self.emit("in_comment = 1;")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (isalnum((unsigned char)c) || c == '_' || c == '-' || (unsigned char)c >= 128) {")
        self.indent += 1
        self.emit("if (tlen < 255) { token[tlen++] = c; }")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (tlen > 0) {")
        self.indent += 1
        self.emit("token[tlen] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(token));")
        self.emit("tlen = 0;")
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_tokenize_expression(const char *s) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!s) { return out; }")
        self.emit("int in_comment = 0;")
        self.emit("for (const char *p = s; *p; ) {")
        self.indent += 1
        self.emit("char c = *p;")
        self.emit("if (in_comment) {")
        self.indent += 1
        self.emit("if (c == '\\n') { in_comment = 0; }")
        self.emit("p++;")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (c == '#') { in_comment = 1; p++; continue; }")
        self.emit("if (isspace((unsigned char)c)) { p++; continue; }")
        self.emit("if (isdigit((unsigned char)c)) {")
        self.indent += 1
        self.emit("char token[256];")
        self.emit("int tlen = 0;")
        self.emit("while (*p && isdigit((unsigned char)*p)) {")
        self.indent += 1
        self.emit("if (tlen < 255) { token[tlen++] = *p; }")
        self.emit("p++;")
        self.indent -= 1
        self.emit("}")
        self.emit("token[tlen] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(token));")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (isalpha((unsigned char)c) || c == '_' || (unsigned char)c >= 128) {")
        self.indent += 1
        self.emit("char token[256];")
        self.emit("int tlen = 0;")
        self.emit("while (*p && (isalnum((unsigned char)*p) || *p == '_' || (unsigned char)*p >= 128)) {")
        self.indent += 1
        self.emit("if (tlen < 255) { token[tlen++] = *p; }")
        self.emit("p++;")
        self.indent -= 1
        self.emit("}")
        self.emit("token[tlen] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(token));")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if ((c == '&' && p[1] == '&') || (c == '|' && p[1] == '|') || (c == '=' && p[1] == '=') ||")
        self.emit("    (c == '!' && p[1] == '=') || (c == '<' && p[1] == '=') || (c == '>' && p[1] == '=') ||")
        self.emit("    (c == '+' && p[1] == '=') || (c == '-' && p[1] == '=') || (c == '*' && p[1] == '=') ||")
        self.emit("    (c == '/' && p[1] == '=') || (c == '%' && p[1] == '=')) {")
        self.indent += 1
        self.emit("char token[3];")
        self.emit("token[0] = c;")
        self.emit("token[1] = p[1];")
        self.emit("token[2] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(token));")
        self.emit("p += 2;")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (c == '(' || c == ')' || c == '+' || c == '-' || c == '*' || c == '/' || c == '%' || c == '<' || c == '>' || c == '=' || c == ';') {")
        self.indent += 1
        self.emit("char token[2];")
        self.emit("token[0] = c;")
        self.emit("token[1] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(token));")
        self.emit("p++;")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("char unknown[2];")
        self.emit("unknown[0] = c;")
        self.emit("unknown[1] = '\\0';")
        self.emit("nl_list_text_push(out, nl_strdup(unknown));")
        self.emit("p++;")
        self.indent -= 1
        self.emit("}")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_bool_to_text(int value) {")
        self.indent += 1
        self.emit('return nl_strdup(value ? "sann" : "usann");')
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_to_lower(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("size_t len = strlen(text);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("for (size_t i = 0; i < len; i++) { out[i] = (char)tolower((unsigned char)text[i]); }")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_to_upper(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("size_t len = strlen(text);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("for (size_t i = 0; i < len; i++) { out[i] = (char)toupper((unsigned char)text[i]); }")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_to_title(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("size_t len = strlen(text);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("int new_word = 1;")
        self.emit("for (size_t i = 0; i < len; i++) {")
        self.indent += 1
        self.emit("unsigned char ch = (unsigned char)text[i];")
        self.emit("if (ch < 128 && (isalnum(ch) || ch == '_')) {")
        self.indent += 1
        self.emit("out[i] = (char)(new_word ? toupper(ch) : tolower(ch));")
        self.emit("new_word = 0;")
        self.indent -= 1
        self.emit("} else {")
        self.indent += 1
        self.emit("out[i] = (char)ch;")
        self.emit("new_word = 1;")
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_reverse(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("size_t len = strlen(text);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("size_t *starts = (size_t *)malloc(sizeof(size_t) * (len + 1));")
        self.emit("size_t *sizes = (size_t *)malloc(sizeof(size_t) * (len + 1));")
        self.emit("if (!starts || !sizes) { perror(\"malloc\"); exit(1); }")
        self.emit("size_t count = 0;")
        self.emit("size_t i = 0;")
        self.emit("while (i < len) {")
        self.indent += 1
        self.emit("size_t start = i;")
        self.emit("unsigned char ch = (unsigned char)text[i];")
        self.emit("if ((ch & 0x80) == 0) {")
        self.indent += 1
        self.emit("i += 1;")
        self.indent -= 1
        self.emit("} else if ((ch & 0xE0) == 0xC0) {")
        self.indent += 1
        self.emit("i += 2;")
        self.indent -= 1
        self.emit("} else if ((ch & 0xF0) == 0xE0) {")
        self.indent += 1
        self.emit("i += 3;")
        self.indent -= 1
        self.emit("} else if ((ch & 0xF8) == 0xF0) {")
        self.indent += 1
        self.emit("i += 4;")
        self.indent -= 1
        self.emit("} else {")
        self.indent += 1
        self.emit("i += 1;")
        self.indent -= 1
        self.emit("}")
        self.emit("starts[count] = start;")
        self.emit("sizes[count] = i - start;")
        self.emit("count++;")
        self.indent -= 1
        self.emit("}")
        self.emit("size_t out_pos = 0;")
        self.emit("for (size_t idx = count; idx > 0; idx--) {")
        self.indent += 1
        self.emit("size_t src = starts[idx - 1];")
        self.emit("size_t cp_len = sizes[idx - 1];")
        self.emit("memcpy(out + out_pos, text + src, cp_len);")
        self.emit("out_pos += cp_len;")
        self.indent -= 1
        self.emit("}")
        self.emit("out[out_pos] = '\\0';")
        self.emit("free(starts);")
        self.emit("free(sizes);")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_text_split_by(const char *text, const char *sep) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!text) { text = \"\"; }")
        self.emit("if (!sep) { sep = \"\"; }")
        self.emit("size_t sep_len = strlen(sep);")
        self.emit("if (sep_len == 0) {")
        self.indent += 1
        self.emit("nl_list_text_push(out, nl_strdup(text));")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit("const char *cursor = text;")
        self.emit("const char *hit = NULL;")
        self.emit("while ((hit = strstr(cursor, sep)) != NULL) {")
        self.indent += 1
        self.emit("size_t chunk = (size_t)(hit - cursor);")
        self.emit("char *part = (char *)malloc(chunk + 1);")
        self.emit("if (!part) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(part, cursor, chunk);")
        self.emit("part[chunk] = '\\0';")
        self.emit("nl_list_text_push(out, part);")
        self.emit("cursor = hit + sep_len;")
        self.indent -= 1
        self.emit("}")
        self.emit("nl_list_text_push(out, nl_strdup(cursor));")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_to_int(const char *s) {")
        self.indent += 1
        self.emit("if (!s) { return 0; }")
        self.emit("return (int)strtol(s, NULL, 10);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_slutter_med(const char *text, const char *suffix) {")
        self.indent += 1
        self.emit("if (!text) { text = \"\"; }")
        self.emit("if (!suffix) { suffix = \"\"; }")
        self.emit("size_t text_len = strlen(text);")
        self.emit("size_t suffix_len = strlen(suffix);")
        self.emit("if (suffix_len > text_len) { return 0; }")
        self.emit("return strcmp(text + (text_len - suffix_len), suffix) == 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_starter_med(const char *text, const char *prefix) {")
        self.indent += 1
        self.emit("if (!text) { text = \"\"; }")
        self.emit("if (!prefix) { prefix = \"\"; }")
        self.emit("size_t text_len = strlen(text);")
        self.emit("size_t prefix_len = strlen(prefix);")
        self.emit("if (prefix_len > text_len) { return 0; }")
        self.emit("return strncmp(text, prefix, prefix_len) == 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_inneholder(const char *text, const char *needle) {")
        self.indent += 1
        self.emit("if (!text) { text = \"\"; }")
        self.emit("if (!needle) { needle = \"\"; }")
        self.emit("return strstr(text, needle) != NULL;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_erstatt(const char *text, const char *old, const char *new_text) {")
        self.indent += 1
        self.emit("if (!text) { text = \"\"; }")
        self.emit("if (!old) { old = \"\"; }")
        self.emit("if (!new_text) { new_text = \"\"; }")
        self.emit("if (!old[0]) { return nl_strdup(text); }")
        self.emit("const char *cursor = text;")
        self.emit("size_t old_len = strlen(old);")
        self.emit("size_t new_len = strlen(new_text);")
        self.emit("size_t count = 0;")
        self.emit("const char *hit = text;")
        self.emit("while ((hit = strstr(hit, old)) != NULL) { count++; hit += old_len; }")
        self.emit("size_t result_len = strlen(text) + count * (new_len - old_len);")
        self.emit("char *out = (char *)malloc(result_len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("char *write = out;")
        self.emit("while ((hit = strstr(cursor, old)) != NULL) {")
        self.indent += 1
        self.emit("size_t chunk = (size_t)(hit - cursor);")
        self.emit("memcpy(write, cursor, chunk);")
        self.emit("write += chunk;")
        self.emit("memcpy(write, new_text, new_len);")
        self.emit("write += new_len;")
        self.emit("cursor = hit + old_len;")
        self.indent -= 1
        self.emit("}")
        self.emit("strcpy(write, cursor);")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_utf8_char_width(unsigned char lead) {")
        self.indent += 1
        self.emit("if ((lead & 0x80) == 0) { return 1; }")
        self.emit("if ((lead & 0xE0) == 0xC0) { return 2; }")
        self.emit("if ((lead & 0xF0) == 0xE0) { return 3; }")
        self.emit("if ((lead & 0xF8) == 0xF0) { return 4; }")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_utf8_codepoint_at(const char *text, int byte_index) {")
        self.indent += 1
        self.emit("const unsigned char *s = (const unsigned char *)(text ? text : \"\");")
        self.emit("unsigned char lead = s[byte_index];")
        self.emit("if (lead == '\\0') { return -1; }")
        self.emit("if ((lead & 0x80) == 0) { return lead; }")
        self.emit("if ((lead & 0xE0) == 0xC0) { return ((lead & 0x1F) << 6) | (s[byte_index + 1] & 0x3F); }")
        self.emit("if ((lead & 0xF0) == 0xE0) { return ((lead & 0x0F) << 12) | ((s[byte_index + 1] & 0x3F) << 6) | (s[byte_index + 2] & 0x3F); }")
        self.emit("if ((lead & 0xF8) == 0xF0) { return ((lead & 0x07) << 18) | ((s[byte_index + 1] & 0x3F) << 12) | ((s[byte_index + 2] & 0x3F) << 6) | (s[byte_index + 3] & 0x3F); }")
        self.emit("return lead;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_utf8_text_length(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return 0; }")
        self.emit("int count = 0;")
        self.emit("for (const unsigned char *p = (const unsigned char *)text; *p; p += nl_utf8_char_width(*p)) { count++; }")
        self.emit("return count;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_utf8_char_offset(const char *text, int char_index) {")
        self.indent += 1
        self.emit("if (!text) { return 0; }")
        self.emit("if (char_index <= 0) { return 0; }")
        self.emit("int current = 0;")
        self.emit("int byte_index = 0;")
        self.emit("while (text[byte_index] != '\\0' && current < char_index) {")
        self.indent += 1
        self.emit("byte_index += nl_utf8_char_width((unsigned char)text[byte_index]);")
        self.emit("current++;")
        self.indent -= 1
        self.emit("}")
        self.emit("return byte_index;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_utf8_is_ordtegn(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return 0; }")
        self.emit("int len = (int)strlen(text);")
        self.emit("if (len <= 0) { return 0; }")
        self.emit("int cp = nl_utf8_codepoint_at(text, 0);")
        self.emit("if (cp < 0) { return 0; }")
        self.emit("if (text[nl_utf8_char_width((unsigned char)text[0])] != '\\0') { return 0; }")
        self.emit("if ((cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') || cp == '_') { return 1; }")
        self.emit("return cp == 0x00C5 || cp == 0x00E5 || cp == 0x00C6 || cp == 0x00E6 || cp == 0x00D8 || cp == 0x00F8;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_split_lines(const char *s) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("const char *start = s ? s : \"\";")
        self.emit("const char *p = start;")
        self.emit("if (*p == '\\0') {")
        self.indent += 1
        self.emit("nl_list_text_push(out, nl_strdup(\"\"));")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit("while (1) {")
        self.indent += 1
        self.emit("if (*p == '\\n' || *p == '\\0') {")
        self.indent += 1
        self.emit("size_t len = (size_t)(p - start);")
        self.emit("char *line = (char *)malloc(len + 1);")
        self.emit("if (!line) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(line, start, len);")
        self.emit("line[len] = '\\0';")
        self.emit("nl_list_text_push(out, line);")
        self.emit("if (*p == '\\0') { break; }")
        self.emit("start = p + 1;")
        self.emit("}")
        self.emit("if (*p == '\\0') { break; }")
        self.emit("p++;")
        self.indent -= 1
        self.emit("}")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_assert(int cond) {")
        self.indent += 1
        self.emit("if (!cond) {")
        self.indent += 1
        self.emit('printf("assert failed\\n");')
        self.emit("exit(1);")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_assert_eq_int(int a, int b) {")
        self.indent += 1
        self.emit("if (a != b) {")
        self.indent += 1
        self.emit('printf("assert_eq failed: %d != %d\\n", a, b);')
        self.emit("exit(1);")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_assert_ne_int(int a, int b) {")
        self.indent += 1
        self.emit("if (a == b) {")
        self.indent += 1
        self.emit('printf("assert_ne failed: %d == %d\\n", a, b);')
        self.emit("exit(1);")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_assert_eq_text(const char *a, const char *b) {")
        self.indent += 1
        self.emit("if (!nl_streq(a, b)) {")
        self.indent += 1
        self.emit('printf("assert_eq failed: \\"%s\\" != \\"%s\\"\\n", a ? a : "", b ? b : "");')
        self.emit("exit(1);")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_assert_ne_text(const char *a, const char *b) {")
        self.indent += 1
        self.emit("if (nl_streq(a, b)) {")
        self.indent += 1
        self.emit('printf("assert_ne failed: \\"%s\\" == \\"%s\\"\\n", a ? a : "", b ? b : "");')
        self.emit("exit(1);")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_int_equal(nl_list_int *a, nl_list_int *b) {")
        self.indent += 1
        self.emit("if (a == b) { return 1; }")
        self.emit("if (!a || !b) { return 0; }")
        self.emit("if (a->len != b->len) { return 0; }")
        self.emit("for (int i = 0; i < a->len; i++) { if (a->data[i] != b->data[i]) { return 0; } }")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_list_text_equal(nl_list_text *a, nl_list_text *b) {")
        self.indent += 1
        self.emit("if (a == b) { return 1; }")
        self.emit("if (!a || !b) { return 0; }")
        self.emit("if (a->len != b->len) { return 0; }")
        self.emit("for (int i = 0; i < a->len; i++) { if (!nl_streq(a->data[i], b->data[i])) { return 0; } }")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static void nl_print_text(const char *s) {")
        self.indent += 1
        self.emit('printf("%s\\n", s ? s : "");')
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_file_exists(const char *path) {")
        self.indent += 1
        self.emit("if (!path) { return 0; }")
        self.emit("FILE *f = fopen(path, \"r\");")
        self.emit("if (!f) { return 0; }")
        self.emit("fclose(f);")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_read_file(const char *path) {")
        self.indent += 1
        self.emit("if (!path) { return nl_strdup(\"\"); }")
        self.emit("FILE *f = fopen(path, \"rb\");")
        self.emit("if (!f) { return nl_strdup(\"\"); }")
        self.emit("fseek(f, 0, SEEK_END);")
        self.emit("long size = ftell(f);")
        self.emit("fseek(f, 0, SEEK_SET);")
        self.emit("if (size < 0) { fclose(f); return nl_strdup(\"\"); }")
        self.emit("char *buf = (char *)malloc((size_t)size + 1);")
        self.emit("if (!buf) { fclose(f); perror(\"malloc\"); exit(1); }")
        self.emit("size_t read_n = fread(buf, 1, (size_t)size, f);")
        self.emit("buf[read_n] = '\\0';")
        self.emit("fclose(f);")
        self.emit("return buf;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_read_env(const char *name) {")
        self.indent += 1
        self.emit("if (!name) { return nl_strdup(\"\"); }")
        self.emit("const char *value = getenv(name);")
        self.emit("return nl_strdup(value ? value : \"\");")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_trim(const char *text) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("const char *start = text;")
        self.emit("while (*start && isspace((unsigned char)*start)) { start++; }")
        self.emit("const char *end = text + strlen(text);")
        self.emit("while (end > start && isspace((unsigned char)*(end - 1))) { end--; }")
        self.emit("size_t len = (size_t)(end - start);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, start, len);")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_text_length(const char *text) {")
        self.indent += 1
        self.emit("return nl_utf8_text_length(text);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_text_slice(const char *text, int start, int end) {")
        self.indent += 1
        self.emit("if (!text) { return nl_strdup(\"\"); }")
        self.emit("int len_text = nl_utf8_text_length(text);")
        self.emit("if (start < 0) { start = 0; }")
        self.emit("if (end < start) { end = start; }")
        self.emit("if (start > len_text) { start = len_text; }")
        self.emit("if (end > len_text) { end = len_text; }")
        self.emit("int start_byte = nl_utf8_char_offset(text, start);")
        self.emit("int end_byte = nl_utf8_char_offset(text, end);")
        self.emit("int len = end_byte - start_byte;")
        self.emit("char *out = (char *)malloc((size_t)len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, text + start_byte, (size_t)len);")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_sass_replace_variables(const char *text, nl_list_text *names, nl_list_text *values) {")
        self.indent += 1
        self.emit("char *current = nl_strdup(text ? text : \"\");")
        self.emit("for (int i = 0; i < nl_list_text_len(names); i++) {")
        self.indent += 1
        self.emit("char *needle = nl_concat(\"$\", names->data[i] ? names->data[i] : \"\");")
        self.emit("char *next = nl_text_erstatt(current, needle, values->data[i] ? values->data[i] : \"\");")
        self.emit("free(needle);")
        self.emit("free(current);")
        self.emit("current = next;")
        self.indent -= 1
        self.emit("}")
        self.emit("return current;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_sass_to_css(const char *source) {")
        self.indent += 1
        self.emit("nl_list_text *lines = nl_split_lines(source ? source : \"\");")
        self.emit("nl_list_text *names = nl_list_text_new();")
        self.emit("nl_list_text *values = nl_list_text_new();")
        self.emit("nl_list_text *stack = nl_list_text_new();")
        self.emit("char *out = nl_strdup(\"\");")
        self.emit("for (int i = 0; i < nl_list_text_len(lines); i++) {")
        self.indent += 1
        self.emit("char *trimmed = nl_text_trim(lines->data[i]);")
        self.emit("if (!trimmed[0] || (trimmed[0] == '/' && trimmed[1] == '/') || trimmed[0] == '*') { free(trimmed); continue; }")
        self.emit("if (trimmed[0] == '$' && strchr(trimmed, ':') && trimmed[strlen(trimmed) - 1] == ';') {")
        self.indent += 1
        self.emit("char *colon = strchr(trimmed, ':');")
        self.emit("char *name = nl_text_trim(nl_text_slice(trimmed, 1, (int)(colon - trimmed)));")
        self.emit("char *value_raw = nl_text_slice(trimmed, (int)(colon - trimmed) + 1, (int)strlen(trimmed) - 1);")
        self.emit("char *value = nl_text_trim(value_raw);")
        self.emit("nl_list_text_push(names, name);")
        self.emit("nl_list_text_push(values, value);")
        self.emit("free(value_raw);")
        self.emit("free(trimmed);")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("char *replaced = nl_sass_replace_variables(trimmed, names, values);")
        self.emit("free(trimmed);")
        self.emit("trimmed = replaced;")
        self.emit("size_t len = strlen(trimmed);")
        self.emit("if (len > 0 && trimmed[len - 1] == '{') {")
        self.indent += 1
        self.emit("char *selector = nl_text_trim(nl_text_slice(trimmed, 0, (int)len - 1));")
        self.emit("if (selector[0] == '&' && nl_list_text_len(stack) > 0) {")
        self.indent += 1
        self.emit("char *parent = stack->data[nl_list_text_len(stack) - 1];")
        self.emit("char *combined = nl_text_erstatt(selector, \"&\", parent ? parent : \"\");")
        self.emit("free(selector);")
        self.emit("selector = combined;")
        self.indent -= 1
        self.emit("} else if (nl_list_text_len(stack) > 0) {")
        self.indent += 1
        self.emit("char *parent = stack->data[nl_list_text_len(stack) - 1];")
        self.emit("char *combined = nl_concat(nl_concat(parent ? parent : \"\", \" \"), selector);")
        self.emit("free(selector);")
        self.emit("selector = combined;")
        self.indent -= 1
        self.emit("}")
        self.emit("nl_list_text_push(stack, selector);")
        self.emit("free(trimmed);")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (strcmp(trimmed, \"}\") == 0) {")
        self.indent += 1
        self.emit("if (nl_list_text_len(stack) > 0) {")
        self.indent += 1
        self.emit("free(nl_list_text_pop(stack));")
        self.indent -= 1
        self.emit("}")
        self.emit("free(trimmed);")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (strchr(trimmed, ':') && trimmed[len - 1] == ';') {")
        self.indent += 1
        self.emit("char *selector = nl_list_text_len(stack) > 0 ? stack->data[nl_list_text_len(stack) - 1] : \"\";")
        self.emit("if (selector && selector[0]) {")
        self.indent += 1
        self.emit("char *block = nl_concat(nl_concat(nl_concat(selector, \" { \"), trimmed), \" }\\n\");")
        self.emit("char *next = nl_concat(out, block);")
        self.emit("free(out);")
        self.emit("free(block);")
        self.emit("out = next;")
        self.indent -= 1
        self.emit("} else {")
        self.indent += 1
        self.emit("char *block = nl_concat(trimmed, \"\\n\");")
        self.emit("char *next = nl_concat(out, block);")
        self.emit("free(out);")
        self.emit("free(block);")
        self.emit("out = next;")
        self.indent -= 1
        self.emit("}")
        self.emit("free(trimmed);")
        self.emit("continue;")
        self.indent -= 1
        self.emit("}")
        self.emit("free(trimmed);")
        self.indent -= 1
        self.emit("}")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_read_argv(void) {")
        self.indent += 1
        self.emit('const char *raw = getenv("NORSCODE_ARGS");')
        self.emit("if (!raw || !raw[0]) { return nl_list_text_new(); }")
        self.emit("return nl_split_lines(raw);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_has_studio_suffix(const char *name) {")
        self.indent += 1
        self.emit("const char *suffixes[] = {\".no\", \".md\", \".toml\", \".py\", \".sh\", \".ps1\"};")
        self.emit("size_t name_len = name ? strlen(name) : 0;")
        self.emit("for (size_t i = 0; i < sizeof(suffixes) / sizeof(suffixes[0]); i++) {")
        self.indent += 1
        self.emit("size_t suffix_len = strlen(suffixes[i]);")
        self.emit("if (name_len >= suffix_len && strcmp(name + (name_len - suffix_len), suffixes[i]) == 0) { return 1; }")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_should_skip_entry(const char *name) {")
        self.indent += 1
        self.emit("if (!name || !name[0]) { return 1; }")
        self.emit("if (name[0] == '.') { return 1; }")
        self.emit("return strcmp(name, \"build\") == 0 || strcmp(name, \"dist\") == 0 || strcmp(name, \"__pycache__\") == 0 || strcmp(name, \".venv\") == 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static void nl_collect_files(const char *root, const char *rel, nl_list_text *out) {")
        self.indent += 1
        self.emit("char *path = rel && rel[0] ? nl_concat(root, rel) : nl_strdup(root);")
        self.emit("DIR *dir = opendir(path);")
        self.emit("if (!dir) { free(path); return; }")
        self.emit("struct dirent *entry;")
        self.emit("while ((entry = readdir(dir)) != NULL) {")
        self.indent += 1
        self.emit("const char *name = entry->d_name;")
        self.emit("if (strcmp(name, \".\") == 0 || strcmp(name, \"..\") == 0) { continue; }")
        self.emit("if (nl_should_skip_entry(name)) { continue; }")
        self.emit("char *next_rel = rel && rel[0] ? nl_concat(nl_concat(rel, \"/\"), name) : nl_strdup(name);")
        self.emit("char *next_path = nl_concat(nl_concat(path, \"/\"), name);")
        self.emit("struct stat st;")
        self.emit("if (stat(next_path, &st) == 0 && S_ISDIR(st.st_mode)) {")
        self.indent += 1
        self.emit("nl_collect_files(root, next_rel, out);")
        self.indent -= 1
        self.emit("} else if (nl_has_studio_suffix(name)) {")
        self.indent += 1
        self.emit("nl_list_text_push(out, next_rel);")
        self.emit("next_rel = NULL;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (next_rel) { free(next_rel); }")
        self.emit("free(next_path);")
        self.indent -= 1
        self.emit("}")
        self.emit("closedir(dir);")
        self.emit("free(path);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static void nl_collect_files_tree(const char *root, const char *rel, nl_list_text *out) {")
        self.indent += 1
        self.emit("char *path = rel && rel[0] ? nl_concat(root, rel) : nl_strdup(root);")
        self.emit("DIR *dir = opendir(path);")
        self.emit("if (!dir) { free(path); return; }")
        self.emit("struct dirent *entry;")
        self.emit("while ((entry = readdir(dir)) != NULL) {")
        self.indent += 1
        self.emit("const char *name = entry->d_name;")
        self.emit("if (strcmp(name, \".\") == 0 || strcmp(name, \"..\") == 0) { continue; }")
        self.emit("if (nl_should_skip_entry(name)) { continue; }")
        self.emit("char *next_rel = rel && rel[0] ? nl_concat(nl_concat(rel, \"/\"), name) : nl_strdup(name);")
        self.emit("char *next_path = nl_concat(nl_concat(path, \"/\"), name);")
        self.emit("struct stat st;")
        self.emit("if (stat(next_path, &st) == 0 && S_ISDIR(st.st_mode)) {")
        self.indent += 1
        self.emit("char *folder = nl_concat(next_rel, \"/\");")
        self.emit("nl_list_text_push(out, folder);")
        self.emit("free(folder);")
        self.emit("nl_collect_files_tree(root, next_rel, out);")
        self.indent -= 1
        self.emit("} else if (nl_has_studio_suffix(name)) {")
        self.indent += 1
        self.emit("nl_list_text_push(out, next_rel);")
        self.emit("next_rel = NULL;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (next_rel) { free(next_rel); }")
        self.emit("free(next_path);")
        self.indent -= 1
        self.emit("}")
        self.emit("closedir(dir);")
        self.emit("free(path);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_list_files(const char *root) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!root || !root[0]) { root = \".\"; }")
        self.emit("nl_collect_files(root, \"\", out);")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_list_files_tree(const char *root) {")
        self.indent += 1
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!root || !root[0]) { root = \".\"; }")
        self.emit("nl_collect_files_tree(root, \"\", out);")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_write_file(const char *path, const char *text) {")
        self.indent += 1
        self.emit("if (!path) { return 0; }")
        self.emit("FILE *f = fopen(path, \"wb\");")
        self.emit("if (!f) { return 0; }")
        self.emit("if (text) { fputs(text, f); }")
        self.emit("fclose(f);")
        self.emit("return 1;")
        self.indent -= 1
        self.emit("}")
        self.emit()

    def emit_gui_runtime_helpers(self):
        self.emit("typedef struct { int kind; int parent; char *text; int visible; int selected_index; int cursor_line; int cursor_col; char *click_callback; char *change_callback; char *tab_callback; char *enter_callback; } nl_gui_object;")
        self.emit("static nl_gui_object *nl_gui_objects = NULL;")
        self.emit("static int nl_gui_count = 0;")
        self.emit("static int nl_gui_cap = 0;")
        self.emit()

        self.emit("static void nl_gui_ensure(int need) {")
        self.indent += 1
        self.emit("if (need <= nl_gui_cap) { return; }")
        self.emit("if (nl_gui_cap == 0) { nl_gui_cap = 8; }")
        self.emit("while (nl_gui_cap < need) { nl_gui_cap *= 2; }")
        self.emit("nl_gui_objects = (nl_gui_object *)realloc(nl_gui_objects, sizeof(nl_gui_object) * nl_gui_cap);")
        self.emit("if (!nl_gui_objects) { perror(\"realloc\"); exit(1); }")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_create(int kind, int parent, const char *text) {")
        self.indent += 1
        self.emit("nl_gui_ensure(nl_gui_count + 1);")
        self.emit("nl_gui_objects[nl_gui_count].kind = kind;")
        self.emit("nl_gui_objects[nl_gui_count].parent = parent;")
        self.emit("nl_gui_objects[nl_gui_count].text = nl_strdup(text ? text : \"\");")
        self.emit("nl_gui_objects[nl_gui_count].visible = 0;")
        self.emit("nl_gui_objects[nl_gui_count].selected_index = -1;")
        self.emit("nl_gui_objects[nl_gui_count].cursor_line = 1;")
        self.emit("nl_gui_objects[nl_gui_count].cursor_col = 1;")
        self.emit("nl_gui_objects[nl_gui_count].click_callback = NULL;")
        self.emit("nl_gui_objects[nl_gui_count].change_callback = NULL;")
        self.emit("nl_gui_objects[nl_gui_count].tab_callback = NULL;")
        self.emit("nl_gui_objects[nl_gui_count].enter_callback = NULL;")
        self.emit("nl_gui_count += 1;")
        self.emit("return nl_gui_count;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_gui_object *nl_gui_get(int id) {")
        self.indent += 1
        self.emit("if (id <= 0 || id > nl_gui_count) { return NULL; }")
        self.emit("return &nl_gui_objects[id - 1];")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_vindu(const char *title) {")
        self.indent += 1
        self.emit("return nl_gui_create(1, 0, title);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_panel(int parent) {")
        self.indent += 1
        self.emit("return nl_gui_create(2, parent, \"\");")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_rad(int parent) {")
        self.indent += 1
        self.emit("return nl_gui_create(10, parent, \"\");")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_tekst(int parent, const char *text) {")
        self.indent += 1
        self.emit("return nl_gui_create(3, parent, text);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_tekstboks(int parent, const char *initial) {")
        self.indent += 1
        self.emit("return nl_gui_create(4, parent, initial);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_editor(int parent, const char *initial) {")
        self.indent += 1
        self.emit("return nl_gui_create(9, parent, initial);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_editor_hopp_til(int id, int line) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 9) { return 0; }")
        self.emit("if (line < 1) { line = 1; }")
        self.emit("obj->cursor_line = line;")
        self.emit("obj->cursor_col = 1;")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static nl_list_text *nl_gui_editor_cursor(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("nl_list_text *out = nl_list_text_new();")
        self.emit("if (!obj || obj->kind != 9) { return out; }")
        self.emit("char line_buffer[32];")
        self.emit("char col_buffer[32];")
        self.emit("snprintf(line_buffer, sizeof(line_buffer), \"%d\", obj->cursor_line < 1 ? 1 : obj->cursor_line);")
        self.emit("snprintf(col_buffer, sizeof(col_buffer), \"%d\", obj->cursor_col < 1 ? 1 : obj->cursor_col);")
        self.emit("nl_list_text_push(out, nl_strdup(line_buffer));")
        self.emit("nl_list_text_push(out, nl_strdup(col_buffer));")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_editor_replace_range(int id, int start_line, int start_col, int end_line, int end_col, const char *replacement) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 9) { return 0; }")
        self.emit("char *updated = NULL;")
        self.emit("char *current = obj->text ? obj->text : \"\";")
        self.emit("int line_count = 1;")
        self.emit("for (char *p = current; *p; p++) { if (*p == '\\n') { line_count += 1; } }")
        self.emit("if (start_line < 1) { start_line = 1; }")
        self.emit("if (start_col < 1) { start_col = 1; }")
        self.emit("if (end_line < start_line) { end_line = start_line; }")
        self.emit("if (end_col < 1) { end_col = 1; }")
        self.emit("nl_list_text *lines = nl_list_text_new();")
        self.emit("char *copy = nl_strdup(current);")
        self.emit("char *line_tok = strtok(copy, \"\\n\");")
        self.emit("while (line_tok) { nl_list_text_push(lines, nl_strdup(line_tok)); line_tok = strtok(NULL, \"\\n\"); }")
        self.emit("while (lines->len < line_count) { nl_list_text_push(lines, nl_strdup(\"\")); }")
        self.emit("if (start_line > lines->len) { while (lines->len < start_line) { nl_list_text_push(lines, nl_strdup(\"\")); } }")
        self.emit("if (end_line > lines->len) { while (lines->len < end_line) { nl_list_text_push(lines, nl_strdup(\"\")); } }")
        self.emit("int start_idx = start_line - 1;")
        self.emit("int end_idx = end_line - 1;")
        self.emit("char *start_text = lines->data[start_idx] ? lines->data[start_idx] : \"\";")
        self.emit("char *end_text = lines->data[end_idx] ? lines->data[end_idx] : \"\";")
        self.emit("char *prefix = nl_text_slice(start_text, 0, start_col - 1);")
        self.emit("char *suffix = nl_text_slice(end_text, end_col - 1, (int)strlen(end_text));")
        self.emit("updated = nl_concat(nl_concat(prefix, replacement ? replacement : \"\"), suffix);")
        self.emit("free(obj->text);")
        self.emit("obj->text = updated;")
        self.emit("obj->cursor_line = start_line;")
        self.emit("obj->cursor_col = start_col + (replacement ? (int)strlen(replacement) : 0);")
        self.emit("free(prefix);")
        self.emit("free(suffix);")
        self.emit("free(copy);")
        self.emit("for (int i = 0; i < lines->len; i++) { free(lines->data[i]); }")
        self.emit("free(lines->data);")
        self.emit("free(lines);")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste(int parent) {")
        self.indent += 1
        self.emit("return nl_gui_create(5, parent, \"\");")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_knapp(int parent, const char *label) {")
        self.indent += 1
        self.emit("return nl_gui_create(6, parent, label);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_etikett(int parent, const char *label) {")
        self.indent += 1
        self.emit("return nl_gui_create(7, parent, label);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_tekstfelt(int parent, const char *initial) {")
        self.indent += 1
        self.emit("return nl_gui_create(8, parent, initial);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste_legg_til(int id, const char *text) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5) { return 0; }")
        self.emit("if (!obj->text) { obj->text = nl_strdup(\"\"); }")
        self.emit("char *current = obj->text;")
        self.emit("char *next = current && current[0] ? nl_concat(current, \"\\n\") : nl_strdup(\"\");")
        self.emit("char *updated = nl_concat(next, text ? text : \"\");")
        self.emit("if (current) { free(current); }")
        self.emit("if (next) { free(next); }")
        self.emit("obj->text = updated;")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste_tom(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5) { return 0; }")
        self.emit("free(obj->text);")
        self.emit("obj->text = nl_strdup(\"\");")
        self.emit("obj->selected_index = -1;")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste_antall(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5 || !obj->text || !obj->text[0]) { return 0; }")
        self.emit("int count = 1;")
        self.emit("for (char *p = obj->text; *p; p++) {")
        self.indent += 1
        self.emit("if (*p == '\\n') { count += 1; }")
        self.indent -= 1
        self.emit("}")
        self.emit("return count;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_gui_liste_hent(int id, int index) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5 || !obj->text || !obj->text[0]) { return nl_strdup(\"\"); }")
        self.emit("int current = 0;")
        self.emit("char *cursor = obj->text;")
        self.emit("while (cursor && *cursor) {")
        self.indent += 1
        self.emit("char *line_end = strchr(cursor, '\\n');")
        self.emit("if (current == index) {")
        self.indent += 1
        self.emit("size_t len = line_end ? (size_t)(line_end - cursor) : strlen(cursor);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, cursor, len);")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (!line_end) { break; }")
        self.emit("cursor = line_end + 1;")
        self.emit("current += 1;")
        self.indent -= 1
        self.emit("}")
        self.emit('return nl_strdup("");')
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste_fjern(int id, int index) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5 || !obj->text) { return 0; }")
        self.emit("char *current = obj->text;")
        self.emit("char *cursor = current;")
        self.emit("int seen = 0;")
        self.emit("while (cursor && *cursor) {")
        self.indent += 1
        self.emit("char *line_end = strchr(cursor, '\\n');")
        self.emit("if (seen == index) {")
        self.indent += 1
        self.emit("size_t prefix_len = (size_t)(cursor - current);")
        self.emit("size_t suffix_len = line_end ? strlen(line_end + 1) : 0;")
        self.emit("size_t new_len = prefix_len + suffix_len + 1;")
        self.emit("char *updated = (char *)malloc(new_len);")
        self.emit("if (!updated) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(updated, current, prefix_len);")
        self.emit("if (line_end) { memcpy(updated + prefix_len, line_end + 1, suffix_len + 1); } else { updated[prefix_len] = '\\0'; }")
        self.emit("free(obj->text);")
        self.emit("obj->text = updated;")
        self.emit("if (obj->selected_index == index) { obj->selected_index = -1; } else if (obj->selected_index > index) { obj->selected_index -= 1; }")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (!line_end) { break; }")
        self.emit("cursor = line_end + 1;")
        self.emit("seen += 1;")
        self.indent -= 1
        self.emit("}")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_liste_velg(int id, int index) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5) { return 0; }")
        self.emit("int previous = obj->selected_index;")
        self.emit("char *items = obj->text ? obj->text : \"\";")
        self.emit("int current = 0;")
        self.emit("int selected = -1;")
        self.emit("char *cursor = items;")
        self.emit("while (cursor && *cursor) {")
        self.indent += 1
        self.emit("char *line_end = strchr(cursor, '\\n');")
        self.emit("if (current == index) { selected = current; break; }")
        self.emit("if (!line_end) { break; }")
        self.emit("cursor = line_end + 1;")
        self.emit("current += 1;")
        self.indent -= 1
        self.emit("}")
        self.emit("obj->selected_index = selected;")
        self.emit("if (obj->selected_index != previous && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_gui_liste_valgt(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->kind != 5 || !obj->text) { return nl_strdup(\"\"); }")
        self.emit("int target = obj->selected_index;")
        self.emit("if (target < 0) { return nl_strdup(\"\"); }")
        self.emit("int current = 0;")
        self.emit("char *cursor = obj->text;")
        self.emit("while (cursor && *cursor) {")
        self.indent += 1
        self.emit("char *line_end = strchr(cursor, '\\n');")
        self.emit("if (current == target) {")
        self.indent += 1
        self.emit("size_t len = line_end ? (size_t)(line_end - cursor) : strlen(cursor);")
        self.emit("char *out = (char *)malloc(len + 1);")
        self.emit("if (!out) { perror(\"malloc\"); exit(1); }")
        self.emit("memcpy(out, cursor, len);")
        self.emit("out[len] = '\\0';")
        self.emit("return out;")
        self.indent -= 1
        self.emit("}")
        self.emit("if (!line_end) { break; }")
        self.emit("cursor = line_end + 1;")
        self.emit("current += 1;")
        self.indent -= 1
        self.emit("}")
        self.emit('return nl_strdup("");')
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_pa_klikk(int id, const char *handler) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("free(obj->click_callback);")
        self.emit("obj->click_callback = nl_strdup(handler ? handler : \"\");")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_pa_endring(int id, const char *handler) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("free(obj->change_callback);")
        self.emit("obj->change_callback = nl_strdup(handler ? handler : \"\");")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static const char *nl_gui_normalize_key(const char *key) {")
        self.indent += 1
        self.emit("if (!key) { return \"\"; }")
        self.emit("if (strcmp(key, \"Return\") == 0 || strcmp(key, \"KP_Enter\") == 0) { return \"enter\"; }")
        self.emit("if (strcmp(key, \"Tab\") == 0) { return \"tab\"; }")
        self.emit("return key;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_pa_tast(int id, const char *key, const char *handler) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("const char *normalized = nl_gui_normalize_key(key);")
        self.emit("if (strcmp(normalized, \"tab\") == 0) { free(obj->tab_callback); obj->tab_callback = nl_strdup(handler ? handler : \"\"); }")
        self.emit("else if (strcmp(normalized, \"enter\") == 0) { free(obj->enter_callback); obj->enter_callback = nl_strdup(handler ? handler : \"\"); }")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_trykk(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("if (obj->click_callback && obj->click_callback[0]) { return nl_call_callback(obj->click_callback, id); }")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_trykk_tast(int id, const char *key) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("const char *normalized = nl_gui_normalize_key(key);")
        self.emit("if (strcmp(normalized, \"tab\") == 0 && obj->tab_callback && obj->tab_callback[0]) { return nl_call_callback(obj->tab_callback, id); }")
        self.emit("if (strcmp(normalized, \"enter\") == 0 && obj->enter_callback && obj->enter_callback[0]) { return nl_call_callback(obj->enter_callback, id); }")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_foresatt(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || obj->parent <= 0) { return 0; }")
        self.emit("return obj->parent;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_barn(int parent_id, int index) {")
        self.indent += 1
        self.emit("int seen = 0;")
        self.emit("for (int i = 0; i < nl_gui_count; i++) {")
        self.indent += 1
        self.emit("if (nl_gui_objects[i].parent == parent_id) {")
        self.indent += 1
        self.emit("if (seen == index) { return i + 1; }")
        self.emit("seen += 1;")
        self.indent -= 1
        self.emit("}")
        self.indent -= 1
        self.emit("}")
        self.emit("return 0;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_sett_tekst(int id, const char *text) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("free(obj->text);")
        self.emit("obj->text = nl_strdup(text ? text : \"\");")
        self.emit("if (obj->kind == 8 && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }")
        self.emit("if (obj->kind == 9 && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static char *nl_gui_hent_tekst(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj || !obj->text) { return nl_strdup(\"\"); }")
        self.emit("return nl_strdup(obj->text);")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_vis(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("obj->visible = 1;")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

        self.emit("static int nl_gui_lukk(int id) {")
        self.indent += 1
        self.emit("nl_gui_object *obj = nl_gui_get(id);")
        self.emit("if (!obj) { return 0; }")
        self.emit("obj->visible = 0;")
        self.emit("return id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

    def _tree_uses_gui_runtime(self, tree) -> bool:
        gui_names = {
            "gui_vindu",
            "gui_panel",
            "gui_rad",
            "gui_tekst",
            "gui_tekstboks",
            "gui_liste",
            "gui_liste_legg_til",
            "gui_liste_tom",
            "gui_liste_antall",
            "gui_liste_hent",
            "gui_liste_fjern",
            "gui_liste_filer_tre",
            "gui_liste_valgt",
            "gui_liste_velg",
            "gui_på_klikk",
            "gui_på_endring",
            "gui_på_tast",
            "gui_trykk",
            "gui_trykk_tast",
            "gui_foresatt",
            "gui_barn",
            "gui_editor",
            "gui_editor_hopp_til",
            "gui_editor_cursor",
            "gui_editor_erstatt_fra_til",
            "gui_knapp",
            "gui_etikett",
            "gui_tekstfelt",
            "gui_sett_tekst",
            "gui_hent_tekst",
            "gui_vis",
            "gui_lukk",
            "les_fil",
            "skriv_fil",
            "fil_eksisterer",
            "les_miljo",
            "argv",
            "kjør_kommando",
            "tekst_slice",
            "liste_filer",
            "liste_filer_tre",
            "gui_liste_filer_tre",
        }

        def visit(node) -> bool:
            if node is None:
                return False
            if isinstance(node, ProgramNode):
                return any(visit(fn) for fn in getattr(node, "functions", []))
            if isinstance(node, FunctionNode):
                return visit(node.body)
            if isinstance(node, BlockNode):
                return any(visit(stmt) for stmt in node.statements)
            if isinstance(node, IfNode):
                return visit(node.condition) or visit(node.then_block) or any(visit(cond) or visit(block) for cond, block in getattr(node, "elif_blocks", [])) or visit(getattr(node, "else_block", None))
            if isinstance(node, IfExprNode):
                return visit(node.condition) or visit(node.then_expr) or visit(node.else_expr)
            if isinstance(node, WhileNode):
                return visit(node.condition) or visit(node.body)
            if isinstance(node, ForNode):
                return visit(node.start_expr) or visit(node.end_expr) or visit(node.step_expr) or visit(node.body)
            if isinstance(node, ForEachNode):
                return visit(node.list_expr) or visit(node.body)
            if isinstance(node, ReturnNode):
                return visit(node.expr)
            if isinstance(node, ExprStmtNode):
                return visit(node.expr)
            if isinstance(node, VarDeclareNode):
                return visit(node.expr)
            if isinstance(node, VarSetNode):
                return visit(node.expr)
            if isinstance(node, IndexSetNode):
                return visit(node.index_expr) or visit(node.value_expr)
            if isinstance(node, BinOpNode):
                return visit(node.left) or visit(node.right)
            if isinstance(node, UnaryOpNode):
                return visit(node.node)
            if isinstance(node, CallNode):
                return node.name in gui_names or any(visit(arg) for arg in node.args)
            if isinstance(node, ModuleCallNode):
                return any(visit(arg) for arg in node.args)
            if isinstance(node, ListLiteralNode):
                return any(visit(item) for item in node.items)
            return False

        return visit(tree)

    def emit_callback_dispatcher(self, tree):
        self.emit("static int nl_call_callback(const char *name, int widget_id) {")
        self.indent += 1
        self.emit("if (!name) { return widget_id; }")
        for fn in tree.functions:
            params = getattr(fn, "params", [])
            if len(params) != 1:
                continue
            if params[0].type_name != TYPE_INT or getattr(fn, "return_type", None) != TYPE_INT:
                continue
            short_name = fn.name
            full_name = f"{fn.module_name}.{fn.name}" if getattr(fn, "module_name", None) and fn.module_name != "__main__" else fn.name
            c_name = self.resolve_c_function_name(fn.name, module_name=getattr(fn, "module_name", None))
            self.emit(f'if (nl_streq(name, {self.c_string(short_name)}) || nl_streq(name, {self.c_string(full_name)})) {{')
            self.indent += 1
            self.emit(f"return {c_name}(widget_id);")
            self.indent -= 1
            self.emit("}")
        self.emit("return widget_id;")
        self.indent -= 1
        self.emit("}")
        self.emit()

    def signature(self, fn):
        params = ", ".join(f"{self.c_type(p.type_name)} {p.name}" for p in fn.params)
        c_name = self.resolve_c_function_name(fn.name, module_name=fn.module_name)
        return f"{self.c_type(fn.return_type)} {c_name}({params})"

    def emit_list_literal_assignment(self, name, list_type, node, declare=False):
        ctor = "nl_list_int_new" if list_type == TYPE_LIST_INT else "nl_list_text_new"
        push = "nl_list_int_push" if list_type == TYPE_LIST_INT else "nl_list_text_push"
        prefix = f"{self.c_type(list_type)} " if declare else ""
        self.emit(f"{prefix}{name} = {ctor}();")
        for item in node.items:
            item_code, _ = self.expr_with_type(item)
            self.emit(f"{push}({name}, {item_code});")

    def visit_function(self, fn):
        previous_module = self.current_module
        previous_return_type = self.current_return_type
        self.current_module = getattr(fn, "module_name", "__main__")
        self.current_return_type = fn.return_type
        self.var_types = {p.name: p.type_name for p in fn.params}

        self.emit(self.signature(fn) + " {")
        self.indent += 1

        for stmt in fn.body.statements:
            self.visit_stmt(stmt)

        if fn.return_type in (TYPE_INT, TYPE_BOOL):
            self.emit("return 0;")
        elif fn.return_type == TYPE_TEXT:
            self.emit('return "";')
        elif fn.return_type == TYPE_LIST_INT:
            self.emit("return nl_list_int_new();")
        elif fn.return_type == TYPE_LIST_TEXT:
            self.emit("return nl_list_text_new();")
        else:
            self.emit("return 0;")

        self.indent -= 1
        self.emit("}")
        self.current_module = previous_module
        self.current_return_type = previous_return_type

    def visit_stmt(self, stmt):
        if isinstance(stmt, VarDeclareNode):
            inferred_type = stmt.var_type
            if inferred_type is None:
                if isinstance(stmt.expr, ListLiteralNode):
                    item_types = [self.expr_with_type(item)[1] for item in stmt.expr.items]
                    inferred_type = TYPE_LIST_TEXT if item_types and item_types[0] == TYPE_TEXT else TYPE_LIST_INT
                else:
                    _, inferred_type = self.expr_with_type(stmt.expr)
            self.var_types[stmt.name] = inferred_type
            if isinstance(stmt.expr, ListLiteralNode):
                self.emit_list_literal_assignment(stmt.name, inferred_type, stmt.expr, declare=True)
                return
            expr_code, _expr_type = self.expr_with_type(stmt.expr)
            self.emit(f"{self.c_type(inferred_type)} {stmt.name} = {expr_code};")
            return

        if isinstance(stmt, VarSetNode):
            var_type = self.var_types.get(stmt.name)
            if isinstance(stmt.expr, ListLiteralNode) and var_type in (TYPE_LIST_INT, TYPE_LIST_TEXT):
                self.emit_list_literal_assignment(stmt.name, var_type, stmt.expr, declare=False)
                return
            expr_code, _expr_type = self.expr_with_type(stmt.expr)
            self.emit(f"{stmt.name} = {expr_code};")
            return

        if isinstance(stmt, IndexSetNode):
            idx_code, _ = self.expr_with_type(stmt.index_expr)
            val_code, _ = self.expr_with_type(stmt.value_expr)
            target_type = self.var_types.get(stmt.target_name)
            if target_type == TYPE_LIST_TEXT:
                self.emit(f"{stmt.target_name}->data[{idx_code}] = {val_code};")
            else:
                self.emit(f"{stmt.target_name}->data[{idx_code}] = {val_code};")
            return

        if isinstance(stmt, PrintNode):
            expr_code, expr_type = self.expr_with_type(stmt.expr)
            if expr_type == TYPE_TEXT:
                self.emit(f"nl_print_text({expr_code});")
            else:
                self.emit(f'printf("%d\\n", {expr_code});')
            return

        if isinstance(stmt, IfNode):
            cond_code, _ = self.expr_with_type(stmt.condition)
            self.emit(f"if {self.format_condition(cond_code)} {{")
            self.indent += 1
            for inner in stmt.then_block.statements:
                self.visit_stmt(inner)
            self.indent -= 1
            self.emit("}")

            for elif_cond, elif_block in stmt.elif_blocks:
                elif_code, _ = self.expr_with_type(elif_cond)
                self.emit(f"else if {self.format_condition(elif_code)} {{")
                self.indent += 1
                for inner in elif_block.statements:
                    self.visit_stmt(inner)
                self.indent -= 1
                self.emit("}")

            if stmt.else_block is not None:
                self.emit("else {")
                self.indent += 1
                for inner in stmt.else_block.statements:
                    self.visit_stmt(inner)
                self.indent -= 1
                self.emit("}")
            return

        if isinstance(stmt, WhileNode):
            cond_code, _ = self.expr_with_type(stmt.condition)
            self.emit(f"while {self.format_condition(cond_code)} {{")
            self.indent += 1
            for inner in stmt.body.statements:
                self.visit_stmt(inner)
            self.indent -= 1
            self.emit("}")
            return

        if isinstance(stmt, ForNode):
            var_name = getattr(stmt, "name", None) or getattr(stmt, "var_name", None) or getattr(stmt, "item_name", None)
            start_code, _ = self.expr_with_type(getattr(stmt, "start_expr", getattr(stmt, "start", NumberNode(0))))
            end_code, _ = self.expr_with_type(getattr(stmt, "end_expr", getattr(stmt, "end", NumberNode(0))))
            step_code, _ = self.expr_with_type(getattr(stmt, "step_expr", NumberNode(1)))

            self.temp_counter += 1
            step_var = f"__nl_step_{self.temp_counter}"
            prev_type = self.var_types.get(var_name)
            self.var_types[var_name] = TYPE_INT

            self.emit(
                f"for (int {var_name} = {start_code}, {step_var} = {step_code}; "
                f"({step_var} >= 0 ? {var_name} <= {end_code} : {var_name} >= {end_code}); "
                f"{var_name} += {step_var}) {{"
            )
            self.indent += 1
            for inner in stmt.body.statements:
                self.visit_stmt(inner)
            self.indent -= 1
            self.emit("}")

            if prev_type is None:
                self.var_types.pop(var_name, None)
            else:
                self.var_types[var_name] = prev_type
            return

        if isinstance(stmt, ForEachNode):
            list_code, list_type = self.expr_with_type(stmt.list_expr)
            item_type = TYPE_INT if list_type == TYPE_LIST_INT else TYPE_TEXT
            c_item_type = self.c_type(item_type)

            self.temp_counter += 1
            idx_var = f"__nl_i_{self.temp_counter}"
            len_expr = f"nl_list_int_len({list_code})" if list_type == TYPE_LIST_INT else f"nl_list_text_len({list_code})"
            item_expr = f"{list_code}->data[{idx_var}]"

            prev_type = self.var_types.get(stmt.item_name)

            self.emit(f"for (int {idx_var} = 0; {idx_var} < {len_expr}; {idx_var}++) {{")
            self.indent += 1
            self.emit(f"{c_item_type} {stmt.item_name} = {item_expr};")
            self.var_types[stmt.item_name] = item_type
            for inner in stmt.body.statements:
                self.visit_stmt(inner)
            self.indent -= 1
            self.emit("}")

            if prev_type is None:
                self.var_types.pop(stmt.item_name, None)
            else:
                self.var_types[stmt.item_name] = prev_type
            return

        if isinstance(stmt, ReturnNode):
            expr_code, _expr_type = self.expr_with_type(stmt.expr, self.current_return_type)
            self.emit(f"return {expr_code};")
            return

        if isinstance(stmt, BreakNode):
            self.emit("break;")
            return

        if isinstance(stmt, ContinueNode):
            self.emit("continue;")
            return

        if isinstance(stmt, ExprStmtNode):
            expr_code, _expr_type = self.expr_with_type(stmt.expr)
            self.emit(f"{expr_code};")
            return

    def _is_empty_list(self, node):
        return isinstance(node, ListLiteralNode) and not node.items

    def expr_with_type(self, node, expected_type=None):
        if isinstance(node, NumberNode):
            return str(node.value), TYPE_INT

        if isinstance(node, StringNode):
            return self.c_string(node.value), TYPE_TEXT

        if isinstance(node, BoolNode):
            return ("1" if node.value else "0"), TYPE_BOOL

        if isinstance(node, ListLiteralNode):
            if not node.items:
                if expected_type == TYPE_LIST_TEXT:
                    return ("nl_list_text_new()", TYPE_LIST_TEXT)
                if expected_type == TYPE_LIST_INT:
                    return ("nl_list_int_new()", TYPE_LIST_INT)
                return ("nl_list_int_new()", TYPE_LIST_INT)
            return ("0", TYPE_LIST_INT)

        if isinstance(node, VarAccessNode):
            return node.name, self.var_types.get(node.name, TYPE_INT)

        if isinstance(node, UnaryOpNode):
            inner_code, inner_type = self.expr_with_type(node.node)
            if node.op.typ == "IKKE":
                return f"(!({inner_code}))", TYPE_BOOL
            if node.op.typ == "PLUS":
                return f"(+({inner_code}))", inner_type
            if node.op.typ == "MINUS":
                return f"(-({inner_code}))", inner_type
            return inner_code, inner_type

        if isinstance(node, BinOpNode):
            left_code, left_type = self.expr_with_type(node.left)
            right_code, right_type = self.expr_with_type(node.right)

            if node.op.typ == "PLUS":
                if left_type == TYPE_TEXT and right_type == TYPE_TEXT:
                    return f"nl_concat({left_code}, {right_code})", TYPE_TEXT
                return f"({left_code} + {right_code})", TYPE_INT

            if node.op.typ == "MINUS":
                return f"({left_code} - {right_code})", TYPE_INT
            if node.op.typ == "MUL":
                return f"({left_code} * {right_code})", TYPE_INT
            if node.op.typ == "DIV":
                return f"({left_code} / {right_code})", TYPE_INT
            if node.op.typ == "PERCENT":
                return f"({left_code} % {right_code})", TYPE_INT

            if node.op.typ in ("GT", "LT", "GTE", "LTE"):
                op_map = {"GT": ">", "LT": "<", "GTE": ">=", "LTE": "<="}
                return f"({left_code} {op_map[node.op.typ]} {right_code})", TYPE_BOOL

            if node.op.typ in ("EQ", "NE"):
                if left_type == TYPE_TEXT and right_type == TYPE_TEXT:
                    cmp_expr = f"nl_streq({left_code}, {right_code})"
                    return (cmp_expr if node.op.typ == "EQ" else f"!({cmp_expr})"), TYPE_BOOL
                op = "==" if node.op.typ == "EQ" else "!="
                return f"({left_code} {op} {right_code})", TYPE_BOOL

            if node.op.typ in ("OG", "ELLER"):
                op = "&&" if node.op.typ == "OG" else "||"
                return f"({left_code} {op} {right_code})", TYPE_BOOL

        if isinstance(node, IfExprNode):
            cond_code, _ = self.expr_with_type(node.condition)
            then_code, then_type = self.expr_with_type(node.then_expr, expected_type)
            else_code, else_type = self.expr_with_type(node.else_expr, expected_type)
            if then_type != else_type:
                if self._is_empty_list(node.then_expr) and else_type in (TYPE_LIST_INT, TYPE_LIST_TEXT):
                    then_code, then_type = self.expr_with_type(node.then_expr, else_type)
                elif self._is_empty_list(node.else_expr) and then_type in (TYPE_LIST_INT, TYPE_LIST_TEXT):
                    else_code, else_type = self.expr_with_type(node.else_expr, then_type)
            if then_type != else_type:
                return "0", TYPE_INT
            return f"(({cond_code}) ? {then_code} : {else_code})", then_type

        if isinstance(node, ModuleCallNode):
            symbol, _full_name = self.resolve_symbol(node.func_name, module_name=node.module_name)
            expected_args = list(getattr(symbol, "params", []) if symbol is not None else [])
            args = [
                self.expr_with_type(arg, expected_args[i] if i < len(expected_args) else None)[0]
                for i, arg in enumerate(node.args)
            ]
            c_name = self.resolve_c_function_name(node.func_name, module_name=node.module_name)
            return_type = symbol.return_type if symbol else TYPE_INT
            return f"{c_name}({', '.join(args)})", return_type

        if isinstance(node, CallNode):
            symbol, _full_name = self.resolve_symbol(node.name)
            expected_args = list(getattr(symbol, "params", []) if symbol is not None else [])
            args_with_types = [
                self.expr_with_type(arg, expected_args[i] if i < len(expected_args) else None)
                for i, arg in enumerate(node.args)
            ]
            args = [code for code, _t in args_with_types]

            if node.name == "assert":
                return f"nl_assert({args[0]})", TYPE_INT

            if node.name == "assert_eq":
                arg_type = args_with_types[0][1]
                if arg_type == TYPE_LIST_TEXT:
                    return f"nl_assert_eq_int(nl_list_text_equal({args[0]}, {args[1]}), 1)", TYPE_INT
                if arg_type == TYPE_LIST_INT:
                    return f"nl_assert_eq_int(nl_list_int_equal({args[0]}, {args[1]}), 1)", TYPE_INT
                if arg_type == TYPE_TEXT:
                    return f"nl_assert_eq_text({args[0]}, {args[1]})", TYPE_INT
                return f"nl_assert_eq_int({args[0]}, {args[1]})", TYPE_INT

            if node.name == "assert_ne":
                arg_type = args_with_types[0][1]
                if arg_type == TYPE_TEXT:
                    return f"nl_assert_ne_text({args[0]}, {args[1]})", TYPE_INT
                return f"nl_assert_ne_int({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_vindu":
                return f"nl_gui_vindu({args[0]})", TYPE_INT

            if node.name == "gui_panel":
                return f"nl_gui_panel({args[0]})", TYPE_INT

            if node.name == "gui_rad":
                return f"nl_gui_rad({args[0]})", TYPE_INT

            if node.name == "gui_tekst":
                return f"nl_gui_tekst({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_tekstboks":
                return f"nl_gui_tekstboks({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_editor":
                return f"nl_gui_editor({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_editor_hopp_til":
                return f"nl_gui_editor_hopp_til({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_editor_cursor":
                return f"nl_gui_editor_cursor({args[0]})", TYPE_LIST_TEXT

            if node.name == "gui_editor_erstatt_fra_til":
                return f"nl_gui_editor_replace_range({args[0]}, {args[1]}, {args[2]}, {args[3]}, {args[4]}, {args[5]})", TYPE_INT

            if node.name == "gui_liste":
                return f"nl_gui_liste({args[0]})", TYPE_INT

            if node.name == "gui_liste_legg_til":
                return f"nl_gui_liste_legg_til({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_liste_tom":
                return f"nl_gui_liste_tom({args[0]})", TYPE_INT

            if node.name == "gui_liste_antall":
                return f"nl_gui_liste_antall({args[0]})", TYPE_INT

            if node.name == "gui_liste_hent":
                return f"nl_gui_liste_hent({args[0]}, {args[1]})", TYPE_TEXT

            if node.name == "gui_liste_fjern":
                return f"nl_gui_liste_fjern({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_liste_valgt":
                return f"nl_gui_liste_valgt({args[0]})", TYPE_TEXT

            if node.name == "gui_liste_velg":
                return f"nl_gui_liste_velg({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_på_klikk":
                return f"nl_gui_pa_klikk({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_på_endring":
                return f"nl_gui_pa_endring({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_på_tast":
                return f"nl_gui_pa_tast({args[0]}, {args[1]}, {args[2]})", TYPE_INT

            if node.name == "gui_trykk":
                return f"nl_gui_trykk({args[0]})", TYPE_INT

            if node.name == "gui_trykk_tast":
                return f"nl_gui_trykk_tast({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_foresatt":
                return f"nl_gui_foresatt({args[0]})", TYPE_INT

            if node.name == "gui_barn":
                return f"nl_gui_barn({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_knapp":
                return f"nl_gui_knapp({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_etikett":
                return f"nl_gui_etikett({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_tekstfelt":
                return f"nl_gui_tekstfelt({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_sett_tekst":
                return f"nl_gui_sett_tekst({args[0]}, {args[1]})", TYPE_INT

            if node.name == "gui_hent_tekst":
                return f"nl_gui_hent_tekst({args[0]})", TYPE_TEXT

            if node.name == "gui_vis":
                return f"nl_gui_vis({args[0]})", TYPE_INT

            if node.name == "gui_lukk":
                return f"nl_gui_lukk({args[0]})", TYPE_INT

            if node.name == "les_fil":
                return f"nl_read_file({args[0]})", TYPE_TEXT

            if node.name == "skriv_fil":
                return f"nl_write_file({args[0]}, {args[1]})", TYPE_INT

            if node.name == "fil_eksisterer":
                return f"nl_file_exists({args[0]})", TYPE_BOOL

            if node.name == "les_miljo":
                return f"nl_read_env({args[0]})", TYPE_TEXT

            if node.name == "les_input":
                return f"nl_read_input({args[0]})", TYPE_TEXT

            if node.name == "tekst_trim":
                return f"nl_text_trim({args[0]})", TYPE_TEXT

            if node.name == "tekst_slice":
                return f"nl_text_slice({args[0]}, {args[1]}, {args[2]})", TYPE_TEXT

            if node.name == "tekst_lengde":
                return f"nl_text_length({args[0]})", TYPE_INT

            if node.name == "argv":
                return "nl_read_argv()", TYPE_LIST_TEXT

            if node.name == "sass_til_css":
                return f"nl_sass_to_css({args[0]})", TYPE_TEXT

            if node.name == "kjør_kommando":
                return f"nl_run_command({args[0]})", TYPE_INT

            if node.name == "liste_filer":
                return f"nl_list_files({args[0]})", TYPE_LIST_TEXT

            if node.name == "liste_filer_tre" or node.name == "gui_liste_filer_tre":
                return f"nl_list_files_tree({args[0]})", TYPE_LIST_TEXT

            if node.name == "tekst_fra_heltall":
                return f"nl_int_to_text({args[0]})", TYPE_TEXT

            if node.name == "tekst_fra_bool":
                return f"nl_bool_to_text({args[0]})", TYPE_TEXT

            if node.name == "tekst_til_små":
                return f"nl_text_to_lower({args[0]})", TYPE_TEXT

            if node.name == "tekst_til_store":
                return f"nl_text_to_upper({args[0]})", TYPE_TEXT

            if node.name == "tekst_til_tittel":
                return f"nl_text_to_title({args[0]})", TYPE_TEXT

            if node.name == "tekst_omvendt":
                return f"nl_text_reverse({args[0]})", TYPE_TEXT

            if node.name == "tekst_del_på":
                return f"nl_text_split_by({args[0]}, {args[1]})", TYPE_LIST_TEXT

            if node.name == "del_på":
                return f"nl_text_split_by({args[0]}, {args[1]})", TYPE_LIST_TEXT

            if node.name == "heltall_fra_tekst":
                return f"nl_text_to_int({args[0]})", TYPE_INT

            if node.name == "tekst_slutter_med":
                return f"nl_text_slutter_med({args[0]}, {args[1]})", TYPE_BOOL

            if node.name == "tekst_starter_med":
                return f"nl_text_starter_med({args[0]}, {args[1]})", TYPE_BOOL

            if node.name == "tekst_inneholder":
                return f"nl_text_inneholder({args[0]}, {args[1]})", TYPE_BOOL

            if node.name == "tekst_erstatt":
                return f"nl_text_erstatt({args[0]}, {args[1]}, {args[2]})", TYPE_TEXT

            if node.name == "tekst_er_ordtegn":
                return f"nl_text_er_ordtegn({args[0]})", TYPE_BOOL

            if node.name == "del_linjer":
                return f"nl_split_lines({args[0]})", TYPE_LIST_TEXT

            if node.name == "del_ord":
                return f"nl_split_words({args[0]})", TYPE_LIST_TEXT

            if node.name == "tokeniser_enkel":
                return f"nl_tokenize_simple({args[0]})", TYPE_LIST_TEXT

            if node.name == "tokeniser_uttrykk":
                return f"nl_tokenize_expression({args[0]})", TYPE_LIST_TEXT

            if node.name == "lengde":
                arg_type = args_with_types[0][1]
                if arg_type == TYPE_LIST_TEXT:
                    return f"nl_list_text_len({args[0]})", TYPE_INT
                return f"nl_list_int_len({args[0]})", TYPE_INT

            if node.name == "legg_til":
                list_type = args_with_types[0][1]
                if list_type == TYPE_LIST_TEXT:
                    return f"nl_list_text_push({args[0]}, {args[1]})", TYPE_INT
                return f"nl_list_int_push({args[0]}, {args[1]})", TYPE_INT

            if node.name == "pop_siste":
                list_type = args_with_types[0][1]
                if list_type == TYPE_LIST_TEXT:
                    return f"nl_list_text_pop({args[0]})", TYPE_TEXT
                return f"nl_list_int_pop({args[0]})", TYPE_INT

            if node.name == "fjern_indeks":
                list_type = args_with_types[0][1]
                if list_type == TYPE_LIST_TEXT:
                    return f"nl_list_text_remove({args[0]}, {args[1]})", TYPE_INT
                return f"nl_list_int_remove({args[0]}, {args[1]})", TYPE_INT

            if node.name == "sett_inn":
                list_type = args_with_types[0][1]
                if list_type == TYPE_LIST_TEXT:
                    return f"nl_list_text_set({args[0]}, {args[1]}, {args[2]})", TYPE_INT
                return f"nl_list_int_set({args[0]}, {args[1]}, {args[2]})", TYPE_INT

            c_name = self.resolve_c_function_name(node.name)
            return_type = symbol.return_type if symbol else TYPE_INT
            return f"{c_name}({', '.join(args)})", return_type

        if isinstance(node, IndexNode):
            target_expr = getattr(node, "list_expr", getattr(node, "target", None))
            list_code, list_type = self.expr_with_type(target_expr)
            idx_code, _ = self.expr_with_type(getattr(node, "index_expr", None))
            if list_type == TYPE_LIST_TEXT:
                return f"{list_code}->data[{idx_code}]", TYPE_TEXT
            return f"{list_code}->data[{idx_code}]", TYPE_INT

        return "0", TYPE_INT
