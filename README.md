

# NorCode 🚀

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
nor --help
nc --help
nl --help
norcode --help
# Legacy alias fungerer fortsatt:
norsklang --help

# Modul-kjøring:
python3 -m norcode --help
python3 -m norsklang --help

# Merk:
# Legacy-aliasene `norsklang` og `python3 -m norsklang` viser et kort varsel
# og videresender til NorCode-CLI.
# Ved bruk av legacy-filer (`norsklang.toml`, `norsklang.lock`, `.norsklang/`)
# vises også et kort migreringsvarsel.

# Planlegg navnemigrering (dry-run):
norcode migrate-names

# Utfør navnemigrering:
norcode migrate-names --apply

# Utfør migrering og rydd bort legacy-filer:
norcode migrate-names --apply --cleanup

# Sikkerhet:
# --cleanup fjerner bare legacy-ressurser når innholdet matcher NorCode-ressursen.

# CI-sjekk: feiler hvis migrering/cleanup gjenstår
norcode migrate-names --cleanup --check
```

### 0b. Bygg og publiser pakke

```bash
# Bygg distributerbare filer lokalt
python3 -m pip install build twine
pyproject-build
python3 -m twine check dist/*

# Forbered ny release lokalt (oppdaterer pyproject + CHANGELOG)
norcode release --bump patch

# Se hva som ville skjedd uten å skrive filer
norcode release --bump minor --dry-run --json
```

Publisering er satt opp i GitHub Actions via `.github/workflows/publish.yml`:

- Push tag `vX.Y.Z` for å trigge build + publisering til PyPI
- Workflowen bruker Trusted Publisher (`id-token`) for opplasting

### 1. Kjør program

```bash
norcode run app.no
```

### 2. Sjekk kode

```bash
norcode check app.no
```

### 3. Kjør tester

```bash
norcode test

# Maskinlesbar testoutput
norcode test --json
```

### 4. IR disasm (debug/tooling)

```bash
# Generer IR disassembly fra tekstfil
norcode ir-disasm path/to/program.nlir

# Streng validering av opcodes/argumenter
norcode ir-disasm path/to/program.nlir --strict

# Sammenlign python- og selfhost-motor
norcode ir-disasm path/to/program.nlir --diff

# Feil hvis strict-resultat avviker mellom motorene
norcode ir-disasm path/to/program.nlir --diff --fail-on-warning

# Lagre diff til fil (for CI artifacts)
norcode ir-disasm path/to/program.nlir --diff --save-diff /tmp/ir.diff

# JSON-output (for scripts/CI)
norcode ir-disasm path/to/program.nlir --json
```

### 5. Pakker (`nl add`)

```bash
# Se registry-pakker
norcode add --list

# Legg til lokal pakke fra ./packages/<navn>
norcode add butikk

# Legg til innebygde standardpakker fra registry
norcode add std_math
norcode add std_tekst
norcode add std_liste
norcode add std_io

# Samme via modul-kjøring
python3 -m norcode add butikk

# Legg til pakke fra vilkårlig sti
norcode add ./packages/butikk

# Egendefinert dependency-navn
norcode add ./packages/butikk --name butikk_local

# Direkte Git-kilde
norcode add minpakke --git https://github.com/org/repo.git --ref v1.2.0

# Direkte URL-kilde
norcode add minpakke --url https://example.com/mypkg-1.2.0.tar.gz

# Last ned/cach ekstern kilde til lokal mappe og skriv sti i dependencies
norcode add demo_git --fetch
norcode add minpakke --url https://example.com/mypkg-1.2.0.tar.gz --fetch

# Tving ny nedlasting av cache
norcode add demo_git --fetch --refresh

# Krev låst git-ref ved add
norcode add minpakke --git https://github.com/org/repo.git --ref v1.2.0 --pin

# Verifiser URL-arkiv med SHA256 ved fetch
norcode add minpakke --url https://example.com/mypkg-1.2.0.tar.gz --fetch --sha256 <sha256>

# Overstyr trusted host-policy for én kommando
norcode add minpakke --url https://ukjent.example/pkg.tar.gz --allow-untrusted
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

Trusted host-policy kan settes i `norcode.toml`:

```toml
[security]
trusted_git_hosts = ["github.com", "*.github.com"]
trusted_url_hosts = ["example.com"]
```

For integritets-pinning av registry metadata:

```bash
# Beregn SHA256 for packages/registry.toml
norcode registry-sign

# Skriv SHA256 inn i norcode.toml (security.trusted_registry_sha256)
norcode registry-sign --write-config
```

Remote registry-indeks kan konfigureres i `norcode.toml`:

```toml
[registry]
sources = ["packages/remote_registry_example.json"]
```

Synkroniser indeks til lokal cache:

```bash
norcode registry-sync
norcode registry-sync --json

# Feil hvis en source feiler
norcode registry-sync --require-all

# Tillat delvis sync og fallback til gammel cache
norcode registry-sync
```

Bygg distribuerbar speilfil:

```bash
norcode registry-mirror
norcode registry-mirror --output build/registry_mirror.json
```

Cache for eksterne pakker lagres under `.norcode/cache/`.
Modul-loaderen leser `[dependencies]` i `norcode.toml` automatisk ved `bruk ...`.
Modul-loaderen bruker også en in-memory parse-cache per fil (med mtime/size-sjekk) for raskere test/bygg-kjøringer.

### 5b. Lockfile

```bash
# Generer/oppdater lockfile
norcode lock

# CI-sjekk: feiler hvis lockfile mangler/er utdatert
norcode lock --check

# Verifiser lockfile mot faktiske path-digests
norcode lock --verify
```

### 5c. Oppgrader dependencies

```bash
# Oppdater alle dependencies som finnes i registry
norcode update

# Oppdater én dependency
norcode update butikk

# Check-modus: feiler hvis noe ville blitt oppdatert
norcode update --check

# Oppdater + regenerer lockfile
norcode update --lock

# Overstyr trusted host-policy for én oppdateringskjøring
norcode update --allow-untrusted
```

### 6. Debug tools

```bash
# Kort symbol-oversikt (default)
norcode debug app.no

# Vis tokens
norcode debug app.no --tokens

# Vis AST + symboler som JSON
norcode debug app.no --ast --symbols --json
```

### 7. Snapshot-oppsett (CI)

```bash
# Oppdater strict snapshot-forventninger
norcode update-snapshots

# CI-sjekk: feiler hvis snapshots er utdaterte
norcode update-snapshots --check
```

### 8. CI-eksempel (GitHub Actions)

```yaml
name: ci
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    env:
      FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Run NorCode CI checks
        run: python3 -m norcode ci --check-names
```

Lokal kjøring av samme sekvens:

```bash
python3 -m norcode ci

# Maskinlesbar output
python3 -m norcode ci --json
# Inkluderer workflow_action_check.issue_count for CI-policy funn
# Inkluderer også steps.total og steps.name_check_enabled
# Inkluderer workflow_action_check.policy med håndhevede regler
# Inkluderer timings_ms per CI-del (millisekunder)
# Inkluderer timings_s per CI-del (sekunder)
# Inkluderer timings_ms.total for total CI-varighet
# Inkluderer timings_ms.wallclock_total / timings_s.wallclock_total basert på epoch-tid
# Inkluderer timings_ms.step_sum / timings_s.step_sum (sum av delsteg)
# Inkluderer timings_ms.overhead / timings_s.overhead (total minus sum av delsteg)
# Inkluderer timings_ratio.step_coverage (andel av total tid brukt i målte delsteg)
# Inkluderer timings_ratio.overhead_share (andel av total tid brukt i overhead)
# Inkluderer timings_ratio.step_coverage_pct (samme andel i prosent)
# Inkluderer timings_ratio.overhead_share_pct (samme andel i prosent)
# Inkluderer timings_ratio.ratio_sum (kontrollsum for andeler, forventet ~1.0)
# Inkluderer timings_ratio.ratio_delta (absolutt avvik fra 1.0 etter avrunding)
# Inkluderer timings_ratio.percent_sum (kontrollsum i prosent, forventet ~100.0)
# Inkluderer timings_ratio.percent_delta (absolutt avvik fra 100.0 etter avrunding)
# Inkluderer timings_ratio.overhead_level (low/medium/high basert på overhead_share)
# Inkluderer timings_ratio.overhead_policy (terskler brukt for overhead_level)
# Inkluderer timings_ratio.overhead_within_medium (boolsk gate: overhead_share <= medium_max)
# Inkluderer started_at_utc og finished_at_utc for kjøringstidsstempel
# Inkluderer started_at_epoch_ms og finished_at_epoch_ms for numerisk sortering
# Inkluderer schema_version for stabil maskinlesbar kontrakt
# Inkluderer run_id (unik ID per CI-kjøring)
# Inkluderer toppnivå ok for samlet CI-status
# Inkluderer steps.order for eksplisitt sjekkrekkefølge
# Inkluderer workflow_action_check.file_extensions for skannegrunnlag
# Inkluderer workflow_action_check.scanned_dir for skannemappe
# Inkluderer invocation med brukte CI-flagg
# Inkluderer invocation.argv med faktisk argumentliste
# Inkluderer invocation.argv0 og invocation.raw for reproduksjon
# Inkluderer source_revision (git commit hash) når tilgjengelig
# Inkluderer source_revision_short (kort commit hash) når tilgjengelig
# Inkluderer source_branch (git branch) når tilgjengelig
# Inkluderer source_tag (eksakt git tag) når tilgjengelig
# Inkluderer source_ref (tag eller branch) for entydig kilde-referanse
# Inkluderer source_ref_type (tag/branch/unknown)
# Inkluderer source_remote (git origin URL) når tilgjengelig
# Inkluderer source_remote_protocol (https/ssh/unknown)
# Inkluderer source_remote_is_https / source_remote_is_ssh for enkel filtrering
# Inkluderer source_remote_host (f.eks. github.com) når tilgjengelig
# Inkluderer source_remote_provider (github/gitlab/bitbucket/unknown)
# Inkluderer source_remote_is_github / source_remote_is_gitlab / source_remote_is_bitbucket / source_remote_is_unknown for enkel host-filtrering
# Inkluderer source_repo_slug (f.eks. owner/repo) når tilgjengelig
# Inkluderer source_repo_owner og source_repo_name for enkel grouping
# Inkluderer source_repo_url (normalisert web-URL) når tilgjengelig
# Inkluderer source_branch_url og source_tag_url når tilgjengelig
# Inkluderer source_ref_url når remote og ref er kjent
# Inkluderer source_revision_url når remote og commit er kjent
# Inkluderer source_is_tagged (om commit har eksakt tag)
# Inkluderer source_is_main (om branch er main)
# Inkluderer source_dirty (om worktree har lokale endringer)
# Inkluderer source_clean (inverse av source_dirty når kjent)
# Inkluderer runtime (python_version, python_major_minor, python_api_version, python_hexversion, python_implementation, python_compiler, python_build, python_cache_tag, python_executable, python_prefix, python_base_prefix, python_is_venv, byteorder, locale, encoding, path_entries, path_separator, env_var_count, stdin_isatty, stdout_isatty, stderr_isatty, shell, term, virtual_env, virtual_env_name, is_ci, is_github_actions, github_actions_run_id, github_actions_run_number, github_actions_run_attempt, github_actions_workflow, github_actions_job, github_actions_ref, github_actions_sha, github_actions_actor, github_actions_event_name, os, arch, platform, hostname, user, uid, gid, pid, ppid, process_group_id, home, tmpdir, cwd, cwd_has_spaces, timezone) for miljøsporing

# Valgfri ekstra-sjekk for navnemigrering i CI
python3 -m norcode ci --check-names
```

Tolkning av `timings_ratio` (hurtigguide):

- `step_coverage` / `step_coverage_pct`: hvor mye av total CI-tid som er direkte målt i delsteg.
- `overhead_share` / `overhead_share_pct`: tid utenfor målte delsteg (oppstart, avrunding, osv.).
- `overhead_level`: grov klassifisering (`low`, `medium`, `high`) basert på policy i `overhead_policy`.
- `overhead_within_medium`: enkel boolsk gate for automasjon (`true` når overhead er innen medium-grensen).
- `ratio_sum` og `percent_sum` bør være nær `1.0` / `100.0`; `ratio_delta` og `percent_delta` viser avrundingsavvik.

Eksempel på `timings_ratio` i `ci --json`:

```json
{
  "step_coverage": 0.9884,
  "overhead_share": 0.0116,
  "step_coverage_pct": 98.84,
  "overhead_share_pct": 1.16,
  "ratio_sum": 1.0,
  "ratio_delta": 0.0,
  "percent_sum": 100.0,
  "percent_delta": 0.0,
  "overhead_policy": {
    "low_max": 0.02,
    "medium_max": 0.05,
    "unit": "share"
  },
  "overhead_level": "low",
  "overhead_within_medium": true
}
```

`norcode ci` kjører nå disse stegene:
1. Snapshot check
2. Engine parity check
3. Full test
4. Workflow action version check (stopper på deprecated action-versjoner og usikker Node opt-out)
5. Name migration check (kun med `--check-names`)

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
norcode/
├── main.py
├── compiler/
├── std/
├── tests/
├── app.no
└── norcode.toml
```

---

## 🔥 Status

Dette prosjektet er under aktiv utvikling.

### Selv-hosting (nytt)

Vi har startet en tidlig selv-hosting bane i `selfhost/`:

- `selfhost/compiler.no` er en compiler skrevet i NorCode
- Første steg kompilerer et lite instruksjonssett (IR/bytecode) til C
- Dette brukes som bootstrap før full lexer/parser i NorCode

Neste steg:

- Utvide selv-hosting til full parser (påbegynt: uttrykksparser + mini-skriptparser med `la`/`sett`/`returner` og aliasene `let`/`const`/`var`/`declare`/`set`/`assign`/`return`, compound assignment (`+=`, `-=`, `*=`, `/=`, `%=`), nestede `hvis ... da ... ellers ...` (uttrykk + assignment), `ellers_hvis`/`ellershvis`/`elif`/`elsif`-støtte, `if/then/else/elseif`-aliaser, `and/or/not`-aliaser, bool-aliaser `on/off`, `yes/no`, `enabled/disabled` og `active/inactive`, engelske sammenligningsaliaser (`is`, `eq`, `is_not`, `neq`, `equals`, `equal_to`, `not_equal_to`, `less_than`, `greater_than`, `less_equal`, `greater_equal`, `less_or_equal`, `greater_or_equal`) inkludert frasevarianter med mellomrom (`equal to`, `is equal to`, `not equal to`, `is not equal to`, `less than`, `is less than`, `greater than`, `is greater than`, `less or equal`, `less or equal to`, `is less or equal`, `is less or equal to`, `less than or equal`, `less than or equal to`, `is less than or equal to`, `greater or equal`, `greater or equal to`, `is greater or equal`, `is greater or equal to`, `greater than or equal`, `greater than or equal to`, `is greater than or equal to`), engelske aritmetikkaliaser (`times`, `multiplied_by`, `divided_by`, `add`, `subtract`, `divide`, `mod_of`, `modulo_of`, `remainder`) inkludert frasevarianter med mellomrom (`multiply by`, `multiplied by`, `divided by`, `divide by`, `modulo of`, `remainder of`), uttrykksstatements med `;` før sluttuttrykk, tomme statements (`;`), unary-operatorer (`!`, `-`, `+`) og norske operator-ord (`og/eller/ikke`, `er/ikke_er`, `mindre_enn`/`storre_enn`, `pluss/minus/ganger/ganget med/delt pa/delt med/mod/modulo`) inkludert fraser med mellomrom (`mindre enn`, `ikke er`, `er ikke`, `lik`, `er lik`, `er lik med`, `ikke lik`, `ikke lik med`, `ulik`, `ulik med`, `er ulik`, `er ikke lik`, `er ikke lik med`, `er mindre enn`, `er storre enn`, `er mindre eller lik`, `er storre eller lik`, `mindre enn eller lik`, `storre enn eller lik`, `mindre enn lik`, `storre enn lik`, `er mindre enn lik`, `er storre enn lik`, `mindre lik`, `storre lik`, `er mindre lik`, `er storre lik`) i `selfhost/compiler.no`)
- Selv-hosting lexer/token-strøm med bedre syntaksfeil og posisjonsinfo (utvidet: mini-skriptparser-feil + uttrykksparser-feil + `hvis`-parser-feil inkluderer token-posisjon)

---

## 👨‍💻 Laget av

Jan Steinar Sætre
