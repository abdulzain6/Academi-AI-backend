# Use the official Ubuntu image as a base image
FROM ubuntu:latest

# Set the working directory
WORKDIR /app

# Set environment variable for non-interactive installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    software-properties-common \
    wget \
    gnupg2 \
    tesseract-ocr \
    wkhtmltopdf \
    texlive-full \
    fonts-freefont-ttf \
    fonts-dejavu \
    fonts-liberation \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-indic \
    fonts-noto \
    graphviz \
    ffmpeg \
    libreoffice \
    poppler-utils \
    nodejs \
    npm \
    python3 \
    python3-pip \
    python3-venv \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add the Pandoc repository and install the latest version of Pandoc
RUN wget -qO- https://github.com/jgm/pandoc/releases/download/2.19.2/pandoc-2.19.2-linux-amd64.tar.gz | tar xvz -C /opt && \
    ln -s /opt/pandoc-2.19.2/bin/pandoc /usr/local/bin/pandoc

# Add the Google Chrome repository
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' && \
    apt-get update && \
    apt-get install -y google-chrome-stable

# Set up a virtual environment and install Python dependencies
COPY ./requirements.txt /app/requirements.txt
RUN python3 -m venv /app/venv && \
    . /app/venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN . /app/venv/bin/activate && python -m nltk.downloader punkt averaged_perceptron_tagger

# Copy markdown styles and install npm dependencies
COPY ./markdown-styles /app/markdown-styles
RUN cd /app/markdown-styles && npm install -g

# Copy the rest of the application code
COPY . /app

# Expose port 8000
EXPOSE 8000

# Run the application using the virtual environment
CMD ["/app/venv/bin/uvicorn", "api.api:app", "--host", "0.0.0.0", "--port", "8000"]
