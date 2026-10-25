"use client";

import { useEffect, useState, type FormEvent } from "react";
import Image from "next/image";
import { signOut } from "next-auth/react";
import {
  BookOpen,
  CalendarDays,
  Check,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  LayoutDashboard,
  Lightbulb,
  Link2,
  Plus,
  Pencil,
  Play,
  Settings,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

type TransportMode = "fastest" | "walking" | "transit" | "cycling";
type DashboardTab = "dashboard" | "settings";

const DEFAULT_HOME_LOCATION = "St. Catherine's College";
const SETTINGS_STORAGE_KEY = "flowboard:settings:v1";
const DEFAULT_WORKDAY_START_HOUR = 8;
const DEFAULT_WORKDAY_END_HOUR = 19;
const DEFAULT_SIMULATION_COUNT = 10000;

function formatHour(hour: number) {
  if (hour === 24) return "12:00 AM (next day)";
  return `${hour % 12 || 12}:00 ${hour < 12 ? "AM" : "PM"}`;
}

type Task = {
  id: string;
  name: string;
  deadline: string; // Local YYYY-MM-DD date, without timezone shifting.
  isIndivisible: boolean;
  completionPercentage: number; // 0-100, not a completed/not-completed flag.
  estimatedLength: number | null; // Required before predicting; legacy tasks may lack it.
};

function normalizeStoredTasks(items: unknown[]): Task[] {
  return items.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return item as Task;
    }
    const task = item as Record<string, unknown>;
    return {
      ...task,
      isIndivisible:
        typeof task.isIndivisible === "boolean" ? task.isIndivisible : false,
    } as Task;
  });
}

export type InfoCard = {
  id: string;
  title: string;
  description: string;
  category?: string;
};

type PredictResponse = {
  review: {
    original_prediction: {
      num_simulations_per_scenario: number;
      risk_by_name: NamedRisk[];
      task_diagnostics: TaskDiagnostic[];
    };
    repaired_prediction: {
      risk_by_name: NamedRisk[];
      task_diagnostics: TaskDiagnostic[];
    };
    judge: {
      measured_verdict: string;
      average_failure_risk_percent: { original: number; repaired: number };
      analysis: { summary: string; remaining_risks: string[] };
    };
    repair: {
      changes: string[];
      warnings: string[];
      proposed_plan: { tasks: Array<{ id: string; title: string }> };
      proposed_task_schedule: Array<{
        task_id: string;
        start_time: number;
        reasoning: string;
      }>;
    };
  };
};

type NamedRisk = {
  name: string;
  category: "meetings" | "tasks" | "unfinished_tasks";
  failure_probability_percent: number;
};

type TaskDiagnostic = {
  name: string;
  deadline_within_simulation_horizon: boolean;
};

function summarisePrediction({ review }: PredictResponse) {
  const { judge, repair } = review;
  const risk = judge.average_failure_risk_percent;
  const taskNames = new Map(
    repair.proposed_plan.tasks.map((task) => [task.id, task.title]),
  );
  const proposedTaskOrder = [...repair.proposed_task_schedule]
    .sort((left, right) => left.start_time - right.start_time)
    .map((item) => ({
      id: item.task_id,
      name: taskNames.get(item.task_id) ?? "Task",
      reasoning: item.reasoning.trim(),
    }));
  const formatRisk = (value: number | undefined) =>
    value === undefined ? "not returned" : `${value.toFixed(1)}%`;
  const riskKey = (item: NamedRisk) => `${item.category}\u0000${item.name}`;
  const originalRisks = new Map(
    review.original_prediction.risk_by_name.map((item) => [riskKey(item), item]),
  );
  const repairedRisks = new Map(
    review.repaired_prediction.risk_by_name.map((item) => [riskKey(item), item]),
  );
  const originalDiagnostics = new Map(
    review.original_prediction.task_diagnostics.map((item) => [item.name, item]),
  );
  const repairedDiagnostics = new Map(
    review.repaired_prediction.task_diagnostics.map((item) => [item.name, item]),
  );
  const taskOutcomeLines: string[] = [];
  const eventRiskCards: InfoCard[] = [];
  const describeRiskChange = (before: number, after: number) => {
    const change = after - before;
    if (change > 0) return `risk increased by ${change.toFixed(1)} percentage points in the revised simulation`;
    if (change < 0) return `risk decreased by ${Math.abs(change).toFixed(1)} percentage points in the revised simulation`;
    return "risk was unchanged in the revised simulation";
  };

  for (const [key, original] of originalRisks) {
    if (original.category === "unfinished_tasks") continue;
    const repaired = repairedRisks.get(key);
    const originalDeadlineRisk = original.failure_probability_percent;
    if (original.category === "meetings") {
      const repairedRisk = repaired?.failure_probability_percent;
      if (originalDeadlineRisk === 0 && repairedRisk === 0) continue;
      const comparison = repairedRisk === undefined
        ? "Revised simulation risk not returned."
        : `${describeRiskChange(originalDeadlineRisk, repairedRisk)}.`;
      eventRiskCards.push({
        id: `event-risk-${eventRiskCards.length}`,
        category: "Event risk",
        title: original.name,
        description: `Missed-event risk: ${formatRisk(originalDeadlineRisk)} → ${formatRisk(repairedRisk)}. ${comparison} Consider leaving earlier, checking alternate transport or routes, or asking whether the event can be rescheduled. These options were not tested by the simulation, and your calendar was not changed.`,
      });
      continue;
    }

    const diagnostic = originalDiagnostics.get(original.name);
    const repairedDiagnostic = repairedDiagnostics.get(original.name);
    const withinHorizon =
      diagnostic?.deadline_within_simulation_horizon ??
      repairedDiagnostic?.deadline_within_simulation_horizon;
    const unfinishedKey = riskKey({
      ...original,
      category: "unfinished_tasks",
    });
    const originalUnfinished = originalRisks.get(unfinishedKey)?.failure_probability_percent;
    const repairedUnfinished = repairedRisks.get(unfinishedKey)?.failure_probability_percent;
    if (withinHorizon === true) {
      const after = repaired?.failure_probability_percent;
      if (originalDeadlineRisk !== 0 || after !== 0) {
        taskOutcomeLines.push(
          `${original.name} — missed deadline: ${formatRisk(originalDeadlineRisk)} → ${formatRisk(after)}${after === undefined ? " (revised simulation risk not returned)" : `; ${describeRiskChange(originalDeadlineRisk, after)}`}.`,
        );
      }
    } else if (
      withinHorizon === false &&
      originalUnfinished !== undefined &&
      (originalUnfinished !== 0 || repairedUnfinished !== 0)
    ) {
      const after = repairedUnfinished;
      taskOutcomeLines.push(
        `${original.name} — unfinished at the 7-day simulation horizon: ${formatRisk(originalUnfinished)} → ${formatRisk(after)}${after === undefined ? " (revised simulation risk not returned)" : `; ${describeRiskChange(originalUnfinished, after)}`}.`,
      );
    }
  }

  const riskCards: InfoCard[] = [
    ...(originalRisks.size > 0 &&
    [...originalRisks.values()].some((item) => item.category === "meetings") &&
    eventRiskCards.length === 0
      ? [{
          id: "event-attendance",
          category: "Event attendance",
          title: "No events were missed in the simulations",
          description: `All tracked events were reached in both the original and revised schedules across ${review.original_prediction.num_simulations_per_scenario.toLocaleString()} simulations per schedule. This is a simulation result, not a guarantee.`,
        }]
      : []),
    ...eventRiskCards,
    ...(taskOutcomeLines.length > 0
      ? [{
          id: "task-risk-summary",
          category: "Task outcomes",
          title: "Task risk in original vs revised simulation",
          description: taskOutcomeLines.join("\n"),
        }]
      : []),
  ];

  const cards: InfoCard[] = [
    ...riskCards,
    {
      id: "risk",
      category: "Risk",
      title: `Average failure risk: ${judge.measured_verdict}`,
      description: risk.original === 0 && risk.repaired === 0
        ? "No failures were observed across tracked items in either simulated schedule."
        : `Average measured failure risk across tracked tasks and events: ${risk.original.toFixed(1)}% in the original simulation and ${risk.repaired.toFixed(1)}% in the revised simulation.`,
    },
    ...(proposedTaskOrder.length > 0
      ? [{
          id: "proposed-task-order",
          category: "Suggested priority",
          title: "Proposed order for the revised simulation",
          description: `The baseline simulation automatically prioritizes tasks using their deadlines and remaining estimated effort. The revised simulation uses this proposed order:\n\n${proposedTaskOrder.map((task, index) =>
            `${index + 1}. ${task.name}${task.reasoning ? ` — ${task.reasoning}` : ""}`
          ).join("\n")}\n\nThis order is a priority hint, not a reserved timetable. It does not move calendar events or guarantee the task will be completed.`,
        }]
      : []),
    ...repair.changes.map((change, index) => ({
      id: `change-${index}`,
      category: "Change",
      title: "Suggested change",
      description: change,
    })),
    ...[...repair.warnings, ...judge.analysis.remaining_risks].map((text, index) => ({
      id: `watch-${index}`,
      category: "Watch out",
      title: "Remaining risk",
      description: text,
    })),
  ];
  return { suggestionText: judge.analysis.summary, cards };
}

type DashboardProps = {
  suggestionText: string;
  /** Cards generated on the server by your LLM, not manually added. */
  informationCards?: InfoCard[];
};

function useLocalCollection<T>(storageKey: string, normalize?: (items: unknown[]) => T[]) {
  const [items, setItems] = useState<T[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (Array.isArray(parsed)) setItems(normalize ? normalize(parsed) : parsed as T[]);
      }
    } catch {
      // An invalid or blocked localStorage entry should not break the UI.
    } finally {
      setLoaded(true);
    }
  }, [normalize, storageKey]);

  useEffect(() => {
    if (!loaded) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      // The dashboard still works when storage is unavailable.
    }
  }, [items, loaded, storageKey]);

  return [items, setItems] as const;
}

function formatDeadline(isoDate: string) {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return Number.isNaN(date.getTime())
    ? isoDate
    : new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      }).format(date);
}

export default function Dashboard({
  suggestionText,
  // Supply informationCards from your LLM in app/page.tsx.
  informationCards = [],
}: DashboardProps) {
  const [tasks, setTasks] = useLocalCollection<Task>(
    "flowboard:tasks:v1",
    normalizeStoredTasks,
  );
  const [taskFormOpen, setTaskFormOpen] = useState(false);
  const [calendarMenuOpen, setCalendarMenuOpen] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState<
    "checking" | "connected" | "disconnected" | "error"
  >("checking");
  const [calendarConfigured, setCalendarConfigured] = useState(false);
  const [calendarEmail, setCalendarEmail] = useState<string | null>(null);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionMessage, setPredictionMessage] = useState("");
  const [completedSimulationCount, setCompletedSimulationCount] = useState<number | null>(null);
  const [prediction, setPrediction] = useState<ReturnType<typeof summarisePrediction> | null>(null);
  const [simulationCount, setSimulationCount] = useState(DEFAULT_SIMULATION_COUNT);
  const [preferredTransportMode, setPreferredTransportMode] = useState<TransportMode>("fastest");
  const [homeLocation, setHomeLocation] = useState(DEFAULT_HOME_LOCATION);
  const [workdayStartHour, setWorkdayStartHour] = useState(DEFAULT_WORKDAY_START_HOUR);
  const [workdayEndHour, setWorkdayEndHour] = useState(DEFAULT_WORKDAY_END_HOUR);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [activeTab, setActiveTab] = useState<DashboardTab>("dashboard");
  const shownCards = prediction?.cards ?? informationCards;
  const shownSuggestion = prediction?.suggestionText ?? suggestionText;

  useEffect(() => {
    let active = true;

    async function loadCalendarStatus() {
      try {
        const response = await fetch("/api/calendar/account", { cache: "no-store" });
        if (!response.ok) {
          throw new Error(`Calendar status request failed (${response.status})`);
        }
        const result: unknown = await response.json();
        if (
          !result ||
          typeof result !== "object" ||
          !("configured" in result) ||
          typeof result.configured !== "boolean" ||
          !("connected" in result) ||
          typeof result.connected !== "boolean" ||
          !("email" in result) ||
          (result.email !== null && typeof result.email !== "string")
        ) {
          throw new Error("Calendar status response was invalid.");
        }
        if (!active) return;
        setCalendarConfigured(result.configured);
        setCalendarEmail(result.email);
        setCalendarStatus(result.connected ? "connected" : "disconnected");
      } catch {
        if (active) setCalendarStatus("error");
      }
    }

    void loadCalendarStatus();
    return () => {
      active = false;
    };
  }, []);

  const calendarConnected = calendarStatus === "connected";
  const calendarStatusLabel = {
    checking: "Checking calendar",
    connected: "Calendar connected",
    disconnected: "Calendar disconnected",
    error: "Calendar status unavailable",
  }[calendarStatus];

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (stored) {
        const settings: unknown = JSON.parse(stored);
        if (settings && typeof settings === "object") {
          const saved = settings as Record<string, unknown>;
          if (
            saved.preferredTransportMode === "fastest" ||
            saved.preferredTransportMode === "walking" ||
            saved.preferredTransportMode === "transit" ||
            saved.preferredTransportMode === "cycling"
          ) {
            setPreferredTransportMode(saved.preferredTransportMode);
          }
          if (
            typeof saved.homeLocation === "string" &&
            saved.homeLocation.trim()
          ) {
            setHomeLocation(saved.homeLocation);
          }
          const savedStartHour = Number.isInteger(saved.workdayStartHour)
            && Number(saved.workdayStartHour) >= 0
            && Number(saved.workdayStartHour) < 24
            ? Number(saved.workdayStartHour)
            : DEFAULT_WORKDAY_START_HOUR;
          const savedEndHour = Number.isInteger(saved.workdayEndHour)
            && Number(saved.workdayEndHour) > 0
            && Number(saved.workdayEndHour) <= 24
            ? Number(saved.workdayEndHour)
            : DEFAULT_WORKDAY_END_HOUR;
          if (savedEndHour > savedStartHour) {
            setWorkdayStartHour(savedStartHour);
            setWorkdayEndHour(savedEndHour);
          }
          if (
            Number.isSafeInteger(saved.simulationCount) &&
            Number(saved.simulationCount) >= 1 &&
            Number(saved.simulationCount) <= 1000000
          ) {
            setSimulationCount(Number(saved.simulationCount));
          }
        }
      }
    } catch {
      // Ignore invalid or unavailable local settings and use defaults.
    } finally {
      setSettingsLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!settingsLoaded) return;
    try {
      window.localStorage.setItem(
        SETTINGS_STORAGE_KEY,
        JSON.stringify({
          preferredTransportMode,
          homeLocation,
          workdayStartHour,
          workdayEndHour,
          simulationCount,
        }),
      );
    } catch {
      // Settings remain usable for this page session if storage is unavailable.
    }
  }, [homeLocation, preferredTransportMode, settingsLoaded, simulationCount, workdayEndHour, workdayStartHour]);

  const [taskName, setTaskName] = useState("");
  const [deadline, setDeadline] = useState("");
  const [isIndivisible, setIsIndivisible] = useState(false);
  const [completionPercentage, setCompletionPercentage] = useState(0);
  const [estimatedLength, setEstimatedLength] = useState("");

  function addTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const duration = Number(estimatedLength);
    if (!taskName.trim() || !deadline || !Number.isSafeInteger(duration) || duration <= 0) return;

    setTasks((existing) => [
      ...existing,
      {
        id: crypto.randomUUID(),
        name: taskName.trim(),
        deadline,
        isIndivisible,
        completionPercentage,
        estimatedLength: duration,
      },
    ]);
    setTaskName("");
    setDeadline("");
    setIsIndivisible(false);
    setCompletionPercentage(0);
    setEstimatedLength("");
    setTaskFormOpen(false);
  }

  function deleteTask(id: string) {
    setTasks((existing) => existing.filter((task) => task.id !== id));
  }

  function updateTask(id: string, changes: Partial<Pick<Task, "deadline" | "isIndivisible" | "completionPercentage" | "estimatedLength">>) {
    // Never allow an edit to erase the required deadline.
    if (changes.deadline !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(changes.deadline)) return;
    if (changes.completionPercentage !== undefined) {
      if (!Number.isInteger(changes.completionPercentage) || changes.completionPercentage < 0 || changes.completionPercentage > 100) return;
    }
    if (changes.estimatedLength !== undefined && changes.estimatedLength !== null) {
      if (!Number.isSafeInteger(changes.estimatedLength) || changes.estimatedLength <= 0) return;
    }
    setTasks((existing) =>
      existing.map((task) => task.id === id ? { ...task, ...changes } : task)
    );
  }

  async function startPrediction() {
    if (predictionLoading) return;
    setPredictionMessage("");
    if (!homeLocation.trim()) {
      setPredictionMessage("Set a home location in Settings before predicting.");
      return;
    }
    if (workdayEndHour <= workdayStartHour) {
      setPredictionMessage("Your workday must end after it starts.");
      return;
    }
    if (!Number.isSafeInteger(simulationCount) || simulationCount < 1 || simulationCount > 1000000) {
      setPredictionMessage("Choose between 1 and 1,000,000 simulations.");
      return;
    }

    // Older tasks in localStorage do not have an estimated length. Never
    // invent a duration: users must provide one before sending to Python.
    if (tasks.some((task) =>
      typeof task.estimatedLength !== "number" ||
      !Number.isSafeInteger(task.estimatedLength) ||
      task.estimatedLength <= 0
    )) {
      setPredictionMessage("Add an estimated length (minutes) to every task before predicting.");
      return;
    }

    setPredictionLoading(true);
    setCompletedSimulationCount(null);
    try {
      // Python converts dashboard fields into engine Task objects:
      // name -> title, completionPercentage -> completion_pct,
      // estimatedLength -> estimated_length; simulation priority is derived
      // from remaining effort and available work time before the deadline.
      // isIndivisible -> can_be_divided, date -> end-of-day datetime.
      const response = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tasks: tasks.map((task) => ({
            id: task.id,
            name: task.name,
            deadline: task.deadline,
            canBeDivided: !task.isIndivisible,
            completionPercentage: task.completionPercentage ?? 0,
            estimatedLength: task.estimatedLength,
          })),
          preferredTransportMode,
          startingLocation: homeLocation.trim(),
          workdayStartHour,
          workdayEndHour,
          numSimulations: simulationCount,
        }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? `Prediction request failed (${response.status})`);
      }
      // The backend runs the planning workflow and returns its review; turn it
      // into the Information cards and Suggestions shown on the right.
      const result = (await response.json()) as PredictResponse;
      setPrediction(summarisePrediction(result));
      setCompletedSimulationCount(result.review.original_prediction.num_simulations_per_scenario);
      setPredictionMessage("Prediction complete.");
    } catch (error) {
      setPredictionMessage(
        error instanceof Error ? error.message : "Could not start prediction."
      );
    } finally {
      setPredictionLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-left">
          <Image className="brand-logo" src="/deltat.svg" alt="" width={40} height={37} priority />
          <span className="brand-name">delta-t</span>
          <span className="topbar-divider" />
          <nav className="workspace-navigation" aria-label="Workspace">
            <button
              className={activeTab === "dashboard" ? "active-navigation" : "navigation-button"}
              type="button"
              aria-label="Dashboard"
              aria-current={activeTab === "dashboard" ? "page" : undefined}
              onClick={() => setActiveTab("dashboard")}
            >
              <LayoutDashboard size={16} strokeWidth={2.2} /> Dashboard
            </button>
            <button
              className={activeTab === "settings" ? "active-navigation" : "navigation-button"}
              type="button"
              aria-label="Settings"
              aria-current={activeTab === "settings" ? "page" : undefined}
              onClick={() => setActiveTab("settings")}
            >
              <Settings size={16} strokeWidth={2.2} /> Settings
            </button>
          </nav>
        </div>

        <div className="topbar-right">
          <span className="workspace-label">PERSONAL WORKSPACE</span>
          <div className="calendar-menu-wrap">
            <button
              className={`calendar-menu-trigger ${calendarConnected ? "connected" : ""}`}
              type="button"
              aria-haspopup="menu"
              aria-expanded={calendarMenuOpen}
              onClick={() => setCalendarMenuOpen((open) => !open)}
            >
              <CalendarDays size={17} />
              <span>{calendarStatusLabel}</span>
              <span className={`connection-dot${calendarConnected ? "" : " disconnected"}`} />
              <ChevronDown size={15} />
            </button>

            {calendarMenuOpen && (
              <div className="calendar-dropdown" role="menu">
                <div className="dropdown-eyebrow">GOOGLE CALENDAR</div>
                {calendarStatus === "checking" ? (
                  <p className="dropdown-help">Checking the calendar connection for this browser…</p>
                ) : calendarConnected ? (
                  <>
                    <div className="dropdown-state">
                      <span className="dropdown-success"><Check size={16} /></span>
                      <div>
                        <strong>Calendar connected</strong>
                        <small>{calendarEmail ?? "Google account"}</small>
                      </div>
                    </div>
                    <p className="dropdown-help">Read-only event access is linked. Events are not imported into this starter.</p>
                    <button
                      className="dropdown-action secondary"
                      type="button"
                      role="menuitem"
                      onClick={() => void signOut({ redirectTo: "/" })}
                    >
                      Sign out of dashboard
                    </button>
                  </>
                ) : calendarStatus === "error" ? (
                  <p className="dropdown-help" role="alert">
                    Could not check the calendar connection. Refresh the page to try again.
                  </p>
                ) : (
                  <>
                    <p className="dropdown-help">
                      {calendarConfigured
                        ? "Connect your Google account to enable read-only Calendar access."
                        : "Calendar connection is not configured yet. Add Google OAuth credentials to enable it."}
                    </p>
                    {calendarConfigured && (
                      <button
                        className="dropdown-action"
                        type="button"
                        role="menuitem"
                        onClick={() => { window.location.href = "/auth/google";}}
                      >
                        <Link2 size={16} /> Connect Google Calendar
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
          <div className="avatar" aria-label="Personal workspace">Δt</div>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="page-intro">
          <div>
            <span className="eyebrow">
              <span className="eyebrow-dot" />
              {activeTab === "dashboard" ? "YOUR DAY, SIMULATED" : "PREFERENCES"}
            </span>
            <h1>
              {activeTab === "dashboard" ? "Your dashboard" : "Settings"}
              {activeTab === "dashboard" && <span className="wave" aria-hidden="true">✳</span>}
            </h1>
            <p>
              {activeTab === "dashboard"
                ? "One calm place for everything you need to get done."
                : "Personalize how your day is simulated."}
            </p>
          </div>
        </div>

        <style>{`
          .dashboard-grid.prediction-layout {
            grid-template-columns: minmax(0, 1fr) minmax(210px, 250px) minmax(0, 1fr);
            gap: 18px;
          }
          .prediction-middle {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: stretch;
            gap: 16px;
            min-width: 0;
          }
          .prediction-start-button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            border: 0;
            border-radius: 12px;
            padding: 14px 16px;
            font-size: 13px;
            font-weight: 800;
            color: white;
            background: linear-gradient(145deg, #806df3, #705ae6);
            box-shadow: 0 6px 16px #8069e629;
          }
          .prediction-status {
            color: #737b92;
            font-size: 11px;
            line-height: 1.5;
            overflow-wrap: anywhere;
          }
          @media (max-width: 1050px) and (min-width: 761px) {
            .dashboard-grid.prediction-layout {
              grid-template-columns: minmax(0, 1fr) minmax(180px, 210px) minmax(0, 1fr);
              gap: 10px;
            }
          }
          @media (max-width: 760px) {
            .dashboard-grid.prediction-layout { display: flex; flex-direction: column; }
            .prediction-middle { padding: 0 12px; }
            .prediction-start-button { width: min(100%, 360px); align-self: center; }
          }
          .transport-preference {
            display: flex;
            flex-direction: column;
            gap: 6px;
            width: 100%;
            color: #66708a;
            font-size: 10px;
            font-weight: 700;
          }
          .transport-preference select {
            width: 100%;
            min-width: 0;
            padding: 8px;
            border: 1px solid #e5e4ef;
            border-radius: 8px;
            background: white;
            color: #39415e;
            font-size: 11px;
          }
          .transport-preference input {
            width: 100%;
            min-width: 0;
            padding: 10px;
            border: 1px solid #e5e4ef;
            border-radius: 8px;
            background: white;
            color: #39415e;
            font-size: 13px;
          }
          .transport-preference-help {
            margin: 0;
            color: #737b92;
            font-size: 10px;
            line-height: 1.4;
            text-align: center;
          }
          .task-edit-controls {
            display: flex;
            flex-wrap: wrap;
            align-items: end;
            gap: 10px;
            margin-top: 7px;
          }
          .task-edit-controls label {
            display: flex;
            flex-direction: column;
            gap: 5px;
            font-size: 10px;
            font-weight: 700;
            color: #66708a;
          }
          .task-edit-controls input[type="date"], .task-edit-controls input[type="number"], .task-edit-controls select {
            min-width: 0;
            max-width: 160px;
            padding: 7px;
            border: 1px solid #e5e4ef;
            background: white;
            border-radius: 8px;
            color: #39415e;
            font-size: 11px;
          }
          .task-edit-controls .task-edit-checkbox {
            flex-direction: row;
            align-items: center;
            gap: 7px;
            cursor: pointer;
          }
          .task-edit-controls .task-edit-checkbox input {
            width: 15px;
            height: 15px;
            margin: 0;
            accent-color: #705ae6;
          }
          .completion-field {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-top: 12px;
          }
          .completion-field-label {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            color: #39415e;
            font-weight: 700;
          }
          .completion-field output,
          .task-edit-progress output {
            font-variant-numeric: tabular-nums;
            color: #705ae6;
          }
          .completion-field input[type="range"],
          .task-edit-progress input[type="range"] {
            display: block;
            width: 100%;
            accent-color: #705ae6;
            cursor: pointer;
          }
          .task-edit-controls .task-edit-progress {
            flex: 1 0 100%;
            display: flex;
            flex-direction: column;
            align-items: stretch;
            gap: 7px;
          }
          .task-edit-progress .completion-field-label {
            font-size: 11px;
          }
        `}</style>
        {activeTab === "dashboard" ? (
        <div className="dashboard-grid prediction-layout">
          <section className="panel todo-panel" aria-labelledby="todo-heading">
            <div className="panel-heading">
              <div className="heading-text">
                <div className="section-icon lilac"><ClipboardList size={20} /></div>
                <div>
                  <h2 id="todo-heading">To-do list</h2>
                  <p>{tasks.length === 1 ? "1 task" : `${tasks.length} tasks`}</p>
                </div>
              </div>
              <button
                className="primary-button"
                type="button"
                aria-expanded={taskFormOpen}
                onClick={() => setTaskFormOpen((open) => !open)}
              >
                {taskFormOpen ? <X size={16} /> : <Plus size={17} />}
                {taskFormOpen ? "Close" : "Add task"}
              </button>
            </div>

            {taskFormOpen && (
              <form className="entry-form" onSubmit={addTask}>
                <h3>Create a task</h3>
                <label htmlFor="task-name">Task name</label>
                <input
                  id="task-name"
                  placeholder="e.g. Finish project proposal"
                  value={taskName}
                  onChange={(event) => setTaskName(event.target.value)}
                  maxLength={130}
                  required
                  autoFocus
                />
                <div>
                  <label htmlFor="task-deadline">Deadline</label>
                  <input
                    id="task-deadline"
                    type="date"
                    value={deadline}
                    onChange={(event) => setDeadline(event.target.value)}
                    required
                  />
                </div>
                <div className="completion-field">
                  <label htmlFor="task-estimated-length">Estimated length (minutes)</label>
                  <input
                    id="task-estimated-length"
                    type="number"
                    min={1}
                    step={1}
                    placeholder="e.g. 60"
                    value={estimatedLength}
                    onChange={(event) => setEstimatedLength(event.target.value)}
                    required
                  />
                </div>
                <div className="completion-field">
                  <label className="completion-field-label" htmlFor="task-completion">
                    <span>Task completion</span>
                    <output htmlFor="task-completion">{completionPercentage}%</output>
                  </label>
                  <input
                    id="task-completion"
                    type="range"
                    min={0}
                    max={100}
                    step={1}
                    value={completionPercentage}
                    onChange={(event) => setCompletionPercentage(event.currentTarget.valueAsNumber)}
                    aria-label="Task completion percentage"
                    aria-valuetext={`${completionPercentage}% complete`}
                  />
                </div>
                <label className="check-row" htmlFor="task-divide">
                  <input
                    id="task-divide"
                    type="checkbox"
                    checked={isIndivisible}
                    onChange={(event) => setIsIndivisible(event.target.checked)}
                  />
                  <span>Must be completed in one sitting</span>
                </label>
                <div className="form-footer">
                  <button type="button" className="plain-button" onClick={() => setTaskFormOpen(false)}>Cancel</button>
                  <button type="submit" className="primary-button">Save task</button>
                </div>
              </form>
            )}

            <div className="task-list scroll-area" aria-live="polite">
              {tasks.length === 0 ? (
                <div className="empty-state todo-empty">
                  <div className="empty-illustration"><ClipboardList size={32} /></div>
                  <h3>Room for what matters.</h3>
                  <p>Your task list is looking peaceful. Add a task to get started.</p>
                  <button className="text-link" type="button" onClick={() => setTaskFormOpen(true)}><Plus size={16} /> Create your first task</button>
                </div>
              ) : (
                tasks.map((task) => (
                  <div className="task-row" key={task.id}>
                    <div className="task-content">
                      <span className="task-name">{task.name}</span>
                      <span className="task-deadline"><CalendarDays size={13} /> {formatDeadline(task.deadline)}</span>
                      <div className="task-progress-inline">
                        <label className="task-progress-label" htmlFor={`task-progress-${task.id}`}>
                          <span>Progress</span>
                          <output htmlFor={`task-progress-${task.id}`}>
                            {task.completionPercentage ?? 0}%
                          </output>
                        </label>
                        <input
                          id={`task-progress-${task.id}`}
                          type="range"
                          min={0}
                          max={100}
                          step={1}
                          value={task.completionPercentage ?? 0}
                          onChange={(event) =>
                            updateTask(task.id, {
                              completionPercentage: event.currentTarget.valueAsNumber,
                            })
                          }
                          aria-label={`Task completion percentage for ${task.name}`}
                          aria-valuetext={`${task.completionPercentage ?? 0}% complete`}
                        />
                      </div>
                      {editingTaskId === task.id && (
                        <div className="task-edit-controls">
                          <label>
                            Deadline
                            <input
                              type="date"
                              aria-label={`Deadline for ${task.name}`}
                              value={task.deadline}
                              required
                              onChange={(event) => {
                                // Clearing a date input emits an empty string; ignore it.
                                if (event.target.value) updateTask(task.id, { deadline: event.target.value });
                              }}
                            />
                          </label>
                          <label>
                            Estimated length (minutes)
                            <input
                              type="number"
                              min={1}
                              step={1}
                              value={task.estimatedLength ?? ""}
                              onChange={(event) => {
                                const value = event.currentTarget.value;
                                updateTask(task.id, {
                                  estimatedLength: value === "" ? null : Number(value),
                                });
                              }}
                              aria-label={`Estimated length in minutes for ${task.name}`}
                              required
                            />
                          </label>
                          <label className="task-edit-checkbox">
                            <input
                              type="checkbox"
                              aria-label={`Must be completed in one sitting: ${task.name}`}
                              checked={task.isIndivisible}
                              onChange={(event) => updateTask(task.id, { isIndivisible: event.target.checked })}
                            />
                            Must be completed in one sitting
                          </label>
                          <button type="button" className="plain-button" onClick={() => setEditingTaskId(null)}>Done</button>
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Edit deadline, divisibility and completion for ${task.name}`}
                      aria-expanded={editingTaskId === task.id}
                      onClick={() => setEditingTaskId((current) => current === task.id ? null : task.id)}
                    ><Pencil size={16} /></button>
                    <button
                      type="button"
                      className="icon-button delete-button"
                      aria-label={`Delete ${task.name}`}
                      onClick={() => deleteTask(task.id)}
                    ><Trash2 size={17} /></button>
                  </div>
                ))
              )}
            </div>
            <div className="panel-bottom"><span>Simulation priority is calculated automatically from deadlines and remaining effort.</span></div>
          </section>

          <div className="prediction-middle">
            <section className={`simulation-console${predictionLoading ? " is-running" : ""}`} aria-label="Simulation runner">
              <div className={`simulation-visual${predictionLoading ? " is-running" : ""}`} aria-hidden="true">
                <span className="simulation-orbit orbit-one" />
                <span className="simulation-orbit orbit-two" />
                <span className="simulation-core"><Sparkles size={21} /></span>
              </div>
              <div className="simulation-copy">
                <span className="simulation-kicker">
                  <span className={`simulation-live-dot${predictionLoading ? " is-running" : ""}`} />
                  {predictionLoading ? "SIMULATION IN PROGRESS" : completedSimulationCount !== null ? "LATEST SIMULATION" : "MONTE CARLO ENGINE"}
                </span>
                <h2>
                  {predictionLoading
                    ? "Exploring outcomes"
                    : completedSimulationCount !== null
                      ? "Results are ready"
                      : "See how your day could unfold"}
                </h2>
                <p>
                  {predictionLoading
                    ? `Evaluating ${simulationCount.toLocaleString()} simulations per scenario across your original and adjusted schedule.`
                    : completedSimulationCount !== null
                      ? `${completedSimulationCount.toLocaleString()} simulations per scenario completed. Review the risk summary and suggested changes.`
                      : `Compare your schedule across ${simulationCount.toLocaleString()} possible outcomes.`}
                </p>
              </div>
              <div className="simulation-count">
                <span>SIMULATIONS / SCENARIO</span>
                <strong>{simulationCount.toLocaleString()}</strong>
              </div>
              <button
                type="button"
                className="prediction-start-button"
                onClick={() => void startPrediction()}
                disabled={predictionLoading || tasks.length === 0}
                aria-label="Start simulation using current task list"
              >
                <Play size={17} />
                {predictionLoading ? "Running simulation..." : "Run simulation"}
              </button>
              {predictionMessage && <p className="prediction-status" role="status">{predictionMessage}</p>}
              <p className="simulation-footnote">A fresh set of scenarios is evaluated for each prediction.</p>
            </section>
          </div>

          <div className="right-stack">
            <section className="panel info-panel" aria-labelledby="info-heading">
              <div className="panel-heading compact-heading">
                <div className="heading-text">
                  <div className="section-icon peach"><BookOpen size={20} /></div>
                  <div>
                    <h2 id="info-heading">Information cards</h2>
                    <p>Generated insights from your AI</p>
                  </div>
                </div>
                <div className="ai-label"><span className="ai-pulse" /> AI SPACE</div>
              </div>
              <div className="cards-scroll scroll-area" aria-live="polite">
                {shownCards.length === 0 ? (
                  <div className="small-empty-state"><div className="empty-ring"><BookOpen size={24} /></div><h3>AI information</h3><p>Information cards generated by your LLM will appear here.</p></div>
                ) : (
                  shownCards.map((card) => (
                    <article className="info-card" key={card.id}>
                      {card.category && <div className="card-topline"><span className="card-category">{card.category}</span></div>}
                      <h3>{card.title}</h3>
                      <p>{card.description}</p>
                    </article>
                  ))
                )}
              </div>
            </section>

            <section className="panel suggestions-panel" aria-labelledby="suggestions-heading">
              <div className="panel-heading compact-heading">
                <div className="heading-text">
                  <div className="section-icon mint"><Sparkles size={20} /></div>
                  <div><h2 id="suggestions-heading">Suggestions</h2><p>A little help from AI</p></div>
                </div>
                <div className="ai-label"><span className="ai-pulse" /> AI SPACE</div>
              </div>
              <div className="suggestions-content scroll-area" aria-live="polite">
                {shownSuggestion.trim() ? (
                  <div className="llm-output"><span className="llm-heading"><Sparkles size={16} /> Your latest suggestions</span><p>{shownSuggestion}</p></div>
                ) : (
                  <div className="suggestion-empty"><div className="suggestion-glow"><Lightbulb size={29} /></div><h3>Fresh ideas, when you need them.</h3><p>Once you connect your LLM, its personalised suggestions will appear right here.</p><span className="llm-hint"><CircleHelp size={14} /> Add your response in <code>app/page.tsx</code></span></div>
                )}
              </div>
            </section>
          </div>
        </div>
        ) : (
          <section className="settings-panel" aria-labelledby="settings-heading">
            <div className="settings-panel-heading">
              <div className="section-icon lilac"><Settings size={20} /></div>
              <div>
                <h2 id="settings-heading">Simulation preferences</h2>
                <p>These settings are saved in this browser and used for your next prediction.</p>
              </div>
            </div>
            <div className="settings-fields">
              <label className="transport-preference" htmlFor="preferred-transport-mode">
                Preferred transport
                <select
                  id="preferred-transport-mode"
                  value={preferredTransportMode}
                  onChange={(event) =>
                    setPreferredTransportMode(event.target.value as TransportMode)
                  }
                >
                  <option value="fastest">Fastest available</option>
                  <option value="walking">Walking</option>
                  <option value="transit">Public transport</option>
                  <option value="cycling">Cycling</option>
                </select>
                <span className="settings-help">
                  Used as the preferred mode when estimating travel time. Weather can affect walking and cycling.
                </span>
              </label>
              <label className="transport-preference" htmlFor="home-location">
                Home / day-start location
                <input
                  id="home-location"
                  type="text"
                  value={homeLocation}
                  onChange={(event) => setHomeLocation(event.target.value)}
                  maxLength={200}
                  placeholder="e.g. St. Catherine's College"
                  autoComplete="street-address"
                />
                <span className="settings-help">
                  The simulator uses this as the starting point for your day.
                </span>
              </label>
              <label className="transport-preference" htmlFor="simulation-count">
                Simulations per scenario
                <input
                  id="simulation-count"
                  type="number"
                  min={1}
                  max={1000000}
                  step={1000}
                  value={simulationCount}
                  onChange={(event) =>
                    setSimulationCount(event.currentTarget.value === "" ? 0 : event.currentTarget.valueAsNumber)
                  }
                  aria-describedby="simulation-count-help"
                />
                <span className="settings-help" id="simulation-count-help">
                  The default is 10,000. Higher counts can improve stability but take longer to run.
                  Allowed range: 1 to 1,000,000.
                </span>
              </label>
              <div className="work-hours-setting">
                <h3>Work hours</h3>
                <p className="settings-help">
                  Adjust each time independently. The end time must be after the start time.
                </p>
                <label htmlFor="workday-start">
                  <span>Start: <strong>{formatHour(workdayStartHour)}</strong></span>
                  <input
                    id="workday-start"
                    type="range"
                    min={0}
                    max={23}
                    step={1}
                    value={workdayStartHour}
                    onChange={(event) => setWorkdayStartHour(event.currentTarget.valueAsNumber)}
                  />
                </label>
                <label htmlFor="workday-end">
                  <span>End: <strong>{formatHour(workdayEndHour)}</strong></span>
                  <input
                    id="workday-end"
                    type="range"
                    min={1}
                    max={24}
                    step={1}
                    value={workdayEndHour}
                    onChange={(event) => setWorkdayEndHour(event.currentTarget.valueAsNumber)}
                  />
                </label>
                {workdayEndHour <= workdayStartHour && (
                  <p className="work-hours-error" role="alert">
                    End time must be later than start time.
                  </p>
                )}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
