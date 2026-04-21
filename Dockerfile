FROM python:3.12-slim

WORKDIR /app

# Зависимости отдельным слоем — кешируются при неизменном requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
