import discord
from discord.ext import commands
import logging
import json
import hmac
import hashlib
from datetime import datetime, timezone

from config import (
    MASTER_SECRET, LICENSE_REQUEST_CHANNEL,
    EMOJIS, COLORS, FOOTER_TEXT
)
import database as db

logger = logging.getLogger(__name__)

class GiveawayHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.request_channel = None

    @commands.Cog.listener()
    async def on_ready(self):
        # Find the license request channel in the first guild (or all)
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.channels, name=LICENSE_REQUEST_CHANNEL)
            if channel:
                self.request_channel = channel
                break
        if self.request_channel:
            logger.info(f"✅ License request channel set to #{self.request_channel.name}")
        else:
            logger.warning(f"⚠️ License request channel #{LICENSE_REQUEST_CHANNEL} not found")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore self and non‑channel messages
        if message.author.id == self.bot.user.id:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.channel.name != LICENSE_REQUEST_CHANNEL:
            return

        # Check if it's a license request
        if not message.content.startswith("LICENSE_REQUEST"):
            return

        # Parse request
        parts = message.content.split(maxsplit=2)
        if len(parts) < 3:
            return
        _, signature, json_str = parts

        # Verify signature
        expected = hmac.new(
            MASTER_SECRET.encode(),
            json_str.encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            logger.warning("Invalid signature on license request")
            return

        # Parse JSON payload
        try:
            data = json.loads(json_str)
            request_id = data.get("request_id")
            giveaway_id = data.get("giveaway_id")
            winners = data.get("winners")   # list of user IDs
            count = data.get("count")        # number of licenses
        except Exception as e:
            logger.error(f"Failed to parse license request JSON: {e}")
            return

        # Generate licenses
        try:
            product_name = f"Giveaway {giveaway_id}"
            codes = db.generate_multiple_user_licenses(count, product_name, giveaway_id)

            # Assign each license to the corresponding winner (if winners list matches count)
            # winners list should be in same order as generated codes
            response_codes = []
            for i, user_id in enumerate(winners[:count]):  # ensure we don't exceed
                license_code = codes[i]
                db.assign_license_to_user(license_code, user_id)
                response_codes.append({"user_id": user_id, "license_code": license_code})

            # Prepare response
            response_data = {
                "request_id": request_id,
                "codes": response_codes
            }
            response_json = json.dumps(response_data)

            # Sign response
            response_signature = hmac.new(
                MASTER_SECRET.encode(),
                response_json.encode(),
                hashlib.sha256
            ).hexdigest()

            # Send response
            await message.channel.send(
                f"LICENSE_RESPONSE {response_signature} {response_json}"
            )
            logger.info(f"✅ Responded to license request {request_id} with {count} codes")

        except Exception as e:
            logger.error(f"Failed to generate licenses: {e}")
            # Optionally send error response? We'll keep silent.

async def setup(bot):
    await bot.add_cog(GiveawayHandler(bot))