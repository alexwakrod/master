"""
Installs missing Python modules, handles venv, and restarts.
pattern: ModuleNotFoundError: No module named '([^']+)'
"""

import subprocess
import sys
import os
import asyncio

async def apply(bot, error_details, bot_path=None):
    """
    Attempts to install the missing module using pip. If bot_path is provided, tries within its venv.
    """
    import re
    match = re.search(r"No module named '([^']+)'", error_details)
    if not match:
        return False, "Could not extract module name"
    module = match.group(1)
    
    # Determine Python executable (prefer venv if bot_path given)
    python_exe = sys.executable
    if bot_path:
        venv_python = os.path.join(bot_path, "venv", "bin", "python")
        if os.path.exists(venv_python):
            python_exe = venv_python
    
    try:
        # Install module
        subprocess.check_call([python_exe, "-m", "pip", "install", module])
        return True, f"Installed module {module}"
    except subprocess.CalledProcessError as e:
        return False, f"Installation failed: {e}"
