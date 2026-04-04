FROM python:3.12-slim
WORKDIR /app
RUN addgroup --gid 1000 appuser && adduser --uid 1000 --gid 1000 --disabled-password --gecos "" appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R appuser:appuser /app
USER appuser
CMD ["python", "bot.py"]
