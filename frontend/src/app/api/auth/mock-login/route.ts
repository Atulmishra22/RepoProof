import { NextRequest, NextResponse } from "next/server";
import { dbPool } from "@/lib/db";
import crypto from "crypto";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const email = body.email || "developer@repoproof.com";
    const password = body.password;

    if (!email || !password) {
      return NextResponse.json(
        { success: false, error: "Email and password are required." },
        { status: 400 }
      );
    }

    // 1. Get user
    let userRes = await dbPool.query("SELECT * FROM users WHERE email = $1", [email]);
    let user = userRes.rows[0];

    // Auto-seed developer@repoproof.com with password 'devpass' if it does not exist
    if (!user && email === "developer@repoproof.com") {
      const salt = crypto.randomBytes(16).toString("hex");
      const hash = crypto.pbkdf2Sync("devpass", salt, 1000, 64, "sha512").toString("hex");
      const passwordHash = `pbkdf2_sha512$1000$${salt}$${hash}`;
      const insertRes = await dbPool.query(
        `INSERT INTO users (email, name, password_hash, subscription_tier, is_active)
         VALUES ($1, 'Developer User', $2, 'PRO', true)
         RETURNING *`,
        [email, passwordHash]
      );
      user = insertRes.rows[0];
    }

    if (!user) {
      return NextResponse.json(
        { success: false, error: "Invalid email or password." },
        { status: 401 }
      );
    }

    if (!user.password_hash) {
      return NextResponse.json(
        { success: false, error: "This account only supports GitHub login." },
        { status: 401 }
      );
    }

    // 2. Verify password hash
    try {
      const parts = user.password_hash.split("$");
      const salt = parts[2];
      const storedHash = parts[3];
      const incomingHash = crypto.pbkdf2Sync(password, salt, 1000, 64, "sha512").toString("hex");

      if (incomingHash !== storedHash) {
        return NextResponse.json(
          { success: false, error: "Invalid email or password." },
          { status: 401 }
        );
      }
    } catch (err) {
      return NextResponse.json(
        { success: false, error: "Failed to verify password credentials." },
        { status: 500 }
      );
    }

    // Update subscription tier in development if specified
    if (body.subscription_tier && body.subscription_tier !== user.subscription_tier) {
      await dbPool.query(
        "UPDATE users SET subscription_tier = $1 WHERE id = $2",
        [body.subscription_tier, user.id]
      );
      user.subscription_tier = body.subscription_tier;
    }

    // 3. Generate session token
    const sessionToken = crypto.randomUUID();
    const expires = new Date();
    expires.setDate(expires.getDate() + 30); // 30 days

    // 4. Create session in database
    await dbPool.query(
      `INSERT INTO sessions ("sessionToken", "userId", expires)
       VALUES ($1, $2, $3)`,
      [sessionToken, user.id, expires]
    );

    // 5. Set cookie
    const isSecure = req.url.startsWith("https://");
    const cookieName = isSecure ? "__Secure-next-auth.session-token" : "next-auth.session-token";

    const response = NextResponse.json({
      success: true,
      user: {
        id: user.id,
        email: user.email,
        name: user.name,
        subscription_tier: user.subscription_tier,
      },
    });

    response.cookies.set(cookieName, sessionToken, {
      httpOnly: true,
      secure: isSecure,
      expires: expires,
      path: "/",
      sameSite: "lax",
    });

    return response;
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
