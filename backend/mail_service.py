from schemas import SearchCriteria


def demo_search(criteria: SearchCriteria) -> list[dict]:
    """Replace this with real IMAP/MailMate integration.

    Expected future behavior:
    - translate SearchCriteria into IMAP search terms and/or a MailMate helper query
    - fetch matching message metadata and bodies
    - return stable message identifiers plus text bodies
    """
    sample_messages = [
        {
            "id": "msg-001",
            "subject": "Project update",
            "sender": "alice@example.com",
            "recipient": "you@example.com",
            "date": "2026-03-10T09:00:00",
            "body": "The project is on track. Key decisions are pending on budget and the deployment schedule.",
            "unread": True,
            "tag": "work",
        },
        {
            "id": "msg-002",
            "subject": "Invoice question",
            "sender": "bob@example.com",
            "recipient": "you@example.com",
            "date": "2026-03-10T10:00:00",
            "body": "Can you confirm the invoice line items and whether travel costs are billable this month?",
            "unread": True,
            "tag": "finance",
        },
        {
            "id": "msg-003",
            "subject": "Reading group",
            "sender": "carol@example.com",
            "recipient": "team@example.com",
            "date": "2026-03-09T17:30:00",
            "body": "Reminder that tomorrow's reading group starts at 4 pm. Please send your paper suggestions.",
            "unread": False,
            "tag": "academic",
        },
    ]

    results: list[dict] = []
    for message in sample_messages:
        checks: list[bool] = []

        if criteria.keyword:
            haystack = f"{message['subject']} {message['body']}"
            checks.append(criteria.keyword.lower() in haystack.lower())
        if criteria.sender:
            checks.append(criteria.sender.lower() in message["sender"].lower())
        if criteria.recipient:
            checks.append(criteria.recipient.lower() in message["recipient"].lower())
        if criteria.tag:
            checks.append(criteria.tag.lower() == message["tag"].lower())
        if criteria.unreadOnly:
            checks.append(bool(message["unread"]))
        if criteria.readOnly:
            checks.append(not bool(message["unread"]))

        if not checks:
            results.append(message)
        elif criteria.useAnd and all(checks):
            results.append(message)
        elif not criteria.useAnd and any(checks):
            results.append(message)

    return results


def mark_messages_read(message_ids: list[str]) -> None:
    # Replace with IMAP \Seen or MailMate-specific command.
    _ = message_ids


def add_keyword_tag(message_ids: list[str], tag: str) -> None:
    # Replace with IMAP keyword add or MailMate integration.
    _ = (message_ids, tag)


def remove_keyword_tag(message_ids: list[str], tag: str) -> None:
    # Replace with IMAP keyword remove.
    _ = (message_ids, tag)


def send_summary_email(recipient: str, subject: str, body: str) -> None:
    # Replace with SMTP or MailMate `emate` command.
    _ = (recipient, subject, body)
