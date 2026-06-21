import { redirect } from "next/navigation";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import ApiInterceptor from "@/components/ApiInterceptor";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await getServerSession(authOptions);

  if (!session) {
    redirect("/login");
  }

  return (
    <>
      <ApiInterceptor />
      <div className="flex-1 flex flex-col">
        {children}
      </div>
    </>
  );
}
