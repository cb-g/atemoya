# Atemoya - Quantitative Finance Models
# Multi-stage Docker build for OCaml + Python environment

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Build essentials
    build-essential \
    gcc \
    g++ \
    make \
    patch \
    unzip \
    wget \
    curl \
    git \
    # OCaml dependencies
    opam \
    m4 \
    pkg-config \
    libgmp-dev \
    libffi-dev \
    # Owl (numerical library) dependencies
    libopenblas-dev \
    liblapacke-dev \
    # Python dependencies
    python3 \
    python3-pip \
    python3-venv \
    # System utilities
    ca-certificates \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=atemoya
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Set working directory
WORKDIR /app

# Change ownership to non-root user
RUN chown -R $USERNAME:$USERNAME /app

# Switch to non-root user
USER $USERNAME

# Initialize OPAM (OCaml package manager)
RUN opam init --disable-sandboxing --auto-setup --yes \
    && eval $(opam env) \
    && opam update

# Set up OPAM environment variables
ENV OPAM_SWITCH_PREFIX=/home/atemoya/.opam/default
ENV PATH="${OPAM_SWITCH_PREFIX}/bin:${PATH}"

# Copy project dependency files
COPY --chown=$USERNAME:$USERNAME atemoya.opam dune-project ./
COPY --chown=$USERNAME:$USERNAME pyproject.toml uv.lock ./

# Install OCaml dependencies
RUN eval $(opam env) && opam install . --deps-only --with-test --yes

# Install uv (Python package manager) and verify it works
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /home/atemoya/.local/bin/uv --version

ENV PATH="/home/atemoya/.local/bin:${PATH}"

# Install Python dependencies
RUN uv sync

# Copy rest of project files (source code)
COPY --chown=$USERNAME:$USERNAME . .

# Build OCaml code
RUN eval $(opam env) && opam exec -- dune build

# Default command: interactive shell with OPAM environment
CMD ["/bin/bash", "-c", "eval $(opam env) && exec /bin/bash"]
