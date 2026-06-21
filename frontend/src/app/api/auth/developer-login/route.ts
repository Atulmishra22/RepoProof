import { NextRequest, NextResponse } from "next/server";
import { dbPool } from "@/lib/db";
import crypto from "crypto";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const email = body.email;
    const password = body.password;

    if (!email || !password) {
      return NextResponse.json(
        { success: false, error: "Email and password are required." },
        { status: 400 }
      );
    }

    const emailLower = email.trim().toLowerCase();

    // 1. Get user
    let userRes = await dbPool.query("SELECT * FROM users WHERE email = $1", [emailLower]);
    let user = userRes.rows[0];

    // Auto-seed developer@repoproof.com with password 'devpass' if it does not exist
    if (!user && emailLower === "developer@repoproof.com") {
      const salt = crypto.randomBytes(16).toString("hex");
      const hash = crypto.pbkdf2Sync("devpass", salt, 100000, 64, "sha512").toString("hex");
      const passwordHash = `pbkdf2_sha512$100000$${salt}$${hash}`;
      const insertRes = await dbPool.query(
        `INSERT INTO users (email, name, password_hash, subscription_tier, is_active, auth_provider)
         VALUES ($1, 'Developer User', $2, 'pro', true, 'credentials')
         RETURNING *`,
        [emailLower, passwordHash]
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
      const iterations = parseInt(parts[1], 10) || 1000;
      const salt = parts[2];
      const storedHash = parts[3];
      const incomingHash = crypto.pbkdf2Sync(password, salt, iterations, 64, "sha512").toString("hex");

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
    if (body.subscription_tier && body.subscription_tier.toLowerCase() !== user.subscription_tier) {
      const tierLower = body.subscription_tier.toLowerCase();
      await dbPool.query(
        "UPDATE users SET subscription_tier = $1 WHERE id = $2",
        [tierLower, user.id]
      );
      user.subscription_tier = tierLower;
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
