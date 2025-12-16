from extraction.task_extractor import TaskExtractor
from classification.task_classifier import TaskClassifier
from scheduling.scheduler import Scheduler
from integration.calendar_integration import CalendarIntegration
from fastapi import FastAPI
'from planner_ai.api.backend import BackendAPI TODO intedragtion '

class BackendAPI:

    def submit_notes(self, notes: str):
        extractor = TaskExtractor()
        tasks = extractor.extract(notes)

        classifier = TaskClassifier()
        classified_tasks = classifier.classify(tasks)

        scheduler = Scheduler()
        scheduled_tasks = scheduler.schedule(classified_tasks)

        integration = CalendarIntegration()
        integration.sync(scheduled_tasks)

        return {"status": "ok"}


app = FastAPI()
' backend = BackendAPI() TODO intedragtion '



@app.post("/notes")
def submit_notes(notes: str):
    return backend.submit_notes(notes)
