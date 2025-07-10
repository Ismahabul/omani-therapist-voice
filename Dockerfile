# --- Stage 1: Builder ---
# This stage installs the dependencies into a virtual environment.
FROM python:3.11-slim as builder

# Set the working directory
WORKDIR /app

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# Ensure Python output is sent straight to the terminal
ENV PYTHONUNBUFFERED 1

# Install and upgrade pip, then create a virtual environment
RUN pip install --upgrade pip
RUN python -m venv /opt/venv

# Activate the virtual environment for subsequent RUN commands
ENV PATH="/opt/venv/bin:$PATH"

# Copy the requirements file and install dependencies into the venv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Final Production Image ---
# This stage creates the final, lean image for production.
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application source code
COPY . .

# Activate the virtual environment for the final container
ENV PATH="/opt/venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# Set the command to run the application using Uvicorn
# The host 0.0.0.0 is crucial for Docker to expose the port correctly.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]