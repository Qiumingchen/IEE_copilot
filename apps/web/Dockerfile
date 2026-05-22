FROM node:22-slim AS deps
WORKDIR /app
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml /app/
COPY apps/web/package.json /app/apps/web/package.json
RUN corepack enable && pnpm install --frozen-lockfile=false

FROM deps AS builder
WORKDIR /app
COPY . /app
ENV NEXT_STANDALONE=true
ENV API_INTERNAL_BASE_URL=http://api:8000
RUN corepack enable && pnpm --filter @iee-copilot/web build

FROM deps
WORKDIR /app
ENV NODE_ENV=production
ENV API_INTERNAL_BASE_URL=http://api:8000
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public
CMD ["node", "apps/web/server.js"]
