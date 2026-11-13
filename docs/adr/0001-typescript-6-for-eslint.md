# 0001: Pin TypeScript 6.0 in the frontend

Date: 2026-11-13. Status: accepted.

## Context

The Vite `react-ts` template now ships TypeScript 7 and oxlint. The spec (section 15) requires
eslint in pre-commit and CI. typescript-eslint 8.72 declares `typescript >=4.8.4 <6.1.0` as its
peer range, so type-aware eslint rules do not support TypeScript 7 yet.

## Decision

Use eslint with typescript-eslint `strictTypeChecked` and pin `typescript ~6.0.3`. Drop oxlint.

## Consequences

Revisit when typescript-eslint supports TypeScript 7; upgrading is a dependency bump only.
