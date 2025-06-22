# Use an official lightweight Python image
FROM python:3.9-slim

# Set a working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# (Optional) expose logs to Docker
ENV PYTHONUNBUFFERED=1

# Configure via environment variables
# You can override these at docker-run time instead of hardcoding in config.py
ENV API_URL="http://host.docker.internal:8000"
ENV TELEGRAM_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

# Start the bot
CMD ["python", "main.py"]
