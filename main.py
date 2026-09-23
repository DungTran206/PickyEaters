import argparse
import json
import sys
import os

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel

from rich.table import Table
from rich.markdown import Markdown
from agent.agent import FoodAgent
from database.db import get_user_preferences, reset_database

console = Console()


def print_banner(user_id: str):
    console.print(
        Panel.fit(
            f"[bold cyan]🍜 PERSONAL FOOD AGENT (Hôm Nay Ăn Gì?)[/bold cyan]\n"
            f"[dim]AI Agent tìm món thông minh, áp mã giảm giá & học khẩu vị cá nhân[/dim]\n\n"
            f"👤 Đang đăng nhập: [bold green]{user_id}[/bold green] | Gõ [bold yellow]/help[/bold yellow] để xem lệnh",
            border_style="cyan"
        )
    )


def show_preferences(user_id: str):
    pref = get_user_preferences(user_id)
    table = Table(title=f"Khẩu vị & Sở thích: {user_id}", border_style="green")
    table.add_column("Mục", style="bold cyan")
    table.add_column("Giá trị", style="white")

    table.add_row("Ẩm thực yêu thích", ", ".join(pref.preferred_cuisines) or "Chưa có")
    table.add_row("Khẩu vị (cay/ngọt/nồng)", ", ".join(pref.preferred_flavors) or "Bình thường")
    table.add_row("Nguyên liệu ghét (dị ứng)", ", ".join(pref.disliked_ingredients) or "Không có")
    table.add_row("Ngân sách (Budget)", f"{pref.budget:,}đ" if pref.budget else "Chưa đặt")
    table.add_row("Đánh giá tối thiểu", f"{pref.minimum_rating}⭐")
    table.add_row("Món từng thích", ", ".join(pref.liked_dishes) or "Chưa có")
    console.print(table)


def run_cli(user_id: str = "user_01", force_mock: bool = False):
    print_banner(user_id)
    agent = FoodAgent(user_id=user_id, force_mock=force_mock)

    while True:
        try:
            console.print("\n[bold yellow]User:[/bold yellow] ", end="")
            user_input = input().strip()

            if not user_input:
                continue

            if user_input.lower() in ["/quit", "/exit", "exit", "quit"]:
                console.print("[dim]Tạm biệt m nhé, chúc m ăn ngon miệng! 🍜[/dim]")
                break

            if user_input.lower() in ["/pref", "/preferences", "/khauvi"]:
                show_preferences(user_id)
                continue

            if user_input.startswith("/user "):
                parts = user_input.split(maxsplit=1)
                if len(parts) == 2:
                    user_id = parts[1].strip()
                    agent = FoodAgent(user_id=user_id, force_mock=force_mock)
                    console.print(f"[green]Đã chuyển sang tài khoản: [bold]{user_id}[/bold][/green]")
                    show_preferences(user_id)
                continue

            if user_input.lower() == "/reset":
                agent.reset_conversation()
                console.print("[yellow]Đã đặt lại cuộc trò chuyện về trạng thái ban đầu.[/yellow]")
                continue

            if user_input.lower() == "/reset-db":
                reset_database()
                agent = FoodAgent(user_id=user_id, force_mock=force_mock)
                console.print("[red]Đã reset toàn bộ database SQLite về mock seed ban đầu.[/red]")
                continue

            if user_input.lower() == "/help":
                console.print(
                    Panel(
                        "• Gõ yêu cầu bất kỳ, ví dụ:\n"
                        "  - 'Món cay dưới 80k'\n"
                        "  - 'Tao muốn ăn đồ Hàn, gần đây, có deal'\n"
                        "  - 'Tao không thích hành'\n"
                        "  - 'Tối nay ăn gì?'\n\n"
                        "• Lệnh hỗ trợ:\n"
                        "  - /pref: Xem sở thích cá nhân hiện tại\n"
                        "  - /user <id>: Đổi tài khoản người dùng\n"
                        "  - /reset: Xóa lịch sử trò chuyện\n"
                        "  - /reset-db: Khôi phục database SQLite ban đầu\n"
                        "  - /quit: Thoát chương trình",
                        title="Trợ giúp",
                        border_style="blue"
                    )
                )
                continue

            # Run agent turn
            with console.status("[bold cyan]Agent đang suy nghĩ và gọi công cụ...[/bold cyan]"):
                res = agent.run(user_input)

            # Display tool calls trace
            tool_calls = res.get("tool_calls", [])
            if tool_calls:
                console.print("\n[dim]─── [bold cyan]Tool Execution Trace[/bold cyan] ───[/dim]")
                for i, tc in enumerate(tool_calls, 1):
                    tool_name = tc.get("tool")
                    args = tc.get("arguments", {})
                    args_str = json.dumps(args, ensure_ascii=False)
                    console.print(f" [cyan]↳ [bold]{i}. {tool_name}[/bold][/cyan] [dim]args={args_str}[/dim]")
                console.print("[dim]────────────────────────────────[/dim]\n")

            # Display Agent response
            console.print(Markdown(res["response"]))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Tạm biệt m nhé, chúc m ăn ngon miệng! 🍜[/dim]")
            break
        except Exception as e:
            console.print(f"[bold red]Đã xảy ra lỗi: {e}[/bold red]")


def main():
    parser = argparse.ArgumentParser(description="Personal Food Agent MVP")
    parser.add_argument("--serve", "--web", dest="serve", action="store_true", help="Launch Web UI & FastAPI server on http://localhost:8000")
    parser.add_argument("--host", default="127.0.0.1", help="FastAPI host")
    parser.add_argument("--port", type=int, default=8000, help="FastAPI port")
    parser.add_argument("--user", default="user_01", help="Default user ID for CLI")
    parser.add_argument("--mock", action="store_true", help="Force autonomous simulation mode without LLM API key")
    parser.add_argument("--reset-db", action="store_true", help="Reset database before running")

    args = parser.parse_args()

    if args.reset_db:
        reset_database()
        print("Database reset successfully.")

    if args.serve:
        import uvicorn
        console.print(
            Panel.fit(
                f"[bold cyan]🌐 PERSONAL FOOD AGENT WEB UI ĐANG CHẠY[/bold cyan]\n\n"
                f"👉 Truy cập trình duyệt tại: [bold green]http://{args.host}:{args.port}[/bold green]\n"
                f"📖 API Docs tại: [bold yellow]http://{args.host}:{args.port}/docs[/bold yellow]",
                border_style="green"
            )
        )
        uvicorn.run("api:app", host=args.host, port=args.port, reload=True)
    else:
        run_cli(user_id=args.user, force_mock=args.mock)


if __name__ == "__main__":
    main()
