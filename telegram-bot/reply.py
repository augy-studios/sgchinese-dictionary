"""Send / edit genuine Telegram Rich Messages (headings, tables) via raw TL requests.

Telethon's high-level ``send_message`` / ``edit_message`` don't expose the
``rich_message`` field, so these helpers build the requests directly. Every
helper takes a ``rich`` dict of the form::

    {"markdown": <Rich Markdown string>, "fallback": <plain text string>}

``fallback`` is what old clients see and what gets sent if Telegram rejects
the rich payload. No parse_mode is used anywhere here - the fallback is plain.
"""

import logging

from telethon import types
from telethon.errors import MessageNotModifiedError
from telethon.tl import functions

logger = logging.getLogger(__name__)


def _rich_markdown(rich: dict) -> types.InputRichMessageMarkdown:
    return types.InputRichMessageMarkdown(markdown=rich["markdown"])


# Editing without reply_markup keeps the old keyboard; an empty inline
# keyboard is what actually removes it.
_NO_BUTTONS = types.ReplyInlineMarkup(rows=[])


def sent_message_id(result) -> int | None:
    """Id of the message a raw send created (bot sends come back as Updates)."""
    if isinstance(result, (types.Message, types.UpdateShortSentMessage)):
        return result.id
    for update in getattr(result, "updates", []):
        if isinstance(update, types.UpdateMessageID):
            return update.id
        if isinstance(update, (types.UpdateNewMessage, types.UpdateNewChannelMessage)):
            return update.message.id
    return None


async def send_rich_message(client, entity, rich: dict, buttons=None):
    markup = client.build_reply_markup(buttons) if buttons else None
    try:
        return await client(functions.messages.SendMessageRequest(
            peer=entity, message=rich["fallback"],
            rich_message=_rich_markdown(rich), reply_markup=markup))
    except Exception as err:
        logger.warning("[send_rich_message] rich send failed, falling back: %s", err)
        return await client.send_message(entity, rich["fallback"], buttons=buttons)


async def edit_rich_message_at(client, peer, msg_id: int, rich: dict, buttons=None) -> None:
    """Edit by chat + message id. No buttons => keyboard removed."""
    markup = client.build_reply_markup(buttons) if buttons else _NO_BUTTONS
    try:
        await client(functions.messages.EditMessageRequest(
            peer=peer, id=msg_id, message=rich["fallback"],
            rich_message=_rich_markdown(rich), reply_markup=markup))
    except MessageNotModifiedError:
        return
    except Exception as err:
        logger.warning("[edit_rich_message_at] rich edit failed, falling back: %s", err)
        await client.edit_message(peer, msg_id, text=rich["fallback"], buttons=buttons)


async def edit_rich_message(client, event, rich: dict, buttons=None) -> None:
    """Edit the message a CallbackQuery came from - regular chat or inline-mode."""
    markup = client.build_reply_markup(buttons) if buttons else None
    is_inline = isinstance(event.query, types.UpdateInlineBotCallbackQuery)
    try:
        if is_inline:
            await client(functions.messages.EditInlineBotMessageRequest(
                id=event.query.msg_id, message=rich["fallback"],
                rich_message=_rich_markdown(rich), reply_markup=markup))
        else:
            await client(functions.messages.EditMessageRequest(
                peer=event.query.peer, id=event.query.msg_id, message=rich["fallback"],
                rich_message=_rich_markdown(rich), reply_markup=markup))
    except MessageNotModifiedError:
        return
    except Exception as err:
        logger.warning("[edit_rich_message] rich edit failed, falling back: %s", err)
        if is_inline:
            await client.edit_message(event.query.msg_id, text=rich["fallback"], buttons=buttons)
        else:
            await client.edit_message(event.query.peer, event.query.msg_id,
                                      text=rich["fallback"], buttons=buttons)
