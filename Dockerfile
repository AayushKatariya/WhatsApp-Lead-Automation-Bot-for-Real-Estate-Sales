FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
# Cloud Run tells the app which port to listen on through $PORT
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
