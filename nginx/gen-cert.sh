#!/bin/sh
# Generate self-signed TLS cert if not already present
if [ ! -f /etc/nginx/certs/cert.pem ]; then
  apk add --no-cache openssl 2>/dev/null || true
  mkdir -p /etc/nginx/certs
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/certs/key.pem \
    -out    /etc/nginx/certs/cert.pem \
    -subj   "/C=US/ST=State/L=City/O=HalluCheck/CN=localhost"
fi
exec nginx -g "daemon off;"
