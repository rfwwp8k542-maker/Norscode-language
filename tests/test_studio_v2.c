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
    
    char * studio_v2_studio_state__studio_v2_state_tittel();
    char * studio_v2_studio_state__studio_v2_state_session_fil(char * rot);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tom();
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_les(char * rot);
    char * studio_v2_studio_state__studio_v2_state_session_verdi(nl_list_text* session, char * nøkkel);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_prosjekter(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_apne_filer(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_aktiv_tab(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_split_fokus(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_tool_window(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_tema(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_keymap(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_runtimevalg(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_favoritter(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_run_config(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_search_query(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_symbol_cache(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_symbol_cache_oppdatert(nl_list_text* session, nl_list_text* cache);
    int studio_v2_studio_state__studio_v2_state_session_symbol_cache_skriv_med_tilstand(char * rot, nl_list_text* cache);
    char * studio_v2_studio_state__studio_v2_state_session_project_tree_anchor(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_project_tree_anchor_oppdatert(nl_list_text* session, char * anker);
    int studio_v2_studio_state__studio_v2_state_session_project_tree_anchor_skriv_med_tilstand(char * rot, char * anker);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profile_tom();
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_oppf_ring(char * navn, char * felt, char * verdi);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profiles(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_finn(nl_list_text* session, char * navn, char * felt);
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_args(nl_list_text* session, char * navn);
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_cwd(nl_list_text* session, char * navn, char * rot);
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_env(nl_list_text* session, char * navn);
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_sammendrag(nl_list_text* session, char * navn, char * rot);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profiles_oppdatert(nl_list_text* session, char * navn, char * args, char * cwd, char * env);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profile_session_oppdatert(nl_list_text* session, char * navn, char * args, char * cwd, char * env);
    int studio_v2_studio_state__studio_v2_state_session_run_profile_skriv_med_tilstand(char * rot, char * navn, char * args, char * cwd, char * env);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_innstillinger(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_innstillinger_oppdatert(nl_list_text* session, char * tema, char * keymap, char * runtimevalg);
    int studio_v2_studio_state__studio_v2_state_session_innstillinger_skriv_med_tilstand(char * rot, char * tema, char * keymap, char * runtimevalg);
    int studio_v2_studio_state__studio_v2_state_session_tema_skriv_med_tilstand(char * rot, char * tema);
    int studio_v2_studio_state__studio_v2_state_session_keymap_skriv_med_tilstand(char * rot, char * keymap);
    int studio_v2_studio_state__studio_v2_state_session_runtimevalg_skriv_med_tilstand(char * rot, char * runtimevalg);
    int studio_v2_studio_state__studio_v2_state_session_palette_open(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_palette_status(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_sist_navigasjon(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tree_fold(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints_for_fil(nl_list_text* session, char * fil);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_tom();
    char * studio_v2_studio_state__studio_v2_state_session_output_oppf_ring(char * nøkkel, char * verdi);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_output_verdi(nl_list_text* session, char * nøkkel);
    char * studio_v2_studio_state__studio_v2_state_session_output_config(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_output_command(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_output_code(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_stdout(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_stderr(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_output_status(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_output_sammendrag(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_test_history(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_test_history_siste(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_test_history_oppdatert(nl_list_text* session, char * historie);
    int studio_v2_studio_state__studio_v2_state_session_test_history_skriv_med_tilstand(char * rot, char * historie);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_oppdatert(nl_list_text* session, char * config, char * kommando, char * kode, nl_list_text* stdout, nl_list_text* stderr);
    int studio_v2_studio_state__studio_v2_state_session_output_skriv_med_tilstand(char * rot, char * config, char * kommando, char * kode, nl_list_text* stdout, nl_list_text* stderr);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug_tom();
    char * studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring(char * nøkkel, char * verdi);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_debug_config(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug_oppdatert(nl_list_text* session, char * debug_config, char * debug_mode, char * debug_action, int debug_linje);
    int studio_v2_studio_state__studio_v2_state_session_debug_skriv_med_tilstand(char * rot, char * debug_config, char * debug_mode, char * debug_action, int debug_linje);
    char * studio_v2_studio_state__studio_v2_state_session_debug_verdi(nl_list_text* session, char * nøkkel);
    char * studio_v2_studio_state__studio_v2_state_session_debug_status(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_debug_handling(nl_list_text* session);
    int studio_v2_studio_state__studio_v2_state_session_debug_linje(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_breakpoint_oppf_ring(char * fil, int linje);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints_oppdatert(nl_list_text* session, char * fil, int linje);
    int studio_v2_studio_state__studio_v2_state_session_tree_fold_satt(nl_list_text* session, char * fold_navn);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tree_fold_oppdatert(nl_list_text* session, char * fold_navn);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_prosjekter_oppdatert(char * rot, nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_apne_filer_oppdatert(char * aktiv_fil, nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(nl_list_text* linjer);
    char * studio_v2_studio_state__studio_v2_state_session_tekst(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * tema, char * keymap, char * runtimevalg, char * palette_open, char * sist_navigasjon, char * search_query, char * project_tree_anchor, nl_list_text* favoritter, nl_list_text* tree_fold, nl_list_text* breakpoints, nl_list_text* output, nl_list_text* run_profiles, nl_list_text* recent_prosjekter, nl_list_text* apne_filer);
    int studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * palette_open, char * sist_navigasjon, nl_list_text* tree_fold);
    int studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand_og_breakpoints(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * palette_open, char * sist_navigasjon, nl_list_text* tree_fold, nl_list_text* breakpoints);
    int studio_v2_studio_state__studio_v2_state_session_lagre(char * rot, char * aktiv_fil);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_search_query_oppdatert(nl_list_text* session, char * query);
    int studio_v2_studio_state__studio_v2_state_session_search_query_skriv_med_tilstand(char * rot, char * query);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_favoritter_oppdatert(nl_list_text* session, char * favoritt);
    int studio_v2_studio_state__studio_v2_state_session_favoritter_skriv_med_tilstand(char * rot, char * favoritt);
    int studio_v2_studio_state__studio_v2_state_session_breakpoint_toggle(char * rot, char * fil, int linje);
    char * studio_v2_studio_state__studio_v2_state_session_workspace(nl_list_text* session);
    char * studio_v2_studio_state__studio_v2_state_session_aktiv_fil(nl_list_text* session);
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_for_workspace(char * rot);
    char * studio_v2_studio_state__studio_v2_state_session_status_for_workspace(char * rot);
    char * studio_v2_studio_state__studio_v2_state_session_status(char * rot);
    char * studio_v2_studio_state__studio_v2_state_rot(nl_list_text* args);
    char * studio_v2_studio_state__studio_v2_state_filsti(char * rot, char * sti_relativ);
    char * studio_v2_studio_state__studio_v2_state_fil_innhold(char * rot, char * sti_relativ);
    char * studio_v2_studio_state__studio_v2_state_aktiv_fil(char * rot);
    nl_list_text* studio_v2_studio_state__studio_v2_state_apne_filer(char * rot, char * aktiv_fil);
    nl_list_text* studio_v2_studio_state__studio_v2_state_workspace_filer(char * rot);
    char * studio_v2_studio_state__studio_v2_state_workspace_filer_status(nl_list_text* filer);
    nl_list_text* studio_v2_studio_state__studio_v2_state_test_filer(char * rot);
    char * studio_v2_studio_state__studio_v2_state_status();
    char * studio_v2_project__studio_v2_prosjektnavn();
    char * studio_v2_project__studio_v2_prosjektrot(nl_list_text* args);
    char * studio_v2_project__studio_v2_prosjektstatus();
    char * studio_v2_project__studio_v2_prosjekt_vcs_status_fil(char * rot);
    char * studio_v2_project__studio_v2_prosjekt_vcs_diff_fil(char * rot);
    char * studio_v2_project__studio_v2_prosjekt_vcs_branch_fil(char * rot);
    char * studio_v2_project__studio_v2_prosjekt_vcs_commit_fil(char * rot);
    int studio_v2_project__studio_v2_prosjekt_vcs_kjor(char * rot, char * kommando, char * utfil);
    char * studio_v2_project__studio_v2_prosjekt_vcs_branch(char * rot);
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_commit(char * rot);
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_history(char * rot);
    int studio_v2_project__studio_v2_prosjekt_vcs_stage(char * rot, char * fil);
    int studio_v2_project__studio_v2_prosjekt_vcs_unstage(char * rot, char * fil);
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_status(char * rot);
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_diff_stat(char * rot);
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_changed_filer(char * rot);
    int studio_v2_project__studio_v2_prosjekt_vcs_antall(char * rot);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_tom();
    int studio_v2_symbol__studio_v2_symbol_er_kilde_fil(char * sti);
    int studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(char * tekstverdi, char * tegn);
    int studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(char * tekstverdi, char * søk);
    int studio_v2_symbol__studio_v2_symbol_finn_siste_tegn_posisjon(char * tekstverdi, char * tegn);
    char * studio_v2_symbol__studio_v2_symbol_liste_til_tekst(nl_list_text* verdier);
    char * studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(char * linje);
    char * studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_hover_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_signature_help_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_hover_fra_workspace(char * rot, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_signature_help_fra_workspace(char * rot, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_indeks(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_workspace(char * rot, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_completion_oppf_ring(char * slag, char * navn, char * detalj);
    int studio_v2_symbol__studio_v2_symbol_completion_match(char * kandidat, char * prefix);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_unique_add(nl_list_text* resultat, char * kandidat);
    int studio_v2_symbol__studio_v2_symbol_completion_match_starter_med(char * kandidat, char * prefix);
    int studio_v2_symbol__studio_v2_symbol_completion_match_utenfor_start(char * kandidat, char * prefix);
    int studio_v2_symbol__studio_v2_symbol_completion_match_n_yaktig(char * kandidat, char * prefix);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(nl_list_text* resultat, nl_list_text* kandidater, char * slag, char * detalj, char * prefix, char * fase, int maks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_keywords();
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_builtins();
    char * studio_v2_symbol__studio_v2_symbol_completion_keyword_detalj(char * navn);
    char * studio_v2_symbol__studio_v2_symbol_completion_builtin_detalj(char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette_fra_slag(nl_list_text* indeks, char * slag, nl_list_text* resultat, int maks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette_prioritert(nl_list_text* indeks, int maks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_fra_indeks(nl_list_text* indeks, char * prefix, int maks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_fra_workspace(char * rot, char * prefix, int maks);
    char * studio_v2_symbol__studio_v2_symbol_completion_type(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_completion_navn(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_completion_detalj(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(char * linje);
    char * studio_v2_symbol__studio_v2_symbol_finn_funksjonsparametere(char * linje);
    char * studio_v2_symbol__studio_v2_symbol_finn_importnavn(char * linje);
    char * studio_v2_symbol__studio_v2_symbol_finn_importalias(char * linje);
    char * studio_v2_symbol__studio_v2_symbol_finn_lokalnavn(char * linje);
    int studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(char * linje, char * prefix, char * segment);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_kilde(char * sti, char * kilde);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_kilde(char * sti, char * kilde, char * navn);
    int studio_v2_symbol__studio_v2_symbol_linjetreff_ord(char * tekstverdi, char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_filer_i_katalog(char * rot, char * katalog);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_workspace_filer(char * rot);
    char * studio_v2_symbol__studio_v2_symbol_fil_innhold(char * rot, char * sti_relativ);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_fil(char * rot, char * sti_relativ, char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(char * rot);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(nl_list_text* filer);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_uten_fil(nl_list_text* indeks, char * fil);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_oppdater_fil(nl_list_text* indeks, char * fil, char * innhold);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_tom();
    char * studio_v2_symbol__studio_v2_symbol_cache_rot(nl_list_text* cache);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_filer(nl_list_text* cache);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_indeks(nl_list_text* cache);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_bygg(char * rot, nl_list_text* filer, nl_list_text* indeks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_fra_workspace(char * rot);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil(nl_list_text* cache, char * fil, char * innhold);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil_skriv_med_tilstand(char * rot, char * fil, char * innhold);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_workspace(char * rot, char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_filer(nl_list_text* filer, char * navn);
    int studio_v2_symbol__studio_v2_symbol_indeks_antall(nl_list_text* indeks);
    char * studio_v2_symbol__studio_v2_symbol_indeks_forste(nl_list_text* indeks);
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_navn(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_med_slag(nl_list_text* indeks, char * slag, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_bruk(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_signatur_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_goto_def(char * rot, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_goto_def_fra_indeks(nl_list_text* indeks, char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_find_references(char * rot, char * navn);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_goto_reference(char * rot, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_goto_reference_fra_indeks(nl_list_text* indeks, char * navn);
    char * studio_v2_symbol__studio_v2_symbol_navigasjon_forslag(char * rot, char * needle);
    char * studio_v2_symbol__studio_v2_symbol_navigasjon_forslag_fra_indeks(nl_list_text* indeks, char * rot, char * needle);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_oppf_ring_deler(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(char * oppføring);
    int studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(char * oppføring);
    int studio_v2_symbol__studio_v2_symbol_oppf_ring_kolonne(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_oppf_ring_sted(char * oppføring);
    char * studio_v2_symbol__studio_v2_symbol_quick_jump(char * rot, char * needle);
    char * studio_v2_symbol__studio_v2_symbol_quick_jump_fra_filer(nl_list_text* filer, char * needle);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette(nl_list_text* indeks, int maks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview(char * rot, char * gammelt, char * nytt);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_ber_rte_filer_fra_indeks(nl_list_text* indeks, char * gammelt);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_indeks(nl_list_text* indeks, char * gammelt, char * nytt);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_ber_rte_oppf_ringer_fra_indeks(nl_list_text* indeks, char * fil, char * gammelt);
    char * studio_v2_symbol__studio_v2_symbol_tekst_fra_linjer(nl_list_text* linjer);
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_oppf_ring(char * innhold, char * oppføring, char * gammelt, char * nytt);
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_innhold_fra_oppf_ringer(char * innhold, nl_list_text* oppføringer, char * gammelt, char * nytt);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_fil(char * rot, char * sti_relativ, char * gammelt, char * nytt);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_filer(nl_list_text* filer, char * gammelt, char * nytt);
    int studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(char * tekstverdi, int posisjon);
    char * studio_v2_symbol__studio_v2_symbol_erstatt_ord(char * innhold, char * gammelt, char * nytt);
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_tekst(char * innhold, char * gammelt, char * nytt);
    char * studio_v2_symbol__studio_v2_symbol_rename_konflikt_fra_indeks(nl_list_text* indeks, char * gammelt, char * nytt);
    char * studio_v2_symbol__studio_v2_symbol_rename_status(char * rot, char * gammelt, char * nytt);
    int studio_v2_symbol__studio_v2_symbol_rename_klar(char * rot, char * gammelt, char * nytt);
    int studio_v2_symbol__studio_v2_symbol_rename_appliser_fil(char * rot, char * sti_relativ, char * gammelt, char * nytt);
    int studio_v2_symbol__studio_v2_symbol_rename_appliser_filer(char * rot, nl_list_text* filer, char * gammelt, char * nytt);
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(nl_list_text* indeks);
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_importer(nl_list_text* indeks);
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_lokale(nl_list_text* indeks);
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(nl_list_text* indeks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_unique_filer(nl_list_text* indeks);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_oppf_ringer_for_fil(nl_list_text* indeks, char * fil);
    int studio_v2_symbol__studio_v2_symbol_indeks_definisjoner_for_fil(nl_list_text* indeks, char * fil);
    int studio_v2_symbol__studio_v2_symbol_indeks_bruk_for_fil(nl_list_text* indeks, char * fil);
    nl_list_text* studio_v2_symbol__studio_v2_symbol_workspace_sammendrag(char * rot);
    char * studio_v2_editor__studio_v2_editor_tom();
    char * studio_v2_editor__studio_v2_editor_layout();
    nl_list_text* studio_v2_editor__studio_v2_editor_tabs_tom();
    nl_list_text* studio_v2_editor__studio_v2_editor_tabs_fra_apne_filer(nl_list_text* apne_filer);
    char * studio_v2_editor__studio_v2_editor_tab_status(nl_list_text* tabs);
    char * studio_v2_editor__studio_v2_editor_split_status(nl_list_text* tabs);
    nl_list_text* studio_v2_editor__studio_v2_editor_split_visning(nl_list_text* tabs);
    int studio_v2_editor__studio_v2_editor_tab_indeks(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_tab_n_v_rende(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_tab_neste(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_tab_forrige(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_tab_velg(nl_list_text* tabs, int valg_indeks);
    char * studio_v2_editor__studio_v2_editor_tab_bytt(nl_list_text* tabs, char * aktiv_fil, char * retning);
    char * studio_v2_editor__studio_v2_editor_split_fokus_valgt(nl_list_text* tabs, char * aktiv_fil, char * fokus);
    char * studio_v2_editor__studio_v2_editor_split_fokus_status(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_split_fokus_neste(nl_list_text* tabs, char * aktiv_fil);
    char * studio_v2_editor__studio_v2_editor_split_fokus_forrige(nl_list_text* tabs, char * aktiv_fil);
    nl_list_text* studio_v2_editor__studio_v2_editor_kjerne();
    nl_list_text* studio_v2_editor__studio_v2_editor_buffer_tom();
    nl_list_text* studio_v2_editor__studio_v2_editor_buffer_fra_tekst(char * tekstverdi);
    char * studio_v2_editor__studio_v2_editor_buffer_til_tekst(nl_list_text* buffer);
    char * studio_v2_editor__studio_v2_editor_format_innrykk(int nivå);
    nl_list_text* studio_v2_editor__studio_v2_editor_formater_buffer(nl_list_text* buffer);
    char * studio_v2_editor__studio_v2_editor_formater_tekst(char * tekstverdi);
    int studio_v2_editor__studio_v2_editor_buffer_antall_linje(nl_list_text* buffer);
    nl_list_text* studio_v2_editor__studio_v2_editor__pne(char * tekstverdi);
    char * studio_v2_editor__studio_v2_editor_lagre(nl_list_text* buffer);
    nl_list_text* studio_v2_editor__studio_v2_editor_oppdater(nl_list_text* buffer, char * tekstverdi);
    nl_list_text* studio_v2_editor__studio_v2_editor_last_om(nl_list_text* buffer, char * tekstverdi);
    nl_list_text* studio_v2_editor__studio_v2_cursor_tom();
    nl_list_text* studio_v2_editor__studio_v2_cursor_med_posisjon(int linje, int kolonne);
    nl_list_text* studio_v2_editor__studio_v2_cursor_flytt(nl_list_text* cursor, int linje, int kolonne);
    char * studio_v2_editor__studio_v2_cursor_linje(nl_list_text* cursor);
    char * studio_v2_editor__studio_v2_cursor_kolonne(nl_list_text* cursor);
    char * studio_v2_editor__studio_v2_cursor_utvalg_start_linje(nl_list_text* cursor);
    char * studio_v2_editor__studio_v2_cursor_utvalg_start_kolonne(nl_list_text* cursor);
    nl_list_text* studio_v2_editor__studio_v2_editor_linjeoversikt(nl_list_text* buffer);
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_tom();
    int studio_v2_editor__studio_v2_editor_breakpoint_finn(nl_list_text* breakpoints, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_toggle(nl_list_text* breakpoints, int linje_nummer);
    char * studio_v2_editor__studio_v2_editor_breakpoint_linje(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_oversikt(nl_list_text* buffer, nl_list_text* breakpoints);
    int studio_v2_editor__studio_v2_editor_debug_funksjonslinje(nl_list_text* buffer, int linje_nummer);
    char * studio_v2_editor__studio_v2_editor_debug_funksjonsnavn(nl_list_text* buffer, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_debug_kallstack(nl_list_text* buffer, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_debug_lokale(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_neste_linje(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_neste_ikke_tomme_linje(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_forrige_funksjonslinje(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_f_rste_breakpoint_etter(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_step_over(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_step_into(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_step_out(nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_debug_resume(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer);
    char * studio_v2_editor__studio_v2_editor_aktiv_linje(nl_list_text* buffer, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_goto_linje(nl_list_text* buffer, int linje_nummer);
    nl_list_text* studio_v2_editor__studio_v2_editor_goto_linje_fra_tekst(nl_list_text* buffer, char * linje_tekst);
    nl_list_text* studio_v2_editor__studio_v2_editor_visningslinjer(nl_list_text* buffer, int start_linje, int antall);
    char * studio_v2_editor__studio_v2_editor_goto_symbol(char * rot, char * navn);
    nl_list_text* studio_v2_editor__studio_v2_editor_referanser(char * rot, char * navn);
    char * studio_v2_editor__studio_v2_editor_referanse_valg(char * rot, char * navn, int valg_indeks);
    nl_list_text* studio_v2_editor__studio_v2_editor_rename_preview(char * rot, char * gammelt, char * nytt);
    nl_list_text* studio_v2_editor__studio_v2_editor_completion(char * rot, char * prefix);
    char * studio_v2_editor__studio_v2_editor_completion_valg(char * rot, char * prefix, int valg_indeks);
    char * studio_v2_editor__studio_v2_editor_completion_prefix_fra_linje(char * linje, int kolonne);
    nl_list_text* studio_v2_editor__studio_v2_editor_completion_fra_linjetekst(char * rot, char * linjetekst, int kolonne);
    char * studio_v2_editor__studio_v2_editor_completion_valg_fra_linjetekst(char * rot, char * linjetekst, int kolonne, int valg_indeks);
    nl_list_text* studio_v2_editor__studio_v2_editor_completion_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne);
    char * studio_v2_editor__studio_v2_editor_completion_valg_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne, int valg_indeks);
    char * studio_v2_editor__studio_v2_editor_hover(char * rot, char * navn);
    char * studio_v2_editor__studio_v2_editor_signature_help(char * rot, char * navn);
    int studio_v2_editor__studio_v2_editor_aktiv_parameter_fra_linje(char * linje, int kolonne);
    char * studio_v2_editor__studio_v2_editor_signature_navn_fra_linje(char * linje, int kolonne);
    char * studio_v2_editor__studio_v2_editor_hurtiginfo(char * rot, char * navn);
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_linjetekst(char * rot, char * linjetekst, int kolonne);
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne);
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_er_symbol_delimiter(char * tegn);
    char * studio_v2_editor__studio_v2_editor_symbol_fra_linje(char * linje, int kolonne);
    char * studio_v2_editor__studio_v2_editor_symbol_fra_linje_med_funksjon(char * linje, int kolonne);
    int studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(char * navn);
    char * studio_v2_editor__studio_v2_editor_symbol_foran_foerste_paren(char * linje);
    char * studio_v2_editor__studio_v2_editor_symbol_etter_likhet(char * linje);
    char * studio_v2_editor__studio_v2_editor_symbol_fra_aktiv_linje(char * linje);
    char * studio_v2_editor__studio_v2_editor_signature_navn_fra_completion(char * rot, char * linjetekst, int kolonne);
    char * studio_v2_editor__studio_v2_editor_signature_help_med_hover(char * rot, char * navn);
    char * studio_v2_editor__studio_v2_editor_hover_fra_linjetekst(char * rot, char * linjetekst, int kolonne);
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_linjetekst(char * rot, char * linjetekst, int kolonne);
    char * studio_v2_editor__studio_v2_editor_hover_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne);
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne);
    char * studio_v2_editor__studio_v2_editor_hover_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer);
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer);
    int studio_v2_editor__studio_v2_editor_sok(nl_list_text* buffer, char * needle);
    char * studio_v2_editor__studio_v2_editor_sok_status(nl_list_text* buffer, char * needle);
    int studio_v2_editor__studio_v2_editor_telle_forekomster(char * tekstverdi, char * needle);
    char * studio_v2_editor__studio_v2_editor_erstatt_tekst(char * tekstverdi, char * gammelt, char * nytt);
    nl_list_text* studio_v2_editor__studio_v2_editor_erstatt_buffer(nl_list_text* buffer, char * gammelt, char * nytt);
    char * studio_v2_editor__studio_v2_editor_erstatt_tekst_fra_buffer(nl_list_text* buffer, char * gammelt, char * nytt);
    char * studio_v2_editor__studio_v2_editor_erstatt_status(nl_list_text* buffer, char * gammelt);
    int studio_v2_editor__studio_v2_editor_erstatt_treff(nl_list_text* buffer, char * gammelt);
    int studio_v2_editor__studio_v2_editor_forste_treff(nl_list_text* buffer, char * needle);
    char * studio_v2_ui__studio_v2_ui_shell();
    char * studio_v2_ui__studio_v2_ui_logo_banner();
    char * studio_v2_ui__studio_v2_ui_logo_tagline();
    char * studio_v2_ui__studio_v2_ui_velkomst_oversikt();
    char * studio_v2_ui__studio_v2_ui_velkomst_undertittel(char * rot, char * session_status);
    nl_list_text* studio_v2_ui__studio_v2_ui_velkomst_handlinger();
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_tittel();
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_status(int antall);
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_current(char * rot);
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_sammendrag(char * rot, int antall);
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_hint();
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_actions();
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_restore_status();
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_shortcut();
    char * studio_v2_ui__studio_v2_ui_run_hint();
    char * studio_v2_ui__studio_v2_ui_run_status_hint();
    char * studio_v2_ui__studio_v2_ui_run_output_hint();
    char * studio_v2_ui__studio_v2_ui_run_history_hint();
    char * studio_v2_ui__studio_v2_ui_run_suite_hint();
    char * studio_v2_ui__studio_v2_ui_output_tittel();
    char * studio_v2_ui__studio_v2_ui_output_stdout_tittel();
    char * studio_v2_ui__studio_v2_ui_output_stderr_tittel();
    char * studio_v2_ui__studio_v2_ui_output_hint();
    char * studio_v2_ui__studio_v2_ui_vcs_tittel();
    char * studio_v2_ui__studio_v2_ui_vcs_status_tittel();
    char * studio_v2_ui__studio_v2_ui_vcs_diff_tittel();
    char * studio_v2_ui__studio_v2_ui_vcs_branch_tittel();
    char * studio_v2_ui__studio_v2_ui_vcs_commit_tittel();
    char * studio_v2_ui__studio_v2_ui_vcs_hint();
    char * studio_v2_ui__studio_v2_ui_tool_window_hint();
    char * studio_v2_ui__studio_v2_ui_structure_hint();
    char * studio_v2_ui__studio_v2_ui_search_hint();
    char * studio_v2_ui__studio_v2_ui_palette_hint();
    char * studio_v2_ui__studio_v2_ui_palette_lukket_hint();
    char * studio_v2_ui__studio_v2_ui_project_hint();
    char * studio_v2_ui__studio_v2_ui_editor_hint();
    char * studio_v2_ui__studio_v2_ui_references_hint();
    char * studio_v2_ui__studio_v2_ui_rename_hint();
    char * studio_v2_ui__studio_v2_ui_rename_apply_hint();
    char * studio_v2_ui__studio_v2_ui_terminal_hint();
    char * studio_v2_ui__studio_v2_ui_problems_hint();
    char * studio_v2_ui__studio_v2_ui_velkomst_spacer();
    nl_list_text* studio_v2_ui__studio_v2_ui_layout();
    char * studio_v2_ui__studio_v2_ui_status();
    char * studio_v2_ui__studio_v2_ui_tema_lys();
    char * studio_v2_ui__studio_v2_ui_tema_mork();
    char * studio_v2_ui__studio_v2_ui_tema_standard();
    char * studio_v2_ui__studio_v2_ui_tema_status(char * tema);
    nl_list_text* studio_v2_ui__studio_v2_ui_tema_palett();
    char * studio_v2_ui__studio_v2_ui_keymap_standard();
    char * studio_v2_ui__studio_v2_ui_keymap_vim();
    nl_list_text* studio_v2_ui__studio_v2_ui_keymap_palett();
    char * studio_v2_ui__studio_v2_ui_runtimevalg_run();
    char * studio_v2_ui__studio_v2_ui_runtimevalg_check();
    char * studio_v2_ui__studio_v2_ui_runtimevalg_test();
    nl_list_text* studio_v2_ui__studio_v2_ui_runtimevalg_palett();
    char * studio_v2_ui__studio_v2_ui_tema_fra_navn(char * navn);
    nl_list_text* studio_v2_ui__studio_v2_ui_snarveier();
    char * studio_v2_ui__studio_v2_ui_snarvei_forste();
    char * studio_v2_ui__studio_v2_ui_snarveier_status();
    char * studio_v2_ui__studio_v2_ui_seksjon_tittel(char * navn);
    char * studio_v2_ui__studio_v2_ui_panel_overskrift(char * navn, char * undertittel);
    char * studio_v2_ui__studio_v2_ui_panel_ikon_overskrift(char * ikon, char * navn, char * undertittel);
    char * studio_v2_ui__studio_v2_ui_panel_status_overskrift(char * ikon, char * navn, char * undertittel, char * status_navn, char * status_verdi);
    char * studio_v2_ui__studio_v2_ui_deloverskrift(char * navn);
    char * studio_v2_ui__studio_v2_ui_status_chip(char * navn, char * verdi);
    char * studio_v2_ui__studio_v2_ui_aktiv_chip(char * navn, char * verdi);
    nl_list_text* studio_v2_ui__studio_v2_ui_session_tom();
    nl_list_text* studio_v2_ui__studio_v2_ui_session_fra_workspace(char * rot, char * aktiv_fil);
    char * studio_v2_ui__studio_v2_ui_session_restore(nl_list_text* session);
    char * studio_v2_ui__studio_v2_ui_session_status(nl_list_text* session);
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_tom();
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_prosjekt(char * prosjektnavn, char * rot);
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_fil(char * sti, char * innhold);
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_diagnostikk(nl_list_text* diagnostikk);
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_valg(char * sti, char * innhold, int startlinje, int sluttlinje);
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_sammendrag(char * prosjektnavn, char * rot, char * sti, char * innhold, nl_list_text* diagnostikk);
    int studio_v2_ai_context__studio_v2_ai_kontekst_antall(nl_list_text* kontekst);
    char * studio_v2_ai_context__studio_v2_ai_kontekst_forste(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_modus_disabled();
    char * studio_v2_ai__studio_v2_ai_modus_lokal();
    char * studio_v2_ai__studio_v2_ai_modus_remote();
    char * studio_v2_ai__studio_v2_ai_modus();
    nl_list_text* studio_v2_ai__studio_v2_ai_provider_tom();
    nl_list_text* studio_v2_ai__studio_v2_ai_provider_fra_modus(char * navn, char * modus);
    char * studio_v2_ai__studio_v2_ai_provider_navn(nl_list_text* provider);
    char * studio_v2_ai__studio_v2_ai_provider_modus(nl_list_text* provider);
    int studio_v2_ai__studio_v2_ai_provider_kan_bruke(nl_list_text* provider);
    char * studio_v2_ai__studio_v2_ai_provider_status(nl_list_text* provider);
    nl_list_text* studio_v2_ai__studio_v2_ai_kontrakt();
    int studio_v2_ai__studio_v2_ai_kan_bruke();
    nl_list_text* studio_v2_ai__studio_v2_ai_handlinger();
    char * studio_v2_ai__studio_v2_ai_handlinger_forste();
    char * studio_v2_ai__studio_v2_ai_handlinger_status();
    char * studio_v2_ai__studio_v2_ai_tekst_konteksttekst(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_tekst_forklar_kode(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_tekst_sammendrag_fil(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_tekst_refaktorering(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_tekst_testgenerering(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_tekst_patch_previsjon(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_handling_forklar_kode(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_handling_sammendrag_fil(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_handling_refaktorering(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_handling_testgenerering(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_handling_patch_previsjon(nl_list_text* kontekst);
    nl_list_text* studio_v2_ai__studio_v2_ai_patch_previsjon_tom();
    nl_list_text* studio_v2_ai__studio_v2_ai_patch_previsjon_fra_kontekst(nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_patch_previsjon_status(nl_list_text* preview);
    char * studio_v2_ai__studio_v2_ai_patch_previsjon_forste(nl_list_text* preview);
    char * studio_v2_ai__studio_v2_ai_patch_godkjenn(nl_list_text* preview);
    char * studio_v2_ai__studio_v2_ai_patch_avvis(nl_list_text* preview);
    nl_list_text* studio_v2_ai__studio_v2_ai_opt_in_tom();
    nl_list_text* studio_v2_ai__studio_v2_ai_opt_in_lag(char * workspace_navn, int tillat_sending, int offline_only, int rediger_kontekst);
    char * studio_v2_ai__studio_v2_ai_opt_in_workspace(nl_list_text* opt_in);
    int studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(nl_list_text* opt_in);
    int studio_v2_ai__studio_v2_ai_opt_in_offline_only(nl_list_text* opt_in);
    int studio_v2_ai__studio_v2_ai_opt_in_rediger_kontekst(nl_list_text* opt_in);
    char * studio_v2_ai__studio_v2_ai_opt_in_status(nl_list_text* opt_in);
    nl_list_text* studio_v2_ai__studio_v2_ai_personvern_policy();
    char * studio_v2_ai__studio_v2_ai_personvern_status();
    int studio_v2_ai__studio_v2_ai_personvern_kan_sende(nl_list_text* opt_in);
    char * studio_v2_ai__studio_v2_ai_kontekst_rediger_tekst(char * tekstverdi);
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_rediger(nl_list_text* kontekst);
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_trim(nl_list_text* kontekst, int maks);
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_sikker(nl_list_text* opt_in, nl_list_text* kontekst);
    char * studio_v2_ai__studio_v2_ai_kontekst_sikker_status(nl_list_text* opt_in);
    nl_list_text* studio_v2_actions__studio_v2_actions_tom();
    nl_list_text* studio_v2_actions__studio_v2_actions_palett();
    nl_list_text* studio_v2_actions__studio_v2_actions_run_konfigurasjoner();
    nl_list_text* studio_v2_actions__studio_v2_actions_terminal(char * rot, char * fil, char * aktiv_config);
    char * studio_v2_actions__studio_v2_actions_terminal_status(char * rot);
    char * studio_v2_actions__studio_v2_actions_status(char * rot);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_tom();
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_run(char * rot, char * fil);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_check(char * rot, char * fil);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_test(char * rot, char * fil);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_debug(char * rot, char * fil);
    char * studio_v2_actions__studio_v2_actions_kommando_debug_tekst(char * rot, char * fil, char * aktiv_config);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_runtime_ci(char * rot);
    char * studio_v2_actions__studio_v2_actions_kommando_args_for_navn(char * rot, char * navn);
    char * studio_v2_actions__studio_v2_actions_kommando_arbeidskatalog(char * rot);
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_for_navn(char * rot, char * fil, char * navn);
    char * studio_v2_actions__studio_v2_actions_kommando_tekst(nl_list_text* kommando);
    char * studio_v2_actions__studio_v2_actions_kommando_status(int kode);
    int studio_v2_actions__studio_v2_actions_kjor(nl_list_text* kommando);
    char * studio_v2_actions__studio_v2_actions_trygg_kjor(char * rot, char * fil, char * navn);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_tom();
    char * studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring(char * slag, char * fil, int linje, char * melding);
    char * studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne(char * slag, char * fil, int linje, int kolonne, char * melding);
    char * studio_v2_diagnostics__studio_v2_diagnostics_finn_oppf_ring(nl_list_text* resultater, char * nøkkel);
    char * studio_v2_diagnostics__studio_v2_diagnostics_alvorlighet_fra_slag(char * slag);
    int studio_v2_diagnostics__studio_v2_diagnostics_er_fatal(char * slag);
    int studio_v2_diagnostics__studio_v2_diagnostics_antall_fatal(nl_list_text* diagnoser);
    int studio_v2_diagnostics__studio_v2_diagnostics_antall_gjenvinnbare(nl_list_text* diagnoser);
    int studio_v2_diagnostics__studio_v2_diagnostics_tell_tegn(char * tekstverdi, char * tegn);
    char * studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(char * linje, int start_posisjon);
    char * studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(char * linje, int blokk_start);
    char * studio_v2_diagnostics__studio_v2_diagnostics_setningstype(char * linje);
    int studio_v2_diagnostics__studio_v2_diagnostics_setningskolonne(char * linje);
    int studio_v2_diagnostics__studio_v2_diagnostics_linje_har_uavsluttet_streng(char * linje);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_innhold(char * sti, char * innhold);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_fil(char * rot, char * sti_relativ);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_workspace(char * rot);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace(char * rot);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace_med_filer(char * rot, nl_list_text* filer, int symbol_antall);
    char * studio_v2_diagnostics__studio_v2_diagnostics_status(char * rot);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_oppdater(char * rot);
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_oppdater_med_filer(char * rot, nl_list_text* filer, int symbol_antall);
    char * studio_v2_diagnostics__studio_v2_diagnostics_oppdater_status(char * rot);
    int start();
    
    char * studio_v2_studio_state__studio_v2_state_tittel() {
        return "Norscode Studio v2";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_fil(char * rot) {
        return nl_concat(rot, "/.norscode/studio_v2.session");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_les(char * rot) {
        char * sti = studio_v2_studio_state__studio_v2_state_session_fil(rot);
        if (!(nl_file_exists(sti))) {
            return studio_v2_studio_state__studio_v2_state_session_tom();
        }
        return nl_split_lines(nl_read_file(sti));
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_verdi(nl_list_text* session, char * nøkkel) {
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], nøkkel)) {
                return deler->data[1];
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_prosjekter(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "recent_project")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_apne_filer(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "open_file")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_aktiv_tab(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "aktiv_tab");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_split_fokus(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "split_fokus");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "høyre";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_tool_window(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "tool_window");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "Project";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_tema(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "tema");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "mørk";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_keymap(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "keymap");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "standard";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_runtimevalg(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "runtimevalg");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "run";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_favoritter(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "favorite_file")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_config(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_verdi(session, "run_config");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "run";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_search_query(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "search_query");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_symbol_cache(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (nl_text_starter_med(ren, "symbol_cache\t")) {
                nl_list_text_push(resultat, nl_text_slice(ren, 13, nl_text_length(ren)));
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_symbol_cache_oppdatert(nl_list_text* session, nl_list_text* cache) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "symbol_cache\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        int cache_indeks = 0;
        while (cache_indeks < nl_list_text_len(cache)) {
            nl_list_text_push(resultat, nl_concat("symbol_cache\t", cache->data[cache_indeks]));
            cache_indeks = (cache_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_symbol_cache_skriv_med_tilstand(char * rot, nl_list_text* cache) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_symbol_cache_oppdatert(session, cache));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_project_tree_anchor(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "project_tree_anchor");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_project_tree_anchor_oppdatert(nl_list_text* session, char * anker) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "project_tree_anchor\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        if (!(nl_streq(anker, ""))) {
            nl_list_text_push(resultat, nl_concat("project_tree_anchor\t", anker));
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_project_tree_anchor_skriv_med_tilstand(char * rot, char * anker) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_project_tree_anchor_oppdatert(session, anker));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profile_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_oppf_ring(char * navn, char * felt, char * verdi) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("run_profile\t", navn), "\t"), felt), "\t"), verdi);
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profiles(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (nl_text_starter_med(ren, "run_profile\t")) {
                nl_list_text_push(resultat, ren);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_finn(nl_list_text* session, char * navn, char * felt) {
        nl_list_text* oppføringer = studio_v2_studio_state__studio_v2_state_session_run_profiles(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(oppføringer)) {
            char * oppføring = oppføringer->data[indeks];
            nl_list_text* deler = nl_text_split_by(oppføring, "\t");
            if ((((nl_list_text_len(deler) >= 4) && nl_streq(deler->data[0], "run_profile")) && nl_streq(deler->data[1], navn)) && nl_streq(deler->data[2], felt)) {
                return deler->data[3];
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_args(nl_list_text* session, char * navn) {
        return studio_v2_studio_state__studio_v2_state_session_run_profile_finn(session, navn, "args");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_cwd(nl_list_text* session, char * navn, char * rot) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_run_profile_finn(session, navn, "cwd");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        if (!(nl_streq(rot, ""))) {
            return rot;
        }
        return ".";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_env(nl_list_text* session, char * navn) {
        return studio_v2_studio_state__studio_v2_state_session_run_profile_finn(session, navn, "env");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_run_profile_sammendrag(nl_list_text* session, char * navn, char * rot) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("args=", studio_v2_studio_state__studio_v2_state_session_run_profile_args(session, navn)), " · cwd="), studio_v2_studio_state__studio_v2_state_session_run_profile_cwd(session, navn, rot)), " · env="), studio_v2_studio_state__studio_v2_state_session_run_profile_env(session, navn));
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profiles_oppdatert(nl_list_text* session, char * navn, char * args, char * cwd, char * env) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* oppføringer = studio_v2_studio_state__studio_v2_state_session_run_profiles(session);
        int i = 0;
        while (i < nl_list_text_len(oppføringer)) {
            char * oppføring = oppføringer->data[i];
            nl_list_text* deler = nl_text_split_by(oppføring, "\t");
            if ((nl_list_text_len(deler) >= 4) && nl_streq(deler->data[1], navn)) {
            }
            else {
                nl_list_text_push(resultat, oppføring);
            }
            i = (i + 1);
        }
        if (!(nl_streq(navn, ""))) {
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_run_profile_oppf_ring(navn, "args", args));
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_run_profile_oppf_ring(navn, "cwd", cwd));
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_run_profile_oppf_ring(navn, "env", env));
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_run_profile_session_oppdatert(nl_list_text* session, char * navn, char * args, char * cwd, char * env) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* run_profiles = studio_v2_studio_state__studio_v2_state_session_run_profiles_oppdatert(session, navn, args, cwd, env);
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "run_profile\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        int i = 0;
        while (i < nl_list_text_len(run_profiles)) {
            nl_list_text_push(resultat, run_profiles->data[i]);
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_run_profile_skriv_med_tilstand(char * rot, char * navn, char * args, char * cwd, char * env) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_run_profile_session_oppdatert(session, navn, args, cwd, env));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_innstillinger(nl_list_text* session) {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_innstillinger_oppdatert(nl_list_text* session, char * tema, char * keymap, char * runtimevalg) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (((!(nl_text_starter_med(ren, "tema\t"))) && (!(nl_text_starter_med(ren, "keymap\t")))) && (!(nl_text_starter_med(ren, "runtimevalg\t")))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        nl_list_text_push(resultat, nl_concat("tema\t", tema));
        nl_list_text_push(resultat, nl_concat("keymap\t", keymap));
        nl_list_text_push(resultat, nl_concat("runtimevalg\t", runtimevalg));
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_innstillinger_skriv_med_tilstand(char * rot, char * tema, char * keymap, char * runtimevalg) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_innstillinger_oppdatert(session, tema, keymap, runtimevalg));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_tema_skriv_med_tilstand(char * rot, char * tema) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        return studio_v2_studio_state__studio_v2_state_session_innstillinger_skriv_med_tilstand(rot, tema, studio_v2_studio_state__studio_v2_state_session_keymap(session), studio_v2_studio_state__studio_v2_state_session_runtimevalg(session));
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_keymap_skriv_med_tilstand(char * rot, char * keymap) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        return studio_v2_studio_state__studio_v2_state_session_innstillinger_skriv_med_tilstand(rot, studio_v2_studio_state__studio_v2_state_session_tema(session), keymap, studio_v2_studio_state__studio_v2_state_session_runtimevalg(session));
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_runtimevalg_skriv_med_tilstand(char * rot, char * runtimevalg) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        return studio_v2_studio_state__studio_v2_state_session_innstillinger_skriv_med_tilstand(rot, studio_v2_studio_state__studio_v2_state_session_tema(session), studio_v2_studio_state__studio_v2_state_session_keymap(session), runtimevalg);
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_palette_open(nl_list_text* session) {
        if (nl_streq(studio_v2_studio_state__studio_v2_state_session_verdi(session, "palette_open"), "åpen")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_palette_status(nl_list_text* session) {
        if (studio_v2_studio_state__studio_v2_state_session_palette_open(session)) {
            return "åpen";
        }
        return "lukket";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_sist_navigasjon(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "sist_navigasjon");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tree_fold(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "tree_fold")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 3) && nl_streq(deler->data[0], "breakpoint")) {
                nl_list_text_push(resultat, nl_concat(nl_concat(deler->data[1], "\t"), deler->data[2]));
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints_for_fil(nl_list_text* session, char * fil) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* breakpoints = studio_v2_studio_state__studio_v2_state_session_breakpoints(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(breakpoints)) {
            nl_list_text* deler = nl_text_split_by(breakpoints->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], fil)) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_oppf_ring(char * nøkkel, char * verdi) {
        return nl_concat(nl_concat(nl_concat("output_", nøkkel), "\t"), verdi);
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (nl_text_starter_med(ren, "output_")) {
                nl_list_text_push(resultat, ren);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_verdi(nl_list_text* session, char * nøkkel) {
        nl_list_text* oppføringer = studio_v2_studio_state__studio_v2_state_session_output(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(oppføringer)) {
            char * oppføring = oppføringer->data[indeks];
            nl_list_text* deler = nl_text_split_by(oppføring, "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], nøkkel)) {
                return deler->data[1];
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_config(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_output_verdi(session, "output_config");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_command(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_output_verdi(session, "output_command");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_code(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_output_verdi(session, "output_code");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_stdout(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* oppføringer = studio_v2_studio_state__studio_v2_state_session_output(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(oppføringer)) {
            char * oppføring = oppføringer->data[indeks];
            nl_list_text* deler = nl_text_split_by(oppføring, "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "output_stdout")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_stderr(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* oppføringer = studio_v2_studio_state__studio_v2_state_session_output(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(oppføringer)) {
            char * oppføring = oppføringer->data[indeks];
            nl_list_text* deler = nl_text_split_by(oppføring, "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], "output_stderr")) {
                nl_list_text_push(resultat, deler->data[1]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_status(nl_list_text* session) {
        if ((nl_streq(studio_v2_studio_state__studio_v2_state_session_output_command(session), "") && (nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_output_stdout(session)) == 0)) && (nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_output_stderr(session)) == 0)) {
            return "tom";
        }
        return "klar";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_output_sammendrag(nl_list_text* session) {
        char * config = studio_v2_studio_state__studio_v2_state_session_output_config(session);
        char * kommando = studio_v2_studio_state__studio_v2_state_session_output_command(session);
        char * kode = studio_v2_studio_state__studio_v2_state_session_output_code(session);
        if (nl_streq(config, "")) {
            config = "run";
        }
        if (nl_streq(kommando, "")) {
            kommando = "(ingen)";
        }
        if (nl_streq(kode, "")) {
            kode = "ukjent";
        }
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("Config: ", config), " · Command: "), kommando), " · Code: "), kode), " · Stdout: "), nl_int_to_text(nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_output_stdout(session)))), " · Stderr: "), nl_int_to_text(nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_output_stderr(session))));
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_test_history(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (nl_text_starter_med(ren, "test_history\t")) {
                nl_list_text* deler = nl_text_split_by(ren, "\t");
                if (nl_list_text_len(deler) >= 2) {
                    nl_list_text_push(resultat, deler->data[1]);
                }
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_test_history_siste(nl_list_text* session) {
        nl_list_text* historikk = studio_v2_studio_state__studio_v2_state_session_test_history(session);
        if (nl_list_text_len(historikk) > 0) {
            return historikk->data[(nl_list_text_len(historikk) - 1)];
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_test_history_oppdatert(nl_list_text* session, char * historie) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* historikk = studio_v2_studio_state__studio_v2_state_session_test_history(session);
        if (!(nl_streq(historie, ""))) {
            nl_list_text_push(historikk, historie);
        }
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "test_history\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        int start = 0;
        if (nl_list_text_len(historikk) > 5) {
            start = (nl_list_text_len(historikk) - 5);
        }
        int historikk_indeks = start;
        while (historikk_indeks < nl_list_text_len(historikk)) {
            nl_list_text_push(resultat, nl_concat("test_history\t", historikk->data[historikk_indeks]));
            historikk_indeks = (historikk_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_test_history_skriv_med_tilstand(char * rot, char * historie) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_test_history_oppdatert(session, historie));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_output_oppdatert(nl_list_text* session, char * config, char * kommando, char * kode, nl_list_text* stdout, nl_list_text* stderr) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "output_"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        if (!(nl_streq(config, ""))) {
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_output_oppf_ring("config", config));
        }
        if (!(nl_streq(kommando, ""))) {
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_output_oppf_ring("command", kommando));
        }
        if (!(nl_streq(kode, ""))) {
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_output_oppf_ring("code", kode));
        }
        int stdout_indeks = 0;
        while (stdout_indeks < nl_list_text_len(stdout)) {
            if (!(nl_streq(stdout->data[stdout_indeks], ""))) {
                nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_output_oppf_ring("stdout", stdout->data[stdout_indeks]));
            }
            stdout_indeks = (stdout_indeks + 1);
        }
        int stderr_indeks = 0;
        while (stderr_indeks < nl_list_text_len(stderr)) {
            if (!(nl_streq(stderr->data[stderr_indeks], ""))) {
                nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_output_oppf_ring("stderr", stderr->data[stderr_indeks]));
            }
            stderr_indeks = (stderr_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_output_skriv_med_tilstand(char * rot, char * config, char * kommando, char * kode, nl_list_text* stdout, nl_list_text* stderr) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_output_oppdatert(session, config, kommando, kode, stdout, stderr));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring(char * nøkkel, char * verdi) {
        return nl_concat(nl_concat(nøkkel, "\t"), verdi);
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug(nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if ((((!(nl_text_starter_med(ren, "debug_config\t"))) && (!(nl_text_starter_med(ren, "debug_mode\t")))) && (!(nl_text_starter_med(ren, "debug_action\t")))) && (!(nl_text_starter_med(ren, "debug_line\t")))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_debug_config(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_debug_verdi(session, "debug_config");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        char * fallback = studio_v2_studio_state__studio_v2_state_session_run_config(session);
        if (!(nl_streq(fallback, ""))) {
            return fallback;
        }
        return "run";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_debug_oppdatert(nl_list_text* session, char * debug_config, char * debug_mode, char * debug_action, int debug_linje) {
        nl_list_text* resultat = studio_v2_studio_state__studio_v2_state_session_debug(session);
        nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring("debug_config", debug_config));
        nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring("debug_mode", debug_mode));
        nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring("debug_action", debug_action));
        nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_debug_oppf_ring("debug_line", nl_int_to_text(debug_linje)));
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_debug_skriv_med_tilstand(char * rot, char * debug_config, char * debug_mode, char * debug_action, int debug_linje) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_debug_oppdatert(session, debug_config, debug_mode, debug_action, debug_linje));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_debug_verdi(nl_list_text* session, char * nøkkel) {
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            nl_list_text* deler = nl_text_split_by(session->data[indeks], "\t");
            if ((nl_list_text_len(deler) >= 2) && nl_streq(deler->data[0], nøkkel)) {
                return deler->data[1];
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_debug_status(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_debug_verdi(session, "debug_mode");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "paused";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_debug_handling(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_debug_verdi(session, "debug_action");
        if (!(nl_streq(verdi, ""))) {
            return verdi;
        }
        return "resume";
        return "";
    }
    
    int studio_v2_studio_state__studio_v2_state_session_debug_linje(nl_list_text* session) {
        char * verdi = studio_v2_studio_state__studio_v2_state_session_debug_verdi(session, "debug_line");
        if (!(nl_streq(verdi, ""))) {
            return nl_text_to_int(verdi);
        }
        return 1;
        return 0;
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_breakpoint_oppf_ring(char * fil, int linje) {
        return nl_concat(nl_concat(nl_concat("breakpoint\t", fil), "\t"), nl_int_to_text(linje));
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_breakpoints_oppdatert(nl_list_text* session, char * fil, int linje) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* breakpoints = studio_v2_studio_state__studio_v2_state_session_breakpoints(session);
        char * mål = nl_concat(nl_concat(fil, "\t"), nl_int_to_text(linje));
        int funnet = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(breakpoints)) {
            char * kandidat = breakpoints->data[indeks];
            if (nl_streq(kandidat, mål)) {
                funnet = 1;
            }
            else {
                nl_list_text_push(resultat, nl_concat("breakpoint\t", kandidat));
            }
            indeks = (indeks + 1);
        }
        if (((!(funnet)) && !(nl_streq(fil, ""))) && (linje > 0)) {
            nl_list_text_push(resultat, studio_v2_studio_state__studio_v2_state_session_breakpoint_oppf_ring(fil, linje));
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_tree_fold_satt(nl_list_text* session, char * fold_navn) {
        nl_list_text* foldet = studio_v2_studio_state__studio_v2_state_session_tree_fold(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(foldet)) {
            if (nl_streq(foldet->data[indeks], fold_navn)) {
                return 1;
            }
            indeks = (indeks + 1);
        }
        return 0;
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_tree_fold_oppdatert(nl_list_text* session, char * fold_navn) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* foldet = studio_v2_studio_state__studio_v2_state_session_tree_fold(session);
        int funnet = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(foldet)) {
            char * kandidat = foldet->data[indeks];
            if (nl_streq(kandidat, fold_navn)) {
                funnet = 1;
            }
            else {
                nl_list_text_push(resultat, kandidat);
            }
            indeks = (indeks + 1);
        }
        if ((!(funnet)) && !(nl_streq(fold_navn, ""))) {
            nl_list_text_push(resultat, fold_navn);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_prosjekter_oppdatert(char * rot, nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* eksisterende = studio_v2_studio_state__studio_v2_state_session_recent_prosjekter(session);
        nl_list_text_push(resultat, rot);
        int i = 0;
        while (i < nl_list_text_len(eksisterende)) {
            char * kandidat = eksisterende->data[i];
            int funnet = 0;
            int j = 0;
            while ((j < nl_list_text_len(resultat)) && (!(funnet))) {
                if (nl_streq(resultat->data[j], kandidat)) {
                    funnet = 1;
                }
                j = (j + 1);
            }
            if ((!(nl_streq(kandidat, "")) && (!(funnet))) && (nl_list_text_len(resultat) < 5)) {
                nl_list_text_push(resultat, kandidat);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_apne_filer_oppdatert(char * aktiv_fil, nl_list_text* session) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* eksisterende = studio_v2_studio_state__studio_v2_state_session_apne_filer(session);
        if (!(nl_streq(aktiv_fil, ""))) {
            nl_list_text_push(resultat, aktiv_fil);
        }
        int i = 0;
        while (i < nl_list_text_len(eksisterende)) {
            char * kandidat = eksisterende->data[i];
            int funnet = 0;
            int j = 0;
            while ((j < nl_list_text_len(resultat)) && (!(funnet))) {
                if (nl_streq(resultat->data[j], kandidat)) {
                    funnet = 1;
                }
                j = (j + 1);
            }
            if ((!(nl_streq(kandidat, "")) && (!(funnet))) && (nl_list_text_len(resultat) < 5)) {
                nl_list_text_push(resultat, kandidat);
            }
            i = (i + 1);
        }
        int har_state = 0;
        int har_editor = 0;
        int j = 0;
        while (j < nl_list_text_len(resultat)) {
            if (nl_streq(resultat->data[j], "studio_v2/studio_state.no")) {
                har_state = 1;
            }
            if (nl_streq(resultat->data[j], "studio_v2/editor.no")) {
                har_editor = 1;
            }
            j = (j + 1);
        }
        if ((!(har_state)) && (nl_list_text_len(resultat) < 5)) {
            nl_list_text_push(resultat, "studio_v2/studio_state.no");
        }
        if ((!(har_editor)) && (nl_list_text_len(resultat) < 5)) {
            nl_list_text_push(resultat, "studio_v2/editor.no");
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(nl_list_text* linjer) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nl_list_text_len(linjer)) {
            resultat = nl_concat(resultat, linjer->data[indeks]);
            if ((indeks + 1) < nl_list_text_len(linjer)) {
                resultat = nl_concat(resultat, "\n");
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_tekst(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * tema, char * keymap, char * runtimevalg, char * palette_open, char * sist_navigasjon, char * search_query, char * project_tree_anchor, nl_list_text* favoritter, nl_list_text* tree_fold, nl_list_text* breakpoints, nl_list_text* output, nl_list_text* run_profiles, nl_list_text* recent_prosjekter, nl_list_text* apne_filer) {
        nl_list_text* linjer = nl_list_text_new();
        nl_list_text_push(linjer, nl_concat("workspace\t", rot));
        nl_list_text_push(linjer, nl_concat("aktiv_fil\t", aktiv_fil));
        nl_list_text_push(linjer, nl_concat("aktiv_tab\t", aktiv_tab));
        nl_list_text_push(linjer, nl_concat("split_fokus\t", split_fokus));
        nl_list_text_push(linjer, nl_concat("tool_window\t", tool_window));
        nl_list_text_push(linjer, nl_concat("run_config\t", run_config));
        nl_list_text_push(linjer, nl_concat("tema\t", tema));
        nl_list_text_push(linjer, nl_concat("keymap\t", keymap));
        nl_list_text_push(linjer, nl_concat("runtimevalg\t", runtimevalg));
        nl_list_text_push(linjer, nl_concat("palette_open\t", palette_open));
        nl_list_text_push(linjer, nl_concat("sist_navigasjon\t", sist_navigasjon));
        nl_list_text_push(linjer, nl_concat("search_query\t", search_query));
        nl_list_text_push(linjer, nl_concat("project_tree_anchor\t", project_tree_anchor));
        nl_list_text_push(linjer, nl_concat("recent_count\t", nl_int_to_text(nl_list_text_len(recent_prosjekter))));
        nl_list_text_push(linjer, nl_concat("open_count\t", nl_int_to_text(nl_list_text_len(apne_filer))));
        int fold_indeks = 0;
        while (fold_indeks < nl_list_text_len(tree_fold)) {
            nl_list_text_push(linjer, nl_concat("tree_fold\t", tree_fold->data[fold_indeks]));
            fold_indeks = (fold_indeks + 1);
        }
        int breakpoint_indeks = 0;
        while (breakpoint_indeks < nl_list_text_len(breakpoints)) {
            nl_list_text_push(linjer, breakpoints->data[breakpoint_indeks]);
            breakpoint_indeks = (breakpoint_indeks + 1);
        }
        int output_indeks = 0;
        while (output_indeks < nl_list_text_len(output)) {
            nl_list_text_push(linjer, output->data[output_indeks]);
            output_indeks = (output_indeks + 1);
        }
        int favoritt_indeks = 0;
        while (favoritt_indeks < nl_list_text_len(favoritter)) {
            nl_list_text_push(linjer, nl_concat("favorite_file\t", favoritter->data[favoritt_indeks]));
            favoritt_indeks = (favoritt_indeks + 1);
        }
        int run_profile_indeks = 0;
        while (run_profile_indeks < nl_list_text_len(run_profiles)) {
            nl_list_text_push(linjer, run_profiles->data[run_profile_indeks]);
            run_profile_indeks = (run_profile_indeks + 1);
        }
        int indeks = 0;
        while (indeks < nl_list_text_len(recent_prosjekter)) {
            nl_list_text_push(linjer, nl_concat("recent_project\t", recent_prosjekter->data[indeks]));
            indeks = (indeks + 1);
        }
        indeks = 0;
        while (indeks < nl_list_text_len(apne_filer)) {
            nl_list_text_push(linjer, nl_concat("open_file\t", apne_filer->data[indeks]));
            indeks = (indeks + 1);
        }
        return studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(linjer);
        return "";
    }
    
    int studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * palette_open, char * sist_navigasjon, nl_list_text* tree_fold) {
        nl_list_text* eksisterende = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* recent_prosjekter = studio_v2_studio_state__studio_v2_state_session_recent_prosjekter_oppdatert(rot, eksisterende);
        nl_list_text* apne_filer = studio_v2_studio_state__studio_v2_state_session_apne_filer_oppdatert(aktiv_fil, eksisterende);
        nl_list_text* breakpoints = studio_v2_studio_state__studio_v2_state_session_breakpoints(eksisterende);
        nl_list_text* output = studio_v2_studio_state__studio_v2_state_session_output(eksisterende);
        nl_list_text* run_profiles = studio_v2_studio_state__studio_v2_state_session_run_profiles(eksisterende);
        char * tema = studio_v2_studio_state__studio_v2_state_session_tema(eksisterende);
        char * keymap = studio_v2_studio_state__studio_v2_state_session_keymap(eksisterende);
        char * runtimevalg = studio_v2_studio_state__studio_v2_state_session_runtimevalg(eksisterende);
        char * search_query = studio_v2_studio_state__studio_v2_state_session_search_query(eksisterende);
        char * project_tree_anchor = studio_v2_studio_state__studio_v2_state_session_project_tree_anchor(eksisterende);
        nl_list_text* favoritter = studio_v2_studio_state__studio_v2_state_session_favoritter(eksisterende);
        char * debug_config = studio_v2_studio_state__studio_v2_state_session_debug_config(eksisterende);
        char * debug_mode = studio_v2_studio_state__studio_v2_state_session_debug_status(eksisterende);
        char * debug_action = studio_v2_studio_state__studio_v2_state_session_debug_handling(eksisterende);
        int debug_linje = studio_v2_studio_state__studio_v2_state_session_debug_linje(eksisterende);
        char * base = studio_v2_studio_state__studio_v2_state_session_tekst(rot, aktiv_fil, aktiv_tab, split_fokus, tool_window, run_config, tema, keymap, runtimevalg, palette_open, sist_navigasjon, search_query, project_tree_anchor, favoritter, tree_fold, breakpoints, output, run_profiles, recent_prosjekter, apne_filer);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_debug_oppdatert(nl_split_lines(base), debug_config, debug_mode, debug_action, debug_linje));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand_og_breakpoints(char * rot, char * aktiv_fil, char * aktiv_tab, char * split_fokus, char * tool_window, char * run_config, char * palette_open, char * sist_navigasjon, nl_list_text* tree_fold, nl_list_text* breakpoints) {
        nl_list_text* eksisterende = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* recent_prosjekter = studio_v2_studio_state__studio_v2_state_session_recent_prosjekter_oppdatert(rot, eksisterende);
        nl_list_text* apne_filer = studio_v2_studio_state__studio_v2_state_session_apne_filer_oppdatert(aktiv_fil, eksisterende);
        nl_list_text* output = studio_v2_studio_state__studio_v2_state_session_output(eksisterende);
        nl_list_text* run_profiles = studio_v2_studio_state__studio_v2_state_session_run_profiles(eksisterende);
        char * tema = studio_v2_studio_state__studio_v2_state_session_tema(eksisterende);
        char * keymap = studio_v2_studio_state__studio_v2_state_session_keymap(eksisterende);
        char * runtimevalg = studio_v2_studio_state__studio_v2_state_session_runtimevalg(eksisterende);
        char * search_query = studio_v2_studio_state__studio_v2_state_session_search_query(eksisterende);
        char * project_tree_anchor = studio_v2_studio_state__studio_v2_state_session_project_tree_anchor(eksisterende);
        nl_list_text* favoritter = studio_v2_studio_state__studio_v2_state_session_favoritter(eksisterende);
        char * debug_config = studio_v2_studio_state__studio_v2_state_session_debug_config(eksisterende);
        char * debug_mode = studio_v2_studio_state__studio_v2_state_session_debug_status(eksisterende);
        char * debug_action = studio_v2_studio_state__studio_v2_state_session_debug_handling(eksisterende);
        int debug_linje = studio_v2_studio_state__studio_v2_state_session_debug_linje(eksisterende);
        char * base = studio_v2_studio_state__studio_v2_state_session_tekst(rot, aktiv_fil, aktiv_tab, split_fokus, tool_window, run_config, tema, keymap, runtimevalg, palette_open, sist_navigasjon, search_query, project_tree_anchor, favoritter, tree_fold, breakpoints, output, run_profiles, recent_prosjekter, apne_filer);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_debug_oppdatert(nl_split_lines(base), debug_config, debug_mode, debug_action, debug_linje));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_lagre(char * rot, char * aktiv_fil) {
        return studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand(rot, aktiv_fil, aktiv_fil, "høyre", "Project", "run", "lukket", aktiv_fil, nl_list_text_new());
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_search_query_oppdatert(nl_list_text* session, char * query) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "search_query\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        nl_list_text_push(resultat, nl_concat("search_query\t", query));
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_search_query_skriv_med_tilstand(char * rot, char * query) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * innhold = studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(studio_v2_studio_state__studio_v2_state_session_search_query_oppdatert(session, query));
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), innhold);
        return 0;
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_favoritter_oppdatert(nl_list_text* session, char * favoritt) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* eksisterende = studio_v2_studio_state__studio_v2_state_session_favoritter(session);
        int funnet = 0;
        int i = 0;
        while (i < nl_list_text_len(eksisterende)) {
            if (nl_streq(eksisterende->data[i], favoritt)) {
                funnet = 1;
            }
            else {
                nl_list_text_push(resultat, eksisterende->data[i]);
            }
            i = (i + 1);
        }
        if (!(nl_streq(favoritt, "")) && (!(funnet))) {
            nl_list_text_push(resultat, favoritt);
        }
        if (nl_list_text_len(resultat) > 5) {
            nl_list_text* trimmet = nl_list_text_new();
            int start = (nl_list_text_len(resultat) - 5);
            int indeks = start;
            while (indeks < nl_list_text_len(resultat)) {
                nl_list_text_push(trimmet, resultat->data[indeks]);
                indeks = (indeks + 1);
            }
            return trimmet;
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_studio_state__studio_v2_state_session_favoritter_skriv_med_tilstand(char * rot, char * favoritt) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* oppdatert = studio_v2_studio_state__studio_v2_state_session_favoritter_oppdatert(session, favoritt);
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(session)) {
            char * linje = session->data[indeks];
            char * ren = nl_text_trim(linje);
            if (!(nl_text_starter_med(ren, "favorite_file\t"))) {
                nl_list_text_push(resultat, linje);
            }
            indeks = (indeks + 1);
        }
        int i = 0;
        while (i < nl_list_text_len(oppdatert)) {
            nl_list_text_push(resultat, nl_concat("favorite_file\t", oppdatert->data[i]));
            i = (i + 1);
        }
        return nl_write_file(studio_v2_studio_state__studio_v2_state_session_fil(rot), studio_v2_studio_state__studio_v2_state_session_linjene_til_tekst(resultat));
        return 0;
    }
    
    int studio_v2_studio_state__studio_v2_state_session_breakpoint_toggle(char * rot, char * fil, int linje) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * aktiv_fil = studio_v2_studio_state__studio_v2_state_session_aktiv_fil(session);
        if (nl_streq(aktiv_fil, "")) {
            aktiv_fil = fil;
        }
        char * aktiv_tab = studio_v2_studio_state__studio_v2_state_session_aktiv_tab(session);
        if (nl_streq(aktiv_tab, "")) {
            aktiv_tab = aktiv_fil;
        }
        char * split_fokus = studio_v2_studio_state__studio_v2_state_session_split_fokus(session);
        char * tool_window = studio_v2_studio_state__studio_v2_state_session_tool_window(session);
        char * run_config = studio_v2_studio_state__studio_v2_state_session_run_config(session);
        char * palette_open = studio_v2_studio_state__studio_v2_state_session_palette_status(session);
        char * sist_navigasjon = studio_v2_studio_state__studio_v2_state_session_sist_navigasjon(session);
        nl_list_text* tree_fold = studio_v2_studio_state__studio_v2_state_session_tree_fold(session);
        nl_list_text* breakpoints = studio_v2_studio_state__studio_v2_state_session_breakpoints_oppdatert(session, fil, linje);
        return studio_v2_studio_state__studio_v2_state_session_lagre_med_tilstand_og_breakpoints(rot, aktiv_fil, aktiv_tab, split_fokus, tool_window, run_config, palette_open, sist_navigasjon, tree_fold, breakpoints);
        return 0;
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_workspace(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "workspace");
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_aktiv_fil(nl_list_text* session) {
        return studio_v2_studio_state__studio_v2_state_session_verdi(session, "aktiv_fil");
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_session_recent_for_workspace(char * rot) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        return studio_v2_studio_state__studio_v2_state_session_recent_prosjekter_oppdatert(rot, session);
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_status_for_workspace(char * rot) {
        if (nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_les(rot)) > 0) {
            return "klar";
        }
        return "tom";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_session_status(char * rot) {
        if (nl_list_text_len(studio_v2_studio_state__studio_v2_state_session_les(rot)) > 0) {
            return "klar";
        }
        return "tom";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_rot(nl_list_text* args) {
        int indeks = 0;
        while (indeks < nl_list_text_len(args)) {
            if (!(nl_text_starter_med(args->data[indeks], "--"))) {
                return args->data[indeks];
            }
            indeks = (indeks + 1);
        }
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(".");
        char * workspace_rot = studio_v2_studio_state__studio_v2_state_session_workspace(session);
        if (!(nl_streq(workspace_rot, ""))) {
            return workspace_rot;
        }
        return ".";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_filsti(char * rot, char * sti_relativ) {
        return nl_concat(nl_concat(rot, "/"), sti_relativ);
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_fil_innhold(char * rot, char * sti_relativ) {
        nl_list_text* kandidater = nl_list_text_new();
        nl_list_text_push(kandidater, studio_v2_studio_state__studio_v2_state_filsti(rot, sti_relativ));
        nl_list_text_push(kandidater, sti_relativ);
        nl_list_text_push(kandidater, nl_concat("../", sti_relativ));
        nl_list_text_push(kandidater, nl_concat("../../", sti_relativ));
        int indeks = 0;
        while (indeks < nl_list_text_len(kandidater)) {
            if (nl_file_exists(kandidater->data[indeks])) {
                return nl_read_file(kandidater->data[indeks]);
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_studio_state__studio_v2_state_aktiv_fil(char * rot) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        char * aktiv_fil = studio_v2_studio_state__studio_v2_state_session_aktiv_fil(session);
        if (!(nl_streq(aktiv_fil, "")) && nl_file_exists(studio_v2_studio_state__studio_v2_state_filsti(rot, aktiv_fil))) {
            return aktiv_fil;
        }
        nl_list_text* åpne_filer = studio_v2_studio_state__studio_v2_state_session_apne_filer(session);
        int indeks = 0;
        while (indeks < nl_list_text_len(åpne_filer)) {
            char * kandidat = åpne_filer->data[indeks];
            if (!(nl_streq(kandidat, "")) && nl_file_exists(studio_v2_studio_state__studio_v2_state_filsti(rot, kandidat))) {
                return kandidat;
            }
            indeks = (indeks + 1);
        }
        nl_list_text* workspace_filer = studio_v2_studio_state__studio_v2_state_workspace_filer(rot);
        if (nl_list_text_len(workspace_filer) > 0) {
            return workspace_filer->data[0];
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_apne_filer(char * rot, char * aktiv_fil) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* resultat = studio_v2_studio_state__studio_v2_state_session_apne_filer_oppdatert(aktiv_fil, session);
        if (nl_list_text_len(resultat) == 0) {
            if (!(nl_streq(aktiv_fil, ""))) {
                nl_list_text_push(resultat, aktiv_fil);
            }
            nl_list_text_push(resultat, "studio_v2/studio_state.no");
            nl_list_text_push(resultat, "studio_v2/editor.no");
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_workspace_filer(char * rot) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* kataloger = nl_list_text_new();
        nl_list_text_push(kataloger, "studio_v2");
        nl_list_text_push(kataloger, "std");
        nl_list_text_push(kataloger, "examples");
        int katalog_indeks = 0;
        while (katalog_indeks < nl_list_text_len(kataloger)) {
            nl_list_text* kandidater = nl_list_text_new();
            nl_list_text_push(kandidater, nl_concat(nl_concat(rot, "/"), kataloger->data[katalog_indeks]));
            nl_list_text_push(kandidater, kataloger->data[katalog_indeks]);
            nl_list_text_push(kandidater, nl_concat("../", kataloger->data[katalog_indeks]));
            nl_list_text_push(kandidater, nl_concat("../../", kataloger->data[katalog_indeks]));
            int kandidat_indeks = 0;
            while (kandidat_indeks < nl_list_text_len(kandidater)) {
                nl_list_text* filer = nl_list_files_tree(kandidater->data[kandidat_indeks]);
                if (nl_list_text_len(filer) > 0) {
                    int fil_indeks = 0;
                    while (fil_indeks < nl_list_text_len(filer)) {
                        nl_list_text_push(resultat, filer->data[fil_indeks]);
                        fil_indeks = (fil_indeks + 1);
                    }
                    break;
                }
                kandidat_indeks = (kandidat_indeks + 1);
            }
            int fil_indeks = 0;
            katalog_indeks = (katalog_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_workspace_filer_status(nl_list_text* filer) {
        if (nl_list_text_len(filer) > 20) {
            return "hurtig-delvis";
        }
        if (nl_list_text_len(filer) > 0) {
            return "hurtig";
        }
        return "tom";
        return "";
    }
    
    nl_list_text* studio_v2_studio_state__studio_v2_state_test_filer(char * rot) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* filer = studio_v2_studio_state__studio_v2_state_workspace_filer(rot);
        int indeks = 0;
        while (indeks < nl_list_text_len(filer)) {
            char * kandidat = filer->data[indeks];
            if (nl_text_inneholder(kandidat, "/tests/test_") && nl_text_slutter_med(kandidat, ".no")) {
                nl_list_text_push(resultat, kandidat);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_studio_state__studio_v2_state_status() {
        return "foundation";
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjektnavn() {
        return "Norscode Studio v2";
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjektrot(nl_list_text* args) {
        int indeks = 0;
        while (indeks < nl_list_text_len(args)) {
            if (!(nl_text_starter_med(args->data[indeks], "--"))) {
                return args->data[indeks];
            }
            indeks = (indeks + 1);
        }
        return ".";
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjektstatus() {
        return "tom";
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjekt_vcs_status_fil(char * rot) {
        return nl_concat(rot, "/.norscode/studio_v2_git_status.txt");
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjekt_vcs_diff_fil(char * rot) {
        return nl_concat(rot, "/.norscode/studio_v2_git_diff.txt");
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjekt_vcs_branch_fil(char * rot) {
        return nl_concat(rot, "/.norscode/studio_v2_git_branch.txt");
        return "";
    }
    
    char * studio_v2_project__studio_v2_prosjekt_vcs_commit_fil(char * rot) {
        return nl_concat(rot, "/.norscode/studio_v2_git_commit.txt");
        return "";
    }
    
    int studio_v2_project__studio_v2_prosjekt_vcs_kjor(char * rot, char * kommando, char * utfil) {
        return nl_run_command(0);
        return 0;
    }
    
    char * studio_v2_project__studio_v2_prosjekt_vcs_branch(char * rot) {
        char * utfil = studio_v2_project__studio_v2_prosjekt_vcs_branch_fil(rot);
        studio_v2_project__studio_v2_prosjekt_vcs_kjor(rot, "branch --show-current", utfil);
        if (nl_file_exists(utfil)) {
            char * branch = nl_text_trim(nl_read_file(utfil));
            if (nl_streq(branch, "")) {
                return "detached";
            }
            return branch;
        }
        return "detached";
        return "";
    }
    
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_commit(char * rot) {
        char * utfil = studio_v2_project__studio_v2_prosjekt_vcs_commit_fil(rot);
        studio_v2_project__studio_v2_prosjekt_vcs_kjor(rot, "log -1 --oneline --decorate --no-color", utfil);
        if (nl_file_exists(utfil)) {
            return nl_split_lines(nl_read_file(utfil));
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_history(char * rot) {
        char * utfil = nl_concat(rot, "/.norscode/studio_v2_git_history.txt");
        studio_v2_project__studio_v2_prosjekt_vcs_kjor(rot, "log --oneline --decorate --no-color --max-count=5", utfil);
        if (nl_file_exists(utfil)) {
            return nl_split_lines(nl_read_file(utfil));
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int studio_v2_project__studio_v2_prosjekt_vcs_stage(char * rot, char * fil) {
        return nl_run_command(0);
        return 0;
    }
    
    int studio_v2_project__studio_v2_prosjekt_vcs_unstage(char * rot, char * fil) {
        return nl_run_command(0);
        return 0;
    }
    
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_status(char * rot) {
        char * utfil = studio_v2_project__studio_v2_prosjekt_vcs_status_fil(rot);
        studio_v2_project__studio_v2_prosjekt_vcs_kjor(rot, "status --short --untracked-files=all", utfil);
        if (nl_file_exists(utfil)) {
            return nl_split_lines(nl_read_file(utfil));
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_diff_stat(char * rot) {
        char * utfil = studio_v2_project__studio_v2_prosjekt_vcs_diff_fil(rot);
        studio_v2_project__studio_v2_prosjekt_vcs_kjor(rot, "diff --stat -- .", utfil);
        if (nl_file_exists(utfil)) {
            return nl_split_lines(nl_read_file(utfil));
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_project__studio_v2_prosjekt_vcs_changed_filer(char * rot) {
        nl_list_text* status = studio_v2_project__studio_v2_prosjekt_vcs_status(rot);
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(status)) {
            char * linje = nl_text_trim(status->data[indeks]);
            if (nl_text_length(linje) > 3) {
                nl_list_text_push(resultat, nl_text_slice(linje, 3, nl_text_length(linje)));
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_project__studio_v2_prosjekt_vcs_antall(char * rot) {
        return nl_list_text_len(studio_v2_project__studio_v2_prosjekt_vcs_status(rot));
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_er_kilde_fil(char * sti) {
        return nl_text_slutter_med(sti, ".no");
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(char * tekstverdi, char * tegn) {
        int indeks = 0;
        while (indeks < nl_text_length(tekstverdi)) {
            if (nl_streq(nl_text_slice(tekstverdi, indeks, (indeks + 1)), tegn)) {
                return indeks;
            }
            indeks = (indeks + 1);
        }
        return (-(1));
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(char * tekstverdi, char * søk) {
        if (nl_streq(søk, "")) {
            return (-(1));
        }
        int indeks = 0;
        int grense = nl_text_length(tekstverdi);
        int søk_lengde = nl_text_length(søk);
        while (indeks < grense) {
            if (((indeks + søk_lengde) <= grense) && nl_streq(nl_text_slice(tekstverdi, indeks, (indeks + søk_lengde)), søk)) {
                return indeks;
            }
            indeks = (indeks + 1);
        }
        return (-(1));
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_finn_siste_tegn_posisjon(char * tekstverdi, char * tegn) {
        int indeks = (nl_text_length(tekstverdi) - 1);
        while (indeks >= 0) {
            if (nl_streq(nl_text_slice(tekstverdi, indeks, (indeks + 1)), tegn)) {
                return indeks;
            }
            indeks = (indeks - 1);
        }
        return (-(1));
        return 0;
    }
    
    char * studio_v2_symbol__studio_v2_symbol_liste_til_tekst(nl_list_text* verdier) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nl_list_text_len(verdier)) {
            if (!(nl_streq(verdier->data[indeks], ""))) {
                if (!(nl_streq(resultat, ""))) {
                    resultat = nl_concat(resultat, ", ");
                }
                resultat = nl_concat(resultat, verdier->data[indeks]);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(char * linje) {
        char * resultat = "";
        int indeks = 0;
        int i_streng = 0;
        int escape = 0;
        int grense = nl_text_length(linje);
        while (indeks < grense) {
            char * tegn = nl_text_slice(linje, indeks, (indeks + 1));
            if (i_streng) {
                if (escape) {
                    escape = 0;
                }
                else if (nl_streq(tegn, "\\")) {
                    escape = 1;
                }
                else if (nl_streq(tegn, "\"")) {
                    i_streng = 0;
                }
                resultat = nl_concat(resultat, " ");
            }
            else {
                if (nl_streq(tegn, "\"")) {
                    i_streng = 1;
                    resultat = nl_concat(resultat, " ");
                }
                else if (nl_streq(tegn, "#")) {
                    return resultat;
                }
                else if ((nl_streq(tegn, "/") && ((indeks + 1) < grense)) && nl_streq(nl_text_slice(linje, (indeks + 1), (indeks + 2)), "/")) {
                    return resultat;
                }
                else {
                    resultat = nl_concat(resultat, tegn);
                }
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(char * oppføring) {
        char * slag = studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(oppføring);
        if (nl_streq(slag, "funksjon")) {
            char * signatur = studio_v2_symbol__studio_v2_symbol_signatur_fra_oppf_ring(oppføring);
            if (!(nl_streq(signatur, ""))) {
                return signatur;
            }
            char * parametere = studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(oppføring);
            if (!(nl_streq(parametere, ""))) {
                return nl_concat(nl_concat("funksjon(", parametere), ")");
            }
            return "funksjon";
        }
        if (nl_streq(slag, "import")) {
            char * modul = studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(oppføring);
            if (!(nl_streq(modul, ""))) {
                return nl_concat("import ", modul);
            }
            return "import";
        }
        if (nl_streq(slag, "lokal")) {
            return "lokal";
        }
        if (nl_streq(slag, "bruk")) {
            return "bruk";
        }
        return slag;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_hover_fra_oppf_ring(char * oppføring) {
        char * navn = studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(oppføring);
        char * parametere = studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(oppføring);
        char * beskrivelse = studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(oppføring);
        char * fil = studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(oppføring);
        int linje = studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(oppføring);
        char * resultat = navn;
        if (!(nl_streq(parametere, ""))) {
            resultat = nl_concat(nl_concat(nl_concat(resultat, "("), parametere), ")");
        }
        if (!(nl_streq(beskrivelse, ""))) {
            resultat = nl_concat(nl_concat(resultat, "\n"), beskrivelse);
        }
        if (!(nl_streq(fil, ""))) {
            resultat = nl_concat(nl_concat(nl_concat(nl_concat(resultat, "\n"), fil), ":"), nl_int_to_text(linje));
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_signature_help_fra_oppf_ring(char * oppføring) {
        char * navn = studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(oppføring);
        char * parametere = studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(oppføring);
        char * beskrivelse = studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(oppføring);
        char * resultat = navn;
        if (!(nl_streq(parametere, ""))) {
            resultat = nl_concat(nl_concat(nl_concat(resultat, "("), parametere), ")");
        }
        else {
            resultat = nl_concat(resultat, "()");
        }
        if (!(nl_streq(beskrivelse, ""))) {
            resultat = nl_concat(nl_concat(resultat, "\n"), beskrivelse);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_hover_fra_workspace(char * rot, char * navn) {
        char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        if (nl_streq(oppføring, "")) {
            return "";
        }
        return studio_v2_symbol__studio_v2_symbol_hover_fra_oppf_ring(oppføring);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_signature_help_fra_workspace(char * rot, char * navn) {
        char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        if (nl_streq(oppføring, "")) {
            return "";
        }
        return studio_v2_symbol__studio_v2_symbol_signature_help_fra_oppf_ring(oppføring);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_oppf_ring(char * oppføring) {
        char * hover = studio_v2_symbol__studio_v2_symbol_hover_fra_oppf_ring(oppføring);
        char * signature = studio_v2_symbol__studio_v2_symbol_signature_help_fra_oppf_ring(oppføring);
        if (nl_streq(hover, "") && nl_streq(signature, "")) {
            return "";
        }
        if (nl_streq(hover, "")) {
            return signature;
        }
        if (nl_streq(signature, "")) {
            return hover;
        }
        return nl_concat(nl_concat(hover, " · "), signature);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_indeks(nl_list_text* indeks, char * navn) {
        char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, navn);
        if (nl_streq(oppføring, "")) {
            return "";
        }
        return studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_oppf_ring(oppføring);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_workspace(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_oppf_ring(char * slag, char * navn, char * detalj) {
        return nl_concat(nl_concat(nl_concat(nl_concat(slag, "\t"), navn), "\t"), detalj);
        return "";
    }
    
    int studio_v2_symbol__studio_v2_symbol_completion_match(char * kandidat, char * prefix) {
        if (nl_streq(prefix, "")) {
            return 1;
        }
        if (nl_text_starter_med(kandidat, prefix)) {
            return 1;
        }
        if (nl_text_inneholder(kandidat, prefix)) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_unique_add(nl_list_text* resultat, char * kandidat) {
        int funnet = 0;
        int indeks = 0;
        while ((indeks < nl_list_text_len(resultat)) && (!(funnet))) {
            if (nl_streq(resultat->data[indeks], kandidat)) {
                funnet = 1;
            }
            indeks = (indeks + 1);
        }
        if ((!(funnet)) && !(nl_streq(kandidat, ""))) {
            nl_list_text_push(resultat, kandidat);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_completion_match_starter_med(char * kandidat, char * prefix) {
        if (nl_streq(prefix, "")) {
            return 1;
        }
        return nl_text_starter_med(kandidat, prefix);
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_completion_match_utenfor_start(char * kandidat, char * prefix) {
        if (nl_streq(prefix, "")) {
            return 0;
        }
        if (nl_text_starter_med(kandidat, prefix)) {
            return 0;
        }
        return nl_text_inneholder(kandidat, prefix);
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_completion_match_n_yaktig(char * kandidat, char * prefix) {
        if (nl_streq(prefix, "")) {
            return 0;
        }
        return nl_streq(kandidat, prefix);
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(nl_list_text* resultat, nl_list_text* kandidater, char * slag, char * detalj, char * prefix, char * fase, int maks) {
        int indeks = 0;
        while ((indeks < nl_list_text_len(kandidater)) && (nl_list_text_len(resultat) < maks)) {
            char * kandidat = kandidater->data[indeks];
            if (nl_streq(fase, "nøyaktig")) {
                if (studio_v2_symbol__studio_v2_symbol_completion_match_n_yaktig(kandidat, prefix)) {
                    resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring(slag, kandidat, detalj));
                }
            }
            else if (nl_streq(fase, "starter")) {
                if (studio_v2_symbol__studio_v2_symbol_completion_match_starter_med(kandidat, prefix)) {
                    resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring(slag, kandidat, detalj));
                }
            }
            else if (nl_streq(fase, "inne")) {
                if (studio_v2_symbol__studio_v2_symbol_completion_match_utenfor_start(kandidat, prefix)) {
                    resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring(slag, kandidat, detalj));
                }
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_keywords() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_builtins() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_keyword_detalj(char * navn) {
        if (nl_streq(navn, "bruk")) {
            return "importer modul";
        }
        if (nl_streq(navn, "ellers")) {
            return "kontrollflyt";
        }
        if (nl_streq(navn, "funksjon")) {
            return "definer funksjon";
        }
        if (nl_streq(navn, "hvis")) {
            return "betinget gren";
        }
        if (nl_streq(navn, "mens")) {
            return "løkke";
        }
        if (nl_streq(navn, "returner")) {
            return "returner verdi";
        }
        if (nl_streq(navn, "bryt")) {
            return "avslutt løkke";
        }
        if (nl_streq(navn, "sann") || nl_streq(navn, "usann")) {
            return "boolsk verdi";
        }
        return "språk";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_builtin_detalj(char * navn) {
        if (nl_text_starter_med(navn, "tekst_")) {
            return "tekstverktøy";
        }
        if (nl_text_starter_med(navn, "liste_")) {
            return "lister og samlinger";
        }
        if (nl_text_starter_med(navn, "fil_")) {
            return "filsystem";
        }
        if (nl_streq(navn, "heltall_fra_tekst") || nl_streq(navn, "bool_fra_tekst")) {
            return "konvertering";
        }
        if (nl_streq(navn, "legg_til") || nl_streq(navn, "lengde")) {
            return "samlinger";
        }
        if (((nl_streq(navn, "skriv_fil") || nl_streq(navn, "les_fil")) || nl_streq(navn, "liste_filer")) || nl_streq(navn, "liste_filer_tre")) {
            return "filsystem";
        }
        if (nl_streq(navn, "kjør_kommando")) {
            return "shell-kjøring";
        }
        return "stdlib";
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette_fra_slag(nl_list_text* indeks, char * slag, nl_list_text* resultat, int maks) {
        int i = 0;
        while ((i < nl_list_text_len(indeks)) && (nl_list_text_len(resultat) < maks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), slag)) {
                resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(indeks->data[i]));
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette_prioritert(nl_list_text* indeks, int maks) {
        nl_list_text* resultat = nl_list_text_new();
        resultat = studio_v2_symbol__studio_v2_symbol_palette_fra_slag(indeks, "lokal", resultat, maks);
        resultat = studio_v2_symbol__studio_v2_symbol_palette_fra_slag(indeks, "import", resultat, maks);
        resultat = studio_v2_symbol__studio_v2_symbol_palette_fra_slag(indeks, "funksjon", resultat, maks);
        resultat = studio_v2_symbol__studio_v2_symbol_palette_fra_slag(indeks, "bruk", resultat, maks);
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_fra_indeks(nl_list_text* indeks, char * prefix, int maks) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* symbol_navn = studio_v2_symbol__studio_v2_symbol_palette_prioritert(indeks, maks);
        nl_list_text* keywords = studio_v2_symbol__studio_v2_symbol_completion_keywords();
        nl_list_text* builtins = studio_v2_symbol__studio_v2_symbol_completion_builtins();
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, keywords, "keyword", "språk", prefix, "nøyaktig", maks);
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, builtins, "builtin", "stdlib", prefix, "nøyaktig", maks);
        int i = 0;
        while ((i < nl_list_text_len(symbol_navn)) && (nl_list_text_len(resultat) < maks)) {
            char * navn = symbol_navn->data[i];
            char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, navn);
            char * detalj = studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(oppføring);
            char * sted = studio_v2_symbol__studio_v2_symbol_oppf_ring_sted(oppføring);
            if (nl_streq(detalj, "")) {
                detalj = sted;
            }
            else {
                detalj = nl_concat(nl_concat(detalj, " · "), sted);
            }
            if (studio_v2_symbol__studio_v2_symbol_completion_match_n_yaktig(navn, prefix)) {
                resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring("symbol", navn, detalj));
            }
            i = (i + 1);
        }
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, keywords, "keyword", "språk", prefix, "starter", maks);
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, builtins, "builtin", "stdlib", prefix, "starter", maks);
        i = 0;
        while ((i < nl_list_text_len(symbol_navn)) && (nl_list_text_len(resultat) < maks)) {
            char * navn = symbol_navn->data[i];
            char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, navn);
            char * detalj = studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(oppføring);
            char * sted = studio_v2_symbol__studio_v2_symbol_oppf_ring_sted(oppføring);
            if (nl_streq(detalj, "")) {
                detalj = sted;
            }
            else {
                detalj = nl_concat(nl_concat(detalj, " · "), sted);
            }
            if ((!(studio_v2_symbol__studio_v2_symbol_completion_match_n_yaktig(navn, prefix))) && studio_v2_symbol__studio_v2_symbol_completion_match_starter_med(navn, prefix)) {
                resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring("symbol", navn, detalj));
            }
            i = (i + 1);
        }
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, keywords, "keyword", "språk", prefix, "inne", maks);
        resultat = studio_v2_symbol__studio_v2_symbol_completion_tilfoy_fra_liste_fase(resultat, builtins, "builtin", "stdlib", prefix, "inne", maks);
        i = 0;
        while ((i < nl_list_text_len(symbol_navn)) && (nl_list_text_len(resultat) < maks)) {
            char * navn = symbol_navn->data[i];
            if (studio_v2_symbol__studio_v2_symbol_completion_match_utenfor_start(navn, prefix)) {
                char * oppføring = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, navn);
                char * detalj = studio_v2_symbol__studio_v2_symbol_beskrivelse_fra_oppf_ring(oppføring);
                char * sted = studio_v2_symbol__studio_v2_symbol_oppf_ring_sted(oppføring);
                if (nl_streq(detalj, "")) {
                    detalj = sted;
                }
                else {
                    detalj = nl_concat(nl_concat(detalj, " · "), sted);
                }
                resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, studio_v2_symbol__studio_v2_symbol_completion_oppf_ring("symbol", navn, detalj));
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_completion_fra_workspace(char * rot, char * prefix, int maks) {
        return studio_v2_symbol__studio_v2_symbol_completion_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), prefix, maks);
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_type(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 0) {
            return deler->data[0];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_navn(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 1) {
            return deler->data[1];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_completion_detalj(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 2) {
            return deler->data[2];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(char * linje) {
        char * ren = nl_text_trim(linje);
        if (!(nl_text_starter_med(ren, "funksjon "))) {
            return "";
        }
        char * rest = nl_text_slice(ren, 9, nl_text_length(ren));
        int navne_start = 0;
        int ferdig = 0;
        while ((navne_start < nl_text_length(rest)) && (!(ferdig))) {
            char * tegn = nl_text_slice(rest, navne_start, (navne_start + 1));
            if (!(nl_streq(tegn, " "))) {
                ferdig = 1;
            }
            else {
                navne_start = (navne_start + 1);
            }
        }
        char * navn_og_rest = nl_text_slice(rest, navne_start, nl_text_length(rest));
        int paren_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(navn_og_rest, "(");
        if (paren_posisjon < 0) {
            return nl_text_trim(navn_og_rest);
        }
        return nl_text_trim(nl_text_slice(navn_og_rest, 0, paren_posisjon));
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_finn_funksjonsparametere(char * linje) {
        int åpning = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(linje, "(");
        if (åpning < 0) {
            return "";
        }
        int lukking = studio_v2_symbol__studio_v2_symbol_finn_siste_tegn_posisjon(linje, ")");
        if ((lukking < 0) || (lukking <= åpning)) {
            return "";
        }
        char * del = nl_text_slice(linje, (åpning + 1), lukking);
        nl_list_text* parametere = nl_text_split_by(del, ",");
        nl_list_text* navn = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(parametere)) {
            char * kandidat = nl_text_trim(parametere->data[indeks]);
            if (!(nl_streq(kandidat, ""))) {
                int kolon = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(kandidat, ":");
                if (kolon >= 0) {
                    kandidat = nl_text_trim(nl_text_slice(kandidat, 0, kolon));
                }
                if (!(nl_streq(kandidat, ""))) {
                    nl_list_text_push(navn, kandidat);
                }
            }
            indeks = (indeks + 1);
        }
        return studio_v2_symbol__studio_v2_symbol_liste_til_tekst(navn);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_finn_importnavn(char * linje) {
        char * ren = nl_text_trim(linje);
        if (!(nl_text_starter_med(ren, "bruk "))) {
            return "";
        }
        char * rest = nl_text_trim(nl_text_slice(ren, 5, nl_text_length(ren)));
        if (nl_streq(rest, "")) {
            return "";
        }
        int som_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(rest, " som ");
        if (som_posisjon >= 0) {
            return nl_text_trim(nl_text_slice(rest, 0, som_posisjon));
        }
        return rest;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_finn_importalias(char * linje) {
        char * ren = nl_text_trim(linje);
        if (!(nl_text_starter_med(ren, "bruk "))) {
            return "";
        }
        char * rest = nl_text_trim(nl_text_slice(ren, 5, nl_text_length(ren)));
        if (nl_streq(rest, "")) {
            return "";
        }
        int som_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(rest, " som ");
        if (som_posisjon < 0) {
            return "";
        }
        return nl_text_trim(nl_text_slice(rest, (som_posisjon + 5), nl_text_length(rest)));
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_finn_lokalnavn(char * linje) {
        char * ren = nl_text_trim(linje);
        if (!(nl_text_starter_med(ren, "la "))) {
            return "";
        }
        char * rest = nl_text_trim(nl_text_slice(ren, 3, nl_text_length(ren)));
        if (nl_streq(rest, "")) {
            return "";
        }
        int slutt = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(rest, "=");
        if (slutt < 0) {
            slutt = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(rest, ":");
        }
        if (slutt < 0) {
            slutt = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(rest, " ");
        }
        if (slutt < 0) {
            return rest;
        }
        return nl_text_trim(nl_text_slice(rest, 0, slutt));
        return "";
    }
    
    int studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(char * linje, char * prefix, char * segment) {
        if (nl_streq(segment, "")) {
            return 0;
        }
        int start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(linje, prefix);
        if (start < 0) {
            return 0;
        }
        start = (start + nl_text_length(prefix));
        char * rest = nl_text_slice(linje, start, nl_text_length(linje));
        int posisjon = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(rest, segment);
        if (posisjon < 0) {
            return 0;
        }
        return ((start + posisjon) + 1);
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_kilde(char * sti, char * kilde) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* linjer = nl_split_lines(kilde);
        int linje_nummer = 0;
        while (linje_nummer < nl_list_text_len(linjer)) {
            char * renset = studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(linjer->data[linje_nummer]);
            char * ren = nl_text_trim(renset);
            if ((!(nl_streq(ren, "")) && (!(nl_text_starter_med(ren, "#")))) && (!(nl_text_starter_med(ren, "//")))) {
                if (nl_text_starter_med(ren, "funksjon ")) {
                    char * navn = studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(ren);
                    if (!(nl_streq(navn, ""))) {
                        char * parametere = studio_v2_symbol__studio_v2_symbol_finn_funksjonsparametere(ren);
                        int kolonne = studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(renset, "funksjon ", navn);
                        nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(sti, "\t"), nl_int_to_text((linje_nummer + 1))), "\tfunksjon\t"), navn), "\t"), ren), "\t"), parametere), "\t"), nl_int_to_text(kolonne)));
                    }
                }
                else if (nl_text_starter_med(ren, "bruk ")) {
                    char * navn = studio_v2_symbol__studio_v2_symbol_finn_importnavn(ren);
                    char * alias = studio_v2_symbol__studio_v2_symbol_finn_importalias(ren);
                    if (!(nl_streq(navn, ""))) {
                        if (!(nl_streq(alias, ""))) {
                            int kolonne = studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(renset, nl_concat(nl_concat("bruk ", navn), " som "), alias);
                            nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(sti, "\t"), nl_int_to_text((linje_nummer + 1))), "\timport\t"), alias), "\t"), ren), "\t"), navn), "\t"), nl_int_to_text(kolonne)));
                        }
                        else {
                            int kolonne = studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(renset, "bruk ", navn);
                            nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(sti, "\t"), nl_int_to_text((linje_nummer + 1))), "\timport\t"), navn), "\t"), ren), "\t\t"), nl_int_to_text(kolonne)));
                        }
                    }
                }
                else if (nl_text_starter_med(ren, "la ")) {
                    char * navn = studio_v2_symbol__studio_v2_symbol_finn_lokalnavn(ren);
                    if (!(nl_streq(navn, ""))) {
                        int kolonne = studio_v2_symbol__studio_v2_symbol_finn_kolonne_fra_segment(renset, "la ", navn);
                        nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(sti, "\t"), nl_int_to_text((linje_nummer + 1))), "\tlokal\t"), navn), "\t"), ren), "\t\t"), nl_int_to_text(kolonne)));
                    }
                }
            }
            linje_nummer = (linje_nummer + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_kilde(char * sti, char * kilde, char * navn) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* linjer = nl_split_lines(kilde);
        int linje_nummer = 0;
        while (linje_nummer < nl_list_text_len(linjer)) {
            char * ren = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(linjer->data[linje_nummer]));
            if ((!(nl_streq(ren, "")) && (!(nl_text_starter_med(ren, "#")))) && (!(nl_text_starter_med(ren, "//")))) {
                if ((!(nl_text_starter_med(ren, "funksjon "))) && studio_v2_symbol__studio_v2_symbol_linjetreff_ord(ren, navn)) {
                    nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(sti, "\t"), nl_int_to_text((linje_nummer + 1))), "\tbruk\t"), navn), "\t"), ren), "\t\t0"));
                }
            }
            linje_nummer = (linje_nummer + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_linjetreff_ord(char * tekstverdi, char * navn) {
        if (nl_streq(navn, "")) {
            return 0;
        }
        int posisjon = 0;
        int grense = nl_text_length(tekstverdi);
        int navn_lengde = nl_text_length(navn);
        while (posisjon < grense) {
            if (((posisjon + navn_lengde) <= grense) && nl_streq(nl_text_slice(tekstverdi, posisjon, (posisjon + navn_lengde)), navn)) {
                int venstre_ok = 1;
                int høyre_ok = 1;
                if (posisjon > 0) {
                    venstre_ok = (!(studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(tekstverdi, (posisjon - 1))));
                }
                if ((posisjon + navn_lengde) < grense) {
                    høyre_ok = (!(studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(tekstverdi, (posisjon + navn_lengde))));
                }
                if (venstre_ok && høyre_ok) {
                    return 1;
                }
            }
            posisjon = (posisjon + 1);
        }
        return 0;
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_filer_i_katalog(char * rot, char * katalog) {
        nl_list_text* kandidater = nl_list_text_new();
        nl_list_text_push(kandidater, nl_concat(nl_concat(rot, "/"), katalog));
        nl_list_text_push(kandidater, katalog);
        nl_list_text_push(kandidater, nl_concat("../", katalog));
        nl_list_text_push(kandidater, nl_concat("../../", katalog));
        int indeks = 0;
        while (indeks < nl_list_text_len(kandidater)) {
            nl_list_text* filer = nl_list_files_tree(kandidater->data[indeks]);
            if (nl_list_text_len(filer) > 0) {
                return filer;
            }
            indeks = (indeks + 1);
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_workspace_filer(char * rot) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* kataloger = nl_list_text_new();
        nl_list_text_push(kataloger, "studio_v2");
        nl_list_text_push(kataloger, "std");
        nl_list_text_push(kataloger, "examples");
        int katalog_indeks = 0;
        while (katalog_indeks < nl_list_text_len(kataloger)) {
            nl_list_text* filer = studio_v2_symbol__studio_v2_symbol_filer_i_katalog(rot, kataloger->data[katalog_indeks]);
            int fil_indeks = 0;
            while (fil_indeks < nl_list_text_len(filer)) {
                nl_list_text_push(resultat, filer->data[fil_indeks]);
                fil_indeks = (fil_indeks + 1);
            }
            katalog_indeks = (katalog_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_fil_innhold(char * rot, char * sti_relativ) {
        nl_list_text* kandidater = nl_list_text_new();
        nl_list_text_push(kandidater, nl_concat(nl_concat(rot, "/"), sti_relativ));
        nl_list_text_push(kandidater, sti_relativ);
        nl_list_text_push(kandidater, nl_concat("../", sti_relativ));
        nl_list_text_push(kandidater, nl_concat("../../", sti_relativ));
        int indeks = 0;
        while (indeks < nl_list_text_len(kandidater)) {
            if (nl_file_exists(kandidater->data[indeks])) {
                return nl_read_file(kandidater->data[indeks]);
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_fil(char * rot, char * sti_relativ, char * navn) {
        char * innhold = studio_v2_symbol__studio_v2_symbol_fil_innhold(rot, sti_relativ);
        if (nl_streq(innhold, "")) {
            return nl_list_text_new();
        }
        return studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_kilde(sti_relativ, innhold, navn);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(char * rot) {
        return studio_v2_symbol__studio_v2_symbol_cache_indeks(studio_v2_symbol__studio_v2_symbol_cache_fra_workspace(rot));
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(nl_list_text* filer) {
        nl_list_text* resultat = nl_list_text_new();
        int fil_indeks = 0;
        while (fil_indeks < nl_list_text_len(filer)) {
            char * sti = filer->data[fil_indeks];
            if (studio_v2_symbol__studio_v2_symbol_er_kilde_fil(sti)) {
                nl_list_text* indeks_del = studio_v2_symbol__studio_v2_symbol_indeks_fra_kilde(sti, nl_read_file(sti));
                int symbol_indeks = 0;
                while (symbol_indeks < nl_list_text_len(indeks_del)) {
                    nl_list_text_push(resultat, indeks_del->data[symbol_indeks]);
                    symbol_indeks = (symbol_indeks + 1);
                }
            }
            fil_indeks = (fil_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_uten_fil(nl_list_text* indeks, char * fil) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (!(nl_streq(studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(indeks->data[i]), fil))) {
                nl_list_text_push(resultat, indeks->data[i]);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_oppdater_fil(nl_list_text* indeks, char * fil, char * innhold) {
        nl_list_text* resultat = studio_v2_symbol__studio_v2_symbol_indeks_uten_fil(indeks, fil);
        nl_list_text* nytt = studio_v2_symbol__studio_v2_symbol_indeks_fra_kilde(fil, innhold);
        int i = 0;
        while (i < nl_list_text_len(nytt)) {
            nl_list_text_push(resultat, nytt->data[i]);
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_tom() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_cache_rot(nl_list_text* cache) {
        if (nl_list_text_len(cache) > 0) {
            nl_list_text* deler = nl_text_split_by(cache->data[0], "\t");
            if (nl_list_text_len(deler) > 1) {
                return deler->data[1];
            }
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_filer(nl_list_text* cache) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        int i_filer = (-(1));
        while (i < nl_list_text_len(cache)) {
            if (nl_streq(cache->data[i], "filer_start")) {
                i_filer = (i + 1);
            }
            else if (nl_streq(cache->data[i], "indeks_start")) {
                if (i_filer >= 0) {
                    int j = i_filer;
                    while (j < i) {
                        if (nl_text_starter_med(cache->data[j], "fil\t")) {
                            nl_list_text* deler = nl_text_split_by(cache->data[j], "\t");
                            if (nl_list_text_len(deler) > 1) {
                                nl_list_text_push(resultat, deler->data[1]);
                            }
                        }
                        j = (j + 1);
                    }
                }
                return resultat;
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_indeks(nl_list_text* cache) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        int indeks_start = (-(1));
        while (i < nl_list_text_len(cache)) {
            if (nl_streq(cache->data[i], "indeks_start")) {
                indeks_start = (i + 1);
                i = nl_list_text_len(cache);
            }
            i = (i + 1);
        }
        if (indeks_start >= 0) {
            int j = indeks_start;
            while (j < nl_list_text_len(cache)) {
                nl_list_text_push(resultat, cache->data[j]);
                j = (j + 1);
            }
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_bygg(char * rot, nl_list_text* filer, nl_list_text* indeks) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text_push(resultat, nl_concat("cache\t", rot));
        nl_list_text_push(resultat, "filer_start");
        int fil_indeks = 0;
        while (fil_indeks < nl_list_text_len(filer)) {
            nl_list_text_push(resultat, nl_concat("fil\t", filer->data[fil_indeks]));
            fil_indeks = (fil_indeks + 1);
        }
        nl_list_text_push(resultat, "indeks_start");
        int symbol_indeks = 0;
        while (symbol_indeks < nl_list_text_len(indeks)) {
            nl_list_text_push(resultat, indeks->data[symbol_indeks]);
            symbol_indeks = (symbol_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_fra_workspace(char * rot) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* cache = studio_v2_studio_state__studio_v2_state_session_symbol_cache(session);
        nl_list_text* filer = studio_v2_symbol__studio_v2_symbol_workspace_filer(rot);
        if ((nl_list_text_len(cache) > 0) && nl_streq(studio_v2_symbol__studio_v2_symbol_cache_rot(cache), rot)) {
            nl_list_text* cache_filer = studio_v2_symbol__studio_v2_symbol_cache_filer(cache);
            if (nl_list_text_len(cache_filer) == nl_list_text_len(filer)) {
                int lik = 1;
                int indeks = 0;
                while ((indeks < nl_list_text_len(filer)) && lik) {
                    if (!(nl_streq(cache_filer->data[indeks], filer->data[indeks]))) {
                        lik = 0;
                    }
                    indeks = (indeks + 1);
                }
                if (lik) {
                    return cache;
                }
            }
        }
        nl_list_text* indeks = studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(filer);
        nl_list_text* cache_ny = studio_v2_symbol__studio_v2_symbol_cache_bygg(rot, filer, indeks);
        studio_v2_studio_state__studio_v2_state_session_symbol_cache_skriv_med_tilstand(rot, cache_ny);
        return cache_ny;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil(nl_list_text* cache, char * fil, char * innhold) {
        char * rot = studio_v2_symbol__studio_v2_symbol_cache_rot(cache);
        nl_list_text* filer = studio_v2_symbol__studio_v2_symbol_cache_filer(cache);
        nl_list_text* indeks = studio_v2_symbol__studio_v2_symbol_cache_indeks(cache);
        nl_list_text* nye_filer = studio_v2_symbol__studio_v2_symbol_indeks_uten_fil(filer, fil);
        if (!(nl_streq(fil, ""))) {
            nl_list_text_push(nye_filer, fil);
        }
        nl_list_text* ny_indeks = studio_v2_symbol__studio_v2_symbol_indeks_oppdater_fil(indeks, fil, innhold);
        return studio_v2_symbol__studio_v2_symbol_cache_bygg(rot, nye_filer, ny_indeks);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil_skriv_med_tilstand(char * rot, char * fil, char * innhold) {
        nl_list_text* session = studio_v2_studio_state__studio_v2_state_session_les(rot);
        nl_list_text* cache = studio_v2_studio_state__studio_v2_state_session_symbol_cache(session);
        if ((nl_list_text_len(cache) == 0) || !(nl_streq(studio_v2_symbol__studio_v2_symbol_cache_rot(cache), rot))) {
            cache = studio_v2_symbol__studio_v2_symbol_cache_fra_workspace(rot);
        }
        nl_list_text* cache_ny = studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil(cache, fil, innhold);
        studio_v2_studio_state__studio_v2_state_session_symbol_cache_skriv_med_tilstand(rot, cache_ny);
        return cache_ny;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_workspace(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_filer(studio_v2_symbol__studio_v2_symbol_workspace_filer(rot), navn);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_filer(nl_list_text* filer, char * navn) {
        nl_list_text* resultat = nl_list_text_new();
        int fil_indeks = 0;
        while (fil_indeks < nl_list_text_len(filer)) {
            char * sti = filer->data[fil_indeks];
            if (studio_v2_symbol__studio_v2_symbol_er_kilde_fil(sti)) {
                nl_list_text* indeks_del = studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_kilde(sti, nl_read_file(sti), navn);
                int symbol_indeks = 0;
                while (symbol_indeks < nl_list_text_len(indeks_del)) {
                    nl_list_text_push(resultat, indeks_del->data[symbol_indeks]);
                    symbol_indeks = (symbol_indeks + 1);
                }
            }
            fil_indeks = (fil_indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_antall(nl_list_text* indeks) {
        return nl_list_text_len(indeks);
        return 0;
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_forste(nl_list_text* indeks) {
        if (nl_list_text_len(indeks) > 0) {
            return indeks->data[0];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn(nl_list_text* indeks, char * navn) {
        char * søk = nl_concat(nl_concat("\tfunksjon\t", navn), "\t");
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_text_inneholder(indeks->data[i], søk)) {
                return indeks->data[i];
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_navn(nl_list_text* indeks, char * navn) {
        char * søk = nl_concat(nl_concat("\t", navn), "\t");
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_text_inneholder(indeks->data[i], søk)) {
                return indeks->data[i];
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_med_slag(nl_list_text* indeks, char * slag, char * navn) {
        char * søk = nl_concat(nl_concat(nl_concat(nl_concat("\t", slag), "\t"), navn), "\t");
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_text_inneholder(indeks->data[i], søk)) {
                return indeks->data[i];
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(nl_list_text* indeks, char * navn) {
        char * kandidat = studio_v2_symbol__studio_v2_symbol_indeks_finn_med_slag(indeks, "lokal", navn);
        if (!(nl_streq(kandidat, ""))) {
            return kandidat;
        }
        kandidat = studio_v2_symbol__studio_v2_symbol_indeks_finn_med_slag(indeks, "import", navn);
        if (!(nl_streq(kandidat, ""))) {
            return kandidat;
        }
        kandidat = studio_v2_symbol__studio_v2_symbol_indeks_finn_med_slag(indeks, "funksjon", navn);
        if (!(nl_streq(kandidat, ""))) {
            return kandidat;
        }
        return studio_v2_symbol__studio_v2_symbol_indeks_finn_navn(indeks, navn);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_indeks_finn_bruk(nl_list_text* indeks, char * navn) {
        char * søk = nl_concat(nl_concat("\tbruk\t", navn), "\t");
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_text_inneholder(indeks->data[i], søk)) {
                return indeks->data[i];
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 3) {
            return deler->data[3];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 2) {
            return deler->data[2];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_signatur_fra_oppf_ring(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 4) {
            return deler->data[4];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_parametere_fra_oppf_ring(char * oppføring) {
        nl_list_text* deler = nl_text_split_by(oppføring, "\t");
        if (nl_list_text_len(deler) > 5) {
            return deler->data[5];
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_goto_def(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_goto_def_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_goto_def_fra_indeks(nl_list_text* indeks, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, navn);
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_find_references(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(nl_list_text* indeks, char * navn) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), "bruk") && nl_streq(studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(indeks->data[i]), navn)) {
                nl_list_text_push(resultat, indeks->data[i]);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_goto_reference(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_goto_reference_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), navn);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_goto_reference_fra_indeks(nl_list_text* indeks, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_indeks_forste(studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(indeks, navn));
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_navigasjon_forslag(char * rot, char * needle) {
        return studio_v2_symbol__studio_v2_symbol_navigasjon_forslag_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), rot, needle);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_navigasjon_forslag_fra_indeks(nl_list_text* indeks, char * rot, char * needle) {
        char * kandidat = studio_v2_symbol__studio_v2_symbol_goto_def_fra_indeks(indeks, needle);
        if (!(nl_streq(kandidat, ""))) {
            return kandidat;
        }
        kandidat = studio_v2_symbol__studio_v2_symbol_goto_reference_fra_indeks(indeks, needle);
        if (!(nl_streq(kandidat, ""))) {
            return kandidat;
        }
        return studio_v2_symbol__studio_v2_symbol_quick_jump(rot, needle);
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_oppf_ring_deler(char * oppføring) {
        return nl_text_split_by(oppføring, "\t");
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(char * oppføring) {
        nl_list_text* deler = studio_v2_symbol__studio_v2_symbol_oppf_ring_deler(oppføring);
        if (nl_list_text_len(deler) > 0) {
            return deler->data[0];
        }
        return "";
        return "";
    }
    
    int studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(char * oppføring) {
        nl_list_text* deler = studio_v2_symbol__studio_v2_symbol_oppf_ring_deler(oppføring);
        if (nl_list_text_len(deler) > 1) {
            return nl_text_to_int(deler->data[1]);
        }
        return 0;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_oppf_ring_kolonne(char * oppføring) {
        nl_list_text* deler = studio_v2_symbol__studio_v2_symbol_oppf_ring_deler(oppføring);
        if (nl_list_text_len(deler) > 6) {
            return nl_text_to_int(deler->data[6]);
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_symbol__studio_v2_symbol_oppf_ring_sted(char * oppføring) {
        char * fil = studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(oppføring);
        int linje = studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(oppføring);
        int kolonne = studio_v2_symbol__studio_v2_symbol_oppf_ring_kolonne(oppføring);
        if (kolonne > 0) {
            return nl_concat(nl_concat(nl_concat(nl_concat(fil, ":"), nl_int_to_text(linje)), ":"), nl_int_to_text(kolonne));
        }
        return nl_concat(nl_concat(fil, ":"), nl_int_to_text(linje));
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_quick_jump(char * rot, char * needle) {
        return studio_v2_symbol__studio_v2_symbol_quick_jump_fra_filer(studio_v2_symbol__studio_v2_symbol_workspace_filer(rot), needle);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_quick_jump_fra_filer(nl_list_text* filer, char * needle) {
        int fil_indeks = 0;
        while (fil_indeks < nl_list_text_len(filer)) {
            if (nl_text_inneholder(filer->data[fil_indeks], needle)) {
                return filer->data[fil_indeks];
            }
            fil_indeks = (fil_indeks + 1);
        }
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_palette(nl_list_text* indeks, int maks) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while ((i < nl_list_text_len(indeks)) && (nl_list_text_len(resultat) < maks)) {
            char * navn = studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(indeks->data[i]);
            int j = 0;
            int funnet = 0;
            while ((j < nl_list_text_len(resultat)) && (!(funnet))) {
                if (nl_streq(resultat->data[j], navn)) {
                    funnet = 1;
                }
                j = (j + 1);
            }
            if (!(nl_streq(navn, "")) && (!(funnet))) {
                nl_list_text_push(resultat, navn);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview(char * rot, char * gammelt, char * nytt) {
        nl_list_text* referanser = studio_v2_symbol__studio_v2_symbol_find_references(rot, gammelt);
        nl_list_text* preview = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(referanser)) {
            nl_list_text* deler = nl_text_split_by(referanser->data[i], "\t");
            if (nl_list_text_len(deler) >= 5) {
                char * nytt_innhold = nl_text_erstatt(deler->data[4], gammelt, nytt);
                nl_list_text_push(preview, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(deler->data[0], "\t"), deler->data[1]), "\t"), gammelt), " -> "), nytt), "\t"), nytt_innhold));
            }
            i = (i + 1);
        }
        return preview;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_ber_rte_filer_fra_indeks(nl_list_text* indeks, char * gammelt) {
        nl_list_text* referanser = studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(indeks, gammelt);
        nl_list_text* filer = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(referanser)) {
            char * fil = studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(referanser->data[i]);
            if (!(nl_streq(fil, ""))) {
                filer = studio_v2_symbol__studio_v2_symbol_completion_unique_add(filer, fil);
            }
            i = (i + 1);
        }
        return filer;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_indeks(nl_list_text* indeks, char * gammelt, char * nytt) {
        nl_list_text* referanser = studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(indeks, gammelt);
        nl_list_text* preview = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(referanser)) {
            nl_list_text* deler = nl_text_split_by(referanser->data[i], "\t");
            if (nl_list_text_len(deler) >= 5) {
                char * nytt_innhold = nl_text_erstatt(deler->data[4], gammelt, nytt);
                nl_list_text_push(preview, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(deler->data[0], "\t"), deler->data[1]), "\t"), gammelt), " -> "), nytt), "\t"), nytt_innhold));
            }
            i = (i + 1);
        }
        return preview;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_ber_rte_oppf_ringer_fra_indeks(nl_list_text* indeks, char * fil, char * gammelt) {
        nl_list_text* referanser = studio_v2_symbol__studio_v2_symbol_find_references_fra_indeks(indeks, gammelt);
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(referanser)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(referanser->data[i]), fil)) {
                nl_list_text_push(resultat, referanser->data[i]);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_symbol__studio_v2_symbol_tekst_fra_linjer(nl_list_text* linjer) {
        char * resultat = "";
        int i = 0;
        while (i < nl_list_text_len(linjer)) {
            if (i > 0) {
                resultat = nl_concat(resultat, "\n");
            }
            resultat = nl_concat(resultat, linjer->data[i]);
            i = (i + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_oppf_ring(char * innhold, char * oppføring, char * gammelt, char * nytt) {
        nl_list_text* linjer = nl_split_lines(innhold);
        int linje_indeks = (studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(oppføring) - 1);
        int kolonne = studio_v2_symbol__studio_v2_symbol_oppf_ring_kolonne(oppføring);
        if (((linje_indeks < 0) || (linje_indeks >= nl_list_text_len(linjer))) || (kolonne <= 0)) {
            return innhold;
        }
        char * linje = linjer->data[linje_indeks];
        int start = (kolonne - 1);
        int slutt = (start + nl_text_length(gammelt));
        if ((start < 0) || (slutt > nl_text_length(linje))) {
            return innhold;
        }
        if (!(nl_streq(nl_text_slice(linje, start, slutt), gammelt))) {
            return innhold;
        }
        linjer->data[linje_indeks] = nl_concat(nl_concat(nl_text_slice(linje, 0, start), nytt), nl_text_slice(linje, slutt, nl_text_length(linje)));
        return studio_v2_symbol__studio_v2_symbol_tekst_fra_linjer(linjer);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_innhold_fra_oppf_ringer(char * innhold, nl_list_text* oppføringer, char * gammelt, char * nytt) {
        char * resultat = innhold;
        nl_list_text* gjenværende = oppføringer;
        while (nl_list_text_len(gjenværende) > 0) {
            int valg_indeks = 0;
            int valg_linje = (-(1));
            int valg_kolonne = (-(1));
            int i = 0;
            while (i < nl_list_text_len(gjenværende)) {
                int linje = studio_v2_symbol__studio_v2_symbol_oppf_ring_linje(gjenværende->data[i]);
                int kolonne = studio_v2_symbol__studio_v2_symbol_oppf_ring_kolonne(gjenværende->data[i]);
                if ((linje > valg_linje) || ((linje == valg_linje) && (kolonne > valg_kolonne))) {
                    valg_linje = linje;
                    valg_kolonne = kolonne;
                    valg_indeks = i;
                }
                i = (i + 1);
            }
            resultat = studio_v2_symbol__studio_v2_symbol_rename_appliser_oppf_ring(resultat, gjenværende->data[valg_indeks], gammelt, nytt);
            nl_list_text* neste = nl_list_text_new();
            int j = 0;
            while (j < nl_list_text_len(gjenværende)) {
                if (j != valg_indeks) {
                    nl_list_text_push(neste, gjenværende->data[j]);
                }
                j = (j + 1);
            }
            gjenværende = neste;
        }
        return resultat;
        return "";
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_fil(char * rot, char * sti_relativ, char * gammelt, char * nytt) {
        nl_list_text* referanser = studio_v2_symbol__studio_v2_symbol_bruk_indeks_fra_fil(rot, sti_relativ, gammelt);
        nl_list_text* preview = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(referanser)) {
            nl_list_text* deler = nl_text_split_by(referanser->data[i], "\t");
            if (nl_list_text_len(deler) >= 5) {
                char * nytt_innhold = nl_text_erstatt(deler->data[4], gammelt, nytt);
                nl_list_text_push(preview, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(deler->data[0], "\t"), deler->data[1]), "\t"), gammelt), " -> "), nytt), "\t"), nytt_innhold));
            }
            i = (i + 1);
        }
        return preview;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_rename_preview_fra_filer(nl_list_text* filer, char * gammelt, char * nytt) {
        return studio_v2_symbol__studio_v2_symbol_rename_preview_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(filer), gammelt, nytt);
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(char * tekstverdi, int posisjon) {
        if ((posisjon < 0) || (posisjon >= nl_text_length(tekstverdi))) {
            return 0;
        }
        return nl_text_er_ordtegn(nl_text_slice(tekstverdi, posisjon, (posisjon + 1)));
        return 0;
    }
    
    char * studio_v2_symbol__studio_v2_symbol_erstatt_ord(char * innhold, char * gammelt, char * nytt) {
        if (nl_streq(gammelt, "") || nl_streq(gammelt, nytt)) {
            return innhold;
        }
        char * resultat = "";
        int posisjon = 0;
        int grense = nl_text_length(innhold);
        int gammelt_lengde = nl_text_length(gammelt);
        while (posisjon < grense) {
            if (((posisjon + gammelt_lengde) <= grense) && nl_streq(nl_text_slice(innhold, posisjon, (posisjon + gammelt_lengde)), gammelt)) {
                int venstre_ok = 1;
                int høyre_ok = 1;
                if (posisjon > 0) {
                    venstre_ok = (!(studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(innhold, (posisjon - 1))));
                }
                if ((posisjon + gammelt_lengde) < grense) {
                    høyre_ok = (!(studio_v2_symbol__studio_v2_symbol_er_ordtegn_pos(innhold, (posisjon + gammelt_lengde))));
                }
                if (venstre_ok && høyre_ok) {
                    resultat = nl_concat(resultat, nytt);
                    posisjon = (posisjon + gammelt_lengde);
                    continue;
                }
            }
            resultat = nl_concat(resultat, nl_text_slice(innhold, posisjon, (posisjon + 1)));
            posisjon = (posisjon + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rename_appliser_tekst(char * innhold, char * gammelt, char * nytt) {
        return studio_v2_symbol__studio_v2_symbol_erstatt_ord(innhold, gammelt, nytt);
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rename_konflikt_fra_indeks(nl_list_text* indeks, char * gammelt, char * nytt) {
        if (nl_streq(gammelt, nytt)) {
            return "";
        }
        char * eksisterende = studio_v2_symbol__studio_v2_symbol_indeks_finn_prioritert_navn(indeks, nytt);
        if (!(nl_streq(eksisterende, ""))) {
            if (!(nl_streq(studio_v2_symbol__studio_v2_symbol_navn_fra_oppf_ring(eksisterende), gammelt))) {
                return eksisterende;
            }
        }
        return "";
        return "";
    }
    
    char * studio_v2_symbol__studio_v2_symbol_rename_status(char * rot, char * gammelt, char * nytt) {
        if (nl_streq(gammelt, "") || nl_streq(nytt, "")) {
            return "tom";
        }
        if (nl_streq(gammelt, nytt)) {
            return "ingen_endring";
        }
        if (!(nl_streq(studio_v2_symbol__studio_v2_symbol_rename_konflikt_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_workspace(rot), gammelt, nytt), ""))) {
            return "konflikt";
        }
        return "klar";
        return "";
    }
    
    int studio_v2_symbol__studio_v2_symbol_rename_klar(char * rot, char * gammelt, char * nytt) {
        if (nl_streq(studio_v2_symbol__studio_v2_symbol_rename_status(rot, gammelt, nytt), "klar")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_rename_appliser_fil(char * rot, char * sti_relativ, char * gammelt, char * nytt) {
        char * sti = nl_concat(nl_concat(rot, "/"), sti_relativ);
        if (!(nl_file_exists(sti))) {
            return 0;
        }
        char * innhold = nl_read_file(sti);
        nl_list_text* oppføringer = studio_v2_symbol__studio_v2_symbol_rename_ber_rte_oppf_ringer_fra_indeks(studio_v2_symbol__studio_v2_symbol_indeks_fra_kilde(sti_relativ, innhold), sti_relativ, gammelt);
        char * nytt_innhold = studio_v2_symbol__studio_v2_symbol_rename_appliser_innhold_fra_oppf_ringer(innhold, oppføringer, gammelt, nytt);
        if (nl_streq(nytt_innhold, innhold)) {
            return 0;
        }
        nl_write_file(sti, nytt_innhold);
        studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil_skriv_med_tilstand(rot, sti_relativ, nytt_innhold);
        return 1;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_rename_appliser_filer(char * rot, nl_list_text* filer, char * gammelt, char * nytt) {
        nl_list_text* indeks = studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(filer);
        nl_list_text* berørte_filer = studio_v2_symbol__studio_v2_symbol_rename_ber_rte_filer_fra_indeks(indeks, gammelt);
        int antall = 0;
        int posisjon = 0;
        while (posisjon < nl_list_text_len(berørte_filer)) {
            char * sti = berørte_filer->data[posisjon];
            if (studio_v2_symbol__studio_v2_symbol_er_kilde_fil(sti)) {
                char * innhold = studio_v2_symbol__studio_v2_symbol_fil_innhold(rot, sti);
                if (!(nl_streq(innhold, ""))) {
                    nl_list_text* oppføringer = studio_v2_symbol__studio_v2_symbol_rename_ber_rte_oppf_ringer_fra_indeks(indeks, sti, gammelt);
                    char * nytt_innhold = studio_v2_symbol__studio_v2_symbol_rename_appliser_innhold_fra_oppf_ringer(innhold, oppføringer, gammelt, nytt);
                    if (!(nl_streq(nytt_innhold, innhold))) {
                        nl_write_file(nl_concat(nl_concat(rot, "/"), sti), nytt_innhold);
                        studio_v2_symbol__studio_v2_symbol_cache_oppdater_fil_skriv_med_tilstand(rot, sti, nytt_innhold);
                        antall = (antall + 1);
                    }
                }
            }
            posisjon = (posisjon + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(nl_list_text* indeks) {
        int antall = 0;
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), "funksjon")) {
                antall = (antall + 1);
            }
            i = (i + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_importer(nl_list_text* indeks) {
        int antall = 0;
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), "import")) {
                antall = (antall + 1);
            }
            i = (i + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_lokale(nl_list_text* indeks) {
        int antall = 0;
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), "lokal")) {
                antall = (antall + 1);
            }
            i = (i + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(nl_list_text* indeks) {
        int antall = 0;
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_slag_fra_oppf_ring(indeks->data[i]), "bruk")) {
                antall = (antall + 1);
            }
            i = (i + 1);
        }
        return antall;
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_unique_filer(nl_list_text* indeks) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            char * fil = studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(indeks->data[i]);
            if (!(nl_streq(fil, ""))) {
                resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, fil);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_indeks_oppf_ringer_for_fil(nl_list_text* indeks, char * fil) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(indeks)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_oppf_ring_fil(indeks->data[i]), fil)) {
                nl_list_text_push(resultat, indeks->data[i]);
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_definisjoner_for_fil(nl_list_text* indeks, char * fil) {
        nl_list_text* oppføringer = studio_v2_symbol__studio_v2_symbol_indeks_oppf_ringer_for_fil(indeks, fil);
        return studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(oppføringer);
        return 0;
    }
    
    int studio_v2_symbol__studio_v2_symbol_indeks_bruk_for_fil(nl_list_text* indeks, char * fil) {
        nl_list_text* oppføringer = studio_v2_symbol__studio_v2_symbol_indeks_oppf_ringer_for_fil(indeks, fil);
        return studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(oppføringer);
        return 0;
    }
    
    nl_list_text* studio_v2_symbol__studio_v2_symbol_workspace_sammendrag(char * rot) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text* cache = studio_v2_symbol__studio_v2_symbol_cache_fra_workspace(rot);
        nl_list_text* filer = studio_v2_symbol__studio_v2_symbol_cache_filer(cache);
        nl_list_text* indeks = studio_v2_symbol__studio_v2_symbol_cache_indeks(cache);
        nl_list_text_push(resultat, nl_concat("workspace\t", rot));
        nl_list_text_push(resultat, nl_concat("cache_filer\t", nl_int_to_text(nl_list_text_len(filer))));
        nl_list_text_push(resultat, nl_concat("cache_symboler\t", nl_int_to_text(nl_list_text_len(indeks))));
        nl_list_text_push(resultat, nl_concat("filer\t", nl_int_to_text(nl_list_text_len(filer))));
        nl_list_text_push(resultat, nl_concat("symboler\t", nl_int_to_text(nl_list_text_len(indeks))));
        nl_list_text_push(resultat, nl_concat("definisjoner\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(indeks))));
        nl_list_text_push(resultat, nl_concat("importer\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_importer(indeks))));
        nl_list_text_push(resultat, nl_concat("lokale\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_lokale(indeks))));
        nl_list_text_push(resultat, nl_concat("bruk\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(indeks))));
        nl_list_text* filer_unique = studio_v2_symbol__studio_v2_symbol_indeks_unique_filer(indeks);
        int i = 0;
        while ((i < nl_list_text_len(filer_unique)) && (i < 5)) {
            nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat(nl_concat(nl_concat("fil\t", filer_unique->data[i]), "\tdef\t"), nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_definisjoner_for_fil(indeks, filer_unique->data[i]))), "\tbruk\t"), nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_bruk_for_fil(indeks, filer_unique->data[i]))));
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_tom() {
        return "";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_layout() {
        return "tool-window-stripe | project | editor | inspector | status-bar";
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_tabs_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_tabs_fra_apne_filer(nl_list_text* apne_filer) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(apne_filer)) {
            char * kandidat = apne_filer->data[indeks];
            int funnet = 0;
            int j = 0;
            while ((j < nl_list_text_len(resultat)) && (!(funnet))) {
                if (nl_streq(resultat->data[j], kandidat)) {
                    funnet = 1;
                }
                j = (j + 1);
            }
            if ((!(nl_streq(kandidat, "")) && (!(funnet))) && (nl_list_text_len(resultat) < 8)) {
                nl_list_text_push(resultat, kandidat);
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_status(nl_list_text* tabs) {
        if (nl_list_text_len(tabs) == 0) {
            return "tom";
        }
        if (nl_list_text_len(tabs) == 1) {
            return "enkel";
        }
        return "delt";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_split_status(nl_list_text* tabs) {
        return studio_v2_editor__studio_v2_editor_tab_status(tabs);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_split_visning(nl_list_text* tabs) {
        if (nl_list_text_len(tabs) >= 2) {
            return 0;
        }
        if (nl_list_text_len(tabs) == 1) {
            return 0;
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int studio_v2_editor__studio_v2_editor_tab_indeks(nl_list_text* tabs, char * aktiv_fil) {
        int indeks = 0;
        while (indeks < nl_list_text_len(tabs)) {
            if (nl_streq(tabs->data[indeks], aktiv_fil)) {
                return indeks;
            }
            indeks = (indeks + 1);
        }
        return (-(1));
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_n_v_rende(nl_list_text* tabs, char * aktiv_fil) {
        if (studio_v2_editor__studio_v2_editor_tab_indeks(tabs, aktiv_fil) >= 0) {
            return aktiv_fil;
        }
        if (nl_list_text_len(tabs) > 0) {
            return tabs->data[0];
        }
        return "";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_neste(nl_list_text* tabs, char * aktiv_fil) {
        if (nl_list_text_len(tabs) == 0) {
            return "";
        }
        int aktiv_indeks = studio_v2_editor__studio_v2_editor_tab_indeks(tabs, aktiv_fil);
        if (aktiv_indeks < 0) {
            return tabs->data[0];
        }
        int neste_indeks = (aktiv_indeks + 1);
        if (neste_indeks >= nl_list_text_len(tabs)) {
            neste_indeks = 0;
        }
        return tabs->data[neste_indeks];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_forrige(nl_list_text* tabs, char * aktiv_fil) {
        if (nl_list_text_len(tabs) == 0) {
            return "";
        }
        int aktiv_indeks = studio_v2_editor__studio_v2_editor_tab_indeks(tabs, aktiv_fil);
        if (aktiv_indeks < 0) {
            return tabs->data[0];
        }
        int forrige_indeks = (aktiv_indeks - 1);
        if (forrige_indeks < 0) {
            forrige_indeks = (nl_list_text_len(tabs) - 1);
        }
        return tabs->data[forrige_indeks];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_velg(nl_list_text* tabs, int valg_indeks) {
        if (nl_list_text_len(tabs) == 0) {
            return "";
        }
        if ((valg_indeks < 0) || (valg_indeks >= nl_list_text_len(tabs))) {
            return tabs->data[0];
        }
        return tabs->data[valg_indeks];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_tab_bytt(nl_list_text* tabs, char * aktiv_fil, char * retning) {
        if (nl_streq(retning, "forrige")) {
            return studio_v2_editor__studio_v2_editor_tab_forrige(tabs, aktiv_fil);
        }
        if (nl_streq(retning, "neste")) {
            return studio_v2_editor__studio_v2_editor_tab_neste(tabs, aktiv_fil);
        }
        return studio_v2_editor__studio_v2_editor_tab_n_v_rende(tabs, aktiv_fil);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_split_fokus_valgt(nl_list_text* tabs, char * aktiv_fil, char * fokus) {
        if (nl_list_text_len(tabs) == 0) {
            return "";
        }
        if (nl_list_text_len(tabs) == 1) {
            return tabs->data[0];
        }
        if (nl_streq(fokus, "høyre") || nl_streq(fokus, "hoyre")) {
            return studio_v2_editor__studio_v2_editor_tab_neste(tabs, aktiv_fil);
        }
        if (nl_streq(fokus, "venstre")) {
            return studio_v2_editor__studio_v2_editor_tab_n_v_rende(tabs, aktiv_fil);
        }
        return studio_v2_editor__studio_v2_editor_split_visning(tabs)->data[0];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_split_fokus_status(nl_list_text* tabs, char * aktiv_fil) {
        if (nl_list_text_len(tabs) == 0) {
            return "tom";
        }
        if (nl_list_text_len(tabs) == 1) {
            return "enkel";
        }
        if (!(nl_streq(studio_v2_editor__studio_v2_editor_split_fokus_valgt(tabs, aktiv_fil, "høyre"), ""))) {
            return "delt";
        }
        return "tom";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_split_fokus_neste(nl_list_text* tabs, char * aktiv_fil) {
        return studio_v2_editor__studio_v2_editor_split_fokus_valgt(tabs, aktiv_fil, "høyre");
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_split_fokus_forrige(nl_list_text* tabs, char * aktiv_fil) {
        return studio_v2_editor__studio_v2_editor_split_fokus_valgt(tabs, aktiv_fil, "venstre");
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_kjerne() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_buffer_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_buffer_fra_tekst(char * tekstverdi) {
        return nl_split_lines(tekstverdi);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_buffer_til_tekst(nl_list_text* buffer) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            resultat = nl_concat(resultat, buffer->data[indeks]);
            if ((indeks + 1) < nl_list_text_len(buffer)) {
                resultat = nl_concat(resultat, "\n");
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_format_innrykk(int nivå) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nivå) {
            resultat = nl_concat(resultat, "    ");
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_formater_buffer(nl_list_text* buffer) {
        nl_list_text* resultat = nl_list_text_new();
        int innrykk = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            char * ren = nl_text_trim(buffer->data[indeks]);
            if (nl_streq(ren, "")) {
                nl_list_text_push(resultat, "");
            }
            else {
                if (nl_text_starter_med(ren, "}")) {
                    innrykk = (innrykk - 1);
                }
                if (innrykk < 0) {
                    innrykk = 0;
                }
                nl_list_text_push(resultat, nl_concat(studio_v2_editor__studio_v2_editor_format_innrykk(innrykk), ren));
                if (nl_text_slutter_med(ren, "{")) {
                    innrykk = (innrykk + 1);
                }
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_formater_tekst(char * tekstverdi) {
        return studio_v2_editor__studio_v2_editor_buffer_til_tekst(studio_v2_editor__studio_v2_editor_formater_buffer(nl_split_lines(tekstverdi)));
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_buffer_antall_linje(nl_list_text* buffer) {
        return nl_list_text_len(buffer);
        return 0;
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor__pne(char * tekstverdi) {
        return nl_split_lines(tekstverdi);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_lagre(nl_list_text* buffer) {
        return studio_v2_editor__studio_v2_editor_buffer_til_tekst(studio_v2_editor__studio_v2_editor_formater_buffer(buffer));
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_oppdater(nl_list_text* buffer, char * tekstverdi) {
        return nl_split_lines(tekstverdi);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_last_om(nl_list_text* buffer, char * tekstverdi) {
        return nl_split_lines(tekstverdi);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_cursor_tom() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_cursor_med_posisjon(int linje, int kolonne) {
        char * verdi = nl_int_to_text(linje);
        char * kolonne_tekst = nl_int_to_text(kolonne);
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_cursor_flytt(nl_list_text* cursor, int linje, int kolonne) {
        char * verdi = nl_int_to_text(linje);
        char * kolonne_tekst = nl_int_to_text(kolonne);
        if (nl_list_text_len(cursor) < 4) {
            return 0;
        }
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_cursor_linje(nl_list_text* cursor) {
        if (nl_list_text_len(cursor) > 0) {
            return cursor->data[0];
        }
        return "1";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_cursor_kolonne(nl_list_text* cursor) {
        if (nl_list_text_len(cursor) > 1) {
            return cursor->data[1];
        }
        return "1";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_cursor_utvalg_start_linje(nl_list_text* cursor) {
        if (nl_list_text_len(cursor) > 2) {
            return cursor->data[2];
        }
        return studio_v2_editor__studio_v2_cursor_linje(cursor);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_cursor_utvalg_start_kolonne(nl_list_text* cursor) {
        if (nl_list_text_len(cursor) > 3) {
            return cursor->data[3];
        }
        return studio_v2_editor__studio_v2_cursor_kolonne(cursor);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_linjeoversikt(nl_list_text* buffer) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            nl_list_text_push(resultat, nl_concat(nl_concat(nl_int_to_text((indeks + 1)), ": "), buffer->data[indeks]));
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    int studio_v2_editor__studio_v2_editor_breakpoint_finn(nl_list_text* breakpoints, int linje_nummer) {
        char * søk = nl_int_to_text(linje_nummer);
        int indeks = 0;
        while (indeks < nl_list_text_len(breakpoints)) {
            if (nl_streq(breakpoints->data[indeks], søk)) {
                return 1;
            }
            indeks = (indeks + 1);
        }
        return 0;
        return 0;
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_toggle(nl_list_text* breakpoints, int linje_nummer) {
        nl_list_text* resultat = nl_list_text_new();
        char * søk = nl_int_to_text(linje_nummer);
        int funnet = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(breakpoints)) {
            if (nl_streq(breakpoints->data[indeks], søk)) {
                funnet = 1;
            }
            else {
                nl_list_text_push(resultat, breakpoints->data[indeks]);
            }
            indeks = (indeks + 1);
        }
        if ((!(funnet)) && (linje_nummer > 0)) {
            nl_list_text_push(resultat, søk);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_breakpoint_linje(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer) {
        char * markør = "· ";
        if (studio_v2_editor__studio_v2_editor_breakpoint_finn(breakpoints, linje_nummer)) {
            markør = "● ";
        }
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return nl_concat(nl_concat(markør, nl_int_to_text(linje_nummer)), ": ?");
        }
        return nl_concat(nl_concat(nl_concat(markør, nl_int_to_text(linje_nummer)), ": "), buffer->data[(linje_nummer - 1)]);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_breakpoint_oversikt(nl_list_text* buffer, nl_list_text* breakpoints) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            nl_list_text_push(resultat, studio_v2_editor__studio_v2_editor_breakpoint_linje(buffer, breakpoints, (indeks + 1)));
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_editor__studio_v2_editor_debug_funksjonslinje(nl_list_text* buffer, int linje_nummer) {
        if ((linje_nummer < 1) || (nl_list_text_len(buffer) == 0)) {
            return 0;
        }
        int indeks = (linje_nummer - 1);
        if (indeks >= nl_list_text_len(buffer)) {
            indeks = (nl_list_text_len(buffer) - 1);
        }
        while (indeks >= 0) {
            char * ren = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(buffer->data[indeks]));
            if (nl_text_starter_med(ren, "funksjon ")) {
                return (indeks + 1);
            }
            indeks = (indeks - 1);
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_debug_funksjonsnavn(nl_list_text* buffer, int linje_nummer) {
        int funksjonslinje = studio_v2_editor__studio_v2_editor_debug_funksjonslinje(buffer, linje_nummer);
        if ((funksjonslinje < 1) || (funksjonslinje > nl_list_text_len(buffer))) {
            return "";
        }
        return studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(buffer->data[(funksjonslinje - 1)])));
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_debug_kallstack(nl_list_text* buffer, int linje_nummer) {
        nl_list_text* resultat = nl_list_text_new();
        char * funksjonsnavn = studio_v2_editor__studio_v2_editor_debug_funksjonsnavn(buffer, linje_nummer);
        int funksjonslinje = studio_v2_editor__studio_v2_editor_debug_funksjonslinje(buffer, linje_nummer);
        if (!(nl_streq(funksjonsnavn, ""))) {
            nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat("Frame 1: ", funksjonsnavn), " · linje "), nl_int_to_text(funksjonslinje)));
        }
        if (nl_list_text_len(resultat) == 0) {
            nl_list_text_push(resultat, "Frame 1: <ingen funksjon>");
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_debug_lokale(nl_list_text* buffer, int linje_nummer) {
        nl_list_text* resultat = nl_list_text_new();
        int funksjonslinje = studio_v2_editor__studio_v2_editor_debug_funksjonslinje(buffer, linje_nummer);
        if (funksjonslinje < 1) {
            return resultat;
        }
        char * header = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(buffer->data[(funksjonslinje - 1)]));
        char * parametere = studio_v2_symbol__studio_v2_symbol_finn_funksjonsparametere(header);
        if (!(nl_streq(parametere, ""))) {
            nl_list_text* deler = nl_text_split_by(parametere, ",");
            int indeks = 0;
            while (indeks < nl_list_text_len(deler)) {
                char * kandidat = nl_text_trim(deler->data[indeks]);
                if (!(nl_streq(kandidat, ""))) {
                    nl_list_text_push(resultat, nl_concat("param ", kandidat));
                }
                indeks = (indeks + 1);
            }
        }
        int i = funksjonslinje;
        while ((i < linje_nummer) && (i <= nl_list_text_len(buffer))) {
            char * ren = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(buffer->data[(i - 1)]));
            if (nl_text_starter_med(ren, "la ")) {
                char * navn = studio_v2_symbol__studio_v2_symbol_finn_lokalnavn(ren);
                if (!(nl_streq(navn, ""))) {
                    resultat = studio_v2_symbol__studio_v2_symbol_completion_unique_add(resultat, nl_concat("lokal ", navn));
                }
            }
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_editor__studio_v2_editor_debug_neste_linje(nl_list_text* buffer, int linje_nummer) {
        if (nl_list_text_len(buffer) == 0) {
            return 0;
        }
        if (linje_nummer < 1) {
            return 1;
        }
        if (linje_nummer >= nl_list_text_len(buffer)) {
            return nl_list_text_len(buffer);
        }
        return (linje_nummer + 1);
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_neste_ikke_tomme_linje(nl_list_text* buffer, int linje_nummer) {
        if (nl_list_text_len(buffer) == 0) {
            return 0;
        }
        int indeks = linje_nummer;
        if (indeks < 1) {
            indeks = 1;
        }
        while (indeks < nl_list_text_len(buffer)) {
            indeks = (indeks + 1);
            if (!(nl_streq(nl_text_trim(buffer->data[(indeks - 1)]), ""))) {
                return indeks;
            }
        }
        return nl_list_text_len(buffer);
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_forrige_funksjonslinje(nl_list_text* buffer, int linje_nummer) {
        int funksjonslinje = studio_v2_editor__studio_v2_editor_debug_funksjonslinje(buffer, linje_nummer);
        if (funksjonslinje > 0) {
            return funksjonslinje;
        }
        if (linje_nummer < 1) {
            return 1;
        }
        if (linje_nummer > nl_list_text_len(buffer)) {
            return nl_list_text_len(buffer);
        }
        return linje_nummer;
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_f_rste_breakpoint_etter(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer) {
        int resultat = 0;
        int beste = nl_list_text_len(buffer);
        int indeks = 0;
        while (indeks < nl_list_text_len(breakpoints)) {
            int kandidat = nl_text_to_int(breakpoints->data[indeks]);
            if ((kandidat > linje_nummer) && (kandidat < beste)) {
                beste = kandidat;
                resultat = kandidat;
            }
            indeks = (indeks + 1);
        }
        if (resultat > 0) {
            return resultat;
        }
        if (nl_list_text_len(buffer) > 0) {
            return nl_list_text_len(buffer);
        }
        return 0;
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_step_over(nl_list_text* buffer, int linje_nummer) {
        return studio_v2_editor__studio_v2_editor_debug_neste_linje(buffer, linje_nummer);
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_step_into(nl_list_text* buffer, int linje_nummer) {
        return studio_v2_editor__studio_v2_editor_debug_neste_ikke_tomme_linje(buffer, linje_nummer);
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_step_out(nl_list_text* buffer, int linje_nummer) {
        return studio_v2_editor__studio_v2_editor_debug_forrige_funksjonslinje(buffer, linje_nummer);
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_debug_resume(nl_list_text* buffer, nl_list_text* breakpoints, int linje_nummer) {
        return studio_v2_editor__studio_v2_editor_debug_f_rste_breakpoint_etter(buffer, breakpoints, linje_nummer);
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_aktiv_linje(nl_list_text* buffer, int linje_nummer) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return nl_concat(nl_concat("* ", nl_int_to_text(linje_nummer)), ": ?");
        }
        return nl_concat(nl_concat(nl_concat("* ", nl_int_to_text(linje_nummer)), ": "), buffer->data[(linje_nummer - 1)]);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_goto_linje(nl_list_text* buffer, int linje_nummer) {
        if (nl_list_text_len(buffer) == 0) {
            return nl_list_text_new();
        }
        if (linje_nummer < 1) {
            linje_nummer = 1;
        }
        if (linje_nummer > nl_list_text_len(buffer)) {
            linje_nummer = nl_list_text_len(buffer);
        }
        int start = (linje_nummer - 1);
        if (start < 1) {
            start = 1;
        }
        if ((start + 2) > nl_list_text_len(buffer)) {
            start = (nl_list_text_len(buffer) - 2);
        }
        if (start < 1) {
            start = 1;
        }
        return studio_v2_editor__studio_v2_editor_visningslinjer(buffer, start, 3);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_goto_linje_fra_tekst(nl_list_text* buffer, char * linje_tekst) {
        if (nl_streq(linje_tekst, "")) {
            return studio_v2_editor__studio_v2_editor_goto_linje(buffer, 1);
        }
        return studio_v2_editor__studio_v2_editor_goto_linje(buffer, nl_text_to_int(linje_tekst));
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_visningslinjer(nl_list_text* buffer, int start_linje, int antall) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = (start_linje - 1);
        int stopp = ((start_linje - 1) + antall);
        if (indeks < 0) {
            indeks = 0;
        }
        if (stopp > nl_list_text_len(buffer)) {
            stopp = nl_list_text_len(buffer);
        }
        while (indeks < stopp) {
            nl_list_text_push(resultat, nl_concat(nl_concat(nl_int_to_text((indeks + 1)), ": "), buffer->data[indeks]));
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_goto_symbol(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_goto_def(rot, navn);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_referanser(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_find_references(rot, navn);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_referanse_valg(char * rot, char * navn, int valg_indeks) {
        nl_list_text* referanser = studio_v2_editor__studio_v2_editor_referanser(rot, navn);
        if (nl_list_text_len(referanser) == 0) {
            return "";
        }
        if ((valg_indeks < 0) || (valg_indeks >= nl_list_text_len(referanser))) {
            return referanser->data[0];
        }
        return referanser->data[valg_indeks];
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_rename_preview(char * rot, char * gammelt, char * nytt) {
        return studio_v2_symbol__studio_v2_symbol_rename_preview(rot, gammelt, nytt);
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_completion(char * rot, char * prefix) {
        return studio_v2_symbol__studio_v2_symbol_completion_fra_workspace(rot, prefix, 12);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_completion_valg(char * rot, char * prefix, int valg_indeks) {
        nl_list_text* forslag = studio_v2_editor__studio_v2_editor_completion(rot, prefix);
        if (nl_list_text_len(forslag) == 0) {
            return "";
        }
        if ((valg_indeks < 0) || (valg_indeks >= nl_list_text_len(forslag))) {
            return forslag->data[0];
        }
        return forslag->data[valg_indeks];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_completion_prefix_fra_linje(char * linje, int kolonne) {
        return studio_v2_editor__studio_v2_editor_symbol_fra_linje(linje, kolonne);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_completion_fra_linjetekst(char * rot, char * linjetekst, int kolonne) {
        char * prefix = studio_v2_editor__studio_v2_editor_completion_prefix_fra_linje(linjetekst, kolonne);
        return studio_v2_editor__studio_v2_editor_completion(rot, prefix);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_completion_valg_fra_linjetekst(char * rot, char * linjetekst, int kolonne, int valg_indeks) {
        nl_list_text* forslag = studio_v2_editor__studio_v2_editor_completion_fra_linjetekst(rot, linjetekst, kolonne);
        if (nl_list_text_len(forslag) == 0) {
            return "";
        }
        if ((valg_indeks < 0) || (valg_indeks >= nl_list_text_len(forslag))) {
            return forslag->data[0];
        }
        return forslag->data[valg_indeks];
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_completion_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return nl_list_text_new();
        }
        return studio_v2_editor__studio_v2_editor_completion_fra_linjetekst(rot, buffer->data[(linje_nummer - 1)], kolonne);
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_completion_valg_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne, int valg_indeks) {
        nl_list_text* forslag = studio_v2_editor__studio_v2_editor_completion_fra_buffer(rot, buffer, linje_nummer, kolonne);
        if (nl_list_text_len(forslag) == 0) {
            return "";
        }
        if ((valg_indeks < 0) || (valg_indeks >= nl_list_text_len(forslag))) {
            return forslag->data[0];
        }
        return forslag->data[valg_indeks];
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hover(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_hover_fra_workspace(rot, navn);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_help(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_signature_help_fra_workspace(rot, navn);
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_aktiv_parameter_fra_linje(char * linje, int kolonne) {
        if (nl_streq(linje, "") || (kolonne < 1)) {
            return 0;
        }
        int grense = (kolonne - 1);
        if (grense > nl_text_length(linje)) {
            grense = nl_text_length(linje);
        }
        char * prefix = nl_text_slice(linje, 0, grense);
        char * renset = studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(prefix);
        int dyp = 0;
        int aktiv = 0;
        int funnet_åpning = 0;
        int indeks = 0;
        while (indeks < nl_text_length(renset)) {
            char * tegn = nl_text_slice(renset, indeks, (indeks + 1));
            if (nl_streq(tegn, "(")) {
                dyp = (dyp + 1);
                if (dyp == 1) {
                    funnet_åpning = 1;
                    aktiv = 1;
                }
            }
            else if (nl_streq(tegn, ")")) {
                if (dyp > 0) {
                    dyp = (dyp - 1);
                }
            }
            else if (nl_streq(tegn, ",") && (dyp == 1)) {
                aktiv = (aktiv + 1);
            }
            indeks = (indeks + 1);
        }
        if (!(funnet_åpning)) {
            return 0;
        }
        if (nl_text_starter_med(nl_text_trim(linje), "funksjon ")) {
            return 0;
        }
        return aktiv;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_navn_fra_linje(char * linje, int kolonne) {
        if (nl_streq(linje, "") || (kolonne < 1)) {
            return "";
        }
        char * ren_linje = studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(nl_text_slice(linje, 0, (kolonne - 1)));
        if (nl_text_starter_med(nl_text_trim(ren_linje), "funksjon ")) {
            return studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(ren_linje);
        }
        int dyp = 0;
        int indeks = (nl_text_length(ren_linje) - 1);
        while (indeks >= 0) {
            char * tegn = nl_text_slice(ren_linje, indeks, (indeks + 1));
            if (nl_streq(tegn, ")")) {
                dyp = (dyp + 1);
            }
            else if (nl_streq(tegn, "(")) {
                if (dyp == 0) {
                    int slutt = indeks;
                    while ((slutt > 0) && nl_streq(nl_text_slice(ren_linje, (slutt - 1), slutt), " ")) {
                        slutt = (slutt - 1);
                    }
                    int start = slutt;
                    while ((start > 0) && (!(studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(ren_linje, (start - 1), start))))) {
                        start = (start - 1);
                    }
                    char * kandidat = nl_text_trim(nl_text_slice(ren_linje, start, slutt));
                    if (studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(kandidat)) {
                        return "";
                    }
                    return kandidat;
                }
                dyp = (dyp - 1);
            }
            indeks = (indeks - 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hurtiginfo(char * rot, char * navn) {
        return studio_v2_symbol__studio_v2_symbol_hurtiginfo_fra_workspace(rot, navn);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_linjetekst(char * rot, char * linjetekst, int kolonne) {
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_linje_med_funksjon(linjetekst, kolonne);
        if (nl_streq(navn, "")) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hurtiginfo(rot, navn);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hurtiginfo_fra_linjetekst(rot, buffer->data[(linje_nummer - 1)], kolonne);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hurtiginfo_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_aktiv_linje(buffer->data[(linje_nummer - 1)]);
        if (nl_streq(navn, "")) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hurtiginfo(rot, navn);
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_er_symbol_delimiter(char * tegn) {
        if (((nl_streq(tegn, " ") || nl_streq(tegn, "\t")) || nl_streq(tegn, "(")) || nl_streq(tegn, ")")) {
            return 1;
        }
        if (((nl_streq(tegn, "{") || nl_streq(tegn, "}")) || nl_streq(tegn, "[")) || nl_streq(tegn, "]")) {
            return 1;
        }
        if (((nl_streq(tegn, ",") || nl_streq(tegn, ":")) || nl_streq(tegn, ";")) || nl_streq(tegn, ".")) {
            return 1;
        }
        if (((nl_streq(tegn, "+") || nl_streq(tegn, "-")) || nl_streq(tegn, "*")) || nl_streq(tegn, "/")) {
            return 1;
        }
        if (((nl_streq(tegn, "=") || nl_streq(tegn, "!")) || nl_streq(tegn, "<")) || nl_streq(tegn, ">")) {
            return 1;
        }
        if (((nl_streq(tegn, "&") || nl_streq(tegn, "|")) || nl_streq(tegn, "^")) || nl_streq(tegn, "%")) {
            return 1;
        }
        if ((nl_streq(tegn, "\"") || nl_streq(tegn, "'")) || nl_streq(tegn, "#")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_symbol_fra_linje(char * linje, int kolonne) {
        if (nl_streq(linje, "")) {
            return "";
        }
        if (kolonne < 1) {
            kolonne = 1;
        }
        int lengde_linjen = nl_text_length(linje);
        if (lengde_linjen == 0) {
            return "";
        }
        if (kolonne > lengde_linjen) {
            kolonne = lengde_linjen;
        }
        int posisjon = (kolonne - 1);
        char * tegn = nl_text_slice(linje, posisjon, (posisjon + 1));
        if (studio_v2_editor__studio_v2_editor_er_symbol_delimiter(tegn) && (posisjon > 0)) {
            posisjon = (posisjon - 1);
        }
        if (studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(linje, posisjon, (posisjon + 1)))) {
            return "";
        }
        int start = posisjon;
        while ((start > 0) && (!(studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(linje, (start - 1), start))))) {
            start = (start - 1);
        }
        int stopp = (posisjon + 1);
        while ((stopp < lengde_linjen) && (!(studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(linje, stopp, (stopp + 1)))))) {
            stopp = (stopp + 1);
        }
        return nl_text_slice(linje, start, stopp);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_symbol_fra_linje_med_funksjon(char * linje, int kolonne) {
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_linje(linje, kolonne);
        char * funksjonsnavn = studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(linje);
        if (!(nl_streq(funksjonsnavn, "")) && ((nl_streq(navn, "funksjon") || nl_streq(navn, "")) || nl_text_starter_med(nl_text_trim(linje), "funksjon "))) {
            return funksjonsnavn;
        }
        return navn;
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(char * navn) {
        if ((nl_streq(navn, "funksjon") || nl_streq(navn, "returner")) || nl_streq(navn, "la")) {
            return 1;
        }
        if (((nl_streq(navn, "hvis") || nl_streq(navn, "ellers")) || nl_streq(navn, "mens")) || nl_streq(navn, "bryt")) {
            return 1;
        }
        if (nl_streq(navn, "sann") || nl_streq(navn, "usann")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_symbol_foran_foerste_paren(char * linje) {
        int paren = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(linje, "(");
        if (paren <= 0) {
            return "";
        }
        int slutt = paren;
        while ((slutt > 0) && nl_streq(nl_text_slice(linje, (slutt - 1), slutt), " ")) {
            slutt = (slutt - 1);
        }
        int start = slutt;
        while ((start > 0) && (!(studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(linje, (start - 1), start))))) {
            start = (start - 1);
        }
        char * navn = nl_text_trim(nl_text_slice(linje, start, slutt));
        if (studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(navn)) {
            return "";
        }
        return navn;
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_symbol_etter_likhet(char * linje) {
        int likhet = studio_v2_symbol__studio_v2_symbol_finn_tegn_posisjon(linje, "=");
        if (likhet < 0) {
            return "";
        }
        char * kandidat = nl_text_trim(nl_text_slice(linje, (likhet + 1), nl_text_length(linje)));
        if (nl_streq(kandidat, "")) {
            return "";
        }
        char * foran_paren = studio_v2_editor__studio_v2_editor_symbol_foran_foerste_paren(kandidat);
        if (!(nl_streq(foran_paren, ""))) {
            return foran_paren;
        }
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_linje(kandidat, nl_text_length(kandidat));
        if (studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(navn)) {
            return "";
        }
        return navn;
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_symbol_fra_aktiv_linje(char * linje) {
        if (nl_streq(linje, "")) {
            return "";
        }
        char * ren = nl_text_trim(linje);
        if (nl_text_starter_med(ren, "ellers hvis ")) {
            ren = nl_text_trim(nl_text_slice(ren, 12, nl_text_length(ren)));
        }
        if (nl_text_starter_med(ren, "ellers ")) {
            ren = nl_text_trim(nl_text_slice(ren, 7, nl_text_length(ren)));
        }
        if (nl_text_starter_med(ren, "returner ")) {
            ren = nl_text_trim(nl_text_slice(ren, 9, nl_text_length(ren)));
        }
        if (nl_text_starter_med(ren, "funksjon ")) {
            char * funksjonsnavn = studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(ren);
            if (!(nl_streq(funksjonsnavn, ""))) {
                return funksjonsnavn;
            }
        }
        if (nl_text_starter_med(ren, "la ")) {
            char * etter_likhet = studio_v2_editor__studio_v2_editor_symbol_etter_likhet(ren);
            if (!(nl_streq(etter_likhet, ""))) {
                return etter_likhet;
            }
        }
        char * foran_paren = studio_v2_editor__studio_v2_editor_symbol_foran_foerste_paren(ren);
        if (!(nl_streq(foran_paren, ""))) {
            return foran_paren;
        }
        char * fallback = studio_v2_editor__studio_v2_editor_symbol_fra_linje(ren, nl_text_length(ren));
        if ((!(studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(fallback))) && !(nl_streq(fallback, ""))) {
            return fallback;
        }
        int indeks = (nl_text_length(ren) - 1);
        while (indeks >= 0) {
            while ((indeks >= 0) && studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(ren, indeks, (indeks + 1)))) {
                indeks = (indeks - 1);
            }
            if (indeks < 0) {
                return "";
            }
            int slutt = (indeks + 1);
            int start = indeks;
            while ((start > 0) && (!(studio_v2_editor__studio_v2_editor_er_symbol_delimiter(nl_text_slice(ren, (start - 1), start))))) {
                start = (start - 1);
            }
            char * kandidat = nl_text_slice(ren, start, slutt);
            if (!(studio_v2_editor__studio_v2_editor_er_reservert_symbolnavn(kandidat))) {
                return kandidat;
            }
            indeks = (start - 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_navn_fra_completion(char * rot, char * linjetekst, int kolonne) {
        nl_list_text* forslag = studio_v2_editor__studio_v2_editor_completion_fra_linjetekst(rot, linjetekst, kolonne);
        int indeks = 0;
        while (indeks < nl_list_text_len(forslag)) {
            if (nl_streq(studio_v2_symbol__studio_v2_symbol_completion_type(forslag->data[indeks]), "symbol") || nl_streq(studio_v2_symbol__studio_v2_symbol_completion_type(forslag->data[indeks]), "builtin")) {
                return studio_v2_symbol__studio_v2_symbol_completion_navn(forslag->data[indeks]);
            }
            indeks = (indeks + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_help_med_hover(char * rot, char * navn) {
        char * signatur = studio_v2_editor__studio_v2_editor_signature_help(rot, navn);
        char * hover = studio_v2_editor__studio_v2_editor_hover(rot, navn);
        if (!(nl_streq(hover, "")) && (!(nl_text_inneholder(signatur, hover)))) {
            return nl_concat(nl_concat(signatur, "\n"), hover);
        }
        return signatur;
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hover_fra_linjetekst(char * rot, char * linjetekst, int kolonne) {
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_linje_med_funksjon(linjetekst, kolonne);
        if (nl_streq(navn, "")) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hover(rot, navn);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_linjetekst(char * rot, char * linjetekst, int kolonne) {
        char * navn = studio_v2_editor__studio_v2_editor_signature_navn_fra_linje(linjetekst, kolonne);
        if (nl_streq(navn, "")) {
            navn = studio_v2_editor__studio_v2_editor_signature_navn_fra_completion(rot, linjetekst, kolonne);
        }
        if (nl_streq(navn, "")) {
            return "";
        }
        char * signatur = studio_v2_editor__studio_v2_editor_signature_help_med_hover(rot, navn);
        int aktiv_parameter = studio_v2_editor__studio_v2_editor_aktiv_parameter_fra_linje(linjetekst, kolonne);
        if (aktiv_parameter > 0) {
            return nl_concat(nl_concat(signatur, "\nAktiv parameter: "), nl_int_to_text(aktiv_parameter));
        }
        return signatur;
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hover_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hover_fra_linjetekst(rot, buffer->data[(linje_nummer - 1)], kolonne);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_buffer(char * rot, nl_list_text* buffer, int linje_nummer, int kolonne) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_signature_help_fra_linjetekst(rot, buffer->data[(linje_nummer - 1)], kolonne);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_hover_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        char * navn = studio_v2_editor__studio_v2_editor_symbol_fra_aktiv_linje(buffer->data[(linje_nummer - 1)]);
        if (nl_streq(navn, "")) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_hover(rot, navn);
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_signature_help_fra_aktiv_linje(char * rot, nl_list_text* buffer, int linje_nummer) {
        if ((linje_nummer < 1) || (linje_nummer > nl_list_text_len(buffer))) {
            return "";
        }
        char * linjetekst = buffer->data[(linje_nummer - 1)];
        char * navn = studio_v2_editor__studio_v2_editor_signature_navn_fra_linje(linjetekst, nl_text_length(linjetekst));
        if (nl_streq(navn, "")) {
            navn = studio_v2_editor__studio_v2_editor_signature_navn_fra_completion(rot, linjetekst, nl_text_length(linjetekst));
        }
        if (nl_streq(navn, "")) {
            return "";
        }
        return studio_v2_editor__studio_v2_editor_signature_help_med_hover(rot, navn);
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_sok(nl_list_text* buffer, char * needle) {
        int treff = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            if (nl_text_inneholder(buffer->data[indeks], needle)) {
                treff = (treff + 1);
            }
            indeks = (indeks + 1);
        }
        return treff;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_sok_status(nl_list_text* buffer, char * needle) {
        if (studio_v2_editor__studio_v2_editor_sok(buffer, needle) > 0) {
            return "funnet";
        }
        return "ikke funnet";
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_telle_forekomster(char * tekstverdi, char * needle) {
        if (nl_streq(needle, "")) {
            return 0;
        }
        int resultat = 0;
        int indeks = 0;
        int tekst_lengde_verdi = nl_text_length(tekstverdi);
        int needle_lengde = nl_text_length(needle);
        if (needle_lengde <= 0) {
            return 0;
        }
        while ((indeks + needle_lengde) <= tekst_lengde_verdi) {
            if (nl_streq(nl_text_slice(tekstverdi, indeks, (indeks + needle_lengde)), needle)) {
                resultat = (resultat + 1);
                indeks = (indeks + needle_lengde);
            }
            else {
                indeks = (indeks + 1);
            }
        }
        return resultat;
        return 0;
    }
    
    char * studio_v2_editor__studio_v2_editor_erstatt_tekst(char * tekstverdi, char * gammelt, char * nytt) {
        if (nl_streq(gammelt, "")) {
            return tekstverdi;
        }
        return nl_text_erstatt(tekstverdi, gammelt, nytt);
        return "";
    }
    
    nl_list_text* studio_v2_editor__studio_v2_editor_erstatt_buffer(nl_list_text* buffer, char * gammelt, char * nytt) {
        nl_list_text* resultat = nl_list_text_new();
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            nl_list_text_push(resultat, studio_v2_editor__studio_v2_editor_erstatt_tekst(buffer->data[indeks], gammelt, nytt));
            indeks = (indeks + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_editor__studio_v2_editor_erstatt_tekst_fra_buffer(nl_list_text* buffer, char * gammelt, char * nytt) {
        return studio_v2_editor__studio_v2_editor_buffer_til_tekst(studio_v2_editor__studio_v2_editor_erstatt_buffer(buffer, gammelt, nytt));
        return "";
    }
    
    char * studio_v2_editor__studio_v2_editor_erstatt_status(nl_list_text* buffer, char * gammelt) {
        if (studio_v2_editor__studio_v2_editor_sok(buffer, gammelt) > 0) {
            return "klar";
        }
        return "tom";
        return "";
    }
    
    int studio_v2_editor__studio_v2_editor_erstatt_treff(nl_list_text* buffer, char * gammelt) {
        int treff = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            treff = (treff + studio_v2_editor__studio_v2_editor_telle_forekomster(buffer->data[indeks], gammelt));
            indeks = (indeks + 1);
        }
        return treff;
        return 0;
    }
    
    int studio_v2_editor__studio_v2_editor_forste_treff(nl_list_text* buffer, char * needle) {
        int indeks = 0;
        while (indeks < nl_list_text_len(buffer)) {
            if (nl_text_inneholder(buffer->data[indeks], needle)) {
                return (indeks + 1);
            }
            indeks = (indeks + 1);
        }
        return 0;
        return 0;
    }
    
    char * studio_v2_ui__studio_v2_ui_shell() {
        return "studio shell";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_logo_banner() {
        return "logo.svg · Norscode Studio v2";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_logo_tagline() {
        return "compact IDE workspace";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_oversikt() {
        return "Open Project · Search";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_undertittel(char * rot, char * session_status) {
        return nl_concat(nl_concat(nl_concat("Workspace: ", rot), " · Session: "), session_status);
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_velkomst_handlinger() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_tittel() {
        return "Recent Workspaces";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_status(int antall) {
        return nl_concat("Recent: ", nl_int_to_text(antall));
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_current(char * rot) {
        return nl_concat("Current workspace: ", rot);
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_sammendrag(char * rot, int antall) {
        return nl_concat(nl_concat(nl_concat("Current workspace: ", rot), " · Recent: "), nl_int_to_text(antall));
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_hint() {
        return "Select recent workspace, then restore it";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_actions() {
        return "Quick actions: Open · Restore · Search";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_restore_status() {
        return "Restore: selected recent";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_recent_shortcut() {
        return "Shortcut: Enter restores selected recent";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_run_hint() {
        return "Shortcut: Enter runs selected config";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_run_status_hint() {
        return "Status: ready";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_run_output_hint() {
        return "Output: waiting for run";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_run_history_hint() {
        return "No run history yet";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_run_suite_hint() {
        return "Suite: Run · Check · Test · Debug · CI";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_output_tittel() {
        return "Run Output";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_output_stdout_tittel() {
        return "Stdout";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_output_stderr_tittel() {
        return "Stderr";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_output_hint() {
        return "Stdout and stderr for the latest run";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_tittel() {
        return "Version Control";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_status_tittel() {
        return "Changed Files";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_diff_tittel() {
        return "Diff";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_branch_tittel() {
        return "Current Branch";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_commit_tittel() {
        return "Latest Commit";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_vcs_hint() {
        return "Select a changed file to open it in the editor";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_tool_window_hint() {
        return "Choose a tool window: Problems, References, Structure, Terminal";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_structure_hint() {
        return "Structure: symbol overview";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_search_hint() {
        return "Shortcut: Enter opens selected result";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_palette_hint() {
        return "Shortcut: Enter runs selected command";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_palette_lukket_hint() {
        return "Ctrl+P opens the command palette";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_project_hint() {
        return "Shortcut: Enter opens file";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_editor_hint() {
        return "Shortcut: Enter opens tab";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_references_hint() {
        return "Shortcut: Enter opens reference";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_rename_hint() {
        return "Shortcut: Enter previews rename";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_rename_apply_hint() {
        return "Apply Rename writes changes to disk";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_terminal_hint() {
        return "Shortcut: Enter logs command";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_problems_hint() {
        return "Shortcut: Enter logs problem";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_velkomst_spacer() {
        return "";
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_layout() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_status() {
        return "klar";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_tema_lys() {
        return "lys";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_tema_mork() {
        return "mørk";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_tema_standard() {
        return studio_v2_ui__studio_v2_ui_tema_mork();
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_tema_status(char * tema) {
        if (nl_streq(tema, studio_v2_ui__studio_v2_ui_tema_lys())) {
            return "aktivt";
        }
        if (nl_streq(tema, studio_v2_ui__studio_v2_ui_tema_mork())) {
            return "aktivt";
        }
        return "ukjent";
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_tema_palett() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_keymap_standard() {
        return "standard";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_keymap_vim() {
        return "vim";
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_keymap_palett() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_runtimevalg_run() {
        return "run";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_runtimevalg_check() {
        return "check";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_runtimevalg_test() {
        return "test";
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_runtimevalg_palett() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_tema_fra_navn(char * navn) {
        if (nl_streq(navn, "lys")) {
            return studio_v2_ui__studio_v2_ui_tema_lys();
        }
        if (nl_streq(navn, "mørk") || nl_streq(navn, "mork")) {
            return studio_v2_ui__studio_v2_ui_tema_mork();
        }
        return studio_v2_ui__studio_v2_ui_tema_standard();
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_snarveier() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_snarvei_forste() {
        return "Ctrl+O\tåpne";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_snarveier_status() {
        return "klar";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_seksjon_tittel(char * navn) {
        return nl_concat(nl_concat("[", navn), "]");
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_panel_overskrift(char * navn, char * undertittel) {
        if (nl_streq(undertittel, "")) {
            return nl_concat(nl_concat("=== ", navn), " ===");
        }
        return nl_concat(nl_concat(nl_concat("=== ", navn), " === "), undertittel);
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_panel_ikon_overskrift(char * ikon, char * navn, char * undertittel) {
        char * grunn = nl_concat(nl_concat(ikon, " "), navn);
        if (nl_streq(undertittel, "")) {
            return nl_concat(nl_concat("=== ", grunn), " ===");
        }
        return nl_concat(nl_concat(nl_concat("=== ", grunn), " === "), undertittel);
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_panel_status_overskrift(char * ikon, char * navn, char * undertittel, char * status_navn, char * status_verdi) {
        if (nl_streq(undertittel, "")) {
            return nl_concat(nl_concat(studio_v2_ui__studio_v2_ui_panel_ikon_overskrift(ikon, navn, ""), " "), studio_v2_ui__studio_v2_ui_status_chip(status_navn, status_verdi));
        }
        return nl_concat(nl_concat(studio_v2_ui__studio_v2_ui_panel_ikon_overskrift(ikon, navn, undertittel), " "), studio_v2_ui__studio_v2_ui_status_chip(status_navn, status_verdi));
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_deloverskrift(char * navn) {
        return nl_concat(nl_concat("--- ", navn), " ---");
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_status_chip(char * navn, char * verdi) {
        return nl_concat(nl_concat(navn, ": "), verdi);
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_aktiv_chip(char * navn, char * verdi) {
        return nl_concat(nl_concat(nl_concat("▶ ", navn), ": "), verdi);
        return "";
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_session_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ui__studio_v2_ui_session_fra_workspace(char * rot, char * aktiv_fil) {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ui__studio_v2_ui_session_restore(nl_list_text* session) {
        if (nl_list_text_len(session) > 0) {
            return "restaurert";
        }
        return "tom";
        return "";
    }
    
    char * studio_v2_ui__studio_v2_ui_session_status(nl_list_text* session) {
        if (nl_list_text_len(session) > 0) {
            return "klar";
        }
        return "tom";
        return "";
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_prosjekt(char * prosjektnavn, char * rot) {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_fil(char * sti, char * innhold) {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_diagnostikk(nl_list_text* diagnostikk) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(diagnostikk)) {
            nl_list_text_push(resultat, nl_concat("diagnostikk\t", diagnostikk->data[i]));
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_fra_valg(char * sti, char * innhold, int startlinje, int sluttlinje) {
        nl_list_text* resultat = studio_v2_ai_context__studio_v2_ai_kontekst_fra_fil(sti, innhold);
        nl_list_text_push(resultat, nl_concat(nl_concat(nl_concat("utvalg\t", nl_int_to_text(startlinje)), "-"), nl_int_to_text(sluttlinje)));
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai_context__studio_v2_ai_kontekst_sammendrag(char * prosjektnavn, char * rot, char * sti, char * innhold, nl_list_text* diagnostikk) {
        nl_list_text* resultat = studio_v2_ai_context__studio_v2_ai_kontekst_fra_prosjekt(prosjektnavn, rot);
        nl_list_text* filkontekst = studio_v2_ai_context__studio_v2_ai_kontekst_fra_fil(sti, innhold);
        nl_list_text* di = studio_v2_ai_context__studio_v2_ai_kontekst_fra_diagnostikk(diagnostikk);
        nl_list_text_push(resultat, nl_concat("aktiv_fil\t", sti));
        nl_list_text_push(resultat, "åpne_filer\t3");
        int i = 0;
        while (i < nl_list_text_len(filkontekst)) {
            nl_list_text_push(resultat, filkontekst->data[i]);
            i = (i + 1);
        }
        i = 0;
        while (i < nl_list_text_len(di)) {
            nl_list_text_push(resultat, di->data[i]);
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    int studio_v2_ai_context__studio_v2_ai_kontekst_antall(nl_list_text* kontekst) {
        return nl_list_text_len(kontekst);
        return 0;
    }
    
    char * studio_v2_ai_context__studio_v2_ai_kontekst_forste(nl_list_text* kontekst) {
        if (nl_list_text_len(kontekst) > 0) {
            return kontekst->data[0];
        }
        return "";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_modus_disabled() {
        return "disabled";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_modus_lokal() {
        return "local";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_modus_remote() {
        return "remote";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_modus() {
        return studio_v2_ai__studio_v2_ai_modus_disabled();
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_provider_tom() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_provider_fra_modus(char * navn, char * modus) {
        char * aktiv = "nei";
        if (!(nl_streq(modus, studio_v2_ai__studio_v2_ai_modus_disabled()))) {
            aktiv = "ja";
        }
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_provider_navn(nl_list_text* provider) {
        int i = 0;
        while (i < nl_list_text_len(provider)) {
            if (nl_text_starter_med(provider->data[i], "navn\t")) {
                return nl_text_slice(provider->data[i], 5, nl_text_length(provider->data[i]));
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_provider_modus(nl_list_text* provider) {
        int i = 0;
        while (i < nl_list_text_len(provider)) {
            if (nl_text_starter_med(provider->data[i], "modus\t")) {
                return nl_text_slice(provider->data[i], 6, nl_text_length(provider->data[i]));
            }
            i = (i + 1);
        }
        return studio_v2_ai__studio_v2_ai_modus_disabled();
        return "";
    }
    
    int studio_v2_ai__studio_v2_ai_provider_kan_bruke(nl_list_text* provider) {
        return !(nl_streq(studio_v2_ai__studio_v2_ai_provider_modus(provider), studio_v2_ai__studio_v2_ai_modus_disabled()));
        return 0;
    }
    
    char * studio_v2_ai__studio_v2_ai_provider_status(nl_list_text* provider) {
        if (studio_v2_ai__studio_v2_ai_provider_kan_bruke(provider)) {
            return "klar";
        }
        return "disabled";
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_kontrakt() {
        return 0;
        return nl_list_text_new();
    }
    
    int studio_v2_ai__studio_v2_ai_kan_bruke() {
        return 0;
        return 0;
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_handlinger() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_handlinger_forste() {
        return "forklar-kode";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handlinger_status() {
        return "preview-first";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_konteksttekst(nl_list_text* kontekst) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nl_list_text_len(kontekst)) {
            resultat = nl_concat(resultat, kontekst->data[indeks]);
            if ((indeks + 1) < nl_list_text_len(kontekst)) {
                resultat = nl_concat(resultat, "\n");
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_forklar_kode(nl_list_text* kontekst) {
        return nl_concat("Forklar koden:\n", studio_v2_ai__studio_v2_ai_tekst_konteksttekst(kontekst));
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_sammendrag_fil(nl_list_text* kontekst) {
        return nl_concat("Oppsummer filen:\n", studio_v2_ai__studio_v2_ai_tekst_konteksttekst(kontekst));
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_refaktorering(nl_list_text* kontekst) {
        return nl_concat("Foreslå refaktorering:\n", studio_v2_ai__studio_v2_ai_tekst_konteksttekst(kontekst));
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_testgenerering(nl_list_text* kontekst) {
        return nl_concat("Generer tester:\n", studio_v2_ai__studio_v2_ai_tekst_konteksttekst(kontekst));
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_tekst_patch_previsjon(nl_list_text* kontekst) {
        return nl_concat("Forhåndsvis patch:\n", studio_v2_ai__studio_v2_ai_tekst_konteksttekst(kontekst));
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handling_forklar_kode(nl_list_text* kontekst) {
        return studio_v2_ai__studio_v2_ai_tekst_forklar_kode(kontekst);
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handling_sammendrag_fil(nl_list_text* kontekst) {
        return studio_v2_ai__studio_v2_ai_tekst_sammendrag_fil(kontekst);
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handling_refaktorering(nl_list_text* kontekst) {
        return studio_v2_ai__studio_v2_ai_tekst_refaktorering(kontekst);
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handling_testgenerering(nl_list_text* kontekst) {
        return studio_v2_ai__studio_v2_ai_tekst_testgenerering(kontekst);
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_handling_patch_previsjon(nl_list_text* kontekst) {
        return studio_v2_ai__studio_v2_ai_tekst_patch_previsjon(kontekst);
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_patch_previsjon_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_patch_previsjon_fra_kontekst(nl_list_text* kontekst) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text_push(resultat, nl_concat("forslag\t1\t", studio_v2_ai__studio_v2_ai_tekst_patch_previsjon(kontekst)));
        nl_list_text_push(resultat, "handling\taccept-reject");
        nl_list_text_push(resultat, "status\tpreview");
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_patch_previsjon_status(nl_list_text* preview) {
        if (nl_list_text_len(preview) > 0) {
            return "preview";
        }
        return "tom";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_patch_previsjon_forste(nl_list_text* preview) {
        if (nl_list_text_len(preview) > 0) {
            return preview->data[0];
        }
        return "";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_patch_godkjenn(nl_list_text* preview) {
        if (nl_list_text_len(preview) > 0) {
            return "godkjent";
        }
        return "ingenting å godkjenne";
        return "";
    }
    
    char * studio_v2_ai__studio_v2_ai_patch_avvis(nl_list_text* preview) {
        if (nl_list_text_len(preview) > 0) {
            return "avvist";
        }
        return "ingenting å avvise";
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_opt_in_tom() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_opt_in_lag(char * workspace_navn, int tillat_sending, int offline_only, int rediger_kontekst) {
        char * sendetekst = "nei";
        char * offline_tekst = "nei";
        char * rediger_tekst = "nei";
        if (tillat_sending) {
            sendetekst = "ja";
        }
        if (offline_only) {
            offline_tekst = "ja";
        }
        if (rediger_kontekst) {
            rediger_tekst = "ja";
        }
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_opt_in_workspace(nl_list_text* opt_in) {
        int i = 0;
        while (i < nl_list_text_len(opt_in)) {
            if (nl_text_starter_med(opt_in->data[i], "workspace\t")) {
                return nl_text_slice(opt_in->data[i], 10, nl_text_length(opt_in->data[i]));
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    int studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(nl_list_text* opt_in) {
        int i = 0;
        while (i < nl_list_text_len(opt_in)) {
            if (nl_text_starter_med(opt_in->data[i], "tillat_sending\t")) {
                return nl_streq(nl_text_slice(opt_in->data[i], 15, nl_text_length(opt_in->data[i])), "ja");
            }
            i = (i + 1);
        }
        return 0;
        return 0;
    }
    
    int studio_v2_ai__studio_v2_ai_opt_in_offline_only(nl_list_text* opt_in) {
        int i = 0;
        while (i < nl_list_text_len(opt_in)) {
            if (nl_text_starter_med(opt_in->data[i], "offline_only\t")) {
                return nl_streq(nl_text_slice(opt_in->data[i], 13, nl_text_length(opt_in->data[i])), "ja");
            }
            i = (i + 1);
        }
        return 1;
        return 0;
    }
    
    int studio_v2_ai__studio_v2_ai_opt_in_rediger_kontekst(nl_list_text* opt_in) {
        int i = 0;
        while (i < nl_list_text_len(opt_in)) {
            if (nl_text_starter_med(opt_in->data[i], "rediger_kontekst\t")) {
                return nl_streq(nl_text_slice(opt_in->data[i], 17, nl_text_length(opt_in->data[i])), "ja");
            }
            i = (i + 1);
        }
        return 1;
        return 0;
    }
    
    char * studio_v2_ai__studio_v2_ai_opt_in_status(nl_list_text* opt_in) {
        if (studio_v2_ai__studio_v2_ai_opt_in_offline_only(opt_in)) {
            return "offline-only";
        }
        if (studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(opt_in)) {
            return "opt-in";
        }
        return "disabled";
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_personvern_policy() {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_personvern_status() {
        return "klar";
        return "";
    }
    
    int studio_v2_ai__studio_v2_ai_personvern_kan_sende(nl_list_text* opt_in) {
        return (studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(opt_in) && (!(studio_v2_ai__studio_v2_ai_opt_in_offline_only(opt_in))));
        return 0;
    }
    
    char * studio_v2_ai__studio_v2_ai_kontekst_rediger_tekst(char * tekstverdi) {
        char * resultat = tekstverdi;
        resultat = nl_text_erstatt(resultat, "passord", "[redacted]");
        resultat = nl_text_erstatt(resultat, "token", "[redacted]");
        resultat = nl_text_erstatt(resultat, "secret", "[redacted]");
        resultat = nl_text_erstatt(resultat, "hemmelig", "[redacted]");
        return resultat;
        return "";
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_rediger(nl_list_text* kontekst) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        while (i < nl_list_text_len(kontekst)) {
            nl_list_text_push(resultat, studio_v2_ai__studio_v2_ai_kontekst_rediger_tekst(kontekst->data[i]));
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_trim(nl_list_text* kontekst, int maks) {
        nl_list_text* resultat = nl_list_text_new();
        int i = 0;
        int grense = maks;
        if (grense < 0) {
            grense = 0;
        }
        while ((i < nl_list_text_len(kontekst)) && (nl_list_text_len(resultat) < grense)) {
            nl_list_text_push(resultat, kontekst->data[i]);
            i = (i + 1);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_ai__studio_v2_ai_kontekst_sikker(nl_list_text* opt_in, nl_list_text* kontekst) {
        nl_list_text* resultat = studio_v2_ai__studio_v2_ai_kontekst_rediger(kontekst);
        if (studio_v2_ai__studio_v2_ai_opt_in_offline_only(opt_in) || (!(studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(opt_in)))) {
            return studio_v2_ai__studio_v2_ai_kontekst_trim(resultat, 6);
        }
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_ai__studio_v2_ai_kontekst_sikker_status(nl_list_text* opt_in) {
        if (studio_v2_ai__studio_v2_ai_opt_in_offline_only(opt_in)) {
            return "offline-only";
        }
        if (studio_v2_ai__studio_v2_ai_opt_in_tillat_sending(opt_in)) {
            return "redacted";
        }
        return "disabled";
        return "";
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_palett() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_run_konfigurasjoner() {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_terminal(char * rot, char * fil, char * aktiv_config) {
        nl_list_text* resultat = nl_list_text_new();
        nl_list_text_push(resultat, nl_concat("$ ", studio_v2_actions__studio_v2_actions_kommando_tekst(studio_v2_actions__studio_v2_actions_kommando_for_navn(rot, fil, aktiv_config))));
        nl_list_text_push(resultat, nl_concat("$ ", studio_v2_actions__studio_v2_actions_kommando_tekst(studio_v2_actions__studio_v2_actions_kommando_check(rot, fil))));
        nl_list_text_push(resultat, nl_concat("$ ", studio_v2_actions__studio_v2_actions_kommando_tekst(studio_v2_actions__studio_v2_actions_kommando_test(rot, fil))));
        nl_list_text_push(resultat, nl_concat("$ ", studio_v2_actions__studio_v2_actions_kommando_debug_tekst(rot, fil, aktiv_config)));
        nl_list_text_push(resultat, nl_concat("$ ", studio_v2_actions__studio_v2_actions_kommando_tekst(studio_v2_actions__studio_v2_actions_kommando_runtime_ci(rot))));
        return resultat;
        return nl_list_text_new();
    }
    
    char * studio_v2_actions__studio_v2_actions_terminal_status(char * rot) {
        if (nl_streq(rot, "")) {
            return "tom";
        }
        return "klar";
        return "";
    }
    
    char * studio_v2_actions__studio_v2_actions_status(char * rot) {
        if (nl_streq(rot, "")) {
            return "tom";
        }
        return "klar";
        return "";
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_run(char * rot, char * fil) {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_check(char * rot, char * fil) {
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_test(char * rot, char * fil) {
        if ((!(nl_streq(fil, "")) && nl_text_inneholder(fil, "tests/test_")) && nl_text_slutter_med(fil, ".no")) {
            return 0;
        }
        return 0;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_debug(char * rot, char * fil) {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_actions__studio_v2_actions_kommando_debug_tekst(char * rot, char * fil, char * aktiv_config) {
        return nl_concat(nl_concat(nl_concat(studio_v2_actions__studio_v2_actions_kommando_tekst(studio_v2_actions__studio_v2_actions_kommando_debug(rot, fil)), " [config="), aktiv_config), "]");
        return "";
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_runtime_ci(char * rot) {
        return 0;
        return nl_list_text_new();
    }
    
    char * studio_v2_actions__studio_v2_actions_kommando_args_for_navn(char * rot, char * navn) {
        if (nl_streq(navn, "runtime-ci")) {
            return "--json";
        }
        return "";
        return "";
    }
    
    char * studio_v2_actions__studio_v2_actions_kommando_arbeidskatalog(char * rot) {
        return rot;
        return "";
    }
    
    nl_list_text* studio_v2_actions__studio_v2_actions_kommando_for_navn(char * rot, char * fil, char * navn) {
        if (nl_streq(navn, "run")) {
            return studio_v2_actions__studio_v2_actions_kommando_run(rot, fil);
        }
        if (nl_streq(navn, "check")) {
            return studio_v2_actions__studio_v2_actions_kommando_check(rot, fil);
        }
        if (nl_streq(navn, "test")) {
            return studio_v2_actions__studio_v2_actions_kommando_test(rot, fil);
        }
        if (nl_streq(navn, "debug")) {
            return studio_v2_actions__studio_v2_actions_kommando_debug(rot, fil);
        }
        if (nl_streq(navn, "runtime-ci")) {
            return studio_v2_actions__studio_v2_actions_kommando_runtime_ci(rot);
        }
        return studio_v2_actions__studio_v2_actions_kommando_tom();
        return nl_list_text_new();
    }
    
    char * studio_v2_actions__studio_v2_actions_kommando_tekst(nl_list_text* kommando) {
        char * resultat = "";
        int indeks = 0;
        while (indeks < nl_list_text_len(kommando)) {
            resultat = nl_concat(resultat, kommando->data[indeks]);
            if ((indeks + 1) < nl_list_text_len(kommando)) {
                resultat = nl_concat(resultat, " ");
            }
            indeks = (indeks + 1);
        }
        return resultat;
        return "";
    }
    
    char * studio_v2_actions__studio_v2_actions_kommando_status(int kode) {
        if (kode == 0) {
            return "ok";
        }
        return nl_concat(nl_concat("feil (kode ", nl_int_to_text(kode)), ")");
        return "";
    }
    
    int studio_v2_actions__studio_v2_actions_kjor(nl_list_text* kommando) {
        return nl_run_command(kommando);
        return 0;
    }
    
    char * studio_v2_actions__studio_v2_actions_trygg_kjor(char * rot, char * fil, char * navn) {
        nl_list_text* kommando = studio_v2_actions__studio_v2_actions_kommando_for_navn(rot, fil, navn);
        if (nl_list_text_len(kommando) == 0) {
            return nl_concat("Feil: ukjent kommando ", navn);
        }
        int kode = studio_v2_actions__studio_v2_actions_kjor(kommando);
        return nl_concat(nl_concat(studio_v2_actions__studio_v2_actions_kommando_tekst(kommando), " -> "), studio_v2_actions__studio_v2_actions_kommando_status(kode));
        return "";
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_tom() {
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring(char * slag, char * fil, int linje, char * melding) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(slag, "\t"), fil), "\t"), nl_int_to_text(linje)), "\t"), melding);
        return "";
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne(char * slag, char * fil, int linje, int kolonne, char * melding) {
        return nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(nl_concat(slag, "\t"), fil), "\t"), nl_int_to_text(linje)), "\t"), melding), " @kolonne "), nl_int_to_text(kolonne));
        return "";
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_finn_oppf_ring(nl_list_text* resultater, char * nøkkel) {
        int i = 0;
        char * søk = nl_concat(nøkkel, "\t");
        while (i < nl_list_text_len(resultater)) {
            if (nl_text_starter_med(resultater->data[i], søk)) {
                return resultater->data[i];
            }
            i = (i + 1);
        }
        return "";
        return "";
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_alvorlighet_fra_slag(char * slag) {
        if (nl_streq(slag, "syntax_error")) {
            return "error";
        }
        if (nl_streq(slag, "warning")) {
            return "warning";
        }
        if (nl_streq(slag, "info")) {
            return "info";
        }
        return "unknown";
        return "";
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_er_fatal(char * slag) {
        if (nl_streq(studio_v2_diagnostics__studio_v2_diagnostics_alvorlighet_fra_slag(slag), "error")) {
            return 1;
        }
        return 0;
        return 0;
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_antall_fatal(nl_list_text* diagnoser) {
        int antall = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(diagnoser)) {
            nl_list_text* deler = nl_text_split_by(diagnoser->data[indeks], "\t");
            if ((nl_list_text_len(deler) > 0) && studio_v2_diagnostics__studio_v2_diagnostics_er_fatal(deler->data[0])) {
                antall = (antall + 1);
            }
            indeks = (indeks + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_antall_gjenvinnbare(nl_list_text* diagnoser) {
        int antall = 0;
        int indeks = 0;
        while (indeks < nl_list_text_len(diagnoser)) {
            nl_list_text* deler = nl_text_split_by(diagnoser->data[indeks], "\t");
            if ((nl_list_text_len(deler) > 0) && (!(studio_v2_diagnostics__studio_v2_diagnostics_er_fatal(deler->data[0])))) {
                antall = (antall + 1);
            }
            indeks = (indeks + 1);
        }
        return antall;
        return 0;
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_tell_tegn(char * tekstverdi, char * tegn) {
        int antall = 0;
        int indeks = 0;
        while (indeks < nl_text_length(tekstverdi)) {
            if (nl_streq(nl_text_slice(tekstverdi, indeks, (indeks + 1)), tegn)) {
                antall = (antall + 1);
            }
            indeks = (indeks + 1);
        }
        return antall;
        return 0;
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(char * linje, int start_posisjon) {
        return nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(nl_text_slice(linje, start_posisjon, nl_text_length(linje))));
        return "";
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(char * linje, int blokk_start) {
        return studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(linje, (blokk_start + 1));
        return "";
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_setningstype(char * linje) {
        char * renset = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(linje));
        if (nl_streq(renset, "")) {
            return "tom";
        }
        if (nl_text_starter_med(renset, "funksjon ")) {
            return "funksjon";
        }
        if (nl_text_starter_med(renset, "bruk ") || nl_streq(renset, "bruk")) {
            return "bruk";
        }
        if (nl_text_starter_med(renset, "la ")) {
            return "la";
        }
        if (nl_text_starter_med(renset, "returner")) {
            return "returner";
        }
        if (nl_text_starter_med(renset, "ellers hvis ")) {
            return "ellers hvis";
        }
        if (nl_streq(renset, "ellers") || nl_text_starter_med(renset, "ellers {")) {
            return "ellers";
        }
        if (nl_text_starter_med(renset, "hvis ")) {
            return "hvis";
        }
        if (nl_text_starter_med(renset, "mens ")) {
            return "mens";
        }
        return "ukjent";
        return "";
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_setningskolonne(char * linje) {
        int indeks = 0;
        while (indeks < nl_text_length(linje)) {
            char * tegn = nl_text_slice(linje, indeks, (indeks + 1));
            if (!(nl_streq(tegn, " ")) && !(nl_streq(tegn, "\t"))) {
                return (indeks + 1);
            }
            indeks = (indeks + 1);
        }
        return 1;
        return 0;
    }
    
    int studio_v2_diagnostics__studio_v2_diagnostics_linje_har_uavsluttet_streng(char * linje) {
        int indeks = 0;
        int i_streng = 0;
        int escape = 0;
        int grense = nl_text_length(linje);
        while (indeks < grense) {
            char * tegn = nl_text_slice(linje, indeks, (indeks + 1));
            if (i_streng) {
                if (escape) {
                    escape = 0;
                }
                else if (nl_streq(tegn, "\\")) {
                    escape = 1;
                }
                else if (nl_streq(tegn, "\"")) {
                    i_streng = 0;
                }
            }
            else {
                if (nl_streq(tegn, "\"")) {
                    i_streng = 1;
                }
                else if (nl_streq(tegn, "#")) {
                    return 0;
                }
                else if ((nl_streq(tegn, "/") && ((indeks + 1) < grense)) && nl_streq(nl_text_slice(linje, (indeks + 1), (indeks + 2)), "/")) {
                    return 0;
                }
            }
            indeks = (indeks + 1);
        }
        return i_streng;
        return 0;
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_innhold(char * sti, char * innhold) {
        nl_list_text* resultater = nl_list_text_new();
        nl_list_text* linjer = nl_split_lines(innhold);
        int parentes = 0;
        int parentes_linje = 0;
        int parentes_kolonne = 0;
        int klammer = 0;
        int klammer_linje = 0;
        int klammer_kolonne = 0;
        int hakeparentes = 0;
        int hakeparentes_linje = 0;
        int hakeparentes_kolonne = 0;
        int linje_indeks = 0;
        while (linje_indeks < nl_list_text_len(linjer)) {
            char * linje = linjer->data[linje_indeks];
            char * renset = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(linje));
            char * setningstype = studio_v2_diagnostics__studio_v2_diagnostics_setningstype(linje);
            int setningskolonne = studio_v2_diagnostics__studio_v2_diagnostics_setningskolonne(linje);
            int tegn_indeks = 0;
            while (tegn_indeks < nl_text_length(renset)) {
                char * tegn = nl_text_slice(renset, tegn_indeks, (tegn_indeks + 1));
                if (nl_streq(tegn, "(")) {
                    parentes = (parentes + 1);
                    parentes_linje = (linje_indeks + 1);
                    parentes_kolonne = ((setningskolonne + tegn_indeks) + 1);
                }
                else if (nl_streq(tegn, ")")) {
                    parentes = (parentes - 1);
                    if (parentes < 0) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "for mange avsluttende parenteser"));
                        parentes = 0;
                        parentes_linje = 0;
                        parentes_kolonne = 0;
                    }
                }
                else if (nl_streq(tegn, "{")) {
                    klammer = (klammer + 1);
                    klammer_linje = (linje_indeks + 1);
                    klammer_kolonne = ((setningskolonne + tegn_indeks) + 1);
                }
                else if (nl_streq(tegn, "}")) {
                    klammer = (klammer - 1);
                    if (klammer < 0) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "for mange avsluttende klammer"));
                        klammer = 0;
                        klammer_linje = 0;
                        klammer_kolonne = 0;
                    }
                }
                else if (nl_streq(tegn, "[")) {
                    hakeparentes = (hakeparentes + 1);
                    hakeparentes_linje = (linje_indeks + 1);
                    hakeparentes_kolonne = ((setningskolonne + tegn_indeks) + 1);
                }
                else if (nl_streq(tegn, "]")) {
                    hakeparentes = (hakeparentes - 1);
                    if (hakeparentes < 0) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "for mange avsluttende hakeparenteser"));
                        hakeparentes = 0;
                        hakeparentes_linje = 0;
                        hakeparentes_kolonne = 0;
                    }
                }
                tegn_indeks = (tegn_indeks + 1);
            }
            if (nl_streq(setningstype, "funksjon") && (!(nl_text_inneholder(renset, "->")))) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler returtype med ->"));
            }
            if (nl_streq(setningstype, "funksjon") && (!(nl_text_inneholder(renset, "(")))) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler åpning ( i signatur"));
            }
            if (nl_streq(setningstype, "funksjon") && (!(nl_text_inneholder(renset, ")")))) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler avsluttende ) i signatur"));
            }
            if (nl_streq(setningstype, "funksjon") && nl_streq(studio_v2_symbol__studio_v2_symbol_finn_funksjonsnavn(renset), "")) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler funksjonsnavn"));
            }
            if (nl_streq(setningstype, "funksjon") && nl_text_inneholder(renset, "->")) {
                int pil_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(renset, "->");
                if (pil_posisjon >= 0) {
                    char * returtype = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(renset, (pil_posisjon + 2));
                    if (nl_streq(returtype, "") || nl_streq(returtype, "{")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler returtype etter ->"));
                    }
                    if (studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(nl_text_slice(renset, (pil_posisjon + 2), nl_text_length(renset)), "->") >= 0) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "for mange -> i signatur"));
                    }
                }
            }
            if ((nl_streq(setningstype, "funksjon") && nl_text_inneholder(renset, "(")) && nl_text_inneholder(renset, ")")) {
                int åpning = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(renset, "(");
                int lukking = studio_v2_symbol__studio_v2_symbol_finn_siste_tegn_posisjon(renset, ")");
                if ((åpning >= 0) && (lukking > åpning)) {
                    char * parametre = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(nl_text_slice(renset, (åpning + 1), lukking)));
                    if (!(nl_streq(parametre, "")) && (!(nl_text_inneholder(parametre, ":")))) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler : i parameter"));
                    }
                    if ((nl_text_inneholder(parametre, ",,") || nl_text_starter_med(parametre, ",")) || nl_text_slutter_med(parametre, ",")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler parameter etter komma"));
                    }
                }
            }
            if (nl_streq(setningstype, "funksjon") && (!(nl_text_inneholder(renset, "{")))) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler funksjonskropp"));
            }
            else if (nl_streq(setningstype, "funksjon") && nl_text_inneholder(renset, "{")) {
                int blokk_start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(renset, "{");
                if (blokk_start >= 0) {
                    char * blokk_rest = studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(renset, blokk_start);
                    if (nl_streq(blokk_rest, "")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring("syntax_error", sti, (linje_indeks + 1), "mangler innhold i funksjonsblokk"));
                    }
                }
            }
            char * ren_linje = renset;
            if (nl_streq(setningstype, "bruk") && nl_streq(ren_linje, "bruk")) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler modulnavn etter bruk"));
            }
            else if (nl_streq(setningstype, "bruk")) {
                char * bruk_innhold = nl_text_trim(studio_v2_symbol__studio_v2_symbol_rens_linje_for_s_k(nl_text_slice(ren_linje, 5, nl_text_length(ren_linje))));
                int som_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(bruk_innhold, " som ");
                if (som_posisjon >= 0) {
                    char * modul = nl_text_trim(nl_text_slice(bruk_innhold, 0, som_posisjon));
                    if (nl_streq(modul, "")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler modulnavn før som"));
                    }
                    char * alias = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(bruk_innhold, (som_posisjon + 5));
                    if (nl_streq(alias, "")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + som_posisjon) + 5), "mangler alias etter som"));
                    }
                    else if (nl_text_starter_med(alias, "#")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + som_posisjon) + 5), "mangler alias etter som"));
                    }
                    else if (nl_text_slutter_med(alias, ",")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + som_posisjon) + 5), "mangler alias etter som"));
                    }
                }
                else if (!(nl_streq(bruk_innhold, ""))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler alias etter som"));
                }
            }
            else if (nl_streq(setningstype, "la")) {
                if (nl_streq(studio_v2_symbol__studio_v2_symbol_finn_lokalnavn(ren_linje), "")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler variabelnavn"));
                }
                else if (studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "=") < 0) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler = i deklarasjon"));
                }
                else if (studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "=") >= 0) {
                    int likhet_posisjon = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "=");
                    char * verdi_tekst = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, (likhet_posisjon + 1));
                    if (nl_streq(verdi_tekst, "")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + likhet_posisjon) + 1), "mangler verdi etter ="));
                    }
                    else if (nl_text_starter_med(verdi_tekst, "#")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + likhet_posisjon) + 1), "mangler verdi etter ="));
                    }
                    else if (nl_text_slutter_med(verdi_tekst, ",")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + likhet_posisjon) + 1), "mangler verdi etter komma"));
                    }
                }
            }
            else if (nl_streq(setningstype, "returner")) {
                char * retur_del = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 8);
                if (nl_streq(retur_del, "")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler verdi etter returner"));
                }
                else if (nl_text_starter_med(retur_del, ",")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler verdi etter returner"));
                }
            }
            if (nl_streq(setningstype, "ellers") && nl_streq(ren_linje, "ellers")) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler hvis etter ellers"));
            }
            else if (nl_streq(setningstype, "ellers") && nl_text_starter_med(ren_linje, "ellers {")) {
                int blokk_start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "{");
                if (blokk_start >= 0) {
                    char * blokk_rest = studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(ren_linje, blokk_start);
                    if (nl_streq(blokk_rest, "")) {
                        nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + blokk_start) + 1), "mangler innhold i ellers-blokk"));
                    }
                }
            }
            if ((nl_streq(setningstype, "hvis") || nl_streq(setningstype, "mens")) || nl_streq(setningstype, "ellers hvis")) {
                if ((nl_streq(ren_linje, "hvis da") || nl_streq(ren_linje, "mens da")) || nl_streq(ren_linje, "ellers hvis da")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler betingelse etter kontrollflyt"));
                }
            }
            if (nl_streq(setningstype, "hvis")) {
                char * betingelse = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 5);
                if (nl_streq(betingelse, "") || nl_streq(betingelse, "da")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 5), "mangler betingelse etter hvis"));
                }
                char * kontroll_fortsatt = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 5);
                if ((!(nl_text_inneholder(kontroll_fortsatt, " da "))) && (!(nl_text_slutter_med(kontroll_fortsatt, " da")))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 5), "mangler da etter kontrollflyt"));
                }
            }
            else if (nl_streq(setningstype, "ellers hvis")) {
                char * betingelse = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 12);
                if (nl_streq(betingelse, "") || nl_streq(betingelse, "da")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 12), "mangler betingelse etter ellers hvis"));
                }
                char * kontroll_fortsatt = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 12);
                if ((!(nl_text_inneholder(kontroll_fortsatt, " da "))) && (!(nl_text_slutter_med(kontroll_fortsatt, " da")))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 12), "mangler da etter kontrollflyt"));
                }
            }
            else if (nl_streq(setningstype, "mens")) {
                char * betingelse = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 5);
                if (nl_streq(betingelse, "") || nl_streq(betingelse, "da")) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 5), "mangler betingelse etter mens"));
                }
                char * kontroll_fortsatt = studio_v2_diagnostics__studio_v2_diagnostics_rest_fra_posisjon(ren_linje, 5);
                if ((!(nl_text_inneholder(kontroll_fortsatt, " da "))) && (!(nl_text_slutter_med(kontroll_fortsatt, " da")))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), (setningskolonne + 5), "mangler da etter kontrollflyt"));
                }
            }
            if (nl_streq(setningstype, "hvis")) {
                if (!(nl_text_inneholder(ren_linje, "{"))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler blokk etter kontrollflyt"));
                }
                else if (nl_text_inneholder(ren_linje, "{")) {
                    int blokk_start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "{");
                    if (blokk_start >= 0) {
                        char * blokk_rest = studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(ren_linje, blokk_start);
                        if (nl_streq(blokk_rest, "")) {
                            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + blokk_start) + 1), "mangler innhold i hvis-blokk"));
                        }
                    }
                }
            }
            else if (nl_streq(setningstype, "ellers hvis")) {
                if (!(nl_text_inneholder(ren_linje, "{"))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler blokk etter kontrollflyt"));
                }
                else if (nl_text_inneholder(ren_linje, "{")) {
                    int blokk_start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "{");
                    if (blokk_start >= 0) {
                        char * blokk_rest = studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(ren_linje, blokk_start);
                        if (nl_streq(blokk_rest, "")) {
                            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + blokk_start) + 1), "mangler innhold i ellers hvis-blokk"));
                        }
                    }
                }
            }
            else if (nl_streq(setningstype, "mens")) {
                if (!(nl_text_inneholder(ren_linje, "{"))) {
                    nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler blokk etter kontrollflyt"));
                }
                else if (nl_text_inneholder(ren_linje, "{")) {
                    int blokk_start = studio_v2_symbol__studio_v2_symbol_finn_tekst_posisjon(ren_linje, "{");
                    if (blokk_start >= 0) {
                        char * blokk_rest = studio_v2_diagnostics__studio_v2_diagnostics_blokk_rest_fra_linje(ren_linje, blokk_start);
                        if (nl_streq(blokk_rest, "")) {
                            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), ((setningskolonne + blokk_start) + 1), "mangler innhold i mens-blokk"));
                        }
                    }
                }
            }
            if (studio_v2_diagnostics__studio_v2_diagnostics_linje_har_uavsluttet_streng(linje)) {
                nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, (linje_indeks + 1), setningskolonne, "mangler avsluttende \""));
            }
            linje_indeks = (linje_indeks + 1);
        }
        if (parentes > 0) {
            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, parentes_linje, parentes_kolonne, "mangler avsluttende parentes"));
        }
        if (klammer > 0) {
            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, klammer_linje, klammer_kolonne, "mangler avsluttende klamme"));
        }
        if (hakeparentes > 0) {
            nl_list_text_push(resultater, studio_v2_diagnostics__studio_v2_diagnostics_tekst_oppf_ring_med_kolonne("syntax_error", sti, hakeparentes_linje, hakeparentes_kolonne, "mangler avsluttende hakeparentes"));
        }
        return resultater;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_fil(char * rot, char * sti_relativ) {
        nl_list_text* kandidater = nl_list_text_new();
        nl_list_text_push(kandidater, nl_concat(nl_concat(rot, "/"), sti_relativ));
        nl_list_text_push(kandidater, sti_relativ);
        nl_list_text_push(kandidater, nl_concat("../", sti_relativ));
        nl_list_text_push(kandidater, nl_concat("../../", sti_relativ));
        int indeks = 0;
        while (indeks < nl_list_text_len(kandidater)) {
            if (nl_file_exists(kandidater->data[indeks])) {
                return studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_innhold(sti_relativ, nl_read_file(kandidater->data[indeks]));
            }
            indeks = (indeks + 1);
        }
        return nl_list_text_new();
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_workspace(char * rot) {
        nl_list_text* resultater = nl_list_text_new();
        nl_list_text* filer = studio_v2_studio_state__studio_v2_state_workspace_filer(rot);
        int fil_indeks = 0;
        while (fil_indeks < nl_list_text_len(filer)) {
            char * sti = filer->data[fil_indeks];
            if (nl_text_slutter_med(sti, ".no")) {
                nl_list_text* fil_resultater = studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_fil(rot, sti);
                int i = 0;
                while (i < nl_list_text_len(fil_resultater)) {
                    nl_list_text_push(resultater, fil_resultater->data[i]);
                    i = (i + 1);
                }
            }
            fil_indeks = (fil_indeks + 1);
        }
        return resultater;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace(char * rot) {
        nl_list_text* resultater = nl_list_text_new();
        nl_list_text* filer = studio_v2_studio_state__studio_v2_state_workspace_filer(rot);
        nl_list_text* symbol_indeks = studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(filer);
        nl_list_text* symbol_sammendrag = studio_v2_symbol__studio_v2_symbol_workspace_sammendrag(rot);
        nl_list_text* syntaks = studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_workspace(rot);
        char * aktiv_fil = studio_v2_studio_state__studio_v2_state_aktiv_fil(rot);
        nl_list_text_push(resultater, nl_concat("workspace\tNorscode Studio v2\t", rot));
        nl_list_text_push(resultater, nl_concat("aktivitetsfil\t", aktiv_fil));
        nl_list_text_push(resultater, nl_concat("åpne_filer\t", nl_int_to_text(nl_list_text_len(studio_v2_studio_state__studio_v2_state_apne_filer(rot, aktiv_fil)))));
        nl_list_text_push(resultater, nl_concat("workspace_filer\t", nl_int_to_text(nl_list_text_len(filer))));
        nl_list_text_push(resultater, nl_concat("workspace_sammendrag\t", nl_int_to_text(nl_list_text_len(symbol_sammendrag))));
        nl_list_text_push(resultater, nl_concat("syntax_errors\t", nl_int_to_text(nl_list_text_len(syntaks))));
        nl_list_text_push(resultater, nl_concat("syntax_errors_fatal\t", nl_int_to_text(studio_v2_diagnostics__studio_v2_diagnostics_antall_fatal(syntaks))));
        nl_list_text_push(resultater, nl_concat("syntax_errors_gjenvinnbare\t", nl_int_to_text(studio_v2_diagnostics__studio_v2_diagnostics_antall_gjenvinnbare(syntaks))));
        nl_list_text_push(resultater, nl_concat("symbol_definisjoner\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symbol_bruk\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symboler\t", nl_int_to_text(nl_list_text_len(symbol_indeks))));
        int sammendrag_indeks = 0;
        while ((sammendrag_indeks < nl_list_text_len(symbol_sammendrag)) && (sammendrag_indeks < 4)) {
            nl_list_text_push(resultater, symbol_sammendrag->data[sammendrag_indeks]);
            sammendrag_indeks = (sammendrag_indeks + 1);
        }
        int syntaks_indeks = 0;
        while ((syntaks_indeks < nl_list_text_len(syntaks)) && (syntaks_indeks < 3)) {
            nl_list_text_push(resultater, syntaks->data[syntaks_indeks]);
            syntaks_indeks = (syntaks_indeks + 1);
        }
        nl_list_text_push(resultater, "status\tklar");
        nl_list_text_push(resultater, nl_concat("symbol_importer\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_importer(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symbol_lokale\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_lokale(symbol_indeks))));
        return resultater;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace_med_filer(char * rot, nl_list_text* filer, int symbol_antall) {
        nl_list_text* resultater = nl_list_text_new();
        nl_list_text* symbol_indeks = studio_v2_symbol__studio_v2_symbol_indeks_fra_filer(filer);
        nl_list_text* symbol_sammendrag = studio_v2_symbol__studio_v2_symbol_workspace_sammendrag(rot);
        nl_list_text* syntaks = studio_v2_diagnostics__studio_v2_diagnostics_syntaks_fra_workspace(rot);
        char * aktiv_fil = studio_v2_studio_state__studio_v2_state_aktiv_fil(rot);
        nl_list_text_push(resultater, nl_concat("workspace\tNorscode Studio v2\t", rot));
        nl_list_text_push(resultater, nl_concat("aktivitetsfil\t", aktiv_fil));
        nl_list_text_push(resultater, nl_concat("åpne_filer\t", nl_int_to_text(nl_list_text_len(studio_v2_studio_state__studio_v2_state_apne_filer(rot, aktiv_fil)))));
        nl_list_text_push(resultater, nl_concat("workspace_filer\t", nl_int_to_text(nl_list_text_len(filer))));
        nl_list_text_push(resultater, nl_concat("workspace_sammendrag\t", nl_int_to_text(nl_list_text_len(symbol_sammendrag))));
        nl_list_text_push(resultater, nl_concat("syntax_errors\t", nl_int_to_text(nl_list_text_len(syntaks))));
        nl_list_text_push(resultater, nl_concat("syntax_errors_fatal\t", nl_int_to_text(studio_v2_diagnostics__studio_v2_diagnostics_antall_fatal(syntaks))));
        nl_list_text_push(resultater, nl_concat("syntax_errors_gjenvinnbare\t", nl_int_to_text(studio_v2_diagnostics__studio_v2_diagnostics_antall_gjenvinnbare(syntaks))));
        nl_list_text_push(resultater, nl_concat("symbol_definisjoner\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_definisjoner(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symbol_bruk\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_bruk(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symboler\t", nl_int_to_text(symbol_antall)));
        int sammendrag_indeks = 0;
        while ((sammendrag_indeks < nl_list_text_len(symbol_sammendrag)) && (sammendrag_indeks < 4)) {
            nl_list_text_push(resultater, symbol_sammendrag->data[sammendrag_indeks]);
            sammendrag_indeks = (sammendrag_indeks + 1);
        }
        int syntaks_indeks = 0;
        while ((syntaks_indeks < nl_list_text_len(syntaks)) && (syntaks_indeks < 3)) {
            nl_list_text_push(resultater, syntaks->data[syntaks_indeks]);
            syntaks_indeks = (syntaks_indeks + 1);
        }
        nl_list_text_push(resultater, "status\tklar");
        nl_list_text_push(resultater, nl_concat("symbol_importer\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_importer(symbol_indeks))));
        nl_list_text_push(resultater, nl_concat("symbol_lokale\t", nl_int_to_text(studio_v2_symbol__studio_v2_symbol_indeks_antall_lokale(symbol_indeks))));
        return resultater;
        return nl_list_text_new();
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_status(char * rot) {
        return "klar";
        return "";
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_oppdater(char * rot) {
        nl_list_text* resultater = studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace(rot);
        nl_list_text_push(resultater, "oppdatering\tinkrementell");
        return resultater;
        return nl_list_text_new();
    }
    
    nl_list_text* studio_v2_diagnostics__studio_v2_diagnostics_oppdater_med_filer(char * rot, nl_list_text* filer, int symbol_antall) {
        nl_list_text* resultater = studio_v2_diagnostics__studio_v2_diagnostics_fra_workspace_med_filer(rot, filer, symbol_antall);
        nl_list_text_push(resultater, "oppdatering\tinkrementell");
        return resultater;
        return nl_list_text_new();
    }
    
    char * studio_v2_diagnostics__studio_v2_diagnostics_oppdater_status(char * rot) {
        return "oppdatert";
        return "";
    }
    
    int start() {
        nl_print_text("Studio v2 foundation-test er klar");
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