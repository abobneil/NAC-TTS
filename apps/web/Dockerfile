FROM node:24-alpine AS build

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm install

COPY apps/web /app
RUN npm run build

FROM caddy:2.10-alpine

COPY ops/docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
