# Handlingsplan

## 1. Fullfør editor-ergonomien

- [x] `go-to-line`
- [x] `go-to-symbol`
- [x] `rename`
- [x] `references`
- [x] tab-bytting
- [x] split-fokus

## 2. Koble handlingene til GUI-en

- [x] Gjør søkefeltet til en faktisk navigasjonsinngang
- [x] La fil-listen trigge relevante handlinger
- [x] La referanselista trigge valg og navigasjon
- [x] Vis valgt tab og aktivt split-fokus i editor-panelet

## 3. Stram inn state-håndteringen

- [x] Lagre aktiv tab
- [x] Lagre split-fokus
- [x] Gjenopprett sist brukte navigasjon
- [x] Sørg for konsistent gjenoppretting av åpne filer og aktiv fil

## 4. Gjør actions-laget mer konkret

- [x] Knytt `run`, `check`, `test` og `runtime-ci` til UI-handlinger
- [x] Legg inn enkel feilhåndtering
- [x] Vis statusmeldinger når en kommando ikke kan kjøres

## 5. Utvid tester systematisk

- [x] Tester for hver ny editor-handling
- [x] GUI-nære tester for tab-valg og referansevalg
- [x] Tester for rename preview
- [x] Hold foundation-testen grønn

## 6. Verifiser etter hver liten leveranse

- [x] Kjør foundation-testen etter hver endring
- [x] Fiks runtime- eller kompileringsblokker før videre arbeid

## Rekkefølge

- [x] 1. `go-to-line` og tab-bytting
- [x] 2. `references` og `rename preview`
- [x] 3. GUI-kobling
- [x] 4. session/state-persistens
- [x] 5. flere tester

## 7. PyCharm-lignende UI

- [x] Del skjermen i tydelige soner: prosjekt, editor og inspeksjon
- [x] Stram inn topp- og bunnlinje til mer kompakt IDE-stil
- [x] Gjør venstre panel mer som et project tool window
- [x] Gjør midtsonen til en tydelig editor-fokusflate
- [x] Gjør høyre panel mer som structure/references/diagnostics
- [x] Legg inn en smal tool-window-stripe for raskere navigasjon
- [x] Gjør tab-linjen over editoren tydeligere
- [x] Reduser antall tekstlinjer per panel
- [x] Juster farger, spacing og typografi mot en mer klassisk IDE-følelse
- [x] Test GUI-en visuelt etter hver endring

## 8. Videre UI-puss

- [x] Legg inn tydeligere visuelle overskrifter per panel
- [x] Gjør tom-tilstander rolige og informative
- [x] Prioriter aktive elementer tydeligere enn passive lister
- [x] Gi editoren mer luft rundt seg
- [x] Gjør sidepanelene smalere og mer kompakte
- [x] Skille bedre mellom status, navigasjon og innhold
- [x] Legg inn egen `Problems`- eller `Diagnostics`-flate hvis det trengs
- [x] Legg inn raskt bytte mellom `Project`, `Editor` og `Inspect`
- [x] Sørg for at søk alltid føles som `Search Everywhere`
- [x] Sørg for at referanser og rename føles som IDE-verktøy, ikke bare lister
- [x] Sjekk at layouten fungerer både på små og store vinduer
- [x] Hold testene grønne etter hver visuell justering

## 9. Triage

- [x] Gjør tab-linjen over editoren tydeligere
- [x] Visuell markør for aktiv tab
- [x] Rens valgmarkør ved tab-klikk

## 10. Større hull igjen

- [x] Ekte project tree med folder-noder og collapse/expand
- [x] Ekte tool-window state for `Project`, `Editor` og `Inspect`
- [x] Mer klassisk run-/configuration-bar øverst
- [x] Kommandopalett som popup i stedet for bare liste
- [x] Tydeligere bottom tool windows for `Problems`, `References` og `Terminal`
- [x] Tastatursnarveier for å åpne og lukke tool windows
- [x] Visuell aktiv/inaktiv markering på tool-window-knappene
- [x] Mer PyCharm-lignende spacing og ikonografi i hele shellen

## 11. Mot PyCharm-nivå

- [x] Ekte IDE-kjerne med stabil layout og konsekvent fokus
  - [x] Stabil topbar, tool-window-stripe, editorflate og statuslinje
  - [x] Konsekvent markering og tastaturnavigasjon
- [x] Fullverdig `Project`
  - [x] Folder tree med `collapse/expand`
  - [x] Nylige prosjekter, åpne tabs og filer i samme arbeidsflyt
  - [x] `Enter` åpner valgt element
  - [x] Bevar valg og aktiv node
  - [x] Bevar scrollposisjon i prosjektlisten
- [x] Smartere editor
  - [x] Ekte tab-håndtering med flere åpne filer
  - [x] Split-view som faktisk er nyttig
  - [x] `go to line`, `go to symbol`, `references`, `rename`
  - [x] Preview før endring og trygg apply-flow
- [x] Ekte `Search Everywhere`
  - [x] Global søkeflate for filer, symboler, kommandoer og nylige prosjekter
  - [x] Filtrering mens du skriver
  - [x] `Enter` åpner valgt treff
  - [x] Tydelige tom-tilstander og treffmarkering
- [x] Ekte `Command Palette`
  - [x] Popup/overlay i stedet for panel
  - [x] Keyboard-first navigasjon
  - [x] Filtrering av kommandoer og konfigurasjoner
  - [x] `Esc` lukker, `Enter` velger
- [x] Run, Debug, Test og CI
  - [x] Egne run configurations
  - [x] Target, arbeidskatalog og args
  - [x] Status, output og feilhåndtering
  - [x] Mer IDE-aktig run/debug bar
  - [x] Debug
  - [x] Test og CI
- [x] Ekte tool windows
  - [x] `Problems`, `References`, `Structure` og `Terminal`
  - [x] Tydelig innhold, preview og navigasjon
  - [x] Rask toggling med tastatur og tool-window-knapper
- [x] `Recent Projects` som i en ekte IDE
  - [x] Åpne eller restore prosjekt direkte
  - [x] Vise status, sist åpnet og kontekst
  - [x] Velg med tastatur, åpne med `Enter`
  - [x] Siste workspace skal være lett å finne igjen
- [x] Klassisk PyCharm-følelse
  - [x] Smalere margins og mer presis spacing
  - [x] Tydeligere typografisk hierarki
  - [x] Konsekvente statuschips, ikoner og paneltitler
  - [x] Bedre tomrom mellom verktøy, innhold og status
- [x] Robusthet for daglig bruk
  - [x] Stabil session-gjenoppretting
  - [x] Ingen skjøre UI-indekser
  - [x] God håndtering av små og store vinduer
  - [x] Ingen krasj ved tom data eller manglende filer
- [x] Kvalitetssikring
  - [x] Tester for alle navigasjons- og redigeringsflyter
  - [x] GUI-smoke test ved oppstart
  - [x] Regression-tester for session/state
  - [x] Visuell sjekk etter hver større UI-endring
- [x] Pakking og finish
  - [x] Ren startkommando
  - [x] Logo, branding og dokumentasjon på plass
  - [x] Kort onboarding i README
  - [x] Samme "føles ferdig"-nivå som en moden IDE

## 12. Ferdigkriterier

- [x] Ingen skjøre UI-hopp
- [x] All navigasjon kan gjøres med tastatur
- [x] `Project`, `Search`, `Editor`, `Run`, `Problems`, `References` og `Terminal` er nyttige i praksis
- [x] Session gjenopprettes riktig
- [x] UI-en er ryddig, konsekvent og lett å skanne
- [x] Tester er grønne og holder seg grønne

## 13. Veien til helt ferdig

- [ ] Bygg semantisk symbolindeks
  - [ ] Parse hele workspace til en stabil symbolmodell
  - [ ] Skil mellom definisjoner, referanser, imports og lokale symboler
  - [ ] Knytt symboler til fil, linje, kolonne og scope
  - [ ] Cache indeks og oppdater inkrementelt ved filendringer
  - [ ] Legg inn testdata for små og store prosjekter
- [ ] Legg inn ekte parser og syntaktisk feildeteksjon
  - [ ] Lag en parser som kan lese hele språkflaten uten å stoppe ved første feil
  - [ ] Rapporter syntaksfeil med tydelige posisjoner
  - [ ] Skil mellom fatal feil og gjenvinnbare feil
  - [ ] Legg inn tester for vanlige syntaksbrudd
  - [ ] Sørg for at parseren kan brukes av diagnostics, completion og rename
- [ ] Gjør `Problems` til ekte diagnostics med fil, linje og severity
  - [ ] Vis error, warning og info
  - [ ] Knytt hver oppføring til fil og linjenummer
  - [ ] Gjør det mulig å hoppe til riktig sted i editoren
  - [ ] Legg inn tomtilstand som forklarer hva som mangler
  - [ ] Test at diagnostics oppdateres når filer endres
- [ ] Implementer completion / autocomplete
  - [ ] Foreslå keywords, builtins og symbols
  - [ ] Rangér treff etter relevans og nylig bruk
  - [ ] La Enter, Tab og pilkeys fungere som i en IDE
  - [ ] Vis korte beskrivelser ved forslag når det er mulig
  - [ ] Legg inn tester for både tom, delvis og fullført input
- [ ] Implementer hover og inline informasjon
  - [ ] Vis symboltype, definisjon og eventuell dokumentasjon
  - [ ] Vis fil- og linjereferanse når data finnes
  - [ ] Håndter tomme eller ukjente symboler rolig
  - [ ] Hold visningen lett og rask, ikke som en modal
  - [ ] Legg inn tester for hover over definisjoner og referanser
- [ ] Implementer signature help
  - [ ] Finn gjeldende funksjonskall og aktiv parameter
  - [ ] Vis parameterliste og markér aktiv parameter
  - [ ] Håndter nested kall og ufullstendige uttrykk
  - [ ] Koble til completion og hover der det passer
  - [ ] Test vanlige kallmønstre og edge cases
- [ ] Gjør rename til ekte refaktorering med trygg preview
  - [ ] Bruk symbolindeks i stedet for ren tekst-erstatning alene
  - [ ] Vis preview før apply
  - [ ] Sjekk kollisjoner og navnekonflikter
  - [ ] Begrens endringer til riktige scopes når det er mulig
  - [ ] Legg inn regresjonstest for rename over flere filer
- [ ] Legg inn formatter / autoformat
  - [ ] Definer grunnleggende formatteringsregler for språkets struktur
  - [ ] Støtt format av fil og format on save
  - [ ] Hold format stabilt så det ikke hopper mellom lagringer
  - [ ] Legg inn tester for typiske kodeformer
  - [ ] Sørg for at formattering ikke bryter eksisterende state
- [ ] Bygg ekte debugger med breakpoints, step og stack
  - [ ] Lag breakpoints i editoren
  - [ ] Vis call stack og lokale variabler
  - [ ] Legg inn step over, step into, step out og resume
  - [ ] Knytt debugger til runtime og run configurations
  - [ ] Legg inn en enkel debug-test som faktisk stopper og fortsetter
- [ ] Gjør run configurations lagbare med args, cwd og env
  - [ ] Lag en modell for navngitte run configurations
  - [ ] Støtt arbeidskatalog, argumenter og miljøvariabler
  - [ ] Gjør aktiv config tydelig i UI
  - [ ] Persistér configs per workspace
  - [ ] Legg inn tester for last/save/restore av configs
- [ ] Bygg et ekte output-panel for run og test
  - [ ] Vis stdout og stderr separat eller tydelig skilte
  - [ ] Vis exit code og status
  - [ ] Gjør output søkbart og scrollbart
  - [ ] Knytt output til valgt run configuration
  - [ ] Legg inn tomtilstand og feiltilstand
- [ ] Legg inn test runner med resultat per test
  - [ ] Oppdag testfiler og testsuiter
  - [ ] Vis pass, fail og skip tydelig
  - [ ] Gi rask navigasjon til feilet linje
  - [ ] Behold historikk for siste kjøring
  - [ ] Legg inn regresjonstester for testflyt
- [ ] Bygg Git / VCS-integrasjon
  - [ ] Vis changed files og diff
  - [ ] Støtt branch status og commit-flyt
  - [ ] Legg inn staging og unstaging hvis det passer modellen
  - [ ] Vis enkel history-view
  - [ ] Legg inn tester for repository-status og endringsvisning
- [ ] Lag settings / preferences for tema, keymap og runtime
  - [ ] Lag en synlig settings-side
  - [ ] Persistér tema, keymap og runtimevalg
  - [ ] Skill mellom globale og workspace-spesifikke innstillinger
  - [ ] Gjør det lett å restore defaults
  - [ ] Legg inn tester for settings persistence
- [ ] Gjør workspace restore fullstendig for tabs, split og panelstate
  - [ ] Husk åpne filer og aktiv tab
  - [ ] Husk split-fokus og panelvalg
  - [ ] Husk søk og siste navigasjon der det er relevant
  - [ ] Restore skal tåle manglende filer uten å krasje
  - [ ] Legg inn regresjonstest for full session restore
- [ ] Utvid project tree med favoritter, recent og åpne filer
  - [ ] Gjør project tree stabil for store mapper
  - [ ] Legg inn favoritter eller pinned files hvis det er nyttig
  - [ ] Vis recent og open files i samme arbeidsflyt
  - [ ] Behold valgt node og scrollposisjon
  - [ ] Legg inn tester for folder-noder og collapse/expand
- [ ] Legg inn ytelses-caching for symboler og filer
  - [ ] Cache workspace-scan og symbolindeks
  - [ ] Rebuild bare det som faktisk endrer seg
  - [ ] Mål oppstartstid og søketid
  - [ ] Unngå at store prosjekt gjør UI tregt
  - [ ] Legg inn enkel perf-regresjonstest eller benchmark
- [ ] Kjør regresjonstester for navigation, rename, completion, diagnostics og debug
  - [ ] Navigation-tester
  - [ ] Rename-tester
  - [ ] Completion-tester
  - [ ] Diagnostics-tester
  - [ ] Debug-tester
  - [ ] Session restore-tester
- [ ] Gjør siste UI-polish på spacing, typografi og ikoner
  - [ ] Stram inn margins og luft
  - [ ] Gjør aktive elementer tydelige
  - [ ] Forbedre tomtilstander og statuslinje
  - [ ] Normaliser ikonbruk og paneltitler
  - [ ] Sjekk layout på små og store vinduer
