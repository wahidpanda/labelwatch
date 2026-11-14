# TypeSafe Jev API (placeholder)

Paste the official TypeSafe System One documentation here before enabling `JEV_ENABLED=true`.

Contract used by this repo (verify against https://docs.typesafe.ai/api):

- `POST {TYPESAFE_API_BASE}/v1/systemone` with `Authorization: Bearer` and body `{ "model", "state", "questions" }`.
- Question types: `noul`, `choice`, `score` with calibrated probabilities in `answers`.
