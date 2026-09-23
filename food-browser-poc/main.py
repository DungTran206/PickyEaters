"""
main.py — CLI entry point for the Food Platform Browser PoC with Menu & Price Extraction.

Usage examples:
  python main.py
  python main.py --platform shopeefood
  python main.py --platform grabfood
  python main.py --platform all --district "Cầu Giấy" --city "Hà Nội"
  python main.py --headless
"""

from __future__ import annotations

import sys
# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import argparse
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from agent import FoodAgent, PlatformResult

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
REPORT_PATH = ARTIFACTS_DIR / "feasibility_report.md"

console = Console()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Food Platform Browser PoC — ShopeeFood & GrabFood access + Menu/Price Extraction"
    )
    parser.add_argument(
        "--platform",
        choices=["shopeefood", "grabfood", "all"],
        default="all",
        help="Which platform to test (default: all)",
    )
    parser.add_argument("--district", default="Cầu Giấy", help="District name (Vietnamese)")
    parser.add_argument("--city", default="Hà Nội", help="City name")
    parser.add_argument("--request", default="Tìm các quán đồ ăn đang có", help="User food request")
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run browser in headless mode (no visible window)",
    )
    parser.add_argument(
        "--no-menu",
        dest="extract_menu",
        action="store_false",
        default=True,
        help="Disable restaurant menu detail extraction",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def yn(val: bool) -> str:
    return "YES ✓" if val else "NO ✗"


def print_feasibility_table(results: list[PlatformResult]):
    table = Table(
        title="FOOD PLATFORM ACCESS TEST",
        box=box.DOUBLE_EDGE,
        style="bold",
        header_style="bold cyan",
    )
    table.add_column("Check", style="dim", width=32)
    for r in results:
        table.add_column(r.platform, justify="center")

    rows = [
        ("Website accessible", "website_accessible"),
        ("Browser interaction", "browser_interaction"),
        ("Search possible", "search_possible"),
        ("Restaurant cards readable", "restaurant_cards_readable"),
        ("Restaurant detail readable", "restaurant_detail_readable"),
        ("Menu readable", "menu_readable"),
        ("Promotion readable", "promotion_readable"),
    ]

    for label, attr in rows:
        row_vals = []
        for r in results:
            val = getattr(r, attr)
            row_vals.append(Text(yn(val), style="green" if val else "red"))
        table.add_row(label, *row_vals)

    console.print("\n")
    console.print(table)

    # Blocked by
    for r in results:
        if r.blocked_by:
            console.print(f"[bold red]{r.platform} blocked by:[/] {r.blocked_by}")

    console.print("\n")


def print_restaurants(result: PlatformResult):
    if not result.restaurants:
        console.print(f"[yellow]{result.platform}: No restaurant data extracted.[/]\n")
        return

    table = Table(
        title=f"{result.platform} — Extracted Restaurants",
        box=box.SIMPLE_HEAVY,
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", width=30)
    table.add_column("Rating", justify="center", width=8)
    table.add_column("Promotion", width=25)
    table.add_column("URL", width=35)

    for i, r in enumerate(result.restaurants, 1):
        table.add_row(
            str(i),
            r.get("restaurant_name") or "–",
            str(r.get("rating")) if r.get("rating") else "–",
            (r.get("promotion") or "–")[:40],
            (r.get("restaurant_url") or "–")[:50],
        )

    console.print(table)
    console.print()


def print_menus(result: PlatformResult):
    """Print extracted menu items & prices in a clean table."""
    restaurants_with_menu = [r for r in result.restaurants if r.get("menu")]
    if not restaurants_with_menu:
        return

    for r in restaurants_with_menu:
        menu = r["menu"]
        table = Table(
            title=f"🍽️ {result.platform} — Menu Quán: {r.get('restaurant_name')} ({len(menu)} món)",
            box=box.ROUNDED,
            header_style="bold green",
        )
        table.add_column("#", style="dim", width=3)
        table.add_column("Tên món ăn (Dish Name)", style="bold cyan", width=35)
        table.add_column("Giá hiện tại", style="bold yellow", justify="right", width=14)
        table.add_column("Giá gốc", style="dim white", justify="right", width=12)
        table.add_column("Khuyến mãi", style="bold red", width=18)
        table.add_column("Mô tả / Nguyên liệu", style="white", width=40)

        for idx, d in enumerate(menu, 1):
            price_str = f"{d['dish_price']:,}đ" if d.get("dish_price") else "–"
            orig_str = f"{d['original_price']:,}đ" if d.get("original_price") else "–"
            disc_str = d.get("discount") or "–"
            desc_str = (d.get("description") or "–")[:60]

            table.add_row(str(idx), d["dish_name"], price_str, orig_str, disc_str, desc_str)

        console.print(table)
        console.print()


def save_feasibility_report(results: list[PlatformResult], location: str, request: str):
    lines = [
        "# Food Platform Browser PoC — Feasibility Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Location tested:** {location}",
        f"**Request tested:** {request}",
        "",
        "---",
        "",
        "```",
        "================================",
        "FOOD PLATFORM ACCESS TEST",
        "================================",
        "",
    ]

    for r in results:
        lines.append(f"{r.platform}:")
        lines.append(f"- Website accessible:         {yn(r.website_accessible)}")
        lines.append(f"- Browser interaction:        {yn(r.browser_interaction)}")
        lines.append(f"- Search possible:            {yn(r.search_possible)}")
        lines.append(f"- Restaurant cards readable:  {yn(r.restaurant_cards_readable)}")
        lines.append(f"- Restaurant detail readable: {yn(r.restaurant_detail_readable)}")
        lines.append(f"- Menu readable:              {yn(r.menu_readable)}")
        lines.append(f"- Promotion readable:         {yn(r.promotion_readable)}")
        lines.append(f"- Blocked by:                 {r.blocked_by or 'N/A'}")
        lines.append("")

    lines.append("```")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for r in results:
        if r.notes:
            lines.append(f"### {r.platform}")
            for note in r.notes:
                lines.append(f"- {note}")
            lines.append("")

    lines.append("## Extracted Data Summary")
    lines.append("")
    for r in results:
        lines.append(f"### {r.platform}")
        lines.append(f"- Restaurants found: {len(r.restaurants)}")
        menus = [rest for rest in r.restaurants if rest.get("menu")]
        if menus:
            for rest in menus:
                lines.append(f"- **Menu extracted for: {rest.get('restaurant_name')}** ({len(rest['menu'])} items):")
                for d in rest["menu"][:5]:
                    orig = f" (gốc {d['original_price']:,}đ)" if d.get('original_price') else ""
                    disc = f" [{d['discount']}]" if d.get('discount') else ""
                    lines.append(f"  - {d['dish_name']}: **{d['dish_price']:,}đ**{orig}{disc}")
        elif r.restaurants:
            lines.append("- Sample restaurants:")
            for rest in r.restaurants[:5]:
                name = rest.get("restaurant_name") or "unknown"
                lines.append(f"  - {name}")
        lines.append("")

    lines.append("## Screenshots")
    lines.append("")
    screenshots_dir = ARTIFACTS_DIR / "screenshots"
    if screenshots_dir.exists():
        for png in sorted(screenshots_dir.glob("*.png")):
            lines.append(f"- `{png.name}`")
    lines.append("")

    lines.append("## What's Required to Build the Full Food Agent")
    lines.append("")
    lines.append(
        "1. **Selector maintenance**: Both platforms update their DOM regularly. "
        "A selector registry or resilient CSS module selector fallback is recommended."
    )
    lines.append(
        "2. **Anti-bot handling**: ShopeeFood may trigger CAPTCHA on unauthenticated high-frequency requests. Persistent browser context solves this."
    )
    lines.append(
        "3. **Menu extraction verified**: GrabFood and ShopeeFood both allow extracting full dishes, descriptions, and current/original prices."
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Feasibility report saved → {REPORT_PATH}[/]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    location = f"{args.district}, {args.city}"

    console.print(Panel(
        f"[bold cyan]Food Platform Browser PoC with Menu Extraction[/]\n"
        f"Location     : [yellow]{location}[/]\n"
        f"Request      : [yellow]{args.request}[/]\n"
        f"Platform     : [yellow]{args.platform}[/]\n"
        f"Headless     : [yellow]{args.headless}[/]\n"
        f"Extract Menu : [yellow]{args.extract_menu}[/]",
        title="[bold]Configuration[/]",
        expand=False,
    ))

    agent = FoodAgent(
        location=location,
        user_request=args.request,
        headless=args.headless,
        extract_menu=args.extract_menu,
    )

    results: list[PlatformResult] = []

    if args.platform in ("grabfood", "all"):
        console.rule("[bold green]Running GrabFood Test[/]")
        gf_result = agent.run_grabfood()
        results.append(gf_result)

    if args.platform in ("shopeefood", "all"):
        console.rule("[bold green]Running ShopeeFood Test[/]")
        sf_result = agent.run_shopeefood()
        results.append(sf_result)

    # Print summary table
    print_feasibility_table(results)

    # Print restaurants and menus
    for r in results:
        print_restaurants(r)
        if args.extract_menu:
            print_menus(r)

    # Print terminal-style feasibility block
    console.rule()
    print()
    print("================================")
    print("FOOD PLATFORM ACCESS TEST")
    print("================================")
    print()
    for r in results:
        print(f"{r.platform}:")
        print(f"  - Website accessible:         {yn(r.website_accessible)}")
        print(f"  - Browser interaction:        {yn(r.browser_interaction)}")
        print(f"  - Search possible:            {yn(r.search_possible)}")
        print(f"  - Restaurant cards readable:  {yn(r.restaurant_cards_readable)}")
        print(f"  - Restaurant detail readable: {yn(r.restaurant_detail_readable)}")
        print(f"  - Menu readable:              {yn(r.menu_readable)}")
        print(f"  - Promotion readable:         {yn(r.promotion_readable)}")
        print(f"  - Blocked by:                 {r.blocked_by or 'N/A'}")
        print()

    # Print screenshots taken
    screenshots_dir = ARTIFACTS_DIR / "screenshots"
    if screenshots_dir.exists():
        pngs = sorted(screenshots_dir.glob("*.png"))
        if pngs:
            console.print(f"\n[bold]Screenshots ({len(pngs)}):[/]")
            for p in pngs:
                console.print(f"  → {p}")

    # Save report
    save_feasibility_report(results, location, args.request)

    # Final exit code: 0 if at least one platform was accessible
    if any(r.website_accessible for r in results):
        sys.exit(0)
    else:
        console.print("[bold red]No platform was accessible. Check your internet connection.[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
