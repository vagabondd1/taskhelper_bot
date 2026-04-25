from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BTN_HINT = "💡 Подсказка"
BTN_NEXT_STEP = "➡️ Следующий шаг"
BTN_VALIDATE_IDEA = "✅ Проверить идею"
BTN_EXPLAIN = "📖 Объяснить"
BTN_CODE_HINT = "💻 Подсказка по коду"
BTN_THIS_IS_WRONG = "❌ Это неверно"
BTN_SHARE_THINKING = "🧠 Мой контекст"

BTN_MODE_GUIDED = "🧩 Шаг за шагом"
BTN_MODE_FULL_SOLUTION = "📋 Полное решение"

BTN_DESCRIBE_TASK = "✍️ Описать задачу"
BTN_EXIT = "🚪 Завершить"
BTN_CLEAR = "🧹 Очистить чат"


GUIDED_BUTTONS = {
    BTN_HINT, BTN_NEXT_STEP, BTN_VALIDATE_IDEA,
    BTN_EXPLAIN, BTN_CODE_HINT, BTN_THIS_IS_WRONG,
    BTN_SHARE_THINKING,
}

MODE_SELECTOR_BUTTONS = {BTN_MODE_GUIDED, BTN_MODE_FULL_SOLUTION}

FULL_SOLUTION_BUTTONS = {BTN_MODE_GUIDED}

START_BUTTONS = {BTN_DESCRIBE_TASK, BTN_CLEAR}

ALL_MENU_BUTTONS = (
    GUIDED_BUTTONS | MODE_SELECTOR_BUTTONS | FULL_SOLUTION_BUTTONS
    | START_BUTTONS | {BTN_EXIT}
)


def _kb(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
    )


def guided_menu() -> ReplyKeyboardMarkup:
    return _kb([
        [BTN_HINT, BTN_NEXT_STEP],
        [BTN_VALIDATE_IDEA, BTN_SHARE_THINKING],
        [BTN_EXPLAIN, BTN_CODE_HINT],
        [BTN_THIS_IS_WRONG],
        [BTN_EXIT],
    ])


def mode_selector() -> ReplyKeyboardMarkup:
    return _kb([
        [BTN_MODE_GUIDED, BTN_MODE_FULL_SOLUTION],
        [BTN_EXIT],
    ])


def full_solution_menu() -> ReplyKeyboardMarkup:
    return _kb([
        [BTN_MODE_GUIDED],
        [BTN_EXIT],
    ])


def start_menu(has_active_session: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[str]] = [[BTN_DESCRIBE_TASK, BTN_CLEAR]]
    if has_active_session:
        rows.append([BTN_EXIT])
    return _kb(rows)


def end_of_plan_menu() -> ReplyKeyboardMarkup:
    return _kb([[BTN_EXIT]])


def remove_menu() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
