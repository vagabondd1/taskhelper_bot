import unicodedata

from app.core.config import settings


def sanitize_text(text: str) -> str:
    """Нормализует пользовательский текст перед сохранением/обработкой.

    PostgreSQL не принимает NUL-байт в TEXT — отправка такого текста рушит
    транзакцию. Контрольные символы (кроме \\n и \\t) тоже выкидываем —
    они ломают логи и JSON-encoding. Unicode приводим к NFC.
    """
    if not text:
        return ""
    # NUL и прочие control chars (категория Unicode Cc), кроме \n и \t
    cleaned = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or unicodedata.category(ch) != "Cc"
    )
    return unicodedata.normalize("NFC", cleaned)


def validate_user_input_length(text: str) -> tuple[bool, str | None]:
    """Проверяет длину входящего сообщения.

    Возвращает (ok, error_message).
    Если ok=False — нужно отправить error_message пользователю и не обрабатывать сообщение.
    """
    limit = settings.max_user_message_length
    if len(text) <= limit:
        return True, None
    return False, (
        f"Сообщение слишком длинное: {len(text)} символов.\n"
        f"Максимум — {limit} символов.\n\n"
        "Пожалуйста, сократи текст задачи и отправь снова."
    )
