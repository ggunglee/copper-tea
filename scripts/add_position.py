from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import UserPosition
from app.db.session import get_session


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("quantity", type=float)
    parser.add_argument("avg_buy_price", type=float)
    parser.add_argument("--currency", default="")
    parser.add_argument("--buy-date", default="")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    session = get_session()
    try:
        position = session.scalar(
            select(UserPosition).where(UserPosition.ticker == args.ticker, UserPosition.is_active.is_(True))
        )
        if position is None:
            position = UserPosition(
                ticker=args.ticker,
                quantity=args.quantity,
                avg_buy_price=args.avg_buy_price,
                buy_date=args.buy_date,
                currency=args.currency,
                notes=args.notes,
                is_active=True,
            )
            session.add(position)
        else:
            position.quantity = args.quantity
            position.avg_buy_price = args.avg_buy_price
            position.buy_date = args.buy_date
            position.currency = args.currency or position.currency
            position.notes = args.notes
        session.commit()
        print(f"Position saved: {args.ticker}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

