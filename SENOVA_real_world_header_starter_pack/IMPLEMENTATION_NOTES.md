# Implementation Notes for Antigravity

1. Inspect the existing repository dictionary, alias map, semantic catalog and tests first.
2. Read `verified_header_starter.csv`; do not blindly append every proposed role to production aliases.
3. Compare normalized header + role pairs against current entries:
   - exact duplicate, same role: dedupe and preserve all source provenance if supported;
   - same normalized phrase, conflicting roles: write to a conflict report, do not auto-merge;
   - ambiguous candidate: keep marked ambiguous or require evidence; do not force-map.
4. Verify literal header spelling against downloadable sample files/export schemas wherever possible. Mark entries as `verified` only after checking an actual template/CSV/XLSX or authoritative schema that specifies the exact header.
5. Never download real customer exports or include customer values. Headers only; redact any accidentally encountered PII.
6. Preserve pipeline order: dictionary/aliases -> FastEmbed -> Gemini only for unresolved headers and only with explicit consent. Never send customer/name-like or unidentified column values to Gemini.
7. Add snapshot tests to prove old aliases still resolve identically. Add tests for new entries, conflicts, ambiguity and source provenance.
8. Run existing backend and frontend test suites and the electronics regression dataset before merging.
9. Report counts separately: source rows, unique normalized headers, verified exact headers, candidate-only fields, duplicate entries, conflicts, dictionary-resolved test headers, false mappings, unresolved headers.
10. This starter pack does not claim completeness or actual download of vendor templates. Use the official URLs to obtain exact sample templates if the environment permits; otherwise list those as manual follow-ups.
