# Use the smallest possible Python base
FROM python:3.11-slim-bookworm AS builder

# Install minimal build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency resolution
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python -e .

# Runtime: Use slim base and install minimal runtime deps
FROM python:3.11-slim-bookworm

# Install only absolutely necessary runtime packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    # X11 essentials
    xvfb \
    xauth \
    # GTK essentials  
    libgtk-3-0 \
    # Draw.io AppImage essentials
    libnss3 \
    libgbm1 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Download draw.io AppImage directly in runtime stage
ARG DRAWIO_VERSION=27.0.9
RUN curl -L \
    -o /opt/drawio.AppImage \
    "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-x86_64-${DRAWIO_VERSION}.AppImage" \
    && chmod +x /opt/drawio.AppImage \
    # Remove curl after download to save space
    && apt-get remove -y curl \
    && apt-get autoremove -y

# Copy minimal files from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
COPY entrypoint.sh /app/

# Setup plugin in multiple locations to ensure it's found
RUN mkdir -p /root/.config/draw.io/plugins \
    /opt/drawio-plugins \
    /usr/share/drawio/plugins

COPY --from=builder /app/src/clab_io_draw/core/svg/svgdata.js /root/.config/draw.io/plugins/svgdata.js
COPY --from=builder /app/src/clab_io_draw/core/svg/svgdata.js /opt/drawio-plugins/svgdata.js
COPY --from=builder /app/src/clab_io_draw/core/svg/svgdata.js /usr/share/drawio/plugins/svgdata.js

# Create draw.io configuration file
RUN echo '{"plugins":[{"url":"file:///root/.config/draw.io/plugins/svgdata.js","enabled":true}]}' > /root/.config/draw.io/config.json && \
    echo '{"plugins":[{"url":"file:///opt/drawio-plugins/svgdata.js","enabled":true}]}' > /opt/drawio-config.json

# Environment setup
ENV PATH="/opt/venv/bin:${PATH}"
ENV DRAWIO_BIN=/opt/drawio.AppImage
ENV APP_BASE_DIR=/app/src/clab_io_draw
ENV TERM=xterm-256color
ENV COLORTERM=truecolor
ENV IN_DOCKER=true
ENV HOME=/root
ENV DRAWIO_CONFIG=/root/.config/draw.io/config.json

RUN chmod +x /app/entrypoint.sh

WORKDIR /data
ENTRYPOINT ["/app/entrypoint.sh"]