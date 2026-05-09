# CCAS Proxy — single ingress nginx image
#
# Built and published to ghcr.io/<owner>/ccas-proxy:${CCAS_VERSION}.
# nginx.conf 內建於 image 內（不依賴 host 掛載），保證任何使用者 pull 即得一致 routing。
# Non-root user (UID 1001) 沿用 docker-deploy.md 既有慣例。

FROM nginx:alpine AS production

LABEL org.opencontainers.image.title="ccas-proxy" \
      org.opencontainers.image.description="CCAS reverse proxy - single ingress nginx for backend (/api) and frontend (/)"

# Non-root user 與必要 temp path（與 frontend nginx 對齊）
RUN addgroup -g 1001 -S appgroup \
    && adduser -S appuser -u 1001 -G appgroup \
    && mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp \
    && chown -R appuser:appgroup /var/cache/nginx /var/log/nginx \
       /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp /tmp/uwsgi_temp /tmp/scgi_temp

# 內建 nginx.conf — 不掛載 host config，pull 即用
COPY --chown=appuser:appgroup nginx.conf /etc/nginx/nginx.conf

USER appuser
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:8080/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
