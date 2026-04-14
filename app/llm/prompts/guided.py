NEW_TASK_PROMPT = """A user submitted a new programming task. Analyze it.

Task:
{task_text}

Instructions:
1. In state_update.task_summary write a concise summary of the task (2-4 sentences max).
2. In state_update.progress_summary write the initial state: "Not started. Step 0."
3. In response_text greet the user, briefly confirm you understood the task, and ask how they want to proceed: step by step (guided) or full solution.
4. Set action_type = "new_task".
5. Do NOT start solving yet."""

HINT_PROMPT = """The user asked for a hint.

Task summary: {task_summary}
Current progress: {progress_summary}
Step index: {step_index}
Last assistant response summary: {last_assistant_summary}

Give a short, targeted hint that nudges the user toward the next thought without revealing the solution.
Hint must be 1-3 sentences. Set action_type = "guided_hint"."""

NEXT_STEP_PROMPT = """The user asked for the next step.

Task summary: {task_summary}
Current progress: {progress_summary}
Step index: {step_index}
Last assistant response summary: {last_assistant_summary}

Provide exactly the next logical step. One step only — not the full solution.
Update state_update.progress_summary with the new progress.
Set state_update.step_increment = true.
Set action_type = "guided_next_step"."""

VALIDATE_IDEA_REQUEST_PROMPT = """The user wants to validate their idea.

Task summary: {task_summary}
Current progress: {progress_summary}

Ask the user to share their hypothesis or approach. Keep it short (1 sentence).
Set state_update.awaiting_hypothesis = true.
Set action_type = "guided_validate_idea"."""

VALIDATE_IDEA_SUBMIT_PROMPT = """The user submitted their hypothesis for validation.

Task summary: {task_summary}
Current progress: {progress_summary}
Step index: {step_index}
User hypothesis: {user_hypothesis}

Evaluate the hypothesis:
- Set validation_result to "correct", "partially_correct", or "incorrect"
- In response_text explain briefly what is right and/or wrong
- Do NOT reveal the full solution even if the hypothesis is wrong
- Update state_update.progress_summary if the hypothesis added meaningful progress
Set action_type = "guided_validate_idea"."""

EXPLAIN_PROMPT = """The user asked to explain the previous assistant response.

Task summary: {task_summary}
Previous action type: {last_action_type}
What needs to be explained: {last_assistant_summary}

Explain specifically what was said in the previous response and why it is relevant to the current step.
Do NOT explain the whole task — explain only the previous response.
Set action_type = "guided_explain"."""

CODE_HINT_PROMPT = """The user asked for a code hint for the current step.

Task summary: {task_summary}
Current progress: {progress_summary}
Step index: {step_index}
Last assistant response summary: {last_assistant_summary}

Provide a small code snippet or pseudocode for the current step only.
Do NOT provide the full solution code.
Use Telegram code formatting: ```python\\n...\\n```
Set action_type = "guided_code_hint"."""

THIS_IS_WRONG_PROMPT = """The user says the previous response was wrong.

Task summary: {task_summary}
Current progress: {progress_summary}
Last assistant response summary: {last_assistant_summary}

Review your previous response:
- If you made an error: acknowledge it, correct it, and explain what changed
- If the previous response was correct: politely explain why it is valid
Set action_type = "guided_recheck"."""
