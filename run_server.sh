#!/usr/bin/env bash
# 路径: /Users/huweihua/java/stock-mcp/run_server.sh
# 用途: 在项目中以两种模式启动服务："fastapi"(FastAPI web 服务) 和 "fastmcp"(MCP 后端)
# 提供 start|stop|status|restart 子命令，并支持自定义端口与日志级别。

set -euo pipefail
IFS=$'\n\t'

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="python3"
VENV="$PROJECT_ROOT/venv"
FASTAPI_SCRIPT="$PROJECT_ROOT/start_server.py"
FASTMCP_SCRIPT="$PROJECT_ROOT/main.py"
FASTAPI_PIDFILE="$PROJECT_ROOT/run_fastapi.pid"
FASTMCP_PIDFILE="$PROJECT_ROOT/run_fastmcp.pid"

# 默认配置
MODE="fastapi"     # fastapi | fastmcp
MCP_MODE="sse"     # 当 MODE=fastmcp 时传递给 main.py 的 --mode 参数 (stdio|sse|streamable-http)
PORT=8000
LOG_LEVEL="INFO"
NOHUP_OUT="/dev/null"

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|status|restart> [--mode fastapi|fastmcp] [--mcp-mode stdio|sse|streamable-http] [--port PORT] [--log-level LEVEL] [--python PYTHON]

Examples:
  # 启动 FastAPI (默认)
  ./run_server.sh start --mode fastapi --port 8000

  # 启动 MCP SSE 模式
  ./run_server.sh start --mode fastmcp --mcp-mode sse --port 8000

  # 停止 FastAPI 或 MCP（分别）
  ./run_server.sh stop --mode fastapi
  ./run_server.sh stop --mode fastmcp

  # 查看状态
  ./run_server.sh status --mode fastapi

EOF
  exit 1
}

parse_args() {
  if [ $# -lt 1 ]; then
    usage
  fi

  CMD="$1"
  shift || true

  while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
      --mode)
        MODE="$2"; shift 2;;
      --mcp-mode)
        MCP_MODE="$2"; shift 2;;
      --port)
        PORT="$2"; shift 2;;
      --log-level)
        LOG_LEVEL="$2"; shift 2;;
      --python)
        PYTHON="$2"; shift 2;;
      -h|--help)
        usage;;
      *)
        echo "Unknown argument: $1"; usage;;
    esac
  done
}

activate_venv_if_exists() {
  if [ -f "$VENV/bin/activate" ]; then
    # shellcheck disable=SC1090
    source "$VENV/bin/activate"
  fi
}

is_running() {
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local pid
    pid=$(cat "$pidfile")
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

start_fastapi() {
  if is_running "$FASTAPI_PIDFILE"; then
    echo "FastAPI already running (pid $(cat "$FASTAPI_PIDFILE"))"
    return
  fi

  echo "Starting FastAPI (目录: $PROJECT_ROOT, 端口: $PORT)"
  activate_venv_if_exists

  nohup "$PYTHON" "$FASTAPI_SCRIPT" >"$NOHUP_OUT" 2>&1 &
  echo $! > "$FASTAPI_PIDFILE"
  sleep 0.5
  echo "FastAPI started (pid $(cat "$FASTAPI_PIDFILE"))"
}

start_fastmcp() {
  if is_running "$FASTMCP_PIDFILE"; then
    echo "FastMCP already running (pid $(cat "$FASTMCP_PIDFILE"))"
    return
  fi

  echo "Starting FastMCP (模式: $MCP_MODE, 端口: $PORT)"
  activate_venv_if_exists

  nohup "$PYTHON" "$FASTMCP_SCRIPT" --mode "$MCP_MODE" --port "$PORT" --log-level "$LOG_LEVEL" >"$NOHUP_OUT" 2>&1 &
  echo $! > "$FASTMCP_PIDFILE"
  sleep 0.5
  echo "FastMCP started (pid $(cat "$FASTMCP_PIDFILE"))"
}

stop_pidfile() {
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local pid
    pid=$(cat "$pidfile")
    if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
      echo "Stopping pid $pid..."
      kill "$pid" || true
      sleep 0.3
      if kill -0 "$pid" >/dev/null 2>&1; then
        echo "PID $pid did not exit, sending SIGKILL..."
        kill -9 "$pid" || true
      fi
    fi
    rm -f "$pidfile"
    echo "Stopped (pidfile removed: $pidfile)"
  else
    echo "No pidfile at $pidfile"
  fi
}

status_pidfile() {
  local pidfile="$1"
  if is_running "$pidfile"; then
    echo "Running (pid $(cat "$pidfile"))"
  else
    echo "Not running"
  fi
}

# 主体
if [ "$#" -lt 1 ]; then
  usage
fi

MAIN_CMD="$1"
shift || true
parse_args "$MAIN_CMD" "$@" || true

case "$MAIN_CMD" in
  start)
    if [ "$MODE" = "fastapi" ]; then
      start_fastapi
    elif [ "$MODE" = "fastmcp" ]; then
      start_fastmcp
    else
      echo "Unknown mode: $MODE"; exit 1
    fi
    ;;
  stop)
    if [ "$MODE" = "fastapi" ]; then
      stop_pidfile "$FASTAPI_PIDFILE"
    elif [ "$MODE" = "fastmcp" ]; then
      stop_pidfile "$FASTMCP_PIDFILE"
    else
      echo "Unknown mode: $MODE"; exit 1
    fi
    ;;
  status)
    if [ "$MODE" = "fastapi" ]; then
      status_pidfile "$FASTAPI_PIDFILE"
    elif [ "$MODE" = "fastmcp" ]; then
      status_pidfile "$FASTMCP_PIDFILE"
    else
      echo "Unknown mode: $MODE"; exit 1
    fi
    ;;
  restart)
    if [ "$MODE" = "fastapi" ]; then
      stop_pidfile "$FASTAPI_PIDFILE"; start_fastapi
    elif [ "$MODE" = "fastmcp" ]; then
      stop_pidfile "$FASTMCP_PIDFILE"; start_fastmcp
    else
      echo "Unknown mode: $MODE"; exit 1
    fi
    ;;
  *)
    usage
    ;;
esac
