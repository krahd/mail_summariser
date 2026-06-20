## Privemail

`privemail` is useful as a cautionary reference, not as a template.

It confirms that the right product category is **local-first private email intelligence**, but it also shows what `mail_summariser` should avoid: becoming a full browser email client, auto-drafting replies, auto-starting model runtimes, managing OAuth setup UX, and owning Gmail-specific behaviour too early.

The useful target remains:

```text
mail_summariser = local/private email catch-up + digest + optional tags
```

not:

```text
mail_summariser = private Gmail client with AI drafting
```

---

# What `privemail` does

`privemail` describes itself as a private local-first AI email assistant/client. Its README says it connects to Gmail, downloads messages to a local encrypted database, uses local AI models for drafting, tone analysis, and prioritisation, and supports Ollama, LM Studio, LocalAI, or any OpenAI-compatible local server. ([GitHub][1])

Architecturally, it is a FastAPI app with frontend static files, routes for contacts/drafts/inbox/system/groups/setup, a scheduler, Gmail client, local database, and AI-engine adapter layer. The main app mounts static frontend files, decides whether to show setup or app view, starts services, initializes the database, loads secrets, and starts the scheduler if setup is complete.

---

# Adopt

## 1. User-data directory handling

Adopt the idea, not the exact implementation.

`privemail` separates development storage from platform-specific writable app storage: Windows `%APPDATA%/Privemail`, macOS `~/Library/Application Support/Privemail`, Linux `~/.local/share/Privemail`.

For `mail_summariser`, use:

```text
~/Library/Application Support/mail_summariser/
  config.toml
  state.sqlite3
  digests/
  logs/
```

Better: use `platformdirs` rather than hand-rolling path logic.

## 2. Gmail API as an optional backend

`privemail` uses Gmail OAuth via `google-auth-oauthlib` and `google-api-python-client`. Its dependencies include those packages explicitly.

Do **not** make Gmail API the default. But add an optional backend later:

```text
backend = "imap"      # default
backend = "gmail-api" # optional
```

Why: Gmail API gives cleaner incremental sync than IMAP for Gmail accounts. Google’s `users.history.list` returns chronological mailbox changes after a stored `startHistoryId`, and the API explicitly supports storing the returned `historyId` for future requests. ([Google for Developers][2])

## 3. Incremental sync state

The important idea from Gmail is not “use Gmail”; it is **persistent sync watermarks**.

For IMAP:

```text
account_id
folder
uidvalidity
last_uid_seen
last_digest_at
```

For Gmail API:

```text
account_id
last_history_id
last_full_sync_at
```

Google warns that old/invalid Gmail `startHistoryId` values can return HTTP 404 and should trigger a full sync. ([Google for Developers][2]) This maps cleanly to `mail_summariser`: every backend should have a “recover with full rescan” path.

## 4. Local priority score

`privemail` stores a `local_priority_score` on email rows and sorts inbox results by that score.

Adopt the concept, but make it transparent and deterministic.

Suggested fields:

```text
priority_score
priority_reasons[]
deadline_detected
reply_likely
sender_class
thread_activity
```

Do not rely only on LLM tone inference.

## 5. Contact-aware weighting

`privemail` has local `Contact` and `Group` entities with tone, goal, urgency, group, and auto-draft flags.

Adopt a smaller version:

```toml
[people]
vip = [
  "reece.augu...@...",
  "student@example.edu"
]

[domains]
high_priority = ["colorado.edu"]
low_priority = ["newsletter.example"]
```

No contact-management UI for now.

## 6. One-at-a-time local model calls

`privemail` uses a global async lock to prevent concurrent model calls from overloading the machine.  The generation functions acquire that lock before calling the model.

Adopt the principle:

```toml
[model]
max_concurrent_requests = 1
```

This matters for local models on a laptop.

## 7. OpenAI-compatible local provider adapter

`privemail` has a wrapper that routes either to native Ollama or to an OpenAI-compatible `/chat/completions` endpoint, then normalises the response into a common shape.

Adopt this at the `modelito` layer, not inside `mail_summariser`.

Useful providers:

```text
ollama native
openai-compatible local server
LM Studio
llama.cpp server
vLLM
SGLang
```

In `mail_summariser`, keep only:

```python
modelito.summarise(prompt, schema=DigestSchema)
```

## 8. JSON-first AI analysis

`privemail` asks the model to return a single JSON object for correspondent analysis, then parses and validates required keys.

Adopt this strongly. For `mail_summariser`, the model should output structured JSON first:

```json
{
  "requires_action": [],
  "deadlines": [],
  "waiting_on_others": [],
  "fyi": [],
  "bulk": [],
  "suggested_tags": [],
  "risk_notes": []
}
```

Then render Markdown from that. Do not let the LLM directly write the final digest.

---

# Avoid

## 1. Avoid full email-client scope

`privemail` is an email client: inbox view, drafts, contacts, groups, setup wizard, browser frontend, sending, local database, scheduler.

`mail_summariser` should not become that at first. For Tomas's needs MailMate is the client. Outlook remains the CU client. The summariser should produce situational awareness. Future versions, in particular commercial ones should revise this decision.

## 2. Avoid broad OAuth scopes

`privemail` requests Gmail readonly, compose, send, and contacts readonly scopes.

For `mail_summariser`, default to the smallest possible scope.

For Gmail API mode, start with:

```text
https://www.googleapis.com/auth/gmail.readonly
```

Google’s history endpoint allows readonly/metadata scopes, among others. ([Google for Developers][2]) Do not request send/compose unless a later feature absolutely requires it.

## 3. Avoid auto-drafting

`privemail` automatically analyses new emails and generates draft replies unless manual mode is enabled.

Do not adopt this for v0.1.

At most:

```text
suggested_reply_intent: "reply needed"
```

not:

```text
generated_draft: "..."
```

Drafting is a separate later tool.

## 4. Avoid auto-starting Ollama

`privemail` starts `ollama serve` via `subprocess.Popen` if the local server is not detected.

Do not adopt. It creates process lifecycle ambiguity and failure modes.

Use:

```text
Ollama unavailable: fail clearly.
```

For v0.1 the user should own model runtime management. Use modelito for everything Ollama. 

## 5. Avoid storing master passwords in JSON

`privemail` writes the master password to `secrets.json`.

Do not adopt.

Use macOS Keychain via `keyring`, `security`, or explicit password commands:

```toml
password_command = "security find-internet-password -s imap.example.com -a user@example.com -w"
```

## 6. Avoid its encryption pattern as-is

`privemail`’s database model tries to import `core.encryption.EncryptedText`, but falls back to plain SQLAlchemy `Text` if unavailable.  The visible `src/core` directory lists `ai.py`, `config.py`, `licensing.py`, and `path_utils.py`, but not `encryption.py`. ([GitHub][3])

There is also an encryption manager deriving a Fernet key from a master password with `APP_SALT = os.urandom(16)`, which is not shown as persisted in that file.  If used for durable encryption, a non-persisted random salt would be wrong.

For `mail_summariser`: do not implement database encryption hastily. Better:

1. store minimal local content;
2. support “headers only” mode;
3. use OS keychain for credentials;
4. later use SQLCipher or a carefully designed encrypted store.

---

# Other sources worth learning from

## 1. Notmuch

Notmuch is the strongest architectural reference. It explicitly separates search/index/tagging from mail receiving/sending/UI, and its homepage describes it as fast global search and tag-based email without giving a third party access to your email. ([Notmuch Mail][4])

Its manual says Notmuch indexes, searches, reads, and tags large email collections; it also makes clear that more sophisticated interfaces are expected to be built on top of the CLI/library. ([Notmuch Mail][5])

Adopt:

```text
mail_summariser should be Notmuch-like:
small core, scriptable, index/tag/digest, no client ambitions.
```

## 2. mbsync / isync

`mbsync` synchronises IMAP4 and Maildir mailboxes, propagating new messages, deletions, and flag changes; sync operations are configurable, and there is a dry-run mode. ([iSync][6])

Adopt as optional backend strategy:

```text
mbsync → Maildir → notmuch → mail_summariser digest
```

This avoids writing your own robust IMAP synchroniser.

## 3. Maildir

Maildir is useful because it stores each message as a separate file, with `tmp`, `new`, and `cur` directories. It avoids some locking problems and is widely supported. ([Wikipedia][7])

Adopt as the preferred local corpus format if you move away from direct IMAP.

## 4. Lieer / gmailieer

Lieer is directly relevant for Gmail users: it provides fast fetching/sending and two-way tag synchronisation between Notmuch and Gmail. ([GitHub][8]) Its README shows the `gmi init` OAuth flow, `gmi pull`, `gmi push`, and token storage in a local credentials file. ([GitHub][8])

Adopt:

```text
Study Lieer’s Gmail label ↔ notmuch tag mapping.
```

Do not reimplement Gmail sync unless necessary.

---

# Concrete additions to `mail_summariser`

## Add now

```text
backend/
  config_loader.py
  credential_resolver.py
  digest_schema.py
  markdown_renderer.py
  priority.py
  state_store.py
```

## Add config

```toml
[privacy]
mode = "local_only"
store_bodies = false
store_body_excerpt_chars = 1200
allow_cloud_models = false

[model]
provider = "modelito"
max_concurrent_requests = 1

[output]
directory = "~/Obsidian/Email Digests"

[permissions]
read_mail = true
write_tags = false
mark_read = false
send_mail = false
```

## Add digest schema

```python
class DigestItem(BaseModel):
    account: str
    folder: str
    message_ref: str
    sender: str
    subject: str
    reason: str
    confidence: float

class Digest(BaseModel):
    requires_action: list[DigestItem]
    deadlines: list[DigestItem]
    waiting_on_others: list[DigestItem]
    fyi: list[DigestItem]
    bulk: list[DigestItem]
    suggested_tags: list[dict]
```

## Add backend abstraction

```python
class MailBackend(Protocol):
    def fetch_changes(self, since: SyncCursor) -> list[MessageSummary]: ...
    def get_message(self, ref: str) -> MessageContent: ...
```

Implement in order:

1. `imap_readonly`
2. `maildir_notmuch`
3. `gmail_api`, later

---

# Do not add yet

```text
browser email client
contacts/groups UI
automatic reply drafts
automatic sending
automatic archiving
Ollama process management
paid installer / packaging
license server
auto-update
```

`privemail`’s roadmap includes packaging, license server, auto-update, tracker blocking, contact/group management, and full local-client ambitions. ([GitHub][9]) None of that belongs in `mail_summariser` yet.

---

# Revised direction

The best synthesis is:

```text
Notmuch architecture
+ mbsync/Maildir ingestion
+ optional Gmail API history sync
+ modelito local model calls
+ Privemail-style local priority scoring
+ JSON-first digest
+ Markdown output
```

Implementation priority:

1. **Read-only IMAP or Maildir ingestion**
2. **Persistent sync cursor**
3. **Structured digest JSON**
4. **Markdown renderer**
5. **Priority scoring**
6. **Optional notmuch tags**
7. **Optional Gmail API backend**

The main thing to learn from `privemail`: **privacy is a product architecture, not a slogan**. Its local-first framing is right; its email-client scope is too large for your current goal.

[1]: https://github.com/safhac/privemail "GitHub - safhac/privemail: **Privemail** is an open-source, local-first email client designed for privacy and speed. · GitHub"
[2]: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list "Method: users.history.list  |  Gmail  |  Google for Developers"
[3]: https://github.com/safhac/privemail/tree/master/src/core "privemail/src/core at master · safhac/privemail · GitHub"
[4]: https://notmuchmail.org/ "notmuch"
[5]: https://notmuchmail.org/doc/latest/man1/notmuch.html "notmuch — notmuch 0.40 documentation"
[6]: https://isync.sourceforge.io/mbsync.html "mbsync"
[7]: https://en.wikipedia.org/wiki/Maildir?utm_source=chatgpt.com "Maildir"
[8]: https://github.com/gauteh/lieer "GitHub - gauteh/lieer: Fast email-fetching, sending, and two-way tag synchronization between notmuch and GMail · GitHub"
[9]: https://github.com/safhac/privemail/blob/master/ROADMAP.md "privemail/ROADMAP.md at master · safhac/privemail · GitHub"
