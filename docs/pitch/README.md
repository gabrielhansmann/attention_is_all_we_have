# Three-minute project pitch

The current presentation is the PowerPoint MCP edition, based on source snapshot `0fa94c3`.
It explains the BMW requirement-evidence engine to a hackathon jury: turn fragmented evidence
into successor requirements the product manager can defend.

- [Editable PowerPoint](bmw-product-intelligence-mcp.pptx)
- [PDF preview](bmw-product-intelligence-mcp.pdf)
- [Timed speaker script](mcp-speaker-script.md)
- [Slide overview](mcp-slide-overview.png)
- [Generation and validation notes](mcp-README.md)
- [PowerPoint MCP setup and usage](mcp-setup.md)

Six main slides are allocated 180 seconds, with a 352-word English script. Three Q&A slides are
hidden in PowerPoint. Speaker notes include timings, delivery cues, sources and claim boundaries.
Advance slides manually; timings are rehearsal targets.

| Time | Slide | Purpose |
|---|---|---|
| 0:00–0:20 | Which customer needs shape the next vehicle? | Establish the PM's decision problem |
| 0:20–0:50 | A shared evidence base | Show the loaded evidence and its provenance |
| 0:50–1:25 | AI proposes. The PM decides. | Explain planning, the backend runner and PM review actions |
| 1:25–2:00 | Every priority has a reason | Explain scoring, separate confidence and decision rationale |
| 2:00–2:35 | A working foundation | Distinguish implemented backend code, sample-data UI and remaining integration |
| 2:35–3:00 | Pilot one vehicle line | Propose the pilot and evaluation measures |

The deck reflects decisions 0014 and 0015: agent modules, the backend runner, Critic checks and
PM review endpoints are implemented and fixture-tested. Full live validation, frontend execution
controls and requirement-backlog writes remain pending. It makes no measured savings, verified
demo recommendation, production readiness or adoption claim.

Edit the current deck through PowerPoint MCP and keep [mcp-pitch.json](mcp-pitch.json) and the
speaker notes aligned. The deprecated draft, its generator and its supporting artifacts have
been removed. The PDF is a separately rendered preview; native Microsoft PowerPoint rendering
was unavailable. Install Inter on the presenting machine for the editable deck's typography.
