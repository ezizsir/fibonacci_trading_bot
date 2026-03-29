import pathlib
import pandas as pd
import json
from pprint import pprint

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FIB_RATIOS = [0, 0.236, 0.382, 0.5, 0.618, 0.65, 0.786, 0.886, 1.0]

DEFAULT_CSV = pathlib.Path(__file__).parent / "atl_ath_stats.csv"

# One color per fib ratio (applied the same way across every grid).
# ... (rest of FIB_COLORS)
FIB_COLORS = [
    "#888888",  # 0.000  – gray
    "#FF3030",  # 0.236  – red
    "#FF8C00",  # 0.382  – orange
    "#FF8C00",  # 0.500  – orange
    "#FFD700",  # 0.618  – yellow
    "#FFD700",  # 0.650  – yellow
    "#00FFFF",  # 0.786  – cyan
    "#FFFFFF",  # 0.886  – white
    "#FFFFFF",  # 1.000  – white
]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_fib_levels(atl: float, top: float) -> dict[float, float]:
    """
    Compute fib price levels for a single grid.

    The grid spans from atl (ratio=0) to top (ratio=1).
    Each ratio maps to:  price = atl + ratio * (top - atl)
    """
    span = top - atl
    return {ratio: atl + ratio * span for ratio in FIB_RATIOS}


def compute_fib_grids(row) -> list[dict]:
    """
    Given one row from atl_ath_stats.csv (dict or pd.Series), return a list
    of Fibonacci grid dicts, expanding upward until the grid top is at least
    40 % above the all-time high.

    Grid construction rules
    -----------------------
    - atl_price  → always the 0-level (anchor, never moves)
    - Grid 1 top → ath_until_atl_price
    - Grid N top → derived so that its 0.236 level equals Grid N-1's 1.0 level
                   i.e.  new_top = atl + (prev_top - atl) / 0.236
    - Stop when the newly computed top >= ath_price * 1.40
    """
    atl        = float(row["atl_price"])
    first_top  = float(row["ath_until_atl_price"])
    ath        = float(row["ath_price"])
    stop_level = ath * 1.40          # grid top must reach this to stop

    grids: list[dict] = []
    current_top = first_top
    grid_num   = 1

    while True:
        levels = compute_fib_levels(atl, current_top)
        grids.append({
            "grid":   grid_num,
            "top":    current_top,
            "levels": levels,
        })

        # Stop once this grid's top has cleared the 40%-above-ATH threshold
        if current_top >= stop_level:
            break

        # Next grid: its 0.236 price == this grid's 1.0 price
        # atl + 0.236 * (new_top - atl) = current_top
        # => new_top = atl + (current_top - atl) / 0.236
        current_top = atl + (current_top - atl) / 0.236
        grid_num   += 1

    return grids


def load_and_compute(csv_path=DEFAULT_CSV) -> dict[str, list[dict]]:
    """
    Read atl_ath_stats.csv and return a dict keyed by ticker, where each
    value is the list of expanding fib grid dicts for that ticker.
    """
    df = pd.read_csv(csv_path)
    result: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        ticker = row["ticker"]
        result[ticker] = compute_fib_grids(row)
    return result


# ---------------------------------------------------------------------------
# Pine Script generation
# ---------------------------------------------------------------------------

def _fmt_price(price: float) -> str:
    """Format a price value for Pine Script, keeping enough precision."""
    if price < 0.01:
        return f"{price:.10f}"
    elif price < 1:
        return f"{price:.8f}"
    elif price < 1000:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"


def _hex_to_rgb(hex_color: str) -> str:
    """Convert '#RRGGBB' to 'r, g, b' string for use in Pine Script color.rgb()."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r}, {g}, {b}"


def generate_pinescript(ticker: str, grids: list[dict]) -> str:
    """
    Generate a Pine Script v5 indicator that draws horizontal lines at every
    Fibonacci level across all grids for *ticker*.

    Uses line.new(extend=extend.both) inside `if barstate.islast` so lines
    are drawn as pure visual overlays and do NOT affect the y-axis scale.
    This means the chart auto-fits to candles, exactly like a normal fib tool.
    """
    total_lines = sum(len(g["levels"]) for g in grids)
    lines: list[str] = []

    lines.append(f'// Fibonacci levels for {ticker}')
    lines.append(f'// Grids: {len(grids)}  |  Total lines: {total_lines}')
    lines.append(f'//@version=5')
    lines.append(
        f'indicator("{ticker} Fib Levels", overlay=true, '
        f'max_lines_count=500, max_labels_count=500)'
    )
    lines.append('')
    lines.append('if barstate.islast')

    for g in grids:
        grid_num = g["grid"]
        lines.append(f'    // Grid {grid_num}  (top = {_fmt_price(g["top"])})')

        for idx, (ratio, price) in enumerate(g["levels"].items()):
            color  = FIB_COLORS[idx % len(FIB_COLORS)]
            lbl    = f"G{grid_num} {ratio:.3f}"
            p      = _fmt_price(price)
            # line.new with extend=extend.both draws across the whole chart
            # without pushing the y-axis to include those price levels.
            lines.append(
                f'    line.new(bar_index, {p}, bar_index + 1, {p}, '
                f'extend=extend.both, '
                f'color=color.new(color.rgb({_hex_to_rgb(color)}), 20), '
                f'width=2)'
            )
            lines.append(
                f'    label.new(bar_index + 2, {p}, "{lbl}", '
                f'color=color.new(color.black, 100), '
                f'textcolor=color.new(color.rgb({_hex_to_rgb(color)}), 0), '
                f'style=label.style_label_left, size=size.small)'
            )
        lines.append('')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Standalone runner – pretty-prints all tickers and saves output to a file
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    data = load_and_compute()

    # Load the CSV once so we don't re-read it per ticker
    meta = pd.read_csv(DEFAULT_CSV).set_index("ticker")

    OUTPUT_TXT  = pathlib.Path(__file__).parent / "fib_levels.txt"
    OUTPUT_CSV  = pathlib.Path(__file__).parent / "fib_levels.csv"
    PINE_DIR    = pathlib.Path(__file__).parent / "pinescript"
    PINE_DIR.mkdir(exist_ok=True)
    PINE_ALL    = pathlib.Path(__file__).parent / "fib_pinescript_all.txt"

    def tee(line: str, fh):
        """Print to terminal and write the same line to the file."""
        print(line)
        fh.write(line + "\n")

    all_pine_scripts: list[str] = []
    csv_results = []

    with OUTPUT_TXT.open("w", encoding="utf-8") as fh:
        for ticker, grids in data.items():
            row                = meta.loc[ticker]
            atl                = float(row["atl_price"])
            atl_date           = row["atl_date"]
            ath                = float(row["ath_price"])
            ath_date           = row["ath_date"]
            ath_until_atl      = float(row["ath_until_atl_price"])
            ath_until_atl_date = row["ath_until_atl_date"]

            tee(f"\n{'='*65}", fh)
            tee(f"  {ticker}  |  ATL: {atl}  |  ATH until ATL: {ath_until_atl}  |  ATH: {ath}", fh)
            tee(f"  {ticker}  |  ATL date: {atl_date}  |  ATH until ATL date: {ath_until_atl_date}  |  ATH date: {ath_date}", fh)
            tee(f"{'='*65}", fh)

            for g in grids:
                tee(f"\n  Grid {g['grid']}  (top = {g['top']:.6f})", fh)
                for ratio, price in g["levels"].items():
                    marker = " <- 1.0" if ratio == 1.0 else ""
                    tee(f"    {ratio:.3f}  ->  {price:.6f}{marker}", fh)

            # --- Generate Pine Script for this ticker ---
            pine_code = generate_pinescript(ticker, grids)
            pine_file = PINE_DIR / f"{ticker}_fib.pine"
            pine_file.write_text(pine_code, encoding="utf-8")
            all_pine_scripts.append(pine_code)
            tee(f"\n  [Pine Script saved to: {pine_file}]", fh)

            # --- Collect CSV data ---
            csv_results.append({
                "ticker": ticker,
                "atl_date": atl_date,
                "fib_levels": json.dumps(grids)
            })

    # Write combined Pine Script file
    PINE_ALL.write_text(
        "\n\n" + ("=" * 70 + "\n\n").join(all_pine_scripts) + "\n",
        encoding="utf-8",
    )

    # Save CSV
    df_out = pd.DataFrame(csv_results)
    df_out.to_csv(OUTPUT_CSV, index=False)

    print(f"\nOutput saved to: {OUTPUT_TXT}")
    print(f"CSV output saved to: {OUTPUT_CSV}")
    print(f"Pine Script files saved to: {PINE_DIR}/")
    print(f"All Pine Scripts combined in: {PINE_ALL}")
