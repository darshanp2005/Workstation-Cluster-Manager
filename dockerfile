# slim, fast, works well with psutil wheels
FROM python:3.11-slim

RUN mkdir -p /home/parth/projects/p2pCluster

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py /app/app.py

EXPOSE 5000

# ENTRYPOINT ensures "python app.py" always runs, and extra args are passed
ENTRYPOINT ["python", "app.py"]
CMD ["--role", "server", "--server-port", "5000"]
