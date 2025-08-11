# syntax=docker/dockerfile:1
### Stage 1: build the React app
FROM node:20-alpine AS build
WORKDIR /app
# Inject Vite envs at build time
ARG VITE_AUTH_URL
ARG VITE_BACKEND_URL
ENV VITE_AUTH_URL=$VITE_AUTH_URL
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
# install dependencies (copied separately to leverage cache)
COPY frontend/package*.json ./
RUN npm ci
# copy source and build
COPY frontend .
RUN npm run build
### Stage 2: serve with Nginx
FROM nginx:stable-alpine AS production
# copy built files from the build stage
COPY --from=build /app/dist /usr/share/nginx/html
# optional: custom Nginx config to support SPA routing
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]