import { Adapter, AdapterUser, AdapterSession, VerificationToken } from "next-auth/adapters";
import { dbPool } from "./db";

export function PostgresAdapter(): Adapter {
  return {
    async createUser(user: Omit<AdapterUser, "id">) {
      const { email, emailVerified, image, name } = user;
      const res = await dbPool.query(
        `INSERT INTO users (email, "emailVerified", image, name, subscription_tier, is_active, auth_provider)
         VALUES ($1, $2, $3, $4, 'free', true, 'github')
         RETURNING id, email, "emailVerified", image, name`,
        [email, emailVerified, image, name]
      );
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        email: row.email,
        emailVerified: row.emailVerified,
        image: row.image,
        name: row.name,
      };
    },

    async getUser(id: string) {
      const res = await dbPool.query(
        `SELECT id, email, "emailVerified", image, name FROM users WHERE id = $1`,
        [id]
      );
      if (res.rows.length === 0) return null;
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        email: row.email,
        emailVerified: row.emailVerified,
        image: row.image,
        name: row.name,
      };
    },

    async getUserByEmail(email: string) {
      const res = await dbPool.query(
        `SELECT id, email, "emailVerified", image, name FROM users WHERE email = $1`,
        [email]
      );
      if (res.rows.length === 0) return null;
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        email: row.email,
        emailVerified: row.emailVerified,
        image: row.image,
        name: row.name,
      };
    },

    async getUserByAccount({ providerAccountId, provider }: { providerAccountId: string; provider: string }) {
      const res = await dbPool.query(
        `SELECT u.id, u.email, u."emailVerified", u.image, u.name 
         FROM users u
         JOIN accounts a ON u.id = a."userId"
         WHERE a.provider = $1 AND a."providerAccountId" = $2`,
        [provider, providerAccountId]
      );
      if (res.rows.length === 0) return null;
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        email: row.email,
        emailVerified: row.emailVerified,
        image: row.image,
        name: row.name,
      };
    },

    async updateUser(user: Partial<AdapterUser> & Pick<AdapterUser, "id">) {
      const { id, email, emailVerified, image, name } = user;
      const res = await dbPool.query(
        `UPDATE users 
         SET email = COALESCE($2, email),
             "emailVerified" = COALESCE($3, "emailVerified"),
             image = COALESCE($4, image),
             name = COALESCE($5, name)
         WHERE id = $1
         RETURNING id, email, "emailVerified", image, name`,
        [id, email, emailVerified, image, name]
      );
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        email: row.email,
        emailVerified: row.emailVerified,
        image: row.image,
        name: row.name,
      };
    },

    async deleteUser(userId: string) {
      await dbPool.query(`DELETE FROM users WHERE id = $1`, [userId]);
    },

    async linkAccount(account: any) {
      await dbPool.query(
        `INSERT INTO accounts (
          "userId", type, provider, "providerAccountId", 
          refresh_token, access_token, expires_at, 
          token_type, scope, id_token, session_state
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
        [
          account.userId,
          account.type,
          account.provider,
          account.providerAccountId,
          account.refresh_token || null,
          account.access_token || null,
          account.expires_at || null,
          account.token_type || null,
          account.scope || null,
          account.id_token || null,
          account.session_state || null,
        ]
      );
    },

    async unlinkAccount({ providerAccountId, provider }: { providerAccountId: string; provider: string }) {
      await dbPool.query(
        `DELETE FROM accounts WHERE provider = $1 AND "providerAccountId" = $2`,
        [provider, providerAccountId]
      );
    },

    async createSession({ sessionToken, userId, expires }: { sessionToken: string; userId: string; expires: Date }) {
      const res = await dbPool.query(
        `INSERT INTO sessions ("sessionToken", "userId", expires)
         VALUES ($1, $2, $3)
         RETURNING id, "sessionToken", "userId", expires`,
        [sessionToken, userId, expires]
      );
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        sessionToken: row.sessionToken,
        userId: row.userId.toString(),
        expires: new Date(row.expires),
      };
    },

    async getSessionAndUser(sessionToken: string) {
      const sessionRes = await dbPool.query(
        `SELECT id, "sessionToken", "userId", expires FROM sessions WHERE "sessionToken" = $1`,
        [sessionToken]
      );
      if (sessionRes.rows.length === 0) return null;
      const session = sessionRes.rows[0];
      
      const userRes = await dbPool.query(
        `SELECT id, email, "emailVerified", image, name FROM users WHERE id = $1`,
        [session.userId]
      );
      if (userRes.rows.length === 0) return null;
      const user = userRes.rows[0];

      return {
        session: {
          id: session.id.toString(),
          sessionToken: session.sessionToken,
          userId: session.userId.toString(),
          expires: new Date(session.expires),
        },
        user: {
          id: user.id.toString(),
          email: user.email,
          emailVerified: user.emailVerified,
          image: user.image,
          name: user.name,
        },
      };
    },

    async updateSession({ sessionToken, expires }: { sessionToken: string; expires?: Date }) {
      const res = await dbPool.query(
        `UPDATE sessions 
         SET expires = COALESCE($2, expires)
         WHERE "sessionToken" = $1
         RETURNING id, "sessionToken", "userId", expires`,
        [sessionToken, expires]
      );
      if (res.rows.length === 0) return null;
      const row = res.rows[0];
      return {
        id: row.id.toString(),
        sessionToken: row.sessionToken,
        userId: row.userId.toString(),
        expires: new Date(row.expires),
      };
    },

    async deleteSession(sessionToken: string) {
      // Call FastAPI backend to clear Redis cache and DB simultaneously
      const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      await fetch(`${backendUrl}/api/v1/auth/signout`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${sessionToken}`
        }
      }).catch(err => {
        console.error("FastAPI signout propagation failed, falling back to direct DB delete:", err);
      });
      // Fallback/Ensure DB row is deleted
      await dbPool.query(`DELETE FROM sessions WHERE "sessionToken" = $1`, [sessionToken]);
    },

    async createVerificationToken({ identifier, expires, token }: VerificationToken) {
      const res = await dbPool.query(
        `INSERT INTO verification_tokens (identifier, expires, token)
         VALUES ($1, $2, $3)
         RETURNING identifier, expires, token`,
        [identifier, expires, token]
      );
      const row = res.rows[0];
      return {
        identifier: row.identifier,
        expires: new Date(row.expires),
        token: row.token,
      };
    },

    async useVerificationToken({ identifier, token }: { identifier: string; token: string }) {
      const res = await dbPool.query(
        `DELETE FROM verification_tokens 
         WHERE identifier = $1 AND token = $2
         RETURNING identifier, expires, token`,
        [identifier, token]
      );
      if (res.rows.length === 0) return null;
      const row = res.rows[0];
      return {
        identifier: row.identifier,
        expires: new Date(row.expires),
        token: row.token,
      };
    },
  };
}
