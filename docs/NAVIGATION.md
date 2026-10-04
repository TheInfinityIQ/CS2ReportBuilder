# Optional file discovery

Open a known source directly. Use targeted file/content search when you know a
name, phrase, or symbol. If the location is unclear, open one relevant 00_INDEX.md
or query the catalog. Do not read maps just to satisfy an onboarding step or
recursively traverse them.

README.md is the project entry; AGENTS.md is the working agreement. The old hats,
router, and precedence hierarchy are retired. Maps describe locations, not authority.

## Existing tools

scripts/navigation.py builds repository maps and a searchable catalog. Its local
profile covers authored folders and batches without writing inside isolated coach
packets. Git, environments, browser profiles, credentials, and caches are excluded.
Descriptions are labeled curated, extracted, or filename; originals establish
content. A six-pair pilot found mixed discovery costs, including overhead with
already known paths. It measured characters, not billed tokens.

The generator remains installed to preserve existing CI checks during cleanup.
Redesign or retirement is a separate evidence-backed choice, not part of this batch.

## Search

```powershell
python scripts/navigation.py find --under docs/history --query coaching --limit 5
python scripts/navigation.py find --root ../demoparser --profile data --query ClaudeCoachingReportsTest --limit 5
```

Terms are ANDed and match metadata, not full contents. Start with one or two
distinctive terms under a relevant directory; use rg for content search. Use
returned paths instead of guessing moved locations. The command still returns
maintenance metadata; concise display is a potential improvement, not implemented.

## Freshness after source changes

While this generator is installed, regenerate and check affected trees:

```powershell
python scripts/navigation.py build
python scripts/navigation.py check
python scripts/navigation.py build --root ../demoparser --profile data
python scripts/navigation.py check --root ../demoparser --profile data
```

Run only profiles affected by the change. Curated summaries bind to source hashes;
review changed sources and update descriptions deliberately. Do not accept new
hashes merely to pass CI. Repository output is versioned; local output remains
local. Freshness does not prove truth, coaching quality, or external-document sync.

History ordering uses explicit document/filename dates and natural versions.
Dates do not establish acceptance; file modification times do not prove chronology.
Update affected current references without an all-log sweep or role announcements.
