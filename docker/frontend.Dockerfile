FROM node:20-alpine

WORKDIR /app/frontend

# Install dependencies
COPY frontend/package.json frontend/package-lock.json* /app/frontend/
RUN npm install

# Copy project files
COPY frontend/ /app/frontend/

# Expose Vite dev server port
EXPOSE 5173

# Run Vite dev server — listen on all interfaces for Docker
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
