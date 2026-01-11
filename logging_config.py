"""
logging_config.py - Structured JSON Logging for Juridico AI
Provides production-ready logging configuration.
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """Formats log records as JSON for production environments."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        
        # Common fields
        if hasattr(record, "job_id"):
            log_entry["job_id"] = record.job_id
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if hasattr(record, "latency_ms"):
            log_entry["latency_ms"] = record.latency_ms
            
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    json_format: bool = True,
    loggers: list = None
):
    """
    Configure logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, use JSON format (for production). If False, use human-readable.
        loggers: List of logger names to configure. If None, configures root.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]
    
    # Configure specific loggers if provided
    if loggers:
        for name in loggers:
            logger = logging.getLogger(name)
            logger.setLevel(log_level)
            logger.handlers = [handler]
            logger.propagate = False
    
    logging.info("Logging configured", extra={"json_format": json_format, "level": level})


# Helper function for structured logging with extra context
def log_with_context(logger: logging.Logger, level: str, message: str, **context):
    """
    Log a message with additional structured context.
    
    Usage:
        log_with_context(logger, "info", "Job started", job_id="123", user="abc")
    """
    log_func = getattr(logger, level.lower(), logger.info)
    
    # Create a LogRecord with extra attributes
    extra = {"extra": context}
    log_func(message, extra=extra)


# Convenience: Pre-configured loggers
def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
