FULL_SOLUTION_PROMPT = """The user requested a FULL solution. This means: working, ready-to-run code is MANDATORY.

Task summary: {task_summary}
Current progress: {progress_summary}

Your `response_text` MUST contain, in this order:
1. Короткое объяснение подхода (1–3 предложения, по-русски).
2. ОБЯЗАТЕЛЬНО — полный рабочий код задачи. Без этого блока ответ считается ошибкой.
   - Код должен компилироваться / запускаться как есть: включи импорты, главную функцию и при необходимости пример запуска.
   - Используй полноценную реализацию, а не "# здесь ваш код".
   - Оформляй в Markdown-блоке с языком, пример:
     ```python
     def solve(nums):
         return sum(nums)
     ```
3. 1–2 предложения про пограничные случаи / типичные ошибки, если уместно.

STRICT CHECK before finishing:
- Есть ли в `response_text` блок вида ```<язык> ... ``` ? Если нет — ты нарушил требование, перепиши.
- Внутри JSON-строки переносы строк между строками кода должны быть реальными `\\n` (JSON-escaped), НЕ буквальными двумя символами обратный слэш+n.

Язык кода выбирай по задаче; если не указан — Python.
Set action_type = "full_solution"."""
