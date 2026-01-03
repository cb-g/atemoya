# Docker Guide for Atemoya

Complete guide for running Atemoya in Docker.

---

## Quick Start

### 1. Prerequisites

Install Docker and Docker Compose:
- **Docker Desktop** (Mac/Windows): https://docs.docker.com/get-docker/
- **Linux**: https://docs.docker.com/engine/install/

Verify installation:
```bash
docker --version
docker-compose --version  # or: docker compose version
```

### 2. Start Container

```bash
# Build and start container
./docker-run.sh up

# Enter interactive shell
./docker-run.sh shell

# Run quickstart menu
./quickstart.sh
```

---

## Docker Commands Reference

### Using the Helper Script

```bash
./docker-run.sh build    # Build Docker image
./docker-run.sh up       # Start container (detached)
./docker-run.sh shell    # Open interactive shell
./docker-run.sh exec     # Run quickstart menu directly
./docker-run.sh down     # Stop container
./docker-run.sh logs     # View container logs
./docker-run.sh clean    # Remove everything (containers, volumes, images)
```

### Direct Docker Compose Commands

```bash
# Build image
docker-compose build

# Start container (detached)
docker-compose up -d

# Enter shell
docker-compose exec atemoya /bin/bash

# Stop container
docker-compose down

# View logs
docker-compose logs -f

# Remove everything including volumes
docker-compose down -v
docker rmi atemoya:latest
```

---

## How It Works

### Architecture

**Multi-Architecture Support:**
- ✅ **ARM64** (Apple Silicon M1/M2/M3, AWS Graviton, Raspberry Pi)
- ✅ **x86_64/amd64** (Intel/AMD processors)
- Docker automatically pulls the correct base image for your architecture
- All dependencies work on both architectures

**Dockerfile:**
- Base: Ubuntu 22.04 (multi-architecture)
- OCaml: OPAM 2.x + Dune
- Python: uv package manager
- Dependencies: Pre-installed for all three models

**docker-compose.yml:**
- Service: `atemoya`
- Volumes: Source code + output directories
- Caching: OPAM and uv caches persisted
- Interactive: `stdin_open: true`, `tty: true`

### Volume Mounts

Source code and outputs are mounted from host:
```yaml
volumes:
  - .:/app                              # Source code (live editing)
  - ./pricing/regime_downside/output    # Outputs persisted
  - ./valuation/dcf_deterministic/output
  - ./valuation/dcf_probabilistic/output
  - opam_cache:/root/.opam              # Cached dependencies
  - uv_cache:/root/.cache/uv
```

**Benefits:**
- ✅ Edit code on host, run in container
- ✅ Outputs saved to host filesystem
- ✅ Fast rebuilds with cached dependencies

---

## Common Workflows

### Run a Single Model

```bash
# Start container
./docker-run.sh up

# Enter shell
./docker-run.sh shell

# Inside container - run quickstart
./quickstart.sh
# → Choose model (Pricing/Valuation)
# → Run workflow
```

### Development Workflow

```bash
# Start container
./docker-run.sh up

# Keep shell open for iterative development
./docker-run.sh shell

# Edit code on host (in your IDE)
# Run inside container:
opam exec -- dune build        # Rebuild OCaml
uv run python/script.py        # Run Python scripts
./quickstart.sh                # Test via menu
```

### Rebuild After Dependencies Change

```bash
# If you modify atemoya.opam or pyproject.toml
./docker-run.sh down
./docker-run.sh build
./docker-run.sh up
```

---

## Troubleshooting

### DNS Resolution Failures During Build

**Error:** `Temporary failure resolving 'ports.ubuntu.com'` or `archive.ubuntu.com`

**Fix:** Configure Docker daemon DNS:

```bash
# Set DNS servers for Docker
sudo tee /etc/docker/daemon.json > /dev/null <<JSON
{
  "dns": ["8.8.8.8", "8.8.4.4", "1.1.1.1"]
}
JSON

# Restart Docker
sudo systemctl restart docker

# Test DNS resolution
docker run --rm busybox nslookup google.com

# Rebuild Atemoya
./docker-run.sh build
```

### Container Won't Start

```bash
# Check logs
./docker-run.sh logs

# Rebuild from scratch
./docker-run.sh clean
./docker-run.sh build
./docker-run.sh up
```

### OPAM Environment Issues

Inside container, manually source OPAM:
```bash
eval $(opam env)
opam exec -- dune build
```

### Permission Issues (Linux)

If output files have wrong ownership:
```bash
# On host (Linux only)
sudo chown -R $USER:$USER pricing/ valuation/
```

### Disk Space

Remove unused Docker resources:
```bash
./docker-run.sh clean          # Remove Atemoya containers/images
docker system prune -a         # Clean all Docker resources (careful!)
```

---

## Advanced Usage

### Custom Docker Compose

Create `docker-compose.override.yml`:
```yaml
services:
  atemoya:
    # Add custom ports
    ports:
      - "8888:8888"  # Jupyter notebook

    # Add environment variables
    environment:
      - MY_VAR=value

    # Change resource limits
    mem_limit: 4g
    cpus: 2
```

### Running Specific Commands

```bash
# Run custom command in container
docker-compose exec atemoya /bin/bash -c "eval \$(opam env) && dune runtest"

# Build only (no quickstart)
docker-compose exec atemoya /bin/bash -c "eval \$(opam env) && dune build"

# Python only
docker-compose exec atemoya uv run pricing/regime_downside/python/viz/plot_results.py --help
```

### Multi-Platform Builds

**Default Behavior:**
Docker automatically builds for your host architecture. No special flags needed!

**Build for Specific Platform:**
Use this if you need to build for a different architecture (e.g., building ARM64 image on x86_64 machine):

```bash
# Build for x86_64/amd64 (Intel/AMD)
docker buildx build --platform linux/amd64 -t atemoya:amd64 .

# Build for ARM64 (Apple Silicon, AWS Graviton)
docker buildx build --platform linux/arm64 -t atemoya:arm64 .

# Build for both architectures (requires Docker Buildx)
docker buildx build --platform linux/amd64,linux/arm64 -t atemoya:latest .
```

**Note:** Cross-architecture builds are slower (use QEMU emulation). Build on native architecture when possible.

---

## Performance Tips

### 1. Use BuildKit (Faster Builds)

```bash
# Enable BuildKit
export DOCKER_BUILDKIT=1
docker-compose build
```

### 2. Persistent Caches

Named volumes persist OPAM and uv caches:
- `atemoya_opam_cache`: OCaml packages
- `atemoya_uv_cache`: Python packages

These survive `docker-compose down` (but not `down -v`).

### 3. Pre-pull Base Image

```bash
docker pull ubuntu:22.04
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test in Docker

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build Docker image
        run: docker-compose build

      - name: Run tests
        run: docker-compose run --rm atemoya /bin/bash -c "eval \$(opam env) && dune runtest"
```

---

## Comparison: Docker vs Native

| Feature | Docker | Native |
|---------|--------|--------|
| **Setup time** | ~5 min (first build) | ~10-20 min (manual) |
| **Isolation** | ✅ Complete | ❌ Uses system |
| **Portability** | ✅ Works anywhere | ⚠️ OS-dependent |
| **Architecture** | ✅ ARM64 + x86_64 | ✅ Platform-native |
| **Performance** | ⚠️ ~5% overhead | ✅ Native speed |
| **Disk space** | ~2-3 GB image | ~1 GB dependencies |
| **Updates** | Rebuild image | `opam update` + `uv sync` |

**Use Docker when:**
- ✅ You have dependency conflicts on host
- ✅ You want quick setup
- ✅ You're on Windows/Mac
- ✅ You need reproducible environment

**Use Native when:**
- ✅ You need maximum performance
- ✅ You're actively developing OCaml/Python
- ✅ You already have OCaml/Python setup

---

## FAQ

**Q: What architectures are supported?**
A: Both ARM64 (Apple Silicon M1/M2/M3, AWS Graviton) and x86_64/amd64 (Intel/AMD). Docker automatically detects and uses the correct architecture.

**Q: Do I need to rebuild after changing code?**
A: No! Source code is mounted as a volume. Just re-run inside container.

**Q: Are outputs saved to my host machine?**
A: Yes! Output directories are mounted from host.

**Q: Can I use my IDE (VS Code, etc.)?**
A: Yes! Edit code on host, run in container. Or use VS Code Remote Containers extension.

**Q: How do I update dependencies?**
A: Modify `atemoya.opam` or `pyproject.toml`, then rebuild: `./docker-run.sh build`

**Q: Can I run multiple models simultaneously?**
A: Yes, open multiple shells: `./docker-run.sh shell` in different terminals.

---

## Support

Issues with Docker setup? Check:
1. Docker daemon is running: `docker ps`
2. Docker Compose is installed: `docker-compose --version`
3. Sufficient disk space: `df -h`
4. Container logs: `./docker-run.sh logs`

For general Atemoya issues, see model-specific `TROUBLESHOOTING.md` files.
