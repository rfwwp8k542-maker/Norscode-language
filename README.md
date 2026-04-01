

# NorskLang 🚀

Et norsk programmeringsspråk som kompilerer til C.

## ✨ Funksjoner

- Norsk syntaks (funksjon, hvis, ellers, osv.)
- Statisk typing (heltall, tekst, bool, lister)
- Modul- og pakke-system
- Egen standardbibliotek (`std`)
- Testsystem med `assert`, `assert_eq`, `assert_ne`
- Kompilerer til C → rask kjøring

---

## 📦 Kom i gang

### 0. Installer CLI

```bash
python3 -m pip install -e .
# Hvis miljøet er offline/strengt:
python3 -m pip install -e . --no-build-isolation

# Deretter kan du bruke:
nl --help
norsklang --help
```

### 0b. Bygg og publiser pakke

```bash
# Bygg distributerbare filer lokalt
python3 -m pip install build twine
pyproject-build
python3 -m twine check dist/*

# Forbered ny release lokalt (oppdaterer pyproject + CHANGELOG)
python3 main.py release --bump patch

# Se hva som ville skjedd uten å skrive filer
python3 main.py release --bump minor --dry-run --json
```

Publisering er satt opp i GitHub Actions via `.github/workflows/publish.yml`:

- Push tag `vX.Y.Z` for å trigge build + publisering til PyPI
- Workflowen bruker Trusted Publisher (`id-token`) for opplasting

### 1. Kjør program

```bash
python3 main.py run app.no
```

### 2. Sjekk kode

```bash
python3 main.py check app.no
```

### 3. Kjør tester

```bash
python3 main.py test

# Maskinlesbar testoutput
python3 main.py test --json
```

### 4. IR disasm (debug/tooling)

```bash
# Generer IR disassembly fra tekstfil
python3 main.py ir-disasm path/to/program.nlir

# Streng validering av opcodes/argumenter
python3 main.py ir-disasm path/to/program.nlir --strict

# Sammenlign python- og selfhost-motor
python3 main.py ir-disasm path/to/program.nlir --diff

# Feil hvis strict-resultat avviker mellom motorene
python3 main.py ir-disasm path/to/program.nlir --diff --fail-on-warning

# Lagre diff til fil (for CI artifacts)
python3 main.py ir-disasm path/to/program.nlir --diff --save-diff /tmp/ir.diff

# JSON-output (for scripts/CI)
python3 main.py ir-disasm path/to/program.nlir --json
```

### 5. Pakker (`nl add`)

```bash
# Se registry-pakker
python3 main.py add --list

# Legg til lokal pakke fra ./packages/<navn>
python3 main.py add butikk

# Legg til innebygde standardpakker fra registry
python3 main.py add std_math
python3 main.py add std_tekst
python3 main.py add std_liste
python3 main.py add std_io

# Samme via launcher
python3 nl add butikk

# Legg til pakke fra vilkårlig sti
python3 main.py add ./packages/butikk

# Egendefinert dependency-navn
python3 main.py add ./packages/butikk --name butikk_local

# Direkte Git-kilde
python3 main.py add minpakke --git https://github.com/org/repo.git --ref v1.2.0

# Direkte URL-kilde
python3 main.py add minpakke --url https://example.com/mypkg-1.2.0.tar.gz

# Last ned/cach ekstern kilde til lokal mappe og skriv sti i dependencies
python3 main.py add demo_git --fetch
python3 main.py add minpakke --url https://example.com/mypkg-1.2.0.tar.gz --fetch

# Tving ny nedlasting av cache
python3 main.py add demo_git --fetch --refresh

# Krev låst git-ref ved add
python3 main.py add minpakke --git https://github.com/org/repo.git --ref v1.2.0 --pin

# Verifiser URL-arkiv med SHA256 ved fetch
python3 main.py add minpakke --url https://example.com/mypkg-1.2.0.tar.gz --fetch --sha256 <sha256>

# Overstyr trusted host-policy for én kommando
python3 main.py add minpakke --url https://ukjent.example/pkg.tar.gz --allow-untrusted
```

Registry kan defineres i `packages/registry.toml`:

```toml
[packages]
butikk = "./butikk"

[registry.packages.eksempel]
path = "./butikk"
description = "Eksempeloppføring"

[registry.packages.demo_git]
git = "https://github.com/org/repo.git"
ref = "v1.2.0"
description = "Hent pakke fra Git"

[registry.packages.demo_url]
url = "https://example.com/mypkg-1.2.0.tar.gz"
description = "Hent pakke fra URL"
```

Trusted host-policy kan settes i `norsklang.toml`:

```toml
[security]
trusted_git_hosts = ["github.com", "*.github.com"]
trusted_url_hosts = ["example.com"]
```

For integritets-pinning av registry metadata:

```bash
# Beregn SHA256 for packages/registry.toml
python3 main.py registry-sign

# Skriv SHA256 inn i norsklang.toml (security.trusted_registry_sha256)
python3 main.py registry-sign --write-config
```

Remote registry-indeks kan konfigureres i `norsklang.toml`:

```toml
[registry]
sources = ["packages/remote_registry_example.json"]
```

Synkroniser indeks til lokal cache:

```bash
python3 main.py registry-sync
python3 main.py registry-sync --json

# Feil hvis en source feiler
python3 main.py registry-sync --require-all

# Tillat delvis sync og fallback til gammel cache
python3 main.py registry-sync
```

Bygg distribuerbar speilfil:

```bash
python3 main.py registry-mirror
python3 main.py registry-mirror --output build/registry_mirror.json
```

Cache for eksterne pakker lagres under `.norsklang/cache/`.
Modul-loaderen leser `[dependencies]` i `norsklang.toml` automatisk ved `bruk ...`.
Modul-loaderen bruker også en in-memory parse-cache per fil (med mtime/size-sjekk) for raskere test/bygg-kjøringer.

### 5b. Lockfile

```bash
# Generer/oppdater lockfile
python3 main.py lock

# CI-sjekk: feiler hvis lockfile mangler/er utdatert
python3 main.py lock --check

# Verifiser lockfile mot faktiske path-digests
python3 main.py lock --verify
```

### 5c. Oppgrader dependencies

```bash
# Oppdater alle dependencies som finnes i registry
python3 main.py update

# Oppdater én dependency
python3 main.py update butikk

# Check-modus: feiler hvis noe ville blitt oppdatert
python3 main.py update --check

# Oppdater + regenerer lockfile
python3 main.py update --lock

# Overstyr trusted host-policy for én oppdateringskjøring
python3 main.py update --allow-untrusted
```

### 6. Debug tools

```bash
# Kort symbol-oversikt (default)
python3 main.py debug app.no

# Vis tokens
python3 main.py debug app.no --tokens

# Vis AST + symboler som JSON
python3 main.py debug app.no --ast --symbols --json
```

### 7. Snapshot-oppsett (CI)

```bash
# Oppdater strict snapshot-forventninger
python3 main.py update-snapshots

# CI-sjekk: feiler hvis snapshots er utdaterte
python3 main.py update-snapshots --check
```

### 8. CI-eksempel (GitHub Actions)

```yaml
name: ci
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Snapshot check
        run: python3 main.py update-snapshots --check
      - name: Engine parity check
        run: python3 main.py ir-disasm tests/ir_sample.nlir --diff --fail-on-warning
      - name: Full test
        run: python3 main.py test
```

Lokal kjøring av samme sekvens:

```bash
python3 main.py ci

# Maskinlesbar output
python3 main.py ci --json
```

---

## 🧠 Eksempel

```no
bruk std.math
bruk std.tekst som t

funksjon start() -> heltall {
    la sum: heltall = math.pluss(10, 20)

    skriv(tekst_fra_heltall(sum))
    skriv(t.hilsen("Jan"))

    returner 0
}
```

---

## 🧪 Testing

```no
funksjon start() -> heltall {
    assert_eq(2 + 2, 4)
    assert_ne(5, 6)
    returner 0
}
```

---

## 📁 Struktur

```
norsklang/
├── main.py
├── compiler/
├── std/
├── tests/
├── app.no
└── norsklang.toml
```

---

## 🔥 Status

Dette prosjektet er under aktiv utvikling.

### Selv-hosting (nytt)

Vi har startet en tidlig selv-hosting bane i `selfhost/`:

- `selfhost/compiler.no` er en compiler skrevet i NorskLang
- Første steg kompilerer et lite instruksjonssett (IR/bytecode) til C
- Dette brukes som bootstrap før full lexer/parser i NorskLang

Neste steg:

- Utvide selv-hosting til full parser (påbegynt: uttrykksparser + mini-skriptparser med `la`/`sett`/`returner`, compound assignment (`+=`, `-=`, `*=`, `/=`, `%=`), nestede `hvis ... da ... ellers ...` (uttrykk + assignment), tomme statements (`;`) og norske operator-ord (`og/eller/ikke`, `er/ikke_er`, `mindre_enn`/`storre_enn`) inkludert fraser med mellomrom (`mindre enn`, `ikke er`, `er ikke`, `er lik`, `ikke lik`, `ulik`, `er ulik`, `er ikke lik`, `er mindre enn`, `er storre enn`, `er mindre eller lik`, `er storre eller lik`) i `selfhost/compiler.no`)
- Selv-hosting lexer/token-strøm med bedre syntaksfeil og posisjonsinfo (utvidet: mini-skriptparser-feil + uttrykksparser-feil + `hvis`-parser-feil inkluderer token-posisjon)

---

## 👨‍💻 Laget av

Jan Steinar Sætre
