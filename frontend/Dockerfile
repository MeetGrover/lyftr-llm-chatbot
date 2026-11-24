# Multi-stage Dockerfile for React Frontend

# Stage 1: Build the Vite production bundle
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Optional build arg for setting backend URL at build time
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# Stage 2: Serve statically with lightweight Nginx
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
