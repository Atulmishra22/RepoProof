import { NextRequest, NextResponse } from "next/server";
import { dbPool } from "@/lib/db";
import crypto from "crypto";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const { email, password, name, subscription_tier } = body;

    if (!email || !password) {
      return NextResponse.json(
        { success: false, error: "Email and password are required." },
        { status: 400 }
      );
    }

    const targetTier = subscription_tier || "FREE";

    // 1. Check if user already exists
    const checkRes = await dbPool.query("SELECT * FROM users WHERE email = $1", [email]);
    if (checkRes.rows.length > 0) {
      return NextResponse.json(
        { success: false, error: "User already registered with this email." },
        { status: 400 }
      );
    }

    // 2. Hash password using PBKDF2
    const salt = crypto.randomBytes(16).toString("hex");
    const hash = crypto.pbkdf2Sync(password, salt, 1000, 64, "sha512").toString("hex");
    const passwordHash = `pbkdf2_sha512$1000$${salt}$${hash}`;

    // 3. Insert user
    await dbPool.query(
      `INSERT INTO users (email, name, password_hash, subscription_tier, is_active)
       VALUES ($1, $2, $3, $4, true)`,
      [email, name || "Developer User", passwordHash, targetTier]
    );

    return NextResponse.json({ success: true, message: "User registered successfully." });
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
