import argparse
import importlib
import sys
from typing import Callable, Dict, Literal

# define supported main features
MainFeature = Literal["valuation"]

# mapping from feature name to Python module path (must have a callable `main()`)
ARG_MAP: Dict[MainFeature, str] = {
    "valuation": "valuation.valuation",
}

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Main feature runner. Available features: valuation"
    )
    parser.add_argument(
        'main_feature',
        choices=ARG_MAP.keys(),
        help="Feature to run",
    )
    parser.add_argument(
        'args',
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the feature's main() function"
    )
    return parser

def run_feature(main_feature: str, feature_args: list[str]) -> None:
    if main_feature not in ARG_MAP:
        print(f"[ERROR] Unknown feature '{main_feature}'. Valid options: {', '.join(ARG_MAP.keys())}")
        return

    module_path: str = ARG_MAP[main_feature]

    try:
        module: Callable = importlib.import_module(module_path)

        if hasattr(module, 'main') and callable(module.main):
            # overwrite sys.argv for compatibility with script-style main()
            sys.argv = [module_path] + feature_args
            module.main()
        else:
            raise AttributeError(f"{module_path} does not have a callable main()")
    except Exception as e:
        print(f"[ERROR] Failed to run '{module_path}': {e}")

def main():
    parser = build_parser()
    args = parser.parse_args()
    run_feature(args.main_feature, args.args)

if __name__ == '__main__':
    main()
