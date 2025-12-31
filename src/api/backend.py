from extraction.task_extractor import TaskExtractor
from classification.task_classifier import TaskClassifier
from integration.calendar_integration import CalendarIntegration
from scheduling.scheduler import Scheduler


class BackendAPI:
    """Central orchestration component of the Planner_AI system."""

    def submit_notes(self, notes: str, llm_tier: str = "large") -> dict:
        """Accepts freeform daily notes and triggers the processing pipeline."""

        # 1. Extract tasks from notes
        extractor = TaskExtractor()
        tasks = extractor.extract(notes, llm_tier=llm_tier)

        # 2. Classify and prioritize tasks
        classifier = TaskClassifier()
        classified_tasks = classifier.classify(tasks, llm_tier=llm_tier)

        # 3. Schedule tasks into calendar slots
        scheduler = Scheduler()
        scheduled_tasks = scheduler.schedule(classified_tasks)

        # 4. Synchronize with external calendar
        integration = CalendarIntegration()
        integration.sync(scheduled_tasks)

        return {
            "tasks_processed": len(scheduled_tasks),
        }
