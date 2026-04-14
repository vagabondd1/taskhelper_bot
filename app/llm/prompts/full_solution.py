FULL_SOLUTION_PROMPT = """The user requested a full solution.

Task summary: {task_summary}
Current progress: {progress_summary}

Provide a complete, well-structured solution:
1. Brief explanation of the approach
2. Step-by-step breakdown
3. Full working code (if applicable) using Telegram formatting: ```python\\n...\\n```
4. Short note on edge cases or common mistakes if relevant

Be thorough. This is full solution mode — do not hold back.
Set action_type = "full_solution"."""
