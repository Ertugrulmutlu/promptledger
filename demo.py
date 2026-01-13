"""Manual demo data generator for PromptLedger."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from promptledger.core import PromptLedger


def _seed_data(ledger: PromptLedger) -> None:
    ledger.add(
        "onboarding_email",
        "Write a friendly onboarding email.\nKeep it concise.",
        reason="initial draft",
        author="demo",
        tags=["draft", "marketing"],
        env="dev",
        metrics={"score": 0.7},
    )
    ledger.add(
        "onboarding_email",
        "Write a friendly onboarding email.\nKeep it concise and warm.",
        reason="tone update",
        author="demo",
        tags=["marketing"],
        env="staging",
        metrics={"score": 0.82},
    )
    ledger.set_label("onboarding_email", 1, "prod")
    ledger.set_label("onboarding_email", 2, "staging")
    ledger.set_label("onboarding_email", 2, "prod")

    ledger.add(
        "support_reply",
        "Reply to the customer with empathy and a clear next step.",
        reason="baseline",
        author="demo",
        tags=["support"],
        env="dev",
        metrics={"score": 0.6},
    )
    ledger.add(
        "support_reply",
        "Reply with empathy and a clear next step. Ask one clarifying question.",
        reason="add clarification step",
        author="demo",
        tags=["support", "tone"],
        env="prod",
        metrics={"score": 0.9},
    )
    ledger.set_label("support_reply", 2, "prod")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo data for PromptLedger.")
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(".promptledger_demo"),
        help="Directory to store demo DB (default: .promptledger_demo)",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch Streamlit UI after seeding data.",
    )
    args = parser.parse_args()

    demo_home = args.home.resolve()
    os.environ["PROMPTLEDGER_HOME"] = str(demo_home)

    ledger = PromptLedger()
    ledger.init()
    _seed_data(ledger)

    print(f"Demo DB created at {ledger.db_path}")
    print("Try: promptledger status")
    print("Try: promptledger label history")
    print("Try: promptledger diff --id onboarding_email --from prod --to staging")
    print("Try: promptledger diff --id support_reply --from 1 --to 2 --mode metadata")

    if args.ui:
        from promptledger.ui import launch_ui

        launch_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
