from typing import Optional
from pydantic import BaseModel


class BotResponse(BaseModel):
    """Результат обработки действия пользователя — передаётся в Telegram-слой."""

    text: str
    show_guided_menu: bool = False
    show_mode_selector: bool = False
    error: bool = False
