#!/usr/bin/env bash
# Start BrightBean Studio development server
# Usage: ./start.sh              # server only
#        ./start.sh --all        # server + worker + tailwind (3 tmux panes)
#        ./start.sh --bg         # server in background
#        ./start.sh --restart    # kill existing tmux session and restart --all

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Activate venv
source .venv/bin/activate

start_server() {
    echo "Starting Django server on http://localhost:8000 ..."
    python manage.py runserver
}

start_worker() {
    echo "Starting background worker..."
    python manage.py process_tasks
}

start_tailwind() {
    echo "Starting Tailwind CSS watcher..."
    cd theme/static_src && npm run start
}

case "${1:-}" in
    --all)
        if command -v tmux &>/dev/null; then
            SESSION="brightbean"
            tmux new-session -d -s "$SESSION" -n server   "cd $PROJECT_DIR && source .venv/bin/activate && python manage.py runserver"
            tmux new-window -t "$SESSION" -n worker        "cd $PROJECT_DIR && source .venv/bin/activate && python manage.py process_tasks"
            tmux new-window -t "$SESSION" -n tailwind      "cd $PROJECT_DIR/theme/static_src && npm run start"
            tmux attach -t "$SESSION"
        else
            echo "tmux not found. Starting server in foreground (worker + tailwind skipped)."
            echo "Install tmux: sudo apt install tmux"
            start_server
        fi
        ;;
    --bg)
        nohup python manage.py runserver > /tmp/brightbean-server.log 2>&1 &
        echo "Server started in background (PID $!). Logs: /tmp/brightbean-server.log"
        echo "http://localhost:8000/accounts/login/"
        ;;
    --restart)
        if command -v tmux &>/dev/null; then
            tmux kill-session -t brightbean 2>/dev/null || true
            echo "Old session killed. Restarting..."
            SCRIPT="$(realpath "$0")"
            exec bash "$SCRIPT" --all
        else
            echo "tmux not found. Can't restart tmux sessions."
            exit 1
        fi
        ;;
    *)        start_server
        ;;
esac
