import structlog
import logging
import sys
import contextvars

# Context variables to hold trace/user/job context
log_context = contextvars.ContextVar("log_context", default={})

def bind_log_context(**kwargs):
    ctx = log_context.get().copy()
    ctx.update(kwargs)
    log_context.set(ctx)

def clear_log_context():
    log_context.set({})

def context_var_processor(logger, method_name, event_dict):
    ctx = log_context.get()
    if ctx:
        event_dict.update(ctx)
    return event_dict

def configure_logging():
    # Set up standard library logging to print to stdout
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            context_var_processor,  # Inject correlation IDs dynamically
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
