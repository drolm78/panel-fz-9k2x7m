FROM python:3.11-slim

# ffmpeg es obligatorio: muestreo de cuadros y extraccion de audio.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY recipe_bot/ ./recipe_bot/
COPY scripts/ ./scripts/

ENV WORK_DIR=/tmp/recipe-bot PYTHONUNBUFFERED=1
CMD ["python", "-m", "recipe_bot"]
