# Stage: base — shared pnpm setup
FROM node:22-slim AS base
RUN corepack enable
WORKDIR /app

# Stage: dev — hot reload via bind mount
FROM base AS dev
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY . .
EXPOSE 5173
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "require('http').get('http://localhost:5173', r => r.statusCode < 400 ? process.exit(0) : process.exit(1)).on('error', () => process.exit(1))"
CMD ["pnpm", "dev", "--host", "0.0.0.0"]

# Stage: build — compile static assets (selective COPY for cache efficiency)
FROM base AS build
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY components.json ./
COPY public/ ./public/
COPY src/ ./src/
RUN pnpm build

# Stage: production — nginx serves static files (non-root)
FROM nginx:alpine AS production
LABEL org.opencontainers.image.title="ccas-frontend" \
      org.opencontainers.image.description="CCAS Frontend - React SPA served by nginx"
RUN addgroup -g 1001 -S appgroup && adduser -S appuser -u 1001 -G appgroup \
    && mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp \
    && chown -R appuser:appgroup /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
       /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp
COPY --from=build --chown=appuser:appgroup /app/dist /usr/share/nginx/html
COPY --chown=appuser:appgroup nginx.conf /etc/nginx/nginx.conf
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
