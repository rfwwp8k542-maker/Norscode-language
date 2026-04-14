# Norscode 1.0 Roadmap

## Vision
Norscode skal være et selvstendig språk med egen binær-first toolchain.
Normal brukerflyt skal ikke kreve Python, Java eller Rust SDK installert lokalt.

Ved 1.0 betyr dette:
- `norscode` er hoved-CLI.
- `run`, `check`, `build`, `test` fungerer via binær standardflyt.
- prosjektkommandoer som `lock`, `add`, `update` og `registry-*` fungerer uten Python som default path.
- lockfile, registry og CI-signaler er deterministiske.

## Product principles
- Binær-first: dokumentasjon og standardkommandoer skal peke på binærveien.
- Legacy er eksplisitt: Python-veien kan eksistere midlertidig, men skal være tydelig merket.
- Samme kontrakt under migrasjon: tekstoutput, JSON-shape og exit-status skal bevares så langt mulig.
- Smale steg: nye native spor rulles ut kontrollert, med fallback der risikoen er høy.

## Current status

### Core language flow
- `run`: native-first
- `check`: semantikk + native validering som standard
- `build`: bytecode-first
- `test`: native-first

### First native project commands
- `lock`: native-first med `--legacy-python` fallback
- `update`: enkel standardflyt er native-first, avansert flyt er fortsatt hybrid/legacy
- `registry-sync`: enkel standardflyt er native-first, avansert flyt er fortsatt hybrid/legacy
- `add`: native bro finnes, men er fortsatt delvis preview / smal mutasjon
- `registry-sign`: native bro finnes, men er fortsatt preview-first
- `registry-mirror`: ikke startet som native brukerflyt
- `ci`: ikke startet som native brukerflyt

### Foundation already completed
- minimal språkspesifikasjon er låst
- bytecode/IR-kontrakter er dokumentert
- archive/path-sikkerhet er strammet inn
- legacy C/`clang`-stier er fjernet fra `run`, `build`, `test`
- docs og CLI er ryddet mot binær-first retning

## Release milestones

### M1. Native core commands
Mål:
- `run`, `check`, `build`, `test` er stabile som binær standardflyt
- ingen normal daglig bruk trenger legacy C/Python-stier for disse kommandoene

Status:
- i praksis nådd i brukerflyt

Gjenstår:
- flytte samme kontrakt inn i framtidig full `norscode` binær-CLI, ikke bare via overgangslag

### M2. First native project commands
Mål:
- `lock` er stabil som native-first prosjektkommando
- `update` og `registry-sync` har trygg native standardflyt for enkel bruk
- `add` er ute av ren preview-fase

Status:
- pågår

Gjenstår:
- styrke `add`
- styrke `registry-sign`
- stabilisere kontrakter i `update` og `registry-sync`

### M3. Registry and distribution
Mål:
- `registry-sync`, `registry-sign`, `registry-mirror` har native-first hovedvei
- registry-format, digest og mirror-output er deterministiske

Status:
- tidlig påbegynt

### M4. Remove Python as default path
Mål:
- Python brukes bare som eksplisitt fallback eller utviklerverktøy
- standard dokumentasjon og normal CLI-flyt er helt binær

Status:
- delvis oppnådd

### M5. 1.0 candidate
Mål:
- stabil CLI
- stabile lock/registry-kontrakter
- dokumentert migrasjon for legacy-brukere
- release-klar pakke/installasjon

Status:
- ikke startet

## Command migration status

| Command | Owner now | Status | Fallback | Next step |
|---|---|---|---|---|
| `run` | hybrid/native | default | no legacy C | flytte inn i full binær-CLI |
| `check` | hybrid/native | default | implicit hybrid | flytte semantikk-kontrakt inn i full binær-CLI |
| `build` | hybrid/native | default | none | flytte inn i full binær-CLI |
| `test` | hybrid/native | default | none | flytte inn i full binær-CLI |
| `lock` | native-first | default | `--legacy-python` | gjøre native kontrakt helt legacy-lik |
| `update` | hybrid/native | partial default | `--legacy-python` | utvide videre fra enkel målrettet `update <pakke>` og `--lock` til bredere flaggparitet |
| `add` | hybrid/native | partial default | `--legacy-python` | utvide fra enkel native standardflyt med `--name`/`--git`/`--url`/`--ref`/`--pin` til bredere add-paritet |
| `registry-sync` | hybrid/native | partial default | `--legacy-python` | utvide native registry-logikk utover lokal init |
| `registry-sign` | hybrid/native | partial | legacy default | utvide fra digest-preview og sidecar-write til full sign/config-flyt |
| `registry-mirror` | hybrid/native | partial | legacy default | utvide fra default-write til full deterministisk mirror-bygging |
| `ci` | hybrid/native | partial | legacy default | gjøre eksisterende native check-runnere mer legacy-like og flytte mer av selve CI-logikken inn i native sporet |

## Current milestone focus

### Active milestone
M2. First native project commands

### CI native status
- første native `ci`-pakke er nå på plass
- native `ci` har:
  - preview
  - `snapshot_check`
  - `parser_fixture_check`
  - `parity_check`
  - `selfhost_m2_sync_check`
  - `selfhost_progress_check`
  - `test_check`
  - `workflow_action_check`
  - `name_migration_check`
- neste steg for `ci` er ikke flere små innganger, men å gjøre de eksisterende runnerne mer like legacy-logikken

### Definition of done for current milestone
- `lock` oppfører seg stabilt som native-first kommando
- `update` enkel standardbruk føles trygg i native spor
- `registry-sync` enkel standardbruk føles trygg i native spor
- `add` kan gjøre mer enn preview og smal skrivevei
- `registry-sign` går fra preview til første faktisk nyttige write-/digest-kontrakt

### Next focused deliverable: `standalone` / distribution
Mål:
- flytte standalone-distribusjon bort fra gammelt `projects/infra`-spor
- gjøre binærbygging konsistent med `projects/language`-pakken som nå brukes i CI
- åpne standalone-jobbene igjen når de bygger og verifiserer riktig produkt

Definition of done:
- én dokumentert build-vei lager `dist/norscode` fra riktig språk-workspace
- Linux-jobben kan bygge og verifisere binæren uten å bruke gammel repo-rot-logikk
- macOS-jobben kan gjøre det samme
- standalone-jobbene kan slås på igjen i vanlig CI uten å gi falske røde bygg

Planned sequence:
1. definere riktig byggeier: `projects/language` vs gammelt `projects/infra`
2. lage ny eller oppdatert standalone-build-kommando for det riktige sporet
3. verifisere at `dist/norscode test` peker på samme språk/workspace som vanlig CI
4. åpne Linux-jobben igjen
5. åpne macOS- og Windows-jobbene igjen

Status nå:
- vanlig CI er grønn mot `projects/language`
- gamle standalone-jobber er gated til `workflow_dispatch`
- standalone-sporet bygger fortsatt et eldre infra-lag og må migreres

## Immediate next 14 days
- migrere standalone/distribusjon til riktig språkspor:
  - definere ny build-vei for `dist/norscode`
  - stoppe avhengighet på gammelt `projects/infra`-oppsett
  - åpne standalone Linux igjen først
- holde `registry-sign` i bevegelse etterpå:
  - fullføre digest-kontrakt
  - senere `--write-config`
- gjøre `registry-mirror` mer komplett etter default-write-sporet
- gjøre `add` mer komplett med færre legacy-avvik
- utvide `update` native-støtte videre fra enkel standardflyt
- holde README, roadmap og workflower synkron med faktisk bygge- og distribusjonsstatus

## Technical direction

### Target architecture
- `norscode-runtime` skal være runtime-binær for bytecode-kjøring og runtime-validering.
- full prosjekt-CLI skal på sikt bo i en egen `norscode` binær-CLI.
- prosjektlogikk og runtime-kjerne skal holdes adskilt.

### Preferred module split
- `cli/`
- `project/`
- `lock/`
- `registry/`
- `runtime_bridge/`

## Risks
- høy: migrasjon uten å bryte tekstoutput, JSON-shape eller exit-status
- høy: lock/registry-determinisme på tvers av OS
- høy: semantiske forskjeller mellom legacy-lag og native-lag
- middels: docs som lover mer enn implementasjonen faktisk gjør
- praktisk: denne handoff-snapshoten mangler full build-wrapper for binærflyten og bruker derfor overgangsbroer

## Success criteria
- bruker kan installere og bruke Norscode uten eksternt språk-runtime i normal flyt
- Linux, macOS og Windows kan kjøre samme binære workflow
- legacy-stier er eksplisitte, små og midlertidige
- 1.0 kan beskrives som et eget språk med egen toolchain, ikke et Python-prosjekt med språk-lag
