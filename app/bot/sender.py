from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, Message

_TG_MAX_LEN = 4096


async def send_response(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет ответ пользователю.

    Если текст длиннее 4096 символов — разбивает на части.
    Пробует Markdown; при ошибке форматирования отправляет plain text.
    """
    parts = _split(text)

    for i, part in enumerate(parts):
        markup = reply_markup if i == len(parts) - 1 else None
        await _send_part(message, part, markup)


async def _send_part(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> None:
    try:
        await message.answer(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception:
        # Если Markdown не парсится (спецсимволы в тексте) — отправляем plain
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
