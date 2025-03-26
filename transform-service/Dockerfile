# Use the official Python slim image (updated to 3.12)
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY main.py .

# Run the app with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]