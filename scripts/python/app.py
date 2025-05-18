from eth_account.signers.local import LocalAccount
from nonce_core import NonceCore
from safety_net import SafetyNet
from strategy_net import StrategyNet
from txpool_monitor import TxpoolMonitor
from logger_on1 import setup_logging
from configuration import Configuration
from main_core import MainCore
from collections import deque
from typing import Any, Dict, List, Optional
from cachetools import TTLCache
from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import threading
import asyncio
import time
import logging
import sys
import os
from decimal import Decimal
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))


app = Flask(__name__, static_folder="../../ui", template_folder="../../ui")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


ui_logger = setup_logging("FlaskUI", level=logging.INFO)


# Add rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)


class BotState:
    def __init__(self):
        self.running = False
        self.start_time = None
        self.status = "stopped"
        self.metrics = {}
        self.logs = []
        

bot_state = BotState()


class WebSocketLogHandler(logging.Handler):
    MAX_QUEUE_SIZE = 200
    
    def __init__(self):
        super().__init__()
        self.logs = []
        
    def emit(self, record: logging.LogRecord):
        log_entry = {
            "timestamp": time.time(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module
        }
        self.logs.append(log_entry)
        
        # Trim logs to prevent memory issues
        if len(self.logs) > self.MAX_QUEUE_SIZE:
            self.logs = self.logs[-self.MAX_QUEUE_SIZE:]
            
        # Emit to WebSocket clients
        socketio.emit("log", log_entry)


ws_handler = WebSocketLogHandler()

logging.getLogger().addHandler(ws_handler)

logging.getLogger().setLevel(logging.DEBUG)
ui_logger.info("WebSocketLogHandler attached to root logger.")


def run_bot_in_thread():
    """Run the bot in a separate thread."""
    global bot_state, core
    
    # Update state
    bot_state.running = True
    bot_state.start_time = time.time()
    bot_state.status = "starting"
    socketio.emit("status_update", {"status": "starting"})
    
    try:
        # Create and run event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the core
        loop.run_until_complete(core.run())
        
        # Update state on success
        bot_state.status = "running"
        socketio.emit("status_update", {"status": "running"})
        
        # Start metrics update task
        update_metrics_task = loop.create_task(update_metrics_periodically(loop))
        
        # Run the loop
        loop.run_forever()
        
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
        bot_state.status = "error"
        bot_state.running = False
        socketio.emit("status_update", {"status": "error", "error": str(e)})
    finally:
        if loop and not loop.is_closed():
            loop.close()


async def update_metrics_periodically(loop):
    """Update metrics from the core periodically."""
    global bot_state, core
    
    while bot_state.running:
        try:
            metrics = get_live_metrics()
            bot_state.metrics = metrics
            socketio.emit("metrics_update", metrics)
        except Exception as e:
            logger.warning(f"Error updating metrics: {e}")
            
        await asyncio.sleep(2)  # Update every 2 seconds


@app.route("/")
@limiter.exempt  # Don't rate limit the main UI
def serve_index():
    """Serve the main UI page."""
    return render_template("index.html")


@app.route("/<path:filename>")
def serve_static_files(filename):
    """Serve static files from the UI directory."""
    return send_from_directory(app.static_folder, filename)


@app.route("/start", methods=["POST"])
@limiter.limit("5/minute")  # Rate limit starting the bot
def start_bot():
    """Start the bot if it's not already running."""
    global bot_state, bot_thread, core, configuration
    
    try:
        if bot_state.running:
            return jsonify({"status": "error", "message": "Bot is already running"})
        
        # Initialize if not already done
        if not core:
            configuration = Configuration()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(configuration.load())
            core = MainCore(configuration)
            loop.run_until_complete(core.initialize())
        
        # Start bot in a separate thread
        bot_thread = threading.Thread(target=run_bot_in_thread)
        bot_thread.daemon = True
        bot_thread.start()
        
        return jsonify({"status": "success", "message": "Bot started"})
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)})


@app.route("/stop", methods=["POST"])
@limiter.limit("5/minute")  # Rate limit stopping the bot
def stop_bot():
    """Stop the bot if it's running."""
    global bot_state, bot_thread, core, loop
    
    try:
        if not bot_state.running:
            return jsonify({"status": "error", "message": "Bot is not running"})
        
        # Flag bot as stopping
        bot_state.status = "stopping"
        socketio.emit("status_update", {"status": "stopping"})
        
        # Stop the bot
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(stop_core_async)
            
        # Update state
        bot_state.running = False
        bot_state.status = "stopped"
        socketio.emit("status_update", {"status": "stopped"})
        
        return jsonify({"status": "success", "message": "Bot stopped"})
        
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)})


def stop_core_async():
    """Stop the core in the event loop."""
    global loop, core
    
    if loop and core:
        asyncio.create_task(core.stop())
        loop.stop()


@app.route("/status", methods=["GET"])
def get_status():
    """Get the current status of the bot."""
    global bot_state
    
    status_data = {
        "status": bot_state.status,
        "running": bot_state.running,
        "uptime": time.time() - bot_state.start_time if bot_state.start_time else 0,
        "metrics": bot_state.metrics
    }
    
    return jsonify(status_data)


def run_async_from_sync(coro):
    """Run an async function from a sync context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _safe_get(obj: Optional[object], attr: str, default: Any = None) -> Any:
    """Safely get an attribute from an object."""
    return getattr(obj, attr, default) if obj is not None else default


def _safe_get_nested(
    obj: Optional[object], attrs: List[str], default: Any = None
) -> Any:
    """Safely get nested attributes from an object."""
    result = obj
    for attr in attrs:
        result = _safe_get(result, attr)
        if result is None:
            return default
    return result


def get_live_metrics() -> Dict[str, Any]:
    """Get live metrics from the bot core."""
    global core
    
    metrics = {
        "timestamp": time.time(),
        "wallet": {
            "balance": 0,
            "transactions": 0,
            "gas_spent": 0
        },
        "market": {
            "gas_price": 0,
            "network_congestion": 0
        },
        "performance": {
            "total_profit": 0,
            "highest_profit_tx": None,
            "strategies": {}
        },
        "system": {
            "memory_usage_mb": 0,
            "cpu_usage": 0
        }
    }
    
    # If core is not running, return default metrics
    if not core:
        return metrics
    
    try:
        # Extract metrics from core components
        if hasattr(core, "safety_net"):
            metrics["market"]["gas_price"] = run_async_from_sync(core.safety_net.get_dynamic_gas_price())
            metrics["market"]["network_congestion"] = run_async_from_sync(core.safety_net.get_network_congestion())
        
        # Get balance and transactions
        if hasattr(core, "web3") and hasattr(core.web3, "eth") and core.account:
            metrics["wallet"]["balance"] = run_async_from_sync(core.web3.eth.get_balance(core.account.address)) / 10**18
        
        # Get strategy metrics if available
        if hasattr(core, "strategy_net") and hasattr(core.strategy_net, "weights"):
            metrics["performance"]["strategies"] = core.strategy_net.weights
        
        # Get system metrics
        import psutil
        process = psutil.Process(os.getpid())
        metrics["system"]["memory_usage_mb"] = process.memory_info().rss / (1024 * 1024)
        metrics["system"]["cpu_usage"] = psutil.cpu_percent()
        
    except Exception as e:
        logger.warning(f"Error collecting metrics: {e}")
    
    return metrics


@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Get current metrics."""
    return jsonify(get_live_metrics())


@app.route("/components", methods=["GET"])
def get_components_status():
    """Get status of all components."""
    global core
    
    if not core:
        return jsonify({"status": "not_initialized"})
    
    components = {
        "core": "initialized",
        "web3": "connected" if _safe_get(core, "web3") else "disconnected",
        "safety_net": "active" if _safe_get(core, "safety_net") else "inactive",
        "strategy_net": "active" if _safe_get(core, "strategy_net") else "inactive",
        "market_monitor": "active" if _safe_get(core, "market_monitor") else "inactive",
        "txpool_monitor": "active" if _safe_get(core, "txpool_monitor") else "inactive",
    }
    
    return jsonify(components)


@app.route("/logs", methods=["GET"])
def get_logs():
    """Get recent logs."""
    global log_handler
    
    # Return the last 100 logs
    return jsonify(log_handler.logs[-100:])


# --- WebSocket Events ---
@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection."""
    logger.debug(f"Client connected: {request.sid}")
    socketio.emit("status_update", {"status": bot_state.status})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.debug(f"Client disconnected: {request.sid}")


@socketio.on("request_metrics")
def handle_request_metrics():
    """Handle metrics request from WebSocket client."""
    socketio.emit("metrics_update", get_live_metrics())


# --- Main Execution ---
if __name__ == "__main__":
    ui_logger.info("Starting Flask development server with SocketIO...")

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False)
