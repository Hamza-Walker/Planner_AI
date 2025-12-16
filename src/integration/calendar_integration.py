from googleapiclient.discovery import build


class CalendarIntegration:

    def __init__(self, credentials=None):
        self.credentials = credentials

    def sync(self, scheduled_tasks: list):
        """
        Synchronize scheduled tasks with external calendar.
        """
        # Stub for checkpoint – real implementation not required
        service = build(
            "calendar",
            "v3",
            credentials=self.credentials
        )

        for task in scheduled_tasks:
            pass  # create or update calendar event
