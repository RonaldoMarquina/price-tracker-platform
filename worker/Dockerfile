FROM python:3.12-slim

WORKDIR /app

# Install python dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application source
COPY app/ ./app/

ENV PYTHONPATH="/app"

CMD ["python", "-m", "app.main"]
