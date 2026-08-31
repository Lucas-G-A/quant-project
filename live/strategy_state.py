# live/strategy_state.py
import json
import os

def save_strategy_state(name: str, state: dict, state_dir="live/state"):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, f"{name}_strategy.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2)

def load_strategy_state(name: str, state_dir="live/state") -> dict:
    path = os.path.join(state_dir, f"{name}_strategy.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}