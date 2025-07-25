FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY bot.py .
COPY start.sh .

# Ensure the start script is executable
RUN chmod +x ./start.sh

# Expose the port Gunicorn will run on
EXPOSE 8080

# Set python to print logs immediately
ENV PYTHONUNBUFFERED 1

# Run the start.sh script when the container launches
CMD ["./start.sh"]