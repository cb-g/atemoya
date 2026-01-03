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
    echo "  up          Start the container (build if needed)"
    echo "  shell       Open interactive shell in container"
    echo "  exec        Execute quickstart.sh in container"
    echo "  down        Stop and remove containers"
    echo "  logs        Show container logs"
    echo "  clean       Remove all Docker resources (containers, volumes, images)"
    echo ""
    echo "Examples:"
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
    echo "1) Build Docker image"
    echo "2) Start container"
    echo "3) Open shell in container"
    echo "4) Run quickstart menu directly"
    echo "5) Stop container"
    echo "6) View logs"
    echo "7) Clean up (remove all Docker resources)"
    echo "8) Quit"
    echo ""
}

# Interactive mode if no arguments provided
if [ $# -eq 0 ]; then
    while true; do
        show_menu
        read -p "Enter your choice: " choice
        echo ""

        case $choice in
            1)
                echo -e "${GREEN}Building Atemoya Docker image...${NC}"
                $COMPOSE_CMD build
                echo ""
                read -p "Press Enter to continue..."
                ;;
            2)
                echo -e "${GREEN}Starting Atemoya container...${NC}"
                $COMPOSE_CMD up -d
                echo -e "${GREEN}✓ Container started!${NC}"
                echo ""
                echo "Next steps:"
                echo "  - Option 3: Open shell"
                echo "  - Option 4: Run quickstart menu"
                echo ""
                read -p "Press Enter to continue..."
                ;;
            3)
                echo -e "${GREEN}Opening shell in Atemoya container...${NC}"
                echo -e "${YELLOW}Tip: Run './quickstart.sh' inside the container${NC}"
                echo ""
                $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && exec /bin/bash"
                ;;
            4)
                echo -e "${GREEN}Running quickstart in Atemoya container...${NC}"
                echo ""
                $COMPOSE_CMD exec atemoya /bin/bash -c "eval \$(opam env) && ./quickstart.sh"
                ;;
            5)
                echo -e "${YELLOW}Stopping Atemoya container...${NC}"
                $COMPOSE_CMD down
                echo -e "${GREEN}✓ Container stopped${NC}"
                echo ""
                read -p "Press Enter to continue..."
                ;;
            6)
                echo -e "${GREEN}Showing container logs (Ctrl+C to exit)...${NC}"
                echo ""
                $COMPOSE_CMD logs -f atemoya
                ;;
            7)
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
            8)
                echo -e "${GREEN}Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${YELLOW}Invalid choice. Please enter 1-8.${NC}"
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

    up)
        echo -e "${GREEN}Starting Atemoya container...${NC}"
        $COMPOSE_CMD up -d
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
