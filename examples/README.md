# Web-eksempelapper

Dette mappen inneholder små, kopierbare web-eksempler for Norscode.

## Eksempler

- `web_hello_api.no`: en enkel hello-world API med OpenAPI
- `web_crud_sample.no`: et lite CRUD-eksempel med validering
- `web_auth_protected.no`: et auth-beskyttet route-eksempel
- `web_json_service.no`: en liten JSON-tjeneste

## Kjøring

Hvert eksempel kan kjøres direkte:

- `norscode run examples/web_hello_api.no`
- `norscode run examples/web_crud_sample.no`
- `norscode run examples/web_auth_protected.no`
- `norscode run examples/web_json_service.no`

GUI-demoen kan åpnes lokalt i et vindu med:

- `norscode gui examples/gui_demo.no`

Hvis du vil tvinge browser:

- `norscode gui --gui-backend browser examples/gui_demo.no`

De har også små `test`-blokker, så du kan verifisere dem med:

- `norscode test examples/web_hello_api.no`
- `norscode test examples/web_crud_sample.no`
- `norscode test examples/web_auth_protected.no`
- `norscode test examples/web_json_service.no`
