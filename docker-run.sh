#!/bin/bash
# Helper script to run Atemoya in Docker Compose

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Atemoya Docker Setup ===${NC}\n"

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Error: Docker is not installed${NC}"
    echo "Please install Docker from https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo -e "${YELLOW}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose from https://docs.docker.com/compose/install/"
    exit 1
fi

# Use 'docker compose' (v2) if available, otherwise 'docker-compose' (v1)
if docker compose version &> /dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  build       Build the Docker image"
    echo "  rebuild     Build the Docker image without cache (fresh build)"
    echo "  up          Start the container (build if needed)"
    echo "  shell       Open interactive shell in container"
    echo "  exec        Execute quickstart.sh in container"
    echo "  down        Stop and remove containers"
    echo "  logs        Show container logs"
    echo "  clean       Remove all Docker resources (containers, volumes, images)"
    echo ""
    echo "Examples:"
    echo "  $0 build      # Build image"
    echo "  $0 rebuild    # Build image without cache"
    echo "  $0 up         # Start container"
    echo "  $0 shell      # Get interactive shell"
    echo "  $0 exec       # Run quickstart menu"
}

# Function to show interactive menu
show_menu() {
    echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                              ║${NC}"
    echo -e "${BLUE}║           ATEMOYA DOCKER MANAGER             ║${NC}"
    echo -e "${BLUE}║                                              ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}1)${NC} Build Docker image"
    echo -e "${GREEN}2)${NC} Build Docker image (no cache)"
    echo -e "${GREEN}3)${NC} Start container"
    echo -e "${GREEN}4)${NC} Open shell in container"
    echo -e "${GREEN}5)${NC} Run quickstart menu directly (default)"
    echo -e "${GREEN}6)${NC} Stop container"
    echo -e "${GREEN}7)${NC} View logs"
    echo -e "${GREEN}8)${NC} Clean up (remove all Docker resources)"
    echo ""
    echo -e "${GREEN}0)${NC} Quit"
    echo ""
}

# Interactive mode if no arguments provided
if [ $# -eq 0 ]; then
    while true; do
        show_menu
        read -p "Enter your choice (default 5): " choice
        choice=${choice:-5}
        echo ""

        case $choice in
            1)
                echo -e "${GREEN}Building Atemoya Docker image...${NC}"
                $COMPOSE_CMD build
                echo ""
                read -p "Press Enter to continue..."
                ;;
            2)
                echo -e "${GREEN}Building Atemoya Docker image (no cache)...${NC}"
                echo -e "${YELLOW}This will rebuild from scratch, ignoring cached layers${NC}"
                $COMPOSE_CMD build --no-cache
                echo ""
                read -p "Press Enter to continue..."
                ;;
            3)
                echo -e "${GREEN}Starting Atemoya container...${NC}"
                $COMPOSE_CMD up -d --no-build
                echo -e "${GREEN}✓ Container started!${NC}"
                echo ""
                echo "Next steps:"
                echo "  - Option 4: Open shell"
                echo "  - Option 5: Run quickstart menu"
                echo ""
                read -p "Press Enter to continue..."
                ;;
            4)
                echo -e "${GREEN}Opening shell in Atemoya container...${NC}"
                echo -e "${YELLOW}Tip: Run './quickstart.sh' inside the container${NC}"
                echo ""
                $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && exec /bin/bash"
                ;;
            5)
                echo -e "${GREEN}Running quickstart in Atemoya container...${NC}"
                echo ""
                $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && ./quickstart.sh"
                ;;
            6)
                echo -e "${YELLOW}Stopping Atemoya container...${NC}"
                $COMPOSE_CMD down
                echo -e "${GREEN}✓ Container stopped${NC}"
                echo ""
                read -p "Press Enter to continue..."
                ;;
            7)
                echo -e "${GREEN}Showing container logs (Ctrl+C to exit)...${NC}"
                echo ""
                $COMPOSE_CMD logs -f atemoya
                ;;
            8)
                echo -e "${YELLOW}=== Docker Cleanup ===${NC}\n"
                echo "This will remove:"
                echo "  - Atemoya container"
                echo "  - Docker volumes (uv cache)"
                echo "  - Atemoya Docker image (~2-3 GB)"
                echo "  - Docker networks"
                echo ""
                echo -e "${YELLOW}Note: Your source code and outputs are NOT affected${NC}"
                echo ""
                read -p "Continue? (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    echo -e "\n${GREEN}Stopping containers...${NC}"
                    $COMPOSE_CMD down -v 2>/dev/null || true

                    echo -e "${GREEN}Removing Atemoya image...${NC}"
                    docker rmi atemoya:latest 2>/dev/null || echo "  (Image not found, skipping)"

                    echo -e "${GREEN}Removing dangling images...${NC}"
                    docker image prune -f 2>/dev/null || true

                    echo -e "\n${GREEN}✓ Cleanup complete!${NC}"
                else
                    echo -e "\n${YELLOW}Cleanup canceled${NC}"
                fi
                echo ""
                read -p "Press Enter to continue..."
                ;;
            0)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${YELLOW}Invalid choice. Please enter 1-8 or 0.${NC}"
                echo ""
                read -p "Press Enter to continue..."
                ;;
        esac
    done
fi

# Command-line mode (for advanced users)
COMMAND=${1}

case "$COMMAND" in
    build)
        echo -e "${GREEN}Building Atemoya Docker image...${NC}"
        $COMPOSE_CMD build
        ;;

    rebuild)
        echo -e "${GREEN}Building Atemoya Docker image (no cache)...${NC}"
        echo -e "${YELLOW}This will rebuild from scratch, ignoring cached layers${NC}"
        $COMPOSE_CMD build --no-cache
        ;;

    up)
        echo -e "${GREEN}Starting Atemoya container...${NC}"
        $COMPOSE_CMD up -d --no-build
        echo -e "${GREEN}Container started!${NC}"
        echo -e "Run: ${BLUE}$0 shell${NC} to enter the container"
        echo -e "Or:  ${BLUE}$0 exec${NC} to run the quickstart menu"
        ;;

    shell)
        echo -e "${GREEN}Opening shell in Atemoya container...${NC}"
        $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && exec /bin/bash"
        ;;

    exec)
        echo -e "${GREEN}Running quickstart in Atemoya container...${NC}"
        $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && ./quickstart.sh"
        ;;

    down)
        echo -e "${YELLOW}Stopping Atemoya container...${NC}"
        $COMPOSE_CMD down
        ;;

    logs)
        $COMPOSE_CMD logs -f atemoya
        ;;

    clean)
        echo -e "${YELLOW}=== Docker Cleanup ===${NC}\n"
        echo "This will remove:"
        echo "  - Atemoya container"
        echo "  - Docker volumes (uv cache)"
        echo "  - Atemoya Docker image (~2-3 GB)"
        echo "  - Docker networks"
        echo ""
        echo -e "${YELLOW}Note: Your source code and outputs are NOT affected${NC}"
        echo ""
        read -p "Continue? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "\n${GREEN}Stopping containers...${NC}"
            $COMPOSE_CMD down -v 2>/dev/null || true

            echo -e "${GREEN}Removing Atemoya image...${NC}"
            docker rmi atemoya:latest 2>/dev/null || echo "  (Image not found, skipping)"

            echo -e "${GREEN}Removing dangling images...${NC}"
            docker image prune -f 2>/dev/null || true

            echo -e "\n${GREEN}✓ Cleanup complete!${NC}"
            echo ""
            echo "To rebuild: ${BLUE}$0 build${NC}"
        else
            echo -e "\n${YELLOW}Cleanup canceled${NC}"
        fi
        ;;

    help|--help|-h)
        show_usage
        ;;

    *)
        echo -e "${YELLOW}Unknown command: $COMMAND${NC}\n"
        show_usage
        exit 1
        ;;
esac
