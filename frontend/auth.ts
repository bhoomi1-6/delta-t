import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

// Least-privilege read-only access to Google Calendar events.
const calendarScope = "https://www.googleapis.com/auth/calendar.events.readonly";

export const { handlers, auth } = NextAuth({
  session: { strategy: "jwt" },
  providers: [
    Google({
      authorization: {
        params: {
          scope: `openid email profile ${calendarScope}`,
        },
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      // Verify that Google actually granted the requested Calendar scope.
      if (account?.provider === "google") {
        token.calendarConnected =
          account.scope?.split(" ").includes(calendarScope) ?? false;
      }
      return token;
    },
    async session({ session, token }) {
      session.calendarConnected = token.calendarConnected === true;
      return session;
    },
  },
});
