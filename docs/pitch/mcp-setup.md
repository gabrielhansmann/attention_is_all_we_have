# PowerPoint MCP

The requested PowerPoint MCP is installed in this checkout's `.venv-presentation` environment
and registered as **`powerpoint`** in `.codex/config.toml`. It runs locally over stdio and requires
no account or API key. The environment and machine-specific configuration are gitignored;
[the configuration template](mcp-config.toml.example) and [dependency pins](requirements.txt)
are included for teammates.

Provider: [Office PowerPoint MCP Server](https://github.com/GongRzhe/Office-PowerPoint-MCP-Server),
MIT-licensed, pinned to PyPI release `2.0.7`, with MCP SDK `1.26.0`. The upstream repository was
archived in March 2026; this version was verified locally rather than assuming ongoing maintenance.
It exposes **37 tools** in the tested build, including opening, creating and saving presentations,
text extraction and formatting, shapes, images, tables, charts and slide inspection.
The provider's advertised tool count and internal version string differ from the installed release;
the package pin and protocol discovery are the references used here.

## Load into Codex

Open a fresh Codex session in this checkout after adding the server. The current session has
the PowerPoint MCP tools attached directly and used them to create, edit, inspect and save the
[updated MCP pitch](mcp-README.md). The earlier setup also verified the server through the real
MCP SDK stdio client. `codex mcp list` confirms the server is enabled with stdio transport.

Codex supports project configuration at `.codex/config.toml` in trusted projects. Configuration
options are documented in the [official Codex MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Reproduce setup

From the repository root:

```bash
python3 -m venv .venv-presentation
.venv-presentation/bin/pip install -r docs/pitch/requirements.txt
```

Replace `/ABSOLUTE/PATH/TO/REPO` in [mcp-config.toml.example](mcp-config.toml.example) with your
checkout's absolute path. Merge that block into `.codex/config.toml`, preserving existing settings
and servers. The Python command uses `-m ppt_mcp_server --transport stdio`, explicitly selecting
stdio. Both the working directory and the template directory point to `docs/pitch/`.

Verify registration and real file operations:

```bash
codex mcp list
PYTHONPATH=backend .venv-presentation/bin/python -m app.presentation.check_mcp
```

The [protocol check](../../backend/app/presentation/check_mcp.py) opens the nine-slide pitch,
inspects every slide, extracts its text, saves a temporary copy and compares slide XML, notes,
relationships and geometry. It also creates a new presentation, adds formatted text, saves it
and reopens it. Temporary files are removed automatically; the original pitch remains intact.
All these checks passed. The sandboxed protocol handshake stalled in this environment;
the same check passed outside the sandbox, as the configured local server runs normally.

## Use for this pitch

Start by opening `docs/pitch/bmw-product-intelligence-mcp.pptx` with
`open_presentation`, using an explicit ID such as `pitch`. Pass that `presentation_id` to every
subsequent tool. Inspect with `get_presentation_info`, `get_slide_info` and
`extract_presentation_text`; edit with `manage_text` and other relevant tools. Slide indexes
are zero-based, so the main pitch uses indexes 0–5 and hidden Q&A slides use indexes 6–8.
Use `save_presentation` to write a review copy first.

The native deck is editable. Keep [mcp-pitch.json](mcp-pitch.json), speaker notes and MCP edits
aligned. The deprecated draft and its generator have been removed. The server manipulates
PowerPoint files; it does not provide a Microsoft PowerPoint renderer. The supplied PDF is the
independently rendered preview described in [README.md](README.md).
