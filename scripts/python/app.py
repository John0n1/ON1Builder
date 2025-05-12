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
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import threading
import asyncio
import time
import logging
import sys
import os
from decimal import Decimal


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))


app = Flask(__name__, static_folder=None)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


ui_logger = setup_logging("FlaskUI", level=logging.INFO)


class BotState:
    def __init__(self):
        self.is_running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.main_core: Optional[MainCore] = None
        self.lock: threading.Lock = threading.Lock()


bot_state = BotState()


class WebSocketLogHandler(logging.Handler):
    MAX_QUEUE_SIZE = 200

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.log_queue = deque(maxlen=self.MAX_QUEUE_SIZE)

    def emit(self, record: logging.LogRecord):
        try:

            log_entry = {
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(record.created)
                ),
                "component": getattr(record, "component", None),
                "tx_hash": getattr(record, "tx_hash", None),
            }

            log_entry = {k: v for k, v in log_entry.items() if v is not None}

            self.log_queue.append(log_entry)

            socketio.emit("log_message", log_entry)

        except Exception as e:

            print(f"Error in WebSocketLogHandler: {e}", file=sys.stderr)
            self.handleError(record)


ws_handler = WebSocketLogHandler()

logging.getLogger().addHandler(ws_handler)

logging.getLogger().setLevel(logging.DEBUG)
ui_logger.info("WebSocketLogHandler attached to root logger.")


def run_bot_in_thread():
    """Target function for the bot's background thread."""

    global bot_state
    ui_logger.info("Bot thread started.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    with bot_state.lock:
        bot_state.loop = loop

        try:
            configuration = Configuration()

            bot_state.main_core = MainCore(configuration)
        except Exception as config_err:
            ui_logger.critical(
                "Failed to load configuration in bot thread: %s",
                config_err,
                exc_info=True,
            )
            bot_state.is_running = False
            return

    main_core_instance = bot_state.main_core

    try:

        loop.run_until_complete(main_core_instance.initialize_components())
        ui_logger.info("MainCore initialized successfully in bot thread.")

        loop.run_until_complete(main_core_instance.run())
        ui_logger.info("MainCore run loop finished in bot thread.")

    except Exception as e:
        ui_logger.critical(
            "An error occurred in the bot thread: %s",
            e,
            exc_info=True)

        if main_core_instance and main_core_instance.running:
            ui_logger.info("Attempting to stop MainCore due to error...")
            try:
                loop.call_soon_threadsafe(
                    asyncio.create_task, main_core_instance.stop()
                )
            except Exception as stop_err:
                ui_logger.error(
                    "Error scheduling stop after bot thread error: %s",
                    stop_err)

    finally:
        ui_logger.info("Bot thread finishing.")
        with bot_state.lock:

            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
                ui_logger.info("Bot thread event loop closed.")
            except Exception as loop_close_err:
                ui_logger.error(
                    "Error closing event loop in bot thread: %s",
                    loop_close_err)

            bot_state.is_running = False
            bot_state.loop = None


@app.route("/")
def serve_index():

    ui_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "ui"))
    return send_from_directory(ui_dir, "index.html")


@app.route("/<path:filename>")
def serve_static_files(filename):

    ui_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "ui"))
    return send_from_directory(ui_dir, filename)


@app.route("/start", methods=["POST"])
def start_bot():
    """Starts the bot in a background thread."""
    global bot_state
    with bot_state.lock:
        if not bot_state.is_running:
            bot_state.is_running = True
            bot_state.thread = threading.Thread(
                target=run_bot_in_thread, daemon=True, name="ON1BuilderBotThread")
            bot_state.thread.start()
            ui_logger.info(
                "Bot start request received. Starting background thread.")
            return jsonify({"status": "Bot starting..."}), 202
        else:
            ui_logger.warning(
                "Received start request, but bot is already running.")
            return jsonify({"status": "Bot is already running"}), 409


@app.route("/stop", methods=["POST"])
def stop_bot():
    """Requests the bot to stop gracefully."""
    global bot_state
    with bot_state.lock:
        if bot_state.is_running and bot_state.main_core and bot_state.loop:
            ui_logger.info(
                "Bot stop request received. Signaling MainCore to stop.")
            try:

                future = asyncio.run_coroutine_threadsafe(
                    bot_state.main_core.stop(), bot_state.loop
                )

                future.result(timeout=2)
                return jsonify({"status": "Bot stopping..."}), 202
            except TimeoutError:
                ui_logger.warning(
                    "Timeout waiting for stop() initiation acknowledgement."
                )
                return (
                    jsonify({"status": "Stop signal sent, acknowledgement timeout."}),
                    202,
                )
            except Exception as e:
                ui_logger.error(
                    "Error occurred while trying to stop the bot: %s",
                    e,
                    exc_info=True)
                return jsonify({"status": "Error signaling stop"}), 500
        elif bot_state.is_running:

            ui_logger.warning(
                "Stop requested, but bot state is inconsistent (running=True, but core/loop missing). Forcing state update."
            )
            bot_state.is_running = False
            return (
                jsonify(
                    {"status": "Bot was in inconsistent running state. State reset."}
                ),
                409,
            )
        else:
            ui_logger.info("Stop requested, but bot is not running.")
            return jsonify({"status": "Bot is not running"}), 400


@app.route("/status", methods=["GET"])
def get_status():
    """Returns the current status of the bot and its components."""
    global bot_state
    with bot_state.lock:
        status = {"bot_running": bot_state.is_running}
        core = bot_state.main_core
        if core:
            status["components_initialized"] = {
                name: comp is not None for name,
                comp in core.components.items()}

            if hasattr(core, "_component_health"):
                status["components_health"] = core._component_health

        else:
            status["components_initialized"] = {}
            status["components_health"] = {}

    return jsonify(status), 200


def run_async_from_sync(coro):
    """Runs an async coroutine from a sync context (Flask route)."""
    global bot_state
    loop = None
    with bot_state.lock:
        if bot_state.is_running and bot_state.loop and bot_state.loop.is_running():
            loop = bot_state.loop

    if loop:
        try:

            future = asyncio.run_coroutine_threadsafe(coro, loop)

            return future.result(timeout=5)
        except asyncio.TimeoutError:
            ui_logger.error(
                "Timeout waiting for async result in run_async_from_sync.")
            return None
        except Exception as e:
            ui_logger.error(
                "Error running async task from sync context: %s",
                e,
                exc_info=True)
            return None
    else:

        ui_logger.warning(
            "Cannot run async task: Bot is not running or loop is unavailable."
        )
        return None


def _safe_get(obj: Optional[object], attr: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, attr, default)


def _safe_get_nested(
    obj: Optional[object], attrs: List[str], default: Any = None
) -> Any:
    current = obj
    for attr in attrs:
        if current is None:
            return default
        current = getattr(current, attr, None)
    return current if current is not None else default


def get_live_metrics() -> Dict[str, Any]:
    """Fetches live metrics from running bot components."""
    default_metrics = {
        "timestamp": time.time(),
        "strategy_performance": {},
        "overall_profit_eth": "0.0",
        "account_balance_eth": "N/A",
        "network_congestion_pct": "N/A",
        "avg_gas_price_gwei": "N/A",
        "mempool_queue_sizes": {},
        "cache_stats": {},
    }
    if not bot_state.is_running or not bot_state.main_core:
        return default_metrics

    core = bot_state.main_core
    metrics = default_metrics.copy()

    try:

        safety_net: Optional[SafetyNet] = core.components.get("safety_net")
        strategy_net: Optional[StrategyNet] = core.components.get("strategy_net")
        mempoolmon: Optional[TxpoolMonitor] = core.components.get(
            "txpool_monitor")
        nonce_core: Optional[NonceCore] = core.components.get("nonce_core")

        # --- Account Balance (Async) ---
        if safety_net and isinstance(safety_net.account, LocalAccount):
            balance = run_async_from_sync(safety_net.get_balance())
            metrics["account_balance_eth"] = (
                f"{balance:.8f}" if isinstance(balance, Decimal) else "Error"
            )
        else:
            metrics["account_balance_eth"] = "N/A (SafetyNet Error)"

        # --- Strategy Performance ---
        if strategy_net:
            overall_profit = Decimal("0")
            perf_data = {}
            for stype, perf_metrics in strategy_net.strategy_performance.items():

                perf_data[stype] = {
                    "executions": _safe_get(
                        perf_metrics,
                        "total_executions",
                        0),
                    "success_rate": f"{
                        _safe_get(
                            perf_metrics,
                            'success_rate',
                            0.0):.2%}",
                    "avg_exec_time_ms": f"{
                        _safe_get(
                            perf_metrics,
                            'avg_execution_time',
                            0.0) * 1000:.2f}",
                    "total_profit_eth": f"{
                        _safe_get(
                            perf_metrics,
                            'total_profit',
                            Decimal('0')):.8f}",
                }
                overall_profit += _safe_get(perf_metrics,
                                            "total_profit", Decimal("0"))
            metrics["strategy_performance"] = perf_data
            metrics["overall_profit_eth"] = f"{overall_profit:.8f}"

        # --- Network & Gas (Async) ---
        if safety_net:
            congestion = run_async_from_sync(
                safety_net.get_network_congestion())
            metrics["network_congestion_pct"] = (
                f"{congestion * 100:.2f}%" if isinstance(congestion, float) else "Error"
            )

            gas_price = run_async_from_sync(safety_net.get_dynamic_gas_price())
            metrics["avg_gas_price_gwei"] = (
                f"{gas_price:.2f}" if isinstance(gas_price, Decimal) else "Error"
            )

        # --- Queue Sizes ---
        if mempoolmon:
            metrics["mempool_queue_sizes"] = {
                "hash_queue": _safe_get_nested(
                    mempoolmon, ["_tx_hash_queue", "qsize"], -1
                )(),
                "analysis_queue": _safe_get_nested(
                    mempoolmon, ["_tx_analysis_queue", "qsize"], -1
                )(),
                "profit_queue": _safe_get_nested(
                    mempoolmon, ["profitable_transactions", "qsize"], -1
                )(),
            }

        # --- Cache Stats (Example for one cache) ---
        if mempoolmon:
            processed_cache: Optional[TTLCache] = _safe_get(
                mempoolmon, "processed_transactions"
            )
            if processed_cache:
                metrics["cache_stats"]["processed_tx"] = {
                    "size": len(processed_cache),
                    "max_size": processed_cache.maxsize,
                    "ttl": processed_cache.ttl,
                }

        # --- Nonce ---
        if nonce_core:
            current_nonce = run_async_from_sync(nonce_core.get_nonce())
            pending_tx_count = len(
                _safe_get(
                    nonce_core,
                    "pending_transactions",
                    set()))
            metrics["nonce_info"] = {
                "current_nonce": (
                    current_nonce if isinstance(current_nonce, int) else "Error"
                ),
                "pending_tracked_tx": pending_tx_count,
                "cache_ttl": _safe_get_nested(
                    nonce_core, ["configuration", "NONCE_CACHE_TTL"]
                ),
            }

    except Exception as e:
        ui_logger.error("Error gathering live metrics: %s", e, exc_info=True)
        metrics["error"] = f"Failed to gather some metrics: {e}"

    metrics["timestamp"] = time.time()
    return metrics


@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Returns live operational metrics from the bot."""

    live_metrics = get_live_metrics()

    return jsonify(live_metrics), 200


@app.route("/components", methods=["GET"])
def get_components_status():
    """Returns the initialization status of components."""
    global bot_state
    with bot_state.lock:
        core = bot_state.main_core
        if core and hasattr(core, "components"):

            status = {
                name: comp is not None for name,
                comp in core.components.items()}
            return jsonify(status), 200
        else:
            return (
                jsonify({"error": "Bot not running or components not initialized"}),
                404,
            )


@app.route("/logs", methods=["GET"])
def get_logs():
    """Returns recent buffered logs."""

    log_list = list(ws_handler.log_queue)
    return jsonify(log_list)


# --- WebSocket Events ---
@socketio.on("connect")
def handle_connect():
    """Handles new client connections by sending initial logs."""
    ui_logger.info(f"Client connected: {request.sid}")

    initial_logs = list(ws_handler.log_queue)
    emit("initial_logs", initial_logs)


@socketio.on("disconnect")
def handle_disconnect():
    """Handles client disconnections."""
    ui_logger.info(f"Client disconnected: {request.sid}")


@socketio.on("request_metrics")
def handle_request_metrics():
    """Handles client requests for updated metrics."""
    ui_logger.debug(f"Metrics requested by client: {request.sid}")
    live_metrics = get_live_metrics()
    emit("update_metrics", live_metrics)


# --- Main Execution ---
if __name__ == "__main__":
    ui_logger.info("Starting Flask development server with SocketIO...")

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False)
