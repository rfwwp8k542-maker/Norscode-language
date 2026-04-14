# Norscode Language

This tree is the language workspace for Norscode.

It includes the compiler, runtime, standard library, examples, tests, package
fixtures, Studio v2 sources, and VS Code language support.

## Språkkommandoer

From inside this folder:

```bash
bin/nc test tests/test_math.no
bin/nc test tests
bin/nc run samples/app.no
bin/nc build samples/app.no
bin/nc check samples/app.no
```

## Prosjektkommandoer

Fra samme mappe:

```bash
bin/nc lock
bin/nc lock --native-runtime
bin/nc add std.io
bin/nc update
bin/nc update --native-runtime
bin/nc registry-sync
bin/nc ci
bin/nc runtime-ci
```

For installerte builds kan du også bruke `norscode` kommandoen direkte:

```bash
norscode test tests/test_math.no
norscode run samples/app.no
norscode build samples/app.no
```

Bygg- og debug-kode for binæren:

```bash
./dist/norscode --help
```

Merk:
- `dist/norscode` forventes å være tilgjengelig i denne handoff-snapshoten.
- Referansen til `scripts/build-standalone.sh` er ikke tilgjengelig i denne workspace-kopien.

Legacy (installeringsmodus via Python):

```bash
python3 -m norscode test tests/test_math.no
```

For automatiserte skript kan du slå av legacy-advarselen:

```bash
NORSCODE_SUPPRESS_LEGACY_WARNING=1 python3 -m norscode test tests/test_math.no
```

Merk:
- `python3 -m norscode` er **legacy** og brukes når du eksplisitt trenger det.
- Primærflyten er binær-first via `bin/nc` eller `norscode`.
- `run` bruker native runtime som standard.
- `test` bruker native runtime som standard.
- `build` lager bytecode (`.ncb.json`) som standard.
- `lock` er fortsatt en sentral prosjektkommando i toppnivå-CLI-en.
- `lock --native-runtime` bruker en første kontrollert bro til `norscode-runtime` for `write`, `check` og `verify`.
- `lock --native-runtime --json` gir nå strukturert resultatobjekt, ikke bare rå stdout.
- `lock` bruker nå native runtime-broen som standard.
- `lock --check` bruker nå native runtime-broen som standard.
- `lock --verify` bruker nå native runtime-broen som standard.
- `lock --legacy-python` gir en eksplisitt fallback til overgangslaget i Python.
- `add` og `update` er fortsatt sentrale prosjektkommandoer i toppnivå-CLI-en.
- `update` har nå også et første binært skjelett i `norscode-runtime`, og previewen leser nå faktisk dependencies fra prosjektconfig.
- `update --native-runtime` bruker en første kontrollert bro til `norscode-runtime` og gir strukturert preview-output.
- den første reelle native `update`-flyten er nå direkte `git+...` uten pinnet ref.
- samme smale native `update`-spor dekker nå også enkel direkte `url+...`.
- toppnivå-broen for `update --native-runtime` beskriver nå eksplisitt både `git+...` og `url+...` som del av dette første native-sporet.
- enkel `update` uten avanserte flagg bruker nå native bro som standard.
- enkel `update --check` uten ekstra avanserte flagg bruker nå native bro som standard.
- enkel `update <pakke>` kan nå også gå gjennom native bro når resten av kommandoen er enkel.
- enkel `update --lock` bruker nå native `update` + native `lock` i samme standardflyt.
- `update --legacy-python` gir en eksplisitt fallback til overgangslaget i Python.
- native `update` eksponerer nå også `target=all` som stabil baseline i outputen.
- native `update` eksponerer nå også toppnivå `status` for bedre kontraktlikhet med Python-laget.
- Rust-`update` previewen planlegger nå også en første item-status per dependency (`unchanged` som startpunkt).
- pinned `git`-kilder blir nå markert som `skipped` med enkel årsak i Rust-previewen.
- lokale path-dependencies blir nå også markert som `skipped` med enkel årsak i Rust-previewen.
- previewen summerer nå også `unchanged` og `skipped` separat.
- previewen eksponerer også `updated_count=0` som stabil baseline for videre migrasjon.
- Rust-`update` har nå også første smale mutasjonssteg: enkel direkte `git+...` uten pinnet ref går gjennom en kontrollert native skrivevei.
- `registry-sync` har nå også et første binært skjelett i `norscode-runtime`, foreløpig som preview av prosjekt/config og standard registry-sti.
- `registry-sync --native-runtime` gir nå en første kontrollert preview-bro i toppnivå-CLI-en.
- Rust-`registry-sync` previewen leser nå også om lokal registry finnes og hvor mange package entries som er definert.
- native `registry-sync` eksponerer nå også toppnivå `status` og `target` som stabil baseline.
- Rust-`registry-sync` har nå også første smale lokale write-steg: den kan initialisere `packages/registry.toml` med et minimalt grunnformat hvis filen mangler.
- toppnivå-broen for `registry-sync --native-runtime` beskriver nå denne lokale init-veien eksplisitt.
- enkel `registry-sync` uten ekstra source/policy-flagg bruker nå native bro som standard.
- `registry-sync --legacy-python` gir en eksplisitt fallback til overgangslaget i Python.
- `registry-sign` har nå også et første binært skjelett i `norscode-runtime`, foreløpig som preview av prosjekt/config og registry-fil.
- `registry-sign --native-runtime` gir nå en første kontrollert preview-bro i toppnivå-CLI-en.
- native `registry-sign` preview beregner nå også første `registry_sha256` når lokal registry-fil finnes.
- `registry-sign --native-runtime --write-digest` kan nå skrive en første lokal sidecar til `packages/registry.toml.sha256`, mens `--write-config` fortsatt er legacy-spor.
- `registry-mirror --native-runtime` gir nå en første kontrollert preview-bro med prosjekt/config, registry-status og default output-sti.
- `registry-mirror --native-runtime --write-default` kan nå skrive en første deterministisk default-output til `build/registry_mirror.json`.
- `ci --native-runtime` gir nå en første kontrollert preview-bro med prosjekt/config og valgt CI-scope.
- `ci --native-runtime --snapshot-check` gir nå første smale native CI-check-runner for `tests/ir_snapshot_cases.json`.
- `ci --native-runtime --parser-fixture-check` gir nå en smal native sjekk av selfhost parity-fixturefiler for valgt suite.
- `ci --native-runtime --parity-check` gir nå en smal native sjekk av parity-prøvefilen `tests/ir_sample.nlir`.
- `ci --native-runtime --selfhost-m2-sync-check` gir nå en smal native sjekk av fixturegrunnlaget for M2-sync.
- `ci --native-runtime --selfhost-progress-check` gir nå en smal native baseline for selfhost progress/ready-signal.
- `ci --native-runtime --test-check` gir nå en smal native sjekk av testgrunnlaget i `tests/`.
- `ci --native-runtime --workflow-action-check` gir nå en smal native sjekk av workflow-grunnlaget i `.github/workflows`.
- `ci --native-runtime --name-migration-check` gir nå en smal native sjekk av legacy-navn som fortsatt ligger igjen i prosjektet.
- samlet betyr dette at `ci` nå har en første native check-pakke, selv om full CI-sekvens fortsatt ligger i legacy-sporet.
- native `workflow_action_check` krever nå også at minst én workflow faktisk refererer `norscode ci`.
- native `name_migration_check` dekker nå også `.norsklang`/`.norscode`-paret og rapporterer hvor mange primærnavn som allerede finnes.
- `add` har nå også et første binært skjelett i `norscode-runtime`, og previewen leser nå faktisk dependency-kontekst fra prosjektconfig.
- `add --native-runtime` gir nå en første kontrollert bro i toppnivå-CLI-en.
- Rust-`add` previewen klassifiserer nå eksisterende dependencies som `path`, `git` eller `url`.
- `add --native-runtime <pakke>` kan nå også previewe om pakken allerede finnes eller er en ny kandidat.
- previewen klassifiserer nå også ønsket pakke som `name`, `path`, `git` eller `url`.
- previewen kombinerer nå ønsket pakke med eksisterende kontekst via `target_existing_kind` og `target_plan`.
- Rust-`add` kan nå også gjøre første smale mutasjon: skrive enkle `path`, `git+...` og `url+...` dependencies direkte til config når inputen er enkel nok.
- native `add` støtter nå også formen `add <navn> <path>` for samme smale lokale path-mutasjon.
- native `add` støtter nå også `--name` i den enkle native standardflyten.
- native `add` støtter nå også `--ref` for direkte `git+...` i den enkle native standardflyten.
- native `add` støtter nå også `--pin` for direkte `git+...`, så lenge dependencyen faktisk blir låst med `@ref`.
- native `add` støtter nå også `--git` som alias inn i den samme enkle native `git+...`-flyten.
- native `add` støtter nå også `--url` som alias inn i den samme enkle native `url+...`-flyten.
- native `add`-outputen eksponerer nå også toppnivå `status` (`updated` / `unchanged`) for den enkle standardflyten.
- native `add` bruker fortsatt ikke `--git`/`--url`-flaggene i Rust-sporet; den smale støtten går via direkte `git+...`/`url+...` input.
- enkel `add` med direkte `path`/`git+...`/`url+...` input bruker nå native bro som standard, med `--legacy-python` som eksplisitt fallback.
- `registry-sync`, `registry-sign` og `registry-mirror` er prosjektkommandoer for registry/cache/distribusjon.
- `ci`, `debug`, `migrate-names` og `release` er også prosjektkommandoer i samme toppnivåflate.
- standalone/distribusjon er neste eksplisitte migrasjonsmål; gamle standalone-jobber i CI er midlertidig gated mens build-sporet flyttes fra eldre `projects/infra` til riktig `projects/language`-grunnlag.
- `bytecode-build` er en lavnivå utviklerkommando for eksplisitt bytecode-artifakt.
- `run` kan fortsatt beholde generert bytecode ved behov via `--keep-bytecode`.
- Legacy C/`clang`-stien er nå fjernet fra `run`, `build` og `test`.
- `build --legacy-c` er fjernet; build følger nå bare bytecode-stien.
- `test --legacy-c` er fjernet; test følger nå bare native runtime-stien.
- `run --legacy-c` er fjernet; run følger nå bare native runtime-stien.
- `check` kombinerer semantikk og native validering som standard.

Disse kommandoene er fortsatt en viktig del av toppnivå-CLI-en mens binær-first migreringen fortsetter:

- `lock` for lockfile
- `add` og `update` for dependencies
- `registry-sync`, `registry-sign` og `registry-mirror` for registry/cache/distribusjon
- `ci`, `debug`, `migrate-names` og `release` for kvalitet, migrasjon og leveransearbeid

Neste tekniske migrasjonsmål i denne gruppen er `lock`.

Planen for `lock` er å speile dagens flyt i fire deler: config discovery, dependency-resolver, deterministisk digest/JSON-skriving og kompatibel `--verify`.

Etter `lock` følger `add` og `update`, med egne blokker for source-parsing, trust-policy, config-skriving og lock-integrasjon.

Etter det følger `registry-sync`, med egne blokker for source-resolver, trust-policy, cache-skriving og fallback-policy.

Deretter kommer `registry-sign` og `registry-mirror`, som fullfører registry-sporet med digest/config-skriving og deterministisk mirror-bygging.

Arkitekturretning:
- `norscode-runtime` er runtime-binæren og skal ikke bære hele prosjekt-CLI-en.
- `lock` og de andre prosjektkommandoene er ment for en framtidig full `norscode` binær-CLI.
- Python-laget er fortsatt overgangslaget i denne snapshoten.

## Kjernekontrakter

- Minimal språkspesifikasjon: [docs/MINIMAL_LANGUAGE_SPEC.md](/Users/jansteinarsaetre/Documents/language_handoff/projects/language/docs/MINIMAL_LANGUAGE_SPEC.md)
- Bytecode-kontrakt: [docs/BYTECODE_CONTRACT.md](/Users/jansteinarsaetre/Documents/language_handoff/projects/language/docs/BYTECODE_CONTRACT.md)
- Bytecode-kompatibilitet: [docs/BYTECODE_COMPATIBILITY.md](/Users/jansteinarsaetre/Documents/language_handoff/projects/language/docs/BYTECODE_COMPATIBILITY.md)

## Layout

- `compiler/` compiler pipeline and code generation
- `runtime/` native runtime implementation
- `std/` standard library modules
- `tests/` compiler and runtime regression tests
- `examples/` and `samples/` runnable programs
- `studio_v2/` Studio v2 workspace
- `vscode-norscode/` editor support package
- `packages/` package registry samples and bundled packages
