# PowerPoint MCP edition

[Editable PowerPoint](bmw-product-intelligence-mcp.pptx) ·
[PDF preview](bmw-product-intelligence-mcp.pdf) ·
[Speaker script](mcp-speaker-script.md) ·
[Slide overview](mcp-slide-overview.png)

Six main slides have 180 seconds allocated, with a 352-word English script. Three Q&A slides
are hidden in PowerPoint. Every slide contains speaker notes, claim boundaries and source paths.
The BMW palette, Inter typography, editable diagrams and actual sample-data workspace screenshot
are retained from the earlier pitch.

The source snapshot is `0fa94c3`. Decisions 0014 and 0015 establish that all agent modules and the
backend runner, Critic checks and PM step actions are implemented and fixture-tested. Their full
live path remains unvalidated. The frontend execution controls and requirement-backlog writes
remain the next integration; outputs currently live on steps. These distinctions are reflected
in the visible slides and spoken script. No measured performance or adoption result is claimed.

## Generation

The attached `powerpoint` MCP created a new presentation from the earlier nine-slide deck with
`create_presentation_from_template`. Its `manage_text` tool changed 17 native text shapes;
`set_core_properties` updated the document metadata, and `save_presentation` wrote this edition.
The earlier draft and its supporting artifacts have since been removed.

Local finishing updated speaker notes from [mcp-pitch.json](mcp-pitch.json), preserved hidden
backup slides, and repaired the server's `format_runs` behavior, which inserts a leading blank
paragraph. Font metrics were used to wrap replacement text within the existing geometry. The
finished file was reopened, inspected and saved again through PowerPoint MCP.

For further MCP edits, open `bmw-product-intelligence-mcp.pptx` with an explicit presentation ID.
Slide indexes 0–5 are the main pitch; indexes 6–8 are hidden Q&A. Keep visible copy, notes and
`mcp-pitch.json` aligned. The deprecated draft generator has been removed; this deck is maintained
through PowerPoint MCP.

## Validation

The PowerPoint package, all nine slide contents, note sources, slide bounds, text fit, 180-second
allocation and three hidden backups were checked. The complete preview was visually inspected.
[Validation metadata](mcp-validation.json) records the source snapshot and checks. The final MCP
save was checked for preservation of slide XML, notes, relationships and dimensions.

The PDF is a separately rendered preview derived from the actual saved slide geometry, not a
Microsoft PowerPoint export. Native Microsoft PowerPoint rendering was unavailable. Use Inter
on the presenting machine for the editable deck's intended typography, or use the PDF.
