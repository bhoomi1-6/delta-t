"use client";

import { useEffect, useState, type FormEvent } from "react";
import { signIn, signOut } from "next-auth/react";
import {
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  CircleHelp,
  ClipboardList,
  LayoutDashboard,
  Lightbulb,
  Link2,
  Plus,
  Pencil,
  Play,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

type Priority = "low" | "medium" | "high";

type Task = {
  id: string;
  name: string;
  deadline: string; // Local YYYY-MM-DD date, without timezone shifting.
  priority: Priority;
  canBeDivided: boolean;
  completionPercentage: number; // 0-100, not a completed/not-completed flag.
  estimatedLength: number | null; // Required before predicting; legacy tasks may lack it.
};

export type InfoCard = {
  id: string;
  title: string;
  description: string;
  category?: string;
};

type DashboardProps = {
  calendarConfigured: boolean;
  calendarConnected: boolean;
  calendarEmail: string | null;
  suggestionText: string;
  /** Cards generated on the server by your LLM, not manually added. */
  informationCards?: InfoCard[];
};

function useLocalCollection<T>(storageKey: string) {
  const [items, setItems] = useState<T[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(storageKey);
      if (stored) {
        const parsed: unknown = JSON.parse(stored);
        if (Array.isArray(parsed)) setItems(parsed as T[]);
      }
    } catch {
      // An invalid or blocked localStorage entry should not break the UI.
    } finally {
      setLoaded(true);
    }
  }, [storageKey]);

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
  calendarConfigured,
  calendarConnected,
  calendarEmail,
  suggestionText,
  // Supply informationCards from your LLM in app/page.tsx.
  informationCards = [],
}: DashboardProps) {
  const [tasks, setTasks] = useLocalCollection<Task>("flowboard:tasks:v1");
  const [taskFormOpen, setTaskFormOpen] = useState(false);
  const [calendarMenuOpen, setCalendarMenuOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionMessage, setPredictionMessage] = useState("");

  const [taskName, setTaskName] = useState("");
  const [deadline, setDeadline] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [canBeDivided, setCanBeDivided] = useState(false);
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
        priority,
        canBeDivided,
        completionPercentage,
        estimatedLength: duration,
      },
    ]);
    setTaskName("");
    setDeadline("");
    setPriority("medium");
    setCanBeDivided(false);
    setCompletionPercentage(0);
    setEstimatedLength("");
    setTaskFormOpen(false);
  }

  function deleteTask(id: string) {
    setTasks((existing) => existing.filter((task) => task.id !== id));
  }

  function updateTask(id: string, changes: Partial<Pick<Task, "deadline" | "priority" | "canBeDivided" | "completionPercentage" | "estimatedLength">>) {
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
    try {
      // Python converts dashboard fields into engine Task objects:
      // name -> title, completionPercentage -> completion_pct,
      // estimatedLength -> estimated_length, priority label -> 0/1/2,
      // canBeDivided -> can_be_divided, date -> end-of-day datetime.
      const response = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tasks: tasks.map((task) => ({
            ...task,
            completionPercentage: task.completionPercentage ?? 0,
          })),
        }),
      });
      if (!response.ok) throw new Error(`Prediction request failed (${response.status})`);
      const data: { success: boolean; tasks: unknown[] } = await response.json();
      setPredictionMessage(`${data.tasks.length} task(s) sent to the prediction backend.`);
      // The backend now returns Task objects, NOT information cards.
      // You can use data.tasks later when displaying prediction results.
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
          <div className="brand-icon" aria-hidden="true">
            <CheckCheck size={21} strokeWidth={2.8} />
          </div>
          <span className="brand-name">flowboard<span className="brand-period">.</span></span>
          <span className="topbar-divider" />
          <span className="active-navigation">
            <LayoutDashboard size={16} strokeWidth={2.2} /> Dashboard
          </span>
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
              <span>{calendarConnected ? "Calendar linked" : "Google Calendar"}</span>
              {calendarConnected && <span className="connection-dot" />}
              <ChevronDown size={15} />
            </button>

            {calendarMenuOpen && (
              <div className="calendar-dropdown" role="menu">
                <div className="dropdown-eyebrow">GOOGLE CALENDAR</div>
                {calendarConnected ? (
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
                ) : (
                  <>
                    <p className="dropdown-help">
                      {calendarConfigured
                        ? "Connect your Google account with read-only Calendar events permission."
                        : "Add your Google OAuth credentials to .env.local to activate this connection."}
                    </p>
                    <button
                      className="dropdown-action"
                      type="button"
                      role="menuitem"
                      disabled={!calendarConfigured}
                      onClick={() => void signIn("google", { redirectTo: "/" })}
                    >
                      <Link2 size={16} /> Connect Google Calendar
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
          <div className="avatar" aria-label="Personal workspace">F</div>
        </div>
      </header>

      <main className="dashboard-main">
        <div className="page-intro">
          <div>
            <span className="eyebrow"><span className="eyebrow-dot" /> YOUR PRODUCTIVITY HUB</span>
            <h1>Your dashboard <span className="wave" aria-hidden="true">✳</span></h1>
            <p>One calm place for everything you need to get done.</p>
          </div>
        </div>

        <style>{`
          .dashboard-grid.prediction-layout {
            grid-template-columns: minmax(0, 1fr) 144px minmax(0, 1fr);
            gap: 14px;
          }
          .prediction-middle {
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 12px;
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
            padding: 14px 10px;
            font-size: 12px;
            font-weight: 800;
            color: white;
            background: linear-gradient(145deg, #806df3, #705ae6);
            box-shadow: 0 6px 16px #8069e629;
          }
          .prediction-status {
            color: #737b92;
            font-size: 11px;
            line-height: 1.5;
            text-align: center;
            overflow-wrap: anywhere;
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
          @media (max-width: 1050px) and (min-width: 761px) {
            .dashboard-grid.prediction-layout {
              grid-template-columns: minmax(0, 1fr) 112px minmax(0, 1fr);
              gap: 10px;
            }
            .prediction-start-button { flex-direction: column; text-align: center; }
          }
          @media (max-width: 760px) {
            .dashboard-grid.prediction-layout { display: flex; flex-direction: column; }
            .prediction-middle { padding: 0 12px; }
            .prediction-start-button { width: min(100%, 260px); }
          }
        `}</style>
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
                <div className="field-grid">
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
                  <div>
                    <label htmlFor="task-priority">Priority label</label>
                    <select
                      id="task-priority"
                      value={priority}
                      onChange={(event) => setPriority(event.target.value as Priority)}
                    >
                      <option value="low">Low priority</option>
                      <option value="medium">Medium priority</option>
                      <option value="high">High priority</option>
                    </select>
                  </div>
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
                    checked={canBeDivided}
                    onChange={(event) => setCanBeDivided(event.target.checked)}
                  />
                  <span>This task can be divided</span>
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
                    <span
                      className={`priority-dot priority-${task.priority}`}
                      title={`${task.priority} priority${task.canBeDivided ? "; can be divided" : ""}`}
                      aria-label={`${task.priority} priority`}
                    />
                    <div className="task-content">
                      <span className="task-name">{task.name}</span>
                      <span className="task-deadline"><CalendarDays size={13} /> {formatDeadline(task.deadline)}</span>
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
                            Priority
                            <select
                              aria-label={`Priority for ${task.name}`}
                              value={task.priority}
                              onChange={(event) => updateTask(task.id, { priority: event.target.value as Priority })}
                            >
                              <option value="low">Low</option>
                              <option value="medium">Medium</option>
                              <option value="high">High</option>
                            </select>
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
                              aria-label={`This task can be divided: ${task.name}`}
                              checked={task.canBeDivided}
                              onChange={(event) => updateTask(task.id, { canBeDivided: event.target.checked })}
                            />
                            This task can be divided
                          </label>
                          <div className="task-edit-progress">
                            <label className="completion-field-label" htmlFor={`task-completion-${task.id}`}>
                              <span>Task completion</span>
                              <output htmlFor={`task-completion-${task.id}`}>
                                {task.completionPercentage ?? 0}%
                              </output>
                            </label>
                            <input
                              id={`task-completion-${task.id}`}
                              type="range"
                              min={0}
                              max={100}
                              step={1}
                              value={task.completionPercentage ?? 0}
                              onChange={(event) => updateTask(task.id, { completionPercentage: event.currentTarget.valueAsNumber })}
                              aria-label={`Task completion percentage for ${task.name}`}
                              aria-valuetext={`${task.completionPercentage ?? 0}% complete`}
                            />
                          </div>
                          <button type="button" className="plain-button" onClick={() => setEditingTaskId(null)}>Done</button>
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Edit priority, deadline, divisibility and completion for ${task.name}`}
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
            <div className="panel-bottom"><span><span className="legend-dot" /> Coloured dots indicate priority</span></div>
          </section>

          <div className="prediction-middle">
            <button
              type="button"
              className="prediction-start-button"
              onClick={() => void startPrediction()}
              disabled={predictionLoading || tasks.length === 0}
              aria-label="Start Prediction using current task list"
            >
              <Play size={17} />
              {predictionLoading ? "Sending..." : "Start Prediction"}
            </button>
            {predictionMessage && <p className="prediction-status" role="status">{predictionMessage}</p>}
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
                {informationCards.length === 0 ? (
                  <div className="small-empty-state"><div className="empty-ring"><BookOpen size={24} /></div><h3>AI information</h3><p>Information cards generated by your LLM will appear here.</p></div>
                ) : (
                  informationCards.map((card) => (
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
                {suggestionText.trim() ? (
                  <div className="llm-output"><span className="llm-heading"><Sparkles size={16} /> Your latest suggestions</span><p>{suggestionText}</p></div>
                ) : (
                  <div className="suggestion-empty"><div className="suggestion-glow"><Lightbulb size={29} /></div><h3>Fresh ideas, when you need them.</h3><p>Once you connect your LLM, its personalised suggestions will appear right here.</p><span className="llm-hint"><CircleHelp size={14} /> Add your response in <code>app/page.tsx</code></span></div>
                )}
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}
