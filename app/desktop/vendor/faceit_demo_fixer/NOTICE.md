# Pinned demo compatibility parser

Upstream: https://github.com/NewTanachot/cs2-faceit-demo-fixer

Commit: `6627fbce1d6ea3f94f604576720602d41006337b`

`demofix.cjs` is the unmodified upstream `demofix.js`, renamed for CommonJS loading. SHA-256: `ef5d03143ef3dca7ed740ab5cfa932bddd87b14e1bb479d00b095cc7c84bd8e8`. Copyright and MIT permission notice are retained in `LICENSE`.

Toolbox runs only this local core through `demo_compat.cjs`, with `sanitizeText: false`. It does not include upstream UI, CLI, analytics, compressed-download pipeline, fonts or network calls. Only the recognized late CChicken baseline pattern is permitted; player/gameplay network messages and frame identities are independently checked. Originals are never output destinations. Private copies remain outside the game installation, are tied to the original download SHA-256, and require separate validation for the installed engine/adapter.
