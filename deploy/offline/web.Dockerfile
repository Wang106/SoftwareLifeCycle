# Fresh local-only npm cache; lifecycle scripts run normally during npm ci.
# npm offline is not a physical network boundary. No host network setting changes.
FROM docker.io/library/node@sha256:aaa4b5baf1ecff3b283486bb1f90405cdda225a3e6f79660d2c559fa510a7292 AS build
WORKDIR /app
COPY artifacts/ /artifacts/
COPY package.json package-lock.json next.config.js next-env.d.ts tsconfig.json /app/
COPY app/ /app/app/
COPY components/ /app/components/
COPY lib/ /app/lib/
RUN mkdir /cache /build-home && touch /build-home/user.npmrc /build-home/global.npmrc \
    && env -i PATH="$PATH" HOME=/build-home CI=true \
      npm_config_cache=/cache npm_config_userconfig=/build-home/user.npmrc \
      npm_config_globalconfig=/build-home/global.npmrc npm_config_registry=https://registry.npmjs.org/ \
      npm_config_offline=true npm_config_fetch_retries=0 npm_config_update_notifier=false \
      npm_config_audit=false npm_config_fund=false NEXT_TELEMETRY_DISABLED=1 \
      WRANGLER_SEND_METRICS=false OPEN_NEXT_TELEMETRY_DISABLED=1 \
      API_BASE_URL= NEXT_PUBLIC_API_BASE_URL= NEXT_PUBLIC_API_URL= \
      /bin/sh -ec 'npm cache add /artifacts/*.tgz --offline --ignore-scripts --no-audit --no-fund; \
        npm cache verify --offline; \
        npm ci --offline --include=dev --include=optional --foreground-scripts --no-audit --no-fund; \
        npm run build'
FROM docker.io/library/node@sha256:aaa4b5baf1ecff3b283486bb1f90405cdda225a3e6f79660d2c559fa510a7292
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT
WORKDIR /app
COPY --from=build /app/node_modules /app/node_modules/
COPY --from=build /app/.next /app/.next/
COPY --from=build /app/package.json /app/package.json
COPY --from=build /app/next.config.js /app/next.config.js
USER 65532:65532
# Fail closed unless the separately reviewed Compose or smoke command overrides it.
ENTRYPOINT ["/bin/false"]
CMD []
