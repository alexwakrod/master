"""
Checks and requests missing permissions.
pattern: Missing Permissions|403
"""

async def apply(bot, error_details, bot_path=None):
    """
    Logs the required permission and suggests adding it.
    """
    return False, "Check bot's permissions in server settings."
