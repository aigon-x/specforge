# CRITIQUE — SpecForge (sceptyk, 2026-10-20)

Zakres: README/ARCHITECTURE/DEVPOST/EVIDENCE, `specforge/`, `tests/`, regulamin Nebius x NVIDIA.
Pomiar: `pytest tests -q` → 46 passed; `forge --offline` → 15 ops/13 schemas; `sha256sum` zgodny z EVIDENCE:143.
Nie zmieniałem kodu. Repo publiczne (GitHub API: private=false, license=MIT) — checklista jest nieaktualna.

## Oceny 0–100

| Kategoria | Ocena | Uzasadnienie |
|---|---:|---|
| Technical execution | 68 | Modularny, typowany kod, 46 testów, determinizm, dobre kody błędów. Minusy: brak pakowania/CI, nieprzetestowany realny transport HTTP, bug operationId, testy kontraktowe bez cyklu życia. |
| Innovation | 42 | Brief→OpenAPI→verify→testy to znany pipeline; LLM tylko przerabia prozę. Brak pętli agenta, brak Nemotron. |
| Użycie Nebius (czy nie atrapa) | 12 | Zero wywołań runtime; domyślny model to Meta-Llama, nie NVIDIA; fixture zaszyty pod `shop.yaml`; usunięcie Nebius zmienia tylko opisy. |
| Jakość dowodów | 55 | Uczciwe, odtwarzalne, hashe się zgadzają, ścieżki negatywne pokazane. Ale dowód dotyczy wyłącznie offline; 45 testów kontraktowych to `45 skipped`, nigdy nie wykonanych. |
| Zgodność z wymogami | 30 | Publiczne repo + MIT + README = OK. Brak: runtime call do Token Factory, NVIDIA open source model, URL działającego demo, wideo. |
| Ryzyko odrzucenia (wyżej = gorzej) | 75 | Stage One (pass/fail) może paść na „reasonably applies the required APIs/SDKs". |

**Średnia: 41/100.** Najsłabsze ogniwo: użycie Nebius (12), nie kod.

## 5 słabości z dowodem

1. **Wymóg „NVIDIA open source model" nie jest spełniony.** `specforge/nebius.py:18` ustawia
   `meta-llama/Meta-Llama-3.1-8B-Instruct`. W całym repo „Nemotron"/„NVIDIA" występuje tylko
   w nazwie hackathonu — `grep` po `*.py/*.yaml` daje 0 trafień. Stage One może to odrzucić.
2. **Brak jakiegokolwiek runtime call do Token Factory.** `README.md:124` i `DEVPOST_DRAFT.md:157`
   mówią wprost, że live nie był uruchomiony. Regulamin: „makes a runtime call to the Token Factory
   inference API" — dowodu nie ma (`EVIDENCE.md` pokazuje tylko `mode: OFFLINE`).
3. **Fixture to atrapa pod jeden brief.** `specforge/fixtures/nebius_fixture.json:8` ma na sztywno
   `listProducts` itd. Dla innego briefu (test: `Category`) enrichment aplikuje 0 operacji, ale
   nadal raportuje 3 ambiguities o `price_cents`/`Order` — fałszywy wynik (`enrich.py:108-117`).
4. **„Runnable" testy kontraktowe nie są runnable end-to-end.** `contract_tests.py:10` wstawia stały
   UUID; wygenerowany `test_deleteCustomer_happy` (`/tmp/.../test_contract_shop.py:95-98`) żąda 204
   dla nieistniejącego zasobu. Na realnym serwisie test padnie; udowodniono tylko `45 skipped`.
5. **Brak URL demo i wideo.** `SUBMISSION-CHECKLIST.md:14-15`: demo BLOKADA, wideo BRAK;
   `DEVPOST_DRAFT.md:128` ma `<VIDEO_URL_PLACEHOLDER>`. Regulamin wymaga URL działającego demo.
   Dodatkowo: `generator.py:120` tworzy `listCategorys` (potwierdzone forge'em), brak `pyproject.toml`
   i `requirements.txt` — instalacja to ręczne `pip install pyyaml`.

## 5 ulepszeń wg wpływu

1. **Realny, zgodny z regulaminem Nebius.** Domyślny model Nemotron + live smoke test z zapisanym
   request/response i latency; fixture generowany z briefu, nie ręczny. Dowód: `nebius.py:18`,
   `fixtures/nebius_fixture.json:8`.
2. **Publiczne demo URL** (hosted CLI/HTTP wrapper lub GitHub Action „try it") + wideo ≥1 min.
   Dowód: `SUBMISSION-CHECKLIST.md:14-15`, `DEVPOST_DRAFT.md:128`.
3. **Testy kontraktowe z cyklem życia**: create→id→get/update/delete, unikalne dane, cleanup,
   asercje na 404 po delete. Dowód: `contract_tests.py:10,59-67`.
4. **Usunięcie sprzężenia fixture↔brief**: proza generowana z operationId/requirements albo
   live-only; ambiguities nie mogą być stałą listą. Dowód: `enrich.py:108-117`.
5. **Poprawka operationId + pakowanie + CI**: liczba mnoga przez regułę, `pyproject.toml`,
   workflow z `pytest` i `verify` na wygenerowanym specu. Dowód: `generator.py:120`.
   (Alternatywa o podobnym wpływie: walidacja zewnętrznym `openapi-spec-validator`.)

## Czy wygenerowany OpenAPI jest realnie użyteczny?

To **prawdziwy, poprawny składniowo OpenAPI 3.1** (6 ścieżek, 15 operacji, 13 schematów, RFC 9457,
`readOnly`, Input/Update, `additionalProperties:false`, 401/404/409/422), ale **szkielet CRUD, nie
kontrakt produkcyjny**: brak `examples`, opisów pól, ETag/If-Match, 429/Retry-After, sortowania,
paginacji kursorowej i linków. Wartość: dobry start dla prostego CRUD i demo pipeline'u; dla realnego
API trzeba go ręcznie pogłębić. To artefakt pod publikę bardziej niż narzędzie gotowe do wdrożenia.

## Werdykt

Solidne rzemiosło inżynierskie wokół słabego rdzenia hackathonowego. Największe ryzyko to nie kod,
lecz Stage One: brak NVIDIA modelu i brak udowodnionego runtime call do Token Factory.
