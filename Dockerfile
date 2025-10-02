# Multi-stage Dockerfile for dlzoom
# Supports both amd64 and arm64 architectures

# Stage 1: Builder
FROM python:3.11-slim as builder

# Exclude documentation to speed up builds
RUN echo 'path-exclude /usr/share/man/*' > /etc/dpkg/dpkg.cfg.d/01_nodoc && \
    echo 'path-exclude /usr/share/doc/*' >> /etc/dpkg/dpkg.cfg.d/01_nodoc

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools for security
RUN pip install --no-cache-dir --upgrade pip setuptools>=78.1.1

# Set working directory
WORKDIR /build

# Copy dependency files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies and build wheel
RUN pip install --no-cache-dir build && \
    python -m build --wheel

# Stage 2: Runtime
FROM python:3.11-slim

# Exclude documentation to speed up builds
RUN echo 'path-exclude /usr/share/man/*' > /etc/dpkg/dpkg.cfg.d/01_nodoc && \
    echo 'path-exclude /usr/share/doc/*' >> /etc/dpkg/dpkg.cfg.d/01_nodoc

# Install runtime dependencies (ffmpeg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and setuptools for security
RUN pip install --no-cache-dir --upgrade pip setuptools>=78.1.1

# Create non-root user
RUN useradd -m -u 1000 dlzoom

# Set working directory
WORKDIR /app

# Copy wheel from builder
COPY --from=builder /build/dist/*.whl /tmp/

# Install the wheel
RUN pip install --no-cache-dir /tmp/*.whl && \
    rm /tmp/*.whl

# Create directory for downloads and set ownership
RUN mkdir -p /app/downloads && \
    chown -R dlzoom:dlzoom /app/downloads

# Switch to non-root user
USER dlzoom

# Set default working directory for downloads
WORKDIR /app/downloads

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command (show help)
ENTRYPOINT ["dlzoom"]
CMD ["--help"]

# Metadata
LABEL org.opencontainers.image.title="dlzoom"
LABEL org.opencontainers.image.description="CLI tool to download Zoom cloud recordings"
LABEL org.opencontainers.image.url="https://github.com/yaniv-golan/dlzoom"
LABEL org.opencontainers.image.source="https://github.com/yaniv-golan/dlzoom"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.licenses="MIT"
