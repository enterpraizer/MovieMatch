# Stage 1: base
FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /app

# Stage 2: deps — install node_modules
FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Stage 3: development
FROM deps AS development
COPY . .
CMD ["pnpm", "dev"]

# Stage 4: builder — production build
FROM deps AS builder
COPY . .
RUN pnpm build

# Stage 5: production runner — minimal image
FROM node:20-alpine AS production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
WORKDIR /app
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME="0.0.0.0" NODE_ENV=production
CMD ["node", "server.js"]
