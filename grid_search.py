import threading
import subprocess
from tqdm import tqdm
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from time import time

ALPHA_START = 0
ALPHA_END = 1

ADJUST_START = 0
ADJUST_END = 1

BASESPREAD_START = 0
BASESPREAD_END = 5

MAXORDER_START = 0
MAXORDER_END = 15

TARGET_FILE = "trader_resin_draft.py"
MAX_STATE_FILE = "best.json"
LOCK = threading.Lock()
NUM_THREADS = 4  # Tune this to match your CPU/IO capacity

# === INIT ===
if not os.path.exists(MAX_STATE_FILE):
    with open(MAX_STATE_FILE, "w") as f:
        json.dump({"max_profit": float("-inf"), "constants": ""}, f)


def load_state():
    with open(MAX_STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with LOCK:
        with open(MAX_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)


def replace_constants(constants_string):
    with LOCK:
        with open(TARGET_FILE, "r") as f:
            lines = f.readlines()

        start = end = None
        for i, line in enumerate(lines):
            if "# start" in line:
                start = i
            elif "# end" in line:
                end = i

        if start is None or end is None or start >= end:
            raise RuntimeError("Could not find valid '# start' and '# end' markers.")

        new_lines = lines[: start + 1] + [constants_string + "\n"] + lines[end:]
        with open(TARGET_FILE, "w") as f:
            f.writelines(new_lines)


def run_and_get_profit(constants_string):
    replace_constants(constants_string)

    try:
        result = subprocess.run(
            ["prosperity3bt", TARGET_FILE, "0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("Total profit"):
            try:
                return float(line.replace(",", "").strip().split()[-1])
            except ValueError:
                return None
    return None


def worker(constants_string):
    profit = run_and_get_profit(constants_string)
    if profit is None:
        return

    with LOCK:
        state = load_state()
        if profit > state["max_profit"]:
            print(f"[NEW MAX] {profit} with: {constants_string}")
            save_state({"max_profit": profit, "constants": constants_string})


def main(constants_list, testing=False):
    if not testing:
        with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
            list(tqdm(executor.map(worker, constants_list), total=len(constants_list)))
        return

    for threads in [1, 2, 4, 8, 16]:
        start = time()
        with ThreadPoolExecutor(max_workers=threads) as executor:
            list(executor.map(worker, constants_list[:20]))  # small test set
        print(f"{threads} threads: {time() - start:.2f}s")


if __name__ == "__main__":
    # Example constants list to test
    constants_strings = []

    print("Creating constant strings")
    for alpha_e_ in range(0, 100):
        for alpha_l_ in range(0, 100):
            for adjust_ in range(0, 100):
                for base_ in range(0, 100):
                    for max_order_e_ in range(0, 100):
                        for max_order_l_ in range(0, 100):
                            alpha_e = alpha_e_ * ALPHA_END / 100
                            alpha_l = alpha_l_ * ALPHA_END / 100
                            adjust = adjust_ * ADJUST_END / 100
                            base = base_ * BASESPREAD_END / 100
                            max_order_e = max_order_e_ * MAXORDER_END / 100
                            max_order_l = max_order_l_ * MAXORDER_END / 100
                            constants = f"ALPHA_EARLY = {alpha_e}\n"
                            constants += f"ALPHA_LATE = {alpha_l}\n"
                            constants += f"BASESPREAD = {base}\n"
                            constants += f"ADJUST_SCALE = {adjust}\n"
                            constants += f"MAX_ORDER_EARLY = {max_order_e}\n"
                            constants += f"MAX_ORDER_LATE = {max_order_l}\n"
                            constants_strings.append(constants)

    print("Starting testing")

    main(constants_strings, True)
