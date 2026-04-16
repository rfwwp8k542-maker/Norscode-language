# Norscode Studio v2

Dette er arbeidsmappen for den nye Studio-appen som skal skrives i Norscode.

## Innhold

- [Roadmap](ROADMAP.md)
- [Checklist](CHECKLIST.md)
- [Next steps](NEXT_STEPS.md)
- [Migrasjon](MIGRATION.md)
- [Stabilisering](STABILIZATION.md)
- AI-integrasjon som egen modulkontrakt
- Ny appstruktur for editor, workspace, symbolindeks, symbolnavigasjon og kommandosurface
- Workspace-snapshoten gjenbrukes ved oppstart, så store prosjekter slipper unødvendige gjenlesinger
- Symbolindeksen leser Norscode-kilder fra workspace og gjør Def/Bruk-oppslag mulig
- Studio v2 kan hoppe til definisjoner og liste referanser via symbolindeksen
- Studio v2 har også enkel hurtignavigasjon for filer og en symbolpalett
- Renames kan forhåndsvises som tekst før de brukes
- Studio v2 kjører nå som terminal/headless-variant, og vi jobber videre med en egen native GUI-front

## Retning

- Studio v2 er en ny app, ikke en videreføring av den gamle GUI-koden
- AI skal være en hjelpefunksjon, ikke en nødvendig avhengighet
- Arbeidet starter med grunnmur, editor, workspace og symbolindeks, før AI legges på toppen
- Bruk `make studio-v2` eller `./scripts/studio-v2.sh` for å starte grunnmuren via native launcher
- I terminal- og CI-miljøer velger kommandoen headless automatisk
- Hvis binæren mangler, bygg den først med `bash scripts/build-standalone.sh`
- Bruk `./dist/norscode studio-v2` når du vil starte Studio v2 i terminal/headless-modus
