from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

_TG_MAX_LEN = 4096
Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup | ReplyKeyboardRemove | None


def _has_code_block(text: str) -> bool:
    """Markdown включаем ТОЛЬКО когда в ответе есть fenced-блок кода.

    Текст пользователя содержит звёздочки/подчёркивания/скобки чаще, чем
    осмысленный markdown — Telegram-парсер падает, sender ретраит plain,
    каждый ответ стоит двух API-запросов. Раньше parse_mode=MARKDOWN был
    глобальным, теперь — точечный.
    """
    return "```" in text


async def send_response(
    message: Message,
    text: str,
    reply_markup: Markup = None,
) -> None:
    """Отправляет ответ пользователю.

    Если текст длиннее 4096 символов — разбивает на части.
    Markdown применяется только когда есть fenced code (```);
    при ошибке парсинга — fallback на plain text.
    """
    parts = _split(text)
    use_markdown = _has_code_block(text)

    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        await _send_part(message, part, markup, use_markdown)


async def _send_part(
    message: Message,
    text: str,
    reply_markup: Markup,
    use_markdown: bool,
) -> None:
    if not use_markdown:
        await message.answer(text, reply_markup=reply_markup)
        return
    try:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception:
        await message.answer(text, reply_markup=reply_markup)


def _split(text: str) -> list[str]:
    if len(text) <= _TG_MAX_LEN:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= _TG_MAX_LEN:
            parts.append(text)
            break
        # Разрезаем по последнему переносу строки в пределах лимита
        cut = text.rfind("\n", 0, _TG_MAX_LEN)
        if cut == -1:
            cut = _TG_MAX_LEN
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts
