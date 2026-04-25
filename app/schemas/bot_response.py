from typing import Optional
from pydantic import BaseModel


class BotResponse(BaseModel):
    """Результат обработки действия пользователя — передаётся в Telegram-слой."""

    text: str
    show_guided_menu: bool = False
    show_mode_selector: bool = False
    show_full_solution_menu: bool = False
    show_start_menu: bool = False
    show_end_of_plan_menu: bool = False
    start_menu_with_exit: bool = False
    remove_keyboard: bool = False
    error: bool = False
