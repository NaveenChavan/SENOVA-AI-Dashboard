# Documentation index

Project-level docs, in the order they're most useful to read.

| Doc | What it covers |
|---|---|
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Start here — what SENOVA is, how it's built, how every part works. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Deep technical reference: API contracts, calculation formulas, data flow. |
| [`PRO_UPGRADE.md`](PRO_UPGRADE.md) | Everything built in the Pro upgrade (insights, forecasting, inventory, filters, chart engine). |
| [`UI_ACCURACY_PASS.md`](UI_ACCURACY_PASS.md) | Design-system rebuild + accuracy audit that re-derived every published number. |
| [`CHANGELOG-UI-REDESIGN.md`](CHANGELOG-UI-REDESIGN.md) | Detailed changelog for the 2026-07-29 frontend redesign. |
| [`CHANGELOG_SESSION.md`](CHANGELOG_SESSION.md) | Full audit changelog (bugs, security, performance, code quality). |
| [`UPGRADES.md`](UPGRADES.md) | Design spec for a planned upgrade (history, WhatsApp sharing, reorder point) — not yet implemented. |
| [`SESSION_2026-07-31_AUTH_SYSTEM.md`](SESSION_2026-07-31_AUTH_SYSTEM.md) | Auth system session: Google + Email/Password sign-in, email verification, account deletion, security hardening, and the phone-auth build-then-remove story. |

The repo root [`README.md`](../README.md) stays at the top level as the
main entry point (what shows on GitHub, install/run instructions). The
`testing/` and `testing2/` folders each keep their own `README.md`
describing their sample files — those are local to that data, not
project-wide docs, so they weren't moved here.
