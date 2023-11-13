FROM python:3.11-slim-buster

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive


RUN apt-get update && \
    apt-get install -y \
    tesseract-ocr \
    wkhtmltopdf \
    pandoc \
    wget \
    gnupg2 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* 

RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -

RUN apt-get update

# Install the latest version of Google Chrome
RUN apt-get install -y google-chrome-stable

# Clear out the local repository of retrieved package files
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "api.api:app", "--host", "0.0.0.0", "--port", "8000"]
