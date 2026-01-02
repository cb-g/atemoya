# Project Orientation

## Project Overview
This project holds multiple quantitative finance models organized into two main paradigms:
1. **Pricing Paradigm** - for short-term investing strategies
2. **Valuation Paradigm** - for long-term investing strategies

In the README.md table of contents, pricing comes first, followed by valuation.

## Technology Stack

### OCaml
- Used for actual computations, optimizations, and algorithms
- Must use **functional programming** paradigm only - **NO OOP**
- Leverage OCaml's functional programming capabilities

### Python
- Used **only** for:
  - Data fetching (yfinance or other freely available sources)
  - Visualizations
- Can use OOP if it fits the needs

## Architecture Principles

### Model Separation
- Each model should be clearly separated
- Easy to add new models without interfering with existing ones
- Easy to edit models independently

### Code Reusability
- Allowed to establish a directory for modular, reusable computations and algorithms
- **Trade-off consideration**: The more models there are, the more complicated it becomes to edit general-purpose functions if they're too specific
- **Strategy**: Be conservative about outsourcing to general-purpose functions
  - Keep things separated initially
  - Outsource to general-purpose directories later when commonalities between models become clear
  - Choose smartly with a look-ahead mentality

### Evolution Strategy
- Start with separated implementations
- Identify common patterns after implementing multiple models
- Refactor to general-purpose modules when patterns are clear and stable

## Development Philosophy
- Functional programming in OCaml
- Clear separation of concerns
- Incremental refactoring based on observed patterns
- Avoid premature optimization/abstraction
