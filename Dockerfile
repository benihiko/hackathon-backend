FROM python:3.11-slim
WORKDIR /app

# mysql-connector-python を追加！
RUN pip install fastapi uvicorn mysql-connector-python

COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
