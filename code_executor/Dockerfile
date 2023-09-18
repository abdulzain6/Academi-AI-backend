# Use Python 3.11 slim-buster image as a parent image
FROM python:3.11-slim-buster

# Set environment variables to non-interactive (this prevents some prompts)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND=noninteractive

# Create app directory
WORKDIR /app

# Create a non-root user and switch to it
# Create a non-root user with a specific user ID (e.g., 1001)
RUN useradd -u 1001 -m myuser

# Install uvicorn explicitly as root
USER root
RUN pip install uvicorn

# Switch back to the non-root user
USER myuser

# Copy just the requirements.txt and install dependencies
# This layer is recreated only if requirements.txt changes
COPY --chown=myuser:myuser requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the current directory contents into the container at /app
# Make sure to set the ownership to the non-root user
COPY --chown=myuser:myuser . /app/

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port 8000"]
