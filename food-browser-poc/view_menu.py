"""
view_menu.py — Xem menu món ăn & giá của 1 quán cụ thể trên ShopeeFood hoặc GrabFood.

Sử dụng:
  # Xem từ kết quả đã cào gần nhất:
  python view_menu.py --platform shopeefood
  python view_menu.py --platform grabfood

  # Cào trực tiếp từ bất kỳ link quán nào:
  python view_menu.py --url "https://shopeefood.vn/ha-noi/com-ngon-sai-gon-com-ga-com-suon-ngon"
  python view_menu.py --url "https://food.grab.com/vn/en/restaurant/burger-factory-base-2-delivery/5-C3CEAELZREMUGT"
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import argparse
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()
RESULTS_DIR = Path(__file__).parent / "artifacts" / "results"


def display_menu_table(platform: str, restaurant_name: str, dishes: list[dict], url: str = "", address: str = ""):
    if not dishes:
        console.print(f"[yellow]Không tìm thấy món ăn nào cho quán: {restaurant_name}[/]")
        return

    table = Table(
        title=f"🍜 [bold green]{platform}[/bold green] — Thực Đơn Quán: [bold yellow]{restaurant_name}[/bold yellow] ({len(dishes)} món)",
        box=box.ROUNDED,
        header_style="bold magenta",
        title_style="bold",
    )
    table.add_column("#", justify="center", style="dim")
    table.add_column("Tên món ăn (Dish Name)", style="bold cyan")
    table.add_column("Giá hiện tại", justify="right", style="bold green")
    table.add_column("Giá gốc", justify="right", style="dim white")
    table.add_column("Ưu đãi / Giảm giá", justify="center", style="bold red")
    table.add_column("Mô tả / Ghi chú", style="white")

    for i, d in enumerate(dishes, 1):
        price_str = f"{d['dish_price']:,}đ" if d.get("dish_price") else "–"
        orig_str = f"{d['original_price']:,}đ" if d.get("original_price") else "–"
        disc_str = d.get("discount") or "–"
        desc_str = (d.get("description") or "–").replace("\n", " ")
        if len(desc_str) > 70:
            desc_str = desc_str[:67] + "..."

        table.add_row(str(i), d["dish_name"], price_str, orig_str, disc_str, desc_str)

    console.print()
    if address:
        console.print(f"📍 [bold cyan]Địa chỉ quán:[/] [white]{address}[/]")
    console.print(table)
    if url:
        console.print(f"🔗 [dim]Link quán: {url}[/dim]\n")


def view_from_cache(platform: str):
    json_file = RESULTS_DIR / f"{platform.lower()}.json"
    if not json_file.exists():
        console.print(f"[red]Chưa có dữ liệu cache tại {json_file}. Hãy chạy main.py trước hoặc cung cấp --url.[/]")
        return

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    restaurants = data.get("restaurants", [])
    menus = [r for r in restaurants if r.get("menu")]

    if not menus:
        console.print(f"[yellow]Không tìm thấy menu trong cache của {platform}.[/]")
        return

    target = menus[0]
    display_menu_table(
        platform=data.get("platform", platform),
        restaurant_name=target.get("restaurant_name", "Quán ăn"),
        dishes=target["menu"],
        url=target.get("restaurant_url", ""),
        address=target.get("address", ""),
    )


def view_from_url(url: str, headless: bool = True):
    from browser import BrowserSession
    from extractors import ShopeeFoodExtractor, GrabFoodExtractor, _extract_schema_org_address

    is_grab = "grab.com" in url.lower()
    platform = "GrabFood" if is_grab else "ShopeeFood"

    console.print(f"[cyan]Đang mở trình duyệt để cào menu trực tiếp từ {platform}...[/]")
    b = BrowserSession(headless=headless)
    try:
        b.start()
        b.open_page(url, wait_until="networkidle", timeout=35000)
        b.wait(2500)
        b.scroll("down", 600)
        b.wait(1000)

        title = b.get_title().split("|")[0].split("⭐")[0].strip()
        address = _extract_schema_org_address(b) or ""

        if is_grab:
            extractor = GrabFoodExtractor(b)
        else:
            extractor = ShopeeFoodExtractor(b)

        dishes = extractor.extract_menu(max_dishes=50)
        display_menu_table(platform=platform, restaurant_name=title, dishes=dishes, url=url, address=address)
    finally:
        b.close()


def main():
    parser = argparse.ArgumentParser(description="Xem menu món & giá của 1 quán ăn")
    parser.add_argument("--platform", choices=["shopeefood", "grabfood"], default=None, help="Xem từ cache của sàn")
    parser.add_argument("--url", default=None, help="Link URL trực tiếp của quán ăn trên GrabFood hoặc ShopeeFood")
    parser.add_argument("--no-headless", action="store_true", help="Hiện cửa sổ trình duyệt khi cào")
    args = parser.parse_args()

    if args.url:
        view_from_url(args.url, headless=not args.no_headless)
    elif args.platform:
        view_from_cache(args.platform)
    else:
        # Default: show cached ShopeeFood menu (or GrabFood)
        console.print("[bold yellow]Không chỉ định tùy chọn, hiển thị quán ăn từ kết quả đã cào:[/]")
        view_from_cache("shopeefood")


if __name__ == "__main__":
    main()
