from extraction.task_extractor import TaskExtractor
from classification.task_classifier import TaskClassifier
from scheduling.scheduler import Scheduler
from integration.calendar_integration import CalendarIntegration


class BackendAPI:
    """
    Central orchestration component of the Planner_AI system.
    Coordinates task extraction, classification, scheduling,
    and calendar synchronization.
    """

    def submit_notes(self, notes: str) -> dict:
        """
        Accepts freeform daily notes and triggers the processing pipeline.
        """

        # 1. Extract tasks from notes
        extractor = TaskExtractor()
        tasks = extractor.extract(notes)

        # 2. Classify and prioritize tasks
        classifier = TaskClassifier()
        classified_tasks = classifier.classify(tasks)

        # 3. Schedule tasks into calendar slots
        scheduler = Scheduler()
        scheduled_tasks = scheduler.schedule(classified_tasks)

        # 4. Synchronize with external calendar
        integration = CalendarIntegration()
        integration.sync(scheduled_tasks)

        return {
            "status": "success",
            "tasks_processed": len(scheduled_tasks)
        }
