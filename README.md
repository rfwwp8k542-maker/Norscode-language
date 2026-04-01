

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

### 5. Snapshot-oppsett (CI)

```bash
# Oppdater strict snapshot-forventninger
python3 main.py update-snapshots

# CI-sjekk: feiler hvis snapshots er utdaterte
python3 main.py update-snapshots --check
```

### 6. CI-eksempel (GitHub Actions)

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

- Pakke-system (`nl add`)
- Bedre test-output
- Debug tools
- Installer (`pip install norsklang`)

---

## 👨‍💻 Laget av

Jan Steinar Sætre
