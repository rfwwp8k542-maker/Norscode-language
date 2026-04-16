# Norscode 1.0 veikart

## Visjon
Norscode skal være et selvstendig språk med egen binær-først verktøykjede.
Normal brukerflyt skal ikke kreve Python, Java eller Rust SDK installert lokalt.

Ved 1.0 betyr dette:
- `norscode` er hoved-kommando.
- `run`, `check`, `build`, `test` fungerer via binær standardflyt.
- prosjektkommandoer som `lock`, `add`, `update` og `registry-*` fungerer uten Python som standardvei.
- lockfil, registry-data og CI-signaler er deterministiske.

## Produktprinsipper
- Binær-først: dokumentasjon og standardkommandoer skal peke på binærveien.
- Legacy er eksplisitt: Python-veien kan eksistere midlertidig, men skal være tydelig merket.
- Samme kontrakt under migrasjon: tekstoutput, JSON-form og avslutningsstatus skal bevares så langt mulig.
- Smale steg: nye binære spor rulles ut kontrollert, med tilbakefall der risikoen er høy.

## Kort oppsummering

### Ferdig
- [x] M1. Binære kjernekommandoer

### Pågår
- [ ] M2. Første binære prosjektkommandoer
- [ ] M3. Registry og distribusjon
- [ ] M4. Fjern Python som standardvei

### Ikke startet som sluttfase
- [ ] M5. 1.0-kandidat

## Nåværende statusliste

### Kjernespråkflyt
- [x] `run` er binær-først
- [x] `check` kjører semantikk + binær validering som standard
- [x] `build` er bytecode-først
- [x] `test` er binær-først

### Første binære prosjektkommandoer
- [x] `lock` har binær-først standardflyt med `--legacy-python` tilbakefall
- [~] `update` har enkel binær-først standardflyt, men avansert flyt er fortsatt hybrid og legacy-preget
- [~] `registry-sync` har enkel binær-først standardflyt, men avansert flyt er fortsatt hybrid og legacy-preget
- [~] `add` har binær bro, men er fortsatt delvis forhåndsvisning og smal mutasjon
- [~] `registry-sign` har binær bro, men er fortsatt forhåndsvisning-først
- [~] `registry-mirror` har første binære spor, men er ikke en ferdig binær standardflyt
- [~] `ci` har første binære spor, men er ikke en ferdig binær standardflyt

### Grunnlag som allerede er fullført
- [x] minimal språkspesifikasjon er låst
- [x] bytecode- og IR-kontrakter er dokumentert
- [x] arkiv- og sti-sikkerhet er strammet inn
- [x] legacy C- og `clang`-stier er fjernet fra `run`, `build`, `test`
- [x] dokumentasjon og CLI er ryddet mot binær-først retning

## Utgivelsesmilepæler

### M1. Binære kjernekommandoer
Status: `ferdig`

Sjekkliste:
- [x] `run` er stabil som binær standardflyt
- [x] `check` er stabil som binær standardflyt
- [x] `build` er stabil som binær standardflyt
- [x] `test` er stabil som binær standardflyt
- [x] normal daglig bruk trenger ikke legacy C- og Python-stier for disse kommandoene
- [x] samme kontrakt er flyttet helt inn i framtidig full `norscode` binærkommando

### M2. Første binære prosjektkommandoer
Status: `avslutningsfase`

Sjekkliste:
- [x] `lock` har binær-først standardflyt
- [~] `lock` har nå svært jevn og nesten helt konsistent kontrakt mellom binær og legacy JSON- og tekstoutput
- [~] binær `lock` løfter `lockfil`, `status`, `problemer`, `sjekk` og `verifisering` tydeligere i tekstoutput og JSON
- [~] `lock` er svært nær stabil som binær-først prosjektkommando, med bare små kontrakthull igjen
- [~] `update` har trygg binær standardflyt for enkel bruk
- [~] `update` sender gjennom flere vanlige flagg i det binære sporet
- [~] binær `update` løfter `mål`, `sjekk` og `lock_ok` tydeligere i JSON- og tekstoutput
- [~] `update` er svært nær stabil kontrakt for bredere bruk, med få små kontrakthull igjen
- [~] `registry-sync` har trygg binær standardflyt for enkel bruk
- [~] `registry-sync` sender gjennom kilde- og policy-flagg i det binære sporet
- [~] binær `registry-sync` har jevnere JSON- og tekstoutput for `kilde`, `lager`, `antall` og tilbakefallsinfo
- [~] `registry-sync` har nær stabil kontrakt for bredere bruk
- [~] `add` er styrket utover den smaleste forhåndsvisningsflyten
- [~] `add` sender gjennom flere vanlige flagg i det binære sporet
- [~] binær `add` har jevnere JSON- og tekstoutput for `navn` og `mål`
- [~] `add` er tydelig styrket ut av den smaleste forhåndsvisningsfasen, men er ikke helt ferdig
- [~] `registry-sign` er styrket som enkel binær forhåndsvisnings- og standardflyt
- [~] enkel `registry-sign` bruker binær forhåndsvisning som standard
- [~] `registry-sign` er nær en stabil første binære prosjektkommando

Neste fokus:
- [~] lukke siste kontrakthull i `lock`
- [ ] lukke siste kontrakthull i `update`
- [ ] lukke siste kontrakthull i `add`
- [ ] lukke siste kontrakthull i `registry-sign`

### M3. Registry og distribusjon
Status: `tidlig påbegynt`

Sjekkliste:
- [~] `registry-sync` har et tydelig binært spor
- [~] `registry-sync`-JSON-formen er jevnere mot Python-sporet
- [~] `registry-sync`-tekstutdata er jevnere mot Python-sporet
- [~] `registry-sync` løfter nå `lager`, `antall`, `kilde` og tilbakefall tydeligere i binær kontrakt
- [~] `registry-sync` løfter nå også `konfig`, `status`, `mål`, `modus`, `endret` og `legacyspor` tydeligere i binær kontrakt
- [~] `registry-sync`-tekstutdata viser nå også `modus` og `endret` når runtime-sporet gir dem
- [~] `registry-sync`-tekstutdata viser nå også `legacyspor` og `registry_finnes` når runtime-sporet gir dem
- [ ] `registry-sync` har binær-først hovedvei
- [~] `registry-sign` har et tydelig binært spor
- [~] `registry-sign`-JSON-formen er jevnere mot Python-sporet
- [~] `registry-sign`-tekstutdata er jevnere mot Python-sporet
- [~] `registry-sign` løfter nå `registry`, `sha256` og `digeststi` tydeligere i binær kontrakt
- [~] `registry-sign` løfter nå også `konfig`, `status`, `modus`, `endret` og `legacyspor` tydeligere i binær kontrakt
- [~] `registry-sign`-tekstutdata viser nå også `modus` og `endret` når runtime-sporet gir dem
- [~] `registry-sign`-tekstutdata viser nå også `legacyspor` og `registry_finnes` når runtime-sporet gir dem
- [ ] `registry-sign` har binær-først hovedvei
- [~] `registry-mirror` har et tydelig binært spor
- [~] `registry-mirror` støtter `--output` i det binære sporet
- [~] `registry-mirror`-JSON-formen er jevnere mot Python-sporet
- [~] `registry-mirror`-tekstoutput er jevnere om skrive- og utdatamodus
- [~] `registry-mirror`-tekstutdata er jevnere mot Python-sporet
- [~] `registry-mirror` løfter nå `utdata`, `antall`, `skrevet` og `ønsket_utdata` tydeligere i binær kontrakt
- [~] `registry-mirror` løfter nå også `konfig`, `status`, `mål`, `modus`, `endret` og `legacyspor` tydeligere i binær kontrakt
- [~] `registry-mirror`-tekstutdata viser nå også `modus` og `endret` når runtime-sporet gir dem
- [~] `registry-mirror`-tekstutdata viser nå også `legacyspor` og `registry_finnes` når runtime-sporet gir dem
- [ ] `registry-mirror` har binær-først hovedvei
- [ ] registry-formatet er deterministisk
- [ ] digest er deterministisk og kontraktstabil
- [ ] mirror-outputen er deterministisk

### M4. Fjern Python som standardvei
Status: `delvis oppnådd`

Sjekkliste:
- [~] Python er ikke lenger standard for kjernekommandoene `run`, `check`, `build`, `test`
- [~] Python er ikke lenger standard for deler av prosjektkommandoene
- [~] `ir-disasm` bruker nå `selfhost` som standardmotor i stedet for `python`
- [~] `ir-disasm --engine`-hjelpeteksten peker nå tydelig på `selfhost` som standard og `python` som tilbakefall og paritetsspor
- [~] `--legacy-python`-hjelpetekster peker nå tydelig på eksplisitt tilbakefall i stedet for normal overgangsvei
- [~] `lock --legacy-python`-meldingene peker nå tydelig på eksplisitt Python-tilbakefall
- [~] toppnivå-CLI-epilogen omtaler nå `python3 -m norscode` som tilbakefall i legacy-sporet, ikke normalvei
- [~] toppnivå-CLI-epilogen omtaler nå hele kommandolinjeopplevelsen som binær-først med legacy som tilbakefall
- [~] toppnivå-CLI-epilogen bruker nå også begrepet `tilbakefall i legacy-sporet` konsekvent
- [~] feilmeldingen for manglende prebygd runtime-binær peker nå tydelig på Python bare som eksplisitt tilbakefall
- [~] flere `--native-runtime`-kravmeldinger peker nå også tydeligere på prebygd runtime-binær
- [~] versjonsstrengen omtaler nå CLI-en konsekvent som binær-først
- [~] toppnivå-CLI-noten om prosjektkommandoer omtaler nå migreringen konsekvent som binær-først
- [~] toppnivå-CLI-noten om standardmodi omtaler nå `run` og `test` samt `build` konsekvent som binær-først og bytecode-først
- [~] toppnivå-CLI-noten om standardmodi omtaler nå også `check` konsekvent med binær validering
- [~] `--runtime-binary`-hjelpeteksten for `run`, `check` og `test` peker nå tydeligere på prebygd runtime-binær
- [~] `--runtime-binary`-hjelpeteksten for prosjekt- og registry-kommandoene peker nå tydeligere på prebygd runtime-binær
- [~] `ci --runtime-binary`-hjelpeteksten peker nå tydeligere på prebygd runtime-binær
- [~] `--native-runtime`-hjelpetekstene peker nå tydeligere på prebygd runtime-binær
- [~] `--runtime-binary`-hjelpetekstene omtaler nå også `--native-runtime` tydeligere som et flagg
- [~] kommandohjelpen for `run`, `check` og `test` peker nå også tydeligere på prebygd runtime-binær som standardvei
- [~] `lock`-standardmeldingene peker nå også tydeligere på prebygd runtime-binær som standardvei
- [~] standardmeldingene for enkel `update` og `registry-sync` peker nå tydeligere på prebygd runtime-binær som standardvei
- [~] standardmeldingene for enkel `add` og `registry-sign` peker nå tydeligere på prebygd runtime-binær som standardvei
- [~] standardmeldingen for `registry-mirror` med eksplisitt utdata-sti peker nå også tydeligere på prebygd runtime-binær
- [~] forhåndsvisningsmeldingene for registry-kommandoene peker nå tydeligere på prebygd runtime-binær
- [~] oppfølgingsmeldingene for `add`, `update`, `registry-sign` og `registry-mirror` bruker nå mer konsekvent språk om prebygd runtime-binær
- [~] feilmeldingen for manglende runtime bruker nå også konsekvent `prebygd runtime-binær`
- [~] `--legacy-python`-hjelpetekstene peker nå også mer konsekvent på Python-tilbakefall mot prebygd runtime-binær
- [~] CI-check-hjelpetekstene omtaler nå sjekkrunnerne konsekvent som binære
- [~] CI-forhåndsvisningsmeldingene omtaler nå også kjøringen konsekvent som binær
- [~] `write-digest`- og `write-default`-hjelpetekstene samt `add --pin`-feilen bruker nå også mer konsekvent språk om prebygd runtime-binær
- [~] `add`-begrensningsmeldingen for prebygd runtime-binær bruker nå mer konsekvent språk
- [~] den synlige CLI-overflaten er nå i stor grad språkvasket fra gammel `native`-ordbruk, bortsett fra selve flaggnavnet `--native-runtime`
- [~] den synlige CLI-overflaten i `main.py` er nå merkbart jevnere norsk for registry-, lock-, CI-, migrerings- og release-meldinger, med etiketter som `Handling`, `Kjøretid`, `Lockfil`, `Register finnes` og `Endringslogg`
- [~] registry-sporet bruker nå jevnere navn i synlig CLI og standardstier, som `registersignering`, `registersynk`, `registerspeiling`, `digest-sidevogn` og `build/registerspeiling.json`
- [~] registry-etikettene i synlig CLI bruker nå jevnere norsk, som `Register`, `Register finnes`, `Lager`, `Utdata`, `Skrivemodus`, `Kilde` og `Mål`
- [~] flere hjelpetekster i prosjekt- og registry-sporet bruker nå jevnere norsk om `JSON-form`, `tørrkjøring`, `opprydding`, `utdata-fil` og `prebygd runtime-binær`
- [~] flere hjelpe- og feilmeldinger bruker nå jevnere norsk om `forhåndsvisning`, `Python-tilbakefall`, `digest-sidevogn`, `registerinitialisering`, `speilbygging` og `endringslogg`
- [~] migrerings- og release-sporet bruker nå jevnere norsk i synlig CLI, med formuleringer som `legacynavn`, `tørrkjøring`, `opprydding` og `Endringslogg`
- [~] README-toppen omtaler nå primærflyten konsekvent som binær-først med prebygd runtime-binær og eksplisitt Python-tilbakefall
- [~] README-delen for `registry-*`, `ci` og `add` bruker nå mer konsekvent språk om binær-først og prebygd runtime-binær
- [~] README-blokken om `add`, `run`, `test`, `check` og arkitekturretning bruker nå mer konsekvent språk om binær-først og Python-tilbakefall
- [~] README-blokken om `lock`, `update`, `registry-*` og `ci` bruker nå mer konsekvent språk om binær-først og prebygd runtime-binær
- [~] README-layouten og den siste `add`-brobeskrivelsen bruker nå mer konsekvent språk om prebygd runtime-binær
- [~] README-sporet for `registry-sign` og `ci` omtaler nå legacy og tilbakefall mer konsekvent
- [~] README bruker nå `den binære forhåndsvisningen` i stedet for `Rust-forhåndsvisningen` i den synlige `update`-delen
- [~] README-overskriften over Python-eksemplet markerer nå tydelig at dette er eksplisitt tilbakefall i legacy-sporet
- [~] README-kulepunktet for `python3 -m norscode` omtaler dette tydeligere som tilbakefall i legacy-sporet
- [~] README-linja om `NORSCODE_SUPPRESS_LEGACY_WARNING` peker tydeligere på eksplisitt Python-tilbakefall
- [~] README-linja om `ci` peker tydeligere på at fullsekvensen fortsatt ligger i eksplisitt tilbakefall i legacy-sporet
- [~] README-arkitekturlinja om Python-laget peker tydeligere på eksplisitt tilbakefalls- og overgangslag
- [~] `MINIMAL_LANGUAGE_SPEC.md` omtaler `run`, `test` og `check` konsekvent som binære og binær-først
- [~] toppen av `MIGRATION_LOG.md` omtaler `run`, `test`, `check`, `lock` og `update` mer konsekvent som binære og binær-først
- [~] `MIGRATION_LOG.md` omtaler `add`, `registry-sync` og `registry-sign` mer konsekvent med binære broer og mutasjonssteg
- [~] nederste del av `MIGRATION_LOG.md` omtaler overganger og åpne områder mer konsekvent som binære og binær-først
- [~] `MIGRATION_LOG.md` omtaler `build` konsekvent som bytecode-først
- [~] `MIGRATION_LOG.md` omtaler Python-sporet tydeligere som eksplisitt tilbakefall
- [~] `MIGRATION_LOG.md` bruker `Python-først` konsekvent i stedet for `Python-first`
- [~] `MIGRATION_LOG.md` omtaler gamle standardveier tydeligere som tilbakefalls- og legacy-veier
- [~] `MINIMAL_LANGUAGE_SPEC.md` omtaler `check` litt jevnere som binær validering
- [~] `MIGRATION_LOG.md` bruker litt jevnere norsk i `legacy-lignende`
- [~] `MIGRATION_LOG.md` bruker `dokumentasjon` i stedet for `docs` i den synlige `add`-delen
- [~] `MIGRATION_LOG.md` omtaler `legacy-status` litt tydeligere som tilbakefallsstatus
- [~] `MIGRATION_LOG.md` bruker bare `tilbakefallsstatus` i den synlige `registry-sign`-delen
- [~] `MIGRATION_LOG.md` bruker litt jevnere språk i `forhåndsvisningen eksponerer nå`
- [~] `MIGRATION_LOG.md` bruker `forhåndsvisningen` jevnere i de synlige `add`- og `registry-sync`-delene
- [~] `MIGRATION_LOG.md` bruker `forhåndsvisningen` jevnere i den synlige `update`-delen
- [~] `MIGRATION_LOG.md` bruker `første binære forhåndsvisning` i stedet for `første Rust-forhåndsvisning` i de synlige `update`, `add` og `registry-*`-delene
- [~] roadmap-toppen bruker nå også `binær-først`, `standardvei` og `binære spor` mer konsekvent
- [~] den synlige statusblokken i roadmapen bruker nå også `binær-først`, `binær bro` og `forhåndsvisning-først` mer konsekvent
- [~] M2- og M3-sjekklistene bruker nå også `binær`, `binært spor` og `binær kontrakt` mer konsekvent
- [~] kommandotabellen og M3-fokusblokken bruker nå også `hybrid-binær`, `binær-først` og `binær prosjektkommando` mer konsekvent
- [~] M4-overskriften i roadmapen bruker nå også `Fjern Python som standardvei`
- [~] roadmap-overskriftene bruker nå også norskere navn som `Kort oppsummering`, `Utgivelsesmilepæler` og `Kommandomigrasjonsstatus`
- [~] kommandotabellen bruker nå også norske statusord som `standard`, `delvis standard` og `legacy-standard`
- [~] kommandotabellen bruker nå også `legacy-standardvei`, `ingen legacy-C-sti`, `ingen tilbakefall` og `implisitt hybridflyt`
- [~] roadmapen bruker nå også `Sjekkliste` konsekvent i milepælblokkene
- [~] roadmap-toppen bruker nå også `veikart`, `Visjon`, `Produktprinsipper` og `verktøykjede`
- [~] roadmap-toppen bruker nå også `hoved-kommando` og `lockfil` i stedet for blandet engelsk
- [~] den øvre milepælblokken bruker nå også `dokumentasjon`, `JSON- og tekstoutput` og `forhåndsvisnings- og standardflyt` mer konsekvent
- [~] den nederste planblokken bruker nå også `Neste 14 dager`, `Teknisk retning`, `Målarkitektur`, `Suksesskriterier` og `verktøykjede`
- [~] den nederste planblokken bruker nå også `forhåndsvisning` og `forhåndsvisningsspor` i stedet for `preview`
- [~] roadmapen bruker nå også `registry-data`, `registry-formatet` og `mirror-outputen` mer konsekvent
- [~] CI- og kommandotabellblokken bruker nå også `forhåndsvisning` og `standard utdata-skriving` mer konsekvent
- [~] den nederste operative blokken bruker nå også `tekstoutput og JSON`, `sidecar-skriving` og `skrivesteg` mer konsekvent
- [~] `registry-sign`-linja i kommandotabellen bruker nå også `signerings- og konfigflyt`
- [~] `registry-sync`-linja i kommandotabellen bruker nå også `registry-dataflyt`
- [~] `registry-mirror`-linja i kommandotabellen bruker nå også `utdata-skriving`
- [~] `ci`-linja i roadmapen bruker nå også `legacy-flyten`
- [~] `ci`-linja i roadmapen bruker nå også `sjekkrunnere`
- [~] roadmapen bruker nå også `binærkommando` i stedet for `binær-CLI`
- [~] den nederste planblokken bruker nå også `standardflyt` og `utdata-sti` i stedet for `default`- og `output`-former
- [~] risiko- og suksessblokken bruker nå også `JSON-form`, `binære lag`, `build-bro` og `arbeidsflyt`
- [~] risiko- og suksessblokken bruker nå også `lockfil- og registry-data-determinisme`
- [~] risikoblokken bruker nå også `legacy-laget` og `det binære laget`
- [~] M5- og arkitekturblokken bruker nå også `registry-data-kontrakter`, `kjøretidsbinær` og `binærkommando`
- [~] arkitektur- og suksessblokken bruker nå også `prosjektkommando` og `språkruntime`
- [~] arkitektur- og risikoblokken bruker nå også `kjøretidsvalidering`, `kjøretidskjerne` og `JSON-formen`
- [~] M5- og neste-14-dager-blokken bruker nå også `brukere av legacy-sporet` og `kommandohjelp`
- [~] CI-blokken bruker nå også `sjekk-runnere`
- [~] arkitektur- og suksessblokken bruker nå også `kjøretidsbinæren` og `tilbakefalls- og legacy-stier`
- [~] `MINIMAL_LANGUAGE_SPEC.md` omtaler nå også feilbanen litt jevnere som binær validering
- [~] `MINIMAL_LANGUAGE_SPEC.md` er nå gjennomgått for de synlige binær- og bytecode-linjene i denne runden
- [ ] Python brukes bare som eksplisitt tilbakefall
- [ ] Python brukes bare som utviklerverktøy der det fortsatt trengs
- [ ] standard dokumentasjon er helt binær
- [ ] normal CLI-flyt er helt binær

### M5. 1.0-kandidat
Status: `ikke startet`

Sjekkliste:
- [ ] stabil CLI
- [ ] stabile lock-kontrakter
- [ ] stabile registry-data-kontrakter
- [ ] dokumentert migrasjon for brukere av legacy-sporet
- [ ] release-klar pakke og installasjon

## Kommandomigrasjonsstatus

| Kommando | Eier nå | Status | Fallback | Ferdig? | Neste steg |
|---|---|---|---|---|
| `run` | hybrid-binær | standard | ingen legacy-C-sti | ja | flytte inn i full binærkommando |
| `check` | hybrid-binær | standard | implisitt hybridflyt | ja | flytte semantisk kontrakt inn i full binærkommando |
| `build` | hybrid-binær | standard | ingen tilbakefall | ja | flytte inn i full binærkommando |
| `test` | hybrid-binær | standard | ingen tilbakefall | ja | flytte inn i full binærkommando |
| `lock` | binær-først | standard | `--legacy-python` | delvis | fullføre siste kontrakt- og paritetsdetaljer i tekstoutput og JSON |
| `update` | hybrid-binær | delvis standard | `--legacy-python` | delvis | utvide videre fra enkel målrettet `update <pakke>` og `--lock` til bredere flaggparitet |
| `add` | hybrid-binær | delvis standard | `--legacy-python` | delvis | utvide fra enkel binær standardflyt med `--name`, `--git`, `--url`, `--ref` og `--pin` til bredere add-paritet |
| `registry-sync` | hybrid-binær | delvis standard | `--legacy-python` | delvis | utvide binær registry-dataflyt utover lokal init og gjøre JSON- og tekstkontrakt jevnere |
| `registry-sign` | hybrid-binær | delvis | legacy-standardvei | delvis | utvide fra digestforhåndsvisning og sidecar-skriving til full signerings- og konfigflyt |
| `registry-mirror` | hybrid-binær | delvis | legacy-standardvei | delvis | utvide fra standard utdata-skriving til full deterministisk mirrorbygging og jevnere kontrakt |
| `ci` | hybrid-binær | delvis | legacy-standardvei | delvis | gjøre eksisterende binære sjekkrunnere mer like legacy-flyten og flytte mer av selve CI-logikken inn i det binære sporet |

## Nåværende milepælfokus

### Aktiv milepæl
M3. Registry og distribusjon

### CI binær status
- første binære `ci`-pakke er nå på plass
- binær `ci` har:
  - [x] forhåndsvisning
  - [x] `snapshot_check`
  - [x] `parser_fixture_check`
  - [x] `parity_check`
  - [x] `selfhost_m2_sync_check`
  - [x] `selfhost_progress_check`
  - [x] `test_check`
  - [x] `workflow_action_check`
  - [x] `name_migration_check`
- neste steg for `ci` er ikke flere små innganger, men å gjøre de eksisterende sjekkrunnerne mer like legacy-flyten

### Ferdigdefinisjon for nåværende milepæl
- [ ] `registry-sync` har en tydelig binær-først hovedvei
- [ ] `registry-sign` har en tydelig binær-først hovedvei
- [ ] `registry-mirror` har en tydelig binær-først hovedvei
- [ ] registry-formatet er deterministisk
- [ ] digest-kontrakten er deterministisk
- [ ] mirror-outputen er deterministisk

### Neste fokuserte leveranse: `registry-sign`
- [ ] gjøre `registry-sign` til neste lille kommando som går fra forhåndsvisning til faktisk nyttig binær prosjektkommando

Sjekkliste:
- [x] binær `registry-sign` kan lese lokal registry-fil
- [x] binær `registry-sign` kan beregne stabil digest
- [x] binær `registry-sign` har første smale skrivesteg
- [~] toppnivå-CLI-en kan bruke binær `registry-sign` uten mye uklarhet i tekstoutput eller tilbakefall
- [ ] `--write-config` er flyttet ut av legacy-sporet
- [ ] forskjellen mellom binær og legacy `registry-sign` er dokumentert
- [ ] første standardovergang er vurdert etter stabil kontrakt

## Neste 14 dager
- [ ] fullføre `registry-sign`-digest-kontrakt
- [ ] utvide `registry-sign` videre mot `--write-config`
- [ ] holde `registry-mirror` i gang som neste forhåndsvisningsspor
- [ ] gi `registry-mirror` første smale binære skrivesteg på standard utdata-sti
- [ ] gjøre `add` mer komplett og løfte flere vanlige tilfeller ut av legacy-sporet
- [ ] utvide `update`-støtte med flere flagg og færre legacy-avvik
- [ ] utvide `registry-sync`-støtte videre utover lokal init og enkel standardflyt
- [ ] definere første binære inngang for `ci`
- [ ] holde README og kommandohjelp synkron med faktisk status

## Teknisk retning

### Målarkitektur
- `norscode-runtime` skal være kjøretidsbinæren for bytecode-kjøring og kjøretidsvalidering.
- full prosjektkommando skal på sikt bo i en egen `norscode` binærkommando.
- prosjektlogikk og kjøretidskjerne skal holdes adskilt.

### Foretrukket moduldeling
- `cli`
- `project`
- `lock`
- `registry`
- `runtimebro`

## Risikoer
- høy: migrasjon uten å bryte tekstoutput, JSON-formen eller avslutningsstatus
- høy: lockfil- og registry-data-determinisme på tvers av OS
- høy: semantiske forskjeller mellom legacy-laget og det binære laget
- middels: dokumentasjon som lover mer enn implementasjonen faktisk gjør
- praktisk: denne handoff-snapshoten mangler full build-bro for binærflyten og bruker derfor overgangsbroer

## Suksesskriterier
- bruker kan installere og bruke Norscode uten ekstern språkruntime i normal flyt
- Linux, macOS og Windows kan kjøre samme binære arbeidsflyt
- tilbakefalls- og legacy-stier er eksplisitte, små og midlertidige
- 1.0 kan beskrives som et eget språk med egen verktøykjede, ikke et Python-prosjekt med språk-lag
