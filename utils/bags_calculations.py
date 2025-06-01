# utils/bags_calculations.py

import asyncio
import collections
import math
import numpy as np

# Conditional import for scipy (SCIPY_AVAILABLE will be passed from bot instance)
# No direct import here; rely on bot.SCIPY_AVAILABLE and bot.norm


async def calculate_exact_probabilities(box_def, num_draws):
    """
    Calculates the exact probability distribution of soulstones from a bag
    after a given number of draws.
    Uses asyncio.sleep(0) to yield control for responsiveness.
    """
    current_probabilities = {0: 1.0}  # Initial state: 0 soulstones, 100% probability
    for _ in range(num_draws):
        await asyncio.sleep(0)  # Yield control to the event loop
        next_probabilities = collections.defaultdict(float)
        for prev_sum, prev_prob in current_probabilities.items():
            for value, prob_of_value in box_def:
                new_sum = prev_sum + value
                new_prob = prev_prob * prob_of_value
                next_probabilities[new_sum] += new_prob
        current_probabilities = next_probabilities
    return current_probabilities


async def run_exact_calculation(box1_def, box2_def, draws_box1, draws_box2, target_sum):
    """
    Combines exact probabilities from two bags and calculates the probability
    of reaching a target sum.
    """
    # Calculate exact probabilities for each box
    prob_box1 = await calculate_exact_probabilities(box1_def, draws_box1)
    prob_box2 = await calculate_exact_probabilities(box2_def, draws_box2)

    # Combine distributions
    combined_probabilities = collections.defaultdict(float)
    for sum1, prob1 in prob_box1.items():
        for sum2, prob2 in prob_box2.items():
            combined_probabilities[sum1 + sum2] += prob1 * prob2

    # Calculate probability of reaching at least the target sum
    prob_at_least_target = sum(
        prob for s, prob in combined_probabilities.items() if s >= target_sum
    )

    prob_exact_target = combined_probabilities.get(target_sum, 0.0)

    # Find top sums
    # Filter out sums that have very low probability before finding top sums
    significant_probabilities = {
        s: p for s, p in combined_probabilities.items() if p > 1e-9
    }  # Threshold for significance

    top_sums = sorted(
        significant_probabilities.items(), key=lambda item: item[1], reverse=True
    )[
        :5
    ]  # Get top 5

    return prob_at_least_target, top_sums, prob_exact_target


async def run_normal_approximation(
    bot_instance, bag1_def, bag2_def, draws_box1, draws_box2, target_sum
):
    """
    Calculates probabilities using normal approximation for large number of draws.
    Requires SciPy for norm.cdf.
    """
    # Get stats for individual bags
    bag1_stats = await get_bag_stats(bag1_def)
    bag2_stats = await get_bag_stats(bag2_def)

    # Calculate combined expected value and standard deviation
    total_expected_value = (
        bag1_stats["expected_value"] * draws_box1
        + bag2_stats["expected_value"] * draws_box2
    )
    total_variance = (bag1_stats["std_dev"] ** 2) * draws_box1 + (
        bag2_stats["std_dev"] ** 2
    ) * draws_box2
    total_std_dev = math.sqrt(total_variance)

    prob_at_least_target = 0.0
    prob_exact_target = 0.0

    if bot_instance.SCIPY_AVAILABLE:
        # Continuity correction: P(X >= x) becomes P(Z >= (x - 0.5 - mu) / sigma)
        # Using 0.5 for continuity correction
        z = (target_sum - 0.5 - total_expected_value) / total_std_dev
        prob_at_least_target = 1 - bot_instance.norm.cdf(z)

        # For exact target, P(X = x) becomes P( (x - 0.5 - mu) / sigma <= Z <= (x + 0.5 - mu) / sigma )
        z_lower = (target_sum - 0.5 - total_expected_value) / total_std_dev
        z_upper = (target_sum + 0.5 - total_expected_value) / total_std_dev
        prob_exact_target = bot_instance.norm.cdf(z_upper) - bot_instance.norm.cdf(
            z_lower
        )

    return (
        prob_at_least_target,
        {},  # Returning an empty dictionary for top_sums as normal approximation doesn't provide them
        prob_exact_target,
    )


async def get_bag_stats(bag_def):
    """
    Calculates expected value and standard deviation for a given bag definition.
    Returns as a dictionary for easier access by name.
    """
    total_value = sum(value * prob for value, prob in bag_def)
    variance_sum = sum(prob * (value - total_value) ** 2 for value, prob in bag_def)
    std_dev = math.sqrt(variance_sum)
    return {"expected_value": total_value, "std_dev": std_dev}


async def async_parser(bot_instance, bag1, bag2, ss):
    """
    Parses inputs and determines which calculation method to use.
    Returns the calculation results and the method used.
    """
    bag1_def = bot_instance.BAG_I_DEFINITION
    bag2_def = bot_instance.BAG_II_DEFINITION

    if (
        bag1 <= bot_instance.EXACT_CALC_THRESHOLD_BOX1
        and bag2 <= bot_instance.EXACT_CALC_THRESHOLD_BOX2
    ):
        prob_at_least_target, top_sums, prob_exact_target = await run_exact_calculation(
            bag1_def, bag2_def, bag1, bag2, ss
        )
        method_used = "exact"
    elif bot_instance.SCIPY_AVAILABLE:
        prob_at_least_target, top_sums, prob_exact_target = (
            await run_normal_approximation(
                bot_instance, bag1_def, bag2_def, bag1, bag2, ss
            )
        )
        method_used = "normal_approximation"
    else:
        # Fallback if thresholds are exceeded and SciPy is not available
        prob_at_least_target = 0.0
        top_sums = []  # Empty list as no top sums can be calculated
        prob_exact_target = 0.0
        method_used = "unsupported"
        # Consider adding a logger warning or user feedback here for unsupported calculations

    return prob_at_least_target, top_sums, prob_exact_target, method_used
