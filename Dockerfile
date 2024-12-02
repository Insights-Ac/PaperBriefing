FROM ubuntu:22.04

# Set environment variables to prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

WORKDIR /app

# Copy requirements file
COPY requirements.txt .
COPY src/ ./src

# Install system dependencies
RUN apt-get clean && \
    apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:mozillateam/ppa && \
    apt-get update && \
    apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    git \
    tesseract-ocr \
    xvfb \
    firefox-esr && \
    # Clean up apt cache to reduce image size
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python3 -m venv /venv --system-site-packages && \
    . /venv/bin/activate && \
    pip install -r requirements.txt

# Add venv to PATH
ENV PATH="/venv/bin:$PATH"

# Set the default command
CMD ["/venv/bin/python3", "src/main.py"]