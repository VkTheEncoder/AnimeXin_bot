# Dockerfile

# 1. Base image
FROM python:3.9-slim

# 2. Set working directory
WORKDIR /app

# 3. Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy your bot code (including config.py)
COPY . .

# 5. Ensure logs are unbuffered (optional but handy)
ENV PYTHONUNBUFFERED=1

# 6. Run the bot
CMD ["python", "main.py"]
