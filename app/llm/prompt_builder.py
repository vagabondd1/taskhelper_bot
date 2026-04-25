from app.db.models import ActionType
from app.llm.prompts.system import SYSTEM_PROMPT
from app.llm.prompts.guided import (
    NEW_TASK_PROMPT,
    HINT_PROMPT,
    NEXT_STEP_PROMPT,
    VALIDATE_IDEA_REQUEST_PROMPT,
    VALIDATE_IDEA_SUBMIT_PROMPT,
    SHARE_THINKING_REQUEST_PROMPT,
    SHARE_THINKING_SUBMIT_PROMPT,
    EXPLAIN_PROMPT,
    CODE_HINT_PROMPT,
    THIS_IS_WRONG_PROMPT,
)
from app.llm.prompts.full_solution import FULL_SOLUTION_PROMPT
from app.schemas.session_state import SessionContext


def _na(value: str | None) -> str:
    return value or "n/a"


def _plan_str(plan: list[str] | None) -> str:
    if not plan:
        return "n/a"
    return "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan))


def _wrap_user(text: str | None) -> str:
    """Оборачивает untrusted user input в маркеры для prompt-injection защиты.

    Экранируем ВСЕ угловые скобки внутри контента — пользователь не может
    инжектировать никакие XML/HTML-теги (включая </user_input>), поэтому
    граница маркера остаётся под нашим контролем.
    """
    if not text:
        return "<user_input></user_input>"
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<user_input>{safe}</user_input>"


def build_messages(
    action: ActionType,
    context: SessionContext,
    user_input: str | None = None,
) -> list[dict]:
    """Собирает минимально достаточный список messages для LLM.

    Никогда не отправляет полный диалог — только нужный контекст под действие.
    """
    user_content = _build_user_content(action, context, user_input)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _build_user_content(
    action: ActionType,
    ctx: SessionContext,
    user_input: str | None,
) -> str:
    match action:
        case ActionType.new_task:
            return NEW_TASK_PROMPT.format(task_text=_wrap_user(user_input))

        case ActionType.guided_hint:
            return HINT_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                plan_steps=_plan_str(ctx.plan_steps),
                current_step_title=_na(ctx.current_step_title),
                progress_summary=_na(ctx.current_progress_summary),
                step_index=ctx.current_step_index,
                last_assistant_summary=_na(ctx.last_assistant_summary),
            )

        case ActionType.guided_next_step:
            return NEXT_STEP_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                plan_steps=_plan_str(ctx.plan_steps),
                current_step_title=_na(ctx.current_step_title),
                next_step_title=_na(ctx.next_step_title),
                progress_summary=_na(ctx.current_progress_summary),
                step_index=ctx.current_step_index,
                step_human=ctx.current_step_index + 1,
                last_assistant_summary=_na(ctx.last_assistant_summary),
            )

        case ActionType.guided_validate_idea:
            if ctx.awaiting_hypothesis and user_input:
                return VALIDATE_IDEA_SUBMIT_PROMPT.format(
                    task_summary=_na(ctx.task_summary),
                    progress_summary=_na(ctx.current_progress_summary),
                    step_index=ctx.current_step_index,
                    user_hypothesis=_wrap_user(user_input),
                )
            return VALIDATE_IDEA_REQUEST_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                progress_summary=_na(ctx.current_progress_summary),
            )

        case ActionType.guided_explain:
            return EXPLAIN_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                last_action_type=_na(
                    ctx.last_action_type.value if ctx.last_action_type else None
                ),
                last_assistant_summary=_na(ctx.last_assistant_summary),
            )

        case ActionType.guided_code_hint:
            return CODE_HINT_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                plan_steps=_plan_str(ctx.plan_steps),
                current_step_title=_na(ctx.current_step_title),
                progress_summary=_na(ctx.current_progress_summary),
                step_index=ctx.current_step_index,
                last_assistant_summary=_na(ctx.last_assistant_summary),
            )

        case ActionType.guided_share_thinking:
            if ctx.awaiting_hypothesis and user_input:
                return SHARE_THINKING_SUBMIT_PROMPT.format(
                    task_summary=_na(ctx.task_summary),
                    progress_summary=_na(ctx.current_progress_summary),
                    step_index=ctx.current_step_index,
                    user_thinking=_wrap_user(user_input),
                )
            return SHARE_THINKING_REQUEST_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                progress_summary=_na(ctx.current_progress_summary),
            )

        case ActionType.guided_recheck:
            return THIS_IS_WRONG_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                progress_summary=_na(ctx.current_progress_summary),
                last_assistant_summary=_na(ctx.last_assistant_summary),
            )

        case ActionType.full_solution:
            return FULL_SOLUTION_PROMPT.format(
                task_summary=_na(ctx.task_summary),
                progress_summary=_na(ctx.current_progress_summary),
            )

        case _:
            raise ValueError(f"Unknown action type for prompt builder: {action}")
