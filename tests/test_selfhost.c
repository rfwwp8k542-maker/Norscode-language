#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

typedef struct { int *data; int len; int cap; } nl_list_int;
typedef struct { char **data; int len; int cap; } nl_list_text;

static nl_list_int *nl_list_int_new(void) {
    nl_list_int *l = (nl_list_int *)malloc(sizeof(nl_list_int));
    if (!l) { perror("malloc"); exit(1); }
    l->len = 0;
    l->cap = 8;
    l->data = (int *)malloc(sizeof(int) * l->cap);
    if (!l->data) { perror("malloc"); exit(1); }
    return l;
}

static nl_list_text *nl_list_text_new(void) {
    nl_list_text *l = (nl_list_text *)malloc(sizeof(nl_list_text));
    if (!l) { perror("malloc"); exit(1); }
    l->len = 0;
    l->cap = 8;
    l->data = (char **)malloc(sizeof(char *) * l->cap);
    if (!l->data) { perror("malloc"); exit(1); }
    return l;
}

static void nl_list_int_ensure(nl_list_int *l, int need) {
    if (need <= l->cap) { return; }
    while (l->cap < need) { l->cap *= 2; }
    l->data = (int *)realloc(l->data, sizeof(int) * l->cap);
    if (!l->data) { perror("realloc"); exit(1); }
}

static void nl_list_text_ensure(nl_list_text *l, int need) {
    if (need <= l->cap) { return; }
    while (l->cap < need) { l->cap *= 2; }
    l->data = (char **)realloc(l->data, sizeof(char *) * l->cap);
    if (!l->data) { perror("realloc"); exit(1); }
}

static int nl_list_int_len(nl_list_int *l) { return l ? l->len : 0; }
static int nl_list_text_len(nl_list_text *l) { return l ? l->len : 0; }

static int nl_list_int_push(nl_list_int *l, int v) {
    nl_list_int_ensure(l, l->len + 1);
    l->data[l->len++] = v;
    return l->len;
}

static int nl_list_text_push(nl_list_text *l, char *v) {
    nl_list_text_ensure(l, l->len + 1);
    l->data[l->len++] = v;
    return l->len;
}

static int nl_list_int_pop(nl_list_int *l) {
    if (!l || l->len == 0) { return 0; }
    int v = l->data[l->len - 1];
    l->len -= 1;
    return v;
}

static char *nl_list_text_pop(nl_list_text *l) {
    if (!l || l->len == 0) { return ""; }
    char *v = l->data[l->len - 1];
    l->len -= 1;
    return v;
}

static int nl_list_int_remove(nl_list_int *l, int idx) {
    if (!l || idx < 0 || idx >= l->len) { return nl_list_int_len(l); }
    for (int i = idx; i < l->len - 1; i++) { l->data[i] = l->data[i + 1]; }
    l->len -= 1;
    return l->len;
}

static int nl_list_text_remove(nl_list_text *l, int idx) {
    if (!l || idx < 0 || idx >= l->len) { return nl_list_text_len(l); }
    for (int i = idx; i < l->len - 1; i++) { l->data[i] = l->data[i + 1]; }
    l->len -= 1;
    return l->len;
}

static int nl_list_int_set(nl_list_int *l, int idx, int v) {
    if (!l || idx < 0 || idx >= l->len) { return nl_list_int_len(l); }
    l->data[idx] = v;
    return l->len;
}

static int nl_list_text_set(nl_list_text *l, int idx, char *v) {
    if (!l || idx < 0 || idx >= l->len) { return nl_list_text_len(l); }
    l->data[idx] = v;
    return l->len;
}

static char *nl_strdup(const char *s) {
    if (!s) { s = ""; }
    size_t n = strlen(s) + 1;
    char *out = (char *)malloc(n);
    if (!out) { perror("malloc"); exit(1); }
    memcpy(out, s, n);
    return out;
}

static int nl_streq(const char *a, const char *b) {
    if (!a) { a = ""; }
    if (!b) { b = ""; }
    return strcmp(a, b) == 0;
}

static char *nl_concat(const char *a, const char *b) {
    if (!a) { a = ""; }
    if (!b) { b = ""; }
    size_t al = strlen(a);
    size_t bl = strlen(b);
    char *out = (char *)malloc(al + bl + 1);
    if (!out) { perror("malloc"); exit(1); }
    memcpy(out, a, al);
    memcpy(out + al, b, bl);
    out[al + bl] = '\0';
    return out;
}

static char *nl_int_to_text(int value) {
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "%d", value);
    return nl_strdup(buffer);
}

static nl_list_text *nl_split_words(const char *s) {
    nl_list_text *out = nl_list_text_new();
    char *copy = nl_strdup(s ? s : "");
    char *tok = strtok(copy, " \t\r\n");
    while (tok) {
        nl_list_text_push(out, nl_strdup(tok));
        tok = strtok(NULL, " \t\r\n");
    }
    return out;
}

static nl_list_text *nl_tokenize_simple(const char *s) {
    nl_list_text *out = nl_list_text_new();
    if (!s) { return out; }
    char token[256];
    int tlen = 0;
    int in_comment = 0;
    for (const char *p = s; ; ++p) {
        char c = *p;
        if (c == '\0') {
            if (tlen > 0) { token[tlen] = '\0'; nl_list_text_push(out, nl_strdup(token)); }
            break;
        }
        if (in_comment) {
            if (c == '\n') { in_comment = 0; }
            continue;
        }
        if (c == '#') {
            if (tlen > 0) { token[tlen] = '\0'; nl_list_text_push(out, nl_strdup(token)); tlen = 0; }
            in_comment = 1;
            continue;
        }
        if (isalnum((unsigned char)c) || c == '_' || c == '-') {
            if (tlen < 255) { token[tlen++] = c; }
            continue;
        }
        if (tlen > 0) {
            token[tlen] = '\0';
            nl_list_text_push(out, nl_strdup(token));
            tlen = 0;
        }
    }
    return out;
}

static char *nl_bool_to_text(int value) {
    return nl_strdup(value ? "sann" : "usann");
}

static int nl_text_to_int(const char *s) {
    if (!s) { return 0; }
    return (int)strtol(s, NULL, 10);
}

static int nl_assert(int cond) {
    if (!cond) {
        printf("assert failed\n");
        exit(1);
    }
    return 0;
}

static int nl_assert_eq_int(int a, int b) {
    if (a != b) {
        printf("assert_eq failed: %d != %d\n", a, b);
        exit(1);
    }
    return 0;
}

static int nl_assert_ne_int(int a, int b) {
    if (a == b) {
        printf("assert_ne failed: %d == %d\n", a, b);
        exit(1);
    }
    return 0;
}

static int nl_assert_eq_text(const char *a, const char *b) {
    if (!nl_streq(a, b)) {
        printf("assert_eq failed: \"%s\" != \"%s\"\n", a ? a : "", b ? b : "");
        exit(1);
    }
    return 0;
}

static int nl_assert_ne_text(const char *a, const char *b) {
    if (nl_streq(a, b)) {
        printf("assert_ne failed: \"%s\" == \"%s\"\n", a ? a : "", b ? b : "");
        exit(1);
    }
    return 0;
}

static void nl_print_text(const char *s) {
    printf("%s\n", s ? s : "");
}

char * selfhost__compiler__append_linje(char * kilde, char * linje) {
    return nl_concat(nl_concat(kilde, linje), "\n");
    return "";
}

char * selfhost__compiler__instruksjon_til_tekst(char * op, int verdi) {
    if ((((((nl_streq(op, "PUSH") || nl_streq(op, "LABEL")) || nl_streq(op, "JMP")) || nl_streq(op, "JZ")) || nl_streq(op, "CALL")) || nl_streq(op, "STORE")) || nl_streq(op, "LOAD")) {
        return nl_concat(nl_concat(op, " "), nl_int_to_text(verdi));
    }
    return op;
    return "";
}

char * selfhost__compiler__disasm_program(nl_list_text* ops, nl_list_int* verdier) {
    char * out = "";
    int i = 0;
    if (nl_list_text_len(ops) != nl_list_int_len(verdier)) {
        return "/* feil: ops og verdier må ha samme lengde */";
    }
    while (i < nl_list_text_len(ops)) {
        out = selfhost__compiler__append_linje(out, nl_concat(nl_concat(nl_int_to_text(i), ": "), selfhost__compiler__instruksjon_til_tekst(ops->data[i], verdier->data[i])));
        i = (i + 1);
    }
    return out;
    return "";
}

int selfhost__compiler__op_krever_arg(char * op) {
    if ((((((nl_streq(op, "PUSH") || nl_streq(op, "LABEL")) || nl_streq(op, "JMP")) || nl_streq(op, "JZ")) || nl_streq(op, "CALL")) || nl_streq(op, "STORE")) || nl_streq(op, "LOAD")) {
        return 1;
    }
    return 0;
    return 0;
}

int selfhost__compiler__op_kjent(char * op) {
    if (selfhost__compiler__op_krever_arg(op)) {
        return 1;
    }
    if ((((nl_streq(op, "ADD") || nl_streq(op, "SUB")) || nl_streq(op, "MUL")) || nl_streq(op, "DIV")) || nl_streq(op, "MOD")) {
        return 1;
    }
    if ((((nl_streq(op, "EQ") || nl_streq(op, "GT")) || nl_streq(op, "LT")) || nl_streq(op, "AND")) || nl_streq(op, "OR")) {
        return 1;
    }
    if ((((nl_streq(op, "NOT") || nl_streq(op, "DUP")) || nl_streq(op, "POP")) || nl_streq(op, "SWAP")) || nl_streq(op, "OVER")) {
        return 1;
    }
    if ((nl_streq(op, "PRINT") || nl_streq(op, "HALT")) || nl_streq(op, "RET")) {
        return 1;
    }
    return 0;
    return 0;
}

int selfhost__compiler__er_heltall_token(char * tok) {
    int n = nl_text_to_int(tok);
    return nl_streq(nl_int_to_text(n), tok);
    return 0;
}

int selfhost__compiler__stack_behov(char * op) {
    if ((((nl_streq(op, "ADD") || nl_streq(op, "SUB")) || nl_streq(op, "MUL")) || nl_streq(op, "DIV")) || nl_streq(op, "MOD")) {
        return 2;
    }
    if ((((nl_streq(op, "EQ") || nl_streq(op, "GT")) || nl_streq(op, "LT")) || nl_streq(op, "AND")) || nl_streq(op, "OR")) {
        return 2;
    }
    if (((((nl_streq(op, "NOT") || nl_streq(op, "POP")) || nl_streq(op, "DUP")) || nl_streq(op, "STORE")) || nl_streq(op, "PRINT")) || nl_streq(op, "JZ")) {
        return 1;
    }
    if (nl_streq(op, "OVER") || nl_streq(op, "SWAP")) {
        return 2;
    }
    return 0;
    return 0;
}

int selfhost__compiler__stack_endring(char * op) {
    if (((nl_streq(op, "PUSH") || nl_streq(op, "LOAD")) || nl_streq(op, "DUP")) || nl_streq(op, "OVER")) {
        return 1;
    }
    if ((((nl_streq(op, "ADD") || nl_streq(op, "SUB")) || nl_streq(op, "MUL")) || nl_streq(op, "DIV")) || nl_streq(op, "MOD")) {
        return (-(1));
    }
    if ((((nl_streq(op, "EQ") || nl_streq(op, "GT")) || nl_streq(op, "LT")) || nl_streq(op, "AND")) || nl_streq(op, "OR")) {
        return (-(1));
    }
    if (nl_streq(op, "POP") || nl_streq(op, "STORE")) {
        return (-(1));
    }
    return 0;
    return 0;
}

char * selfhost__compiler__sjekk_program(nl_list_text* ops, nl_list_int* verdier) {
    nl_list_int* labels = nl_list_int_new();
    nl_list_int_push(labels, 0);
    int i = 0;
    int n = nl_list_text_len(ops);
    int dybde = 0;
    if (n == 0) {
        return "/* feil: tomt program */";
    }
    nl_list_int_remove(labels, 0);
    while (nl_list_int_len(labels) < n) {
        nl_list_int_push(labels, 0);
    }
    while (i < n) {
        if (nl_streq(ops->data[i], "LABEL")) {
            nl_list_int_set(labels, i, 1);
        }
        i = (i + 1);
    }
    i = 0;
    while (i < n) {
        char * op = ops->data[i];
        if ((nl_streq(op, "JMP") || nl_streq(op, "JZ")) || nl_streq(op, "CALL")) {
            int target = verdier->data[i];
            if ((target < 0) || (target >= n)) {
                return nl_concat(nl_concat("/* feil: ugyldig hopp-target ", nl_int_to_text(target)), " */");
            }
            if (labels->data[target] != 1) {
                return nl_concat(nl_concat("/* feil: hopp-target mangler LABEL ved indeks ", nl_int_to_text(target)), " */");
            }
        }
        if (nl_streq(op, "STORE") || nl_streq(op, "LOAD")) {
            int idx = verdier->data[i];
            if ((idx < 0) || (idx >= 256)) {
                return nl_concat(nl_concat("/* feil: minneindeks utenfor range ", nl_int_to_text(idx)), " */");
            }
        }
        i = (i + 1);
    }
    i = 0;
    while (i < n) {
        char * op2 = ops->data[i];
        int behov = selfhost__compiler__stack_behov(op2);
        if (dybde < behov) {
            return nl_concat(nl_concat(nl_concat(nl_concat("/* feil: stack-underflow ved indeks ", nl_int_to_text(i)), " ("), op2), ") */");
        }
        dybde = (dybde + selfhost__compiler__stack_endring(op2));
        if (dybde < 0) {
            return nl_concat(nl_concat(nl_concat(nl_concat("/* feil: stack-underflow ved indeks ", nl_int_to_text(i)), " ("), op2), ") */");
        }
        i = (i + 1);
    }
    return "";
    return "";
}

char * selfhost__compiler__instruksjon_til_c(char * op, int verdi) {
    if (nl_streq(op, "PUSH")) {
        return nl_concat(nl_concat("stack[sp++] = ", nl_int_to_text(verdi)), ";");
    }
    else if (nl_streq(op, "LABEL")) {
        return nl_concat(nl_concat("L", nl_int_to_text(verdi)), ":;");
    }
    else if (nl_streq(op, "JMP")) {
        return nl_concat(nl_concat("goto L", nl_int_to_text(verdi)), ";");
    }
    else if (nl_streq(op, "JZ")) {
        return nl_concat(nl_concat("if (stack[sp-1] == 0) goto L", nl_int_to_text(verdi)), ";");
    }
    else if (nl_streq(op, "CALL")) {
        return nl_concat(nl_concat("ret_stack[rsp++] = 0; goto L", nl_int_to_text(verdi)), ";");
    }
    else if (nl_streq(op, "RET")) {
        return "goto *labels[0];";
    }
    else if (nl_streq(op, "STORE")) {
        return nl_concat(nl_concat("mem[", nl_int_to_text(verdi)), "] = stack[sp-1]; sp = sp - 1;");
    }
    else if (nl_streq(op, "LOAD")) {
        return nl_concat(nl_concat("stack[sp++] = mem[", nl_int_to_text(verdi)), "];");
    }
    else if (nl_streq(op, "ADD")) {
        return "stack[sp-2] = stack[sp-2] + stack[sp-1]; sp = sp - 1;";
    }
    else if (nl_streq(op, "SUB")) {
        return "stack[sp-2] = stack[sp-2] - stack[sp-1]; sp = sp - 1;";
    }
    else if (nl_streq(op, "MUL")) {
        return "stack[sp-2] = stack[sp-2] * stack[sp-1]; sp = sp - 1;";
    }
    else if (nl_streq(op, "DIV")) {
        return "stack[sp-2] = stack[sp-2] / stack[sp-1]; sp = sp - 1;";
    }
    else if (nl_streq(op, "MOD")) {
        return "stack[sp-2] = stack[sp-2] % stack[sp-1]; sp = sp - 1;";
    }
    else if (nl_streq(op, "EQ")) {
        return "stack[sp-2] = (stack[sp-2] == stack[sp-1]); sp = sp - 1;";
    }
    else if (nl_streq(op, "GT")) {
        return "stack[sp-2] = (stack[sp-2] > stack[sp-1]); sp = sp - 1;";
    }
    else if (nl_streq(op, "LT")) {
        return "stack[sp-2] = (stack[sp-2] < stack[sp-1]); sp = sp - 1;";
    }
    else if (nl_streq(op, "AND")) {
        return "stack[sp-2] = (stack[sp-2] && stack[sp-1]); sp = sp - 1;";
    }
    else if (nl_streq(op, "OR")) {
        return "stack[sp-2] = (stack[sp-2] || stack[sp-1]); sp = sp - 1;";
    }
    else if (nl_streq(op, "NOT")) {
        return "stack[sp-1] = !stack[sp-1];";
    }
    else if (nl_streq(op, "DUP")) {
        return "stack[sp] = stack[sp-1]; sp = sp + 1;";
    }
    else if (nl_streq(op, "POP")) {
        return "sp = sp - 1;";
    }
    else if (nl_streq(op, "SWAP")) {
        return "tmp = stack[sp-1]; stack[sp-1] = stack[sp-2]; stack[sp-2] = tmp;";
    }
    else if (nl_streq(op, "OVER")) {
        return "stack[sp] = stack[sp-2]; sp = sp + 1;";
    }
    else if (nl_streq(op, "PRINT")) {
        return "printf(\"%d\\n\", stack[sp-1]);";
    }
    else if (nl_streq(op, "HALT")) {
        return "return 0;";
    }
    return nl_concat(nl_concat("/* ukjent instruksjon: ", op), " */");
    return "";
}

char * selfhost__compiler__instruksjon_til_c_med_retur(char * op, int verdi, int retur) {
    if (nl_streq(op, "CALL")) {
        return nl_concat(nl_concat(nl_concat(nl_concat("if (rsp >= 256) { printf(\"ret-stack overflow\\n\"); return 1; } ret_stack[rsp++] = ", nl_int_to_text(retur)), "; goto L"), nl_int_to_text(verdi)), ";");
    }
    if (nl_streq(op, "RET")) {
        return "if (rsp <= 0) { printf(\"ret-stack underflow\\n\"); return 1; } goto *labels[ret_stack[--rsp]];";
    }
    if (nl_streq(op, "LOAD")) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("if (sp >= 256) { printf(\"stack overflow\\n\"); return 1; } if (", nl_int_to_text(verdi)), " < 0 || "), nl_int_to_text(verdi)), " >= 256) { printf(\"mem index out of range\\n\"); return 1; } "), selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if (nl_streq(op, "STORE")) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("if (sp < 1) { printf(\"stack underflow\\n\"); return 1; } if (", nl_int_to_text(verdi)), " < 0 || "), nl_int_to_text(verdi)), " >= 256) { printf(\"mem index out of range\\n\"); return 1; } "), selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if ((nl_streq(op, "PUSH") || nl_streq(op, "DUP")) || nl_streq(op, "OVER")) {
        return nl_concat("if (sp >= 256) { printf(\"stack overflow\\n\"); return 1; } ", selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if ((((nl_streq(op, "ADD") || nl_streq(op, "SUB")) || nl_streq(op, "MUL")) || nl_streq(op, "DIV")) || nl_streq(op, "MOD")) {
        return nl_concat("if (sp < 2) { printf(\"stack underflow\\n\"); return 1; } ", selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if ((((nl_streq(op, "EQ") || nl_streq(op, "GT")) || nl_streq(op, "LT")) || nl_streq(op, "AND")) || nl_streq(op, "OR")) {
        return nl_concat("if (sp < 2) { printf(\"stack underflow\\n\"); return 1; } ", selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if (((nl_streq(op, "NOT") || nl_streq(op, "POP")) || nl_streq(op, "PRINT")) || nl_streq(op, "JZ")) {
        return nl_concat("if (sp < 1) { printf(\"stack underflow\\n\"); return 1; } ", selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    if (nl_streq(op, "SWAP")) {
        return nl_concat("if (sp < 2) { printf(\"stack underflow\\n\"); return 1; } ", selfhost__compiler__instruksjon_til_c(op, verdi));
    }
    return selfhost__compiler__instruksjon_til_c(op, verdi);
    return "";
}

char * selfhost__compiler__kompiler_til_c(nl_list_text* ops, nl_list_int* verdier) {
    char * c = "";
    int i = 0;
    int n = nl_list_text_len(ops);
    char * valideringsfeil = "";
    if (nl_list_text_len(ops) != nl_list_int_len(verdier)) {
        return "/* feil: ops og verdier må ha samme lengde */";
    }
    valideringsfeil = selfhost__compiler__sjekk_program(ops, verdier);
    if (!(nl_streq(valideringsfeil, ""))) {
        return valideringsfeil;
    }
    c = selfhost__compiler__append_linje(c, "#include <stdio.h>");
    c = selfhost__compiler__append_linje(c, "");
    c = selfhost__compiler__append_linje(c, "int main(void) {");
    c = selfhost__compiler__append_linje(c, "    int stack[256];");
    c = selfhost__compiler__append_linje(c, "    int mem[256] = {0};");
    c = selfhost__compiler__append_linje(c, "    int ret_stack[256];");
    c = selfhost__compiler__append_linje(c, "    int sp = 0;");
    c = selfhost__compiler__append_linje(c, "    int rsp = 0;");
    c = selfhost__compiler__append_linje(c, "    int tmp = 0;");
    c = selfhost__compiler__append_linje(c, "    void *labels[512] = {0};");
    while (i < n) {
        c = selfhost__compiler__append_linje(c, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("L", nl_int_to_text(i)), ":; labels["), nl_int_to_text(i)), "] = &&L"), nl_int_to_text(i)), ";"));
        c = selfhost__compiler__append_linje(c, nl_concat("    ", selfhost__compiler__instruksjon_til_c_med_retur(ops->data[i], verdier->data[i], (i + 1))));
        i = (i + 1);
    }
    c = selfhost__compiler__append_linje(c, nl_concat(nl_concat(nl_concat(nl_concat("labels[", nl_int_to_text(n)), "] = &&L"), nl_int_to_text(n)), ";"));
    c = selfhost__compiler__append_linje(c, nl_concat(nl_concat("L", nl_int_to_text(n)), ":;"));
    c = selfhost__compiler__append_linje(c, "    return 0;");
    c = selfhost__compiler__append_linje(c, "}");
    return c;
    return "";
}

char * selfhost__compiler__demo_program() {
    nl_list_text* ops = nl_list_text_new();
    nl_list_text_push(ops, "PUSH");
    nl_list_text_push(ops, "PUSH");
    nl_list_text_push(ops, "ADD");
    nl_list_text_push(ops, "PRINT");
    nl_list_text_push(ops, "HALT");
    nl_list_int* verdier = nl_list_int_new();
    nl_list_int_push(verdier, 10);
    nl_list_int_push(verdier, 32);
    nl_list_int_push(verdier, 0);
    nl_list_int_push(verdier, 0);
    nl_list_int_push(verdier, 0);
    return selfhost__compiler__kompiler_til_c(ops, verdier);
    return "";
}

char * selfhost__compiler__kompiler_fra_tokens(nl_list_text* tokens) {
    nl_list_text* ops = nl_list_text_new();
    nl_list_text_push(ops, "HALT");
    nl_list_int* verdier = nl_list_int_new();
    nl_list_int_push(verdier, 0);
    int i = 0;
    while (i < nl_list_text_len(tokens)) {
        char * op = tokens->data[i];
        if ((((((nl_streq(op, "PUSH") || nl_streq(op, "LABEL")) || nl_streq(op, "JMP")) || nl_streq(op, "JZ")) || nl_streq(op, "STORE")) || nl_streq(op, "LOAD")) || nl_streq(op, "CALL")) {
            if ((i + 1) >= nl_list_text_len(tokens)) {
                return "/* feil: op mangler verdi */";
            }
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, nl_text_to_int(tokens->data[(i + 1)]));
            i = (i + 2);
        }
        else {
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, 0);
            i = (i + 1);
        }
    }
    nl_list_text_remove(ops, 0);
    nl_list_int_remove(verdier, 0);
    return selfhost__compiler__kompiler_til_c(ops, verdier);
    return "";
}

char * selfhost__compiler__disasm_fra_tokens(nl_list_text* tokens) {
    nl_list_text* ops = nl_list_text_new();
    nl_list_text_push(ops, "HALT");
    nl_list_int* verdier = nl_list_int_new();
    nl_list_int_push(verdier, 0);
    int i = 0;
    while (i < nl_list_text_len(tokens)) {
        char * op = tokens->data[i];
        if ((((((nl_streq(op, "PUSH") || nl_streq(op, "LABEL")) || nl_streq(op, "JMP")) || nl_streq(op, "JZ")) || nl_streq(op, "STORE")) || nl_streq(op, "LOAD")) || nl_streq(op, "CALL")) {
            if ((i + 1) >= nl_list_text_len(tokens)) {
                return "/* feil: op mangler verdi */";
            }
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, nl_text_to_int(tokens->data[(i + 1)]));
            i = (i + 2);
        }
        else {
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, 0);
            i = (i + 1);
        }
    }
    nl_list_text_remove(ops, 0);
    nl_list_int_remove(verdier, 0);
    return selfhost__compiler__disasm_program(ops, verdier);
    return "";
}

char * selfhost__compiler__disasm_fra_tokens_strict(nl_list_text* tokens) {
    nl_list_text* ops = nl_list_text_new();
    nl_list_text_push(ops, "HALT");
    nl_list_int* verdier = nl_list_int_new();
    nl_list_int_push(verdier, 0);
    int i = 0;
    while (i < nl_list_text_len(tokens)) {
        char * op = tokens->data[i];
        if (selfhost__compiler__op_kjent(op) == 0) {
            return nl_concat(nl_concat("/* feil: ukjent opcode ", op), " */");
        }
        if (selfhost__compiler__op_krever_arg(op)) {
            if ((i + 1) >= nl_list_text_len(tokens)) {
                return "/* feil: op mangler verdi */";
            }
            if (selfhost__compiler__er_heltall_token(tokens->data[(i + 1)]) == 0) {
                return nl_concat(nl_concat("/* feil: ugyldig heltallsargument ", tokens->data[(i + 1)]), " */");
            }
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, nl_text_to_int(tokens->data[(i + 1)]));
            i = (i + 2);
        }
        else {
            nl_list_text_push(ops, op);
            nl_list_int_push(verdier, 0);
            i = (i + 1);
        }
    }
    nl_list_text_remove(ops, 0);
    nl_list_int_remove(verdier, 0);
    return selfhost__compiler__disasm_program(ops, verdier);
    return "";
}

char * selfhost__compiler__disasm_fra_linjer(nl_list_text* linjer) {
    nl_list_text* tokens = nl_list_text_new();
    nl_list_text_push(tokens, "");
    for (int __nl_i_1 = 0; __nl_i_1 < nl_list_text_len(linjer); __nl_i_1++) {
        char * linje = linjer->data[__nl_i_1];
        if (nl_streq(linje, "")) {
            continue;
        }
        nl_list_text_push(tokens, linje);
    }
    nl_list_text_remove(tokens, 0);
    return selfhost__compiler__disasm_fra_tokens(tokens);
    return "";
}

nl_list_text* selfhost__compiler__linjer_til_tokens(nl_list_text* linjer) {
    nl_list_text* tokens = nl_list_text_new();
    nl_list_text_push(tokens, "");
    for (int __nl_i_2 = 0; __nl_i_2 < nl_list_text_len(linjer); __nl_i_2++) {
        char * linje = linjer->data[__nl_i_2];
        if (nl_streq(linje, "")) {
            continue;
        }
        nl_list_text_push(tokens, linje);
    }
    nl_list_text_remove(tokens, 0);
    return tokens;
    return nl_list_text_new();
}

char * selfhost__compiler__kompiler_fra_linjer(nl_list_text* linjer) {
    nl_list_text* tokens = selfhost__compiler__linjer_til_tokens(linjer);
    return selfhost__compiler__kompiler_fra_tokens(tokens);
    return "";
}

char * selfhost__compiler__kompiler_fra_kilde(char * kilde) {
    nl_list_text* tokens = nl_tokenize_simple(kilde);
    return selfhost__compiler__kompiler_fra_tokens(tokens);
    return "";
}

char * selfhost__compiler__disasm_fra_kilde(char * kilde) {
    nl_list_text* tokens = nl_tokenize_simple(kilde);
    return selfhost__compiler__disasm_fra_tokens(tokens);
    return "";
}

char * selfhost__compiler__disasm_fra_kilde_strict(char * kilde) {
    nl_list_text* tokens = nl_tokenize_simple(kilde);
    return selfhost__compiler__disasm_fra_tokens_strict(tokens);
    return "";
}

int start() {
    char * push_linje = selfhost__compiler__instruksjon_til_c("PUSH", 42);
    nl_assert_eq_text(push_linje, "stack[sp++] = 42;");
    char * add_linje = selfhost__compiler__instruksjon_til_c("ADD", 0);
    nl_assert_eq_text(add_linje, "stack[sp-2] = stack[sp-2] + stack[sp-1]; sp = sp - 1;");
    char * halt_linje = selfhost__compiler__instruksjon_til_c("HALT", 0);
    nl_assert_eq_text(halt_linje, "return 0;");
    char * label_linje = selfhost__compiler__instruksjon_til_c("LABEL", 7);
    nl_assert_eq_text(label_linje, "L7:;");
    char * jmp_linje = selfhost__compiler__instruksjon_til_c("JMP", 7);
    nl_assert_eq_text(jmp_linje, "goto L7;");
    char * jz_linje = selfhost__compiler__instruksjon_til_c("JZ", 7);
    nl_assert_eq_text(jz_linje, "if (stack[sp-1] == 0) goto L7;");
    char * call_linje = selfhost__compiler__instruksjon_til_c("CALL", 7);
    nl_assert_eq_text(call_linje, "ret_stack[rsp++] = 0; goto L7;");
    char * ret_linje = selfhost__compiler__instruksjon_til_c("RET", 0);
    nl_assert_eq_text(ret_linje, "goto *labels[0];");
    char * store_linje = selfhost__compiler__instruksjon_til_c("STORE", 3);
    nl_assert_eq_text(store_linje, "mem[3] = stack[sp-1]; sp = sp - 1;");
    char * load_linje = selfhost__compiler__instruksjon_til_c("LOAD", 3);
    nl_assert_eq_text(load_linje, "stack[sp++] = mem[3];");
    char * eq_linje = selfhost__compiler__instruksjon_til_c("EQ", 0);
    nl_assert_eq_text(eq_linje, "stack[sp-2] = (stack[sp-2] == stack[sp-1]); sp = sp - 1;");
    char * gt_linje = selfhost__compiler__instruksjon_til_c("GT", 0);
    nl_assert_eq_text(gt_linje, "stack[sp-2] = (stack[sp-2] > stack[sp-1]); sp = sp - 1;");
    char * lt_linje = selfhost__compiler__instruksjon_til_c("LT", 0);
    nl_assert_eq_text(lt_linje, "stack[sp-2] = (stack[sp-2] < stack[sp-1]); sp = sp - 1;");
    char * mod_linje = selfhost__compiler__instruksjon_til_c("MOD", 0);
    nl_assert_eq_text(mod_linje, "stack[sp-2] = stack[sp-2] % stack[sp-1]; sp = sp - 1;");
    char * and_linje = selfhost__compiler__instruksjon_til_c("AND", 0);
    nl_assert_eq_text(and_linje, "stack[sp-2] = (stack[sp-2] && stack[sp-1]); sp = sp - 1;");
    char * or_linje = selfhost__compiler__instruksjon_til_c("OR", 0);
    nl_assert_eq_text(or_linje, "stack[sp-2] = (stack[sp-2] || stack[sp-1]); sp = sp - 1;");
    char * not_linje = selfhost__compiler__instruksjon_til_c("NOT", 0);
    nl_assert_eq_text(not_linje, "stack[sp-1] = !stack[sp-1];");
    char * dup_linje = selfhost__compiler__instruksjon_til_c("DUP", 0);
    nl_assert_eq_text(dup_linje, "stack[sp] = stack[sp-1]; sp = sp + 1;");
    char * pop_linje = selfhost__compiler__instruksjon_til_c("POP", 0);
    nl_assert_eq_text(pop_linje, "sp = sp - 1;");
    char * swap_linje = selfhost__compiler__instruksjon_til_c("SWAP", 0);
    nl_assert_eq_text(swap_linje, "tmp = stack[sp-1]; stack[sp-1] = stack[sp-2]; stack[sp-2] = tmp;");
    char * over_linje = selfhost__compiler__instruksjon_til_c("OVER", 0);
    nl_assert_eq_text(over_linje, "stack[sp] = stack[sp-2]; sp = sp + 1;");
    char * demo = selfhost__compiler__demo_program();
    nl_assert_ne_text(demo, "");
    nl_list_text* ops = nl_list_text_new();
    nl_list_text_push(ops, "PUSH");
    nl_list_text_push(ops, "PUSH");
    nl_list_text_push(ops, "MUL");
    nl_list_text_push(ops, "PRINT");
    nl_list_text_push(ops, "HALT");
    nl_list_int* verdier = nl_list_int_new();
    nl_list_int_push(verdier, 6);
    nl_list_int_push(verdier, 7);
    nl_list_int_push(verdier, 0);
    nl_list_int_push(verdier, 0);
    nl_list_int_push(verdier, 0);
    char * c = selfhost__compiler__kompiler_til_c(ops, verdier);
    nl_assert_ne_text(c, "");
    nl_list_text* tokens = nl_list_text_new();
    nl_list_text_push(tokens, "PUSH");
    nl_list_text_push(tokens, "8");
    nl_list_text_push(tokens, "PUSH");
    nl_list_text_push(tokens, "9");
    nl_list_text_push(tokens, "ADD");
    nl_list_text_push(tokens, "PRINT");
    nl_list_text_push(tokens, "HALT");
    char * c2 = selfhost__compiler__kompiler_fra_tokens(tokens);
    nl_assert_ne_text(c2, "");
    nl_list_text* tokens_jmp = nl_list_text_new();
    nl_list_text_push(tokens_jmp, "PUSH");
    nl_list_text_push(tokens_jmp, "0");
    nl_list_text_push(tokens_jmp, "JZ");
    nl_list_text_push(tokens_jmp, "1");
    nl_list_text_push(tokens_jmp, "PUSH");
    nl_list_text_push(tokens_jmp, "99");
    nl_list_text_push(tokens_jmp, "PRINT");
    nl_list_text_push(tokens_jmp, "LABEL");
    nl_list_text_push(tokens_jmp, "1");
    nl_list_text_push(tokens_jmp, "HALT");
    char * c2b = selfhost__compiler__kompiler_fra_tokens(tokens_jmp);
    nl_assert_ne_text(c2b, "");
    nl_list_text* tokens_cmp_jz = nl_list_text_new();
    nl_list_text_push(tokens_cmp_jz, "PUSH");
    nl_list_text_push(tokens_cmp_jz, "4");
    nl_list_text_push(tokens_cmp_jz, "PUSH");
    nl_list_text_push(tokens_cmp_jz, "4");
    nl_list_text_push(tokens_cmp_jz, "EQ");
    nl_list_text_push(tokens_cmp_jz, "JZ");
    nl_list_text_push(tokens_cmp_jz, "2");
    nl_list_text_push(tokens_cmp_jz, "PUSH");
    nl_list_text_push(tokens_cmp_jz, "1");
    nl_list_text_push(tokens_cmp_jz, "PRINT");
    nl_list_text_push(tokens_cmp_jz, "LABEL");
    nl_list_text_push(tokens_cmp_jz, "2");
    nl_list_text_push(tokens_cmp_jz, "HALT");
    char * c2c = selfhost__compiler__kompiler_fra_tokens(tokens_cmp_jz);
    nl_assert_ne_text(c2c, "");
    nl_list_text* tokens_stack = nl_list_text_new();
    nl_list_text_push(tokens_stack, "PUSH");
    nl_list_text_push(tokens_stack, "5");
    nl_list_text_push(tokens_stack, "DUP");
    nl_list_text_push(tokens_stack, "ADD");
    nl_list_text_push(tokens_stack, "POP");
    nl_list_text_push(tokens_stack, "HALT");
    char * c2d = selfhost__compiler__kompiler_fra_tokens(tokens_stack);
    nl_assert_ne_text(c2d, "");
    nl_list_text* tokens_stack2 = nl_list_text_new();
    nl_list_text_push(tokens_stack2, "PUSH");
    nl_list_text_push(tokens_stack2, "2");
    nl_list_text_push(tokens_stack2, "PUSH");
    nl_list_text_push(tokens_stack2, "9");
    nl_list_text_push(tokens_stack2, "SWAP");
    nl_list_text_push(tokens_stack2, "OVER");
    nl_list_text_push(tokens_stack2, "ADD");
    nl_list_text_push(tokens_stack2, "HALT");
    char * c2e = selfhost__compiler__kompiler_fra_tokens(tokens_stack2);
    nl_assert_ne_text(c2e, "");
    nl_list_text* tokens_mod = nl_list_text_new();
    nl_list_text_push(tokens_mod, "PUSH");
    nl_list_text_push(tokens_mod, "17");
    nl_list_text_push(tokens_mod, "PUSH");
    nl_list_text_push(tokens_mod, "5");
    nl_list_text_push(tokens_mod, "MOD");
    nl_list_text_push(tokens_mod, "PRINT");
    nl_list_text_push(tokens_mod, "HALT");
    char * c2f = selfhost__compiler__kompiler_fra_tokens(tokens_mod);
    nl_assert_ne_text(c2f, "");
    nl_list_text* tokens_bool = nl_list_text_new();
    nl_list_text_push(tokens_bool, "PUSH");
    nl_list_text_push(tokens_bool, "1");
    nl_list_text_push(tokens_bool, "PUSH");
    nl_list_text_push(tokens_bool, "0");
    nl_list_text_push(tokens_bool, "AND");
    nl_list_text_push(tokens_bool, "NOT");
    nl_list_text_push(tokens_bool, "PRINT");
    nl_list_text_push(tokens_bool, "HALT");
    char * c2g = selfhost__compiler__kompiler_fra_tokens(tokens_bool);
    nl_assert_ne_text(c2g, "");
    nl_list_text* tokens_mem = nl_list_text_new();
    nl_list_text_push(tokens_mem, "PUSH");
    nl_list_text_push(tokens_mem, "42");
    nl_list_text_push(tokens_mem, "STORE");
    nl_list_text_push(tokens_mem, "0");
    nl_list_text_push(tokens_mem, "LOAD");
    nl_list_text_push(tokens_mem, "0");
    nl_list_text_push(tokens_mem, "PUSH");
    nl_list_text_push(tokens_mem, "1");
    nl_list_text_push(tokens_mem, "ADD");
    nl_list_text_push(tokens_mem, "PRINT");
    nl_list_text_push(tokens_mem, "HALT");
    char * c2h = selfhost__compiler__kompiler_fra_tokens(tokens_mem);
    nl_assert_ne_text(c2h, "");
    nl_list_text* tokens_call = nl_list_text_new();
    nl_list_text_push(tokens_call, "CALL");
    nl_list_text_push(tokens_call, "3");
    nl_list_text_push(tokens_call, "HALT");
    nl_list_text_push(tokens_call, "LABEL");
    nl_list_text_push(tokens_call, "3");
    nl_list_text_push(tokens_call, "PUSH");
    nl_list_text_push(tokens_call, "99");
    nl_list_text_push(tokens_call, "RET");
    char * c2i = selfhost__compiler__kompiler_fra_tokens(tokens_call);
    nl_assert_ne_text(c2i, "");
    nl_list_text* tokens_bad_jump = nl_list_text_new();
    nl_list_text_push(tokens_bad_jump, "JMP");
    nl_list_text_push(tokens_bad_jump, "9");
    nl_list_text_push(tokens_bad_jump, "HALT");
    char * c_bad = selfhost__compiler__kompiler_fra_tokens(tokens_bad_jump);
    nl_assert_eq_text(c_bad, "/* feil: ugyldig hopp-target 9 */");
    nl_list_text* tokens_underflow = nl_list_text_new();
    nl_list_text_push(tokens_underflow, "ADD");
    nl_list_text_push(tokens_underflow, "HALT");
    char * c_underflow = selfhost__compiler__kompiler_fra_tokens(tokens_underflow);
    nl_assert_eq_text(c_underflow, "/* feil: stack-underflow ved indeks 0 (ADD) */");
    nl_list_text* tokens_bad_mem = nl_list_text_new();
    nl_list_text_push(tokens_bad_mem, "PUSH");
    nl_list_text_push(tokens_bad_mem, "1");
    nl_list_text_push(tokens_bad_mem, "STORE");
    nl_list_text_push(tokens_bad_mem, "999");
    nl_list_text_push(tokens_bad_mem, "HALT");
    char * c_bad_mem = selfhost__compiler__kompiler_fra_tokens(tokens_bad_mem);
    nl_assert_eq_text(c_bad_mem, "/* feil: minneindeks utenfor range 999 */");
    nl_list_text* tokens_dis = nl_list_text_new();
    nl_list_text_push(tokens_dis, "PUSH");
    nl_list_text_push(tokens_dis, "3");
    nl_list_text_push(tokens_dis, "PUSH");
    nl_list_text_push(tokens_dis, "4");
    nl_list_text_push(tokens_dis, "ADD");
    nl_list_text_push(tokens_dis, "HALT");
    char * dis = selfhost__compiler__disasm_fra_tokens(tokens_dis);
    nl_assert_eq_text(dis, "0: PUSH 3\n1: PUSH 4\n2: ADD\n3: HALT\n");
    char * dis_src = selfhost__compiler__disasm_fra_kilde("# c\nPUSH 3;\nPUSH 4\nADD\nHALT");
    nl_assert_eq_text(dis_src, "0: PUSH 3\n1: PUSH 4\n2: ADD\n3: HALT\n");
    char * dis_src_strict = selfhost__compiler__disasm_fra_kilde_strict("PUSH 3\nPUSH 4\nADD\nHALT");
    nl_assert_eq_text(dis_src_strict, "0: PUSH 3\n1: PUSH 4\n2: ADD\n3: HALT\n");
    char * dis_src_bad = selfhost__compiler__disasm_fra_kilde_strict("PUSH x\nHALT");
    nl_assert_eq_text(dis_src_bad, "/* feil: ugyldig heltallsargument x */");
    nl_list_text* linjer = nl_list_text_new();
    nl_list_text_push(linjer, "");
    nl_list_text_push(linjer, "PUSH");
    nl_list_text_push(linjer, "11");
    nl_list_text_push(linjer, "PUSH");
    nl_list_text_push(linjer, "4");
    nl_list_text_push(linjer, "SUB");
    nl_list_text_push(linjer, "PRINT");
    nl_list_text_push(linjer, "HALT");
    char * c3 = selfhost__compiler__kompiler_fra_linjer(linjer);
    nl_assert_ne_text(c3, "");
    char * kilde = "# kommentar\nPUSH 10;\nPUSH 32\nADD\nPRINT\nHALT";
    char * c4 = selfhost__compiler__kompiler_fra_kilde(kilde);
    nl_assert_eq_text(c4, demo);
    return 0;
    return 0;
}

int main(void) {
    return start();
}