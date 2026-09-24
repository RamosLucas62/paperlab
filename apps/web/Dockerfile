FROM node:22.23.0-alpine3.22
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
