from app.core.config import settings


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
