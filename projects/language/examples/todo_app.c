#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

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

typedef struct { int kind; int parent; char *text; int visible; char *click_callback; char *change_callback; } nl_gui_object;
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
    nl_gui_objects[nl_gui_count].click_callback = NULL;
    nl_gui_objects[nl_gui_count].change_callback = NULL;
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

static int nl_gui_tekst(int parent, const char *text) {
    return nl_gui_create(3, parent, text);
}

static int nl_gui_tekstboks(int parent, const char *initial) {
    return nl_gui_create(4, parent, initial);
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
    return id;
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

static int nl_gui_trykk(int id) {
    nl_gui_object *obj = nl_gui_get(id);
    if (!obj) { return 0; }
    if (obj->click_callback && obj->click_callback[0]) { return nl_call_callback(obj->click_callback, id); }
    return id;
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

int std_gui__vindu(char * tittel) {
    return nl_gui_vindu(tittel);
    return 0;
}

int std_gui__panel(int foresatt) {
    return nl_gui_panel(foresatt);
    return 0;
}

int std_gui__tekst(int foresatt, char * tekstverdi) {
    return nl_gui_tekst(foresatt, tekstverdi);
    return 0;
}

int std_gui__tekstboks(int foresatt, char * starttekst) {
    return nl_gui_tekstboks(foresatt, starttekst);
    return 0;
}

int std_gui__liste(int foresatt) {
    return nl_gui_liste(foresatt);
    return 0;
}

int std_gui__liste_legg_til(int liste_id, char * tekstverdi) {
    return nl_gui_liste_legg_til(liste_id, tekstverdi);
    return 0;
}

int std_gui__liste_tom(int liste_id) {
    return nl_gui_liste_tom(liste_id);
    return 0;
}

int std_gui__p__klikk(int widget_id, char * funksjonsnavn) {
    return nl_gui_pa_klikk(widget_id, funksjonsnavn);
    return 0;
}

int std_gui__p__endring(int widget_id, char * funksjonsnavn) {
    return nl_gui_pa_endring(widget_id, funksjonsnavn);
    return 0;
}

int std_gui__trykk(int widget_id) {
    return nl_gui_trykk(widget_id);
    return 0;
}

int std_gui__foresatt(int widget_id) {
    return nl_gui_foresatt(widget_id);
    return 0;
}

int std_gui__barn(int widget_id, int indeks) {
    return nl_gui_barn(widget_id, indeks);
    return 0;
}

int std_gui__knapp(int foresatt, char * tekstverdi) {
    return nl_gui_knapp(foresatt, tekstverdi);
    return 0;
}

int std_gui__etikett(int foresatt, char * tekstverdi) {
    return nl_gui_etikett(foresatt, tekstverdi);
    return 0;
}

int std_gui__tekstfelt(int foresatt, char * starttekst) {
    return nl_gui_tekstfelt(foresatt, starttekst);
    return 0;
}

int std_gui__sett_tekst(int widget_id, char * tekstverdi) {
    return nl_gui_sett_tekst(widget_id, tekstverdi);
    return 0;
}

char * std_gui__hent_tekst(int widget_id) {
    return nl_gui_hent_tekst(widget_id);
    return "";
}

int std_gui__vis(int vindu_id) {
    return nl_gui_vis(vindu_id);
    return 0;
}

int std_gui__lukk(int vindu_id) {
    return nl_gui_lukk(vindu_id);
    return 0;
}

int legg_til_punkt(int knapp_id) {
    int panel_id = std_gui__foresatt(knapp_id);
    int input_id = std_gui__barn(panel_id, 1);
    int liste_id = std_gui__barn(panel_id, 3);
    int status_id = std_gui__barn(panel_id, 4);
    char * tekstverdi = std_gui__hent_tekst(input_id);
    if (!(nl_streq(tekstverdi, ""))) {
        std_gui__liste_legg_til(liste_id, tekstverdi);
        std_gui__sett_tekst(input_id, "");
        std_gui__sett_tekst(status_id, "Punkt lagt til");
    }
    else {
        std_gui__sett_tekst(status_id, "Skriv noe først");
    }
    return knapp_id;
    return 0;
}

int oppdater_status(int widget_id) {
    int panel_id = std_gui__foresatt(widget_id);
    int status_id = std_gui__barn(panel_id, 4);
    char * tekstverdi = std_gui__hent_tekst(widget_id);
    if (!(nl_streq(tekstverdi, ""))) {
        std_gui__sett_tekst(status_id, nl_concat("Skriver: ", tekstverdi));
    }
    else {
        std_gui__sett_tekst(status_id, "Tomt felt");
    }
    return widget_id;
    return 0;
}

int start() {
    int vindu_id = std_gui__vindu("Norscode Todo");
    int panel_id = std_gui__panel(vindu_id);
    int tittel_id = std_gui__tekst(panel_id, "Norscode Todo");
    int input_id = std_gui__tekstboks(panel_id, "");
    int knapp_id = std_gui__knapp(panel_id, "Legg til");
    int liste_id = std_gui__liste(panel_id);
    int status_id = std_gui__tekst(panel_id, "Klar");
    std_gui__p__klikk(knapp_id, "legg_til_punkt");
    std_gui__p__endring(input_id, "oppdater_status");
    std_gui__trykk(knapp_id);
    std_gui__sett_tekst(input_id, "Kjøp melk");
    std_gui__trykk(knapp_id);
    std_gui__vis(vindu_id);
    nl_print_text(nl_int_to_text(vindu_id));
    nl_print_text(nl_int_to_text(panel_id));
    nl_print_text(nl_int_to_text(tittel_id));
    nl_print_text(nl_int_to_text(input_id));
    nl_print_text(nl_int_to_text(knapp_id));
    nl_print_text(nl_int_to_text(liste_id));
    nl_print_text(std_gui__hent_tekst(status_id));
    return 0;
    return 0;
}

static int nl_call_callback(const char *name, int widget_id) {
    if (!name) { return widget_id; }
    if (nl_streq(name, "panel") || nl_streq(name, "std.gui.panel")) {
        return std_gui__panel(widget_id);
    }
    if (nl_streq(name, "liste") || nl_streq(name, "std.gui.liste")) {
        return std_gui__liste(widget_id);
    }
    if (nl_streq(name, "liste_tom") || nl_streq(name, "std.gui.liste_tom")) {
        return std_gui__liste_tom(widget_id);
    }
    if (nl_streq(name, "trykk") || nl_streq(name, "std.gui.trykk")) {
        return std_gui__trykk(widget_id);
    }
    if (nl_streq(name, "foresatt") || nl_streq(name, "std.gui.foresatt")) {
        return std_gui__foresatt(widget_id);
    }
    if (nl_streq(name, "vis") || nl_streq(name, "std.gui.vis")) {
        return std_gui__vis(widget_id);
    }
    if (nl_streq(name, "lukk") || nl_streq(name, "std.gui.lukk")) {
        return std_gui__lukk(widget_id);
    }
    if (nl_streq(name, "legg_til_punkt") || nl_streq(name, "legg_til_punkt")) {
        return legg_til_punkt(widget_id);
    }
    if (nl_streq(name, "oppdater_status") || nl_streq(name, "oppdater_status")) {
        return oppdater_status(widget_id);
    }
    return widget_id;
}

int main(void) {
    return start();
}