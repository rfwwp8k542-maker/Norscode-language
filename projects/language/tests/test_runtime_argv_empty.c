#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <dirent.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#include <sys/wait.h>
#endif

typedef struct { int *data; int len; int cap; } nl_list_int;
typedef struct { char **data; int len; int cap; } nl_list_text;

static int nl_call_callback(const char *name, int widget_id);

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

static int nl_run_command(nl_list_text *parts) {
    if (!parts || !parts->data || parts->len <= 0) { return 1; }
    char **argv = (char **)calloc((size_t)parts->len + 1, sizeof(char *));
    if (!argv) { perror("calloc"); exit(1); }
    for (int i = 0; i < parts->len; i++) {
        argv[i] = nl_strdup(parts->data[i] ? parts->data[i] : "");
    }
    argv[parts->len] = NULL;
    #ifdef _WIN32
    int status = _spawnvp(_P_WAIT, argv[0], (const char * const *)argv);
    for (int i = 0; i < parts->len; i++) { free(argv[i]); }
    free(argv);
    if (status == -1) { return 1; }
    return status == 0 ? 0 : 1;
    #else
    pid_t pid = fork();
    if (pid == -1) {
        for (int i = 0; i < parts->len; i++) { free(argv[i]); }
        free(argv);
        return 1;
    }
    if (pid == 0) {
        execvp(argv[0], argv);
        _exit(127);
    }
    int status = 1;
    if (waitpid(pid, &status, 0) == -1) {
        for (int i = 0; i < parts->len; i++) { free(argv[i]); }
        free(argv);
        return 1;
    }
    for (int i = 0; i < parts->len; i++) { free(argv[i]); }
    free(argv);
    if (WIFEXITED(status)) { return WEXITSTATUS(status) == 0 ? 0 : WEXITSTATUS(status); }
    if (WIFSIGNALED(status)) { return 128 + WTERMSIG(status); }
    return 1;
    #endif
}

static char *nl_read_input(const char *prompt) {
    (void)prompt;
    return nl_strdup("");
}

static char *nl_int_to_text(int value) {
    char buffer[32];
    snprintf(buffer, sizeof(buffer), "%d", value);
    return nl_strdup(buffer);
}

static int nl_text_er_ordtegn(const char *text) {
    if (!text) { return 0; }
    const unsigned char *s = (const unsigned char *)text;
    unsigned char lead = s[0];
    int width = 1;
    int cp = 0;
    if ((lead & 0x80) == 0) { cp = lead; }
    else if ((lead & 0xE0) == 0xC0) { width = 2; cp = ((lead & 0x1F) << 6) | (s[1] & 0x3F); }
    else if ((lead & 0xF0) == 0xE0) { width = 3; cp = ((lead & 0x0F) << 12) | ((s[1] & 0x3F) << 6) | (s[2] & 0x3F); }
    else if ((lead & 0xF8) == 0xF0) { width = 4; cp = ((lead & 0x07) << 18) | ((s[1] & 0x3F) << 12) | ((s[2] & 0x3F) << 6) | (s[3] & 0x3F); }
    else { return 0; }
    if (s[width] != '\0') { return 0; }
    if ((cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') || cp == '_') { return 1; }
    return cp == 0x00C5 || cp == 0x00E5 || cp == 0x00C6 || cp == 0x00E6 || cp == 0x00D8 || cp == 0x00F8;
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
        if (isalnum((unsigned char)c) || c == '_' || c == '-' || (unsigned char)c >= 128) {
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

static nl_list_text *nl_tokenize_expression(const char *s) {
    nl_list_text *out = nl_list_text_new();
    if (!s) { return out; }
    int in_comment = 0;
    for (const char *p = s; *p; ) {
        char c = *p;
        if (in_comment) {
            if (c == '\n') { in_comment = 0; }
            p++;
            continue;
        }
        if (c == '#') { in_comment = 1; p++; continue; }
        if (isspace((unsigned char)c)) { p++; continue; }
        if (isdigit((unsigned char)c)) {
            char token[256];
            int tlen = 0;
            while (*p && isdigit((unsigned char)*p)) {
                if (tlen < 255) { token[tlen++] = *p; }
                p++;
            }
            token[tlen] = '\0';
            nl_list_text_push(out, nl_strdup(token));
            continue;
        }
        if (isalpha((unsigned char)c) || c == '_' || (unsigned char)c >= 128) {
            char token[256];
            int tlen = 0;
            while (*p && (isalnum((unsigned char)*p) || *p == '_' || (unsigned char)*p >= 128)) {
                if (tlen < 255) { token[tlen++] = *p; }
                p++;
            }
            token[tlen] = '\0';
            nl_list_text_push(out, nl_strdup(token));
            continue;
        }
        if ((c == '&' && p[1] == '&') || (c == '|' && p[1] == '|') || (c == '=' && p[1] == '=') ||
            (c == '!' && p[1] == '=') || (c == '<' && p[1] == '=') || (c == '>' && p[1] == '=') ||
            (c == '+' && p[1] == '=') || (c == '-' && p[1] == '=') || (c == '*' && p[1] == '=') ||
            (c == '/' && p[1] == '=') || (c == '%' && p[1] == '=')) {
            char token[3];
            token[0] = c;
            token[1] = p[1];
            token[2] = '\0';
            nl_list_text_push(out, nl_strdup(token));
            p += 2;
            continue;
        }
        if (c == '(' || c == ')' || c == '+' || c == '-' || c == '*' || c == '/' || c == '%' || c == '<' || c == '>' || c == '=' || c == ';') {
            char token[2];
            token[0] = c;
            token[1] = '\0';
            nl_list_text_push(out, nl_strdup(token));
            p++;
            continue;
        }
        char unknown[2];
        unknown[0] = c;
        unknown[1] = '\0';
        nl_list_text_push(out, nl_strdup(unknown));
        p++;
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

static int nl_text_slutter_med(const char *text, const char *suffix) {
    if (!text) { text = ""; }
    if (!suffix) { suffix = ""; }
    size_t text_len = strlen(text);
    size_t suffix_len = strlen(suffix);
    if (suffix_len > text_len) { return 0; }
    return strcmp(text + (text_len - suffix_len), suffix) == 0;
}

static int nl_text_starter_med(const char *text, const char *prefix) {
    if (!text) { text = ""; }
    if (!prefix) { prefix = ""; }
    size_t text_len = strlen(text);
    size_t prefix_len = strlen(prefix);
    if (prefix_len > text_len) { return 0; }
    return strncmp(text, prefix, prefix_len) == 0;
}

static int nl_text_inneholder(const char *text, const char *needle) {
    if (!text) { text = ""; }
    if (!needle) { needle = ""; }
    return strstr(text, needle) != NULL;
}

static char *nl_text_erstatt(const char *text, const char *old, const char *new_text) {
    if (!text) { text = ""; }
    if (!old) { old = ""; }
    if (!new_text) { new_text = ""; }
    if (!old[0]) { return nl_strdup(text); }
    const char *cursor = text;
    size_t old_len = strlen(old);
    size_t new_len = strlen(new_text);
    size_t count = 0;
    const char *hit = text;
    while ((hit = strstr(hit, old)) != NULL) { count++; hit += old_len; }
    size_t result_len = strlen(text) + count * (new_len - old_len);
    char *out = (char *)malloc(result_len + 1);
    if (!out) { perror("malloc"); exit(1); }
    char *write = out;
    while ((hit = strstr(cursor, old)) != NULL) {
        size_t chunk = (size_t)(hit - cursor);
        memcpy(write, cursor, chunk);
        write += chunk;
        memcpy(write, new_text, new_len);
        write += new_len;
        cursor = hit + old_len;
    }
    strcpy(write, cursor);
    return out;
}

static int nl_utf8_char_width(unsigned char lead) {
    if ((lead & 0x80) == 0) { return 1; }
    if ((lead & 0xE0) == 0xC0) { return 2; }
    if ((lead & 0xF0) == 0xE0) { return 3; }
    if ((lead & 0xF8) == 0xF0) { return 4; }
    return 1;
}

static int nl_utf8_codepoint_at(const char *text, int byte_index) {
    const unsigned char *s = (const unsigned char *)(text ? text : "");
    unsigned char lead = s[byte_index];
    if (lead == '\0') { return -1; }
    if ((lead & 0x80) == 0) { return lead; }
    if ((lead & 0xE0) == 0xC0) { return ((lead & 0x1F) << 6) | (s[byte_index + 1] & 0x3F); }
    if ((lead & 0xF0) == 0xE0) { return ((lead & 0x0F) << 12) | ((s[byte_index + 1] & 0x3F) << 6) | (s[byte_index + 2] & 0x3F); }
    if ((lead & 0xF8) == 0xF0) { return ((lead & 0x07) << 18) | ((s[byte_index + 1] & 0x3F) << 12) | ((s[byte_index + 2] & 0x3F) << 6) | (s[byte_index + 3] & 0x3F); }
    return lead;
}

static int nl_utf8_text_length(const char *text) {
    if (!text) { return 0; }
    int count = 0;
    for (const unsigned char *p = (const unsigned char *)text; *p; p += nl_utf8_char_width(*p)) { count++; }
    return count;
}

static int nl_utf8_char_offset(const char *text, int char_index) {
    if (!text) { return 0; }
    if (char_index <= 0) { return 0; }
    int current = 0;
    int byte_index = 0;
    while (text[byte_index] != '\0' && current < char_index) {
        byte_index += nl_utf8_char_width((unsigned char)text[byte_index]);
        current++;
    }
    return byte_index;
}

static int nl_utf8_is_ordtegn(const char *text) {
    if (!text) { return 0; }
    int len = (int)strlen(text);
    if (len <= 0) { return 0; }
    int cp = nl_utf8_codepoint_at(text, 0);
    if (cp < 0) { return 0; }
    if (text[nl_utf8_char_width((unsigned char)text[0])] != '\0') { return 0; }
    if ((cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z') || cp == '_') { return 1; }
    return cp == 0x00C5 || cp == 0x00E5 || cp == 0x00C6 || cp == 0x00E6 || cp == 0x00D8 || cp == 0x00F8;
}

static nl_list_text *nl_split_lines(const char *s) {
    nl_list_text *out = nl_list_text_new();
    const char *start = s ? s : "";
    const char *p = start;
    if (*p == '\0') {
        nl_list_text_push(out, nl_strdup(""));
        return out;
    }
    while (1) {
        if (*p == '\n' || *p == '\0') {
            size_t len = (size_t)(p - start);
            char *line = (char *)malloc(len + 1);
            if (!line) { perror("malloc"); exit(1); }
            memcpy(line, start, len);
            line[len] = '\0';
            nl_list_text_push(out, line);
            if (*p == '\0') { break; }
            start = p + 1;
            }
            if (*p == '\0') { break; }
            p++;
        }
        return out;
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
    
    static int nl_list_int_equal(nl_list_int *a, nl_list_int *b) {
        if (a == b) { return 1; }
        if (!a || !b) { return 0; }
        if (a->len != b->len) { return 0; }
        for (int i = 0; i < a->len; i++) { if (a->data[i] != b->data[i]) { return 0; } }
        return 1;
    }
    
    static int nl_list_text_equal(nl_list_text *a, nl_list_text *b) {
        if (a == b) { return 1; }
        if (!a || !b) { return 0; }
        if (a->len != b->len) { return 0; }
        for (int i = 0; i < a->len; i++) { if (!nl_streq(a->data[i], b->data[i])) { return 0; } }
        return 1;
    }
    
    static void nl_print_text(const char *s) {
        printf("%s\n", s ? s : "");
    }
    
    static int nl_file_exists(const char *path) {
        if (!path) { return 0; }
        FILE *f = fopen(path, "r");
        if (!f) { return 0; }
        fclose(f);
        return 1;
    }
    
    static char *nl_read_file(const char *path) {
        if (!path) { return nl_strdup(""); }
        FILE *f = fopen(path, "rb");
        if (!f) { return nl_strdup(""); }
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fseek(f, 0, SEEK_SET);
        if (size < 0) { fclose(f); return nl_strdup(""); }
        char *buf = (char *)malloc((size_t)size + 1);
        if (!buf) { fclose(f); perror("malloc"); exit(1); }
        size_t read_n = fread(buf, 1, (size_t)size, f);
        buf[read_n] = '\0';
        fclose(f);
        return buf;
    }
    
    static char *nl_read_env(const char *name) {
        if (!name) { return nl_strdup(""); }
        const char *value = getenv(name);
        return nl_strdup(value ? value : "");
    }
    
    static char *nl_text_trim(const char *text) {
        if (!text) { return nl_strdup(""); }
        const char *start = text;
        while (*start && isspace((unsigned char)*start)) { start++; }
        const char *end = text + strlen(text);
        while (end > start && isspace((unsigned char)*(end - 1))) { end--; }
        size_t len = (size_t)(end - start);
        char *out = (char *)malloc(len + 1);
        if (!out) { perror("malloc"); exit(1); }
        memcpy(out, start, len);
        out[len] = '\0';
        return out;
    }
    
    static int nl_text_length(const char *text) {
        return nl_utf8_text_length(text);
    }
    
    static char *nl_text_slice(const char *text, int start, int end) {
        if (!text) { return nl_strdup(""); }
        int len_text = nl_utf8_text_length(text);
        if (start < 0) { start = 0; }
        if (end < start) { end = start; }
        if (start > len_text) { start = len_text; }
        if (end > len_text) { end = len_text; }
        int start_byte = nl_utf8_char_offset(text, start);
        int end_byte = nl_utf8_char_offset(text, end);
        int len = end_byte - start_byte;
        char *out = (char *)malloc((size_t)len + 1);
        if (!out) { perror("malloc"); exit(1); }
        memcpy(out, text + start_byte, (size_t)len);
        out[len] = '\0';
        return out;
    }
    
    static char *nl_sass_replace_variables(const char *text, nl_list_text *names, nl_list_text *values) {
        char *current = nl_strdup(text ? text : "");
        for (int i = 0; i < nl_list_text_len(names); i++) {
            char *needle = nl_concat("$", names->data[i] ? names->data[i] : "");
            char *next = nl_text_erstatt(current, needle, values->data[i] ? values->data[i] : "");
            free(needle);
            free(current);
            current = next;
        }
        return current;
    }
    
    static char *nl_sass_to_css(const char *source) {
        nl_list_text *lines = nl_split_lines(source ? source : "");
        nl_list_text *names = nl_list_text_new();
        nl_list_text *values = nl_list_text_new();
        nl_list_text *stack = nl_list_text_new();
        char *out = nl_strdup("");
        for (int i = 0; i < nl_list_text_len(lines); i++) {
            char *trimmed = nl_text_trim(lines->data[i]);
            if (!trimmed[0] || (trimmed[0] == '/' && trimmed[1] == '/') || trimmed[0] == '*') { free(trimmed); continue; }
            if (trimmed[0] == '$' && strchr(trimmed, ':') && trimmed[strlen(trimmed) - 1] == ';') {
                char *colon = strchr(trimmed, ':');
                char *name = nl_text_trim(nl_text_slice(trimmed, 1, (int)(colon - trimmed)));
                char *value_raw = nl_text_slice(trimmed, (int)(colon - trimmed) + 1, (int)strlen(trimmed) - 1);
                char *value = nl_text_trim(value_raw);
                nl_list_text_push(names, name);
                nl_list_text_push(values, value);
                free(value_raw);
                free(trimmed);
                continue;
            }
            char *replaced = nl_sass_replace_variables(trimmed, names, values);
            free(trimmed);
            trimmed = replaced;
            size_t len = strlen(trimmed);
            if (len > 0 && trimmed[len - 1] == '{') {
                char *selector = nl_text_trim(nl_text_slice(trimmed, 0, (int)len - 1));
                if (selector[0] == '&' && nl_list_text_len(stack) > 0) {
                    char *parent = stack->data[nl_list_text_len(stack) - 1];
                    char *combined = nl_text_erstatt(selector, "&", parent ? parent : "");
                    free(selector);
                    selector = combined;
                } else if (nl_list_text_len(stack) > 0) {
                    char *parent = stack->data[nl_list_text_len(stack) - 1];
                    char *combined = nl_concat(nl_concat(parent ? parent : "", " "), selector);
                    free(selector);
                    selector = combined;
                }
                nl_list_text_push(stack, selector);
                free(trimmed);
                continue;
            }
            if (strcmp(trimmed, "}") == 0) {
                if (nl_list_text_len(stack) > 0) {
                    free(nl_list_text_pop(stack));
                }
                free(trimmed);
                continue;
            }
            if (strchr(trimmed, ':') && trimmed[len - 1] == ';') {
                char *selector = nl_list_text_len(stack) > 0 ? stack->data[nl_list_text_len(stack) - 1] : "";
                if (selector && selector[0]) {
                    char *block = nl_concat(nl_concat(nl_concat(selector, " { "), trimmed), " }\n");
                    char *next = nl_concat(out, block);
                    free(out);
                    free(block);
                    out = next;
                } else {
                    char *block = nl_concat(trimmed, "\n");
                    char *next = nl_concat(out, block);
                    free(out);
                    free(block);
                    out = next;
                }
                free(trimmed);
                continue;
            }
            free(trimmed);
        }
        return out;
    }
    
    static nl_list_text *nl_read_argv(void) {
        const char *raw = getenv("NORSCODE_ARGS");
        if (!raw || !raw[0]) { return nl_list_text_new(); }
        return nl_split_lines(raw);
    }
    
    static int nl_has_studio_suffix(const char *name) {
        const char *suffixes[] = {".no", ".md", ".toml", ".py", ".sh", ".ps1"};
        size_t name_len = name ? strlen(name) : 0;
        for (size_t i = 0; i < sizeof(suffixes) / sizeof(suffixes[0]); i++) {
            size_t suffix_len = strlen(suffixes[i]);
            if (name_len >= suffix_len && strcmp(name + (name_len - suffix_len), suffixes[i]) == 0) { return 1; }
        }
        return 0;
    }
    
    static int nl_should_skip_entry(const char *name) {
        if (!name || !name[0]) { return 1; }
        if (name[0] == '.') { return 1; }
        return strcmp(name, "build") == 0 || strcmp(name, "dist") == 0 || strcmp(name, "__pycache__") == 0 || strcmp(name, ".venv") == 0;
    }
    
    static void nl_collect_files(const char *root, const char *rel, nl_list_text *out) {
        char *path = rel && rel[0] ? nl_concat(root, rel) : nl_strdup(root);
        DIR *dir = opendir(path);
        if (!dir) { free(path); return; }
        struct dirent *entry;
        while ((entry = readdir(dir)) != NULL) {
            const char *name = entry->d_name;
            if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) { continue; }
            if (nl_should_skip_entry(name)) { continue; }
            char *next_rel = rel && rel[0] ? nl_concat(nl_concat(rel, "/"), name) : nl_strdup(name);
            char *next_path = nl_concat(nl_concat(path, "/"), name);
            struct stat st;
            if (stat(next_path, &st) == 0 && S_ISDIR(st.st_mode)) {
                nl_collect_files(root, next_rel, out);
            } else if (nl_has_studio_suffix(name)) {
                nl_list_text_push(out, next_rel);
                next_rel = NULL;
            }
            if (next_rel) { free(next_rel); }
            free(next_path);
        }
        closedir(dir);
        free(path);
    }
    
    static void nl_collect_files_tree(const char *root, const char *rel, nl_list_text *out) {
        char *path = rel && rel[0] ? nl_concat(root, rel) : nl_strdup(root);
        DIR *dir = opendir(path);
        if (!dir) { free(path); return; }
        struct dirent *entry;
        while ((entry = readdir(dir)) != NULL) {
            const char *name = entry->d_name;
            if (strcmp(name, ".") == 0 || strcmp(name, "..") == 0) { continue; }
            if (nl_should_skip_entry(name)) { continue; }
            char *next_rel = rel && rel[0] ? nl_concat(nl_concat(rel, "/"), name) : nl_strdup(name);
            char *next_path = nl_concat(nl_concat(path, "/"), name);
            struct stat st;
            if (stat(next_path, &st) == 0 && S_ISDIR(st.st_mode)) {
                char *folder = nl_concat(next_rel, "/");
                nl_list_text_push(out, folder);
                free(folder);
                nl_collect_files_tree(root, next_rel, out);
            } else if (nl_has_studio_suffix(name)) {
                nl_list_text_push(out, next_rel);
                next_rel = NULL;
            }
            if (next_rel) { free(next_rel); }
            free(next_path);
        }
        closedir(dir);
        free(path);
    }
    
    static nl_list_text *nl_list_files(const char *root) {
        nl_list_text *out = nl_list_text_new();
        if (!root || !root[0]) { root = "."; }
        nl_collect_files(root, "", out);
        return out;
    }
    
    static nl_list_text *nl_list_files_tree(const char *root) {
        nl_list_text *out = nl_list_text_new();
        if (!root || !root[0]) { root = "."; }
        nl_collect_files_tree(root, "", out);
        return out;
    }
    
    static int nl_write_file(const char *path, const char *text) {
        if (!path) { return 0; }
        FILE *f = fopen(path, "wb");
        if (!f) { return 0; }
        if (text) { fputs(text, f); }
        fclose(f);
        return 1;
    }
    
    int start() {
        return 0;
        return 0;
    }
    
    int main(void) {
        return start();
    }