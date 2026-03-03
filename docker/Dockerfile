# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for OpenCV and other PDF processing libraries
RUN apt-get update && apt-get install -y 
    libgl1-mesa-glx 
    libglib2.0-0 
    build-essential 
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
# Note: This assumes the build context is the project root
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Create directories for logs and temp files
RUN mkdir -p logs temp

# Expose the port the app runs on
EXPOSE 8080

# Run uvicorn when the container launches
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
