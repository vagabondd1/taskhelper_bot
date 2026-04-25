FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем — кешируются при неизменном requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh \
    && groupadd --system --gid 1000 appgroup \
    && useradd --system --uid 1000 --gid appgroup --no-create-home appuser \
    && chown -R appuser:appgroup /app

USER appuser

CMD ["./entrypoint.sh"]
