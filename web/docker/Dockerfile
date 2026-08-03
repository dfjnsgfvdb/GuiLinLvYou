
# Static frontend image for the Liguan tourism opinion console.
FROM nginx:stable-alpine

WORKDIR /app

COPY dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
