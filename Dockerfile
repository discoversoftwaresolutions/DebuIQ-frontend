# Use an official Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 ffmpeg libavdevice-dev libavfilter-dev libavformat-dev libavcodec-dev libavutil-dev \
    && apt-get clean

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source code
COPY . .

# Expose the port for Railway
EXPOSE $PORT

# Start Streamlit app
CMD ["streamlit", "run", "frontend/streamlit-dashboard.py", "--server.port=$PORT", "--server.enableCORS=false"]
