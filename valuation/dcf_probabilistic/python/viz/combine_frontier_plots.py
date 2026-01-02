#!/usr/bin/env python3
"""
Combine FCFF and FCFE frontier plots side by side for README display.
Creates combined vertically stacked plots with FCFF on top, FCFE on bottom.
"""

import argparse
from pathlib import Path
from PIL import Image


def combine_frontier_plots(output_dir: Path):
    """Combine FCFF (top) and FCFE (bottom) frontier plots."""

    multi_asset_dir = output_dir / "multi_asset"
    fcfe_dir = multi_asset_dir / "fcfe"
    fcff_dir = multi_asset_dir / "fcff"

    # Plot types to combine
    plot_types = [
        "efficient_frontier_risk_return",
        "efficient_frontier_tail_risk",
        "efficient_frontier_downside",
        "efficient_frontier_cvar",
        "efficient_frontier_var",
        "efficient_frontier_drawdown",
    ]

    for plot_type in plot_types:
        fcff_file = fcff_dir / f"{plot_type}_fcff.png"
        fcfe_file = fcfe_dir / f"{plot_type}_fcfe.png"

        if not fcff_file.exists():
            print(f"Warning: {fcff_file} not found, skipping")
            continue
        if not fcfe_file.exists():
            print(f"Warning: {fcfe_file} not found, skipping")
            continue

        # Load images
        img_fcff = Image.open(fcff_file)
        img_fcfe = Image.open(fcfe_file)

        # Create combined image (vertically stacked: FCFF top, FCFE bottom)
        width = max(img_fcff.width, img_fcfe.width)
        height = img_fcff.height + img_fcfe.height

        combined = Image.new('RGB', (width, height), (255, 255, 255))
        combined.paste(img_fcff, (0, 0))
        combined.paste(img_fcfe, (0, img_fcff.height))

        # Save to multi_asset directory
        output_path = multi_asset_dir / f"{plot_type}_combined.png"
        combined.save(output_path, dpi=(300, 300))
        print(f"✓ Created: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Combine FCFF and FCFE frontier plots vertically"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("valuation/dcf_probabilistic/output"),
        help="Directory containing the plots"
    )

    args = parser.parse_args()

    output_dir = args.output_dir
    if not output_dir.exists():
        print(f"Error: Output directory {output_dir} does not exist")
        return

    combine_frontier_plots(output_dir)
    print("\nAll combined frontier plots created!")


if __name__ == "__main__":
    main()
