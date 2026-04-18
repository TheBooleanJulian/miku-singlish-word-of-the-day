FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-dejavu-core && \
    mkdir -p /app/fonts && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf /app/fonts/ && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf /app/fonts/ && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf /app/fonts/ && \
    cp /usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf /app/fonts/ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
