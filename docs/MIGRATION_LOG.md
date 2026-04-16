# Norscode Migration Log

Dette dokumentet er historikk, ikke styringsplan.
Den aktive planen ligger i [ROADMAP.md](/Users/jansteinarsaetre/Documents/language_handoff/projects/language/ROADMAP.md).

## Formål
- bevare viktige migrasjonsgrep
- dokumentere hva som faktisk er flyttet
- unngå at hoved-roadmapen blir en lang aktivitetslogg

## Fase 1: kjerne og kontrakter
- minimal språkspesifikasjon ble låst
- bytecode/IR-kompatibilitet ble dokumentert
- archive/path-sikkerhet i pakkehåndtering ble strammet inn
- `tomllib` fikk fallback via `tomli`
- binær-først dokumentasjon ble gjort til standard
- eksplisitt Python-fallback ble tydelig merket i CLI og bootstrap
- legacy C/`clang`-stier ble fjernet fra:
  - `run`
  - `build`
  - `test`

## Språkkommandoer: brukerflyt
- `run` ble binær-først
- `check` ble standardisert som semantikk + binær validering
- `build` ble bytecode-først
- `test` ble binær-først
- overgangskommandoer som bare ga midlertidig verdi ble senere ryddet ut av toppnivå-CLI-en

## `lock`
- første Rust-skjelett for prosjekt discovery og config-load ble opprettet
- første dependency-parser for `[dependencies]` ble lagt inn i Rust-laget
- første `LockDocument` og serialisering ble lagt inn
- første `LockWrite`, `LockCheck` og `LockVerify` ble etablert i Rust-laget
- `LockCheck` ble gjort mer legacy-lignende ved å ignorere `generated_at`
- `LockVerify` ble gradvis strammet inn for:
  - `lock_version`
  - `project`
  - `project.name`
  - typekontrakter for prosjektmetadata
  - `dependencies`
  - `specifier`
  - `kind`
  - `resolved`
- `generated_at` ble gjort RFC3339/ISO-lik
- toppnivå-CLI fikk første binære bro for `lock`
- `lock`
- `lock --check`
- `lock --verify`
  bruker nå binær bro som standard
- `lock --legacy-python` ble lagt inn som eksplisitt fallback

## `update`
- første binære preview ble opprettet
- binær bro via toppnivå-CLI ble lagt inn
- dependency-plan med `unchanged`/`skipped` ble lagt inn i previewen
- pinned `git`, `url` og lokale path-dependencies ble gitt tydelige skip-grunner
- `status`, `target`, `updated_count`, `unchanged_count`, `skipped_count` ble standardisert i output
- første smale binære skrivevei ble lagt inn for:
  - direkte upinnet `git+...`
  - direkte `url+...`
- enkel `update` og enkel `update --check` bruker nå binær bro som standard
- `update --legacy-python` ble lagt inn som eksplisitt fallback

## `add`
- første binære preview ble opprettet
- binær bro via toppnivå-CLI ble lagt inn
- previewen fikk klassifisering av eksisterende dependencies:
  - `path`
  - `git`
  - `url`
- previewen fikk klassifisering av ønsket input:
  - `name`
  - `path`
  - `git`
  - `url`
- previewen fikk `target_status`, `target_existing_kind` og `target_plan`
- første smale binære mutasjonsvei ble lagt inn for:
  - direkte `path`
  - `add <navn> <path>`
  - direkte `git+...`
  - direkte `url+...`
- dokumentasjon og CLI-hjelp ble gjort ærlige om at `--git` og `--url` fortsatt er legacy-spor

## `registry-sync`
- første binære preview ble opprettet
- binær bro via toppnivå-CLI ble lagt inn
- previewen begynte å lese:
  - standard registry-sti
  - om registry finnes
  - `package_count`
- `status` og `target` ble lagt inn som baseline i output
- første smale binære write-steg ble lagt inn:
  - lokal init av `packages/registry.toml` med minimalt grunnformat
- enkel `registry-sync` uten avanserte source/policy-flagg bruker nå binær bro som standard
- `registry-sync --legacy-python` ble lagt inn som eksplisitt fallback

## `registry-sign`
- første binære preview ble opprettet
- binær bro via toppnivå-CLI ble lagt inn
- previewen eksponerer nå:
  - config
  - fallback-status
  - registry-sti
  - om registry finnes
  - første `registry_sha256` når filen finnes
- full write-/config-flyt er ikke flyttet ennå

## Intern opprydding i Python-laget
- `lock` ble delt opp i tydeligere document/write/verify-retning
- `add` fikk egne helpere for:
  - registry-oppløsning
  - eksplisitt `git/url`
  - path/default-package
- `update` fikk egne helpere for:
  - per-dependency planlegging
  - `--lock`-bro
- `registry-sync` fikk egne helpere for:
  - source selection
  - merge
  - fallback
  - cache-skriving
- `registry-sign` fikk egne helpere for:
  - digest-lesing
  - config-skriving
- `registry-mirror` fikk egne helpere for:
  - package-row mapping
  - payload-skriving
- `ci` ble delt opp i tydeligere planning/payload/check-runner-retning

## Viktige overganger i brukerflate
- dokumentasjon ble flyttet fra Python-først til binær-først
- prosjektkommandoer ble tydelig merket i CLI og README
- fallback-/legacy-veier ble gjort eksplisitte i stedet for skjulte standarder

## Åpne migrasjonsområder
- `add` er fortsatt ikke fullverdig binær standardkommando
- `registry-sign` mangler første smale write-steg og senere `--write-config`
- `registry-mirror` mangler binær preview/flyt
- `ci` mangler binær inngang i brukerflaten
- full framtidig `norscode` binær-CLI finnes ikke som ferdig produkt i denne snapshoten
