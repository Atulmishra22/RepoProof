import { NextRequest, NextResponse } from "next/server";
import { dbPool } from "@/lib/db";
import crypto from "crypto";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const email = body.email || "developer@repoproof.com";
    const name = body.name || "Developer User";
    const image = body.image || "https://avatars.githubusercontent.com/u/9919?v=4"; // Octocat
    const subscription_tier = body.subscription_tier || "FREE";

    // 1. Get or create user
    let userRes = await dbPool.query("SELECT * FROM users WHERE email = $1", [email]);
    let user = userRes.rows[0];

    if (!user) {
      const insertRes = await dbPool.query(
        `INSERT INTO users (email, name, image, subscription_tier, is_active)
         VALUES ($1, $2, $3, $4, true)
         RETURNING *`,
        [email, name, image, subscription_tier]
      );
      user = insertRes.rows[0];
    } else {
      // Update subscription tier if specified
      if (body.subscription_tier) {
        await dbPool.query(
          "UPDATE users SET subscription_tier = $1 WHERE id = $2",
          [subscription_tier, user.id]
        );
        user.subscription_tier = subscription_tier;
      }
    }

    // 2. Generate session token
    const sessionToken = crypto.randomUUID();
    const expires = new Date();
    expires.setDate(expires.getDate() + 30); // 30 days

    // 3. Create session in database
    await dbPool.query(
      `INSERT INTO sessions ("sessionToken", "userId", expires)
       VALUES ($1, $2, $3)`,
      [sessionToken, user.id, expires]
    );

    // 4. Set cookie
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
