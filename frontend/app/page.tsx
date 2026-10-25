import Dashboard from "@/components/dashboard";

export default async function HomePage() {
  // =====================================================================
  // INSERT YOUR LLM RESPONSE HERE
  // Replace the empty string with text returned by your server-side LLM.
  // Example: const suggestionText = await myLLMFunction();
  // Keep LLM API keys and provider calls on the server, not in the browser.
  // =====================================================================
  const suggestionText = "";

  return (
    <Dashboard
      suggestionText={suggestionText}
    />
  );
}
