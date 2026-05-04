from sqlalchemy import select

from app.db.models import AlertHistory, RunLog
from app.db.session import get_session


def main() -> None:
    session = get_session()
    try:
        run = session.scalar(select(RunLog).order_by(RunLog.started_at.desc()).limit(1))
        alert_count = session.query(AlertHistory).count()
        if run is None:
            print("No runs yet.")
        else:
            print(f"Last run: #{run.id} {run.status} started={run.started_at} finished={run.finished_at}")
            if run.error_message:
                print(run.error_message)
        print(f"Alert history rows: {alert_count}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

