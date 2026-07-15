FROM python:3.10-slim

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/requirements.txt

# Install PyTorch CPU and other python dependencies
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy source code
COPY ./app /code/app

# Download real model weights (bypassing Git LFS pointer)
RUN curl -L -o /code/generator_scripted.pt https://media.githubusercontent.com/media/Gioezzy/songket_model/main/generator_scripted.pt

# Ensure static directories exist
RUN mkdir -p /code/static/images

# Expose FastAPI port
# Start command dynamically using PORT environment variable
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
