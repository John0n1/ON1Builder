#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ON1Builder – API Server with Multi-Chain Support
=============================================
Provides API endpoints for monitoring and controlling the bot.
"""

import os
import sys
import json
import logging
import asyncio
import time
import datetime
import html
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from configuration_multi_chain import MultiChainConfiguration
from multi_chain_core import MultiChainCore

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log"),
    ],
)
logger = logging.getLogger("App")

# Create Flask app
app = Flask(__name__)
CORS(app)

# Global variables
config = None
core = None
bot_status = "stopped"
bot_task = None

# Initialize configuration and core
async def initialize() -> bool:
    """Initialize the configuration and core.
    
    Returns:
        True if initialization was successful, False otherwise
    """
    global config, core
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = MultiChainConfiguration()
        
        # Create core
        logger.info("Creating MultiChainCore...")
        core = MultiChainCore(config)
        
        # Initialize core
        logger.info("Initializing MultiChainCore...")
        success = await core.initialize()
        if not success:
            logger.error("Failed to initialize MultiChainCore")
            return False
        
        logger.info("Initialization complete")
        return True
    except Exception as e:
        logger.error(f"Error during initialization: {e}")
        return False

# Health check
@app.route("/healthz", methods=["GET"])
def healthz() -> Tuple[Dict[str, Any], int]:
    """Health check endpoint.
    
    Returns:
        A tuple of (response, status_code)
    """
    try:
        # Check if configuration is loaded
        if config is None:
            return jsonify({
                "status": "error",
                "message": "Configuration not loaded",
                "go_live": False,
            }), 500
        
        # Check if core is initialized
        if core is None:
            return jsonify({
                "status": "error",
                "message": "Core not initialized",
                "go_live": config.GO_LIVE,
            }), 500
        
        # Check if any chains are active
        if not core.workers:
            return jsonify({
                "status": "error",
                "message": "No active chains",
                "go_live": config.GO_LIVE,
            }), 500
        
        # Check Vault connectivity if GO_LIVE is true
        if config.GO_LIVE:
            if not hasattr(config, "VAULT_ADDR") or not config.VAULT_ADDR:
                return jsonify({
                    "status": "error",
                    "message": "VAULT_ADDR not set",
                    "go_live": config.GO_LIVE,
                }), 500
            
            if not hasattr(config, "VAULT_TOKEN") or not config.VAULT_TOKEN:
                return jsonify({
                    "status": "error",
                    "message": "VAULT_TOKEN not set",
                    "go_live": config.GO_LIVE,
                }), 500
        
        # All checks passed
        return jsonify({
            "status": "ok",
            "message": "Service is healthy",
            "go_live": config.GO_LIVE,
            "active_chains": len(core.workers),
            "bot_status": bot_status,
        }), 200
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error in health check: {str(e)}",
            "go_live": getattr(config, "GO_LIVE", False) if config else False,
        }), 500

# Metrics endpoint
@app.route("/metrics", methods=["GET"])
def metrics() -> Dict[str, Any]:
    """Metrics endpoint.
    
    Returns:
        A dictionary of metrics
    """
    try:
        # Check if core is initialized
        if core is None:
            return jsonify({
                "status": "error",
                "message": "Core not initialized",
            }), 500
        
        # Get metrics from core
        metrics = core.get_metrics()
        
        # Add bot status
        metrics["bot_status"] = bot_status
        
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting metrics: {str(e)}",
        }), 500

# Status endpoint
@app.route("/status", methods=["GET"])
def status() -> Dict[str, Any]:
    """Status endpoint.
    
    Returns:
        A dictionary with the current status
    """
    try:
        return jsonify({
            "status": bot_status,
            "go_live": getattr(config, "GO_LIVE", False) if config else False,
            "dry_run": getattr(config, "DRY_RUN", True) if config else True,
            "active_chains": len(core.workers) if core else 0,
            "uptime": core.metrics["uptime_seconds"] if core else 0,
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error getting status: {str(e)}",
        }), 500

# Start bot endpoint
@app.route("/start", methods=["POST"])
def start_bot() -> Dict[str, Any]:
    """Start the bot.
    
    Returns:
        A dictionary with the result
    """
    global bot_status, bot_task
    
    try:
        # Check if bot is already running
        if bot_status == "running":
            return jsonify({
                "status": "error",
                "message": "Bot is already running",
            }), 400
        
        # Check if core is initialized
        if core is None:
            return jsonify({
                "status": "error",
                "message": "Core not initialized",
            }), 500
        
        # Start the bot
        logger.info("Starting bot...")
        bot_status = "starting"
        
        # Create task to run the core
        async def run_core():
            global bot_status
            try:
                bot_status = "running"
                await core.run()
            except Exception as e:
                logger.error(f"Error running core: {e}")
            finally:
                bot_status = "stopped"
        
        # Start the task
        loop = asyncio.get_event_loop()
        bot_task = loop.create_task(run_core())
        
        return jsonify({
            "status": "success",
            "message": "Bot started",
        })
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        bot_status = "error"
        return jsonify({
            "status": "error",
            "message": f"Error starting bot: {str(e)}",
        }), 500

# Stop bot endpoint
@app.route("/stop", methods=["POST"])
def stop_bot() -> Dict[str, Any]:
    """Stop the bot.
    
    Returns:
        A dictionary with the result
    """
    global bot_status, bot_task
    
    try:
        # Check if bot is running
        if bot_status != "running":
            return jsonify({
                "status": "error",
                "message": f"Bot is not running (status: {bot_status})",
            }), 400
        
        # Check if core is initialized
        if core is None:
            return jsonify({
                "status": "error",
                "message": "Core not initialized",
            }), 500
        
        # Stop the bot
        logger.info("Stopping bot...")
        bot_status = "stopping"
        
        # Create task to stop the core
        async def stop_core():
            global bot_status
            try:
                await core.stop()
                if bot_task:
                    bot_task.cancel()
            except Exception as e:
                logger.error(f"Error stopping core: {e}")
            finally:
                bot_status = "stopped"
        
        # Start the task
        loop = asyncio.get_event_loop()
        loop.create_task(stop_core())
        
        return jsonify({
            "status": "success",
            "message": "Bot stopping",
        })
    except Exception as e:
        logger.error(f"Error stopping bot: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "An internal error occurred while stopping the bot.",
        }), 500

# Test alert endpoint
@app.route("/api/test-alert", methods=["POST"])
def test_alert() -> Dict[str, Any]:
    """Send a test alert.
    
    Returns:
        A dictionary with the result
    """
    try:
        # Check if core is initialized
        if core is None:
            return jsonify({
                "status": "error",
                "message": "Core not initialized",
            }), 500
        
        # Log test alert
        logger.info("Sending test alert")
        
        # Implementation of alert sending
        message = request.json.get("message", "Test alert from ON1Builder")
        level = request.json.get("level", "INFO")
        
        # Send Slack alert if configured
        if os.environ.get("SLACK_WEBHOOK_URL"):
            try:
                import requests
                webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
                icon = "🟢" if level == "INFO" else "🔴"
                
                payload = {
                    "text": f"{icon} *ON1Builder Alert*",
                    "attachments": [
                        {
                            "color": "#36a64f" if level == "INFO" else "#ff0000",
                            "title": f"{level} Alert",
                            "text": message,
                            "fields": [
                                {
                                    "title": "Environment",
                                    "value": os.environ.get("ENVIRONMENT", "production"),
                                    "short": True
                                },
                                {
                                    "title": "Time",
                                    "value": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "short": True
                                }
                            ]
                        }
                    ]
                }
                
                requests.post(webhook_url, json=payload, timeout=5)
                logger.info(f"Sent Slack alert: {message}")
            except Exception as e:
                logger.error(f"Error sending Slack alert: {e}")
        
        # Send email alert if configured
        if all(os.environ.get(key) for key in ["SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_EMAIL"]):
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                smtp_server = os.environ.get("SMTP_SERVER")
                smtp_port = int(os.environ.get("SMTP_PORT", "587"))
                smtp_user = os.environ.get("SMTP_USERNAME")
                smtp_password = os.environ.get("SMTP_PASSWORD")
                to_email = os.environ.get("ALERT_EMAIL")
                
                msg = MIMEMultipart()
                msg["Subject"] = f"ON1Builder {level} Alert"
                msg["From"] = smtp_user
                msg["To"] = to_email
                
                html_content = f"""
                <html>
                <body>
                    <h2>ON1Builder Alert</h2>
                    <p><strong>Level:</strong> {level}</p>
                    <p><strong>Message:</strong> {message}</p>
                    <p><strong>Time:</strong> {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p><strong>Environment:</strong> {os.environ.get("ENVIRONMENT", "production")}</p>
                </body>
                </html>
                """
                
                msg.attach(MIMEText(html_content, "html"))
                
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                    server.send_message(msg)
                    
                logger.info(f"Sent email alert to {to_email}")
            except Exception as e:
                logger.error(f"Error sending email alert: {e}")
        
        return jsonify({
            "status": "success",
            "message": "Test alert sent",
        })
    except Exception as e:
        logger.error(f"Error sending test alert: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "An internal error occurred while sending the test alert.",
        }), 500

# Simulate transaction endpoint
@app.route("/api/simulate-transaction", methods=["POST"])
def simulate_transaction() -> Dict[str, Any]:
    """Simulate a transaction."""
    try:
        data = request.json
        if not data or not isinstance(data, dict):
            return {"success": False, "error": "Invalid request format"}, 400
            
        required_fields = ["tx_hash", "chain_id"]
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return {
                "success": False, 
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            }, 400
            
        # Get transaction data
        tx_hash = data["tx_hash"]
        chain_id = data["chain_id"]
        
        if chain_id not in core.workers:
            return {"success": False, "error": f"Chain ID {html.escape(chain_id)} not supported"}, 400
            
        # Run simulation async
        result = asyncio.run(_run_simulation(tx_hash, chain_id))
        
        if result.get("success", False):
            return {"success": True, "result": result}, 200
        else:
            return {"success": False, "error": result.get("error", "Unknown error")}, 400
            
    except Exception as e:
        logger.exception(f"Error simulating transaction: {e}")
        return {"success": False, "error": str(e)}, 500

async def _run_simulation(tx_hash: str, chain_id: str) -> Dict[str, Any]:
    """Run transaction simulation with proper error handling."""
    try:
        # Get chain worker
        worker = core.workers.get(chain_id)
        if not worker:
            return {"success": False, "error": f"Chain worker for {chain_id} not found"}
            
        # Get transaction
        tx = await worker.txpool_monitor._fetch_transaction(tx_hash)
        if not tx:
            return {"success": False, "error": f"Transaction {tx_hash} not found"}
            
        # Simulate transaction
        simulation_result = await worker.transaction_core.simulate_transaction(tx)
        
        return {
            "success": simulation_result,
            "transaction": tx,
            "chain_id": chain_id,
            "error": None if simulation_result else "Simulation failed"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Main function
async def main() -> int:
    """Main entry point.
    
    Returns:
        Exit code
    """
    try:
        # Initialize configuration and core
        success = await initialize()
        if not success:
            logger.error("Initialization failed")
            return 1
        
        logger.info("Initialization successful")
        return 0
    except Exception as e:
        logger.error(f"Error in main: {e}")
        return 1

# Run the app
if __name__ == "__main__":
    # Run initialization
    loop = asyncio.get_event_loop()
    exit_code = loop.run_until_complete(main())
    
    if exit_code != 0:
        sys.exit(exit_code)
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5001)
