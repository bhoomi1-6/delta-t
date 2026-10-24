import { auth } from "@/auth";
import Dashboard from "@/components/dashboard";

export default async function HomePage() {
  // The rest of the dashboard works even before OAuth credentials are configured.
  const calendarConfigured = Boolean(
    process.env.AUTH_SECRET &&
      process.env.AUTH_SECRET !== "replace-with-a-long-random-secret" &&
      process.env.AUTH_GOOGLE_ID &&
      process.env.AUTH_GOOGLE_SECRET
  );
  const session = calendarConfigured ? await auth() : null;

  // =====================================================================
  // INSERT YOUR LLM RESPONSE HERE
  // Replace the empty string with text returned by your server-side LLM.
  // Example: const suggestionText = await myLLMFunction();
  // Keep LLM API keys and provider calls on the server, not in the browser.
  // =====================================================================
  const suggestionText = "";

  return (
    <Dashboard
      calendarConfigured={calendarConfigured}
      calendarConnected={session?.calendarConnected === true}
      calendarEmail={session?.user?.email ?? null}
      suggestionText={suggestionText}
    />
  );
}
