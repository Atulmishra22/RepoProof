import { NextAuthOptions } from "next-auth";
import GithubProvider from "next-auth/providers/github";
import { PostgresAdapter } from "./auth-adapter";
import { dbPool } from "./db";

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
      allowDangerousEmailAccountLinking: true,
    }),
  ],
  callbacks: {
    async signIn({ user, account, profile }) {
      // Extract GitHub username from OAuth profile and save to user record
      if (account?.provider === "github" && profile?.login) {
        try {
          console.log(
            `[AUTH] Linking GitHub OAuth for user ${user.id}, username: ${(profile as any).login}`
          );
          // Update user with github_username and auth_provider
          // Also update email if it's the noreply email (to keep the real email)
          const updateRes = await dbPool.query(
            `UPDATE users 
             SET github_username = $1, 
                 auth_provider = 'github',
                 image = COALESCE($3, image),
                 name = COALESCE($4, name)
             WHERE id = $2
             RETURNING id, github_username, auth_provider`,
            [
              (profile as any).login,
              user.id,
              profile.avatar_url || null,
              profile.name || null,
            ]
          );
          console.log("[AUTH] User updated with GitHub info:", updateRes.rows[0]);
        } catch (error) {
          console.error("[AUTH] Failed to update github_username:", error);
        }
      }
      return true;
    },
    async session({ session, user }) {
      if (session.user) {
        (session.user as any).id = user.id;
        (session.user as any).subscription_tier = (user as any).subscription_tier;
        (session.user as any).github_username = (user as any).github_username;
        (session.user as any).auth_provider = (user as any).auth_provider;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
};
