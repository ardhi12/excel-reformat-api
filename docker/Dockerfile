# Image
FROM python:3.11.7-slim

# Working directory
WORKDIR /app

# Copy file to workdir
COPY app/requirements.txt .

# Install python packages
RUN pip3 install -r requirements.txt

# Copy files to workdir
COPY app/ .

# Command run python
CMD ["python", "main.py"]