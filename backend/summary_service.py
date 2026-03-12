def summarize_messages(messages: list[dict], summary_length: int) -> str:
    """Demo summarizer.

    Replace this with an OpenAI API call or another local/remote summarizer.
    `summary_length` is an integer from 1 to 10.
    """
    level = max(1, min(summary_length, 10))

    intro = {
        1: "Very terse digest",
        2: "Brief digest",
        3: "Compact digest",
        4: "Short digest",
        5: "Balanced digest",
        6: "Expanded digest",
        7: "Detailed digest",
        8: "Rich digest",
        9: "Very detailed digest",
        10: "Comprehensive digest",
    }[level]

    lines = [intro, "", f"Messages summarized: {len(messages)}", ""]

    for idx, message in enumerate(messages, start=1):
        body = message.get("body", "").strip().replace("\n", " ")
        excerpt_length = 60 + level * 18
        excerpt = body[:excerpt_length]
        lines.append(f"{idx}. {message['sender']} — {message['subject']}")
        lines.append(f"   {excerpt}")
        if level >= 5:
            lines.append("   Action: review and decide whether a reply is needed.")
        lines.append("")

    if level >= 7:
        lines.append("Overall themes:")
        lines.append("- Follow-ups and planning")
        lines.append("- Items that may need a response")

    return "\n".join(lines).strip()
