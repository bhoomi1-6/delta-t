import "next-auth";

declare module "next-auth" {
  interface Session {
    calendarConnected?: boolean;
  }
}
