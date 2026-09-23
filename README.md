# G-code backup indexer / parser

Index CNC machine backup trees into a searchable catalog of **program instances** (by date, machine, source type, and path), so a later recovery step can locate a chosen instance without re-scanning the backup folder.

## Status

**Planning / early setup.** No scanner or parsers are implemented in this repository yet. Architecture and machine roster live in Project Context (Cursor Project docs) until code lands here.

Intended direction (locked in project planning):

- Python + SQLite index (+ Excel export)
- Layout-aware scan: `date/` → `machine/` → select the multi-program “glued” dump → detect control family → parse → normalize → write
- Pluggable parsers per control family (HAAS and FANUC glued dumps expected once samples are available)
- Machine identity via a config alias map (tolerate folder-name drift)

## Non-goals (for now)

- Inventing proprietary glue separators or binary layouts without real backup samples
- Shipping a recovery UI (recovery is a separate consumer of the index)
- Auth, cloud services, or MES/PLM integration

## Repository

Public GitHub home for this project once created and linked. Until then, planning notes remain in the Cursor Project Context.

## License

TBD
