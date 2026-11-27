FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py server.py review.py release_check.py storage.py cloud_services.py ./
COPY static/ ./static/
CMD ["python", "app.py"]
