"""Implied volatility computation via Black-Scholes inversion.

Vectorized Newton-Raphson solver for computing implied volatility from
option prices. Used by replay scripts and collectors that need IV from
raw bid/ask data (e.g., ThetaData which provides no pre-computed IV).
"""

import numpy as np
from scipy.stats import norm


def implied_vol_newton_raphson(
    prices: np.ndarray,
    spots: np.ndarray,
    strikes: np.ndarray,
    expiries: np.ndarray,
    rates: np.ndarray,
    option_types: np.ndarray,
    tol: float = 1e-5,
    max_iter: int = 50,
) -> np.ndarray:
    """Vectorized implied volatility using Newton-Raphson.

    Args:
        prices: Array of option mid prices
        spots: Array of underlying spot prices
        strikes: Array of strike prices
        expiries: Array of times to expiry (in years)
        rates: Array of risk-free rates
        option_types: Array of 'call' or 'put' strings
        tol: Convergence tolerance
        max_iter: Maximum iterations

    Returns:
        Array of implied volatilities (NaN where solver failed)
    """
    n = len(prices)
    sigma = np.full(n, 0.3)
    is_call = option_types == "call"
    valid = expiries > 0

    for _ in range(max_iter):
        d1 = np.where(
            valid,
            (np.log(spots / strikes) + (rates + 0.5 * sigma**2) * expiries)
            / (sigma * np.sqrt(expiries)),
            0,
        )
        d2 = d1 - sigma * np.sqrt(expiries)

        call_price = spots * norm.cdf(d1) - strikes * np.exp(-rates * expiries) * norm.cdf(d2)
        put_price = strikes * np.exp(-rates * expiries) * norm.cdf(-d2) - spots * norm.cdf(-d1)

        bs_price = np.where(is_call, call_price, put_price)
        vega = spots * np.sqrt(expiries) * norm.pdf(d1)

        price_diff = bs_price - prices
        converged = np.abs(price_diff) < tol

        update_mask = valid & ~converged & (vega > 1e-10)
        sigma = np.where(update_mask, sigma - price_diff / vega, sigma)
        sigma = np.clip(sigma, 0.01, 5.0)

        if np.all(converged | ~valid):
            break

    sigma = np.where(valid & (sigma > 0.01) & (sigma < 5.0), sigma, np.nan)
    return sigma
