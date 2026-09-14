FROM node:20-alpine AS build
WORKDIR /srv
COPY package.json .
RUN npm install
COPY . .
# VITE_API_BASE_URL is baked in at build time (Vite convention) -- defaults to the
# same-machine API port, matching how docker-compose.yml exposes it.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /srv/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
