#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int lengde; int kapasitet; int *data; } ListeHeiltall;
typedef struct { int lengde; int kapasitet; char **data; } ListeTekst;

static void nl_fail(const char *msg) { fprintf(stderr, "%s\n", msg); exit(1); }
static int sjekk_indeks(int idx, int lengde) { if (idx < 0 || idx >= lengde) nl_fail("Indeks utenfor område"); return idx; }
static void skriv_heltall(int x) { printf("%d\n", x); }
static void skriv_bool(int x) { printf("%s\n", x ? "sann" : "usann"); }
static void skriv_tekst(const char *s) { printf("%s\n", s); }
static char *nl_strdup(const char *s) { size_t len = strlen(s); char *out = (char *)malloc(len + 1); if (!out) nl_fail("Minnefeil"); memcpy(out, s, len + 1); return out; }
static char *tekst_pluss(const char *a, const char *b) { size_t la = strlen(a), lb = strlen(b); char *out = (char *)malloc(la + lb + 1); if (!out) nl_fail("Minnefeil"); memcpy(out, a, la); memcpy(out + la, b, lb + 1); return out; }
static char *tekst_fra_heltall_builtin(int x) { char buffer[64]; snprintf(buffer, sizeof(buffer), "%d", x); return nl_strdup(buffer); }
static char *tekst_fra_bool_builtin(int x) { return nl_strdup(x ? "sann" : "usann"); }
static char *les_input_builtin(const char *prompt) { char buffer[1024]; printf("%s", prompt); if (!fgets(buffer, sizeof(buffer), stdin)) return nl_strdup(""); buffer[strcspn(buffer, "\n")] = 0; return nl_strdup(buffer); }
static ListeHeiltall lag_liste_heltall(int antall, int *verdier) { ListeHeiltall l; l.lengde = antall; l.kapasitet = antall > 0 ? antall : 1; l.data = (int *)malloc(sizeof(int) * l.kapasitet); if (!l.data) nl_fail("Minnefeil"); for (int i = 0; i < antall; i++) l.data[i] = verdier ? verdier[i] : 0; return l; }
static ListeTekst lag_liste_tekst(int antall, char **verdier) { ListeTekst l; l.lengde = antall; l.kapasitet = antall > 0 ? antall : 1; l.data = (char **)malloc(sizeof(char*) * l.kapasitet); if (!l.data) nl_fail("Minnefeil"); for (int i = 0; i < antall; i++) l.data[i] = verdier ? verdier[i] : nl_strdup(""); return l; }
static void reserve_heltall(ListeHeiltall *l) { if (l->lengde < l->kapasitet) return; l->kapasitet *= 2; l->data = (int *)realloc(l->data, sizeof(int) * l->kapasitet); if (!l->data) nl_fail("Minnefeil"); }
static void reserve_tekst(ListeTekst *l) { if (l->lengde < l->kapasitet) return; l->kapasitet *= 2; l->data = (char **)realloc(l->data, sizeof(char*) * l->kapasitet); if (!l->data) nl_fail("Minnefeil"); }
static void legg_til_heltall_builtin(ListeHeiltall *l, int verdi) { reserve_heltall(l); l->data[l->lengde++] = verdi; }
static void legg_til_tekst_builtin(ListeTekst *l, char *verdi) { reserve_tekst(l); l->data[l->lengde++] = verdi; }
static int pop_siste_heltall_builtin(ListeHeiltall *l) { if (l->lengde <= 0) nl_fail("Kan ikke poppe fra tom liste"); return l->data[--l->lengde]; }
static char *pop_siste_tekst_builtin(ListeTekst *l) { if (l->lengde <= 0) nl_fail("Kan ikke poppe fra tom liste"); return l->data[--l->lengde]; }
static void fjern_indeks_heltall_builtin(ListeHeiltall *l, int indeks) { sjekk_indeks(indeks, l->lengde); for (int i = indeks; i < l->lengde - 1; i++) l->data[i] = l->data[i + 1]; l->lengde--; }
static void fjern_indeks_tekst_builtin(ListeTekst *l, int indeks) { sjekk_indeks(indeks, l->lengde); for (int i = indeks; i < l->lengde - 1; i++) l->data[i] = l->data[i + 1]; l->lengde--; }
static void sett_inn_heltall_builtin(ListeHeiltall *l, int indeks, int verdi) { if (indeks < 0 || indeks > l->lengde) nl_fail("Indeks utenfor område"); reserve_heltall(l); for (int i = l->lengde; i > indeks; i--) l->data[i] = l->data[i - 1]; l->data[indeks] = verdi; l->lengde++; }
static void sett_inn_tekst_builtin(ListeTekst *l, int indeks, char *verdi) { if (indeks < 0 || indeks > l->lengde) nl_fail("Indeks utenfor område"); reserve_tekst(l); for (int i = l->lengde; i > indeks; i--) l->data[i] = l->data[i - 1]; l->data[indeks] = verdi; l->lengde++; }

/* modul: math */
int math__pluss(int a, int b);
/* modul: math */
int math__minus(int a, int b);
/* modul: math */
int math__gange(int a, int b);
/* modul: math */
int math__del(int a, int b);
/* modul: math */
int math__maks(int a, int b);
/* modul: math */
int math__min(int a, int b);
/* modul: math */
int math__absolutt(int x);
/* modul: tekstmodul */
char * tekstmodul__hilsen(char * navn);
/* modul: tekstmodul */
char * tekstmodul__rop(char * tekstverdi);
/* modul: tekstmodul */
char * tekstmodul__omgitt_av_klammer(char * tekstverdi);
/* modul: tekstmodul */
char * tekstmodul__ja_nei(int verdi);
/* modul: tekstmodul */
char * tekstmodul__tall_til_tekst(int verdi);
/* modul: tekstmodul */
char * tekstmodul__bool_til_tekst(int verdi);
/* modul: listemodul */
int listemodul__legg_til_tall(ListeHeiltall *liste, int verdi);
/* modul: listemodul */
int listemodul__legg_til_tekst(ListeTekst *liste, char * verdi);
/* modul: listemodul */
int listemodul__siste_tall(ListeHeiltall *liste);
/* modul: listemodul */
char * listemodul__siste_tekst(ListeTekst *liste);
/* modul: listemodul */
int listemodul__antall_tall(ListeHeiltall liste);
/* modul: listemodul */
int listemodul__antall_tekst(ListeTekst liste);
int start();

int math__pluss(int a, int b) {
    return (a + b);
}

int math__minus(int a, int b) {
    return (a - b);
}

int math__gange(int a, int b) {
    return (a * b);
}

int math__del(int a, int b) {
    int resultat = 0;
    if ((b == 0)) {
        resultat = 0;
    }
    else {
        resultat = (a / b);
    }
    return resultat;
}

int math__maks(int a, int b) {
    int resultat = a;
    if ((a > b)) {
        resultat = a;
    }
    else {
        resultat = b;
    }
    return resultat;
}

int math__min(int a, int b) {
    int resultat = a;
    if ((a < b)) {
        resultat = a;
    }
    else {
        resultat = b;
    }
    return resultat;
}

int math__absolutt(int x) {
    int resultat = x;
    if ((x < 0)) {
        resultat = (-x);
    }
    else {
        resultat = x;
    }
    return resultat;
}

char * tekstmodul__hilsen(char * navn) {
    return tekst_pluss(nl_strdup("Hei "), navn);
}

char * tekstmodul__rop(char * tekstverdi) {
    return tekst_pluss(tekstverdi, nl_strdup("!"));
}

char * tekstmodul__omgitt_av_klammer(char * tekstverdi) {
    return tekst_pluss(tekst_pluss(nl_strdup("["), tekstverdi), nl_strdup("]"));
}

char * tekstmodul__ja_nei(int verdi) {
    char * resultat = nl_strdup("");
    if (verdi) {
        resultat = nl_strdup("ja");
    }
    else {
        resultat = nl_strdup("nei");
    }
    return resultat;
}

char * tekstmodul__tall_til_tekst(int verdi) {
    return tekst_fra_heltall_builtin(verdi);
}

char * tekstmodul__bool_til_tekst(int verdi) {
    return tekst_fra_bool_builtin(verdi);
}

int listemodul__legg_til_tall(ListeHeiltall *liste, int verdi) {
    return (legg_til_heltall_builtin(liste, verdi), 0);
}

int listemodul__legg_til_tekst(ListeTekst *liste, char * verdi) {
    return (legg_til_tekst_builtin(liste, verdi), 0);
}

int listemodul__siste_tall(ListeHeiltall *liste) {
    return pop_siste_heltall_builtin(liste);
}

char * listemodul__siste_tekst(ListeTekst *liste) {
    return pop_siste_tekst_builtin(liste);
}

int listemodul__antall_tall(ListeHeiltall liste) {
    return liste.lengde;
}

int listemodul__antall_tekst(ListeTekst liste) {
    return liste.lengde;
}

int start() {
    int sum = math__pluss(10, 20);
    int diff = math__minus(50, 8);
    char * melding = tekstmodul__hilsen(nl_strdup("Jan"));
    ListeHeiltall tall = lag_liste_heltall(3, (int[]){1, 2, 3});
    ListeTekst ord = lag_liste_tekst(3, (char*[]){nl_strdup("hei"), nl_strdup("på"), nl_strdup("deg")});
    listemodul__legg_til_tall(&tall, 99);
    listemodul__legg_til_tekst(&ord, nl_strdup("nå"));
    skriv_tekst(nl_strdup("Sum:"));
    skriv_tekst(tekst_fra_heltall_builtin(sum));
    skriv_tekst(nl_strdup("Minus:"));
    skriv_tekst(tekst_fra_heltall_builtin(diff));
    skriv_tekst(nl_strdup("Melding:"));
    skriv_tekst(tekstmodul__rop(melding));
    skriv_tekst(nl_strdup("Antall tall:"));
    skriv_tekst(tekst_fra_heltall_builtin(listemodul__antall_tall(tall)));
    skriv_tekst(nl_strdup("Antall ord:"));
    skriv_tekst(tekst_fra_heltall_builtin(listemodul__antall_tekst(ord)));
    return 0;
}

int main(void) {
    return start();
}