"""
Convex LP solver for portfolio optimization.
Implements the full specification with all slack variables.
"""

import json
import sys
import numpy as np

try:
    import cvxpy as cp
except ImportError:
    print("Error: cvxpy not installed. Install with: uv pip install cvxpy", file=sys.stderr)
    sys.exit(1)


def solve_portfolio_lp(problem_file, solution_file):
    """
    Solve portfolio optimization LP per specification.

    Implements:
    - LPM1 with slack variables
    - CVaR with slack variables
    - Turnover L1 with slack variables
    - Stress beta L1 penalty with slack variables
    - All constraints from specification
    """

    # Load problem
    with open(problem_file, 'r') as f:
        prob = json.load(f)

    N = prob['n_assets']
    T = prob['n_scenarios']

    # Convert to numpy arrays
    R = np.array(prob['asset_scenarios'])  # T x N
    b = np.array(prob['benchmark_scenarios'])  # T
    r_c = np.array(prob['cash_scenarios'])  # T
    w_prev = np.array(prob['prev_weights'])  # N
    w_c_prev = prob['prev_cash']
    betas = np.array(prob['asset_betas'])  # N
    s = prob['stress_weight']

    # Hyperparameters
    lambda_lpm1 = prob['lambda_lpm1']
    lambda_cvar = prob['lambda_cvar']
    lambda_beta = prob['lambda_beta']
    kappa = prob['kappa']  # c + gamma
    tau = prob['lpm_threshold']
    alpha = prob['cvar_alpha']
    beta_target = prob['beta_target']

    # === DECISION VARIABLES ===

    # Primary variables
    w = cp.Variable(N, nonneg=True)  # Asset weights
    w_c = cp.Variable(nonneg=True)   # Cash weight

    # LPM slack variables
    s_lpm = cp.Variable(T, nonneg=True)

    # CVaR slack variables
    eta = cp.Variable()
    u = cp.Variable(T, nonneg=True)

    # Turnover slack variables (L1 norm)
    z = cp.Variable(N, nonneg=True)

    # Beta penalty slack (L1 norm for LP)
    v = cp.Variable(nonneg=True)

    # === SCENARIO EXPRESSIONS (linear) ===

    # Portfolio scenario returns: p_t = sum_i w_i R_ti + w_c r^c_t
    # Using matrix multiplication: p = R @ w + r_c * w_c
    p = R @ w + r_c * w_c  # T vector

    # Active scenario returns: a_t = p_t - b_t
    a = p - b  # T vector

    # === CONSTRAINTS ===

    constraints = []

    # (1) Full investment
    constraints.append(cp.sum(w) + w_c == 1.0)

    # (2) LPM1 slack constraints
    # s_lpm_t >= tau - a_t
    # s_lpm_t >= 0 (already enforced by nonneg=True)
    constraints.append(s_lpm >= tau - a)

    # (3) CVaR slack constraints
    # u_t >= -a_t - eta
    # u_t >= 0 (already enforced)
    constraints.append(u >= -a - eta)

    # (4) Turnover slack constraints
    # z_i >= w_i - w_prev_i
    # z_i >= -(w_i - w_prev_i)
    # z_i >= 0 (already enforced)
    delta_w = w - w_prev
    constraints.append(z >= delta_w)
    constraints.append(z >= -delta_w)

    # (5) Beta penalty slack (LP version, Option A)
    # Portfolio beta: beta(w) = sum_i w_i * beta_i
    portfolio_beta = betas @ w

    # v >= beta(w) - beta_target
    # v >= -(beta(w) - beta_target)
    # v >= 0 (already enforced)
    beta_dev = portfolio_beta - beta_target
    constraints.append(v >= beta_dev)
    constraints.append(v >= -beta_dev)

    # === OBJECTIVE ===

    # LPM1 term
    lpm1_term = (lambda_lpm1 / T) * cp.sum(s_lpm)

    # CVaR term
    cvar_term = lambda_cvar * (eta + (1.0 / ((1 - alpha) * T)) * cp.sum(u))

    # Turnover + cost term
    turnover_term = kappa * cp.sum(z)

    # Stress beta penalty (L1, LP version)
    beta_penalty_term = lambda_beta * s * v

    # Total objective
    objective = cp.Minimize(
        lpm1_term + cvar_term + turnover_term + beta_penalty_term
    )

    # === SOLVE ===

    problem = cp.Problem(objective, constraints)

    try:
        # Try solvers in order of preference: CLARABEL > SCS > OSQP
        try:
            problem.solve(solver=cp.CLARABEL, verbose=False)
        except:
            try:
                problem.solve(solver=cp.SCS, verbose=False)
            except:
                problem.solve(solver=cp.OSQP, verbose=False)

        if problem.status not in ["optimal", "optimal_inaccurate"]:
            print(f"Solver status: {problem.status}", file=sys.stderr)
            # Fall back to previous weights
            solution = {
                "asset_weights": w_prev.tolist(),
                "cash_weight": w_c_prev,
                "objective_value": float('inf'),
                "lpm1_value": 0.0,
                "cvar_value": 0.0,
                "turnover": 0.0,
                "beta_penalty": 0.0,
                "solver_status": problem.status
            }
        else:
            # Extract solution
            w_opt = w.value
            w_c_opt = w_c.value

            # Calculate components
            lpm1_val = (1.0 / T) * np.sum(s_lpm.value)
            cvar_val = eta.value + (1.0 / ((1 - alpha) * T)) * np.sum(u.value)
            turnover_val = np.sum(z.value)
            beta_pen_val = s * v.value

            solution = {
                "asset_weights": w_opt.tolist(),
                "cash_weight": float(w_c_opt),
                "objective_value": problem.value,
                "lpm1_value": lpm1_val,
                "cvar_value": cvar_val,
                "turnover": turnover_val,
                "beta_penalty": beta_pen_val,
                "solver_status": problem.status
            }

    except Exception as e:
        print(f"Solver error: {e}", file=sys.stderr)
        # Fall back to previous weights
        solution = {
            "asset_weights": w_prev.tolist(),
            "cash_weight": w_c_prev,
            "objective_value": float('inf'),
            "lpm1_value": 0.0,
            "cvar_value": 0.0,
            "turnover": 0.0,
            "beta_penalty": 0.0,
            "solver_status": "error"
        }

    # Save solution
    with open(solution_file, 'w') as f:
        json.dump(solution, f, indent=2)

    return solution


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: solve_lp.py <problem_file.json> <solution_file.json>")
        sys.exit(1)

    problem_file = sys.argv[1]
    solution_file = sys.argv[2]

    solve_portfolio_lp(problem_file, solution_file)
