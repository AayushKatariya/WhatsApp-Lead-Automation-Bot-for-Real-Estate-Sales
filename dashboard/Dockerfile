# Lead dashboard for Google Cloud Run: builds the Next.js app, then runs only its small standalone server.
FROM node:24-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0
# server.js, the needed node_modules and db/schema.sql (see outputFileTracingIncludes in next.config.ts)
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER node
# Cloud Run tells the server which port to use through $PORT
CMD ["node", "server.js"]
