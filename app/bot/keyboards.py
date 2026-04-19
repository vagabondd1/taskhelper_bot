from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Callback data константы
CB_HINT = "action:hint"
CB_NEXT_STEP = "action:next_step"
CB_VALIDATE_IDEA = "action:validate_idea"
CB_EXPLAIN = "action:explain"
CB_CODE_HINT = "action:code_hint"
CB_THIS_IS_WRONG = "action:this_is_wrong"
CB_MODE_GUIDED = "mode:guided"
CB_MODE_FULL_SOLUTION = "mode:full_solution"
CB_GET_FULL_SOLUTION = "action:full_solution"


def guided_menu() -> InlineKeyboardMarkup:
    """Фиксированный порядок кнопок guided mode согласно ТЗ."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ This is wrong", callback_data=CB_THIS_IS_WRONG)],
        [InlineKeyboardButton(text="💡 Hint", callback_data=CB_HINT)],
        [InlineKeyboardButton(text="➡️ Next step", callback_data=CB_NEXT_STEP)],
        [InlineKeyboardButton(text="✅ Validate my idea", callback_data=CB_VALIDATE_IDEA)],
        [InlineKeyboardButton(text="📖 Explain", callback_data=CB_EXPLAIN)],
        [InlineKeyboardButton(text="💻 Code hint", callback_data=CB_CODE_HINT)],
    ])


def mode_selector() -> InlineKeyboardMarkup:
    """Выбор режима после получения новой задачи."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Guided mode", callback_data=CB_MODE_GUIDED)],
        [InlineKeyboardButton(text="📋 Full solution", callback_data=CB_MODE_FULL_SOLUTION)],
    ])


def full_solution_menu() -> InlineKeyboardMarkup:
    """Кнопки в full solution mode."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Get full solution", callback_data=CB_GET_FULL_SOLUTION)],
        [InlineKeyboardButton(text="🧩 Switch to guided mode", callback_data=CB_MODE_GUIDED)],
    ])
