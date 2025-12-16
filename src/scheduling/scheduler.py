from storage.routine_store import RoutineStore


class Scheduler:

    def schedule(self, tasks: list):
        routines = RoutineStore().load()
        # deterministic scheduling logic
        return tasks
