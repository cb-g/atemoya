# Atemoya - Quantitative Finance Models
# Multi-stage Docker build for OCaml + Python environment

FROM ubuntu:24.04

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
    cron \
    sudo \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=atemoya
ARG USER_UID=1000
ARG USER_GID=1000

# Handle existing user/group with same UID/GID (common in Ubuntu 24.04)
RUN existing_user=$(getent passwd $USER_UID | cut -d: -f1) && \
    existing_group=$(getent group $USER_GID | cut -d: -f1) && \
    # If user exists with different name, delete it
    if [ -n "$existing_user" ] && [ "$existing_user" != "$USERNAME" ]; then \
        userdel -r $existing_user 2>/dev/null || true; \
    fi && \
    # If group exists with different name, delete it
    if [ -n "$existing_group" ] && [ "$existing_group" != "$USERNAME" ]; then \
        groupdel $existing_group 2>/dev/null || true; \
    fi && \
    # Create our group and user
    groupadd --gid $USER_GID $USERNAME 2>/dev/null || true && \
    useradd --uid $USER_UID --gid $USER_GID -m $USERNAME 2>/dev/null || true && \
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME

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

# Copy project dependency files
COPY --chown=$USERNAME:$USERNAME atemoya.opam dune-project ./
COPY --chown=$USERNAME:$USERNAME pyproject.toml uv.lock ./

# Create a named switch for this project (not a local "." switch which auto-installs)
RUN opam switch create atemoya-build 5.2.1 --yes && eval $(opam env --switch=atemoya-build)

# Pin the project and install only dependencies (not the package itself yet)
RUN eval $(opam env --switch=atemoya-build) && \
    opam pin add atemoya . --no-action --yes && \
    opam install atemoya --deps-only --with-test --yes

# Set up OPAM environment variables to use this switch
ENV OPAM_SWITCH_PREFIX=/home/atemoya/.opam/atemoya-build
ENV PATH="/home/atemoya/.opam/atemoya-build/bin:${PATH}"

# Install uv (Python package manager) and verify it works
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /home/atemoya/.local/bin/uv --version

ENV PATH="/home/atemoya/.local/bin:${PATH}"

# Configure uv to use copy mode (hardlinks don't work across Docker volumes on macOS)
ENV UV_LINK_MODE=copy

# Install Python dependencies using system Python
# Remove any existing .venv first to avoid stale/broken environments
RUN rm -rf .venv && uv sync --python $(which python3)

# Copy rest of project files (source code)
COPY --chown=$USERNAME:$USERNAME . .

# Build OCaml code
RUN eval $(opam env) && opam exec -- dune build

# Default command: interactive shell with OPAM environment
CMD ["/bin/bash", "-c", "eval $(opam env) && exec /bin/bash"]
