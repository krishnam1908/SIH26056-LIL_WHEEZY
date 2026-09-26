# Production Dockerfile for APIx Airfare Price Index & Real-Time Scraper Engine
FROM node:20-slim

# Install Python 3 and pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Install Python dependencies
COPY backend/scraper_python/requirements.txt ./backend/scraper_python/
RUN pip3 install --no-cache-dir --break-system-packages -r backend/scraper_python/requirements.txt

# Copy application source code
COPY . .

# Set environment
ENV NODE_ENV=production
ENV PORT=5000

EXPOSE 5000

CMD ["npm", "start"]
