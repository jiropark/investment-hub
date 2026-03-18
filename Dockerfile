FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY app.py .
COPY templates/ templates/
EXPOSE 8091
CMD ["python", "app.py"]
