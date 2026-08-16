from __future__ import annotations


def bot_was_added_to_chat(update: dict, bot_id: int | None) -> int | None:
    if bot_id is None:
        return None
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    for member in message.get("new_chat_members") or []:
        if member.get("is_bot") and member.get("id") == bot_id:
            return int(chat_id)
    return None
