FROM nginx:1.27-alpine

# Replace the default config with our reverse-proxy + static config
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Static web assets
COPY index.html /usr/share/nginx/html/index.html
COPY login.html /usr/share/nginx/html/login.html
COPY register.html /usr/share/nginx/html/register.html
COPY dashboard.html /usr/share/nginx/html/dashboard.html
COPY payment.html /usr/share/nginx/html/payment.html
COPY assets /usr/share/nginx/html/assets

# Ensure the /i mount target exists so nginx can serve from it without errors
# at boot when the volume is empty.
RUN mkdir -p /usr/share/nginx/html/i

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]