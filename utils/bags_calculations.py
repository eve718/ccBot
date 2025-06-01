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
    # Calculate probabilities for each bag individually
    prob_box1_dist = await calculate_exact_probabilities(box1_def, draws_box1)
    prob_box2_dist = await calculate_exact_probabilities(box2_def, draws_box2)

    total_probabilities = collections.defaultdict(float)
    for sum1, prob1 in prob_box1_dist.items():
        await asyncio.sleep(0)  # Yield control
        for sum2, prob2 in prob_box2_dist.items():
            total_probabilities[sum1 + sum2] += prob1 * prob2

    prob_at_least_target = sum(
        prob for s, prob in total_probabilities.items() if s >= target_sum
    )
    prob_exact_target = total_probabilities.get(target_sum, 0.0)

    # Get top 3 sums with highest probabilities
    # Filter out 0 probability entries for top sums
    non_zero_probabilities = {s: p for s, p in total_probabilities.items() if p > 0}

    # Sort by probability in descending order, then by sum in descending order for ties
    sorted_probabilities = sorted(
        non_zero_probabilities.items(),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )

    # Take top 3
    top_sums = dict(sorted_probabilities[:3])

    return prob_at_least_target, top_sums, prob_exact_target


async def simulate_single_bag_draws(box_def, num_draws):
    """Simulates multiple draws from a single bag definition."""
    results = []
    values = [item[0] for item in box_def]
    probabilities = [item[1] for item in box_def]
    for _ in range(num_draws):
        await asyncio.sleep(0)  # Yield control
        results.append(np.random.choice(values, p=probabilities))
    return sum(results)


async def run_monte_carlo_simulation(
    box1_def, box2_def, draws_box1, draws_box2, num_simulations
):
    """
    Runs a Monte Carlo simulation to estimate soulstone probabilities.
    Returns a list of total soulstones from each simulation.
    """
    simulation_results = []
    for i in range(num_simulations):
        await asyncio.sleep(0)  # Yield control
        # Simulate draws from Box I
        sum_box1 = await simulate_single_bag_draws(box1_def, draws_box1)
        # Simulate draws from Box II
        sum_box2 = await simulate_single_bag_draws(box2_def, draws_box2)
        simulation_results.append(sum_box1 + sum_box2)
    return simulation_results


def get_bag_stats(box_def):
    """Calculates expected value and standard deviation for a single bag definition."""
    values = np.array([item[0] for item in box_def])
    probabilities = np.array([item[1] for item in box_def])
    expected_value = np.sum(values * probabilities)
    variance = np.sum((values - expected_value) ** 2 * probabilities)
    std_dev = np.sqrt(variance)
    return expected_value, std_dev


async def run_normal_approximation(
    bot_instance, box1_def, box2_def, draws_box1, draws_box2, target_sum
):
    """
    Calculates probabilities using normal approximation.
    Requires scipy.stats.norm to be available via bot_instance.
    """
    if not bot_instance.SCIPY_AVAILABLE:
        raise ValueError("SciPy library is not available for normal approximation.")

    # Get stats for each bag
    exp_val1, std_dev1 = get_bag_stats(box1_def)
    exp_val2, std_dev2 = get_bag_stats(box2_def)

    # Total expected value and variance for combined draws
    total_expected_value = (exp_val1 * draws_box1) + (exp_val2 * draws_box2)
    total_variance = (std_dev1**2 * draws_box1) + (std_dev2**2 * draws_box2)
    total_std_dev = np.sqrt(total_variance)

    if total_std_dev == 0:
        # Handle cases where std_dev is 0 (e.g., only one possible outcome)
        if target_sum <= total_expected_value:
            prob_at_least_target = 1.0
            prob_exact_target = 1.0 if target_sum == total_expected_value else 0.0
        else:
            prob_at_least_target = 0.0
            prob_exact_target = 0.0
    else:
        # Use continuity correction for discrete distribution approximation
        z_score = (target_sum - 0.5 - total_expected_value) / total_std_dev
        prob_at_least_target = 1 - bot_instance.norm.cdf(z_score)

        # To approximate exact probability, use pdf of (target_sum - 0.5) and (target_sum + 0.5)
        # Or, more simply, P(X=k) approx P(k-0.5 < X < k+0.5) = cdf(k+0.5) - cdf(k-0.5)
        z_lower = (target_sum - 0.5 - total_expected_value) / total_std_dev
        z_upper = (target_sum + 0.5 - total_expected_value) / total_std_dev
        prob_exact_target = bot_instance.norm.cdf(z_upper) - bot_instance.norm.cdf(
            z_lower
        )

    return (
        prob_at_least_target,
        {},
        prob_exact_target,
    )  # {} for top_sums as normal approx doesn't provide them


async def async_parser(bot_instance, bag1, bag2, ss):
    """
    Parses inputs and determines which calculation method to use.
    """

    # Access bag definitions from bot_instance
    bag1_def = bot_instance.BAG_I_DEFINITION
    bag2_def = bot_instance.BAG_II_DEFINITION

    # Determine calculation method
    if (
        bag1 <= bot_instance.EXACT_CALC_THRESHOLD_BOX1
        and bag2 <= bot_instance.EXACT_CALC_THRESHOLD_BOX2
    ):
        result_data = await run_exact_calculation(bag1_def, bag2_def, bag1, bag2, ss)
        method_used = "exact"
    elif bot_instance.SCIPY_AVAILABLE:
        # For large numbers, use normal approximation if scipy is available
        result_data = await run_normal_approximation(
            bot_instance, bag1_def, bag2_def, bag1, bag2, ss
        )
        method_used = "normal_approx"
    else:
        # Fallback if scipy is not available and inputs are too large for exact
        raise ValueError(
            "Inputs too large for exact calculation and SciPy not available for approximation."
        )

    return result_data, method_used
