import { DashboardSkeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div className="min-h-screen bg-background">
      <DashboardSkeleton statCount={4} />
    </div>
  );
}
