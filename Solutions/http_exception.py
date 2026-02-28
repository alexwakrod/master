"""
Generic HTTP error handler.
pattern: HTTPException
"""

async def apply(bot, error_details, bot_path=None):
    """
    Logs and retries.
    """
    return True, "Retried after HTTP error (simulated)."
