## Open Interpreter Analysis

Learn from **Open Interpreter’s control surfaces**, not from its scope.

Open Interpreter is now a large Rust coding-agent system. The current README describes it as a “coding agent for low-cost models,” with harness emulation, native sandboxing, provider/model switching, ACP, MCP, skills, hooks, permissions, and local state under `~/.openinterpreter`. ([GitHub][1])

For `mail_summariser`, the lesson is **not** to become an agent runtime. The lesson is to adopt its discipline around:

* explicit modes;
* local state;
* structured non-interactive execution;
* permissions;
* profiles;
* session resumability;
* project-local instructions.

---

# Add to `mail_summariser`

## 1. Non-interactive CLI first

Open Interpreter’s `interpreter exec` is the right pattern: one task, runs to completion, emits stdout/stderr, optional JSON events, optional output schema. ([Open Interpreter][2])

Add:

```bash
mail-summariser digest --since 24h
mail-summariser digest --account personal --since 7d
mail-summariser inspect --since 24h --json
mail-summariser test-connection
```

This should become the primary interface. FastAPI becomes optional/debug-only.

## 2. Structured output schemas

Open Interpreter supports `--output-schema <file>` to force structured final output. ([Open Interpreter][2])

For `mail_summariser`, define a strict digest schema:

```json
{
  "requires_action": [],
  "deadlines": [],
  "waiting_on_others": [],
  "fyi": [],
  "bulk": [],
  "risks": [],
  "suggested_tags": []
}
```

Then render Markdown from that. The LLM should not directly produce the final digest document.

## 3. Local config with precedence

Open Interpreter uses durable TOML config in `~/.openinterpreter/config.toml`, optional project config, and CLI overrides with clear precedence. ([Open Interpreter][3])

Copy this idea:

```text
~/.mail_summariser/config.toml
.mail_summariser/config.toml
CLI flags
```

Precedence:

```text
defaults < user config < project config < CLI flags
```

Add:

```bash
mail-summariser config debug
```

like Open Interpreter’s `/debug-config`.

## 4. Permission profiles

Open Interpreter’s most relevant design is its permission system: read-only, workspace-write, danger-full-access, plus finer-grained profiles with filesystem/network allow/deny rules. ([Open Interpreter][4]) ([Open Interpreter][5])

For email, map that to mailbox permissions:

```toml
[permissions.read_only]
read_mail = true
write_tags = false
mark_read = false
move_mail = false
send_mail = false

[permissions.tag_suggest]
read_mail = true
write_tags = false
suggest_tags = true

[permissions.tag_write]
read_mail = true
write_tags = true
mark_read = false
move_mail = false
send_mail = false

[permissions.danger_full_access]
read_mail = true
write_tags = true
mark_read = true
move_mail = true
send_mail = true
```

Default should be:

```toml
default_permissions = "read_only"
```

This is more important than UI.

## 5. Approval policy

Open Interpreter separates the technical sandbox from the approval policy: sandbox controls what is possible; approval controls when the agent asks. ([Open Interpreter][4])

For `mail_summariser`:

```toml
approval_policy = "on-request"
```

Meaning:

| Action                | Default        |
| --------------------- | -------------- |
| Read IMAP             | allowed        |
| Write Markdown digest | allowed        |
| Suggest tags          | allowed        |
| Write IMAP tags       | ask            |
| Mark read             | ask            |
| Archive/move          | ask            |
| Send email            | never, for now |

Do not implement autonomous send.

## 6. Local sessions / digest history

Open Interpreter stores sessions locally and supports resume, fork, compact, and history limits. ([Open Interpreter][6])

For `mail_summariser`, use a simpler version:

```text
~/.mail_summariser/
  config.toml
  state.sqlite3
  digests/
    2026-06-18.md
  runs/
    2026-06-18T09-00-00.json
```

Keep:

* last successful run;
* account/folder/UID watermarks;
* digest JSON;
* rendered Markdown;
* model/provider metadata;
* prompt version.

No “conversation” needed.

## 7. “Harness” idea, but renamed

Open Interpreter harnesses change the model-facing prompt, tool schema, message conversion, and response handling while keeping the same runtime. ([Open Interpreter][7])

For `mail_summariser`, this maps well to **digest profiles**, not provider harnesses:

```toml
[digest_profiles.catchup]
goal = "Tell me what changed and what needs attention."

[digest_profiles.deadlines]
goal = "Extract dates, deadlines, commitments, and scheduling risks."

[digest_profiles.reply_queue]
goal = "Find messages likely requiring a reply."

[digest_profiles.admin]
goal = "Find forms, payments, logistics, institutional tasks."
```

CLI:

```bash
mail-summariser digest --profile catchup
mail-summariser digest --profile deadlines
mail-summariser digest --profile reply_queue
```

This gives flexibility without building an agent framework.

## 8. Project guidance file

Open Interpreter supports `AGENTS.md` and command surfaces around project guidance. Its slash command list includes `/init` to create `AGENTS.md`, `/mention`, `/review`, `/skills`, `/hooks`, and status/debug commands. ([Open Interpreter][8])

For `mail_summariser`, add:

```text
.mail_summariser/instructions.md
```

Example:

```markdown
# mail_summariser instructions

Prioritise:
- students;
- CU administrative messages;
- grants;
- deadlines;
- collaborators;
- travel/logistics.

Deprioritise:
- newsletters;
- automated notifications;
- receipts unless overdue;
- promotions.

Never:
- send replies;
- mark messages read;
- archive messages;
- expose full message bodies to cloud models unless explicitly allowed.
```

This should be fed into the summarisation prompt.

---

# Do not copy

## Do not add a daemon yet

Open Interpreter uses a local daemon so repeated launches are fast. ([Open Interpreter][9])

For `mail_summariser`, this is premature. Use a normal CLI plus cron/launchd.

## Do not add TUI/slash commands

No `/model`, `/permissions`, `/resume`, `/skills`, `/mcp`, etc. A small CLI is enough.

## Do not add MCP / ACP / computer use

Open Interpreter supports MCP, ACP, skills, hooks, app tools, and browser/native app testing. ([GitHub][1])

Do not add any of this to `mail_summariser`. Email privacy and correctness are already sufficient complexity.

## Do not add real sandboxing

Open Interpreter needs OS-level sandboxing because it executes arbitrary commands. `mail_summariser` should not execute arbitrary commands except controlled password retrieval. A logical permission model is enough.

---

# Concrete implementation plan

## New files

```text
backend/
  cli.py
  config_loader.py
  permissions.py
  digest_profiles.py
  structured_digest.py
  markdown_renderer.py
  state_store.py
```

## Delete / postpone

```text
webapp/
macos-app/
SMTP summary sending
Ollama lifecycle management
fake-mail runtime mode
undo stack
model download UI
daemon/server lifecycle
```

## Keep

```text
IMAP reading
summary sentinel/fallback
SQLite state
tests
modelito integration
```

## Suggested v0.1 command

```bash
mail-summariser digest \
  --since 24h \
  --profile catchup \
  --permissions read_only \
  --output ~/Obsidian/Email/Digests/2026-06-18.md
```

## Bottom line

Open Interpreter confirms the direction: **power comes from disciplined execution boundaries, not from UI surface**.

For `mail_summariser`, add:

1. CLI-first non-interactive mode.
2. TOML config with precedence.
3. explicit permission profiles.
4. approval policy for any mutation.
5. structured JSON digest before Markdown rendering.
6. local run/session history.
7. digest profiles as the analogue of harnesses.

Do not add agent-runtime complexity.

[1]: https://github.com/openinterpreter/open-interpreter "GitHub - openinterpreter/openinterpreter: A lightweight coding agent for open models like Deepseek, Kimi, and Qwen · GitHub"
[2]: https://www.openinterpreter.com/docs/terminal/exec "Non-Interactive Mode | Open Interpreter Docs"
[3]: https://www.openinterpreter.com/docs/terminal/config "Configuration | Open Interpreter Docs"
[4]: https://www.openinterpreter.com/docs/terminal/sandbox "Sandbox & Approvals | Open Interpreter Docs"
[5]: https://www.openinterpreter.com/docs/terminal/permissions "Permissions | Open Interpreter Docs"
[6]: https://www.openinterpreter.com/docs/terminal/sessions "Sessions | Open Interpreter Docs"
[7]: https://www.openinterpreter.com/docs/terminal/harness "Harness | Open Interpreter Docs"
[8]: https://www.openinterpreter.com/docs/terminal/slash_commands "Slash Commands | Open Interpreter Docs"
[9]: https://www.openinterpreter.com/docs/terminal/daemon "Daemon | Open Interpreter Docs"
