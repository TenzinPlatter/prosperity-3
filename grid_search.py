import subprocess

ALPHA_START = 0
ALPHA_END = 1

ADJUST_START = 0
ADJUST_END = 1

BASESPREAD_START = 0
BASESPREAD_END = 5

MAXORDER_START = 0
MAXORDER_END = 15

vars = [0, 0, 0, 0, 0, 0]

max_profit = -1

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

                        contents = ""
                        with open("trader_resin_draft.py", "r") as f:
                            in_constants = False
                            added_constants = False
                            for line in f:
                                if in_constants:
                                    if not added_constants:
                                        constants = f"ALPHA_EARLY = {alpha_e}\n"
                                        constants += f"ALPHA_LATE = {alpha_l}\n"
                                        constants += f"BASESPREAD = {base}\n"
                                        constants += f"ADJUST_SCALE = {adjust}\n"
                                        constants += (
                                            f"MAX_ORDER_EARLY = {max_order_e}\n"
                                        )
                                        constants += f"MAX_ORDER_LATE = {max_order_l}\n"
                                        added_constants = True
                                        contents += constants

                                else:
                                    contents += line

                                if line.startswith("# start"):
                                    in_constants = True

                                if line.startswith("# end"):
                                    in_constants = False
                                    contents += line

                        with open("trader_resin_draft.py", "w") as f:
                            f.write(contents)

                        out = subprocess.run(
                            ["prosperity3bt", "trader_resin_draft.py", "0"],
                            stdout=subprocess.PIPE,
                            text=True,
                        ).stdout

                        result = -1
                        for line in out.split("\n"):
                            if line.startswith("Total profit"):
                                result = line.split()[-1].replace(",", "")
                                break

                        result = float(result)
                        if result > max_profit:
                            max_profit = result
                            vars[0] = alpha_e
                            vars[1] = alpha_l
                            vars[2] = adjust
                            vars[3] = base
                            vars[4] = max_order_e
                            vars[5] = max_order_l


with open(".results", "w") as f:
    f.write("Results:\n")
    f.write(f"max profit: {max_profit}\n")
    f.write(f"alpha early: {vars[0]}\n")
    f.write(f"alpha late: {vars[1]}\n")
    f.write(f"adjust: {vars[2]}\n")
    f.write(f"base: {vars[3]}\n")
    f.write(f"max_order early: {vars[4]}\n")
    f.write(f"max_order late: {vars[5]}\n")
