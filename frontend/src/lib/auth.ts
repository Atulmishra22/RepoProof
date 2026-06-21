import { NextAuthOptions } from "next-auth";
import GithubProvider from "next-auth/providers/github";
import { PostgresAdapter } from "./auth-adapter";

export const authOptions: NextAuthOptions = {
  adapter: PostgresAdapter(),
  session: {
    strategy: "database",
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  providers: [
    GithubProvider({
      clientId: process.env.GITHUB_CLIENT_ID || "",
      clientSecret: process.env.GITHUB_CLIENT_SECRET || "",
    }),
  ],
  callbacks: {
    async session({ session, user }) {
      if (session.user) {
        (session.user as any).id = user.id;
        (session.user as any).subscription_tier = (user as any).subscription_tier;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
};
