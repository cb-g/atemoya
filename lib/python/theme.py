"""
Kanagawa Theme for Matplotlib Visualizations

Provides consistent Kanagawa Dragon (dark) and Lotus (light) color palettes
across all visualization scripts in the project.

Usage:
    from lib.python.theme import setup_dark_mode, KANAGAWA_DRAGON
    setup_dark_mode()
"""

import matplotlib.pyplot as plt

# Kanagawa Dragon color palette (dark mode)
# Reference: https://github.com/rebelot/kanagawa.nvim
KANAGAWA_DRAGON = {
    'bg': '#181616',
    'fg': '#c5c9c5',
    'black': '#0d0c0c',
    'red': '#c4746e',
    'green': '#8a9a7b',
    'yellow': '#c4b28a',
    'blue': '#8ba4b0',
    'magenta': '#a292a3',
    'cyan': '#8ea4a2',
    'white': '#c5c9c5',
    'gray': '#625e5a',
    # Additional UI colors
    'bg_dark': '#0d0c0c',
    'bg_light': '#282727',
    'comment': '#625e5a',
    # Extended colors
    'orange': '#d19a66',
    'purple': '#a292a3',  # Alias for magenta
}

# Kanagawa Lotus color palette (light mode)
KANAGAWA_LOTUS = {
    'bg': '#f2ecbc',
    'fg': '#545464',
    'black': '#1f1f28',
    'red': '#c84053',
    'green': '#6f894e',
    'yellow': '#77713f',
    'blue': '#4d699b',
    'magenta': '#b35b79',
    'cyan': '#597b75',
    'white': '#545464',
    'gray': '#b8b5b9',
    # Additional UI colors
    'bg_dark': '#e7dba0',
    'bg_light': '#f5f0c8',
    'comment': '#8a8980',
}

# Extended vibrant colors (for charts needing more distinct colors)
KANAGAWA_VIBRANT = [
    '#7FCDCD',  # Vibrant cyan
    '#E8C547',  # Vibrant yellow
    '#D4779C',  # Vibrant magenta
    '#98C379',  # Vibrant green
    '#61AFEF',  # Vibrant blue
    '#E06C75',  # Vibrant red
    '#C678DD',  # Vibrant purple
    '#56B6C2',  # Vibrant teal
    '#E5C07B',  # Vibrant gold
    '#BE5046',  # Vibrant rust
    '#88C0D0',  # Vibrant ice
    '#BF616A',  # Vibrant crimson
    '#D19A66',  # Vibrant orange
    '#A3BE8C',  # Vibrant lime
    '#B48EAD',  # Vibrant violet
    '#EBCB8B',  # Vibrant amber
]


def setup_dark_mode():
    """Configure matplotlib for Kanagawa Dragon dark mode."""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'figure.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.facecolor': KANAGAWA_DRAGON['bg'],
        'axes.edgecolor': KANAGAWA_DRAGON['gray'],
        'axes.labelcolor': KANAGAWA_DRAGON['fg'],
        'text.color': KANAGAWA_DRAGON['fg'],
        'xtick.color': KANAGAWA_DRAGON['fg'],
        'ytick.color': KANAGAWA_DRAGON['fg'],
        'grid.color': KANAGAWA_DRAGON['gray'],
        'grid.alpha': 0.3,
        'legend.facecolor': KANAGAWA_DRAGON['bg'],
        'legend.edgecolor': KANAGAWA_DRAGON['gray'],
        'figure.edgecolor': KANAGAWA_DRAGON['bg'],
        'savefig.facecolor': KANAGAWA_DRAGON['bg'],
        'savefig.edgecolor': KANAGAWA_DRAGON['bg'],
    })


def setup_light_mode():
    """Configure matplotlib for Kanagawa Lotus light mode."""
    plt.style.use('default')
    plt.rcParams.update({
        'figure.facecolor': KANAGAWA_LOTUS['bg'],
        'axes.facecolor': KANAGAWA_LOTUS['bg'],
        'axes.edgecolor': KANAGAWA_LOTUS['gray'],
        'axes.labelcolor': KANAGAWA_LOTUS['fg'],
        'text.color': KANAGAWA_LOTUS['fg'],
        'xtick.color': KANAGAWA_LOTUS['fg'],
        'ytick.color': KANAGAWA_LOTUS['fg'],
        'grid.color': KANAGAWA_LOTUS['gray'],
        'grid.alpha': 0.3,
        'legend.facecolor': KANAGAWA_LOTUS['bg'],
        'legend.edgecolor': KANAGAWA_LOTUS['gray'],
        'figure.edgecolor': KANAGAWA_LOTUS['bg'],
        'savefig.facecolor': KANAGAWA_LOTUS['bg'],
        'savefig.edgecolor': KANAGAWA_LOTUS['bg'],
    })


def get_color_cycle(n_colors: int = 8, vibrant: bool = True):
    """
    Get a list of colors for plotting multiple series.

    Args:
        n_colors: Number of colors needed
        vibrant: If True, use vibrant colors; otherwise use base palette

    Returns:
        List of hex color strings
    """
    if vibrant:
        return KANAGAWA_VIBRANT[:n_colors]
    else:
        base_colors = [
            KANAGAWA_DRAGON['cyan'],
            KANAGAWA_DRAGON['yellow'],
            KANAGAWA_DRAGON['magenta'],
            KANAGAWA_DRAGON['green'],
            KANAGAWA_DRAGON['blue'],
            KANAGAWA_DRAGON['red'],
        ]
        return (base_colors * ((n_colors // len(base_colors)) + 1))[:n_colors]


def set_color_cycle(ax=None, vibrant: bool = True, n_colors: int = 8):
    """
    Set the color cycle for an axes object.

    Args:
        ax: Matplotlib axes (or None to use current axes)
        vibrant: If True, use vibrant colors
        n_colors: Number of colors in cycle
    """
    colors = get_color_cycle(n_colors, vibrant)
    if ax is None:
        plt.rcParams['axes.prop_cycle'] = plt.cycler(color=colors)
    else:
        ax.set_prop_cycle(color=colors)


def save_figure(fig, output_path, dpi=150, **kwargs):
    """
    Save a matplotlib figure in both PNG and SVG formats.

    SVG is preferred for web display (README) as it scales perfectly when zooming.
    PNG is kept for compatibility.

    Args:
        fig: Matplotlib figure object
        output_path: Path to save (with .png extension - .svg will be generated)
        dpi: DPI for PNG output (default 150)
        **kwargs: Additional arguments passed to savefig
    """
    from pathlib import Path

    output_path = Path(output_path)

    # Ensure output_path ends with .png
    if output_path.suffix != '.png':
        output_path = output_path.with_suffix('.png')

    # Default kwargs
    save_kwargs = {
        'dpi': dpi,
        'bbox_inches': 'tight',
        'facecolor': fig.get_facecolor(),
        'edgecolor': 'none',
    }
    save_kwargs.update(kwargs)

    # Save PNG
    fig.savefig(output_path, **save_kwargs)

    # Save SVG (remove dpi as it's not applicable)
    svg_path = output_path.with_suffix('.svg')
    svg_kwargs = {k: v for k, v in save_kwargs.items() if k != 'dpi'}
    svg_kwargs['format'] = 'svg'
    fig.savefig(svg_path, **svg_kwargs)

    print(f"Saved: {output_path} and {svg_path}")


# Convenience aliases
COLORS = KANAGAWA_DRAGON  # Default to dark mode
