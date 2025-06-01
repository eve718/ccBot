# config.py

import os
import collections

# --- Bot Configuration ---
CALCULATION_TIMEOUT = 15  # Timeout for bag calculations in seconds
EXACT_CALC_THRESHOLD_BOX1 = 100  # Max draws for Bag I to attempt exact calculation
EXACT_CALC_THRESHOLD_BOX2 = 100  # Max draws for Bag II to attempt exact calculation
PROB_DIFFERENCE_THRESHOLD = 0.001  # Threshold for reporting top sums as too close

# Define Bag I and Bag II contents as lists of (soulstone_value, probability) tuples
# Ensure probabilities sum to 1.0 for each bag
BAG_I_DEFINITION = [
    (1, 0.45),
    (2, 0.30),
    (3, 0.15),
    (4, 0.07),
    (5, 0.03),
]

BAG_II_DEFINITION = [
    (5, 0.40),
    (10, 0.30),
    (15, 0.20),
    (20, 0.08),
    (25, 0.02),
]

# --- Command Menu Configuration (from general.py) ---
COMMAND_MENU = {
    "bags": {
        "description": "Calculates soulstone probabilities from bag draws.",
        "usage_prefix": "`!bags <bag I count> <bag II count> <target soulstones>`",
        "usage_slash": "`/bags bag1:<count> bag2:<count> ss:<target>`",
        "emoji": "💎",
        "has_args": True,
    },
    "baginfo": {
        "description": "Displays information about Bag I and Bag II contents and their average values.",
        "usage_prefix": "`!baginfo`",
        "usage_slash": "`/baginfo`",
        "emoji": "🛍️",
        "has_args": False,
    },
    "ping": {
        "description": "Checks the bot's latency.",
        "usage_prefix": "`!ping`",
        "usage_slash": "`/ping`",
        "emoji": "🏓",
        "has_args": False,
    },
    "info": {
        "description": "Displays general information about the bot.",
        "usage_prefix": "`!info`",
        "usage_slash": "`/info`",
        "emoji": "ℹ️",
        "has_args": False,
    },
    "menu": {
        "description": "Displays this interactive list of available commands.",
        "usage_prefix": "`!menu`",
        "usage_slash": "`/menu`",
        "emoji": "📜",
        "has_args": False,
    },
    "owner": {
        "description": "Owner-only commands for bot management.",
        "usage_prefix": "`!help owner` for details.",
        "usage_slash": "Owner-only commands. No direct slash menu.",
        "emoji": "👑",
        "has_args": False,
    },
}
