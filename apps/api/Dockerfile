# Render runs Linux x86_64 containers. Build from the repository root:
# docker build --platform linux/amd64 -f apps/api/Dockerfile .
FROM --platform=linux/amd64 node:24.14.1-bookworm-slim AS web-build
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1 KEEPSAKE_STATIC_EXPORT=1
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci --no-audit --no-fund
COPY apps/web apps/web
COPY packages packages
RUN npm run build

FROM --platform=linux/amd64 python:3.14.3-slim-bookworm AS blender-download
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates curl xz-utils && rm -rf /var/lib/apt/lists/*
# Official Blender release, pinned to the same version as the validated local master.
# SHA256 from https://download.blender.org/release/Blender4.5/blender-4.5.16.sha256
RUN curl --fail --location --retry 3 --connect-timeout 20 \
      https://download.blender.org/release/Blender4.5/blender-4.5.16-linux-x64.tar.xz \
      --output /tmp/blender.tar.xz \
    && echo '23432b064977908beb1ab4b7f32f024e7331105c875c187dce002aff84b10c11  /tmp/blender.tar.xz' | sha256sum --check --strict \
    && mkdir -p /opt/blender \
    && tar -xJf /tmp/blender.tar.xz --strip-components=1 -C /opt/blender \
    && rm /tmp/blender.tar.xz

FROM --platform=linux/amd64 python:3.14.3-slim-bookworm AS runtime
WORKDIR /app
# The Blender binary links these libraries even in headless CPU rendering mode.
RUN apt-get update && apt-get install --no-install-recommends -y \
      ca-certificates tini libgl1 libegl1 libvulkan1 libstdc++6 libx11-6 libxi6 libxrender1 libxfixes3 \
      libxxf86vm1 libxkbcommon0 libsm6 libice6 libgomp1 libfontconfig1 libdbus-1-3 \
      libwayland-client0 libwayland-cursor0 libwayland-egl1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /bin/sh keepsake \
    && install -d -m 0700 -o keepsake -g keepsake /home/keepsake/.ssh
COPY --from=blender-download /opt/blender /opt/blender
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r apps/api/requirements.txt
COPY apps/api /app/apps/api
COPY workers /app/workers
COPY packages/schemas /app/packages/schemas
COPY migrations /app/migrations
COPY assets/designs /app/assets/designs
COPY --from=web-build /build/apps/web/out /app/public
# Free preview deployment: ephemeral private data, bounded single-job CPU rendering.
# Local runs retain their higher-resolution default settings.
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    KEEPSAKE_WEB_DIR=/app/public KEEPSAKE_DATA_DIR=/tmp/keepsake-data \
    KEEPSAKE_BUILD_WORKERS=1 KEEPSAKE_MAX_PENDING_BUILDS=2 \
    KEEPSAKE_BUILD_TIMEOUT_SECONDS=1000 \
    BLENDER_BIN=/opt/blender/blender BLENDER_THREADS=1 BLENDER_TIMEOUT_SECONDS=900 \
    BLENDER_RENDER_RESOLUTION=512 BLENDER_RENDER_SAMPLES=8 BLENDER_DENOISE=0 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
USER keepsake:keepsake
# Validate actual Linux GLB/STL/PNG generation during image build. This validates
# binary dependencies and output provenance, not the live service's memory budget.
RUN python workers/blender/run.py \
      --params assets/designs/better-together/0.1.0-demo/example-params.json \
      --output /tmp/keepsake-image-build-check --revision 1 \
    && rm -rf /tmp/keepsake-image-build-check
EXPOSE 10000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec python -m uvicorn apps.api.main:app --host 0.0.0.0 --port \"${PORT:-10000}\" --workers 1 --no-proxy-headers"]
