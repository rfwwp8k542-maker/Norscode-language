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

static char *nl_text_to_lower(const char *text) {
    if (!text) { return nl_strdup(""); }
    size_t len = strlen(text);
    char *out = (char *)malloc(len + 1);
    if (!out) { perror("malloc"); exit(1); }
    for (size_t i = 0; i < len; i++) { out[i] = (char)tolower((unsigned char)text[i]); }
    out[len] = '\0';
    return out;
}

static char *nl_text_to_upper(const char *text) {
    if (!text) { return nl_strdup(""); }
    size_t len = strlen(text);
    char *out = (char *)malloc(len + 1);
    if (!out) { perror("malloc"); exit(1); }
    for (size_t i = 0; i < len; i++) { out[i] = (char)toupper((unsigned char)text[i]); }
    out[len] = '\0';
    return out;
}

static char *nl_text_to_title(const char *text) {
    if (!text) { return nl_strdup(""); }
    size_t len = strlen(text);
    char *out = (char *)malloc(len + 1);
    if (!out) { perror("malloc"); exit(1); }
    int new_word = 1;
    for (size_t i = 0; i < len; i++) {
        unsigned char ch = (unsigned char)text[i];
        if (ch < 128 && (isalnum(ch) || ch == '_')) {
            out[i] = (char)(new_word ? toupper(ch) : tolower(ch));
            new_word = 0;
        } else {
            out[i] = (char)ch;
            new_word = 1;
        }
    }
    out[len] = '\0';
    return out;
}

static char *nl_text_reverse(const char *text) {
    if (!text) { return nl_strdup(""); }
    size_t len = strlen(text);
    char *out = (char *)malloc(len + 1);
    if (!out) { perror("malloc"); exit(1); }
    size_t *starts = (size_t *)malloc(sizeof(size_t) * (len + 1));
    size_t *sizes = (size_t *)malloc(sizeof(size_t) * (len + 1));
    if (!starts || !sizes) { perror("malloc"); exit(1); }
    size_t count = 0;
    size_t i = 0;
    while (i < len) {
        size_t start = i;
        unsigned char ch = (unsigned char)text[i];
        if ((ch & 0x80) == 0) {
            i += 1;
        } else if ((ch & 0xE0) == 0xC0) {
            i += 2;
        } else if ((ch & 0xF0) == 0xE0) {
            i += 3;
        } else if ((ch & 0xF8) == 0xF0) {
            i += 4;
        } else {
            i += 1;
        }
        starts[count] = start;
        sizes[count] = i - start;
        count++;
    }
    size_t out_pos = 0;
    for (size_t idx = count; idx > 0; idx--) {
        size_t src = starts[idx - 1];
        size_t cp_len = sizes[idx - 1];
        memcpy(out + out_pos, text + src, cp_len);
        out_pos += cp_len;
    }
    out[out_pos] = '\0';
    free(starts);
    free(sizes);
    return out;
}

static nl_list_text *nl_text_split_by(const char *text, const char *sep) {
    nl_list_text *out = nl_list_text_new();
    if (!text) { text = ""; }
    if (!sep) { sep = ""; }
    size_t sep_len = strlen(sep);
    if (sep_len == 0) {
        nl_list_text_push(out, nl_strdup(text));
        return out;
    }
    const char *cursor = text;
    const char *hit = NULL;
    while ((hit = strstr(cursor, sep)) != NULL) {
        size_t chunk = (size_t)(hit - cursor);
        char *part = (char *)malloc(chunk + 1);
        if (!part) { perror("malloc"); exit(1); }
        memcpy(part, cursor, chunk);
        part[chunk] = '\0';
        nl_list_text_push(out, part);
        cursor = hit + sep_len;
    }
    nl_list_text_push(out, nl_strdup(cursor));
    return out;
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
    
    typedef struct { int kind; int parent; char *text; int visible; int selected_index; int cursor_line; int cursor_col; char *click_callback; char *change_callback; char *tab_callback; char *enter_callback; } nl_gui_object;
    static nl_gui_object *nl_gui_objects = NULL;
    static int nl_gui_count = 0;
    static int nl_gui_cap = 0;
    
    static void nl_gui_ensure(int need) {
        if (need <= nl_gui_cap) { return; }
        if (nl_gui_cap == 0) { nl_gui_cap = 8; }
        while (nl_gui_cap < need) { nl_gui_cap *= 2; }
        nl_gui_objects = (nl_gui_object *)realloc(nl_gui_objects, sizeof(nl_gui_object) * nl_gui_cap);
        if (!nl_gui_objects) { perror("realloc"); exit(1); }
    }
    
    static int nl_gui_create(int kind, int parent, const char *text) {
        nl_gui_ensure(nl_gui_count + 1);
        nl_gui_objects[nl_gui_count].kind = kind;
        nl_gui_objects[nl_gui_count].parent = parent;
        nl_gui_objects[nl_gui_count].text = nl_strdup(text ? text : "");
        nl_gui_objects[nl_gui_count].visible = 0;
        nl_gui_objects[nl_gui_count].selected_index = -1;
        nl_gui_objects[nl_gui_count].cursor_line = 1;
        nl_gui_objects[nl_gui_count].cursor_col = 1;
        nl_gui_objects[nl_gui_count].click_callback = NULL;
        nl_gui_objects[nl_gui_count].change_callback = NULL;
        nl_gui_objects[nl_gui_count].tab_callback = NULL;
        nl_gui_objects[nl_gui_count].enter_callback = NULL;
        nl_gui_count += 1;
        return nl_gui_count;
    }
    
    static nl_gui_object *nl_gui_get(int id) {
        if (id <= 0 || id > nl_gui_count) { return NULL; }
        return &nl_gui_objects[id - 1];
    }
    
    static int nl_gui_vindu(const char *title) {
        return nl_gui_create(1, 0, title);
    }
    
    static int nl_gui_panel(int parent) {
        return nl_gui_create(2, parent, "");
    }
    
    static int nl_gui_rad(int parent) {
        return nl_gui_create(10, parent, "");
    }
    
    static int nl_gui_tekst(int parent, const char *text) {
        return nl_gui_create(3, parent, text);
    }
    
    static int nl_gui_tekstboks(int parent, const char *initial) {
        return nl_gui_create(4, parent, initial);
    }
    
    static int nl_gui_editor(int parent, const char *initial) {
        return nl_gui_create(9, parent, initial);
    }
    
    static int nl_gui_editor_hopp_til(int id, int line) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 9) { return 0; }
        if (line < 1) { line = 1; }
        obj->cursor_line = line;
        obj->cursor_col = 1;
        return id;
    }
    
    static nl_list_text *nl_gui_editor_cursor(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        nl_list_text *out = nl_list_text_new();
        if (!obj || obj->kind != 9) { return out; }
        char line_buffer[32];
        char col_buffer[32];
        snprintf(line_buffer, sizeof(line_buffer), "%d", obj->cursor_line < 1 ? 1 : obj->cursor_line);
        snprintf(col_buffer, sizeof(col_buffer), "%d", obj->cursor_col < 1 ? 1 : obj->cursor_col);
        nl_list_text_push(out, nl_strdup(line_buffer));
        nl_list_text_push(out, nl_strdup(col_buffer));
        return out;
    }
    
    static int nl_gui_editor_replace_range(int id, int start_line, int start_col, int end_line, int end_col, const char *replacement) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 9) { return 0; }
        char *updated = NULL;
        char *current = obj->text ? obj->text : "";
        int line_count = 1;
        for (char *p = current; *p; p++) { if (*p == '\n') { line_count += 1; } }
        if (start_line < 1) { start_line = 1; }
        if (start_col < 1) { start_col = 1; }
        if (end_line < start_line) { end_line = start_line; }
        if (end_col < 1) { end_col = 1; }
        nl_list_text *lines = nl_list_text_new();
        char *copy = nl_strdup(current);
        char *line_tok = strtok(copy, "\n");
        while (line_tok) { nl_list_text_push(lines, nl_strdup(line_tok)); line_tok = strtok(NULL, "\n"); }
        while (lines->len < line_count) { nl_list_text_push(lines, nl_strdup("")); }
        if (start_line > lines->len) { while (lines->len < start_line) { nl_list_text_push(lines, nl_strdup("")); } }
        if (end_line > lines->len) { while (lines->len < end_line) { nl_list_text_push(lines, nl_strdup("")); } }
        int start_idx = start_line - 1;
        int end_idx = end_line - 1;
        char *start_text = lines->data[start_idx] ? lines->data[start_idx] : "";
        char *end_text = lines->data[end_idx] ? lines->data[end_idx] : "";
        char *prefix = nl_text_slice(start_text, 0, start_col - 1);
        char *suffix = nl_text_slice(end_text, end_col - 1, (int)strlen(end_text));
        updated = nl_concat(nl_concat(prefix, replacement ? replacement : ""), suffix);
        free(obj->text);
        obj->text = updated;
        obj->cursor_line = start_line;
        obj->cursor_col = start_col + (replacement ? (int)strlen(replacement) : 0);
        free(prefix);
        free(suffix);
        free(copy);
        for (int i = 0; i < lines->len; i++) { free(lines->data[i]); }
        free(lines->data);
        free(lines);
        return id;
    }
    
    static int nl_gui_liste(int parent) {
        return nl_gui_create(5, parent, "");
    }
    
    static int nl_gui_knapp(int parent, const char *label) {
        return nl_gui_create(6, parent, label);
    }
    
    static int nl_gui_etikett(int parent, const char *label) {
        return nl_gui_create(7, parent, label);
    }
    
    static int nl_gui_tekstfelt(int parent, const char *initial) {
        return nl_gui_create(8, parent, initial);
    }
    
    static int nl_gui_liste_legg_til(int id, const char *text) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5) { return 0; }
        if (!obj->text) { obj->text = nl_strdup(""); }
        char *current = obj->text;
        char *next = current && current[0] ? nl_concat(current, "\n") : nl_strdup("");
        char *updated = nl_concat(next, text ? text : "");
        if (current) { free(current); }
        if (next) { free(next); }
        obj->text = updated;
        return id;
    }
    
    static int nl_gui_liste_tom(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5) { return 0; }
        free(obj->text);
        obj->text = nl_strdup("");
        obj->selected_index = -1;
        return id;
    }
    
    static int nl_gui_liste_antall(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5 || !obj->text || !obj->text[0]) { return 0; }
        int count = 1;
        for (char *p = obj->text; *p; p++) {
            if (*p == '\n') { count += 1; }
        }
        return count;
    }
    
    static char *nl_gui_liste_hent(int id, int index) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5 || !obj->text || !obj->text[0]) { return nl_strdup(""); }
        int current = 0;
        char *cursor = obj->text;
        while (cursor && *cursor) {
            char *line_end = strchr(cursor, '\n');
            if (current == index) {
                size_t len = line_end ? (size_t)(line_end - cursor) : strlen(cursor);
                char *out = (char *)malloc(len + 1);
                if (!out) { perror("malloc"); exit(1); }
                memcpy(out, cursor, len);
                out[len] = '\0';
                return out;
            }
            if (!line_end) { break; }
            cursor = line_end + 1;
            current += 1;
        }
        return nl_strdup("");
    }
    
    static int nl_gui_liste_fjern(int id, int index) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5 || !obj->text) { return 0; }
        char *current = obj->text;
        char *cursor = current;
        int seen = 0;
        while (cursor && *cursor) {
            char *line_end = strchr(cursor, '\n');
            if (seen == index) {
                size_t prefix_len = (size_t)(cursor - current);
                size_t suffix_len = line_end ? strlen(line_end + 1) : 0;
                size_t new_len = prefix_len + suffix_len + 1;
                char *updated = (char *)malloc(new_len);
                if (!updated) { perror("malloc"); exit(1); }
                memcpy(updated, current, prefix_len);
                if (line_end) { memcpy(updated + prefix_len, line_end + 1, suffix_len + 1); } else { updated[prefix_len] = '\0'; }
                free(obj->text);
                obj->text = updated;
                if (obj->selected_index == index) { obj->selected_index = -1; } else if (obj->selected_index > index) { obj->selected_index -= 1; }
                return id;
            }
            if (!line_end) { break; }
            cursor = line_end + 1;
            seen += 1;
        }
        return id;
    }
    
    static int nl_gui_liste_velg(int id, int index) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5) { return 0; }
        int previous = obj->selected_index;
        char *items = obj->text ? obj->text : "";
        int current = 0;
        int selected = -1;
        char *cursor = items;
        while (cursor && *cursor) {
            char *line_end = strchr(cursor, '\n');
            if (current == index) { selected = current; break; }
            if (!line_end) { break; }
            cursor = line_end + 1;
            current += 1;
        }
        obj->selected_index = selected;
        if (obj->selected_index != previous && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }
        return id;
    }
    
    static char *nl_gui_liste_valgt(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->kind != 5 || !obj->text) { return nl_strdup(""); }
        int target = obj->selected_index;
        if (target < 0) { return nl_strdup(""); }
        int current = 0;
        char *cursor = obj->text;
        while (cursor && *cursor) {
            char *line_end = strchr(cursor, '\n');
            if (current == target) {
                size_t len = line_end ? (size_t)(line_end - cursor) : strlen(cursor);
                char *out = (char *)malloc(len + 1);
                if (!out) { perror("malloc"); exit(1); }
                memcpy(out, cursor, len);
                out[len] = '\0';
                return out;
            }
            if (!line_end) { break; }
            cursor = line_end + 1;
            current += 1;
        }
        return nl_strdup("");
    }
    
    static int nl_gui_pa_klikk(int id, const char *handler) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        free(obj->click_callback);
        obj->click_callback = nl_strdup(handler ? handler : "");
        return id;
    }
    
    static int nl_gui_pa_endring(int id, const char *handler) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        free(obj->change_callback);
        obj->change_callback = nl_strdup(handler ? handler : "");
        return id;
    }
    
    static const char *nl_gui_normalize_key(const char *key) {
        if (!key) { return ""; }
        if (strcmp(key, "Return") == 0 || strcmp(key, "KP_Enter") == 0) { return "enter"; }
        if (strcmp(key, "Tab") == 0) { return "tab"; }
        return key;
    }
    
    static int nl_gui_pa_tast(int id, const char *key, const char *handler) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        const char *normalized = nl_gui_normalize_key(key);
        if (strcmp(normalized, "tab") == 0) { free(obj->tab_callback); obj->tab_callback = nl_strdup(handler ? handler : ""); }
        else if (strcmp(normalized, "enter") == 0) { free(obj->enter_callback); obj->enter_callback = nl_strdup(handler ? handler : ""); }
        return id;
    }
    
    static int nl_gui_trykk(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        if (obj->click_callback && obj->click_callback[0]) { return nl_call_callback(obj->click_callback, id); }
        return id;
    }
    
    static int nl_gui_trykk_tast(int id, const char *key) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        const char *normalized = nl_gui_normalize_key(key);
        if (strcmp(normalized, "tab") == 0 && obj->tab_callback && obj->tab_callback[0]) { return nl_call_callback(obj->tab_callback, id); }
        if (strcmp(normalized, "enter") == 0 && obj->enter_callback && obj->enter_callback[0]) { return nl_call_callback(obj->enter_callback, id); }
        return 0;
    }
    
    static int nl_gui_foresatt(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || obj->parent <= 0) { return 0; }
        return obj->parent;
    }
    
    static int nl_gui_barn(int parent_id, int index) {
        int seen = 0;
        for (int i = 0; i < nl_gui_count; i++) {
            if (nl_gui_objects[i].parent == parent_id) {
                if (seen == index) { return i + 1; }
                seen += 1;
            }
        }
        return 0;
    }
    
    static int nl_gui_sett_tekst(int id, const char *text) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        free(obj->text);
        obj->text = nl_strdup(text ? text : "");
        if (obj->kind == 8 && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }
        if (obj->kind == 9 && obj->change_callback && obj->change_callback[0]) { nl_call_callback(obj->change_callback, id); }
        return id;
    }
    
    static char *nl_gui_hent_tekst(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj || !obj->text) { return nl_strdup(""); }
        return nl_strdup(obj->text);
    }
    
    static int nl_gui_vis(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        obj->visible = 1;
        return id;
    }
    
    static int nl_gui_lukk(int id) {
        nl_gui_object *obj = nl_gui_get(id);
        if (!obj) { return 0; }
        obj->visible = 0;
        return id;
    }
    
    char * std_web__http_status_tekst(int kode) {
        if (kode == 200) {
            return "OK";
        }
        else if (kode == 201) {
            return "Created";
        }
        else if (kode == 202) {
            return "Accepted";
        }
        else if (kode == 204) {
            return "No Content";
        }
        else if (kode == 301) {
            return "Moved Permanently";
        }
        else if (kode == 302) {
            return "Found";
        }
        else if (kode == 400) {
            return "Bad Request";
        }
        else if (kode == 401) {
            return "Unauthorized";
        }
        else if (kode == 403) {
            return "Forbidden";
        }
        else if (kode == 404) {
            return "Not Found";
        }
        else if (kode == 405) {
            return "Method Not Allowed";
        }
        else if (kode == 409) {
            return "Conflict";
        }
        else if (kode == 415) {
            return "Unsupported Media Type";
        }
        else if (kode == 422) {
            return "Unprocessable Content";
        }
        else if (kode == 500) {
            return "Internal Server Error";
        }
        else if (kode == 502) {
            return "Bad Gateway";
        }
        return "Unknown Status";
        return "";
    }
    
    char * std_web__http_statuslinje(int kode) {
        char * status = "";
        if (kode == 200) {
            status = "OK";
        }
        else if (kode == 201) {
            status = "Created";
        }
        else if (kode == 202) {
            status = "Accepted";
        }
        else if (kode == 204) {
            status = "No Content";
        }
        else if (kode == 301) {
            status = "Moved Permanently";
        }
        else if (kode == 302) {
            status = "Found";
        }
        else if (kode == 400) {
            status = "Bad Request";
        }
        else if (kode == 401) {
            status = "Unauthorized";
        }
        else if (kode == 403) {
            status = "Forbidden";
        }
        else if (kode == 404) {
            status = "Not Found";
        }
        else if (kode == 405) {
            status = "Method Not Allowed";
        }
        else if (kode == 409) {
            status = "Conflict";
        }
        else if (kode == 415) {
            status = "Unsupported Media Type";
        }
        else if (kode == 422) {
            status = "Unprocessable Content";
        }
        else if (kode == 500) {
            status = "Internal Server Error";
        }
        else if (kode == 502) {
            status = "Bad Gateway";
        }
        else {
            status = "Unknown Status";
        }
        return nl_concat(nl_concat(nl_concat("HTTP/1.1 ", nl_int_to_text(kode)), " "), status);
        return "";
    }
    
    char * std_web__http_header_tekst(char * navn, char * verdi) {
        return nl_concat(nl_concat(navn, ": "), verdi);
        return "";
    }
    
    char * std_web__http_content_type_html() {
        return "text/html; charset=utf-8";
        return "";
    }
    
    char * std_web__http_content_type_json() {
        return "application/json; charset=utf-8";
        return "";
    }
    
    char * std_web__http_content_type_text() {
        return "text/plain; charset=utf-8";
        return "";
    }
    
    char * std_web__http_respons_tekst(int kode, char * content_type, char * body) {
        char * status = "";
        if (kode == 200) {
            status = "OK";
        }
        else if (kode == 201) {
            status = "Created";
        }
        else if (kode == 202) {
            status = "Accepted";
        }
        else if (kode == 204) {
            status = "No Content";
        }
        else if (kode == 301) {
            status = "Moved Permanently";
        }
        else if (kode == 302) {
            status = "Found";
        }
        else if (kode == 400) {
            status = "Bad Request";
        }
        else if (kode == 401) {
            status = "Unauthorized";
        }
        else if (kode == 403) {
            status = "Forbidden";
        }
        else if (kode == 404) {
            status = "Not Found";
        }
        else if (kode == 405) {
            status = "Method Not Allowed";
        }
        else if (kode == 409) {
            status = "Conflict";
        }
        else if (kode == 415) {
            status = "Unsupported Media Type";
        }
        else if (kode == 422) {
            status = "Unprocessable Content";
        }
        else if (kode == 500) {
            status = "Internal Server Error";
        }
        else if (kode == 502) {
            status = "Bad Gateway";
        }
        else {
            status = "Unknown Status";
        }
        char * respons = nl_concat(nl_concat(nl_concat(nl_concat("HTTP/1.1 ", nl_int_to_text(kode)), " "), status), "r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Type: "), content_type), "r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        respons = nl_concat(respons, "r\n");
        return nl_concat(respons, body);
        return "";
    }
    
    char * std_web__http_json_respons(char * body) {
        char * respons = "HTTP/1.1 200 OKr\n";
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Type: "), std_web__http_content_type_json()), "r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        respons = nl_concat(respons, "r\n");
        return nl_concat(respons, body);
        return "";
    }
    
    char * std_web__http_html_respons(char * body) {
        char * respons = "HTTP/1.1 200 OKr\n";
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Type: "), std_web__http_content_type_html()), "r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        respons = nl_concat(respons, "r\n");
        return nl_concat(respons, body);
        return "";
    }
    
    char * std_web__http_tekst_respons(char * body) {
        char * respons = "HTTP/1.1 200 OKr\n";
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Type: "), std_web__http_content_type_text()), "r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        respons = nl_concat(respons, "r\n");
        return nl_concat(respons, body);
        return "";
    }
    
    char * std_web__http_request_tekst(char * method, char * path, char * host, char * content_type, char * body) {
        char * request = nl_concat(nl_concat(nl_concat(method, " "), path), " HTTP/1.1r\n");
        request = nl_concat(nl_concat(nl_concat(request, "Host: "), host), "r\n");
        request = nl_concat(nl_concat(nl_concat(request, "Content-Type: "), content_type), "r\n");
        request = nl_concat(nl_concat(nl_concat(request, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        request = nl_concat(request, "r\n");
        return nl_concat(request, body);
        return "";
    }
    
    nl_list_text* std_web__router_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int std_web__router_registrer(nl_list_text* ruter, char * metode, char * mønster, char * navn) {
        nl_list_text_push(ruter, nl_concat(nl_concat(nl_concat(nl_concat(metode, "\t"), mønster), "\t"), navn));
        return nl_list_text_len(ruter);
        return 0;
    }
    
    int std_web__router_path_match(char * mønster, char * sti) {
        nl_list_text* mønster_deler = nl_text_split_by(mønster, "/");
        nl_list_text* sti_deler = nl_text_split_by(sti, "/");
        nl_list_text* mønster_segmenter = nl_list_text_new();
        nl_list_text* sti_segmenter = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(mønster_deler)) {
            if (!(nl_streq(mønster_deler->data[i], ""))) {
                nl_list_text_push(mønster_segmenter, mønster_deler->data[i]);
            }
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(sti_deler)) {
            if (!(nl_streq(sti_deler->data[i], ""))) {
                nl_list_text_push(sti_segmenter, sti_deler->data[i]);
            }
            i = (i + 1);
        }
        if (nl_list_text_len(mønster_segmenter) != nl_list_text_len(sti_segmenter)) {
            return 0;
        }
        i = 0;
        while (i < nl_list_text_len(mønster_segmenter)) {
            char * mønster_segment = mønster_segmenter->data[i];
            char * sti_segment = sti_segmenter->data[i];
            if ((!((nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")))) && !(nl_streq(mønster_segment, sti_segment))) {
                return 0;
            }
            i = (i + 1);
        }
        return 1;
        return 0;
    }
    
    char * std_web__router_path_param(char * mønster, char * sti, char * navn) {
        nl_list_text* mønster_deler = nl_text_split_by(mønster, "/");
        nl_list_text* sti_deler = nl_text_split_by(sti, "/");
        nl_list_text* mønster_segmenter = nl_list_text_new();
        nl_list_text* sti_segmenter = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(mønster_deler)) {
            if (!(nl_streq(mønster_deler->data[i], ""))) {
                nl_list_text_push(mønster_segmenter, mønster_deler->data[i]);
            }
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(sti_deler)) {
            if (!(nl_streq(sti_deler->data[i], ""))) {
                nl_list_text_push(sti_segmenter, sti_deler->data[i]);
            }
            i = (i + 1);
        }
        if (nl_list_text_len(mønster_segmenter) != nl_list_text_len(sti_segmenter)) {
            return "";
        }
        i = 0;
        while (i < nl_list_text_len(mønster_segmenter)) {
            char * mønster_segment = mønster_segmenter->data[i];
            char * sti_segment = sti_segmenter->data[i];
            if (nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")) {
                char * segment_navn = nl_text_slice(mønster_segment, 1, (nl_text_length(mønster_segment) - 1));
                if (nl_streq(segment_navn, navn)) {
                    return sti_segment;
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * std_web__router_query_param(char * query, char * navn) {
        char * ren_query = query;
        if (nl_text_starter_med(ren_query, "?")) {
            ren_query = nl_text_slice(ren_query, 1, nl_text_length(ren_query));
        }
        nl_list_text* deler = nl_text_split_by(ren_query, "&");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = deler->data[i];
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, "=");
                if ((nl_list_text_len(par_deler) >= 1) && nl_streq(par_deler->data[0], navn)) {
                    if (nl_list_text_len(par_deler) >= 2) {
                        return par_deler->data[1];
                    }
                    return "";
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * std_web__router_join_path(char * prefix, char * sti) {
        if (nl_streq(prefix, "")) {
            return sti;
        }
        if (nl_streq(sti, "")) {
            return prefix;
        }
        int prefix_slutter_med_skråstrek = nl_text_slutter_med(prefix, "/");
        int sti_starter_med_skråstrek = nl_text_starter_med(sti, "/");
        if (prefix_slutter_med_skråstrek && sti_starter_med_skråstrek) {
            return nl_concat(prefix, nl_text_slice(sti, 1, nl_text_length(sti)));
        }
        if (prefix_slutter_med_skråstrek || sti_starter_med_skråstrek) {
            return nl_concat(prefix, sti);
        }
        return nl_concat(nl_concat(prefix, "/"), sti);
        return "";
    }
    
    char * std_web__router_match_rute(nl_list_text* ruter, char * metode, char * sti) {
        int i = 0;
        while (i < nl_list_text_len(ruter)) {
            char * rute = ruter->data[i];
            nl_list_text* deler = nl_text_split_by(rute, "\t");
            if ((nl_list_text_len(deler) >= 3) && nl_streq(deler->data[0], metode)) {
                nl_list_text* mønster_deler = nl_text_split_by(deler->data[1], "/");
                nl_list_text* sti_deler = nl_text_split_by(sti, "/");
                nl_list_text* mønster_segmenter = nl_list_text_new();
                nl_list_text* sti_segmenter = nl_list_text_new();
                int j = 0;
                while (j < nl_list_text_len(mønster_deler)) {
                    if (!(nl_streq(mønster_deler->data[j], ""))) {
                        nl_list_text_push(mønster_segmenter, mønster_deler->data[j]);
                    }
                    j = (j + 1);
                }
                j = 0;
                while (j < nl_list_text_len(sti_deler)) {
                    if (!(nl_streq(sti_deler->data[j], ""))) {
                        nl_list_text_push(sti_segmenter, sti_deler->data[j]);
                    }
                    j = (j + 1);
                }
                if (nl_list_text_len(mønster_segmenter) == nl_list_text_len(sti_segmenter)) {
                    int match = 1;
                    j = 0;
                    while (j < nl_list_text_len(mønster_segmenter)) {
                        char * mønster_segment = mønster_segmenter->data[j];
                        char * sti_segment = sti_segmenter->data[j];
                        if ((!((nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")))) && !(nl_streq(mønster_segment, sti_segment))) {
                            match = 0;
                        }
                        j = (j + 1);
                    }
                    if (match) {
                        return deler->data[2];
                    }
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * std_web__http_query_felt_tekst(char * query, char * navn) {
        char * ren_query = query;
        if (nl_text_starter_med(ren_query, "?")) {
            ren_query = nl_text_slice(ren_query, 1, nl_text_length(ren_query));
        }
        nl_list_text* deler = nl_text_split_by(ren_query, "&");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, "=");
                if ((nl_list_text_len(par_deler) >= 1) && nl_streq(nl_text_trim(par_deler->data[0]), navn)) {
                    if (nl_list_text_len(par_deler) >= 2) {
                        return nl_text_trim(par_deler->data[1]);
                    }
                    return "";
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    int std_web__http_query_felt_heltall(char * query, char * navn) {
        char * ren_query = query;
        if (nl_text_starter_med(ren_query, "?")) {
            ren_query = nl_text_slice(ren_query, 1, nl_text_length(ren_query));
        }
        nl_list_text* deler = nl_text_split_by(ren_query, "&");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, "=");
                if ((nl_list_text_len(par_deler) >= 1) && nl_streq(nl_text_trim(par_deler->data[0]), navn)) {
                    if (nl_list_text_len(par_deler) >= 2) {
                        char * verdi = nl_text_trim(par_deler->data[1]);
                        if (nl_text_starter_med(verdi, "\"") && nl_text_slutter_med(verdi, "\"")) {
                            verdi = nl_text_slice(verdi, 1, (nl_text_length(verdi) - 1));
                        }
                        return nl_text_to_int(verdi);
                    }
                    return 0;
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    int std_web__http_query_felt_bool(char * query, char * navn) {
        char * ren_query = query;
        if (nl_text_starter_med(ren_query, "?")) {
            ren_query = nl_text_slice(ren_query, 1, nl_text_length(ren_query));
        }
        nl_list_text* deler = nl_text_split_by(ren_query, "&");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, "=");
                if ((nl_list_text_len(par_deler) >= 1) && nl_streq(nl_text_trim(par_deler->data[0]), navn)) {
                    if (nl_list_text_len(par_deler) >= 2) {
                        char * verdi = nl_text_to_lower(nl_text_trim(par_deler->data[1]));
                        if (nl_text_starter_med(verdi, "\"") && nl_text_slutter_med(verdi, "\"")) {
                            verdi = nl_text_slice(verdi, 1, (nl_text_length(verdi) - 1));
                        }
                        if (((nl_streq(verdi, "sann") || nl_streq(verdi, "true")) || nl_streq(verdi, "1")) || nl_streq(verdi, "ja")) {
                            return 1;
                        }
                    }
                    return 0;
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    char * std_web__http_path_felt_tekst(char * mønster, char * sti, char * navn) {
        nl_list_text* mønster_deler = nl_text_split_by(mønster, "/");
        nl_list_text* sti_deler = nl_text_split_by(sti, "/");
        nl_list_text* mønster_segmenter = nl_list_text_new();
        nl_list_text* sti_segmenter = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(mønster_deler)) {
            if (!(nl_streq(mønster_deler->data[i], ""))) {
                nl_list_text_push(mønster_segmenter, mønster_deler->data[i]);
            }
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(sti_deler)) {
            if (!(nl_streq(sti_deler->data[i], ""))) {
                nl_list_text_push(sti_segmenter, sti_deler->data[i]);
            }
            i = (i + 1);
        }
        if (nl_list_text_len(mønster_segmenter) != nl_list_text_len(sti_segmenter)) {
            return "";
        }
        i = 0;
        while (i < nl_list_text_len(mønster_segmenter)) {
            char * mønster_segment = mønster_segmenter->data[i];
            char * sti_segment = sti_segmenter->data[i];
            if (nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")) {
                char * segment_navn = nl_text_slice(mønster_segment, 1, (nl_text_length(mønster_segment) - 1));
                if (nl_streq(segment_navn, navn)) {
                    return sti_segment;
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    int std_web__http_path_felt_heltall(char * mønster, char * sti, char * navn) {
        nl_list_text* mønster_deler = nl_text_split_by(mønster, "/");
        nl_list_text* sti_deler = nl_text_split_by(sti, "/");
        nl_list_text* mønster_segmenter = nl_list_text_new();
        nl_list_text* sti_segmenter = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(mønster_deler)) {
            if (!(nl_streq(mønster_deler->data[i], ""))) {
                nl_list_text_push(mønster_segmenter, mønster_deler->data[i]);
            }
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(sti_deler)) {
            if (!(nl_streq(sti_deler->data[i], ""))) {
                nl_list_text_push(sti_segmenter, sti_deler->data[i]);
            }
            i = (i + 1);
        }
        if (nl_list_text_len(mønster_segmenter) != nl_list_text_len(sti_segmenter)) {
            return 0;
        }
        i = 0;
        while (i < nl_list_text_len(mønster_segmenter)) {
            char * mønster_segment = mønster_segmenter->data[i];
            char * sti_segment = sti_segmenter->data[i];
            if (nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")) {
                char * segment_navn = nl_text_slice(mønster_segment, 1, (nl_text_length(mønster_segment) - 1));
                if (nl_streq(segment_navn, navn)) {
                    return nl_text_to_int(sti_segment);
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    int std_web__http_path_felt_bool(char * mønster, char * sti, char * navn) {
        nl_list_text* mønster_deler = nl_text_split_by(mønster, "/");
        nl_list_text* sti_deler = nl_text_split_by(sti, "/");
        nl_list_text* mønster_segmenter = nl_list_text_new();
        nl_list_text* sti_segmenter = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(mønster_deler)) {
            if (!(nl_streq(mønster_deler->data[i], ""))) {
                nl_list_text_push(mønster_segmenter, mønster_deler->data[i]);
            }
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(sti_deler)) {
            if (!(nl_streq(sti_deler->data[i], ""))) {
                nl_list_text_push(sti_segmenter, sti_deler->data[i]);
            }
            i = (i + 1);
        }
        if (nl_list_text_len(mønster_segmenter) != nl_list_text_len(sti_segmenter)) {
            return 0;
        }
        i = 0;
        while (i < nl_list_text_len(mønster_segmenter)) {
            char * mønster_segment = mønster_segmenter->data[i];
            char * sti_segment = sti_segmenter->data[i];
            if (nl_text_starter_med(mønster_segment, "{") && nl_text_slutter_med(mønster_segment, "}")) {
                char * segment_navn = nl_text_slice(mønster_segment, 1, (nl_text_length(mønster_segment) - 1));
                if (nl_streq(segment_navn, navn)) {
                    char * verdi = nl_text_to_lower(sti_segment);
                    if (((nl_streq(verdi, "sann") || nl_streq(verdi, "true")) || nl_streq(verdi, "1")) || nl_streq(verdi, "ja")) {
                        return 1;
                    }
                    return 0;
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    char * std_web__http_body_json_felt_tekst(char * body, char * navn) {
        char * ren_body = nl_text_trim(body);
        if (!((nl_text_starter_med(ren_body, "{") && nl_text_slutter_med(ren_body, "}")))) {
            return "";
        }
        char * innhold = nl_text_slice(ren_body, 1, (nl_text_length(ren_body) - 1));
        nl_list_text* deler = nl_text_split_by(innhold, ",");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, ":");
                if (nl_list_text_len(par_deler) >= 2) {
                    char * nøkkel = nl_text_trim(par_deler->data[0]);
                    char * verdi = nl_text_trim(par_deler->data[1]);
                    if (nl_text_starter_med(nøkkel, "\"") && nl_text_slutter_med(nøkkel, "\"")) {
                        nøkkel = nl_text_slice(nøkkel, 1, (nl_text_length(nøkkel) - 1));
                    }
                    if (nl_streq(nøkkel, navn)) {
                        if (nl_text_starter_med(verdi, "\"") && nl_text_slutter_med(verdi, "\"")) {
                            return nl_text_slice(verdi, 1, (nl_text_length(verdi) - 1));
                        }
                        return verdi;
                    }
                }
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    int std_web__http_body_json_felt_heltall(char * body, char * navn) {
        char * ren_body = nl_text_trim(body);
        if (!((nl_text_starter_med(ren_body, "{") && nl_text_slutter_med(ren_body, "}")))) {
            return 0;
        }
        char * innhold = nl_text_slice(ren_body, 1, (nl_text_length(ren_body) - 1));
        nl_list_text* deler = nl_text_split_by(innhold, ",");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, ":");
                if (nl_list_text_len(par_deler) >= 2) {
                    char * nøkkel = nl_text_trim(par_deler->data[0]);
                    char * verdi = nl_text_trim(par_deler->data[1]);
                    if (nl_text_starter_med(nøkkel, "\"") && nl_text_slutter_med(nøkkel, "\"")) {
                        nøkkel = nl_text_slice(nøkkel, 1, (nl_text_length(nøkkel) - 1));
                    }
                    if (nl_streq(nøkkel, navn)) {
                        if (nl_text_starter_med(verdi, "\"") && nl_text_slutter_med(verdi, "\"")) {
                            verdi = nl_text_slice(verdi, 1, (nl_text_length(verdi) - 1));
                        }
                        return nl_text_to_int(verdi);
                    }
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    int std_web__http_body_json_felt_bool(char * body, char * navn) {
        char * ren_body = nl_text_trim(body);
        if (!((nl_text_starter_med(ren_body, "{") && nl_text_slutter_med(ren_body, "}")))) {
            return 0;
        }
        char * innhold = nl_text_slice(ren_body, 1, (nl_text_length(ren_body) - 1));
        nl_list_text* deler = nl_text_split_by(innhold, ",");
        int i = 0;
        while (i < nl_list_text_len(deler)) {
            char * par = nl_text_trim(deler->data[i]);
            if (!(nl_streq(par, ""))) {
                nl_list_text* par_deler = nl_text_split_by(par, ":");
                if (nl_list_text_len(par_deler) >= 2) {
                    char * nøkkel = nl_text_trim(par_deler->data[0]);
                    char * verdi = nl_text_to_lower(nl_text_trim(par_deler->data[1]));
                    if (nl_text_starter_med(nøkkel, "\"") && nl_text_slutter_med(nøkkel, "\"")) {
                        nøkkel = nl_text_slice(nøkkel, 1, (nl_text_length(nøkkel) - 1));
                    }
                    if (nl_streq(nøkkel, navn)) {
                        if (nl_text_starter_med(verdi, "\"") && nl_text_slutter_med(verdi, "\"")) {
                            verdi = nl_text_slice(verdi, 1, (nl_text_length(verdi) - 1));
                        }
                        if (((nl_streq(verdi, "sann") || nl_streq(verdi, "true")) || nl_streq(verdi, "1")) || nl_streq(verdi, "ja")) {
                            return 1;
                        }
                        return 0;
                    }
                }
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    char * std_web__http_typed_input_feil_respons(char * kilde, char * navn, char * forventet, char * verdi) {
        char * body = nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("{\"detail\":[{\"source\":\"", kilde), "\",\"field\":\""), navn), "\",\"expected\":\""), forventet), "\",\"received\":\""), verdi), "\"}]}");
        char * respons = "HTTP/1.1 422 Unprocessable Contentr\n";
        respons = nl_concat(respons, "Content-Type: application/json; charset=utf-8r\n");
        respons = nl_concat(nl_concat(nl_concat(respons, "Content-Length: "), nl_int_to_text(nl_text_length(body))), "r\n");
        respons = nl_concat(respons, "r\n");
        return nl_concat(respons, body);
        return "";
    }
    
    nl_list_text* std_web__schema_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int std_web__schema_felt_tekst(nl_list_text* schema, char * navn, int påkrevd, char * standard, char * eksempel, char * verdier, char * barn_schema) {
        nl_list_text_push(schema, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(navn, "\ttekst\t"), nl_bool_to_text(påkrevd)), "\t"), standard), "\t"), eksempel), "\t"), verdier), "\t"), barn_schema));
        return nl_list_text_len(schema);
        return 0;
    }
    
    int std_web__schema_felt_heltall(nl_list_text* schema, char * navn, int påkrevd, char * standard, char * eksempel, char * verdier, char * barn_schema) {
        nl_list_text_push(schema, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(navn, "\theltall\t"), nl_bool_to_text(påkrevd)), "\t"), standard), "\t"), eksempel), "\t"), verdier), "\t"), barn_schema));
        return nl_list_text_len(schema);
        return 0;
    }
    
    int std_web__schema_felt_bool(nl_list_text* schema, char * navn, int påkrevd, char * standard, char * eksempel, char * verdier, char * barn_schema) {
        nl_list_text_push(schema, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(navn, "\tbool\t"), nl_bool_to_text(påkrevd)), "\t"), standard), "\t"), eksempel), "\t"), verdier), "\t"), barn_schema));
        return nl_list_text_len(schema);
        return 0;
    }
    
    int std_web__schema_felt_objekt(nl_list_text* schema, char * navn, int påkrevd, char * standard, char * eksempel, char * barn_schema) {
        nl_list_text_push(schema, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(navn, "\tobjekt\t"), nl_bool_to_text(påkrevd)), "\t"), standard), "\t"), eksempel), "\t\t"), barn_schema));
        return nl_list_text_len(schema);
        return 0;
    }
    
    int std_web__schema_felt_liste(nl_list_text* schema, char * navn, char * element_type, int påkrevd, char * standard, char * eksempel, char * verdier, char * barn_schema) {
        nl_list_text_push(schema, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(navn, "\tliste_"), element_type), "\t"), nl_bool_to_text(påkrevd)), "\t"), standard), "\t"), eksempel), "\t"), verdier), "\t"), barn_schema));
        return nl_list_text_len(schema);
        return 0;
    }
    
    int std_web__schema_felt_antall(nl_list_text* schema) {
        return nl_list_text_len(schema);
        return 0;
    }
    
    char * std_web__schema_felt_navn(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 1) {
            return deler->data[0];
        }
        return "";
        return "";
    }
    
    char * std_web__schema_felt_type(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 2) {
            return deler->data[1];
        }
        return "";
        return "";
    }
    
    int std_web__schema_felt_p_krevd(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return 0;
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 3) {
            return nl_streq(deler->data[2], "sann");
        }
        return 0;
        return 0;
    }
    
    char * std_web__schema_felt_standard(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 4) {
            return deler->data[3];
        }
        return "";
        return "";
    }
    
    char * std_web__schema_felt_eksempel(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 5) {
            return deler->data[4];
        }
        return "";
        return "";
    }
    
    char * std_web__schema_felt_verdier(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 6) {
            return deler->data[5];
        }
        return "";
        return "";
    }
    
    char * std_web__schema_felt_barn_schema(nl_list_text* schema, int indeks) {
        if ((indeks < 0) || (indeks >= nl_list_text_len(schema))) {
            return "";
        }
        nl_list_text* deler = nl_text_split_by(schema->data[indeks], "\t");
        if (nl_list_text_len(deler) >= 7) {
            return deler->data[6];
        }
        return "";
        return "";
    }
    
    int std_web__schema_felt_indeks(nl_list_text* schema, char * navn) {
        int i = 0;
        while (i < nl_list_text_len(schema)) {
            nl_list_text* deler = nl_text_split_by(schema->data[i], "\t");
            if ((nl_list_text_len(deler) >= 1) && nl_streq(deler->data[0], navn)) {
                return i;
            }
            i = (i + 1);
        }
        return (-(1));
        return 0;
    }
    
    int std_web__schema_verdi_er_heltall(char * verdi) {
        char * ren = nl_text_trim(verdi);
        if (nl_streq(ren, "")) {
            return 0;
        }
        return nl_streq(nl_int_to_text(nl_text_to_int(ren)), ren);
        return 0;
    }
    
    int std_web__schema_verdi_er_bool(char * verdi) {
        char * ren = nl_text_to_lower(nl_text_trim(verdi));
        if (((((((nl_streq(ren, "sann") || nl_streq(ren, "usann")) || nl_streq(ren, "true")) || nl_streq(ren, "false")) || nl_streq(ren, "1")) || nl_streq(ren, "0")) || nl_streq(ren, "ja")) || nl_streq(ren, "nei")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    int std_web__schema_verdi_type_ok(char * type, char * verdi) {
        if (nl_streq(type, "tekst")) {
            return 1;
        }
        if (nl_streq(type, "heltall")) {
            return std_web__schema_verdi_er_heltall(verdi);
        }
        if (nl_streq(type, "bool")) {
            return std_web__schema_verdi_er_bool(verdi);
        }
        if (nl_streq(type, "objekt")) {
            char * ren = nl_text_trim(verdi);
            return (nl_text_starter_med(ren, "{") && nl_text_slutter_med(ren, "}"));
        }
        if (nl_text_starter_med(type, "liste_")) {
            char * ren = nl_text_trim(verdi);
            return (nl_text_starter_med(ren, "[") && nl_text_slutter_med(ren, "]"));
        }
        return 1;
        return 0;
    }
    
    int std_web__schema_enum_inneholder(char * verdier, char * verdi) {
        if (nl_streq(verdier, "")) {
            return 1;
        }
        nl_list_text* alternativer = nl_text_split_by(verdier, "|");
        int i = 0;
        while (i < nl_list_text_len(alternativer)) {
            if (nl_streq(nl_text_trim(alternativer->data[i]), verdi)) {
                return 1;
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    char * std_web__schema_valider_felt(nl_list_text* schema, char * navn, char * verdi) {
        int indeks = std_web__schema_felt_indeks(schema, navn);
        if (indeks < 0) {
            return std_web__http_typed_input_feil_respons("schema", navn, "kjent felt", verdi);
        }
        if (nl_streq(nl_text_trim(verdi), "") && (!(std_web__schema_felt_p_krevd(schema, indeks)))) {
            return "";
        }
        if (std_web__schema_felt_p_krevd(schema, indeks) && nl_streq(nl_text_trim(verdi), "")) {
            return std_web__http_typed_input_feil_respons("schema", navn, std_web__schema_felt_type(schema, indeks), verdi);
        }
        char * type = std_web__schema_felt_type(schema, indeks);
        char * ren = nl_text_trim(verdi);
        if (nl_streq(type, "heltall")) {
            if (!(std_web__schema_verdi_er_heltall(ren))) {
                return std_web__http_typed_input_feil_respons("schema", navn, "heltall", verdi);
            }
        }
        else if (nl_streq(type, "bool")) {
            if (!(std_web__schema_verdi_er_bool(ren))) {
                return std_web__http_typed_input_feil_respons("schema", navn, "bool", verdi);
            }
        }
        else if (nl_streq(type, "objekt")) {
            if (!((nl_text_starter_med(ren, "{") && nl_text_slutter_med(ren, "}")))) {
                return std_web__http_typed_input_feil_respons("schema", navn, "objekt", verdi);
            }
        }
        else if (nl_text_starter_med(type, "liste_")) {
            if (!((nl_text_starter_med(ren, "[") && nl_text_slutter_med(ren, "]")))) {
                return std_web__http_typed_input_feil_respons("schema", navn, type, verdi);
            }
        }
        char * verdier = std_web__schema_felt_verdier(schema, indeks);
        if (!(nl_streq(verdier, ""))) {
            nl_list_text* alternativer = nl_text_split_by(verdier, "|");
            int funnet = 0;
            int j = 0;
            while (j < nl_list_text_len(alternativer)) {
                if (nl_streq(nl_text_trim(alternativer->data[j]), ren)) {
                    funnet = 1;
                }
                j = (j + 1);
            }
            if (!(funnet)) {
                return std_web__http_typed_input_feil_respons("schema", navn, nl_concat("en av: ", verdier), verdi);
            }
        }
        return "";
        return "";
    }
    
    char * std_web__schema_beskrivelse(nl_list_text* schema) {
        char * resultat = "";
        int i = 0;
        while (i < nl_list_text_len(schema)) {
            nl_list_text* deler = nl_text_split_by(schema->data[i], "\t");
            char * navn = "";
            char * type = "";
            int påkrevd = 0;
            char * standard = "";
            char * eksempel = "";
            char * verdier = "";
            char * barn = "";
            if (nl_list_text_len(deler) >= 1) {
                navn = deler->data[0];
            }
            if (nl_list_text_len(deler) >= 2) {
                type = deler->data[1];
            }
            if (nl_list_text_len(deler) >= 3) {
                påkrevd = nl_streq(deler->data[2], "sann");
            }
            if (nl_list_text_len(deler) >= 4) {
                standard = deler->data[3];
            }
            if (nl_list_text_len(deler) >= 5) {
                eksempel = deler->data[4];
            }
            if (nl_list_text_len(deler) >= 6) {
                verdier = deler->data[5];
            }
            if (nl_list_text_len(deler) >= 7) {
                barn = deler->data[6];
            }
            char * linje = nl_concat(nl_concat(navn, ": "), type);
            if (påkrevd) {
                linje = nl_concat(linje, " (påkrevd)");
            }
            if (!(nl_streq(standard, ""))) {
                linje = nl_concat(nl_concat(linje, " standard="), standard);
            }
            if (!(nl_streq(eksempel, ""))) {
                linje = nl_concat(nl_concat(linje, " eksempel="), eksempel);
            }
            if (!(nl_streq(verdier, ""))) {
                linje = nl_concat(nl_concat(linje, " enum="), verdier);
            }
            if (!(nl_streq(barn, ""))) {
                linje = nl_concat(nl_concat(linje, " barn="), barn);
            }
            if (!(nl_streq(resultat, ""))) {
                resultat = nl_concat(resultat, "\n");
            }
            resultat = nl_concat(resultat, linje);
            i = (i + 1);
        }
        return resultat;
        return "";
    }
    
    char * std_web__schema_sammendrag(nl_list_text* schema) {
        return nl_concat(nl_concat("schema(", nl_int_to_text(nl_list_text_len(schema))), " felt)");
        return "";
    }
    
    char * std_web__bootstrap_html(char * tittel, char * overskrift, char * ingress, char * knappetekst) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("<!doctype html>\n<html lang=\"no\">\n<head>\n    <meta charset=\"utf-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n    <title>", tittel), "</title>\n    <link href=\"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css\" rel=\"stylesheet\">\n    <link rel=\"stylesheet\" href=\"styles.css\">\n</head>\n<body class=\"bg-light\">\n    <main class=\"container py-5\">\n        <section class=\"card shadow border-0 rounded-4 p-5 bg-white\">\n            <h1 class=\"display-5 fw-bold\">"), overskrift), "</h1>\n            <p class=\"lead\">"), ingress), "</p>\n            <button class=\"btn btn-primary\">"), knappetekst), "</button>\n        </section>\n    </main>\n</body>\n</html>\n");
        return "";
    }
    
    char * std_web__css_startmal() {
        return "body {\n    margin: 0;\n    font-family: system-ui, sans-serif;\n    background: #f8fafc;\n    color: #0f172a;\n}\n\nmain {\n    max-width: 960px;\n    margin: 0 auto;\n    padding: 48px 24px;\n}\n\n.card {\n    border: 0;\n    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.15);\n}\n";
        return "";
    }
    
    char * std_web__sass_startmal() {
        return "$bg: #0f172a;\n$panel: #111827;\n$accent: #60a5fa;\n\nbody {\n    margin: 0;\n    font-family: system-ui, sans-serif;\n    background: $bg;\n    color: #e2e8f0;\n}\n\nmain {\n    max-width: 960px;\n    margin: 0 auto;\n    padding: 48px 24px;\n}\n\n.card {\n    background: $panel;\n    border-radius: 24px;\n    padding: 32px;\n    box-shadow: 0 12px 30px rgba(15, 23, 42, 0.25);\n\n    button {\n        background: $accent;\n        border: 0;\n        border-radius: 999px;\n        color: $bg;\n        padding: 12px 18px;\n        font-weight: 700;\n    }\n}\n";
        return "";
    }
    
    char * std_web__sass_til_css_tekst(char * kilde) {
        return nl_sass_to_css(kilde);
        return "";
    }
    
    char * std_web__css_trim(char * tekstverdi) {
        return nl_text_trim(tekstverdi);
        return "";
    }
    
    int start() {
        return 0;
        return 0;
    }
    
    static int nl_call_callback(const char *name, int widget_id) {
        if (!name) { return widget_id; }
        return widget_id;
    }
    
    int main(void) {
        return start();
    }