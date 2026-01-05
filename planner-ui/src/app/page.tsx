import { NotesForm } from "@/components/NotesForm";
import { EnergyStatus } from "@/components/EnergyStatus";
import { TaskList } from "@/components/TaskList";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-600 mt-1">
          Submit your daily notes and let AI extract, classify, and schedule your tasks.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <NotesForm />
        </div>
        <div>
          <EnergyStatus />
        </div>
      </div>

      <TaskList />
    </div>
  );
}
